"""Evidence structurer: converts raw research into structured claims with provenance.

@decision DEC-RESEARCH-007: LLM structures raw research into ResearchResult.
@title LLM-driven evidence structuring
@status accepted
@rationale Uses the configured LLM to extract factual claims, assess source
reliability, identify gaps, and format evidence for pipeline injection. The
formatted_evidence string is what techniques see; the full ResearchResult
preserves provenance as an artifact.

@decision DEC-RESEARCH-012: URL backfill restores citation URLs dropped by LLM.
@title Post-structuring URL backfill from raw citations
@status accepted
@rationale The LLM structurer frequently omits URLs when generating ResearchSource
objects, leaving url=None and breaking source verification (nothing to fetch).
After generate_structured() returns, _backfill_urls() matches sources to the
original SearchResult citations by title (exact first, then substring, both
case-insensitive) and fills in any missing URLs. Deterministic, cheap, transparent.
"""

from __future__ import annotations

import logging

from sat.models.research import ResearchResult, ResearchSource
from sat.providers.base import LLMMessage, LLMProvider
from sat.research.base import ResearchResponse, SearchResult

logger = logging.getLogger(__name__)


STRUCTURER_SYSTEM_PROMPT = """You are an intelligence analyst structuring raw research \
into a formal evidence assessment.

Given raw research findings, you must produce a structured analysis with:

1. **Sources**: Identify each distinct source. Assess reliability as High/Medium/Low/Unknown. \
Include the original URL for each source — this is critical for verification.
2. **Claims**: Extract specific factual claims. Link each to source IDs. Rate confidence.
3. **Evidence Summary**: Write a concise evidence summary suitable for feeding into \
analytic techniques.
4. **Gaps**: Identify what important information is missing.

## Output Requirements

- technique_id: "research"
- technique_name: "Deep Research"
- summary: Brief overview of what was found
- query: The original research query
- sources: List of ResearchSource objects (id like "S1", "S2", etc.) \
— sources must include the url field with the original citation URL
- claims: List of ResearchClaim objects linked to source IDs
- formatted_evidence: A well-structured text summary of the evidence \
(this is what downstream techniques will see)
- research_provider: The provider that was used
- gaps_identified: List of information gaps

## formatted_evidence Format

Structure the formatted_evidence field as follows:

### Key Findings
- Bullet points of the most important findings with source attribution

### Source Landscape
- Brief characterization of source quality and diversity

### Confidence Assessment
- Overall confidence level with reasoning

### Information Gaps
- What is missing or uncertain"""


def _backfill_urls(
    result: ResearchResult,
    citations: list[SearchResult],
) -> ResearchResult:
    """Fill in missing URLs on ResearchSource objects from original citations.

    The LLM structurer frequently omits URLs when generating sources. This
    function matches each source with url=None back to the original citations
    by title and fills in the URL. Matching order:
      1. Exact title match (case-insensitive)
      2. Substring match (source title inside citation title, or vice versa)

    Sources that already have a URL are left unchanged. Returns a new
    ResearchResult via model_copy — never mutates the input.

    Args:
        result: The structured ResearchResult returned by the LLM.
        citations: The original SearchResult citations from the research backend.

    Returns:
        A new ResearchResult (model_copy) with URLs backfilled where possible.
    """
    if not citations:
        return result

    updated_sources: list[ResearchSource] = []
    backfilled = 0
    unmatched = 0

    for source in result.sources:
        if source.url is not None:
            # Already has a URL — leave it alone
            updated_sources.append(source)
            continue

        source_lower = source.title.lower()
        matched_url: str | None = None

        # Pass 1: exact match (case-insensitive)
        for citation in citations:
            if citation.title.lower() == source_lower:
                matched_url = citation.url
                break

        # Pass 2: substring match (either title contained in the other)
        if matched_url is None:
            for citation in citations:
                cit_lower = citation.title.lower()
                if source_lower in cit_lower or cit_lower in source_lower:
                    matched_url = citation.url
                    break

        if matched_url is not None:
            updated_sources.append(source.model_copy(update={"url": matched_url}))
            backfilled += 1
        else:
            updated_sources.append(source)
            unmatched += 1

    if backfilled:
        logger.info("URL backfill: %d source(s) matched from citations", backfilled)
    if unmatched:
        logger.warning("URL backfill: %d source(s) could not be matched to any citation", unmatched)

    return result.model_copy(update={"sources": updated_sources})


def _validate_extraction_coverage(
    raw_content_length: int,
    citation_count: int,
    result: ResearchResult,
    query: str = "",
) -> None:
    """Log warnings when structured output looks thin relative to the raw input.

    This is a diagnostic aid — it never raises exceptions or interrupts the
    pipeline. Warnings surface potential LLM structuring quality issues:
    underextracted claims, dropped citations, and missing gaps on complex topics.

    Args:
        raw_content_length: Length of the raw research content string in chars.
        citation_count: Number of citations in the raw ResearchResponse.
        result: The structured ResearchResult to validate.
        query: The original research query (used for complexity heuristic).
    """
    # Claim density: substantial raw content should yield at least 3 claims
    if raw_content_length > 2000 and len(result.claims) < 3:
        logger.warning(
            "Low claim density: raw content is %d chars but only %d claim(s) extracted "
            "(expected ≥3 for content this size)",
            raw_content_length,
            len(result.claims),
        )

    # Source coverage: structured sources should cover at least half of citations
    if citation_count > 0 and len(result.sources) < citation_count / 2:
        logger.warning(
            "Low source coverage: %d citation(s) in raw response but only %d source(s) "
            "structured (expected ≥%d)",
            citation_count,
            len(result.sources),
            citation_count // 2,
        )

    # Gap detection: a non-trivial query with zero gaps is suspicious
    if len(query) > 20 and len(result.gaps_identified) == 0:
        logger.warning(
            "Zero gaps identified for query %r — complex topics typically have "
            "information gaps; structurer may have skipped gap analysis",
            query,
        )


async def structure_evidence(
    raw: ResearchResponse,
    query: str,
    provider: LLMProvider,
    research_provider_name: str,
) -> ResearchResult:
    """Structure raw research into a ResearchResult with provenance.

    Args:
        raw: Raw research response from the backend
        query: Original research query
        provider: LLM provider for structuring
        research_provider_name: Name of the research backend used
    """
    user_content = f"## Research Query\n\n{query}\n\n## Raw Research Findings\n\n{raw.content}"
    if raw.citations:
        user_content += "\n\n## Sources Found\n\n"
        for i, citation in enumerate(raw.citations, 1):
            user_content += f"{i}. [{citation.title}]({citation.url}): {citation.snippet}\n"

    result = await provider.generate_structured(
        system_prompt=STRUCTURER_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=user_content)],
        output_schema=ResearchResult,
        max_tokens=16384,
    )

    assert isinstance(result, ResearchResult)
    result.research_provider = research_provider_name

    # Backfill any URLs the LLM dropped during structuring
    if raw.citations:
        result = _backfill_urls(result, raw.citations)

    # Validate extraction coverage and log warnings for thin results
    _validate_extraction_coverage(
        raw_content_length=len(raw.content),
        citation_count=len(raw.citations),
        result=result,
        query=query,
    )

    return result
