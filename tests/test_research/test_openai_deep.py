"""Tests for OpenAI deep research provider.

@decision DEC-TEST-RESEARCH-009: OpenAI deep research unit tests with HTTP mocks.
@title OpenAI background research API tests
@status accepted
@rationale Tests the full submit → poll → extract flow by mocking httpx at the HTTP
boundary. This is the correct use of mocks per Sacred Practice #5, as we're mocking
external service boundaries. Verifies protocol conformance, polling behavior, fallback
model selection, error handling, timeout scenarios, and rate limit retry logic
(DEC-RESEARCH-012: single retry with parsed delay on rate-limit failures).
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

    # -----------------------------------------------------------------------
    # Rate limit retry tests (DEC-RESEARCH-012)
    # -----------------------------------------------------------------------

    async def test_rate_limit_failure_retries_once_and_succeeds(self):
        """Rate-limit failure on first attempt triggers one retry that succeeds.

        Simulates the production scenario: OpenAI returns status='failed' with a
        rate-limit message on the first poll, then succeeds on the retry submit+poll.
        The retry delay is patched to zero so the test runs instantly.
        """
        # @mock-exempt: Mocking external OpenAI Responses API at the service boundary.

        rate_limit_msg = (
            "Rate limit reached for o3-deep-research-2025-06-26 on tokens per minute. "
            "Please try again in 930ms."
        )

        # First submit → response ID #1
        submit_first = MagicMock()
        submit_first.status_code = 200
        submit_first.json.return_value = {"id": "resp_ratelimit_1"}
        submit_first.raise_for_status = MagicMock()

        # First poll → failed with rate limit
        poll_failed = MagicMock()
        poll_failed.status_code = 200
        poll_failed.json.return_value = {
            "id": "resp_ratelimit_1",
            "status": "failed",
            "error": {"message": rate_limit_msg},
        }
        poll_failed.raise_for_status = MagicMock()

        # Retry submit → response ID #2
        submit_retry = MagicMock()
        submit_retry.status_code = 200
        submit_retry.json.return_value = {"id": "resp_ratelimit_2"}
        submit_retry.raise_for_status = MagicMock()

        # Retry poll → completed
        poll_ok = MagicMock()
        poll_ok.status_code = 200
        poll_ok.json.return_value = {
            "id": "resp_ratelimit_2",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Retry succeeded content"}],
                }
            ],
        }
        poll_ok.raise_for_status = MagicMock()

        with (
            patch("sat.research.openai_deep.httpx.AsyncClient") as mock_client_cls,
            patch("sat.research.openai_deep.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[submit_first, submit_retry])
            mock_client.get = AsyncMock(side_effect=[poll_failed, poll_ok])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from sat.research.openai_deep import OpenAIDeepResearchProvider

                provider = OpenAIDeepResearchProvider()

            result = await provider.research("test query")

        assert result.content == "Retry succeeded content"
        # Two submit calls: original + retry
        assert mock_client.post.call_count == 2
        # Sleep was called once for the retry delay
        mock_sleep.assert_called_once()
        # Parsed delay from "930ms" = 0.930s + 0.5s buffer = 1.430s (capped at 10s)
        sleep_duration = mock_sleep.call_args[0][0]
        assert 1.0 < sleep_duration < 10.0, f"Expected delay ~1.43s, got {sleep_duration}"

    async def test_rate_limit_retry_with_unparseable_delay_uses_default(self):
        """Rate-limit message with no parseable delay falls back to 2s default."""
        # @mock-exempt: Mocking external OpenAI Responses API at the service boundary.

        # Rate limit message without a parseable "Xms" pattern
        rate_limit_msg = "Rate limit reached for model. Please try again later."

        submit_first = MagicMock()
        submit_first.status_code = 200
        submit_first.json.return_value = {"id": "resp_noparse_1"}
        submit_first.raise_for_status = MagicMock()

        poll_failed = MagicMock()
        poll_failed.status_code = 200
        poll_failed.json.return_value = {
            "id": "resp_noparse_1",
            "status": "failed",
            "error": {"message": rate_limit_msg},
        }
        poll_failed.raise_for_status = MagicMock()

        submit_retry = MagicMock()
        submit_retry.status_code = 200
        submit_retry.json.return_value = {"id": "resp_noparse_2"}
        submit_retry.raise_for_status = MagicMock()

        poll_ok = MagicMock()
        poll_ok.status_code = 200
        poll_ok.json.return_value = {
            "id": "resp_noparse_2",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Default delay retry content"}],
                }
            ],
        }
        poll_ok.raise_for_status = MagicMock()

        with (
            patch("sat.research.openai_deep.httpx.AsyncClient") as mock_client_cls,
            patch("sat.research.openai_deep.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[submit_first, submit_retry])
            mock_client.get = AsyncMock(side_effect=[poll_failed, poll_ok])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from sat.research.openai_deep import OpenAIDeepResearchProvider

                provider = OpenAIDeepResearchProvider()

            result = await provider.research("test query")

        assert result.content == "Default delay retry content"
        mock_sleep.assert_called_once_with(2.0)

    async def test_rate_limit_retry_second_failure_propagates(self):
        """If the retry also fails with rate limit, the error propagates (no second retry)."""
        # @mock-exempt: Mocking external OpenAI Responses API at the service boundary.

        rate_limit_msg = "Rate limit reached. Please try again in 500ms."

        def make_submit(resp_id):
            m = MagicMock()
            m.status_code = 200
            m.json.return_value = {"id": resp_id}
            m.raise_for_status = MagicMock()
            return m

        def make_poll_failed(resp_id, msg):
            m = MagicMock()
            m.status_code = 200
            m.json.return_value = {
                "id": resp_id,
                "status": "failed",
                "error": {"message": msg},
            }
            m.raise_for_status = MagicMock()
            return m

        with (
            patch("sat.research.openai_deep.httpx.AsyncClient") as mock_client_cls,
            patch("sat.research.openai_deep.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=[make_submit("resp_fail_1"), make_submit("resp_fail_2")]
            )
            mock_client.get = AsyncMock(
                side_effect=[
                    make_poll_failed("resp_fail_1", rate_limit_msg),
                    make_poll_failed("resp_fail_2", rate_limit_msg),
                ]
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from sat.research.openai_deep import OpenAIDeepResearchProvider, ResearchRequestFailed

                provider = OpenAIDeepResearchProvider()

            with pytest.raises(ResearchRequestFailed, match="(?i)rate limit"):
                await provider.research("test query")

        # Exactly 2 submit calls (original + one retry, no third attempt)
        assert mock_client.post.call_count == 2

    async def test_non_rate_limit_failure_does_not_retry(self):
        """A failed status with a non-rate-limit error is raised immediately without retry."""
        # @mock-exempt: Mocking external OpenAI Responses API at the service boundary.

        submit_response = MagicMock()
        submit_response.status_code = 200
        submit_response.json.return_value = {"id": "resp_server_err"}
        submit_response.raise_for_status = MagicMock()

        poll_response = MagicMock()
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "id": "resp_server_err",
            "status": "failed",
            "error": {"message": "Internal server error during research"},
        }
        poll_response.raise_for_status = MagicMock()

        with (
            patch("sat.research.openai_deep.httpx.AsyncClient") as mock_client_cls,
            patch("sat.research.openai_deep.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_response)
            mock_client.get = AsyncMock(return_value=poll_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from sat.research.openai_deep import OpenAIDeepResearchProvider, ResearchRequestFailed

                provider = OpenAIDeepResearchProvider()

            with pytest.raises(ResearchRequestFailed, match="Internal server error"):
                await provider.research("test query")

        # Only one submit — no retry
        assert mock_client.post.call_count == 1
        # Sleep never called — no retry delay
        mock_sleep.assert_not_called()


class TestParseRetryDelay:
    """Unit tests for the _parse_rate_limit_delay helper."""

    def test_parses_milliseconds_from_message(self):
        from sat.research.openai_deep import _parse_rate_limit_delay

        msg = "Rate limit reached. Please try again in 930ms."
        delay = _parse_rate_limit_delay(msg)
        # 930ms = 0.930s + 0.5s buffer = 1.430s
        assert abs(delay - 1.430) < 0.001

    def test_parses_large_millisecond_value_caps_at_max(self):
        from sat.research.openai_deep import _parse_rate_limit_delay

        # 60000ms = 60s, but max cap is 10s
        msg = "Rate limit reached. Please try again in 60000ms."
        delay = _parse_rate_limit_delay(msg)
        assert delay == 10.0

    def test_returns_default_when_no_ms_value(self):
        from sat.research.openai_deep import _parse_rate_limit_delay

        msg = "Rate limit reached. Please try again later."
        delay = _parse_rate_limit_delay(msg)
        assert delay == 2.0

    def test_returns_default_for_empty_message(self):
        from sat.research.openai_deep import _parse_rate_limit_delay

        delay = _parse_rate_limit_delay("")
        assert delay == 2.0

    def test_buffer_added_to_parsed_delay(self):
        from sat.research.openai_deep import _parse_rate_limit_delay

        # 100ms + 0.5s buffer = 0.600s
        msg = "Please try again in 100ms."
        delay = _parse_rate_limit_delay(msg)
        assert abs(delay - 0.600) < 0.001
