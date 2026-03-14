"""Tests for research provider registry.

@decision DEC-TEST-RESEARCH-002: Validate auto-selection priority and fallback behavior.
@title Research registry unit tests
@status accepted
@rationale Confirms the registry correctly selects providers based on available API keys
following the priority Perplexity > Brave > LLM, and raises appropriate errors when
no provider is available.
"""
# @mock-exempt: Registry tests must mock env vars and avoid real API connections.
# The mock_provider fixture is an in-memory test double from conftest.py, not a mock.

from __future__ import annotations

from unittest.mock import patch

import pytest

from sat.research.registry import create_research_provider


class TestResearchRegistry:
    """Test research provider creation and auto-selection."""

    def test_create_perplexity_provider(self):
        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            provider = create_research_provider("perplexity")
        assert type(provider).__name__ == "PerplexityProvider"

    def test_create_brave_provider(self):
        with patch.dict("os.environ", {"BRAVE_API_KEY": "test-key"}):
            provider = create_research_provider("brave")
        assert type(provider).__name__ == "BraveProvider"

    def test_create_openai_deep_provider(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = create_research_provider("openai_deep")
        assert type(provider).__name__ == "OpenAIDeepResearchProvider"

    def test_create_gemini_deep_provider(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            provider = create_research_provider("gemini_deep")
        assert type(provider).__name__ == "GeminiDeepResearchProvider"

    def test_create_llm_provider(self, mock_provider):
        llm = mock_provider()
        provider = create_research_provider("llm", llm_provider=llm)
        assert type(provider).__name__ == "LLMResearchProvider"

    def test_create_llm_provider_requires_llm(self):
        with pytest.raises(ValueError, match="LLM research requires"):
            create_research_provider("llm")

    def test_auto_selects_perplexity_first(self):
        with patch.dict(
            "os.environ",
            {"PERPLEXITY_API_KEY": "pkey", "BRAVE_API_KEY": "bkey"},
        ):
            provider = create_research_provider("auto")
        assert type(provider).__name__ == "PerplexityProvider"

    def test_auto_selects_brave_without_perplexity(self):
        with patch.dict(
            "os.environ",
            {"BRAVE_API_KEY": "bkey"},
            clear=False,
        ):
            import os

            os.environ.pop("PERPLEXITY_API_KEY", None)
            provider = create_research_provider("auto")
        assert type(provider).__name__ == "BraveProvider"

    def test_auto_selects_llm_fallback(self, mock_provider):
        with patch.dict("os.environ", {}, clear=True):
            llm = mock_provider()
            provider = create_research_provider("auto", llm_provider=llm)
        assert type(provider).__name__ == "LLMResearchProvider"

    def test_auto_raises_when_nothing_available(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="No research provider available"),
        ):
            create_research_provider("auto")

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown research provider"):
            create_research_provider("nonexistent")
