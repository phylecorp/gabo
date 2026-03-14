"""Tests for async URL fetching.

Uses unittest.mock to stub httpx — fetcher is tested with controlled HTTP
responses without making real network calls.

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary; mocking it
# avoids real network calls while testing fetch logic, error handling, and
# concurrency control in isolation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from sat.research.verification.fetcher import fetch_sources


def _make_source(id: str, url: str | None = None):
    """Create a minimal mock ResearchSource."""
    src = MagicMock()
    src.id = id
    src.url = url
    return src


class TestFetchSources:
    async def test_fetches_successful_url(self):
        source = _make_source("S1", "https://example.com/article")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<p>Article content here.</p>"

        with patch("sat.research.verification.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            results = await fetch_sources([source], timeout=5.0, concurrency=1)

        assert "S1" in results
        fetch_result, text = results["S1"]
        assert fetch_result.status == "success"
        assert fetch_result.source_id == "S1"
        assert "Article content here" in text

    async def test_handles_timeout(self):
        source = _make_source("S1", "https://slow.example.com/")

        with patch("sat.research.verification.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            mock_client_cls.return_value = mock_client

            results = await fetch_sources([source], timeout=5.0, concurrency=1)

        assert "S1" in results
        fetch_result, text = results["S1"]
        assert fetch_result.status == "timeout"
        assert text == ""

    async def test_handles_404(self):
        source = _make_source("S1", "https://example.com/not-found")
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {}

        with patch("sat.research.verification.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            results = await fetch_sources([source], timeout=5.0, concurrency=1)

        assert "S1" in results
        fetch_result, text = results["S1"]
        assert fetch_result.status == "failed"
        assert "404" in (fetch_result.error or "")

    async def test_handles_403_blocked(self):
        source = _make_source("S1", "https://example.com/blocked")
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {}

        with patch("sat.research.verification.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            results = await fetch_sources([source], timeout=5.0, concurrency=1)

        assert "S1" in results
        fetch_result, _ = results["S1"]
        assert fetch_result.status == "blocked"

    async def test_skips_sources_without_url(self):
        source_with_url = _make_source("S1", "https://example.com/")
        source_no_url = _make_source("S2", None)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<p>Content</p>"

        with patch("sat.research.verification.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            results = await fetch_sources(
                [source_with_url, source_no_url], timeout=5.0, concurrency=2
            )

        # S2 (no URL) should not appear in results
        assert "S1" in results
        assert "S2" not in results

    async def test_respects_concurrency_limit(self):
        """Verify that only `concurrency` requests run simultaneously."""
        sources = [_make_source(f"S{i}", f"https://example.com/{i}") for i in range(10)]

        active_count = 0
        max_active = 0

        async def slow_get(url, **kwargs):
            nonlocal active_count, max_active
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.01)
            active_count -= 1
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/plain"}
            mock_response.text = "content"
            return mock_response

        with patch("sat.research.verification.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = slow_get
            mock_client_cls.return_value = mock_client

            await fetch_sources(sources, timeout=5.0, concurrency=3)

        assert max_active <= 3

    async def test_returns_empty_dict_for_no_sources(self):
        results = await fetch_sources([], timeout=5.0, concurrency=5)
        assert results == {}
