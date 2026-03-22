"""Evidence gathering and curation API routes.

@decision DEC-API-012
@title Two-phase analysis flow: gather evidence, then analyze with curated selection
@status accepted
@rationale The existing single-shot POST /api/analysis → pipeline runs end-to-end.
These new endpoints split that into: gather evidence → user curates → run analysis
with selected evidence. The existing /api/analysis endpoint is unchanged for CLI/power users.

@decision DEC-API-013
@title Persist curated EvidencePool as evidence.json after analysis completes
@status accepted
@rationale The curated evidence selection is meaningful context for the run — which
items were selected, their confidence, categories, and sources. Persisting it as
evidence.json in the run output directory (alongside manifest.json) lets the frontend
retrieve it later via GET /api/runs/{run_id}/evidence without re-gathering. The
manifest.json is also updated with evidence_path="evidence.json" so RunDetail includes
the path. Persistence happens inside the execute() coroutine after run_analysis returns
and output_path is known. On failure the evidence write is best-effort (logged but not
re-raised) to avoid masking the real pipeline error.

@decision DEC-API-014
@title POST /api/evidence/pool: synchronous pool creation without LLM calls
@status accepted
@rationale The gather endpoint uses LLMs for decomposition/research — it's async,
expensive, and requires a WebSocket for progress. When users type evidence manually
or upload documents, they already have the raw material; no LLM processing is needed
to build a reviewable pool. The /pool endpoint fills this gap: it runs document
ingestion (filesystem/HTTP I/O only), splits text into paragraphs with _split_to_user_items,
merges both lists, and returns a ready EvidencePool in a single synchronous HTTP response.
The resulting session is immediately usable by the existing analyze_curated endpoint.
Document items use "DOC-<n>" IDs and "document" source; user text items use "U-<n>" and
"user" source — consistent with the prefix conventions in EvidenceItem (DEC-EVIDENCE-001).
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
    PoolRequest,
    PoolResponse,
    UpdateEvidenceItemRequest,
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
from sat.evidence.gatherer import _split_to_user_items
from sat.evidence.persistence import persist_evidence
from sat.ingestion import ingest_evidence
from sat.models.evidence import EvidenceItem, EvidencePool
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
            except Exception:
                # Log full exception server-side; broadcast only a generic message
                # to avoid leaking API keys or internal details (DEC-SEC-006).
                logger.exception("Evidence gathering failed for session %s", session.session_id)
                session.status = "failed"
                session.error = "Evidence gathering failed — check server logs for details"
                error_event = {
                    "type": "evidence_failed",
                    "data": {
                        "error": "Evidence gathering failed — check server logs for details",
                        "session_id": session.session_id,
                    },
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

        # Build a curated EvidencePool with selection state for persistence.
        # This is written to evidence.json after the pipeline completes so the
        # frontend can retrieve the curated evidence selection via
        # GET /api/runs/{run_id}/evidence (DEC-API-013).
        curated_pool = pool.model_copy(update={"items": curated_items})

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

                # Persist the curated EvidencePool as evidence.json in the output
                # directory and update manifest.json with evidence_path (DEC-API-013).
                try:
                    persist_evidence(output_path, curated_pool)
                except Exception:
                    logger.warning(
                        "Failed to persist evidence.json for run %s",
                        run.run_id,
                        exc_info=True,
                    )

                completion = {
                    "type": "run_completed",
                    "data": {"output_dir": str(output_path), "run_id": run.run_id},
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await _broadcast_run(run, completion)
            except Exception:
                # Log full exception server-side; broadcast only a generic message
                # to avoid leaking API keys or internal details (DEC-SEC-006).
                logger.exception("Curated analysis failed for run %s", run.run_id)
                run.status = "failed"
                run.error = "Analysis failed — check server logs for details"
                error_event = {
                    "type": "run_failed",
                    "data": {
                        "error": "Analysis failed — check server logs for details",
                        "run_id": run.run_id,
                    },
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await _broadcast_run(run, error_event)

        run_manager.start_or_queue(run, execute)

        return AnalysisResponse(
            run_id=run.run_id,
            ws_url=f"ws://localhost:{port}/ws/analysis/{run.run_id}",
            queue_position=run_manager.queue_position(run.run_id),
        )

    @router.post("/api/evidence/pool", response_model=PoolResponse)
    async def create_pool(request: PoolRequest) -> PoolResponse:
        """Create an EvidencePool synchronously from text and/or document sources.

        No LLM calls are made. Document ingestion (filesystem/HTTP I/O) is awaited
        when evidence_sources are provided. Text is split into paragraphs.

        The resulting EvidenceSession is immediately status="ready", so the
        existing POST /api/evidence/{session_id}/analyze endpoint can be called
        right after without waiting for a background gather task.

        Item ID conventions (DEC-EVIDENCE-001, DEC-API-014):
        - Document items: ``DOC-<n>`` with source="document"
        - User text items: ``U-<n>`` with source="user"
        """
        session = evidence_manager.create_session()
        session.name = request.name
        session.evidence_sources = request.evidence_sources or None

        doc_items: list[EvidenceItem] = []
        user_items: list[EvidenceItem] = []

        # 1. Ingest document sources (filesystem / HTTP I/O, no LLM)
        if request.evidence_sources:
            ingestion_result = await ingest_evidence(sources=request.evidence_sources)
            for n, doc in enumerate(ingestion_result.documents, start=1):
                doc_items.append(
                    EvidenceItem(
                        item_id=f"DOC-{n}",
                        claim=doc.markdown.strip(),
                        source="document",
                        source_ids=[doc.source_name],
                        category="fact",
                        confidence="Medium",
                        entities=[],
                        verified=False,
                        selected=True,
                    )
                )

        # 2. Split user text into paragraph items
        if request.evidence:
            user_items = _split_to_user_items(request.evidence)

        all_items = doc_items + user_items

        pool = EvidencePool(
            session_id=session.session_id,
            question=request.question,
            items=all_items,
            status="ready",
        )
        session.pool = pool
        session.status = "ready"

        return PoolResponse(session_id=session.session_id, pool=pool)

    @router.patch("/api/evidence/{session_id}/items/{item_id}")
    async def update_evidence_item(
        session_id: str,
        item_id: str,
        request: UpdateEvidenceItemRequest,
    ) -> EvidenceItem:
        """Update fields on a single evidence item during curation.

        @decision DEC-API-015
        @title PATCH endpoint for evidence item editing during curation
        @status accepted
        @rationale Users need to correct errors in gathered evidence items (wrong claim
        text, incorrect confidence, or mis-categorized items) before committing to analysis.
        Only fields that are provided (non-None) are updated; others are preserved.
        Returns the updated EvidenceItem. Session must exist and be in 'ready' state.
        The update is applied to session.pool in-place so subsequent GET /api/evidence/{id}
        reflects the change without a re-gather.
        """
        session = evidence_manager.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Evidence session not found")
        if session.pool is None or session.status != "ready":
            raise HTTPException(
                status_code=409,
                detail=f"Evidence session not ready (status: {session.status})",
            )

        # Find and update the item; rebuild the items list immutably (Pydantic models are frozen)
        updated_item: EvidenceItem | None = None
        updated_items = []
        for item in session.pool.items:
            if item.item_id == item_id:
                updates = {}
                if request.claim is not None:
                    updates["claim"] = request.claim
                if request.confidence is not None:
                    updates["confidence"] = request.confidence
                if request.category is not None:
                    updates["category"] = request.category
                updated_item = item.model_copy(update=updates) if updates else item
                updated_items.append(updated_item)
            else:
                updated_items.append(item)

        if updated_item is None:
            raise HTTPException(status_code=404, detail=f"Evidence item {item_id} not found")

        session.pool = session.pool.model_copy(update={"items": updated_items})
        return updated_item

    return router
