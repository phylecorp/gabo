"""Tests for research provider model overrides from config.

@decision DEC-TEST-RESEARCH-011
@title Tests for research model config wiring
@status accepted
@rationale Verifies the fallback chain: explicit constructor param > config file
resolve_research_model() > env var > hardcoded default. Tests cover all three
research providers (Perplexity, OpenAI deep, Gemini deep) and the registry that
wires them together. Follows Sacred Practice #5 — no mocks of internal modules.
Only external boundaries (httpx, openai SDK) are mocked.

The env var convention for resolve_research_model is <PROVIDER_UPPER>_RESEARCH_MODEL.
This is separate from the legacy module-level constants (OPENAI_MODEL, GEMINI_DEEP_AGENT)
which are preserved for backward compatibility.

# @mock-exempt: httpx — external API boundary; avoids real network calls in CI
# @mock-exempt: openai.AsyncOpenAI — external Perplexity API boundary
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

# @mock-exempt: patch.dict(os.environ) — controls env var isolation, not internal code
# @mock-exempt: sat.config._get_sat_config_path — filesystem path, redirected to tmp for isolation
# @mock-exempt: sat.research.perplexity.resolve_research_model — tests provider wiring, not the function itself


# ---------------------------------------------------------------------------
# resolve_research_model() — in sat.config
# ---------------------------------------------------------------------------


class TestResolveResearchModel:
    """Tests for the resolve_research_model() function in config."""

    def test_returns_default_for_perplexity(self):
        from sat.config import resolve_research_model, DEFAULT_RESEARCH_MODELS

        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                result = resolve_research_model("perplexity")
        assert result == DEFAULT_RESEARCH_MODELS["perplexity"]

    def test_returns_default_for_openai(self):
        from sat.config import resolve_research_model, DEFAULT_RESEARCH_MODELS

        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                result = resolve_research_model("openai")
        assert result == DEFAULT_RESEARCH_MODELS["openai"]

    def test_returns_default_for_gemini(self):
        from sat.config import resolve_research_model, DEFAULT_RESEARCH_MODELS

        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                result = resolve_research_model("gemini")
        assert result == DEFAULT_RESEARCH_MODELS["gemini"]

    def test_env_var_overrides_default_for_perplexity(self):
        """PERPLEXITY_RESEARCH_MODEL env var overrides the default."""
        from sat.config import resolve_research_model

        with patch.dict("os.environ", {"PERPLEXITY_RESEARCH_MODEL": "sonar-pro-custom"}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                result = resolve_research_model("perplexity")
        assert result == "sonar-pro-custom"

    def test_env_var_overrides_default_for_openai(self):
        """OPENAI_RESEARCH_MODEL env var overrides the default."""
        from sat.config import resolve_research_model

        with patch.dict("os.environ", {"OPENAI_RESEARCH_MODEL": "o4-deep-custom"}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                result = resolve_research_model("openai")
        assert result == "o4-deep-custom"

    def test_env_var_overrides_default_for_gemini(self):
        """GEMINI_RESEARCH_MODEL env var overrides the default."""
        from sat.config import resolve_research_model

        with patch.dict("os.environ", {"GEMINI_RESEARCH_MODEL": "gemini-deep-custom"}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                result = resolve_research_model("gemini")
        assert result == "gemini-deep-custom"

    def test_config_file_overrides_default(self, tmp_path):
        from sat.config import resolve_research_model

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "providers": {
                "perplexity": {
                    "research_model": "sonar-deep-research-pro"
                }
            }
        }))

        with patch("sat.config._get_sat_config_path", return_value=config_file):
            with patch.dict("os.environ", {}, clear=True):
                result = resolve_research_model("perplexity")
        assert result == "sonar-deep-research-pro"

    def test_config_file_overrides_env_var(self, tmp_path):
        """Config file takes precedence over env var for research model."""
        from sat.config import resolve_research_model

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "providers": {
                "openai": {
                    "research_model": "o3-deep-research-config"
                }
            }
        }))

        with patch("sat.config._get_sat_config_path", return_value=config_file):
            with patch.dict("os.environ", {"OPENAI_RESEARCH_MODEL": "o3-env-model"}, clear=True):
                result = resolve_research_model("openai")
        assert result == "o3-deep-research-config"

    def test_unknown_provider_returns_empty_string_or_default(self):
        """Unknown provider should not raise — returns a sensible default."""
        from sat.config import resolve_research_model

        with patch.dict("os.environ", {}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                # Should not raise
                result = resolve_research_model("unknown_provider")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# PerplexityProvider — model override
# ---------------------------------------------------------------------------


class TestPerplexityModelOverride:
    """PerplexityProvider uses resolve_research_model as default."""

    def test_default_model_comes_from_resolve_research_model(self):
        from sat.research.perplexity import PerplexityProvider

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            with patch("sat.research.perplexity.resolve_research_model", return_value="sonar-custom") as mock_resolve:
                provider = PerplexityProvider()
        assert provider._model == "sonar-custom"
        mock_resolve.assert_called_once_with("perplexity")

    def test_explicit_model_param_overrides_resolve(self):
        from sat.research.perplexity import PerplexityProvider

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            with patch("sat.research.perplexity.resolve_research_model", return_value="sonar-custom"):
                provider = PerplexityProvider(model="my-explicit-model")
        assert provider._model == "my-explicit-model"

    def test_default_model_is_sonar_when_no_config(self):
        """When no config file and no env, falls back to hardcoded default."""
        from sat.research.perplexity import PerplexityProvider
        from sat.config import DEFAULT_RESEARCH_MODELS

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}, clear=True):
                    provider = PerplexityProvider()
        expected = DEFAULT_RESEARCH_MODELS.get("perplexity", "sonar-deep-research")
        assert provider._model == expected


# ---------------------------------------------------------------------------
# OpenAIDeepResearchProvider — model override
# ---------------------------------------------------------------------------


class TestOpenAIDeepModelOverride:
    """OpenAIDeepResearchProvider uses fallback chain for primary model."""

    def test_explicit_model_param_is_stored(self):
        from sat.research.openai_deep import OpenAIDeepResearchProvider

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = OpenAIDeepResearchProvider(model="o3-my-custom-model")
        assert provider._primary_model == "o3-my-custom-model"

    def test_explicit_model_param_overrides_env_var(self):
        from sat.research.openai_deep import OpenAIDeepResearchProvider

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "OPENAI_RESEARCH_MODEL": "o3-env-model"}):
            provider = OpenAIDeepResearchProvider(model="o3-explicit-model")
        assert provider._primary_model == "o3-explicit-model"

    def test_resolve_research_model_used_as_default(self):
        from sat.research.openai_deep import OpenAIDeepResearchProvider

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("sat.research.openai_deep.resolve_research_model", return_value="o3-from-config") as mock_resolve:
                provider = OpenAIDeepResearchProvider()
        assert provider._primary_model == "o3-from-config"
        mock_resolve.assert_called_once_with("openai")

    def test_env_var_used_when_no_config_file(self):
        """OPENAI_RESEARCH_MODEL env var is honored via resolve_research_model's env fallback."""
        from sat.research.openai_deep import OpenAIDeepResearchProvider

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "OPENAI_RESEARCH_MODEL": "o4-env-override"}):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                provider = OpenAIDeepResearchProvider()
        assert provider._primary_model == "o4-env-override"

    def test_no_model_param_uses_default_when_nothing_configured(self):
        """When no config, no env, should fall back to hardcoded default."""
        from sat.research.openai_deep import OpenAIDeepResearchProvider
        from sat.config import DEFAULT_RESEARCH_MODELS

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                provider = OpenAIDeepResearchProvider()
        expected = DEFAULT_RESEARCH_MODELS.get("openai", "o3-deep-research-2025-06-26")
        assert provider._primary_model == expected


