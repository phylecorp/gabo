"""Integration tests for ProviderConfig.resolve_model() fallback chain (Issue #12).

Verifies that NewAnalysis with model=None correctly falls back to saved defaults,
and that explicit model params override config.json defaults.

@decision DEC-CFG-005
@title ProviderConfig.resolve_model() three-tier fallback: explicit > config.json > env/built-in
@status accepted
@rationale When the frontend sends model=None (no manual override), the backend must
resolve the model via: explicit model param > config.json default_model > env var >
built-in DEFAULT_MODELS. This test suite verifies all four tiers of the chain using
real ProviderConfig instances and a tmp_path config file redirected via monkeypatch
on the sat.config module (which the docstring explicitly designates as overrideable
in tests: "Overrideable in tests by monkey-patching this function on the module").

Production scenario: NewAnalysis computes effectiveModel as
  modelOverride.trim() || selectedProviderInfo?.default_model || null
If a user has saved default_model="gpt-4o" in config.json via Settings, the frontend
sends that value as the model param. If no saved model, frontend sends null and the
backend resolve chain applies. This file tests both paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import sat.config as config_mod
from sat.config import ProviderConfig, DEFAULT_MODELS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_config(tmp_path: Path, providers: dict) -> Path:
    """Write a minimal ~/.sat/config.json to tmp_path and return its path."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"providers": providers}))
    return config_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    """Redirect _get_sat_config_path to a temp file for test isolation.

    _get_sat_config_path is explicitly designed to be overrideable in tests
    (see docstring in sat/config.py). This fixture uses monkeypatch.setattr
    (not unittest.mock) to redirect it to a temp file.
    """
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_file)
    return config_file


