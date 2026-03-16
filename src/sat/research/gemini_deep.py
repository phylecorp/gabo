"""Gemini deep research provider using Interactions API.

@decision DEC-RESEARCH-010: Gemini deep research via Interactions API.
@title Gemini background deep research with polling
@status accepted
@rationale Uses the v1beta Interactions API with deep-research-pro agent.
Background mode with polling every 15s. Extracts citations via fallback chain
(sources > groundingMetadata > regex). Returns ResearchResponse.

@decision DEC-RESEARCH-011
@title Model resolution via resolve_research_model() for config-driven overrides
@status accepted
@rationale The agent name now resolves via resolve_research_model("gemini")
rather than the module-level GEMINI_DEEP_AGENT env var. This lets users
configure the deep research agent in ~/.sat/config.json or via
GEMINI_RESEARCH_MODEL without restarting. Explicit constructor param wins.
The module-level AGENT constant is removed; _submit_request uses self._agent.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

import httpx

from sat.config import resolve_research_model
from sat.research.base import ResearchResponse, SearchResult

logger = logging.getLogger(__name__)

# Constants
POLL_INTERVAL = 15  # seconds
MAX_POLL_ATTEMPTS = 80  # 20 minutes max


class GeminiDeepResearchProvider:
    """Research provider using Gemini's deep research agent."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError("No Gemini API key. Set GEMINI_API_KEY or pass api_key.")
        self._api_key = key
        self._base_url = "https://generativelanguage.googleapis.com/v1beta"
        # Resolution: explicit param > config file > GEMINI_RESEARCH_MODEL env var > default
        self._agent = model or resolve_research_model("gemini")

    async def research(
        self,
        query: str,
        context: str | None = None,
        max_sources: int = 10,
    ) -> ResearchResponse:
        """Execute deep research via Gemini Interactions API."""
        topic = query
        if context:
            topic = f"{context}\n\n{query}"

        # Submit research request
        interaction_id = await self._submit_request(topic)
        logger.info(f"Submitted Gemini deep research request {interaction_id}")

        # Poll for completion
        result = await self._poll_until_complete(interaction_id)

        # Extract report and citations
        report = self._extract_report(result)
        citations = self._extract_citations(result, report)

        return ResearchResponse(content=report, citations=citations)

    async def _submit_request(self, topic: str) -> str:
        """Submit background research request and return interaction ID."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/interactions",
                headers={
                    "x-goog-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "input": topic,
                    "agent": self._agent,
                    "background": True,
                    "store": True,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            # Try multiple possible ID fields
            return data.get("name") or data.get("id") or data.get("interactionId", "")

    async def _poll_until_complete(self, interaction_id: str) -> dict:
        """Poll the interaction endpoint until research is complete."""
        async with httpx.AsyncClient() as client:
            for attempt in range(MAX_POLL_ATTEMPTS):
                response = await client.get(
                    f"{self._base_url}/interactions/{interaction_id}",
                    headers={"x-goog-api-key": self._api_key},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                # Status can be in multiple locations
                status = data.get("status") or data.get("metadata", {}).get("status", "")
                status_lower = status.lower()
                logger.debug(f"Poll attempt {attempt + 1}/{MAX_POLL_ATTEMPTS}: status={status}")

                if status_lower == "completed":
                    return data
                elif status_lower == "failed":
                    raise RuntimeError(f"Research request {interaction_id} failed")

                await asyncio.sleep(POLL_INTERVAL)

            raise TimeoutError(
                f"Research request {interaction_id} timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s"
            )

    def _extract_report(self, result: dict) -> str:
        """Extract the research report text from the response."""
        # Try outputs array first
        outputs = result.get("outputs", [])
        if outputs:
            last_output = outputs[-1]
            text = last_output.get("text") or last_output.get("content", "")
            if text:
                return text

        # Fallback to result field
        result_obj = result.get("result", {})
        return result_obj.get("text") or result_obj.get("content", "")

    def _extract_citations(self, result: dict, report: str) -> list[SearchResult]:
        """Extract citations from sources, groundingMetadata, or regex fallback."""
        citations = []

        # Try sources field
        sources = result.get("sources", [])
        if sources:
            for source in sources:
                url = source.get("url", "")
                title = source.get("title", url)
                if url:
                    citations.append(SearchResult(title=title, url=url, snippet=""))
            return citations

        # Try groundingMetadata
        metadata = result.get("groundingMetadata", {})
        queries = metadata.get("webSearchQueries", [])
        if queries:
            for query in queries:
                url = query.get("url", "")
                title = query.get("title", url)
                if url:
                    citations.append(SearchResult(title=title, url=url, snippet=""))
            return citations

        # Fallback: extract URLs via regex
        url_pattern = r"https?://[^\s\)]+"
        urls = re.findall(url_pattern, report)
        for url in urls:
            citations.append(SearchResult(title=url, url=url, snippet=""))

        return citations
