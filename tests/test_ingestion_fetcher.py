"""Tests for the ingestion URL fetcher.

@decision DEC-INGEST-003: URL fetching via httpx + Docling.
@title Tests for fetch_and_parse — HTTP success, 404, and timeout paths
@status accepted
@rationale Verifies that HTML content is fetched and wrapped as a ParsedDocument,
that HTTP errors and timeouts produce a ParsedDocument with a warning rather than
raising, and that the source_name is set to the original URL.

All patches in this module target external service boundaries:
- httpx.AsyncClient: external HTTP service — real network calls must not occur in tests
- sat.ingestion.fetcher.httpx.AsyncClient: same boundary, patch site

URLs use public numeric IP literals (1.1.1.1) to bypass the SSRF DNS lookup —
tests exercise HTTP parsing behavior, not DNS resolution.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch  # @mock-exempt: httpx.AsyncClient is an external HTTP service boundary

import httpx

from sat.ingestion.fetcher import fetch_and_parse


class TestFetchAndParse:
    async def test_fetch_html_success(self):
        """Successful HTML fetch returns a ParsedDocument with the URL as source_name.

        Uses numeric public IP (1.1.1.1) so SSRF validation passes without DNS.
        """
        html_bytes = b"<html><body><p>Hello world</p></body></html>"
        mock_response = MagicMock()  # @mock-exempt: represents external HTTP response object
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.content = html_bytes
        mock_response.raise_for_status = MagicMock()  # @mock-exempt: external HTTP boundary

        mock_client = AsyncMock()  # @mock-exempt: external HTTP service boundary
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)  # @mock-exempt: external HTTP call

        with patch("sat.ingestion.fetcher.httpx.AsyncClient", return_value=mock_client):  # @mock-exempt: external HTTP service
            doc = await fetch_and_parse("https://1.1.1.1/page")

        assert doc.source_name == "https://1.1.1.1/page"
        assert len(doc.source_id) == 8
        # No error warnings
        assert not any("HTTP" in w or "Timeout" in w or "Failed" in w for w in doc.parse_warnings)

    async def test_fetch_404_returns_warning(self):
        """HTTP 404 produces a ParsedDocument with an empty markdown and a warning.

        Uses numeric public IP (1.1.1.1) so SSRF validation passes without DNS.
        """
        mock_response = MagicMock()  # @mock-exempt: external HTTP response object
        mock_response.status_code = 404
        mock_response.raise_for_status = MagicMock(  # @mock-exempt: external HTTP boundary
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)
        )
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = b""

        mock_client = AsyncMock()  # @mock-exempt: external HTTP service boundary
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)  # @mock-exempt: external HTTP call

        with patch("sat.ingestion.fetcher.httpx.AsyncClient", return_value=mock_client):  # @mock-exempt: external HTTP service
            doc = await fetch_and_parse("https://1.1.1.1/missing")

        assert doc.markdown == ""
        assert any("404" in w for w in doc.parse_warnings)

    async def test_fetch_timeout_returns_warning(self):
        """Network timeout produces a ParsedDocument with an empty markdown and a warning.

        Uses numeric public IP (1.1.1.1) so SSRF validation passes without DNS.
        This test exercises timeout handling, not DNS resolution.
        """
        mock_client = AsyncMock()  # @mock-exempt: external HTTP service boundary
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))  # @mock-exempt: external HTTP call

        with patch("sat.ingestion.fetcher.httpx.AsyncClient", return_value=mock_client):  # @mock-exempt: external HTTP service
            doc = await fetch_and_parse("https://1.1.1.1/", timeout=1.0)

        assert doc.markdown == ""
        assert any("Timeout" in w or "timeout" in w for w in doc.parse_warnings)
