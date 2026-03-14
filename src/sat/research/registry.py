"""Research provider registry with auto-selection based on available API keys.

@decision DEC-RESEARCH-006: Auto-selection priority: Perplexity > Brave > LLM.
@title Graceful fallback across research backends
@status accepted
@rationale Perplexity provides the best research quality (multi-step with citations).
Brave is a good fallback for targeted queries. LLM fallback always works but uses
training data only. Auto-selection checks env vars to find the best available backend.
"""

from __future__ import annotations

import logging
import os

from sat.providers.base import LLMProvider
from sat.research.base import ResearchProvider

logger = logging.getLogger(__name__)


def create_research_provider(
    provider_name: str = "auto",
    api_key: str | None = None,
    llm_provider: LLMProvider | None = None,
) -> ResearchProvider:
    """Create a research provider, auto-selecting if not specified.

    Args:
        provider_name: "perplexity", "brave", "llm", "openai_deep", "gemini_deep", or "auto"
        api_key: API key for the research provider
        llm_provider: LLM provider for fallback research
    """
    if provider_name == "openai_deep":
        from sat.research.openai_deep import OpenAIDeepResearchProvider

        return OpenAIDeepResearchProvider(api_key=api_key)

    if provider_name == "gemini_deep":
        from sat.research.gemini_deep import GeminiDeepResearchProvider

        return GeminiDeepResearchProvider(api_key=api_key)

    if provider_name == "perplexity":
        from sat.research.perplexity import PerplexityProvider

        return PerplexityProvider(api_key=api_key)

    if provider_name == "brave":
        from sat.research.brave import BraveProvider

        return BraveProvider(api_key=api_key)

    if provider_name == "llm":
        if not llm_provider:
            raise ValueError("LLM research requires an llm_provider")
        from sat.research.llm_search import LLMResearchProvider

        return LLMResearchProvider(llm_provider)

    if provider_name == "auto":
        if api_key or os.environ.get("PERPLEXITY_API_KEY"):
            logger.info("Auto-selected Perplexity research provider")
            from sat.research.perplexity import PerplexityProvider

            return PerplexityProvider(api_key=api_key)

        if os.environ.get("BRAVE_API_KEY"):
            logger.info("Auto-selected Brave research provider")
            from sat.research.brave import BraveProvider

            return BraveProvider()

        if llm_provider:
            logger.info("Auto-selected LLM fallback research provider")
            from sat.research.llm_search import LLMResearchProvider

            return LLMResearchProvider(llm_provider)

        raise ValueError(
            "No research provider available. Set PERPLEXITY_API_KEY, BRAVE_API_KEY, "
            "or provide an LLM provider for fallback research."
        )

    raise ValueError(
        f"Unknown research provider: {provider_name!r}. "
        "Available: perplexity, brave, llm, openai_deep, gemini_deep, auto"
    )
