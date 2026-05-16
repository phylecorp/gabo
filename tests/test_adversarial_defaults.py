"""Tests for adversarial defaults config loading and build_adversarial_config integration.

Covers:
1. load_adversarial_defaults() — missing config, empty config, valid config, malformed JSON
2. AdversarialDefaults validation — rounds bounds, field types
3. build_adversarial_config() with explicit defaults parameter:
   - Challenger provider/model from defaults overrides auto-resolution
   - Investigator provider/model from defaults overrides auto-resolution
   - Mode from defaults used when caller omits it
   - Rounds from defaults used when caller uses default (1)
   - Empty defaults → existing auto-resolution behavior
4. Backward compat: calling without defaults param still works (loads from config file)

@decision DEC-ADV-DEFAULTS-001
@title AdversarialDefaults loaded from ~/.sat/config.json adversarial key
@status accepted
@rationale Persistent adversarial defaults let users configure their preferred
  mode, rounds, and provider overrides once rather than repeating CLI flags or
  API parameters. The defaults are layered under the existing adversarial config
  build logic — explicit call arguments always win.

@mock-exempt: _get_sat_config_path is internal path resolution; monkeypatching
  it redirects I/O to a temp file. resolve_challenger/investigator_provider use
  env vars (external OS state), so patch.dict(os.environ) is appropriate there.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

import sat.config as config_mod
from sat.adversarial.config import build_adversarial_config
from sat.config import AdversarialDefaults, load_adversarial_defaults


# ---------------------------------------------------------------------------
# Fixture: redirect _get_sat_config_path to a temp file
# ---------------------------------------------------------------------------


@pytest.fixture()
def config_dir(tmp_path, monkeypatch):
    """Redirect sat.config._get_sat_config_path to a temp path.

    Also redirects the same function as seen from sat.adversarial.config,
    since build_adversarial_config imports via 'from sat.config import ...'.
    """
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
    return tmp_path


# ---------------------------------------------------------------------------
# load_adversarial_defaults() — config-loading behaviour
# ---------------------------------------------------------------------------


class TestLoadAdversarialDefaults:
    """load_adversarial_defaults() reads from config or returns empty defaults."""

    def test_missing_config_returns_empty_defaults(self, config_dir):
        """When ~/.sat/config.json does not exist, return all-None AdversarialDefaults."""
        result = load_adversarial_defaults()
        assert result.enabled is None
        assert result.mode is None
        assert result.rounds is None
        assert result.challenger_provider is None
        assert result.challenger_model is None
        assert result.investigator_provider is None
        assert result.investigator_model is None

    def test_config_with_no_adversarial_key_returns_empty(self, config_dir):
        """Config file with no 'adversarial' key returns empty defaults."""
        data = {"providers": {"anthropic": {"api_key": "abc"}}}
        (config_dir / "config.json").write_text(json.dumps(data))

        result = load_adversarial_defaults()
        assert result.mode is None
        assert result.rounds is None

    def test_valid_full_config_parsed(self, config_dir):
        """Valid adversarial section in config.json is parsed into AdversarialDefaults."""
        data = {
            "adversarial": {
                "enabled": True,
                "mode": "trident",
                "rounds": 3,
                "challenger_provider": "openai",
                "challenger_model": "gpt-4o",
                "investigator_provider": "gemini",
                "investigator_model": "gemini-2.5-pro",
            }
        }
        (config_dir / "config.json").write_text(json.dumps(data))

        result = load_adversarial_defaults()
        assert result.enabled is True
        assert result.mode == "trident"
        assert result.rounds == 3
        assert result.challenger_provider == "openai"
        assert result.challenger_model == "gpt-4o"
        assert result.investigator_provider == "gemini"
        assert result.investigator_model == "gemini-2.5-pro"

    def test_partial_config_parsed(self, config_dir):
        """Partial adversarial section parses what's present; rest are None."""
        data = {"adversarial": {"mode": "dual", "rounds": 2}}
        (config_dir / "config.json").write_text(json.dumps(data))

        result = load_adversarial_defaults()
        assert result.mode == "dual"
        assert result.rounds == 2
        assert result.enabled is None
        assert result.challenger_provider is None

    def test_malformed_json_returns_empty(self, config_dir):
        """Malformed JSON returns empty defaults without raising."""
        (config_dir / "config.json").write_text("{ NOT VALID JSON }")
        result = load_adversarial_defaults()
        assert result.mode is None
        assert result.rounds is None

    def test_adversarial_key_not_a_dict_returns_empty(self, config_dir):
        """If 'adversarial' value is not a dict, return empty defaults."""
        data = {"adversarial": "not-a-dict"}
        (config_dir / "config.json").write_text(json.dumps(data))
        result = load_adversarial_defaults()
        assert result.mode is None
        assert result.rounds is None

    def test_empty_adversarial_dict_returns_empty(self, config_dir):
        """Empty adversarial dict returns all-None defaults."""
        data = {"adversarial": {}}
        (config_dir / "config.json").write_text(json.dumps(data))
        result = load_adversarial_defaults()
        assert result.mode is None
        assert result.rounds is None
        assert result.enabled is None