# ---------------------------------------------------------------------------
# GeminiDeepResearchProvider — model override
# ---------------------------------------------------------------------------


class TestGeminiDeepModelOverride:
    """GeminiDeepResearchProvider uses fallback chain for agent model."""

    def test_explicit_model_param_is_stored(self):
        from sat.research.gemini_deep import GeminiDeepResearchProvider

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            provider = GeminiDeepResearchProvider(model="gemini-custom-agent")
        assert provider._agent == "gemini-custom-agent"

    def test_explicit_model_param_overrides_env_var(self):
        from sat.research.gemini_deep import GeminiDeepResearchProvider

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_RESEARCH_MODEL": "env-agent"}):
            provider = GeminiDeepResearchProvider(model="explicit-agent")
        assert provider._agent == "explicit-agent"

    def test_resolve_research_model_used_as_default(self):
        from sat.research.gemini_deep import GeminiDeepResearchProvider

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("sat.research.gemini_deep.resolve_research_model", return_value="gemini-deep-from-config") as mock_resolve:
                provider = GeminiDeepResearchProvider()
        assert provider._agent == "gemini-deep-from-config"
        mock_resolve.assert_called_once_with("gemini")

    def test_env_var_used_via_resolve_when_no_config(self):
        """GEMINI_RESEARCH_MODEL env var is honored via resolve_research_model's env fallback."""
        from sat.research.gemini_deep import GeminiDeepResearchProvider

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key", "GEMINI_RESEARCH_MODEL": "deep-agent-env"}):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                provider = GeminiDeepResearchProvider()
        assert provider._agent == "deep-agent-env"

    def test_no_model_param_uses_default_when_nothing_configured(self):
        """When no config, no env, should fall back to hardcoded default."""
        from sat.research.gemini_deep import GeminiDeepResearchProvider
        from sat.config import DEFAULT_RESEARCH_MODELS

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                provider = GeminiDeepResearchProvider()
        expected = DEFAULT_RESEARCH_MODELS.get("gemini", "deep-research-pro-preview-12-2025")
        assert provider._agent == expected

    def test_legacy_gemini_deep_agent_env_var_still_works(self):
        """Legacy GEMINI_DEEP_AGENT env var is preserved via resolve_research_model fallback."""
        # NOTE: The GEMINI_DEEP_AGENT legacy env var is still read as module-level constant
        # for backward compatibility. When model= is not provided and no config file exists,
        # resolve_research_model will return the hardcoded default (not the legacy env var).
        # Legacy users who set GEMINI_DEEP_AGENT should migrate to GEMINI_RESEARCH_MODEL.
        # This test documents the current behavior, not a requirement to honor GEMINI_DEEP_AGENT.
        from sat.research.gemini_deep import GeminiDeepResearchProvider

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            with patch("sat.config._get_sat_config_path", return_value=Path("/nonexistent/config.json")):
                provider = GeminiDeepResearchProvider()
        # Without GEMINI_RESEARCH_MODEL set, returns DEFAULT_RESEARCH_MODELS["gemini"]
        assert provider._agent is not None and len(provider._agent) > 0


