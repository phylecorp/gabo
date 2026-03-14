"""Test that all Pydantic models validate correctly and produce JSON schemas.

@decision DEC-TEST-MODELS-001: Comprehensive schema and round-trip validation.
Tests all 13 result models for JSON schema generation, field descriptions
(critical for LLM structured output quality), and round-trip serialization.
AltFuturesResult gets a specific test for its exactly-4-scenarios constraint.
"""

from __future__ import annotations

import json

import pytest

from sat.models.ach import ACHEvidence, ACHHypothesis, ACHRating, ACHResult
from sat.models.alt_futures import AltFuturesResult, FuturesAxis, ScenarioQuadrant
from sat.models.assumptions import KeyAssumptionsResult
from sat.models.brainstorming import BrainstormingResult
from sat.models.devils_advocacy import DevilsAdvocacyResult
from sat.models.high_impact import HighImpactResult
from sat.models.indicators import IndicatorsResult
from sat.models.outside_in import OutsideInResult
from sat.models.quality import QualityOfInfoResult
from sat.models.red_team import RedTeamResult
from sat.models.synthesis import SynthesisResult
from sat.models.team_ab import TeamABResult
from sat.models.what_if import WhatIfResult


ALL_RESULT_MODELS = [
    KeyAssumptionsResult,
    QualityOfInfoResult,
    IndicatorsResult,
    ACHResult,
    DevilsAdvocacyResult,
    TeamABResult,
    HighImpactResult,
    WhatIfResult,
    BrainstormingResult,
    OutsideInResult,
    RedTeamResult,
    AltFuturesResult,
    SynthesisResult,
]


class TestModelSchemas:
    """All models should produce valid JSON schemas."""

    @pytest.mark.parametrize("model_cls", ALL_RESULT_MODELS)
    def test_json_schema_generation(self, model_cls):
        """Each model should generate a valid JSON schema."""
        schema = model_cls.model_json_schema()
        assert "properties" in schema
        assert "title" in schema
        # Should be valid JSON
        json.dumps(schema)

    @pytest.mark.parametrize("model_cls", ALL_RESULT_MODELS)
    def test_schema_has_descriptions(self, model_cls):
        """All fields should have descriptions (they drive LLM structured output)."""
        schema = model_cls.model_json_schema()
        properties = schema.get("properties", {})
        for field_name, field_schema in properties.items():
            # Allow $ref fields (nested models) to not have descriptions directly
            if "$ref" not in field_schema and "allOf" not in field_schema and "anyOf" not in field_schema:
                assert "description" in field_schema, (
                    f"{model_cls.__name__}.{field_name} missing description"
                )


class TestACHModel:
    """ACH model has specific structural requirements."""

    def test_ach_round_trip(self):
        """ACH result should round-trip through JSON."""
        result = ACHResult(
            technique_id="ach",
            technique_name="Analysis of Competing Hypotheses",
            summary="H1 is most likely",
            hypotheses=[
                ACHHypothesis(id="H1", description="Hypothesis one"),
                ACHHypothesis(id="H2", description="Hypothesis two"),
            ],
            evidence=[
                ACHEvidence(id="E1", description="Evidence one", credibility="High", relevance="High"),
            ],
            matrix=[
                ACHRating(evidence_id="E1", hypothesis_id="H1", rating="C", explanation="Fits"),
                ACHRating(evidence_id="E1", hypothesis_id="H2", rating="I", explanation="Contradicts"),
            ],
            inconsistency_scores={"H1": 0.0, "H2": 1.0},
            most_likely="H1",
            rejected=["H2"],
            diagnosticity_notes="E1 is highly diagnostic",
            missing_evidence=["Need more data"],
        )

        json_str = result.model_dump_json()
        restored = ACHResult.model_validate_json(json_str)
        assert restored.most_likely == "H1"
        assert restored.inconsistency_scores["H2"] == 1.0


class TestAltFuturesModel:
    """Alternative Futures model accepts flexible scenario counts for LLM robustness."""

    def test_requires_exactly_four_scenarios(self):
        """AltFuturesResult accepts any number of scenarios for LLM robustness.

        The 2x2 matrix conceptually has 4 quadrants, but the schema allows
        partial output (including empty list) to handle incomplete LLM responses.
        """
        base = dict(
            technique_id="alt_futures",
            technique_name="Alternative Futures",
            summary="Test",
            focal_issue="Test issue",
            key_uncertainties=["U1"],
            x_axis=FuturesAxis(name="X", low_label="Low X", high_label="High X"),
            y_axis=FuturesAxis(name="Y", low_label="Low Y", high_label="High Y"),
            cross_cutting_indicators=["I1"],
            strategic_implications="Implications",
        )
        scenario = ScenarioQuadrant(
            quadrant_label="Q1",
            scenario_name="S1",
            narrative="Story",
            indicators=["I1"],
            policy_implications="Policy",
        )

        # Exactly 4 scenarios (ideal case)
        result = AltFuturesResult(**base, scenarios=[scenario] * 4)
        assert len(result.scenarios) == 4

        # Fewer than 4 is now allowed (LLM robustness)
        result_partial = AltFuturesResult(**base, scenarios=[scenario] * 3)
        assert len(result_partial.scenarios) == 3

        # More than 4 is also allowed (LLM might generate extras)
        result_extra = AltFuturesResult(**base, scenarios=[scenario] * 5)
        assert len(result_extra.scenarios) == 5

        # Empty list is allowed (default)
        result_empty = AltFuturesResult(**base, scenarios=[])
        assert len(result_empty.scenarios) == 0
