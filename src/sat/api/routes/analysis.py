"""POST /api/analysis — start a new analysis run in the background.

@decision DEC-API-004
@title asyncio.create_task for fire-and-forget pipeline execution
@status accepted
@rationale run_analysis is a long-running async coroutine (seconds to minutes).
We launch it as a background task so the POST returns immediately with a run_id
and ws_url. The frontend connects to the WebSocket to observe progress. Using
asyncio.create_task (rather than a thread pool) keeps everything on the same
event loop, so EventBus callbacks can safely call ws.send_json() without
cross-thread coordination.

@decision DEC-CONCURRENCY-003
@title Analysis route uses start_or_queue instead of direct asyncio.create_task
@status accepted
@rationale Using manager.start_or_queue() instead of asyncio.create_task()
directly enforces the concurrency cap transparently. The analysis route doesn't
need to know the cap or queue logic — RunManager owns that. The response now
includes queue_position so the frontend can show "queued" state immediately
on submit without waiting for a WebSocket event.

@decision DEC-API-015
@title Quick-run path persists evidence.json best-effort after pipeline completes
@status accepted
@rationale POST /api/analysis (quick-run path) previously never persisted a
structured EvidencePool — research results and decomposition facts lived only
in the flat config.evidence string. After run_analysis() returns output_path,
we call build_evidence_pool() to reconstruct a structured pool from the pipeline
artifact files (*-research.json, *-decomposition.json) and persist it via
persist_evidence(). This makes GET /api/runs/{run_id}/evidence work for quick-run
outputs, giving the frontend a uniform evidence API for both paths. The block is
best-effort: any exception is logged and swallowed so evidence persistence never
masks a real pipeline failure. Empty pools (no artifacts produced) are not
written — nothing to persist when items is empty.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from sat.adversarial.config import AdversarialConfig, build_adversarial_config
from sat.api.auth import verify_token
from sat.api.models import AnalysisRequest, AnalysisResponse
from sat.api.run_manager import ActiveRun, RunManager
from sat.config import (
    AnalysisConfig,
    GapResolutionConfig,
    ProviderConfig,
    ReportConfig,
    ResearchConfig,
    get_default_runs_dir,
)
from sat.pipeline import run_analysis

if TYPE_CHECKING:
    from sat.providers.rate_limiter import ProviderRateLimiter

logger = logging.getLogger(__name__)


def _validate_output_dir(output_dir: str) -> Path:
    """Validate that output_dir is safe: either relative (within CWD) or absolute
    within the configured runs directory.

    Accepts:
    - Relative paths without '..' — resolved against CWD (CLI compat, "." is fine)
    - Absolute paths that are within get_default_runs_dir() — the stable location
      for packaged app runs

    Rejects:
    - Relative paths containing '..' traversal sequences
    - Absolute paths outside both CWD and the configured runs directory

    Returns the resolved Path on success, raises HTTPException(400) on failure.

    @decision DEC-SEC-006
    @title output_dir validated against CWD and runs dir to prevent path traversal
    @status accepted
    @rationale An unchecked output_dir allows callers to write run artifacts
    to arbitrary filesystem locations (e.g. ../../etc). The check now accepts
    two safe bases: CWD (for CLI compat, relative paths) and ~/.sat/runs/
    (for packaged app use). Symlinks are resolved (realpath) to prevent
    symlink-based traversal bypasses (DEC-SEC-011).
    """
    if ".." in Path(output_dir).parts:
        raise HTTPException(status_code=400, detail="output_dir must not contain '..'")

    if os.path.isabs(output_dir):
        # Absolute path: must be within the configured runs directory
        runs_dir = Path(os.path.realpath(get_default_runs_dir()))
        resolved = Path(os.path.realpath(output_dir))
        if not (
            str(resolved) == str(runs_dir)
            or str(resolved).startswith(str(runs_dir) + os.sep)
        ):
            raise HTTPException(
                status_code=400,
                detail="output_dir must be within the runs directory",
            )
        return resolved

    # Relative path: resolve against CWD (preserves CLI compatibility)
    resolved = Path(os.path.realpath(output_dir))
    cwd = Path(os.path.realpath("."))
    if not (str(resolved) == str(cwd) or str(resolved).startswith(str(cwd) + os.sep)):
        raise HTTPException(
            status_code=400, detail="output_dir must be within the working directory"
        )
    return resolved


def _validate_techniques(techniques: list[str] | None) -> None:
    """Validate that all technique IDs in *techniques* are registered.

    None is accepted (means auto-select). Raises ValueError for unknown IDs.

    @decision DEC-SEC-007
    @title Technique IDs validated against registry before run starts
    @status accepted
    @rationale Unvalidated technique IDs would cause the pipeline to silently
    skip unknown techniques or error mid-run. Validating upfront gives a clean
    400 response with the unknown ID listed, improving debuggability and preventing
    mis-typed IDs from wasting LLM quota.
    """
    if techniques is None:
        return
    import sat.techniques  # noqa: F401 — trigger registration
    from sat.techniques.registry import list_technique_ids

    known = set(list_technique_ids())
    unknown = [t for t in techniques if t not in known]
    if unknown:
        raise ValueError(f"Unknown technique IDs: {unknown!r}. Known: {sorted(known)!r}")


async def _broadcast(run: ActiveRun, event_dict: dict) -> None:
    """Append event_dict to events_log and broadcast to all WS clients."""
    run.events_log.append(event_dict)
    for ws in list(run.ws_clients):
        try:
            await ws.send_json(event_dict)
        except Exception:  # @defprog-exempt: WebSocket send to a disconnected client is expected; failure is silently dropped
            pass


def create_analysis_router(
    manager: RunManager,
    port: int,
    rate_limiter: ProviderRateLimiter | None = None,
) -> APIRouter:
    """Return the analysis router wired to *manager* and bound to *port* for WS URLs.

    Args:
        manager: Shared RunManager instance.
        port: Server port used to construct ws_url values.
        rate_limiter: Optional per-provider rate limiter. When provided, LLM calls
            are throttled across all concurrent analyses.
    """
    router = APIRouter(dependencies=[Depends(verify_token)])

    @router.post("/api/analysis", response_model=AnalysisResponse)
    async def start_analysis(request: AnalysisRequest) -> AnalysisResponse:
        """Start a new analysis run. Returns run_id and WebSocket URL immediately.

        If the concurrency cap is reached, the run is queued and queue_position
        is set in the response so the frontend can show queued state.
        """
        # Resolve output_dir: None means "use the stable default runs directory"
        # (DEC-RUNS-001). An explicit "." preserves CLI / dev-mode behaviour.
        effective_output_dir = request.output_dir if request.output_dir is not None else str(get_default_runs_dir())

        # Validate and canonicalise the resolved path before starting the run
        resolved_output_dir = _validate_output_dir(effective_output_dir)
        try:
            _validate_techniques(request.techniques)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        provider_cfg = ProviderConfig(
            provider=request.provider,
            model=request.model,
        )

        research_cfg = ResearchConfig(
            enabled=request.research_enabled,
            mode=request.research_mode,
            gap_resolution=GapResolutionConfig(enabled=request.gap_resolution_enabled),
        )

        report_cfg = ReportConfig(
            enabled=request.report_enabled,
            fmt=request.report_format,
        )

        adversarial_cfg: AdversarialConfig | None = None
        if request.adversarial_enabled:
            adversarial_cfg = build_adversarial_config(
                provider=request.provider,
                model=request.model,
                mode=request.adversarial_mode,
                rounds=request.adversarial_rounds,
            )

        config = AnalysisConfig(
            question=request.question,
            name=request.name,
            evidence=request.evidence,
            techniques=request.techniques,
            output_dir=resolved_output_dir,
            provider=provider_cfg,
            research=research_cfg,
            adversarial=adversarial_cfg,
            report=report_cfg,
            evidence_sources=request.evidence_sources,
        )

        run = manager.create_run(config)

        async def execute() -> None:
            try:
                output_path = await run_analysis(config, run.bus, rate_limiter)
                run.output_dir = str(output_path)
                run.status = "completed"

                # Best-effort evidence persistence (DEC-API-015).
                # Reconstruct a structured EvidencePool from pipeline artifact files
                # and write evidence.json so GET /api/runs/{run_id}/evidence works
                # for quick-run outputs. Never raises — logged and swallowed.
                try:
                    from sat.evidence.persistence import build_evidence_pool, persist_evidence

                    pool = build_evidence_pool(output_path, config.question)
                    if pool.items:
                        persist_evidence(output_path, pool)
                except Exception:
                    logger.warning(
                        "Failed to persist evidence pool for run %s",
                        run.run_id,
                        exc_info=True,
                    )

                completion = {
                    "type": "run_completed",
                    "data": {"output_dir": str(output_path), "run_id": run.run_id},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await _broadcast(run, completion)
            except Exception as e:
                run.status = "failed"
                # Store a generic error message — never expose raw exception
                # strings to the client (they may contain API keys, file paths,
                # or other sensitive information). Details go to the server log.
                logger.error(
                    "Run %s failed: %s",
                    run.run_id,
                    str(e),
                    exc_info=True,
                )
                run.error = "Analysis failed — check server logs for details"
                error_event = {
                    "type": "run_failed",
                    "data": {
                        "error": "Analysis failed — check server logs for details",
                        "run_id": run.run_id,
                    },
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await _broadcast(run, error_event)

        manager.start_or_queue(run, execute)

        return AnalysisResponse(
            run_id=run.run_id,
            ws_url=f"ws://localhost:{port}/ws/analysis/{run.run_id}",
            queue_position=manager.queue_position(run.run_id),
        )

    return router
