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

@decision DEC-RESEARCH-012
@title Per-provider single retry on rate-limit failures during polling
@status accepted
@rationale OpenAI's deep research server returns status='failed' with a rate-limit
error when TPM is exhausted mid-processing (e.g., "Rate limit reached... try again
in 930ms"). The rate-limit window is sub-second to a few seconds, so a single
retry after a brief delay recovers most failures without a full multi_runner retry
cycle (which only fires when ALL providers fail). Implementation:
- research() wraps the submit+poll sequence in a try/except for ResearchRequestFailed
- If the error message contains "rate limit" (case-insensitive), parse the retry-after
  delay from the message ("try again in Xms"), add a 0.5s buffer, cap at 10s, or
  default to 2s if unparseable
- Resubmit once (new response ID) and poll again; second failure propagates
- Only one retry; no loop; non-rate-limit failures propagate immediately
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

import httpx

from sat.config import resolve_research_model
from sat.events import EventBus, NullBus, ProviderPolling
from sat.research.base import ResearchResponse, SearchResult

logger = logging.getLogger(__name__)

# Rate-limit retry constants (DEC-RESEARCH-012)
_RATE_LIMIT_RETRY_BUFFER_S = 0.5   # seconds added to parsed delay as safety margin
_RATE_LIMIT_RETRY_MAX_S = 10.0     # cap: never wait more than 10 seconds
_RATE_LIMIT_RETRY_DEFAULT_S = 2.0  # fallback when ms value cannot be parsed


def _parse_rate_limit_delay(error_message: str) -> float:
    """Parse the retry delay from an OpenAI rate-limit error message.

    OpenAI rate-limit messages include a suggestion like "Please try again in 930ms."
    This function extracts the millisecond value, converts to seconds, adds a small
    buffer for safety, and caps the result. Returns a default when parsing fails.

    Args:
        error_message: The error message from OpenAI's response (may be empty).

    Returns:
        Delay in seconds to wait before retrying.

    Examples:
        "Please try again in 930ms."  → 0.930 + 0.5 = 1.430s
        "Please try again in 60000ms." → min(60.5, 10.0) = 10.0s
        "Please try again later."      → 2.0s (default)
    """
    match = re.search(r"try again in (\d+)ms", error_message, re.IGNORECASE)
    if not match:
        return _RATE_LIMIT_RETRY_DEFAULT_S
    ms_value = int(match.group(1))
    delay = ms_value / 1000.0 + _RATE_LIMIT_RETRY_BUFFER_S
    return min(delay, _RATE_LIMIT_RETRY_MAX_S)


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


# Throttle: emit ProviderPolling every Nth attempt to avoid log flooding.
# At 10s poll interval, every 4th attempt = ~every 40s (roughly once per minute).
_POLL_EMIT_EVERY_N = 4


class OpenAIDeepResearchProvider:
    """Research provider using OpenAI's deep research models."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        events: EventBus | None = None,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("No OpenAI API key. Set OPENAI_API_KEY or pass api_key.")
        self._api_key = key
        self._base_url = "https://api.openai.com/v1"
        # Resolution: explicit param > config file > OPENAI_RESEARCH_MODEL env var > default
        self._primary_model = model or resolve_research_model("openai")
        # EventBus for liveness events (DEC-RESEARCH-015). NullBus when not provided.
        self._events: EventBus = events if events is not None else NullBus

    async def research(
        self,
        query: str,
        context: str | None = None,
        max_sources: int = 10,
    ) -> ResearchResponse:
        """Execute deep research via OpenAI Responses API.

        Includes a single rate-limit retry (DEC-RESEARCH-012): if the initial
        submit+poll cycle fails with a rate-limit error, waits the suggested delay
        and resubmits once. A second failure on the retry propagates normally.
        """
        topic = query
        if context:
            topic = f"{context}\n\n{query}"

        # Submit + poll with one rate-limit retry (DEC-RESEARCH-012).
        try:
            result = await self._submit_and_poll(topic)
        except ResearchRequestFailed as exc:
            error_msg = str(exc)
            if "rate limit" not in error_msg.lower():
                raise  # Non-rate-limit failure: propagate immediately without retry
            delay = _parse_rate_limit_delay(error_msg)
            logger.warning(
                "Rate-limit failure on first attempt; retrying in %.2fs. Error: %s",
                delay, error_msg,
            )
            await asyncio.sleep(delay)
            # Single retry — second failure propagates as-is
            result = await self._submit_and_poll(topic)

        # Extract report and citations
        report = self._extract_report(result)
        citations = self._extract_citations(result)

        return ResearchResponse(content=report, citations=citations)

    async def _submit_and_poll(self, topic: str) -> dict:
        """Submit a new request and poll until complete.

        Handles 404 fallback: tries the primary model first, falls back to
        FALLBACK_MODEL on 404 (same logic as the original research() method).
        Extracted so the retry path in research() can resubmit cleanly.
        """
        # Try primary model first, fallback to o4-mini on 404
        try:
            response_id = await self._submit_request(topic, self._primary_model)
            logger.info(
                "Submitted deep research request %s with %s", response_id, self._primary_model
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(
                    "%s not available, falling back to %s",
                    self._primary_model, FALLBACK_MODEL,
                )
                response_id = await self._submit_request(topic, FALLBACK_MODEL)
                logger.info(
                    "Submitted deep research request %s with %s", response_id, FALLBACK_MODEL
                )
            else:
                raise

        return await self._poll_until_complete(response_id)

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
        """Poll the response endpoint until research is complete.

        Emits ProviderPolling on the first attempt and every _POLL_EMIT_EVERY_N
        attempts thereafter (DEC-RESEARCH-015). This throttling keeps the event log
        readable without flooding it — at 10s intervals, events arrive ~once per minute.
        """
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

                # Emit liveness event on first attempt and every Nth thereafter.
                if attempt % _POLL_EMIT_EVERY_N == 0:
                    await self._events.emit(ProviderPolling(
                        name="openai_deep",
                        attempt=attempt + 1,
                        max_attempts=MAX_POLL_ATTEMPTS,
                        status=status,
                    ))

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
