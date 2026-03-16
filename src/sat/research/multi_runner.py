"""Multi-provider research runner: queries all available deep research providers in parallel.

@decision DEC-RESEARCH-011: Parallel multi-provider deep research with graceful degradation.
@title Multi-model research orchestration
@status accepted
@rationale Querying OpenAI, Perplexity, and Gemini deep research in parallel produces
richer, cross-validated evidence. Each provider may have different training data and
search capabilities. Graceful degradation ensures the pipeline works even if only one
provider is available, falling back to LLM research if none are. Transient failures
(timeouts, rate limits, connection errors, and OpenAI server-side ResearchRequestFailed)
trigger a single retry when all providers fail, preventing total pipeline failure from
temporary issues.

@decision DEC-RESEARCH-012
@title Research provider API keys resolved from config file before env var
@status accepted
@rationale The Settings UI saves API keys to ~/.sat/config.json via ProviderConfig.
Research providers previously only checked os.environ, so keys saved through the UI
were silently ignored. discover_providers() now calls _load_config_file_key() for each
research provider and passes the resolved key to the constructor. This matches the
approach LLM providers already use via ProviderConfig.resolve_api_key(). The provider
constructors' existing fallback (api_key or os.environ.get(...)) still handles env-var-only
configurations, preserving backward compatibility.
"""

from __future__ import annotations

import asyncio
import logging

from sat.config import _load_config_file_key
from sat.errors import is_transient_error
from sat.events import (
    EventBus,
    NullBus,
    ProviderCompleted,
    ProviderFailed,
    ProviderStarted,
    ResearchCompleted,
    ResearchStarted,
    StageStarted,
)
from sat.models.research import ResearchResult
from sat.providers.base import LLMMessage, LLMProvider
from sat.research.base import ResearchProvider, ResearchResponse, SearchResult
from sat.research.runner import QUERY_SYSTEM_PROMPT
from sat.research.structurer import structure_evidence

logger = logging.getLogger(__name__)

_RETRY_DELAY = 5  # seconds before retry — negligible vs. the 1200s already spent

# Research-specific transient error names beyond the shared base set.
# - TimeoutException, ConnectError: httpx transport errors
# - ResearchRequestFailed: openai_deep server-side polling failure
_RESEARCH_EXTRA_TRANSIENT: frozenset[str] = frozenset(
    {
        "TimeoutException",  # httpx
        "ConnectError",  # httpx
        "ResearchRequestFailed",  # openai_deep server-side failure
    }
)


def discover_providers(
    llm_provider: LLMProvider | None = None,
) -> list[tuple[str, ResearchProvider]]:
    """Discover available research providers by attempting construction.

    Returns list of (name, provider) tuples for providers with valid API keys.
    Priority: deep research providers + brave (always attempted), then LLM fallback
    only when nothing else is available.

    API key resolution order per provider:
    1. ~/.sat/config.json (populated by Settings UI)
    2. Environment variable (legacy / CLI workflow)

    The provider constructors themselves implement the env-var fallback
    (api_key or os.environ.get(...)), so passing None here is safe when no
    config-file key is found — the constructor will try the env var itself.
    """
    providers: list[tuple[str, ResearchProvider]] = []

    # Try deep research providers
    try:
        from sat.research.openai_deep import OpenAIDeepResearchProvider

        providers.append(
            ("openai_deep", OpenAIDeepResearchProvider(api_key=_load_config_file_key("openai")))
        )
        logger.info("OpenAI deep research: available")
    except (ValueError, ImportError):
        logger.debug("OpenAI deep research: unavailable (no API key)")

    try:
        from sat.research.perplexity import PerplexityProvider

        providers.append(
            ("perplexity", PerplexityProvider(api_key=_load_config_file_key("perplexity")))
        )
        logger.info("Perplexity deep research: available")
    except (ValueError, ImportError):
        logger.debug("Perplexity deep research: unavailable (no API key)")

    try:
        from sat.research.gemini_deep import GeminiDeepResearchProvider

        providers.append(
            ("gemini_deep", GeminiDeepResearchProvider(api_key=_load_config_file_key("gemini")))
        )
        logger.info("Gemini deep research: available")
    except (ValueError, ImportError):
        logger.debug("Gemini deep research: unavailable (no API key)")

    # Always include Brave search alongside deep providers
    try:
        from sat.research.brave import BraveProvider

        providers.append(
            ("brave", BraveProvider(api_key=_load_config_file_key("brave")))
        )
        logger.info("Brave search: available")
    except (ValueError, ImportError):
        logger.debug("Brave search: unavailable (no API key)")

    # LLM fallback only if nothing else is available
    if not providers and llm_provider:
        from sat.research.llm_search import LLMResearchProvider

        providers.append(("llm", LLMResearchProvider(llm_provider)))
        logger.info("Falling back to LLM research")

    return providers


