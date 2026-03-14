"""Async URL fetcher with per-domain rate limiting for source verification.

@decision DEC-VERIFY-003: httpx with asyncio.Semaphore for controlled concurrent fetching.
@title Rate-limited async HTTP fetching using existing httpx dependency
@status accepted
@rationale httpx is already a project dependency. asyncio.Semaphore bounds global
concurrency and a per-domain timestamp dict prevents hammering individual hosts.
One-second inter-request delay per domain is conservative but avoids triggering
bot-detection on news/government sites commonly cited in research outputs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence

import httpx

from sat.models.verification import FetchResult
from sat.research.verification.extractor import extract_text

logger = logging.getLogger(__name__)

_USER_AGENT = "SAT-SourceVerifier/1.0"
_DOMAIN_DELAY = 0.5  # seconds between requests to the same domain


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL for rate-limiting purposes."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    except Exception:
        return url


class _DomainThrottle:
    """Per-domain last-access timestamps with async lock for safe concurrent access."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_access: dict[str, float] = {}

    async def wait(self, domain: str) -> None:
        """Wait until the domain rate-limit delay has elapsed."""
        async with self._lock:
            now = time.monotonic()
            last = self._last_access.get(domain, 0.0)
            wait_time = _DOMAIN_DELAY - (now - last)
            if wait_time > 0:
                self._last_access[domain] = now + wait_time
                delay = wait_time
            else:
                self._last_access[domain] = now
                delay = 0.0
        if delay > 0:
            await asyncio.sleep(delay)


async def _fetch_one(
    source_id: str,
    url: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    throttle: _DomainThrottle,
    max_chars: int = 15000,
) -> tuple[FetchResult, str]:
    """Fetch a single URL and return (FetchResult, extracted_text)."""
    domain = _extract_domain(url)

    async with semaphore:
        await throttle.wait(domain)
        try:
            response = await client.get(url, follow_redirects=True)

            if response.status_code >= 400:
                status = "blocked" if response.status_code in (401, 403, 429) else "failed"
                return (
                    FetchResult(
                        source_id=source_id,
                        url=url,
                        status=status,
                        error=f"HTTP {response.status_code}",
                    ),
                    "",
                )

            content_type = response.headers.get("content-type", "")
            if "html" in content_type or not content_type:
                text = extract_text(response.text, max_chars=max_chars)
            else:
                # Plain text or other text formats — use directly
                text = response.text[:max_chars]

            return (
                FetchResult(
                    source_id=source_id,
                    url=url,
                    status="success",
                    content_length=len(text),
                ),
                text,
            )

        except httpx.TimeoutException as exc:
            logger.debug("Timeout fetching %s: %s", url, exc)
            return (
                FetchResult(source_id=source_id, url=url, status="timeout", error=str(exc)),
                "",
            )
        except httpx.HTTPError as exc:
            logger.debug("HTTP error fetching %s: %s", url, exc)
            return (
                FetchResult(source_id=source_id, url=url, status="failed", error=str(exc)),
                "",
            )
        except Exception as exc:
            logger.debug("Unexpected error fetching %s: %s", url, exc)
            return (
                FetchResult(source_id=source_id, url=url, status="failed", error=str(exc)),
                "",
            )


async def fetch_sources(
    sources: Sequence,
    timeout: float = 15.0,
    concurrency: int = 5,
    max_chars: int = 15000,
) -> dict[str, tuple[FetchResult, str]]:
    """Fetch all source URLs concurrently with per-domain rate limiting.

    Args:
        sources: Sequence of ResearchSource objects (must have .id and .url attributes).
        timeout: Per-request timeout in seconds.
        concurrency: Maximum concurrent requests.
        max_chars: Maximum characters of extracted text per source.

    Returns:
        Dict mapping source_id -> (FetchResult, extracted_text).
        Sources without URLs are omitted from the result.
    """
    # Filter sources that have URLs
    fetchable = [(s.id, s.url) for s in sources if s.url]

    if not fetchable:
        return {}

    semaphore = asyncio.Semaphore(concurrency)
    throttle = _DomainThrottle()

    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    timeout_config = httpx.Timeout(timeout)

    results: dict[str, tuple[FetchResult, str]] = {}

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=timeout_config,
        limits=limits,
        max_redirects=3,
    ) as client:
        tasks = [
            _fetch_one(source_id, url, client, semaphore, throttle, max_chars)
            for source_id, url in fetchable
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for i, outcome in enumerate(outcomes):
        source_id, url = fetchable[i]
        if isinstance(outcome, Exception):
            results[source_id] = (
                FetchResult(
                    source_id=source_id,
                    url=url,
                    status="failed",
                    error=str(outcome),
                ),
                "",
            )
        else:
            fetch_result, text = outcome
            results[source_id] = (fetch_result, text)

    return results
