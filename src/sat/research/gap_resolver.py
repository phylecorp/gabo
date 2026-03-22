"""Gap-driven iterative research: resolves information gaps from initial research.

@decision DEC-RESEARCH-013
@title Gap resolver as separate pipeline stage with configurable iteration cap
@status accepted
@rationale Research identifies information gaps (gaps_identified on ResearchResult) but
never acts on them. Intelligence tradecraft requires iterative gap-driven research.
The gap resolver runs as a separate stage after initial research, formulating follow-up
queries from identified gaps, running them through the existing research provider, and
merging new findings. Capped at max_iterations (default 2) to control token cost.
Each iteration may identify new gaps; the loop terminates when no gaps remain or the
cap is reached. Graceful degradation: any failure at any stage stops iteration and
returns the best result accumulated so far — never crashes the pipeline.
"""

from __future__ import annotations

import logging

from sat.events import EventBus, NullBus, StageCompleted, StageStarted
from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.providers.base import LLMMessage, LLMProvider
from sat.research.base import ResearchProvider
from sat.research.structurer import structure_evidence

logger = logging.getLogger(__name__)

GAP_QUERY_SYSTEM = """You are a research gap analyst. Given a list of information gaps identified during prior research, generate a focused search query that will address the most important gaps.

Prioritize:
1. Gaps that would most materially change the analysis if resolved
2. Gaps about factual data that is likely findable via search
3. Gaps that multiple findings depend on

Skip gaps that are inherently unanswerable (e.g., classified information, future predictions).

Respond with ONLY the search query text, nothing else. If no actionable gaps exist, respond with "NO_ACTIONABLE_GAPS"."""


async def resolve_gaps(
    research_result: ResearchResult,
    research_provider: ResearchProvider,
    llm_provider: LLMProvider,
    max_iterations: int = 2,
    max_sources: int = 5,
    events: EventBus | None = None,
) -> ResearchResult:
    """Run iterative gap resolution on a research result.

    For each iteration:
    1. Check if gaps_identified is non-empty
    2. Generate a follow-up query from the gaps via LLM
    3. Run research with that query
    4. Merge new claims and sources into the result
    5. Update gaps from the new research

    Args:
        research_result: Initial research result with gaps_identified.
        research_provider: Provider for follow-up research queries.
        llm_provider: LLM for query generation and evidence structuring.
        max_iterations: Maximum gap resolution iterations (default 2).
        max_sources: Max sources per follow-up query (default 5, smaller than initial).
        events: Optional event bus for progress.

    Returns:
        Updated ResearchResult with merged findings from gap resolution.
        Returns the input unchanged if no gaps exist or all stages fail gracefully.
    """
    bus = events or NullBus
    current = research_result
    total_new_claims = 0
    total_new_sources = 0

    for iteration in range(max_iterations):
        gaps = current.gaps_identified
        if not gaps:
            logger.info("No gaps remaining after iteration %d — stopping", iteration)
            break

        await bus.emit(StageStarted(stage="gap_resolution", technique_id=f"iteration-{iteration + 1}"))
        logger.info(
            "Gap resolution iteration %d/%d: %d gap(s) to address",
            iteration + 1, max_iterations, len(gaps),
        )

        # Generate follow-up query from gaps
        gaps_text = "\n".join(f"- {gap}" for gap in gaps)
        try:
            query_result = await llm_provider.generate(
                system_prompt=GAP_QUERY_SYSTEM,
                messages=[LLMMessage(role="user", content=f"Information gaps to address:\n\n{gaps_text}")],
                max_tokens=200,
                temperature=0.1,
            )
            follow_up_query = query_result.text.strip()
        except Exception as exc:
            logger.warning("Gap query generation failed: %s — stopping", exc)
            break

        if follow_up_query == "NO_ACTIONABLE_GAPS":
            logger.info("No actionable gaps identified — stopping")
            break

        logger.info("Gap follow-up query: %s", follow_up_query)

        # Run follow-up research
        try:
            raw_response = await research_provider.research(
                query=follow_up_query,
                context=f"Follow-up research for gaps in: {current.query}",
                max_sources=max_sources,
            )
        except Exception as exc:
            logger.warning("Gap follow-up research failed: %s — stopping", exc)
            break

        if not raw_response.content.strip():
            logger.info("Follow-up research returned empty content — stopping")
            break

        # Structure the follow-up evidence
        try:
            follow_up_result = await structure_evidence(
                raw=raw_response,
                query=follow_up_query,
                provider=llm_provider,
                research_provider_name=current.research_provider,
            )
        except Exception as exc:
            logger.warning("Gap evidence structuring failed: %s — stopping", exc)
            break

        # Merge new findings into the current result
        new_claims, new_sources = _merge_follow_up(current, follow_up_result)
        total_new_claims += len(new_claims)
        total_new_sources += len(new_sources)

        # Update the result with merged data and new gaps
        current = current.model_copy(update={
            "claims": list(current.claims) + new_claims,
            "sources": list(current.sources) + new_sources,
            "gaps_identified": follow_up_result.gaps_identified,  # Replace with remaining gaps
        })

        await bus.emit(StageCompleted(
            stage="gap_resolution",
            technique_id=f"iteration-{iteration + 1}",
        ))

        logger.info(
            "Iteration %d: +%d claims, +%d sources, %d gaps remaining",
            iteration + 1, len(new_claims), len(new_sources),
            len(current.gaps_identified),
        )

    if total_new_claims > 0 or total_new_sources > 0:
        logger.info(
            "Gap resolution complete: +%d claims, +%d sources total",
            total_new_claims, total_new_sources,
        )

    return current


def _merge_follow_up(
    existing: ResearchResult,
    follow_up: ResearchResult,
) -> tuple[list[ResearchClaim], list[ResearchSource]]:
    """Merge follow-up research, deduplicating by claim text and source ID.

    Deduplication rules:
    - Claims: case-insensitive, whitespace-stripped text match
    - Sources: exact ID match

    Args:
        existing: The accumulated research result so far.
        follow_up: New research result to merge from.

    Returns:
        Tuple of (new_claims, new_sources) — only items not already present.
    """
    existing_claim_texts = {c.claim.strip().lower() for c in existing.claims}
    existing_source_ids = {s.id for s in existing.sources}

    new_claims = [
        c for c in follow_up.claims
        if c.claim.strip().lower() not in existing_claim_texts
    ]
    new_sources = [
        s for s in follow_up.sources
        if s.id not in existing_source_ids
    ]

    return new_claims, new_sources
