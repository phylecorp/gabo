"""Evidence gathering and curation API routes.

@decision DEC-API-012
@title Two-phase analysis flow: gather evidence, then analyze with curated selection
@status accepted
@rationale The existing single-shot POST /api/analysis → pipeline runs end-to-end.
These new endpoints split that into: gather evidence → user curates → run analysis
with selected evidence. The existing /api/analysis endpoint is unchanged for CLI/power users.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from sat.adversarial.config import AdversarialConfig, build_adversarial_config
from sat.api.evidence_manager import EvidenceSession, EvidenceSessionManager
from sat.api.models import (
    AnalysisResponse,
    CuratedAnalysisRequest,
    EvidenceGatherRequest,
    EvidenceGatherResponse,
)
from sat.api.run_manager import ActiveRun, RunManager
from sat.config import (
    AnalysisConfig,
    DecompositionConfig,
    ProviderConfig,
    ReportConfig,
    ResearchConfig,
)
from sat.evidence import gather_evidence
from sat.evidence.formatter import format_curated_evidence
from sat.models.evidence import EvidencePool
from sat.pipeline import run_analysis

if TYPE_CHECKING:
    from sat.providers.rate_limiter import ProviderRateLimiter

logger = logging.getLogger(__name__)


async def _broadcast_session(session: EvidenceSession, event_dict: dict) -> None:
    """Append event_dict to session events_log and broadcast to all WS clients.

    Disconnected clients are pruned silently — a send failure means the client
    disconnected, which is expected and not an error condition.
    @defprog-exempt: WebSocket send to a disconnected client is expected; pruning is intentional.
    """
    session.events_log.append(event_dict)
    disconnected = []
    for ws in list(session.ws_clients):
        try:
            await ws.send_json(event_dict)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in session.ws_clients:
            session.ws_clients.remove(ws)


async def _broadcast_run(run: ActiveRun, event_dict: dict) -> None:
    """Append event_dict to run events_log and broadcast to all WS clients.

    Disconnected clients are pruned silently — a send failure means the client
    disconnected, which is expected and not an error condition.
    @defprog-exempt: WebSocket send to a disconnected client is expected; pruning is intentional.
    """
    run.events_log.append(event_dict)
    disconnected = []
    for ws in list(run.ws_clients):
        try:
            await ws.send_json(event_dict)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in run.ws_clients:
            run.ws_clients.remove(ws)


def create_evidence_router(
    evidence_manager: EvidenceSessionManager,
    run_manager: RunManager,
    port: int,
    rate_limiter: ProviderRateLimiter | None = None,
) -> APIRouter:
    """Return the evidence router wired to the given managers and port.

    Args:
        evidence_manager: Session manager for evidence gathering.
        run_manager: Shared RunManager for creating and queuing analysis runs.
        port: Server port for constructing ws_url values.
        rate_limiter: Optional per-provider rate limiter for concurrent LLM calls.
    """
    router = APIRouter()

    @router.post("/api/evidence/gather", response_model=EvidenceGatherResponse)
    async def gather(request: EvidenceGatherRequest) -> EvidenceGatherResponse:
        """Start evidence gathering. Returns session_id and WebSocket URL immediately."""
        session = evidence_manager.create_session()
        # Store sources on the session so the analyze step can pick them up
        # even when CuratedAnalysisRequest.evidence_sources is omitted.
        session.evidence_sources = request.evidence_sources
        # Store name on the session so the analyze step can carry it forward.
        session.name = request.name

        provider_cfg = ProviderConfig(
            provider=request.provider,
            model=request.model,
        )
        research_cfg = ResearchConfig(
            enabled=request.research_enabled,
            mode=request.research_mode,
        )
        decomposition_cfg = DecompositionConfig(
            enabled=True,  # always attempt decomposition if evidence is provided
        )

        async def execute() -> None:
            try:
                # Create provider inside background task — construction resolves
                # API keys from env vars and fails loudly if missing, which is
                # correct behavior in the task context (error surfaced via WS).
                from sat.providers.registry import create_provider

                provider = create_provider(provider_cfg, rate_limiter)

                pool = await gather_evidence(
                    question=request.question,
                    evidence=request.evidence,
                    research_config=research_cfg,
                    decomposition_config=decomposition_cfg,
                    provider=provider,
                    events=session.bus,
                )
                session.pool = pool
                session.status = "ready"
                completion = {
                    "type": "evidence_ready",
                    "data": {
                        "session_id": session.session_id,
                        "item_count": len(pool.items),
                        "source_count": len(pool.sources),
                        "gap_count": len(pool.gaps),
                    },
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await _broadcast_session(session, completion)
            except Exception as e:
                logger.exception("Evidence gathering failed for session %s", session.session_id)
                session.status = "failed"
                session.error = str(e)
                error_event = {
                    "type": "evidence_failed",
                    "data": {"error": str(e), "session_id": session.session_id},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await _broadcast_session(session, error_event)

        session.task = asyncio.create_task(execute())

        return EvidenceGatherResponse(
            session_id=session.session_id,
            ws_url=f"ws://localhost:{port}/ws/evidence/{session.session_id}",
        )

    @router.get("/api/evidence/{session_id}", response_model=EvidencePool)
    async def get_evidence_pool(session_id: str) -> EvidencePool:
        """Return the EvidencePool for a session (for polling / late-join)."""
        session = evidence_manager.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Evidence session not found")
        if session.pool is None:
            # Session exists but gathering isn't complete yet; return status shell
            return EvidencePool(
                session_id=session_id,
                question="",
                items=[],
                status=session.status,
                error=session.error,
            )
        return session.pool

    @router.post("/api/evidence/{session_id}/analyze", response_model=AnalysisResponse)
    async def analyze_curated(
        session_id: str,
        request: CuratedAnalysisRequest,
    ) -> AnalysisResponse:
        """Start analysis using curated evidence selection.

        Formats selected items into evidence text, creates an AnalysisConfig with
        research and decomposition disabled (already done), and runs the pipeline.
        """
        session = evidence_manager.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Evidence session not found")
        if session.pool is None or session.status != "ready":
            raise HTTPException(
                status_code=409,
                detail=f"Evidence session not ready (status: {session.status})",
            )

        pool = session.pool

        # Mark items selected/deselected based on the caller's list
        item_ids_set = set(request.selected_item_ids)
        curated_items = [
            item.model_copy(update={"selected": item.item_id in item_ids_set})
            for item in pool.items
        ]

        evidence_text = format_curated_evidence(
            items=curated_items,
            sources=pool.sources,
            gaps=pool.gaps,
        )

        provider_cfg = ProviderConfig(
            provider=request.provider,
            model=request.model,
        )

        adversarial_cfg: AdversarialConfig | None = None
        if request.adversarial_enabled:
            adversarial_cfg = build_adversarial_config(
                provider=request.provider,
                model=request.model,
                mode=request.adversarial_mode,
                rounds=request.adversarial_rounds,
            )

        report_cfg = ReportConfig(
            enabled=request.report_enabled,
            fmt=request.report_format,
        )

        # Resolve sources: prefer request-provided sources, fall back to sources
        # stored when the gather step was initiated. This ensures ingestion runs
        # regardless of which path the client uses to supply sources.
        effective_sources = request.evidence_sources or session.evidence_sources

        # Resolve name: prefer request-provided name, fall back to session-stored name.
        effective_name = request.name or session.name

        config = AnalysisConfig(
            question=pool.question,
            name=effective_name,
            evidence=evidence_text if evidence_text else None,
            techniques=request.techniques,
            output_dir=Path("."),
            provider=provider_cfg,
            research=ResearchConfig(enabled=False),  # already gathered
            decomposition=DecompositionConfig(enabled=False),  # already done
            adversarial=adversarial_cfg,
            report=report_cfg,
            evidence_sources=effective_sources,
        )

        run = run_manager.create_run(config)

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
                await _broadcast_run(run, completion)
            except Exception as e:
                logger.exception("Curated analysis failed for run %s", run.run_id)
                run.status = "failed"
                run.error = str(e)
                error_event = {
                    "type": "run_failed",
                    "data": {"error": str(e), "run_id": run.run_id},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await _broadcast_run(run, error_event)

        run_manager.start_or_queue(run, execute)

        return AnalysisResponse(
            run_id=run.run_id,
            ws_url=f"ws://localhost:{port}/ws/analysis/{run.run_id}",
            queue_position=run_manager.queue_position(run.run_id),
        )

    return router
