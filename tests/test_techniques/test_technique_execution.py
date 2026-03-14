"""Per-technique execution tests with mock LLM.

Verifies that every registered technique can execute end-to-end
with a mock provider, catching prompt-schema mismatches early.

@decision DEC-TEST-TECHNIQUE-001
@title Per-technique integration tests with minimal models
@status accepted
@rationale Each technique's execute() method must work with minimal valid output
from the LLM. By mocking the provider to return minimal instances (only base
fields + truly required fields), we verify the full pipeline without external
dependencies. This catches schema mismatches, missing defaults, and validation
issues before they hit production. Mock is acceptable here because we're testing
the technique-provider interface, not the LLM itself.

# @mock-exempt: Testing technique-provider interface boundary. The LLM provider
# is an external dependency (network, API keys, cost). Mocking it here lets us
# verify schema robustness and execution flow without external calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sat.models.base import ArtifactResult
from sat.techniques.base import TechniqueContext
from sat.techniques.registry import get_technique

# Import all result models
from sat.models.ach import ACHResult
from sat.models.alt_futures import AltFuturesResult
from sat.models.assumptions import KeyAssumptionsResult
from sat.models.brainstorming import BrainstormingResult
from sat.models.devils_advocacy import DevilsAdvocacyResult
from sat.models.high_impact import HighImpactResult
from sat.models.indicators import IndicatorsResult
from sat.models.outside_in import OutsideInResult
from sat.models.quality import QualityOfInfoResult
from sat.models.red_team import RedTeamResult
from sat.models.team_ab import TeamABResult
from sat.models.what_if import WhatIfResult


def _make_ctx(
    question: str = "Test question?", evidence: str = "Test evidence."
) -> TechniqueContext:
    """Create a minimal technique context for testing."""
    return TechniqueContext(question=question, evidence=evidence, prior_results={})


def _mock_provider(return_value: ArtifactResult) -> AsyncMock:
    """Create a mock provider that returns a specific result."""
    provider = AsyncMock()
    provider.generate_structured = AsyncMock(return_value=return_value)
    return provider


# Minimal valid instances — only base fields + any truly required fields
# These prove the schemas are robust enough for partial LLM output
MINIMAL_RESULTS = {
    "assumptions": KeyAssumptionsResult(
        technique_id="assumptions",
        technique_name="Key Assumptions Check",
        summary="Test summary",
    ),
    "quality": QualityOfInfoResult(
        technique_id="quality",
        technique_name="Quality of Information Check",
        summary="Test summary",
    ),
    "ach": ACHResult(
        technique_id="ach",
        technique_name="Analysis of Competing Hypotheses",
        summary="Test summary",
    ),
    "indicators": IndicatorsResult(
        technique_id="indicators",
        technique_name="Indicators/Signposts of Change",
        summary="Test summary",
        hypothesis_or_scenario="Test scenario",
    ),
    "devils_advocacy": DevilsAdvocacyResult(
        technique_id="devils_advocacy",
        technique_name="Devil's Advocacy",
        summary="Test summary",
    ),
    "team_ab": TeamABResult(
        technique_id="team_ab",
        technique_name="Team A/Team B",
        summary="Test summary",
    ),
    "what_if": WhatIfResult(
        technique_id="what_if",
        technique_name="What If Analysis",
        summary="Test summary",
    ),
    "high_impact": HighImpactResult(
        technique_id="high_impact",
        technique_name="High-Impact/Low-Probability",
        summary="Test summary",
    ),
    "brainstorming": BrainstormingResult(
        technique_id="brainstorming",
        technique_name="Brainstorming",
        summary="Test summary",
    ),
    "red_team": RedTeamResult(
        technique_id="red_team",
        technique_name="Red Team Analysis",
        summary="Test summary",
    ),
    "alt_futures": AltFuturesResult(
        technique_id="alt_futures",
        technique_name="Alternative Futures Analysis",
        summary="Test summary",
    ),
    "outside_in": OutsideInResult(
        technique_id="outside_in",
        technique_name="Outside-In Thinking",
        summary="Test summary",
    ),
}


@pytest.mark.parametrize("technique_id", list(MINIMAL_RESULTS.keys()))
async def test_technique_executes(technique_id: str):
    """Each technique should execute and return its result type."""
    import sat.techniques  # noqa: F401 — ensure registration

    technique = get_technique(technique_id)
    ctx = _make_ctx()
    mock_result = MINIMAL_RESULTS[technique_id]
    provider = _mock_provider(mock_result)

    result = await technique.execute(ctx, provider)
    assert isinstance(result, type(mock_result))
    assert result.technique_id == technique_id


@pytest.mark.parametrize("technique_id", list(MINIMAL_RESULTS.keys()))
def test_minimal_model_validates(technique_id: str):
    """Each model should validate with only base fields + required fields."""
    result = MINIMAL_RESULTS[technique_id]
    # Round-trip through JSON to verify serialization
    json_str = result.model_dump_json()
    restored = type(result).model_validate_json(json_str)
    assert restored.technique_id == technique_id


def test_all_techniques_have_tests():
    """Ensure we have test coverage for all registered techniques."""
    import sat.techniques  # noqa: F401 — ensure registration
    from sat.techniques.registry import list_technique_ids

    registered_ids = set(list_technique_ids())
    tested_ids = set(MINIMAL_RESULTS.keys())

    # Synthesis is a special technique that runs after all others
    registered_ids.discard("synthesis")

    missing = registered_ids - tested_ids
    extra = tested_ids - registered_ids

    assert not missing, f"Missing tests for techniques: {missing}"
    assert not extra, f"Tests for non-existent techniques: {extra}"
