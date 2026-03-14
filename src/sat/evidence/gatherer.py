"""Evidence gathering: fans out to decomposition + research, merges into EvidencePool.

@decision DEC-EVIDENCE-002
@title gather_evidence runs decomposition and research in parallel regardless of evidence presence
@status accepted
@rationale Previously research only ran when no evidence was provided (pipeline.py:243).
The gatherer always runs both decomposition (if evidence text exists) and research (if enabled),
merging results into a unified EvidencePool. This gives users maximum evidence to curate.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sat.config import DecompositionConfig, ResearchConfig
from sat.events import (
    EventBus,
    EvidenceGatheringCompleted,
    EvidenceGatheringStarted,
    NullBus,
    StageCompleted,
    StageStarted,
)
from sat.models.evidence import EvidenceItem, EvidencePool

if TYPE_CHECKING:
    from sat.providers.base import LLMProvider

logger = logging.getLogger(__name__)


def _normalize_confidence(raw: str) -> str:
    """Normalize confidence strings to Title Case (High/Medium/Low)."""
    mapping = {
        "high": "High",
        "medium": "Medium",
        "med": "Medium",
        "low": "Low",
    }
    return mapping.get(raw.lower(), raw.capitalize() if raw else "Medium")


async def gather_evidence(
    question: str,
    evidence: str | None,
    research_config: ResearchConfig,
    decomposition_config: DecompositionConfig,
    provider: "LLMProvider",
    events: EventBus | None = None,
) -> EvidencePool:
    """Gather evidence from all configured sources and return a unified EvidencePool.

    Runs decomposition (if evidence text + decomposition enabled) and research
    (if research enabled) in parallel, then merges and deduplicates results.

    Args:
        question: The analytic question being investigated.
        evidence: Raw evidence text provided by the user (may be None).
        research_config: Research phase configuration.
        decomposition_config: Decomposition phase configuration.
        provider: LLM provider for decomposition and research structuring.
        events: Optional event bus for progress visibility.

    Returns:
        EvidencePool with all gathered items, sources, gaps, and metadata.
    """
    import asyncio

    bus = events if events is not None else NullBus
    session_id = uuid.uuid4().hex[:12]

    has_evidence = bool(evidence)
    research_enabled = research_config.enabled
    decomposition_enabled = decomposition_config.enabled and has_evidence

    await bus.emit(
        EvidenceGatheringStarted(
            session_id=session_id,
            has_evidence=has_evidence,
            research_enabled=research_enabled,
            decomposition_enabled=decomposition_enabled,
        )
    )

    decomp_items: list[EvidenceItem] = []
    research_items: list[EvidenceItem] = []
    research_sources: list[dict] = []
    research_gaps: list[str] = []
    provider_summary = ""

    # Build coroutines to run
    tasks = []
    task_labels = []

    if has_evidence and decomposition_enabled:
        tasks.append(_run_decomposition(evidence, provider, decomposition_config, bus))  # type: ignore[arg-type]
        task_labels.append("decomposition")

    if research_enabled:
        tasks.append(_run_research(question, provider, research_config, bus))
        task_labels.append("research")

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for label, result in zip(task_labels, results):
            if isinstance(result, Exception):
                logger.warning("Evidence %s failed: %s", label, result)
            elif label == "decomposition":
                decomp_items = result  # type: ignore[assignment]
            elif label == "research":
                items, sources, gaps, summary = result  # type: ignore[misc]
                research_items = items
                research_sources = sources
                research_gaps = gaps
                provider_summary = summary

    # If evidence exists but decomposition is disabled, create user items from paragraphs
    user_items: list[EvidenceItem] = []
    if has_evidence and not decomposition_enabled:
        user_items = _split_to_user_items(evidence)  # type: ignore[arg-type]

    # Merge and deduplicate
    all_items = _merge_and_deduplicate(decomp_items, research_items, user_items)

    pool = EvidencePool(
        session_id=session_id,
        question=question,
        items=all_items,
        sources=research_sources,
        gaps=research_gaps,
        provider_summary=provider_summary,
        status="ready",
    )

    await bus.emit(
        EvidenceGatheringCompleted(
            session_id=session_id,
            item_count=len(all_items),
            source_count=len(research_sources),
            gap_count=len(research_gaps),
        )
    )

    return pool


async def _run_decomposition(
    evidence: str,
    provider: "LLMProvider",
    config: DecompositionConfig,
    bus: EventBus = NullBus,
) -> list[EvidenceItem]:
    """Run decomposition and convert AtomicFacts to EvidenceItems with D- prefix."""
    from sat.decomposition import decompose_evidence

    await bus.emit(StageStarted(stage="decomposition"))
    result = await decompose_evidence(
        evidence=evidence,
        provider=provider,
        config=config,
    )
    await bus.emit(StageCompleted(stage="decomposition"))

    items: list[EvidenceItem] = []
    for n, fact in enumerate(result.facts, start=1):
        item = EvidenceItem(
            item_id=f"D-{fact.fact_id}",
            claim=fact.claim,
            source="decomposition",
            source_ids=list(fact.source_ids),
            category=fact.category,
            confidence=_normalize_confidence(fact.confidence),
            entities=list(fact.entities),
            verified=False,
            selected=True,
        )
        items.append(item)

    return items


async def _run_research(
    question: str,
    provider: "LLMProvider",
    config: ResearchConfig,
    bus: EventBus,
) -> tuple[list[EvidenceItem], list[dict], list[str], str]:
    """Run research and convert ResearchClaims to EvidenceItems with R- prefix.

    Returns:
        (items, sources_dicts, gaps, provider_summary)
    """
    research_result = None

    if config.mode == "multi":
        from sat.research.multi_runner import run_multi_research

        research_result = await run_multi_research(
            question=question,
            llm_provider=provider,
            max_sources=config.max_sources,
            events=bus,
        )
    else:
        from sat.research.registry import create_research_provider
        from sat.research.runner import run_research as run_deep_research

        research_prov = create_research_provider(
            provider_name=config.provider,
            api_key=config.api_key,
            llm_provider=provider,
        )
        research_result = await run_deep_research(
            question=question,
            research_provider=research_prov,
            llm_provider=provider,
            max_sources=config.max_sources,
            events=bus,
        )

    items: list[EvidenceItem] = []
    for n, claim in enumerate(research_result.claims, start=1):
        item = EvidenceItem(
            item_id=f"R-C{n}",
            claim=claim.claim,
            source="research",
            source_ids=list(claim.source_ids),
            category=claim.category,
            confidence=_normalize_confidence(claim.confidence),
            entities=[],
            verified=claim.verified,
            selected=True,
            provider_name=research_result.research_provider,
        )
        items.append(item)

    # Convert sources to plain dicts
    sources_dicts = [
        {
            "id": s.id,
            "title": s.title,
            "url": s.url,
            "source_type": s.source_type,
            "reliability_assessment": s.reliability_assessment,
        }
        for s in research_result.sources
    ]

    provider_summary = f"Research via {research_result.research_provider}"
    if research_result.verification_status:
        provider_summary += f" ({research_result.verification_status})"

    return items, sources_dicts, list(research_result.gaps_identified), provider_summary


def _split_to_user_items(evidence: str) -> list[EvidenceItem]:
    """Split raw evidence text into paragraph-level user items with U- prefix."""
    paragraphs = [p.strip() for p in evidence.split("\n\n") if p.strip()]
    items: list[EvidenceItem] = []
    for n, para in enumerate(paragraphs, start=1):
        items.append(
            EvidenceItem(
                item_id=f"U-{n}",
                claim=para,
                source="user",
                source_ids=[],
                category="fact",
                confidence="Medium",
                entities=[],
                verified=False,
                selected=True,
            )
        )
    return items


def _merge_and_deduplicate(
    decomp_items: list[EvidenceItem],
    research_items: list[EvidenceItem],
    user_items: list[EvidenceItem],
) -> list[EvidenceItem]:
    """Merge items from all sources, deduplicating by exact claim text.

    Preference order for duplicates: research > decomposition > user.
    Items appear in the output in the order: decomposition, research, user
    (with duplicates from lower-priority sources dropped).
    """
    seen_claims: dict[str, EvidenceItem] = {}

    # Process in priority order: research first (highest priority)
    for item in research_items:
        key = item.claim.strip().lower()
        if key not in seen_claims:
            seen_claims[key] = item

    # Decomposition: only add if claim not already present
    for item in decomp_items:
        key = item.claim.strip().lower()
        if key not in seen_claims:
            seen_claims[key] = item

    # User items: only add if claim not already present
    for item in user_items:
        key = item.claim.strip().lower()
        if key not in seen_claims:
            seen_claims[key] = item

    # Return in a stable order: decomp first (by item_id), then research, then user
    ordered: list[EvidenceItem] = []
    for item in decomp_items:
        key = item.claim.strip().lower()
        if seen_claims.get(key) is item:
            ordered.append(item)

    for item in research_items:
        key = item.claim.strip().lower()
        if seen_claims.get(key) is item:
            ordered.append(item)

    for item in user_items:
        key = item.claim.strip().lower()
        if seen_claims.get(key) is item:
            ordered.append(item)

    return ordered