# ---------------------------------------------------------------------------
# AdversarialDefaults model — validation
# ---------------------------------------------------------------------------


class TestAdversarialDefaultsValidation:
    """AdversarialDefaults Pydantic model validates fields correctly."""

    def test_all_none_defaults(self):
        """Default construction produces all-None fields."""
        d = AdversarialDefaults()
        assert d.enabled is None
        assert d.mode is None
        assert d.rounds is None
        assert d.challenger_provider is None
        assert d.challenger_model is None
        assert d.investigator_provider is None
        assert d.investigator_model is None

    def test_rounds_lower_bound_one(self):
        """rounds=1 is valid (ge=1)."""
        d = AdversarialDefaults(rounds=1)
        assert d.rounds == 1

    def test_rounds_upper_bound_five(self):
        """rounds=5 is valid (le=5)."""
        d = AdversarialDefaults(rounds=5)
        assert d.rounds == 5

    def test_rounds_zero_raises(self):
        """rounds=0 violates ge=1 constraint."""
        with pytest.raises(Exception):
            AdversarialDefaults(rounds=0)

    def test_rounds_six_raises(self):
        """rounds=6 violates le=5 constraint."""
        with pytest.raises(Exception):
            AdversarialDefaults(rounds=6)

    def test_mode_dual(self):
        """mode='dual' is stored as-is."""
        d = AdversarialDefaults(mode="dual")
        assert d.mode == "dual"

    def test_mode_trident(self):
        """mode='trident' is stored as-is."""
        d = AdversarialDefaults(mode="trident")
        assert d.mode == "trident"

    def test_enabled_true(self):
        d = AdversarialDefaults(enabled=True)
        assert d.enabled is True

    def test_enabled_false(self):
        d = AdversarialDefaults(enabled=False)
        assert d.enabled is False


# ---------------------------------------------------------------------------
# build_adversarial_config() with explicit defaults
# ---------------------------------------------------------------------------


