"""Tests for per-technique model/temperature override configuration.

@decision DEC-TECH-OVERRIDE-001
@title Per-technique model and temperature overrides from ~/.sat/config.json
@status accepted
@rationale Analysts need different models for creative vs analytical techniques
  without changing the global provider config. TechniqueOverride is loaded from
  the technique_overrides key in ~/.sat/config.json. Resolution order:
  config override > technique class property > provider default.
  load_technique_overrides() is defensive: any parse or IO error returns {}.

# @mock-exempt: Provider boundary. AsyncMock inspects kwargs without real API calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

import sat.config as config_mod
from sat.config import TechniqueOverride, load_technique_overrides
from sat.techniques.base import TechniqueContext


# ---------------------------------------------------------------------------
# Fixture: redirect _get_sat_config_path to a temp file
# ---------------------------------------------------------------------------

@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Redirect _get_sat_config_path to a temp path."""
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
    return tmp_path


# ---------------------------------------------------------------------------
# load_technique_overrides() — config-loading behaviour
# ---------------------------------------------------------------------------

class TestLoadTechniqueOverrides:
    """load_technique_overrides() correctly reads from config or returns {}."""

    def test_no_config_file_returns_empty(self, config_dir):
        """When ~/.sat/config.json does not exist, return empty dict."""
        result = load_technique_overrides()
        assert result == {}

    def test_valid_overrides_parsed(self, config_dir):
        """Valid technique_overrides key produces correct TechniqueOverride objects."""
        data = {
            "technique_overrides": {
                "brainstorming": {"model": "gpt-4o", "temperature": 0.7},
                "ach": {"model": "claude-sonnet-4-6"},
            }
        }
        (config_dir / "config.json").write_text(json.dumps(data))

        result = load_technique_overrides()

        assert "brainstorming" in result
        assert result["brainstorming"].model == "gpt-4o"
        assert result["brainstorming"].temperature == 0.7

        assert "ach" in result
        assert result["ach"].model == "claude-sonnet-4-6"
        assert result["ach"].temperature is None

    def test_temperature_only_override(self, config_dir):
        """temperature-only entry leaves model as None."""
        data = {"technique_overrides": {"red_team": {"temperature": 1.2}}}
        (config_dir / "config.json").write_text(json.dumps(data))

        result = load_technique_overrides()
        assert result["red_team"].model is None
        assert result["red_team"].temperature == 1.2

    def test_model_only_override(self, config_dir):
        """model-only entry leaves temperature as None."""
        data = {"technique_overrides": {"ach": {"model": "o3"}}}
        (config_dir / "config.json").write_text(json.dumps(data))

        result = load_technique_overrides()
        assert result["ach"].model == "o3"
        assert result["ach"].temperature is None

    def test_malformed_json_returns_empty(self, config_dir):
        """Malformed JSON returns {} without raising."""
        (config_dir / "config.json").write_text("{ NOT VALID JSON }")
        assert load_technique_overrides() == {}

    def test_no_technique_overrides_key_returns_empty(self, config_dir):
        """Config file with no technique_overrides key returns {}."""
        data = {"providers": {"anthropic": {"api_key": "abc"}}}
        (config_dir / "config.json").write_text(json.dumps(data))
        assert load_technique_overrides() == {}

    def test_non_dict_entry_is_skipped(self, config_dir):
        """Non-dict entries in technique_overrides are silently skipped."""
        data = {
            "technique_overrides": {
                "brainstorming": "not-a-dict",
                "ach": {"model": "o3"},
            }
        }
        (config_dir / "config.json").write_text(json.dumps(data))

        result = load_technique_overrides()
        assert "brainstorming" not in result
        assert "ach" in result

    def test_empty_technique_overrides_returns_empty(self, config_dir):
        """Empty technique_overrides object returns {}."""
        data = {"technique_overrides": {}}
        (config_dir / "config.json").write_text(json.dumps(data))
        assert load_technique_overrides() == {}


# ---------------------------------------------------------------------------
# TechniqueOverride model — validation
# ---------------------------------------------------------------------------

class TestTechniqueOverrideValidation:
    """TechniqueOverride Pydantic model validates correctly."""

    def test_all_none_defaults(self):
        """Both fields default to None."""
        override = TechniqueOverride()
        assert override.model is None
        assert override.temperature is None

    def test_model_set(self):
        override = TechniqueOverride(model="gpt-4o")
        assert override.model == "gpt-4o"
        assert override.temperature is None

    def test_temperature_lower_bound(self):
        """temperature=0.0 is valid."""
        override = TechniqueOverride(temperature=0.0)
        assert override.temperature == 0.0

    def test_temperature_upper_bound(self):
        """temperature=2.0 is valid."""
        override = TechniqueOverride(temperature=2.0)
        assert override.temperature == 2.0

    def test_temperature_midrange(self):
        override = TechniqueOverride(temperature=1.0)
        assert override.temperature == 1.0

    def test_temperature_below_lower_raises(self):
        """temperature < 0 should raise ValidationError."""
        with pytest.raises(Exception):
            TechniqueOverride(temperature=-0.1)

    def test_temperature_above_upper_raises(self):
        """temperature > 2.0 should raise ValidationError."""
        with pytest.raises(Exception):
            TechniqueOverride(temperature=2.1)

    def test_model_can_be_any_string(self):
        """Model field accepts any non-None string."""
        override = TechniqueOverride(model="some-custom-model-v1")
        assert override.model == "some-custom-model-v1"


