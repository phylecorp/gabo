"""OpenAI deep research provider using o3-deep-research.

@decision DEC-RESEARCH-009: OpenAI deep research via Responses API.
@title OpenAI background deep research with polling
@status accepted
@rationale Uses the Responses API with background=true for deep research that
can take 2-10 minutes. Polls until completion. Primary model o3-deep-research
with o4-mini fallback on 404. Returns ResearchResponse with report and citations.
ResearchRequestFailed (a RuntimeError subclass) is raised when OpenAI returns
status='failed', enabling multi_runner.py to classify the error as transient
and retry the request, since server-side failures are intermittent.

@decision DEC-RESEARCH-011
@title Model resolution via resolve_research_model() for config-driven overrides
@status accepted
@rationale The primary model now resolves via resolve_research_model("openai")
rather than a module-level env var constant. This lets users configure the deep
research model in ~/.sat/config.json or via OPENAI_RESEARCH_MODEL without
restarting. Explicit constructor param wins; FALLBACK_MODEL (for 404 auto-
downgrade) remains a module-level constant since it's not user-configurable.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx

from sat.config import resolve_research_model
from sat.research.base import ResearchResponse, SearchResult

logger = logging.getLogger(__name__)


class ResearchRequestFailed(RuntimeError):
    """OpenAI research request returned status='failed'. Retryable.

    Subclasses RuntimeError for backward compatibility with existing catch-all
    error handling, but provides a specific type name that multi_runner.py's
    _is_research_transient() can identify for retry classification.
    """


# Constants
# FALLBACK_MODEL is used for automatic 404 downgrade — not config-driven.
FALLBACK_MODEL = os.environ.get("OPENAI_DEEP_RESEARCH_FALLBACK", "o4-mini-deep-research-2025-06-26")
POLL_INTERVAL = 10  # seconds
MAX_POLL_ATTEMPTS = 120  # 20 minutes max


class OpenAIDeepResearchProvider:
    """Research provider using OpenAI's deep research models."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("No OpenAI API key. Set OPENAI_API_KEY or pass api_key.")
        self._api_key = key
        self._base_url = "https://api.openai.com/v1"
        # Resolution: explicit param > config file > OPENAI_RESEARCH_MODEL env var > default
        self._primary_model = model or resolve_research_model("openai")

    async def research(
        self,
        query: str,
        context: str | None = None,
        max_sources: int = 10,
    ) -> ResearchResponse:
        """Execute deep research via OpenAI Responses API."""
        topic = query
        if context:
            topic = f"{context}\n\n{query}"

        # Try primary model first, fallback to o4-mini on 404
        response_id = None
        try:
            response_id = await self._submit_request(topic, self._primary_model)
            logger.info(f"Submitted deep research request {response_id} with {self._primary_model}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"{self._primary_model} not available, falling back to {FALLBACK_MODEL}")
                response_id = await self._submit_request(topic, FALLBACK_MODEL)
                logger.info(f"Submitted deep research request {response_id} with {FALLBACK_MODEL}")
            else:
                raise

        # Poll for completion
        result = await self._poll_until_complete(response_id)

        # Extract report and citations
        report = self._extract_report(result)
        citations = self._extract_citations(result)

        return ResearchResponse(content=report, citations=citations)

    async def _submit_request(self, topic: str, model: str) -> str:
        """Submit background research request and return response ID."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": topic,
                    "reasoning": {"summary": "auto"},
                    "background": True,
                    "tools": [{"type": "web_search_preview"}],
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["id"]

    async def _poll_until_complete(self, response_id: str) -> dict:
        """Poll the response endpoint until research is complete."""
        async with httpx.AsyncClient() as client:
            for attempt in range(MAX_POLL_ATTEMPTS):
                response = await client.get(
                    f"{self._base_url}/responses/{response_id}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                status = data.get("status", "")
                logger.debug(f"Poll attempt {attempt + 1}/{MAX_POLL_ATTEMPTS}: status={status}")

                if status == "completed":
                    return data
                elif status == "failed":
                    error_detail = data.get("error", {})
                    error_msg = error_detail.get("message", "") if isinstance(error_detail, dict) else str(error_detail)
                    logger.warning(
                        "Research request %s failed: %s (full status: %s)",
                        response_id, error_msg or "no detail", data.get("status_details", {}),
                    )
                    raise ResearchRequestFailed(
                        f"Research request {response_id} failed: {error_msg or 'no detail provided'}"
                    )

                await asyncio.sleep(POLL_INTERVAL)

            raise TimeoutError(
                f"Research request {response_id} timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s"
            )

    def _extract_report(self, result: dict) -> str:
        """Extract the research report text from the response."""
        outputs = result.get("output", [])
        for item in outputs:
            if item.get("type") == "message":
                content = item.get("content", [])
                for block in content:
                    if block.get("type") == "output_text":
                        return block.get("text", "")
        return ""

    def _extract_citations(self, result: dict) -> list[SearchResult]:
        """Extract citations from url_citation annotations inside output blocks."""
        citations = []
        seen_urls: set[str] = set()
        for item in result.get("output", []):
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        for ann in block.get("annotations", []):
                            if ann.get("type") == "url_citation":
                                url = ann.get("url", "")
                                if url and url not in seen_urls:
                                    seen_urls.add(url)
                                    title = ann.get("title", url)
                                    citations.append(SearchResult(title=title, url=url, snippet=""))
        return citations