class TestBuildAdversarialConfigWithDefaults:
    """build_adversarial_config() respects AdversarialDefaults overrides."""

    def test_empty_defaults_uses_auto_resolution(self):
        """Empty AdversarialDefaults falls through to auto-resolution (existing behavior)."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
                cfg = build_adversarial_config(
                    provider="anthropic",
                    defaults=AdversarialDefaults(),
                )
        assert cfg.providers["primary"].provider == "anthropic"
        assert cfg.providers["challenger"].provider == "openai"

    def test_challenger_provider_from_defaults_overrides_auto(self):
        """challenger_provider in defaults overrides resolve_challenger_provider result."""
        # Even with OPENAI available, defaults forces gemini as challenger
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "GEMINI_API_KEY": "gem-test"}, clear=False):
            cfg = build_adversarial_config(
                provider="anthropic",
                defaults=AdversarialDefaults(
                    challenger_provider="gemini",
                    challenger_model="gemini-2.5-pro",
                ),
            )
        assert cfg.providers["challenger"].provider == "gemini"
        assert cfg.providers["challenger"].model == "gemini-2.5-pro"

    def test_challenger_provider_without_model_resolves_default(self):
        """challenger_provider from defaults without challenger_model resolves default model."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                cfg = build_adversarial_config(
                    provider="anthropic",
                    defaults=AdversarialDefaults(challenger_provider="openai"),
                )
        assert cfg.providers["challenger"].provider == "openai"
        # Model should be resolved (non-empty string)
        assert cfg.providers["challenger"].model

    def test_investigator_provider_from_defaults_overrides_auto(self):
        """investigator_provider in defaults sets the investigator ProviderRef."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                cfg = build_adversarial_config(
                    provider="anthropic",
                    defaults=AdversarialDefaults(
                        investigator_provider="gemini",
                        investigator_model="gemini-2.5-pro",
                    ),
                )
        assert "investigator" in cfg.providers
        assert cfg.providers["investigator"].provider == "gemini"
        assert cfg.providers["investigator"].model == "gemini-2.5-pro"

    def test_investigator_from_defaults_sets_trident_mode(self):
        """When investigator_provider from defaults triggers trident, effective_mode is 'trident'."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                cfg = build_adversarial_config(
                    provider="anthropic",
                    defaults=AdversarialDefaults(investigator_provider="gemini"),
                )
        assert cfg.mode == "trident"
        assert cfg.roles is not None
        assert cfg.roles.investigator == "investigator"

    def test_mode_from_defaults_dual(self):
        """mode='dual' in defaults is used when caller omits mode."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {
                "ANTHROPIC_API_KEY": "ant-key",
                "OPENAI_API_KEY": "oai-key",
                "GEMINI_API_KEY": "gem-key",
            }, clear=True):
                # All three providers available, but defaults forces dual
                cfg = build_adversarial_config(
                    provider="anthropic",
                    defaults=AdversarialDefaults(mode="dual"),
                )
        assert cfg.mode == "dual"
        assert "investigator" not in cfg.providers

    def test_mode_from_defaults_trident(self):
        """mode='trident' in defaults activates trident when caller omits mode."""
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "ant-key",
            "OPENAI_API_KEY": "oai-key",
            "GEMINI_API_KEY": "gem-key",
        }, clear=True):
            cfg = build_adversarial_config(
                provider="anthropic",
                defaults=AdversarialDefaults(mode="trident"),
            )
        assert cfg.mode == "trident"
        assert "investigator" in cfg.providers

    def test_explicit_mode_param_beats_defaults_mode(self):
        """Explicit mode= argument to build_adversarial_config beats defaults.mode."""
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "ant-key",
            "OPENAI_API_KEY": "oai-key",
            "GEMINI_API_KEY": "gem-key",
        }, clear=True):
            # defaults says trident but caller explicitly says dual
            cfg = build_adversarial_config(
                provider="anthropic",
                mode="dual",
                defaults=AdversarialDefaults(mode="trident"),
            )
        assert cfg.mode == "dual"
        assert "investigator" not in cfg.providers

    def test_rounds_from_defaults_used_when_caller_uses_default(self):
        """defaults.rounds is applied when caller does not pass rounds (uses default=1)."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
                cfg = build_adversarial_config(
                    provider="anthropic",
                    defaults=AdversarialDefaults(rounds=3),
                )
        assert cfg.rounds == 3

    def test_explicit_rounds_beats_defaults_rounds(self):
        """Explicitly passing rounds=2 overrides defaults.rounds=4."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
                cfg = build_adversarial_config(
                    provider="anthropic",
                    rounds=2,
                    defaults=AdversarialDefaults(rounds=4),
                )
        assert cfg.rounds == 2

    def test_no_defaults_rounds_uses_caller_rounds(self):
        """When defaults.rounds is None, caller rounds value is used as-is."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
                cfg = build_adversarial_config(
                    provider="anthropic",
                    rounds=1,
                    defaults=AdversarialDefaults(),
                )
        assert cfg.rounds == 1


# ---------------------------------------------------------------------------
# Backward compatibility: no defaults param → loads from config file
# ---------------------------------------------------------------------------


class TestBuildAdversarialConfigBackwardCompat:
    """Calling build_adversarial_config without defaults= still works."""

    def test_no_defaults_param_still_works(self):
        """Omitting defaults= does not raise and returns valid config."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
                cfg = build_adversarial_config(provider="anthropic")
        assert cfg.enabled is True
        assert "primary" in cfg.providers
        assert "challenger" in cfg.providers

    def test_no_defaults_param_reads_config_file(self, config_dir):
        """When defaults= is omitted, rounds from config file are applied."""
        data = {"adversarial": {"rounds": 4}}
        (config_dir / "config.json").write_text(json.dumps(data))

        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
                cfg = build_adversarial_config(provider="anthropic")
        # defaults.rounds=4, caller uses default rounds=1, so effective is 4
        assert cfg.rounds == 4

    def test_no_defaults_param_challenger_from_config_file(self, config_dir):
        """When defaults= is omitted, challenger_provider from config file is applied."""
        data = {
            "adversarial": {
                "challenger_provider": "gemini",
                "challenger_model": "gemini-2.5-pro",
            }
        }
        (config_dir / "config.json").write_text(json.dumps(data))

        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                cfg = build_adversarial_config(provider="anthropic")
        assert cfg.providers["challenger"].provider == "gemini"
        assert cfg.providers["challenger"].model == "gemini-2.5-pro"