@pytest.fixture(autouse=True)
def clean_model_env_vars(monkeypatch):
    """Remove model-related env vars before each test to ensure clean state."""
    for var in ("ANTHROPIC_MODEL", "OPENAI_MODEL", "GEMINI_MODEL"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Tier 1: Explicit model param overrides everything
# ---------------------------------------------------------------------------


class TestExplicitModelParam:
    """When model is explicitly set, it wins over all other sources."""

    def test_explicit_model_returned_directly(self, tmp_config):
        """Explicit model param wins over config.json default_model."""
        tmp_config.write_text(json.dumps({"providers": {"openai": {"default_model": "gpt-4o"}}}))
        cfg = ProviderConfig(provider="openai", model="gpt-4.1")
        assert cfg.resolve_model() == "gpt-4.1"

    def test_explicit_model_wins_over_env_var(self, tmp_config, monkeypatch):
        """Explicit model param wins even when OPENAI_MODEL env var is set."""
        tmp_config.write_text(json.dumps({"providers": {}}))
        monkeypatch.setenv("OPENAI_MODEL", "env-model")
        cfg = ProviderConfig(provider="openai", model="gpt-4.1")
        assert cfg.resolve_model() == "gpt-4.1"

    def test_explicit_model_wins_for_anthropic(self, tmp_config):
        """Explicit model param works for Anthropic provider."""
        tmp_config.write_text(
            json.dumps({"providers": {"anthropic": {"default_model": "claude-opus-4-6"}}})
        )
        cfg = ProviderConfig(provider="anthropic", model="claude-sonnet-4-6")
        assert cfg.resolve_model() == "claude-sonnet-4-6"

    def test_explicit_model_wins_for_gemini(self, tmp_config):
        """Explicit model param works for Gemini provider."""
        tmp_config.write_text(
            json.dumps({"providers": {"gemini": {"default_model": "gemini-2.5-pro"}}})
        )
        cfg = ProviderConfig(provider="gemini", model="gemini-2.0-flash")
        assert cfg.resolve_model() == "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# Tier 2: Config file default_model (model=None falls through to config.json)
# ---------------------------------------------------------------------------


class TestConfigFileModelFallback:
    """When model=None, resolve_model() reads default_model from config.json."""

    def test_model_none_falls_through_to_config_file(self, tmp_config):
        """Core requirement: ProviderConfig(model=None) resolves to config.json default_model."""
        tmp_config.write_text(json.dumps({"providers": {"openai": {"default_model": "gpt-4o"}}}))
        cfg = ProviderConfig(provider="openai", model=None)
        assert cfg.resolve_model() == "gpt-4o"

    def test_model_none_falls_through_for_anthropic(self, tmp_config):
        """Config file fallback works for Anthropic provider."""
        tmp_config.write_text(
            json.dumps({"providers": {"anthropic": {"default_model": "claude-haiku-4-5-20251001"}}})
        )
        cfg = ProviderConfig(provider="anthropic", model=None)
        assert cfg.resolve_model() == "claude-haiku-4-5-20251001"

    def test_model_none_falls_through_for_gemini(self, tmp_config):
        """Config file fallback works for Gemini provider."""
        tmp_config.write_text(
            json.dumps({"providers": {"gemini": {"default_model": "gemini-2.0-flash"}}})
        )
        cfg = ProviderConfig(provider="gemini", model=None)
        assert cfg.resolve_model() == "gemini-2.0-flash"

    def test_empty_default_model_in_config_falls_through(self, tmp_config):
        """An empty string default_model in config.json is treated as absent — falls to next tier."""
        tmp_config.write_text(json.dumps({"providers": {"openai": {"default_model": ""}}}))
        cfg = ProviderConfig(provider="openai", model=None)
        # Falls through empty config to built-in default
        result = cfg.resolve_model()
        assert result == DEFAULT_MODELS["openai"]

    def test_missing_provider_in_config_falls_through(self, tmp_config):
        """If provider has no entry in config.json, falls through to env/built-in."""
        tmp_config.write_text(
            json.dumps({"providers": {"anthropic": {"default_model": "claude-opus-4-6"}}})
        )
        cfg = ProviderConfig(provider="openai", model=None)
        # No openai entry → falls through to built-in default
        result = cfg.resolve_model()
        assert result == DEFAULT_MODELS["openai"]


# ---------------------------------------------------------------------------
# Tier 3: Environment variable fallback
# ---------------------------------------------------------------------------


class TestEnvVarModelFallback:
    """When model=None and no config.json entry, env var is checked."""

    def test_model_none_reads_openai_model_env_var(self, tmp_config, monkeypatch):
        """OPENAI_MODEL env var is used when model=None and no config.json entry."""
        tmp_config.write_text(json.dumps({"providers": {}}))  # No openai entry
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
        cfg = ProviderConfig(provider="openai", model=None)
        assert cfg.resolve_model() == "gpt-4.1"

    def test_model_none_reads_anthropic_model_env_var(self, tmp_config, monkeypatch):
        """ANTHROPIC_MODEL env var is used when model=None and no config.json entry."""
        tmp_config.write_text(json.dumps({"providers": {}}))
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        cfg = ProviderConfig(provider="anthropic", model=None)
        assert cfg.resolve_model() == "claude-sonnet-4-6"

    def test_config_file_wins_over_env_var(self, tmp_config, monkeypatch):
        """config.json default_model takes priority over env var (tier 2 > tier 3)."""
        tmp_config.write_text(json.dumps({"providers": {"openai": {"default_model": "gpt-4o"}}}))
        monkeypatch.setenv("OPENAI_MODEL", "env-model")
        cfg = ProviderConfig(provider="openai", model=None)
        assert cfg.resolve_model() == "gpt-4o"


# ---------------------------------------------------------------------------
# Tier 4: Built-in DEFAULT_MODELS fallback
# ---------------------------------------------------------------------------


class TestBuiltinDefaultModelFallback:
    """When model=None and no config.json and no env var, built-in default is used."""

    def test_model_none_no_config_no_env_returns_builtin(self, tmp_config):
        """Falls all the way through to built-in default when nothing else is set."""
        tmp_config.write_text(json.dumps({"providers": {}}))
        cfg = ProviderConfig(provider="openai", model=None)
        assert cfg.resolve_model() == DEFAULT_MODELS["openai"]

    def test_anthropic_builtin_default(self, tmp_config):
        """Anthropic built-in default is returned when no other source is available."""
        tmp_config.write_text(json.dumps({"providers": {}}))
        cfg = ProviderConfig(provider="anthropic", model=None)
        assert cfg.resolve_model() == DEFAULT_MODELS["anthropic"]

    def test_gemini_builtin_default(self, tmp_config):
        """Gemini built-in default is returned when no other source is available."""
        tmp_config.write_text(json.dumps({"providers": {}}))
        cfg = ProviderConfig(provider="gemini", model=None)
        assert cfg.resolve_model() == DEFAULT_MODELS["gemini"]

    def test_unknown_provider_returns_anthropic_default(self, tmp_config):
        """Unknown provider falls back to 'claude-opus-4-6' (the .get() fallback in resolve_model)."""
        tmp_config.write_text(json.dumps({"providers": {}}))
        cfg = ProviderConfig(provider="unknown_provider", model=None)
        # DEFAULT_MODELS.get("unknown_provider", "claude-opus-4-6") → hardcoded fallback
        assert cfg.resolve_model() == "claude-opus-4-6"

    def test_config_file_missing_entirely_falls_to_builtin(self, tmp_path, monkeypatch):
        """When ~/.sat/config.json doesn't exist, falls all the way to built-in default."""
        non_existent = tmp_path / "does_not_exist.json"
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: non_existent)
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        cfg = ProviderConfig(provider="openai", model=None)
        assert cfg.resolve_model() == DEFAULT_MODELS["openai"]


