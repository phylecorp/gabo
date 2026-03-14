"""Tests for token estimation and budget calculation.

@decision DEC-TEST-PREPROC-002: Token estimation and budget calculation tests.
@title Measurer test coverage
@status accepted
@rationale Validates character/4 heuristic, provider context windows, budget
calculation, and the needs_reduction threshold check across providers.
"""

from sat.preprocessing.measurer import (
    calculate_budget,
    estimate_tokens,
    get_context_window,
    needs_reduction,
)


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_short_text(self):
        # 20 chars -> 5 tokens
        assert estimate_tokens("12345678901234567890") == 5

    def test_longer_text(self):
        text = "a" * 400
        assert estimate_tokens(text) == 100


class TestGetContextWindow:
    def test_anthropic(self):
        assert get_context_window("anthropic") == 200_000

    def test_openai(self):
        assert get_context_window("openai") == 200_000

    def test_gemini(self):
        assert get_context_window("gemini") == 1_000_000

    def test_unknown_provider(self):
        assert get_context_window("unknown") == 200_000


class TestCalculateBudget:
    def test_default_fraction(self):
        # anthropic: 200_000 * 0.4 = 80_000
        assert calculate_budget("anthropic") == 80_000

    def test_custom_fraction(self):
        assert calculate_budget("anthropic", 0.5) == 100_000

    def test_gemini(self):
        assert calculate_budget("gemini") == 400_000


class TestNeedsReduction:
    def test_small_text_no_reduction(self):
        text = "a" * 1000  # 250 tokens, well under 80K budget
        assert needs_reduction(text, "anthropic") is False

    def test_large_text_needs_reduction(self):
        # Need > 80K tokens = > 320K chars for anthropic default
        text = "a" * 400_000  # 100K tokens
        assert needs_reduction(text, "anthropic") is True

    def test_gemini_higher_budget(self):
        # Gemini budget is 400K tokens, so 100K tokens fits
        text = "a" * 400_000  # 100K tokens
        assert needs_reduction(text, "gemini") is False
