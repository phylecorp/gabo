"""Tests for _TECHNIQUE_KEY_FIELDS registry in sat.prompts.base.

@decision DEC-TEST-REGISTRY-001: Verify registry field names match actual Pydantic models.
The _TECHNIQUE_KEY_FIELDS registry maps technique IDs to field names that are
extracted for prior-results formatting. If field names drift from the actual models,
extraction silently produces empty output (the field.get() returns None). This test
locks the registry fields against the actual model schema.

Bug covered: 8 of 12 technique entries had wrong field names (e.g., 'sources_assessed'
instead of 'sources', 'ideas' instead of 'divergent_ideas', etc.) — all would silently
produce empty output when formatting prior results.
"""

from __future__ import annotations

import pytest

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
from sat.prompts.base import _TECHNIQUE_KEY_FIELDS


# Map technique IDs to their Pydantic model classes for field-name validation
_MODEL_MAP = {
    "assumptions": KeyAssumptionsResult,
    "ach": ACHResult,
    "quality": QualityOfInfoResult,
    "indicators": IndicatorsResult,
    "devils_advocacy": DevilsAdvocacyResult,
    "red_team": RedTeamResult,
    "brainstorming": BrainstormingResult,
    "alt_futures": AltFuturesResult,
    "outside_in": OutsideInResult,
    "what_if": WhatIfResult,
    "high_impact": HighImpactResult,
    "team_ab": TeamABResult,
}


class TestTechniqueKeyFieldsRegistry:
    """All field names in _TECHNIQUE_KEY_FIELDS must exist on their respective models."""

    def test_all_twelve_techniques_present(self):
        """Registry covers all 12 technique IDs."""
        assert set(_TECHNIQUE_KEY_FIELDS.keys()) == set(_MODEL_MAP.keys())

    @pytest.mark.parametrize("tid", list(_MODEL_MAP.keys()))
    def test_all_fields_exist_on_model(self, tid: str):
        """Every field listed for a technique must exist on that technique's Pydantic model."""
        model = _MODEL_MAP[tid]
        model_fields = set(model.model_fields.keys())
        fields = _TECHNIQUE_KEY_FIELDS[tid]
        for field in fields:
            assert field in model_fields, (
                f"{tid}: field '{field}' not found in {model.__name__}. "
                f"Available fields: {sorted(model_fields)}"
            )

    def test_assumptions_includes_most_vulnerable(self):
        """assumptions registry must include 'most_vulnerable' (was missing before fix)."""
        assert "most_vulnerable" in _TECHNIQUE_KEY_FIELDS["assumptions"]

    def test_quality_uses_sources_not_sources_assessed(self):
        """quality registry must use 'sources' not 'sources_assessed' (old wrong name)."""
        assert "sources" in _TECHNIQUE_KEY_FIELDS["quality"]
        assert "sources_assessed" not in _TECHNIQUE_KEY_FIELDS["quality"]

    def test_quality_includes_key_gaps_and_deception_indicators(self):
        """quality registry includes key_gaps and deception_indicators fields."""
        assert "key_gaps" in _TECHNIQUE_KEY_FIELDS["quality"]
        assert "deception_indicators" in _TECHNIQUE_KEY_FIELDS["quality"]

    def test_indicators_uses_trigger_mechanisms_not_collection_strategy(self):
        """indicators registry must use 'trigger_mechanisms' not 'collection_strategy'."""
        assert "trigger_mechanisms" in _TECHNIQUE_KEY_FIELDS["indicators"]
        assert "collection_strategy" not in _TECHNIQUE_KEY_FIELDS["indicators"]

    def test_devils_advocacy_uses_alternative_hypothesis(self):
        """devils_advocacy must use 'alternative_hypothesis' not 'alternative_interpretations'."""
        assert "alternative_hypothesis" in _TECHNIQUE_KEY_FIELDS["devils_advocacy"]
        assert "alternative_interpretations" not in _TECHNIQUE_KEY_FIELDS["devils_advocacy"]

    def test_red_team_uses_adversary_identity_not_scenario(self):
        """red_team must use 'adversary_identity' and 'first_person_memo', not 'scenario'."""
        assert "adversary_identity" in _TECHNIQUE_KEY_FIELDS["red_team"]
        assert "first_person_memo" in _TECHNIQUE_KEY_FIELDS["red_team"]
        assert "scenario" not in _TECHNIQUE_KEY_FIELDS["red_team"]

    def test_brainstorming_uses_divergent_ideas_not_ideas(self):
        """brainstorming must use 'divergent_ideas' not 'ideas'."""
        assert "divergent_ideas" in _TECHNIQUE_KEY_FIELDS["brainstorming"]
        assert "ideas" not in _TECHNIQUE_KEY_FIELDS["brainstorming"]

    def test_alt_futures_uses_key_uncertainties_not_drivers(self):
        """alt_futures must use 'key_uncertainties' not 'drivers'."""
        assert "key_uncertainties" in _TECHNIQUE_KEY_FIELDS["alt_futures"]
        assert "drivers" not in _TECHNIQUE_KEY_FIELDS["alt_futures"]

    def test_outside_in_uses_forces_not_factors(self):
        """outside_in must use 'forces' not 'factors'."""
        assert "forces" in _TECHNIQUE_KEY_FIELDS["outside_in"]
        assert "factors" not in _TECHNIQUE_KEY_FIELDS["outside_in"]

    def test_what_if_uses_chain_of_argumentation_not_scenarios(self):
        """what_if must use 'chain_of_argumentation' not 'scenarios'."""
        assert "chain_of_argumentation" in _TECHNIQUE_KEY_FIELDS["what_if"]
        assert "scenarios" not in _TECHNIQUE_KEY_FIELDS["what_if"]

    def test_high_impact_uses_pathways_not_scenarios(self):
        """high_impact must use 'pathways' and 'event_definition', not 'scenarios'."""
        assert "pathways" in _TECHNIQUE_KEY_FIELDS["high_impact"]
        assert "event_definition" in _TECHNIQUE_KEY_FIELDS["high_impact"]
        assert "scenarios" not in _TECHNIQUE_KEY_FIELDS["high_impact"]

    def test_team_ab_uses_team_a_team_b_not_team_a_position(self):
        """team_ab must use 'team_a' and 'team_b', not 'team_a_position' / 'team_b_position'."""
        assert "team_a" in _TECHNIQUE_KEY_FIELDS["team_ab"]
        assert "team_b" in _TECHNIQUE_KEY_FIELDS["team_ab"]
        assert "team_a_position" not in _TECHNIQUE_KEY_FIELDS["team_ab"]
        assert "team_b_position" not in _TECHNIQUE_KEY_FIELDS["team_ab"]
