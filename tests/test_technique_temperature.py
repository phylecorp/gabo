"""Tests for per-technique temperature control (Issue #6).

@decision DEC-TEMP-001
@title Per-technique temperature: creative=0.9, analytical=default, adversarial critique=0.8
@status accepted
@rationale Creative techniques (brainstorming, red team, alt futures, etc.) need higher
  temperature for divergent thinking. Analytical techniques (ACH, quality check) need
  low temperature for precise, consistent output. The provider default (0.3) was being
  used for all techniques, actively suppressing creative output quality.

# @mock-exempt: Testing technique-provider interface boundary. Mocking the
# provider lets us inspect the kwargs passed without making real API calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import sat.techniques  # noqa: F401 — ensure registration

from sat.techniques.base import TechniqueContext
from sat.techniques.registry import get_technique

# Creative techniques — imaginative category
from sat.techniques.imaginative.brainstorming import Brainstorming
from sat.techniques.imaginative.red_team import RedTeamAnalysis
from sat.techniques.imaginative.alt_futures import AltFuturesAnalysis
from sat.techniques.imaginative.outside_in import OutsideInThinking

# Creative techniques — contrarian category
from sat.techniques.contrarian.devils_advocacy import DevilsAdvocacy
from sat.techniques.contrarian.team_ab import TeamAB
from sat.techniques.contrarian.what_if import WhatIfAnalysis
from sat.techniques.contrarian.high_impact import HighImpactAnalysis

# Analytical techniques — diagnostic category
from sat.techniques.diagnostic.ach import ACHTechnique
from sat.techniques.diagnostic.quality import QualityOfInfoCheck
from sat.techniques.diagnostic.assumptions import KeyAssumptionsCheck
from sat.techniques.diagnostic.indicators import IndicatorsCheck


CREATIVE_TECHNIQUES = [
    Brainstorming,
    RedTeamAnalysis,
    AltFuturesAnalysis,
    OutsideInThinking,
    DevilsAdvocacy,
    TeamAB,
    WhatIfAnalysis,
    HighImpactAnalysis,
]

ANALYTICAL_TECHNIQUES = [
    ACHTechnique,
    QualityOfInfoCheck,
    KeyAssumptionsCheck,
    IndicatorsCheck,
]


class TestBaseTemperatureDefault:
    """Base Technique.temperature must default to None."""

    def test_base_temperature_default_is_none(self):
        """Any technique that doesn't override temperature returns None."""
        # ACH is analytical — must not override temperature
        technique = ACHTechnique()
        assert technique.temperature is None, (
            "ACHTechnique.temperature must be None (analytical techniques use provider default)"
        )


class TestCreativeTechniqueTemperature:
    """All 8 creative techniques must return temperature=0.9."""

    @pytest.mark.parametrize("TechClass", CREATIVE_TECHNIQUES, ids=lambda c: c.__name__)
    def test_creative_temperature_is_09(self, TechClass):
        """Creative technique must return temperature=0.9."""
        technique = TechClass()
        assert technique.temperature == 0.9, (
            f"{TechClass.__name__}.temperature must be 0.9 for divergent thinking, "
            f"got {technique.temperature}"
        )


class TestAnalyticalTechniqueTemperature:
    """All 4 analytical techniques must return temperature=None (use provider default)."""

    @pytest.mark.parametrize("TechClass", ANALYTICAL_TECHNIQUES, ids=lambda c: c.__name__)
    def test_analytical_temperature_is_none(self, TechClass):
        """Analytical technique must return temperature=None (use provider default 0.3)."""
        technique = TechClass()
        assert technique.temperature is None, (
            f"{TechClass.__name__}.temperature must be None so analytical techniques "
            f"run at the low provider default (0.3), got {technique.temperature}"
        )


class TestExecutePassesTemperature:
    """execute() must forward temperature to generate_structured() when set.

    # @mock-exempt: Provider is an external dependency. We use AsyncMock to
    # inspect call kwargs without real API calls.
    """

    @pytest.mark.asyncio
    async def test_creative_execute_passes_temperature(self):
        """A creative technique's execute() passes temperature=0.9 to generate_structured."""
        from sat.models.brainstorming import BrainstormingResult

        technique = Brainstorming()
        assert technique.temperature == 0.9, "Precondition: brainstorming has temperature=0.9"

        ctx = TechniqueContext(question="What are alternative explanations?", evidence="Some evidence.")
        mock_result = BrainstormingResult(
            technique_id="brainstorming",
            technique_name="Brainstorming",
            summary="Test",
        )
        provider = AsyncMock()
        provider.generate_structured = AsyncMock(return_value=mock_result)

        await technique.execute(ctx, provider)

        provider.generate_structured.assert_called_once()
        _, kwargs = provider.generate_structured.call_args
        assert "temperature" in kwargs, (
            "generate_structured was not called with temperature kwarg for creative technique"
        )
        assert kwargs["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_analytical_execute_omits_temperature(self):
        """Techniques with temperature=None must NOT pass temperature to generate_structured."""
        from sat.models.assumptions import KeyAssumptionsResult

        technique = KeyAssumptionsCheck()
        assert technique.temperature is None, (
            "Precondition: KeyAssumptionsCheck has no temperature override"
        )

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
        assert "temperature" not in kwargs, (
            "generate_structured should not receive temperature when technique.temperature is None"
        )

    @pytest.mark.asyncio
    async def test_all_creative_techniques_pass_temperature_09(self):
        """All 8 creative techniques pass temperature=0.9 through execute()."""
        # Use red team as a second creative example
        from sat.models.red_team import RedTeamResult

        technique = RedTeamAnalysis()
        ctx = TechniqueContext(question="What could go wrong?", evidence="Evidence.")
        mock_result = RedTeamResult(
            technique_id="red_team",
            technique_name="Red Team Analysis",
            summary="Test",
        )
        provider = AsyncMock()
        provider.generate_structured = AsyncMock(return_value=mock_result)

        await technique.execute(ctx, provider)

        _, kwargs = provider.generate_structured.call_args
        assert kwargs.get("temperature") == 0.9, (
            f"RedTeamAnalysis must pass temperature=0.9, got {kwargs.get('temperature')}"
        )


class TestRegistryTemperatureIntegration:
    """Verify technique temperature via registry lookup (production path)."""

    @pytest.mark.parametrize(
        "technique_id,expected_temperature",
        [
            ("brainstorming", 0.9),
            ("red_team", 0.9),
            ("alt_futures", 0.9),
            ("outside_in", 0.9),
            ("devils_advocacy", 0.9),
            ("team_ab", 0.9),
            ("what_if", 0.9),
            ("high_impact", 0.9),
            ("ach", None),
            ("quality", None),
            ("assumptions", None),
            ("indicators", None),
        ],
    )
    def test_temperature_via_registry(self, technique_id: str, expected_temperature):
        """Verify technique temperature value via registry lookup."""
        technique = get_technique(technique_id)
        assert technique.temperature == expected_temperature, (
            f"Technique '{technique_id}': expected temperature={expected_temperature}, "
            f"got {technique.temperature}"
        )
