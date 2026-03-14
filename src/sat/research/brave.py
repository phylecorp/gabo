"""Brave Search research backend.

@decision DEC-RESEARCH-004: Brave Search API for targeted factual queries.
@title Brave Search as secondary research backend
@status accepted
@rationale Returns web search results with snippets and URLs. Good for targeted
fact-finding. Uses httpx for async HTTP. Falls back to this when Perplexity
is unavailable.
"""

from __future__ import annotations

import logging
import os

import httpx

from sat.research.base import ResearchResponse, SearchResult

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveProvider:
    """Research provider using Brave Search API."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("BRAVE_API_KEY")
        if not key:
            raise ValueError("No Brave API key. Set BRAVE_API_KEY or pass api_key.")
        self._api_key = key

    async def research(
        self,
        query: str,
        context: str | None = None,
        max_sources: int = 10,
    ) -> ResearchResponse:
        """Execute research via Brave Search."""
        search_query = query
        if context:
            search_query = f"{query} {context[:200]}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                BRAVE_SEARCH_URL,
                headers={
                    "X-Subscription-Token": self._api_key,
                    "Accept": "application/json",
                },
                params={"q": search_query, "count": max_sources},
            )
            response.raise_for_status()
            data = response.json()

        results: list[SearchResult] = []
        content_parts: list[str] = []
        for item in data.get("web", {}).get("results", []):
            title = item.get("title", "")
            url = item.get("url", "")
            snippet = item.get("description", "")
            results.append(SearchResult(title=title, url=url, snippet=snippet))
            content_parts.append(f"**{title}**\n{snippet}\nSource: {url}")

        content = "\n\n".join(content_parts) if content_parts else "No results found."
        return ResearchResponse(content=content, citations=results)
