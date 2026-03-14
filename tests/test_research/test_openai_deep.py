"""Tests for OpenAI deep research provider.

@decision DEC-TEST-RESEARCH-009: OpenAI deep research unit tests with HTTP mocks.
@title OpenAI background research API tests
@status accepted
@rationale Tests the full submit → poll → extract flow by mocking httpx at the HTTP
boundary. This is the correct use of mocks per Sacred Practice #5, as we're mocking
external service boundaries. Verifies protocol conformance, polling behavior, fallback
model selection, error handling, and timeout scenarios.
"""
# @mock-exempt: Mocking external OpenAI Responses API at the service boundary.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sat.research.base import ResearchProvider


class TestOpenAIDeepResearch:
    """Test OpenAI deep research provider."""

    def test_satisfies_protocol(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from sat.research.openai_deep import OpenAIDeepResearchProvider

            provider = OpenAIDeepResearchProvider()
        assert isinstance(provider, ResearchProvider)

    def test_raises_without_api_key(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="No OpenAI API key"),
        ):
            from sat.research.openai_deep import OpenAIDeepResearchProvider

            OpenAIDeepResearchProvider()

    async def test_research_calls_api(self):
        """Test successful research flow: submit → poll → extract."""
        # Mock submit response
        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"id": "resp_123"}
        submit_response.raise_for_status = MagicMock()

        # Mock poll response (completed)
        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "id": "resp_123",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Deep research findings about AI",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com",
                                    "title": "Example Source",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.openai_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from sat.research.openai_deep import OpenAIDeepResearchProvider

                provider = OpenAIDeepResearchProvider()

            result = await provider.research("test query")

        assert result.content == "Deep research findings about AI"
        assert len(result.citations) == 1
        assert result.citations[0].url == "https://example.com"
        assert result.citations[0].title == "Example Source"

    async def test_fallback_on_404(self):
        """Test fallback to o4-mini when primary model returns 404."""
        # Mock 404 on primary model
        submit_404 = MagicMock()
        submit_404.status_code = 404
        # Create proper HTTPStatusError
        mock_request = MagicMock(spec=httpx.Request)
        http_error = httpx.HTTPStatusError(
            "404 Not Found", request=mock_request, response=submit_404
        )
        submit_404.raise_for_status = MagicMock(side_effect=http_error)

        # Mock success on fallback model
        submit_success = MagicMock()
        submit_success.status_code = 200
        submit_success.json.return_value = {"id": "resp_fallback"}
        submit_success.raise_for_status = MagicMock()

        # Mock poll response
        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "id": "resp_fallback",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Fallback findings"}],
                }
            ],
        }
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.openai_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            # First call fails, second succeeds
            mock_client.post = AsyncMock(side_effect=[submit_404, submit_success])
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from sat.research.openai_deep import OpenAIDeepResearchProvider

                provider = OpenAIDeepResearchProvider()

            result = await provider.research("test query")

        assert result.content == "Fallback findings"
        assert mock_client.post.call_count == 2

    async def test_handles_failure_status(self):
        # @mock-exempt: Mocking external OpenAI Responses API at the service boundary.
        """Test that status='failed' raises ResearchRequestFailed (a RuntimeError subclass)."""
        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"id": "resp_fail"}
        submit_response.raise_for_status = MagicMock()

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {"id": "resp_fail", "status": "failed"}
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.openai_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from sat.research.openai_deep import OpenAIDeepResearchProvider, ResearchRequestFailed

                provider = OpenAIDeepResearchProvider()

            with pytest.raises(ResearchRequestFailed, match="failed"):
                await provider.research("test query")

    async def test_failure_status_includes_error_detail(self):
        # @mock-exempt: Mocking external OpenAI Responses API at the service boundary.
        """Test that error detail from API response is included in the exception message."""
        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"id": "resp_fail_detail"}
        submit_response.raise_for_status = MagicMock()

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "id": "resp_fail_detail",
            "status": "failed",
            "error": {"message": "Internal server error during research"},
            "status_details": {"reason": "server_error"},
        }
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.openai_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from sat.research.openai_deep import OpenAIDeepResearchProvider, ResearchRequestFailed

                provider = OpenAIDeepResearchProvider()

            with pytest.raises(ResearchRequestFailed, match="Internal server error during research"):
                await provider.research("test query")

    async def test_timeout_on_perpetual_progress(self):
        """Test timeout when polling exceeds max attempts."""
        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"id": "resp_timeout"}
        submit_response.raise_for_status = MagicMock()

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {"id": "resp_timeout", "status": "in_progress"}
        poll_response.raise_for_status = MagicMock()

        with patch("sat.research.openai_deep.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
                patch("sat.research.openai_deep.MAX_POLL_ATTEMPTS", 2),
            ):
                from sat.research.openai_deep import OpenAIDeepResearchProvider

                provider = OpenAIDeepResearchProvider()

                with pytest.raises(TimeoutError, match="timed out"):
                    await provider.research("test query")
