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

@decision DEC-RESEARCH-014
@title Parallel gap resolution replaces sequential iteration
@status accepted
@rationale The original sequential loop required N×(research + structure) wall-clock
time for N gaps. The new approach generates all follow-up queries in a single LLM call
(one query per actionable gap), then fans out research and structuring concurrently via
asyncio.gather. max_iterations now caps the number of parallel queries rather than
sequential iterations. This preserves the token-cost contract while delivering
sub-linear latency scaling with gap count. Graceful degradation is preserved: failed
individual query coroutines are swallowed and do not crash the pipeline. The final
merge deduplicates across all concurrent results, so overlapping findings are handled
identically to the prior sequential approach.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel, Field

from sat.events import EventBus, NullBus, StageCompleted, StageStarted
from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.providers.base import LLMMessage, LLMProvider
from sat.research.base import ResearchProvider
from sat.research.structurer import structure_evidence

logger = logging.getLogger(__name__)

GAP_QUERY_SYSTEM = """You are a research gap analyst. Given a list of information gaps identified during prior research, generate focused search queries that will address the most important gaps — one query per actionable gap.

Prioritize:
1. Gaps that would most materially change the analysis if resolved
2. Gaps about factual data that is likely findable via search
3. Gaps that multiple findings depend on

Skip gaps that are inherently unanswerable (e.g., classified information, future predictions).

Return a JSON object with a "queries" field containing a list of query strings. Each string should be a focused search query for one gap. If no actionable gaps exist, return {"queries": []}."""


class GapQueries(BaseModel):
    """Structured output for batch gap query generation.

    A single LLM call returns all follow-up queries at once, enabling
    concurrent research execution rather than sequential iteration.
    """

    queries: list[str] = Field(
        default_factory=list,
        description="One search query per actionable gap, in priority order.",
    )


async def _resolve_single_gap(
    query: str,
    current: ResearchResult,
    research_provider: ResearchProvider,
    llm_provider: LLMProvider,
    max_sources: int,
    query_index: int,
) -> tuple[list[ResearchClaim], list[ResearchSource], str | None]:
    """Run research + structuring for a single follow-up query.

    Returns (new_claims, new_sources, error_message). On any failure,
    returns empty lists and a non-None error string — callers must not crash.
    """
    try:
        raw_response = await research_provider.research(
            query=query,
            context=f"Follow-up research for gaps in: {current.query}",
            max_sources=max_sources,
        )
    except Exception as exc:
        logger.warning("Gap follow-up research failed for query %d: %s", query_index + 1, exc)
        return [], [], str(exc)

    if not raw_response.content.strip():
        logger.info("Follow-up research returned empty content for query %d — skipping", query_index + 1)
        return [], [], "empty_response"

    try:
        follow_up_result = await structure_evidence(
            raw=raw_response,
            query=query,
            provider=llm_provider,
            research_provider_name=current.research_provider,
        )
    except Exception as exc:
        logger.warning("Gap evidence structuring failed for query %d: %s", query_index + 1, exc)
        return [], [], str(exc)

    new_claims, new_sources = _merge_follow_up(current, follow_up_result)
    origin_label = f"gap_resolution_query_{query_index + 1}"
    new_claims = [c.model_copy(update={"origin": origin_label}) for c in new_claims]
    return new_claims, new_sources, None


async def resolve_gaps(
    research_result: ResearchResult,
    research_provider: ResearchProvider,
    llm_provider: LLMProvider,
    max_iterations: int = 2,
    max_sources: int = 5,
    events: EventBus | None = None,
) -> ResearchResult:
    """Run parallel gap resolution on a research result.

    Generates all follow-up queries in a single LLM call, then runs all
    research + structuring concurrently, then merges all results at once.
    max_iterations caps the number of parallel queries (previously: sequential
    iterations).

    Args:
        research_result: Initial research result with gaps_identified.
        research_provider: Provider for follow-up research queries.
        llm_provider: LLM for query generation and evidence structuring.
        max_iterations: Maximum number of parallel follow-up queries (default 2).
        max_sources: Max sources per follow-up query (default 5, smaller than initial).
        events: Optional event bus for progress.

    Returns:
        Updated ResearchResult with merged findings from gap resolution.
        Returns the input unchanged if no gaps exist or all stages fail gracefully.
    """
    bus = events or NullBus
    current = research_result

    gaps = current.gaps_identified
    if not gaps:
        logger.info("No gaps identified — skipping gap resolution")
        return current

    logger.info("Gap resolution: %d gap(s) identified, generating queries", len(gaps))

    # Step 1: Generate all follow-up queries in a single LLM call.
    gaps_text = "\n".join(f"- {gap}" for gap in gaps)
    try:
        gap_queries: GapQueries = await llm_provider.generate_structured(
            system_prompt=GAP_QUERY_SYSTEM,
            messages=[
                LLMMessage(role="user", content=f"Information gaps to address:\n\n{gaps_text}")
            ],
            output_schema=GapQueries,
            max_tokens=400,
            temperature=0.1,
        )
        queries = gap_queries.queries[:max_iterations]
    except Exception as exc:
        logger.warning("Gap query generation failed: %s — skipping gap resolution", exc)
        return current

    if not queries:
        logger.info("No actionable gaps identified — skipping gap resolution")
        return current

    logger.info(
        "Gap resolution: running %d parallel follow-up quer%s",
        len(queries),
        "y" if len(queries) == 1 else "ies",
    )

    # Step 2: Emit start events and run all research + structuring concurrently.
    for i, query in enumerate(queries):
        await bus.emit(StageStarted(stage="gap_resolution", technique_id=f"query-{i + 1}"))
        logger.info("Gap follow-up query %d: %s", i + 1, query)

    results = await asyncio.gather(
        *[
            _resolve_single_gap(
                query=q,
                current=current,
                research_provider=research_provider,
                llm_provider=llm_provider,
                max_sources=max_sources,
                query_index=i,
            )
            for i, q in enumerate(queries)
        ]
    )

    # Step 3: Merge all successful results.
    total_new_claims = 0
    total_new_sources = 0
    all_new_claims: list[ResearchClaim] = []
    all_new_sources: list[ResearchSource] = []

    # Deduplicate across parallel results: track what we've accumulated.
    seen_claim_texts: set[str] = {c.claim.strip().lower() for c in current.claims}
    seen_source_ids: set[str] = {s.id for s in current.sources}

    for i, (new_claims, new_sources, error) in enumerate(results):
        if error is None:
            await bus.emit(StageCompleted(stage="gap_resolution", technique_id=f"query-{i + 1}"))

        for claim in new_claims:
            key = claim.claim.strip().lower()
            if key not in seen_claim_texts:
                seen_claim_texts.add(key)
                all_new_claims.append(claim)
                total_new_claims += 1

        for source in new_sources:
            if source.id not in seen_source_ids:
                seen_source_ids.add(source.id)
                all_new_sources.append(source)
                total_new_sources += 1

    if all_new_claims or all_new_sources:
        current = current.model_copy(
            update={
                "claims": list(current.claims) + all_new_claims,
                "sources": list(current.sources) + all_new_sources,
                # After parallel resolution, gaps are considered addressed.
                "gaps_identified": [],
            }
        )
        logger.info(
            "Gap resolution complete: +%d claims, +%d sources from %d parallel quer%s",
            total_new_claims,
            total_new_sources,
            len(queries),
            "y" if len(queries) == 1 else "ies",
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
        c for c in follow_up.claims if c.claim.strip().lower() not in existing_claim_texts
    ]
    new_sources = [s for s in follow_up.sources if s.id not in existing_source_ids]

    return new_claims, new_sources