# ---------------------------------------------------------------------------
# execute() temperature resolution — override > class property > None
# ---------------------------------------------------------------------------

class TestExecuteTemperatureResolution:
    """temperature_override in execute() takes precedence over technique class property."""

    @pytest.mark.asyncio
    async def test_override_beats_class_property(self):
        """temperature_override=0.5 is used even when technique.temperature=0.9."""
        from sat.techniques.imaginative.brainstorming import Brainstorming
        from sat.models.brainstorming import BrainstormingResult

        technique = Brainstorming()
        assert technique.temperature == 0.9, "Precondition: brainstorming has temperature=0.9"

        ctx = TechniqueContext(question="Test?", evidence="Some evidence.")
        mock_result = BrainstormingResult(
            technique_id="brainstorming",
            technique_name="Brainstorming",
            summary="Test",
        )
        provider = AsyncMock()
        provider.generate_structured = AsyncMock(return_value=mock_result)

        await technique.execute(ctx, provider, temperature_override=0.5)

        _, kwargs = provider.generate_structured.call_args
        assert kwargs.get("temperature") == 0.5, (
            f"Expected temperature=0.5 from override, got {kwargs.get('temperature')}"
        )

    @pytest.mark.asyncio
    async def test_class_property_used_when_no_override(self):
        """When temperature_override is None, technique.temperature is used."""
        from sat.techniques.imaginative.brainstorming import Brainstorming
        from sat.models.brainstorming import BrainstormingResult

        technique = Brainstorming()
        ctx = TechniqueContext(question="Test?", evidence="Evidence.")
        mock_result = BrainstormingResult(
            technique_id="brainstorming",
            technique_name="Brainstorming",
            summary="Test",
        )
        provider = AsyncMock()
        provider.generate_structured = AsyncMock(return_value=mock_result)

        await technique.execute(ctx, provider, temperature_override=None)

        _, kwargs = provider.generate_structured.call_args
        assert kwargs.get("temperature") == 0.9, (
            f"Expected technique's own temperature=0.9, got {kwargs.get('temperature')}"
        )

    @pytest.mark.asyncio
    async def test_override_zero_is_used(self):
        """temperature_override=0.0 (falsy!) is passed through, not ignored."""
        from sat.techniques.imaginative.brainstorming import Brainstorming
        from sat.models.brainstorming import BrainstormingResult

        technique = Brainstorming()
        ctx = TechniqueContext(question="Test?", evidence="Evidence.")
        mock_result = BrainstormingResult(
            technique_id="brainstorming",
            technique_name="Brainstorming",
            summary="Test",
        )
        provider = AsyncMock()
        provider.generate_structured = AsyncMock(return_value=mock_result)

        await technique.execute(ctx, provider, temperature_override=0.0)

        _, kwargs = provider.generate_structured.call_args
        assert kwargs.get("temperature") == 0.0, (
            f"temperature_override=0.0 must not be ignored (falsy trap), got {kwargs.get('temperature')}"
        )

    @pytest.mark.asyncio
    async def test_no_temperature_set_no_kwarg(self):
        """When both override is None and class property is None, temperature kwarg is omitted."""
        from sat.techniques.diagnostic.ach import ACHTechnique
        from sat.models.ach import ACHResult

        technique = ACHTechnique()
        assert technique.temperature is None, "Precondition: ACH has no temperature override"

        ctx = TechniqueContext(question="Test?", evidence="Evidence.")
        mock_result = ACHResult(
            technique_id="ach",
            technique_name="ACH",
            summary="Test",
        )
        provider = AsyncMock()
        provider.generate_structured = AsyncMock(return_value=mock_result)

        await technique.execute(ctx, provider, temperature_override=None)

        _, kwargs = provider.generate_structured.call_args
        assert "temperature" not in kwargs, (
            "temperature kwarg must be omitted when both override and class property are None"
        )

    @pytest.mark.asyncio
    async def test_override_on_analytical_technique(self):
        """temperature_override on a technique with temperature=None applies the override."""
        from sat.techniques.diagnostic.assumptions import KeyAssumptionsCheck
        from sat.models.assumptions import KeyAssumptionsResult

        technique = KeyAssumptionsCheck()
        assert technique.temperature is None, "Precondition: KeyAssumptionsCheck has no temperature"

        ctx = TechniqueContext(question="Test?", evidence="Evidence.")
        mock_result = KeyAssumptionsResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Test",
        )
        provider = AsyncMock()
        provider.generate_structured = AsyncMock(return_value=mock_result)

        await technique.execute(ctx, provider, temperature_override=0.8)

        _, kwargs = provider.generate_structured.call_args
        assert kwargs.get("temperature") == 0.8, (
            f"temperature_override=0.8 on analytical technique must be applied, got {kwargs.get('temperature')}"
        )