def merge_responses(results: list[tuple[str, ResearchResponse]]) -> ResearchResponse:
    """Merge multiple research responses into a single response.

    Combines content with provider-attribution headers. Deduplicates citations by URL.
    """
    sections = []
    seen_urls: set[str] = set()
    all_citations: list[SearchResult] = []

    for name, response in results:
        sections.append(f"## {name} Research\n\n{response.content}")
        for citation in response.citations:
            if citation.url not in seen_urls:
                seen_urls.add(citation.url)
                all_citations.append(citation)

    merged_content = "\n\n---\n\n".join(sections)
    return ResearchResponse(content=merged_content, citations=all_citations)


async def run_multi_research(
    question: str,
    llm_provider: LLMProvider,
    max_sources: int = 10,
    events: EventBus | None = None,
) -> ResearchResult:
    """Execute research across all available providers in parallel.

    Discovers available providers, generates a search query, runs all providers
    concurrently, merges successful results, and structures the evidence.

    Args:
        question: The analytic question to research.
        llm_provider: LLM for query generation and evidence structuring.
        max_sources: Maximum sources to retrieve per provider.
        events: Optional event bus for progress visibility. Uses NullBus if omitted.
    """
    bus = events or NullBus

    providers = discover_providers(llm_provider)
    if not providers:
        raise ValueError("No research providers available. Configure at least one API key.")

    provider_names = [name for name, _ in providers]
    logger.info("Running multi-provider research with: %s", ", ".join(provider_names))

    # Generate optimized search query
    query_result = await llm_provider.generate(
        system_prompt=QUERY_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=question)],
        max_tokens=200,
        temperature=0.1,
    )
    search_query = query_result.text.strip()
    logger.info("Generated search query: %s", search_query)

    await bus.emit(ResearchStarted(provider_names=provider_names, query=search_query))

    # Signal each provider as starting so the UI can show pending → running immediately.
    # These are emitted synchronously before the parallel gather so the frontend sees
    # all provider dots transition to "running" before any results arrive.
    for name, _ in providers:
        await bus.emit(ProviderStarted(name=name))

    # Run all providers in parallel
    tasks = [
        prov.research(query=search_query, context=question, max_sources=max_sources)
        for _, prov in providers
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter successes and log failures
    successes: list[tuple[str, ResearchResponse]] = []
    retryable: list[tuple[str, ResearchProvider]] = []
    for (name, prov), result in zip(providers, raw_results):
        if isinstance(result, Exception):
            if is_transient_error(result, _RESEARCH_EXTRA_TRANSIENT):
                logger.warning("Provider %s hit transient error: %s", name, result)
                retryable.append((name, prov))
                await bus.emit(ProviderFailed(name=name, error=str(result), transient=True))
            else:
                logger.warning("Provider %s failed: %s", name, result)
                await bus.emit(ProviderFailed(name=name, error=str(result), transient=False))
        else:
            successes.append((name, result))
            logger.info("Provider %s returned %d citations", name, len(result.citations))
            await bus.emit(
                ProviderCompleted(
                    name=name,
                    citation_count=len(result.citations),
                    content_length=len(result.content),
                )
            )

    # Retry transient failures once if nothing succeeded
    if not successes and retryable:
        retry_names = [n for n, _ in retryable]
        logger.info(
            "All providers failed with transient errors, retrying: %s",
            ", ".join(retry_names),
        )
        await asyncio.sleep(_RETRY_DELAY)
        retry_tasks = [
            prov.research(query=search_query, context=question, max_sources=max_sources)
            for _, prov in retryable
        ]
        retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
        for (name, _), result in zip(retryable, retry_results):
            if isinstance(result, Exception):
                logger.warning("Provider %s failed on retry: %s", name, result)
                await bus.emit(ProviderFailed(name=name, error=str(result), transient=False))
            else:
                successes.append((name, result))
                logger.info(
                    "Provider %s succeeded on retry with %d citations",
                    name,
                    len(result.citations),
                )
                await bus.emit(
                    ProviderCompleted(
                        name=name,
                        citation_count=len(result.citations),
                        content_length=len(result.content),
                    )
                )

    if not successes:
        raise RuntimeError("All research providers failed")

    # Merge responses
    merged = merge_responses(successes)

    # Structure evidence using LLM
    success_names = [name for name, _ in successes]
    provider_label = f"multi({','.join(success_names)})"

    await bus.emit(StageStarted(stage="structuring"))
    result = await structure_evidence(
        raw=merged,
        query=search_query,
        provider=llm_provider,
        research_provider_name=provider_label,
    )
    await bus.emit(
        ResearchCompleted(
            source_count=len(result.sources),
            claim_count=len(result.claims),
            provider_label=provider_label,
        )
    )
    return result
