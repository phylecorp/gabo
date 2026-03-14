"""Research runner: orchestrates the full deep research pipeline.

@decision DEC-RESEARCH-008: Runner encapsulates research + structuring.
@title Single entry point for pipeline research
@status accepted
@rationale Single entry point for the pipeline to call. Handles query generation,
research execution, and evidence structuring. Returns ResearchResult ready for
artifact writing and evidence injection.
"""

from __future__ import annotations

import logging

from sat.events import (
    EventBus,
    NullBus,
    ProviderCompleted,
    ResearchCompleted,
    ResearchStarted,
)
from sat.models.research import ResearchResult
from sat.providers.base import LLMMessage, LLMProvider
from sat.research.base import ResearchProvider
from sat.research.structurer import structure_evidence

logger = logging.getLogger(__name__)

QUERY_SYSTEM_PROMPT = """You are a research query specialist. Given an analytic question, \
generate an optimal search query that will find the most relevant factual information.

The query should:
- Focus on factual, verifiable information
- Be specific enough to get relevant results
- Cover the key aspects of the question
- Be suitable for a web search engine

Respond with ONLY the search query text, nothing else."""


async def run_research(
    question: str,
    research_provider: ResearchProvider,
    llm_provider: LLMProvider,
    max_sources: int = 10,
    events: EventBus | None = None,
) -> ResearchResult:
    """Execute the full research pipeline.

    Args:
        question: The analytic question to research
        research_provider: Backend for fact-gathering
        llm_provider: LLM for query generation and structuring
        max_sources: Maximum sources to retrieve
        events: Optional event bus for progress visibility. Uses NullBus if omitted.

    Returns:
        Structured ResearchResult with evidence and provenance
    """
    bus = events or NullBus

    # Step 1: Generate optimized search query
    query_result = await llm_provider.generate(
        system_prompt=QUERY_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=question)],
        max_tokens=200,
        temperature=0.1,
    )
    search_query = query_result.text.strip()
    logger.info("Generated search query: %s", search_query)

    # Step 2: Execute research
    provider_name = type(research_provider).__name__.lower()
    if "perplexity" in provider_name:
        research_name = "perplexity"
    elif "brave" in provider_name:
        research_name = "brave"
    else:
        research_name = "llm"

    await bus.emit(ResearchStarted(provider_names=[research_name], query=search_query))

    raw_response = await research_provider.research(
        query=search_query, context=question, max_sources=max_sources
    )
    logger.info("Research returned %d citations", len(raw_response.citations))

    await bus.emit(
        ProviderCompleted(
            name=research_name,
            citation_count=len(raw_response.citations),
            content_length=len(raw_response.content),
        )
    )

    # Step 3: Structure evidence
    result = await structure_evidence(
        raw=raw_response,
        query=search_query,
        provider=llm_provider,
        research_provider_name=research_name,
    )

    await bus.emit(
        ResearchCompleted(
            source_count=len(result.sources),
            claim_count=len(result.claims),
            provider_label=research_name,
        )
    )
    return result
