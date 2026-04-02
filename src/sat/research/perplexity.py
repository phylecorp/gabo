"""Perplexity research backend using sonar-deep-research model.

@decision DEC-RESEARCH-003: Perplexity via OpenAI-compatible API.
@title Perplexity as primary research backend
@status accepted
@rationale Uses sonar-deep-research for comprehensive multi-step research with
inline citations. OpenAI-compatible API means we reuse the openai SDK. Priority
backend when PERPLEXITY_API_KEY is available.

@decision DEC-RESEARCH-011
@title Model resolution via resolve_research_model() for config-driven overrides
@status accepted
@rationale The default model now comes from resolve_research_model("perplexity")
rather than a hardcoded string. This allows users to set a preferred model in
~/.sat/config.json (research_model field) or the PERPLEXITY_RESEARCH_MODEL env
var without needing to modify code. Explicit constructor param still takes
priority, preserving existing programmatic use.
"""

from __future__ import annotations

import logging
import os

import openai

from sat.config import resolve_research_model
from sat.events import EventBus, NullBus, ProviderPolling
from sat.research.base import ResearchResponse, SearchResult

logger = logging.getLogger(__name__)


class PerplexityProvider:
    """Research provider using Perplexity's sonar-deep-research model."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        events: EventBus | None = None,
    ) -> None:
        key = api_key or os.environ.get("PERPLEXITY_API_KEY")
        if not key:
            raise ValueError("No Perplexity API key. Set PERPLEXITY_API_KEY or pass api_key.")
        self._client = openai.AsyncOpenAI(api_key=key, base_url="https://api.perplexity.ai")
        # Resolution: explicit param > config file > env var > hardcoded default
        self._model = model or resolve_research_model("perplexity")
        # EventBus for liveness events (DEC-RESEARCH-015). NullBus when not provided.
        self._events: EventBus = events if events is not None else NullBus

    async def research(
        self,
        query: str,
        context: str | None = None,
        max_sources: int = 10,
    ) -> ResearchResponse:
        """Execute research via Perplexity.

        Perplexity has no polling loop — it makes a single blocking API call that
        can take minutes. Emits one ProviderPolling before the call starts so the
        frontend knows this provider is alive and awaiting a response (DEC-RESEARCH-015).
        """
        system_msg = (
            "You are a research assistant. Provide comprehensive, factual information "
            "with citations. Focus on verifiable facts, data, and expert analysis."
        )
        user_msg = query
        if context:
            user_msg = f"Context: {context}\n\nResearch question: {query}"

        # Signal liveness: single polling event before the blocking call.
        await self._events.emit(ProviderPolling(
            name="perplexity",
            attempt=1,
            max_attempts=1,
            status="awaiting_response",
        ))

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        )

        content = response.choices[0].message.content or ""

        # Extract citations if available in the response
        citations: list[SearchResult] = []
        if hasattr(response, "citations") and response.citations:
            for i, url in enumerate(response.citations):
                citations.append(SearchResult(title=f"Source {i + 1}", url=url, snippet=""))

        return ResearchResponse(content=content, citations=citations)