# ---------------------------------------------------------------------------
# Production scenario: NewAnalysis model passthrough
# ---------------------------------------------------------------------------


class TestNewAnalysisModelPassthrough:
    """End-to-end scenarios mirroring what NewAnalysis sends to the backend.

    Production sequence:
    1. User selects provider (e.g. "openai")
    2. Frontend calls GET /api/config/providers → gets ProviderInfo with default_model
    3. effectiveModel = modelOverride.trim() || selectedProviderInfo?.default_model || null
    4. Backend receives model=<effectiveModel> and calls
       ProviderConfig(provider=..., model=<effectiveModel>).resolve_model()

    Case A: User typed a manual override → model="gpt-4.1" (explicit tier 1)
    Case B: User has a saved default in config.json → model="gpt-4o" (config tier 2, but
            the frontend already sends it as the model param, so it arrives as tier 1)
    Case C: Neither override nor saved default → model=null → backend resolves via chain
    """

    def test_case_a_manual_override_sent_directly(self, tmp_config):
        """Case A: Manual override passes through to ProviderConfig as tier-1 explicit model."""
        tmp_config.write_text(json.dumps({"providers": {"openai": {"default_model": "gpt-4o"}}}))
        # Frontend sends model="gpt-4.1" (user typed it)
        cfg = ProviderConfig(provider="openai", model="gpt-4.1")
        assert cfg.resolve_model() == "gpt-4.1"

    def test_case_b_config_default_sent_as_model_param(self, tmp_config):
        """Case B: Frontend reads config default and sends it as model param — arrives as tier 1."""
        tmp_config.write_text(json.dumps({"providers": {"openai": {"default_model": "gpt-4o"}}}))
        # Frontend reads default_model="gpt-4o" from GET /api/config/providers
        # and sends it as model="gpt-4o" → arrives as tier-1 explicit value
        cfg = ProviderConfig(provider="openai", model="gpt-4o")
        assert cfg.resolve_model() == "gpt-4o"

    def test_case_c_null_triggers_config_file_fallback(self, tmp_config):
        """Case C: model=null → backend reads config.json default_model as tier-2 fallback."""
        tmp_config.write_text(json.dumps({"providers": {"openai": {"default_model": "gpt-4o"}}}))
        # Frontend sends model=None (no override, no saved default in ProviderInfo)
        cfg = ProviderConfig(provider="openai", model=None)
        assert cfg.resolve_model() == "gpt-4o"

    def test_case_c_null_no_config_returns_builtin(self, tmp_config):
        """Case C variant: model=null, no config → falls to built-in default."""
        tmp_config.write_text(json.dumps({"providers": {}}))
        cfg = ProviderConfig(provider="openai", model=None)
        assert cfg.resolve_model() == DEFAULT_MODELS["openai"]
