"""Tests for build_adversarial_config factory function.

Covers the four key scenarios: basic dual mode, self-critique fallback,
trident auto-detection, and explicit trident mode.

@mock-exempt: Environment variables are external OS state.
Testing environment variable resolution requires controlling os.environ,
which is an external boundary, not internal code.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from sat.adversarial.config import build_adversarial_config


class TestBuildAdversarialConfigDualMode:
    """Basic dual mode with a challenger available."""

    def test_returns_adversarial_config_enabled(self):
        """Factory always returns enabled=True config."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            cfg = build_adversarial_config(provider="anthropic")
        assert cfg.enabled is True

    def test_returns_populated_providers(self):
        """Providers dict must have at least 'primary' and 'challenger'."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            cfg = build_adversarial_config(provider="anthropic")
        assert "primary" in cfg.providers
        assert "challenger" in cfg.providers
        assert cfg.providers["primary"].provider == "anthropic"
        assert cfg.providers["challenger"].provider == "openai"

    def test_returns_populated_roles(self):
        """RoleAssignment must not be None and must map primary and challenger."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            cfg = build_adversarial_config(provider="anthropic")
        assert cfg.roles is not None
        assert cfg.roles.primary == "primary"
        assert cfg.roles.challenger == "challenger"

    def test_mode_is_dual_when_no_investigator(self):
        """Mode is 'dual' when only one challenger provider is available."""
        env = {"OPENAI_API_KEY": "sk-test"}
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, env, clear=True):
                cfg = build_adversarial_config(provider="anthropic")
        assert cfg.mode == "dual"
        assert "investigator" not in cfg.providers

    def test_explicit_model_passed_to_primary(self):
        """Explicit model param is passed to the primary ProviderRef."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            cfg = build_adversarial_config(
                provider="anthropic", model="claude-3-5-haiku-20241022"
            )
        assert cfg.providers["primary"].model == "claude-3-5-haiku-20241022"

    def test_explicit_rounds_propagated(self):
        """Rounds parameter is set on the returned config."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            cfg = build_adversarial_config(provider="anthropic", rounds=3)
        assert cfg.rounds == 3

    def test_api_key_passed_to_primary(self):
        """Explicit api_key is threaded into the primary ProviderRef."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
            cfg = build_adversarial_config(provider="anthropic", api_key="my-key")
        assert cfg.providers["primary"].api_key == "my-key"


class TestBuildAdversarialConfigSelfCritiqueFallback:
    """When no other provider is available, fall back to self-critique."""

    def test_self_critique_when_no_challenger(self):
        """Primary provider is also used as challenger in self-critique mode."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                cfg = build_adversarial_config(provider="anthropic")
        assert cfg.providers["primary"].provider == "anthropic"
        assert cfg.providers["challenger"].provider == "anthropic"

    def test_self_critique_roles_still_populated(self):
        """RoleAssignment is still present in self-critique fallback."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                cfg = build_adversarial_config(provider="anthropic")
        assert cfg.roles is not None
        assert cfg.roles.primary == "primary"
        assert cfg.roles.challenger == "challenger"

    def test_self_critique_mode_is_dual(self):
        """Mode is 'dual' in self-critique — no investigator available."""
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                cfg = build_adversarial_config(provider="anthropic")
        assert cfg.mode == "dual"


class TestBuildAdversarialConfigTridetAutoDetect:
    """Trident auto-detection when all three providers have keys."""

    def test_auto_upgrades_to_trident_when_three_providers_available(self):
        """Mode auto-upgrades to 'trident' when a third provider key is present."""
        env = {
            "ANTHROPIC_API_KEY": "ant-key",
            "OPENAI_API_KEY": "oai-key",
            "GEMINI_API_KEY": "gem-key",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = build_adversarial_config(provider="anthropic")
        assert cfg.mode == "trident"

    def test_investigator_provider_added_in_trident(self):
        """'investigator' key present in providers and roles when trident."""
        env = {
            "ANTHROPIC_API_KEY": "ant-key",
            "OPENAI_API_KEY": "oai-key",
            "GEMINI_API_KEY": "gem-key",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = build_adversarial_config(provider="anthropic")
        assert "investigator" in cfg.providers
        assert cfg.roles is not None
        assert cfg.roles.investigator == "investigator"

    def test_investigator_is_different_from_primary_and_challenger(self):
        """Investigator provider is neither primary nor challenger."""
        env = {
            "ANTHROPIC_API_KEY": "ant-key",
            "OPENAI_API_KEY": "oai-key",
            "GEMINI_API_KEY": "gem-key",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = build_adversarial_config(provider="anthropic")
        primary_prov = cfg.providers["primary"].provider
        challenger_prov = cfg.providers["challenger"].provider
        investigator_prov = cfg.providers["investigator"].provider
        assert investigator_prov != primary_prov
        assert investigator_prov != challenger_prov


class TestBuildAdversarialConfigExplicitTriident:
    """Explicit trident mode requested by caller."""

    def test_explicit_trident_resolves_investigator(self):
        """Explicit trident mode resolves investigator when third provider available."""
        env = {
            "ANTHROPIC_API_KEY": "ant-key",
            "OPENAI_API_KEY": "oai-key",
            "GEMINI_API_KEY": "gem-key",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = build_adversarial_config(
                provider="anthropic", mode="trident"
            )
        assert cfg.mode == "trident"
        assert "investigator" in cfg.providers

    def test_explicit_trident_without_third_provider_stays_dual_roles(self):
        """Explicit trident without a third provider: investigator absent from providers."""
        env = {
            "OPENAI_API_KEY": "oai-key",
        }
        with patch("sat.config._load_config_file_key", return_value=None):
            with patch.dict(os.environ, env, clear=True):
                cfg = build_adversarial_config(
                    provider="anthropic", mode="trident"
                )
        # No Gemini key, so investigator cannot be resolved — providers dict has 2 entries
        assert "investigator" not in cfg.providers

    def test_explicit_dual_mode_does_not_auto_upgrade(self):
        """Explicit dual mode is NOT upgraded to trident even with three providers."""
        env = {
            "ANTHROPIC_API_KEY": "ant-key",
            "OPENAI_API_KEY": "oai-key",
            "GEMINI_API_KEY": "gem-key",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = build_adversarial_config(provider="anthropic", mode="dual")
        assert cfg.mode == "dual"
        assert "investigator" not in cfg.providers