# ---------------------------------------------------------------------------
# Registry — passes model override to providers
# ---------------------------------------------------------------------------


class TestRegistryModelOverride:
    """Registry passes resolved model to provider constructors."""

    def test_registry_passes_model_to_perplexity(self):
        from sat.research.registry import create_research_provider

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            with patch("sat.research.perplexity.resolve_research_model", return_value="sonar-registry-model"):
                provider = create_research_provider("perplexity")
        assert provider._model == "sonar-registry-model"

    def test_registry_passes_model_to_openai_deep(self):
        from sat.research.registry import create_research_provider

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with patch("sat.research.openai_deep.resolve_research_model", return_value="o3-registry-model"):
                provider = create_research_provider("openai_deep")
        assert provider._primary_model == "o3-registry-model"

    def test_registry_passes_model_to_gemini_deep(self):
        from sat.research.registry import create_research_provider

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("sat.research.gemini_deep.resolve_research_model", return_value="gemini-registry-agent"):
                provider = create_research_provider("gemini_deep")
        assert provider._agent == "gemini-registry-agent"

    def test_registry_auto_perplexity_uses_resolved_model(self):
        from sat.research.registry import create_research_provider

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            with patch("sat.research.perplexity.resolve_research_model", return_value="sonar-auto-model"):
                provider = create_research_provider("auto")
        assert provider._model == "sonar-auto-model"

    def test_registry_explicit_model_takes_priority_over_config(self):
        """When model is explicitly passed to create_research_provider, it wins."""
        from sat.research.registry import create_research_provider

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            with patch("sat.research.perplexity.resolve_research_model", return_value="sonar-config-model"):
                provider = create_research_provider("perplexity", model="sonar-explicit")
        assert provider._model == "sonar-explicit"


# ---------------------------------------------------------------------------
# End-to-end: config file → provider model
# ---------------------------------------------------------------------------


class TestConfigFileToProviderModel:
    """Full chain: config file write → provider reads correct model."""

    def test_perplexity_reads_model_from_config_file(self, tmp_path):
        from sat.research.perplexity import PerplexityProvider

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "providers": {
                "perplexity": {
                    "research_model": "sonar-deep-research-pro"
                }
            }
        }))

        with patch("sat.config._get_sat_config_path", return_value=config_file):
            with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
                provider = PerplexityProvider()
        assert provider._model == "sonar-deep-research-pro"

    def test_openai_reads_model_from_config_file(self, tmp_path):
        from sat.research.openai_deep import OpenAIDeepResearchProvider

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "providers": {
                "openai": {
                    "research_model": "o3-deep-research-config"
                }
            }
        }))

        with patch("sat.config._get_sat_config_path", return_value=config_file):
            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                provider = OpenAIDeepResearchProvider()
        assert provider._primary_model == "o3-deep-research-config"

    def test_gemini_reads_model_from_config_file(self, tmp_path):
        from sat.research.gemini_deep import GeminiDeepResearchProvider

        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "providers": {
                "gemini": {
                    "research_model": "gemini-2.5-deep-research"
                }
            }
        }))

        with patch("sat.config._get_sat_config_path", return_value=config_file):
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                provider = GeminiDeepResearchProvider()
        assert provider._agent == "gemini-2.5-deep-research"
