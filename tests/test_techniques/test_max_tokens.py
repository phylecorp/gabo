"""Tests for per-technique max_tokens token budget override (Bug 3A fix).

@decision DEC-TEST-MAXTOKENS-001: Verify max_tokens property and pass-through.
ACH technique overrides max_tokens to 16384 to avoid silent truncation of the
hypothesis matrix. These tests verify the property value and that execute()
passes max_tokens to generate_structured() when the property is set.

# @mock-exempt: Testing technique-provider interface boundary. Mocking the
# provider lets us inspect the kwargs passed without making real API calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import sat.techniques  # noqa: F401 — ensure registration

from sat.models.ach import ACHResult
from sat.techniques.base import TechniqueContext
from sat.techniques.diagnostic.ach import ACHTechnique
from sat.techniques.registry import get_technique


class TestACHMaxTokensProperty:
    """ACHTechnique.max_tokens must be >= 8192."""

    def test_ach_max_tokens_is_set(self):
        """ACHTechnique must override max_tokens (not None)."""
        technique = ACHTechnique()
        assert technique.max_tokens is not None, "ACHTechnique.max_tokens must not be None"

    def test_ach_max_tokens_value(self):
        """ACHTechnique.max_tokens must be at least 8192."""
        technique = ACHTechnique()
        assert technique.max_tokens >= 8192, (
            f"ACHTechnique.max_tokens={technique.max_tokens} is below the 8192 minimum "
            "needed for a complete hypothesis matrix"
        )

    def test_ach_max_tokens_exact(self):
        """ACHTechnique.max_tokens must equal 16384 per the spec."""
        technique = ACHTechnique()
        assert technique.max_tokens == 16384


class TestBaseTechniqueMaxTokensDefault:
    """Base Technique.max_tokens must default to None."""

    def test_default_is_none(self):
        """Any technique that doesn't override max_tokens returns None."""
        # Use a non-ACH technique — assumptions doesn't override max_tokens
        technique = get_technique("assumptions")
        assert technique.max_tokens is None, (
            "Base Technique.max_tokens default must be None (assumptions should not override it)"
        )


class TestExecutePassesMaxTokens:
    """execute() must forward max_tokens to generate_structured() when set.

    # @mock-exempt: Provider is an external dependency. We use AsyncMock to
    # inspect call kwargs without real API calls.
    """

    @pytest.mark.asyncio
    async def test_ach_execute_passes_max_tokens(self):
        """ACHTechnique.execute() passes max_tokens=16384 to generate_structured."""
        technique = ACHTechnique()
        ctx = TechniqueContext(question="Test question?", evidence="Test evidence.")

        mock_result = ACHResult(
            technique_id="ach",
            technique_name="Analysis of Competing Hypotheses",
            summary="Test",
        )
        provider = AsyncMock()
        provider.generate_structured = AsyncMock(return_value=mock_result)

        await technique.execute(ctx, provider)

        provider.generate_structured.assert_called_once()
        _, kwargs = provider.generate_structured.call_args
        assert "max_tokens" in kwargs, "generate_structured was not called with max_tokens kwarg"
        assert kwargs["max_tokens"] == 16384

    @pytest.mark.asyncio
    async def test_non_ach_execute_omits_max_tokens(self):
        """Techniques with max_tokens=None must NOT pass max_tokens to generate_structured."""
        from sat.models.assumptions import KeyAssumptionsResult

        technique = get_technique("assumptions")
        assert technique.max_tokens is None, "Precondition: assumptions has no max_tokens override"

        ctx = TechniqueContext(question="Test?", evidence="Evidence.")
        mock_result = KeyAssumptionsResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Test",
        )
        provider = AsyncMock()
        provider.generate_structured = AsyncMock(return_value=mock_result)

        await technique.execute(ctx, provider)

        provider.generate_structured.assert_called_once()
        _, kwargs = provider.generate_structured.call_args
        assert "max_tokens" not in kwargs, (
            "generate_structured should not receive max_tokens when technique.max_tokens is None"
        )
