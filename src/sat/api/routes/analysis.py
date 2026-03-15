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
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter

from sat.adversarial.config import AdversarialConfig, build_adversarial_config
from sat.api.models import AnalysisRequest, AnalysisResponse
from sat.api.run_manager import ActiveRun, RunManager
from sat.config import AnalysisConfig, ProviderConfig, ReportConfig, ResearchConfig
from sat.pipeline import run_analysis

if TYPE_CHECKING:
    from sat.providers.rate_limiter import ProviderRateLimiter


async def _broadcast(run: ActiveRun, event_dict: dict) -> None:
    """Append event_dict to events_log and broadcast to all WS clients."""
    run.events_log.append(event_dict)
    for ws in list(run.ws_clients):
        try:
            await ws.send_json(event_dict)
        except Exception:
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
    router = APIRouter()

    @router.post("/api/analysis", response_model=AnalysisResponse)
    async def start_analysis(request: AnalysisRequest) -> AnalysisResponse:
        """Start a new analysis run. Returns run_id and WebSocket URL immediately.

        If the concurrency cap is reached, the run is queued and queue_position
        is set in the response so the frontend can show queued state.
        """
        provider_cfg = ProviderConfig(
            provider=request.provider,
            model=request.model,
        )

        research_cfg = ResearchConfig(
            enabled=request.research_enabled,
            mode=request.research_mode,
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
            output_dir=Path(request.output_dir),
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
                completion = {
                    "type": "run_completed",
                    "data": {"output_dir": str(output_path), "run_id": run.run_id},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await _broadcast(run, completion)
            except Exception as e:
                run.status = "failed"
                run.error = str(e)
                error_event = {
                    "type": "run_failed",
                    "data": {"error": str(e), "run_id": run.run_id},
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
