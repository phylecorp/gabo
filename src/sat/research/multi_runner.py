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

@decision DEC-MODELS-003
@title Research providers accept model override from config in discover_providers()
@status accepted
@rationale discover_providers() now also passes model=_load_config_file_research_model(provider)
to each deep research provider constructor. This ensures that when a user configures a
research_model in ~/.sat/config.json via the Settings UI, it is explicitly forwarded through
the multi-runner path. The provider constructors already resolve their own model via
resolve_research_model() as a fallback, so passing None here is safe and backward compatible.
Explicit wiring in discover_providers() gives callers visibility into which model is being used
without having to inspect each provider's internal state.
"""

from __future__ import annotations

import asyncio
import logging

from sat.config import _load_config_file_key, _load_config_file_research_model
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
    events: EventBus | None = None,
) -> list[tuple[str, ResearchProvider]]:
    """Discover available research providers by attempting construction.

    Returns list of (name, provider) tuples for providers with valid API keys.
    Priority: deep research providers + brave (always attempted), then LLM fallback
    only when nothing else is available.

    Resolution order per provider:
    1. API key: ~/.sat/config.json > environment variable
    2. Model: ~/.sat/config.json research_model field > PROVIDER_RESEARCH_MODEL env var
              > built-in default (resolved via each provider's constructor)

    The provider constructors implement the full model resolution chain via
    resolve_research_model(). Passing model=_load_config_file_research_model(provider)
    here explicitly promotes the config-file value to the highest-priority slot,
    so the Settings UI model preference takes effect without relying on the
    provider's internal resolution (DEC-MODELS-003). Passing None is safe when
    no config-file model is set — the constructor falls back to env var then default.

    Args:
        llm_provider: Optional LLM provider for the fallback LLM research path.
        events: Optional EventBus for liveness events (DEC-RESEARCH-015). Passed
            to providers that support it (OpenAI, Gemini, Perplexity). NullBus
            default inside each provider when not provided.
    """
    providers: list[tuple[str, ResearchProvider]] = []

    # Try deep research providers
    try:
        from sat.research.openai_deep import OpenAIDeepResearchProvider

        providers.append(
            (
                "openai_deep",
                OpenAIDeepResearchProvider(
                    api_key=_load_config_file_key("openai"),
                    model=_load_config_file_research_model("openai"),
                    events=events,
                ),
            )
        )
        logger.info("OpenAI deep research: available")
    except (ValueError, ImportError):
        logger.debug("OpenAI deep research: unavailable (no API key)")

    try:
        from sat.research.perplexity import PerplexityProvider

        providers.append(
            (
                "perplexity",
                PerplexityProvider(
                    api_key=_load_config_file_key("perplexity"),
                    model=_load_config_file_research_model("perplexity"),
                    events=events,
                ),
            )
        )
        logger.info("Perplexity deep research: available")
    except (ValueError, ImportError):
        logger.debug("Perplexity deep research: unavailable (no API key)")

    try:
        from sat.research.gemini_deep import GeminiDeepResearchProvider

        providers.append(
            (
                "gemini_deep",
                GeminiDeepResearchProvider(
                    api_key=_load_config_file_key("gemini"),
                    model=_load_config_file_research_model("gemini"),
                    events=events,
                ),
            )
        )
        logger.info("Gemini deep research: available")
    except (ValueError, ImportError):
        logger.debug("Gemini deep research: unavailable (no API key)")

    # Always include Brave search alongside deep providers (no polling, no events needed)
    try:
        from sat.research.brave import BraveProvider

        providers.append(("brave", BraveProvider(api_key=_load_config_file_key("brave"))))
        logger.info("Brave search: available")
    except (ValueError, ImportError):
        logger.debug("Brave search: unavailable (no API key)")

    # LLM fallback only if nothing else is available (no polling, no events needed)
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

    providers = discover_providers(llm_provider, events=bus)
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


class MultiResearchAdapter:
    """Wraps multi-provider research into the ResearchProvider protocol interface.

    @decision DEC-RESEARCH-014
    @title MultiResearchAdapter bridges gap resolver to multi-provider research
    @status accepted
    @rationale Gap resolution previously used a single-provider path regardless of the
    pipeline's research mode. This meant that gap follow-up queries received narrower,
    single-source evidence while the initial research benefited from cross-validated
    multi-provider results. MultiResearchAdapter implements the ResearchProvider protocol
    so gap_resolver.resolve_gaps() can accept it without modification. When mode=="multi",
    pipeline.py passes a MultiResearchAdapter instead of a single provider, giving gap
    resolution the same cross-validated evidence quality as the initial research phase.
    The adapter runs discover_providers() + parallel gather + merge_responses() — the
    same core path as run_multi_research() — but returns a raw ResearchResponse rather
    than a structured ResearchResult, because gap_resolver calls structure_evidence()
    internally after receiving the raw response.
    """

    def __init__(self, llm_provider: LLMProvider) -> None:
        self._llm = llm_provider

    async def research(
        self,
        query: str,
        context: str | None = None,
        max_sources: int = 10,
    ) -> ResearchResponse:
        """Run all available providers in parallel and return merged raw response.

        Discovers providers each call so dynamic API key changes take effect.
        Falls back gracefully: if all providers fail, raises RuntimeError.
        """
        providers = discover_providers(self._llm)
        if not providers:
            raise ValueError("No research providers available for gap resolution.")

        provider_names = [name for name, _ in providers]
        logger.info(
            "MultiResearchAdapter: gap follow-up with providers: %s",
            ", ".join(provider_names),
        )

        tasks = [
            prov.research(query=query, context=context, max_sources=max_sources)
            for _, prov in providers
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        successes: list[tuple[str, ResearchResponse]] = []
        for (name, _), result in zip(providers, raw_results):
            if isinstance(result, Exception):
                logger.warning("MultiResearchAdapter: provider %s failed: %s", name, result)
            else:
                successes.append((name, result))
                logger.info(
                    "MultiResearchAdapter: provider %s returned %d citations",
                    name,
                    len(result.citations),
                )

        if not successes:
            raise RuntimeError("All research providers failed during gap resolution follow-up")

        return merge_responses(successes)
