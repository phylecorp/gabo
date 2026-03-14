"""Tests for Gemini deep research provider.

@decision DEC-TEST-RESEARCH-010: Gemini deep research unit tests with HTTP mocks.
@title Gemini Interactions API tests
@status accepted
@rationale Tests the full submit → poll → extract flow by mocking httpx at the HTTP
boundary. This is the correct use of mocks per Sacred Practice #5. Verifies protocol
conformance, polling behavior with flexible ID/status field handling, citation extraction
with fallback chain, error handling, and timeout scenarios.
"""
# @mock-exempt: Mocking external Gemini Interactions API at the service boundary.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sat.research.base import ResearchProvider


class TestGeminiDeepResearch:
    """Test Gemini deep research provider."""

    def test_satisfies_protocol(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            from sat.research.gemini_deep import GeminiDeepResearchProvider

            provider = GeminiDeepResearchProvider()
        assert isinstance(provider, ResearchProvider)

    def test_raises_without_api_key(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="No Gemini API key"),
        ):
            from sat.research.gemini_deep import GeminiDeepResearchProvider

            GeminiDeepResearchProvider()

    async def test_research_calls_api(self):
        """Test successful research flow: submit → poll → extract."""
        # Mock submit response
        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"name": "interactions/int_456"}
        submit_response.raise_for_status = MagicMock()

        # Mock poll response (completed)
        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "name": "interactions/int_456",
            "status": "completed",
            "outputs": [{"text": "Comprehensive Gemini research results"}],
            "sources": [{"url": "https://gemini-source.com", "title": "Gemini Source"}],
        }
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.gemini_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                from sat.research.gemini_deep import GeminiDeepResearchProvider

                provider = GeminiDeepResearchProvider()

            result = await provider.research("test query")

        assert result.content == "Comprehensive Gemini research results"
        assert len(result.citations) == 1
        assert result.citations[0].url == "https://gemini-source.com"
        assert result.citations[0].title == "Gemini Source"

        # Verify store=True was sent in the POST body
        post_call = mock_client.post.call_args
        assert post_call is not None
        post_json = post_call.kwargs.get("json", {})
        assert post_json.get("store") is True

    async def test_handles_uppercase_status(self):
        """Test handling of uppercase COMPLETED status."""
        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"id": "int_upper"}
        submit_response.raise_for_status = MagicMock()

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "id": "int_upper",
            "metadata": {"status": "COMPLETED"},
            "outputs": [{"content": "Results with uppercase status"}],
        }
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.gemini_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                from sat.research.gemini_deep import GeminiDeepResearchProvider

                provider = GeminiDeepResearchProvider()

            result = await provider.research("test query")

        assert result.content == "Results with uppercase status"

    async def test_handles_failure_status(self):
        """Test error handling when research job fails."""
        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"name": "interactions/fail"}
        submit_response.raise_for_status = MagicMock()

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "name": "interactions/fail",
            "status": "failed",
        }
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.gemini_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                from sat.research.gemini_deep import GeminiDeepResearchProvider

                provider = GeminiDeepResearchProvider()

            with pytest.raises(RuntimeError, match="failed"):
                await provider.research("test query")

    async def test_timeout_on_perpetual_progress(self):
        """Test timeout when polling exceeds max attempts."""
        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"name": "interactions/timeout"}
        submit_response.raise_for_status = MagicMock()

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "name": "interactions/timeout",
            "status": "in_progress",
        }
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.gemini_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with (
                patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
                patch("sat.research.gemini_deep.MAX_POLL_ATTEMPTS", 2),
            ):
                from sat.research.gemini_deep import GeminiDeepResearchProvider

                provider = GeminiDeepResearchProvider()

                with pytest.raises(TimeoutError, match="timed out"):
                    await provider.research("test query")

    async def test_citation_fallback_chain(self):
        """Test citation extraction falls back to regex when sources missing."""
        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"name": "interactions/cit"}
        submit_response.raise_for_status = MagicMock()

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "name": "interactions/cit",
            "status": "completed",
            "outputs": [{"text": "Research with URLs: https://example.org and https://test.com"}],
            # No sources field - should fallback to regex
        }
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.gemini_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                from sat.research.gemini_deep import GeminiDeepResearchProvider

                provider = GeminiDeepResearchProvider()

            result = await provider.research("test query")

        # Should extract URLs via regex
        assert len(result.citations) >= 2
        urls = {c.url for c in result.citations}
        assert "https://example.org" in urls
        assert "https://test.com" in urls
