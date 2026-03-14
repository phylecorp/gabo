"""Tests for individual research backends.

@decision DEC-TEST-RESEARCH-004: Backend tests at external service boundary.
@title Research backend unit tests with HTTP mocks
@status accepted
@rationale Each research backend makes external HTTP API calls (Perplexity API,
Brave Search API). These tests mock the HTTP boundary — the only place mocking
is appropriate per Sacred Practice #5. LLM backend uses an in-memory test double.
"""
# @mock-exempt: Mocking external HTTP APIs (Perplexity, Brave Search) at the
# service boundary. This is the correct use of mocks per project conventions.

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sat.providers.base import LLMResult, LLMUsage
from sat.research.base import ResearchProvider


class TestPerplexityBackend:
    """Test Perplexity research provider."""

    def test_satisfies_protocol(self):
        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            from sat.research.perplexity import PerplexityProvider

            provider = PerplexityProvider()
        assert isinstance(provider, ResearchProvider)

    def test_raises_without_api_key(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="No Perplexity API key"),
        ):
            from sat.research.perplexity import PerplexityProvider

            PerplexityProvider()

    async def test_research_calls_api(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Research findings about AI"
        mock_response.citations = None

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            from sat.research.perplexity import PerplexityProvider

            provider = PerplexityProvider()
        provider._client = mock_client

        result = await provider.research("test query")
        assert result.content == "Research findings about AI"
        mock_client.chat.completions.create.assert_called_once()


class TestBraveBackend:
    """Test Brave Search research provider."""

    def test_satisfies_protocol(self):
        with patch.dict("os.environ", {"BRAVE_API_KEY": "test-key"}):
            from sat.research.brave import BraveProvider

            provider = BraveProvider()
        assert isinstance(provider, ResearchProvider)

    def test_raises_without_api_key(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="No Brave API key"),
        ):
            from sat.research.brave import BraveProvider

            BraveProvider()

    async def test_research_calls_api(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://example.com",
                        "description": "A test result",
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("sat.research.brave.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with patch.dict("os.environ", {"BRAVE_API_KEY": "test-key"}):
                from sat.research.brave import BraveProvider

                provider = BraveProvider()

            result = await provider.research("test query")

        assert len(result.citations) == 1
        assert result.citations[0].title == "Test Result"
        assert "Test Result" in result.content


class TestLLMBackend:
    """Test LLM fallback research provider."""

    def test_satisfies_protocol(self):
        from tests.helpers import MockProvider

        from sat.research.llm_search import LLMResearchProvider

        provider = LLMResearchProvider(MockProvider(text_response="research text"))
        assert isinstance(provider, ResearchProvider)

    async def test_research_uses_llm(self):
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=LLMResult(
                text="LLM research findings",
                usage=LLMUsage(input_tokens=100, output_tokens=50),
            )
        )

        from sat.research.llm_search import LLMResearchProvider

        provider = LLMResearchProvider(mock_llm)
        result = await provider.research("test query")

        assert result.content == "LLM research findings"
        assert result.citations == []
        mock_llm.generate.assert_called_once()
