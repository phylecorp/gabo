"""Tests for research model config storage and resolution (issue #10).

Covers:
- DEFAULT_RESEARCH_MODELS constant in sat.config
- _load_config_file_research_model reads research_model from config.json
- resolve_research_model() follows the fallback chain:
    config.json research_model > env var > DEFAULT_RESEARCH_MODELS
- ProviderSettings and ProviderSettingsResponse include research_model field
- PUT /api/config/settings accepts and persists research_model
- GET /api/config/settings returns research_model from config file
- Backwards compatibility: config.json without research_model still works

@decision DEC-CFG-004
@title resolve_research_model follows the same chain as resolve_model
@status accepted
@rationale Research providers (perplexity, openai, gemini) use different models
than analysis providers. Rather than overloading the existing DEFAULT_MODELS dict,
a separate DEFAULT_RESEARCH_MODELS dict keeps the two concerns separate and avoids
the risk of mixing analysis model defaults with research model defaults. The
resolution chain mirrors resolve_model: config file > env var > built-in default.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

import sat.config as config_mod
import sat.api.routes.config as api_config_mod
from sat.api.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_config(tmp_path, data: dict):
    """Write a sat config.json and return its path."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))
    return config_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8744)


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def tmp_config_path(tmp_path, monkeypatch):
    """Redirect config path to a temp file for both sat.config and api routes."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_file)
    monkeypatch.setattr(api_config_mod, "_get_config_path", lambda: config_file)
    return config_file


@pytest.fixture(autouse=True)
def clean_research_env():
    """Remove research model env vars before/after each test."""
    keys = [
        "PERPLEXITY_RESEARCH_MODEL",
        "OPENAI_RESEARCH_MODEL",
        "GEMINI_RESEARCH_MODEL",
    ]
    saved = {k: os.environ.pop(k, None) for k in keys}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


# ---------------------------------------------------------------------------
# DEFAULT_RESEARCH_MODELS constant
# ---------------------------------------------------------------------------


class TestDefaultResearchModels:
    def test_constant_exists(self):
        from sat.config import DEFAULT_RESEARCH_MODELS
        assert isinstance(DEFAULT_RESEARCH_MODELS, dict)

    def test_perplexity_default(self):
        from sat.config import DEFAULT_RESEARCH_MODELS
        assert DEFAULT_RESEARCH_MODELS["perplexity"] == "sonar-deep-research"

    def test_openai_default(self):
        from sat.config import DEFAULT_RESEARCH_MODELS
        assert DEFAULT_RESEARCH_MODELS["openai"] == "o3-deep-research-2025-06-26"

    def test_gemini_default(self):
        from sat.config import DEFAULT_RESEARCH_MODELS
        assert DEFAULT_RESEARCH_MODELS["gemini"] == "deep-research-pro-preview-12-2025"


# ---------------------------------------------------------------------------
# _load_config_file_research_model
# ---------------------------------------------------------------------------


class TestLoadConfigFileResearchModel:
    def test_returns_none_if_no_config_file(self, tmp_path):
        config_path = tmp_path / "nonexistent.json"
        config_mod._get_sat_config_path = lambda: config_path
        result = config_mod._load_config_file_research_model("perplexity")
        assert result is None

    def test_returns_none_if_provider_missing(self, tmp_path, monkeypatch):
        config_path = write_config(tmp_path, {
            "providers": {
                "openai": {"api_key": "sk-test", "default_model": "o3"}
            }
        })
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        result = config_mod._load_config_file_research_model("perplexity")
        assert result is None

    def test_returns_none_if_research_model_field_missing(self, tmp_path, monkeypatch):
        config_path = write_config(tmp_path, {
            "providers": {
                "openai": {"api_key": "sk-test", "default_model": "o3"}
            }
        })
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        result = config_mod._load_config_file_research_model("openai")
        assert result is None

    def test_returns_research_model_when_present(self, tmp_path, monkeypatch):
        config_path = write_config(tmp_path, {
            "providers": {
                "openai": {
                    "api_key": "sk-test",
                    "default_model": "o3",
                    "research_model": "o3-deep-research-2025-06-26",
                }
            }
        })
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        result = config_mod._load_config_file_research_model("openai")
        assert result == "o3-deep-research-2025-06-26"

    def test_returns_none_if_research_model_empty_string(self, tmp_path, monkeypatch):
        config_path = write_config(tmp_path, {
            "providers": {
                "perplexity": {
                    "api_key": "pplx-test",
                    "research_model": "",
                }
            }
        })
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        result = config_mod._load_config_file_research_model("perplexity")
        assert result is None

    def test_handles_malformed_json(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.json"
        config_path.write_text("this is not valid json {{{")
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        # Should not raise; returns None on parse error
        result = config_mod._load_config_file_research_model("openai")
        assert result is None


# ---------------------------------------------------------------------------
# resolve_research_model fallback chain
# ---------------------------------------------------------------------------


class TestResolveResearchModel:
    def test_returns_config_file_value_when_present(self, tmp_path, monkeypatch):
        """Config file research_model has highest priority."""
        config_path = write_config(tmp_path, {
            "providers": {
                "openai": {
                    "research_model": "o3-deep-research-2025-06-26",
                }
            }
        })
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        monkeypatch.setenv("OPENAI_RESEARCH_MODEL", "env-model-should-be-ignored")
        result = config_mod.resolve_research_model("openai")
        assert result == "o3-deep-research-2025-06-26"

    def test_falls_back_to_env_var_when_no_config_file(self, tmp_path, monkeypatch):
        """Env var used when no research_model in config file."""
        config_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        monkeypatch.setenv("OPENAI_RESEARCH_MODEL", "o3-deep-research-env")
        result = config_mod.resolve_research_model("openai")
        assert result == "o3-deep-research-env"

    def test_falls_back_to_env_var_when_research_model_not_in_config(
        self, tmp_path, monkeypatch
    ):
        """Env var used when config exists but research_model field is absent."""
        config_path = write_config(tmp_path, {
            "providers": {
                "openai": {"api_key": "sk-test", "default_model": "o3"}
            }
        })
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        monkeypatch.setenv("OPENAI_RESEARCH_MODEL", "o3-env-fallback")
        result = config_mod.resolve_research_model("openai")
        assert result == "o3-env-fallback"

    def test_falls_back_to_default_when_no_config_and_no_env(
        self, tmp_path, monkeypatch
    ):
        """DEFAULT_RESEARCH_MODELS used when nothing else is configured."""
        config_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        result = config_mod.resolve_research_model("perplexity")
        assert result == "sonar-deep-research"

    def test_falls_back_to_default_for_gemini(self, tmp_path, monkeypatch):
        config_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        result = config_mod.resolve_research_model("gemini")
        assert result == "deep-research-pro-preview-12-2025"

    def test_falls_back_to_default_for_openai(self, tmp_path, monkeypatch):
        config_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        result = config_mod.resolve_research_model("openai")
        assert result == "o3-deep-research-2025-06-26"

    def test_unknown_provider_returns_empty_string(self, tmp_path, monkeypatch):
        """Unknown provider (not in DEFAULT_RESEARCH_MODELS) returns empty string."""
        config_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        result = config_mod.resolve_research_model("unknownprovider")
        assert result == ""

    def test_perplexity_config_overrides_env_and_default(self, tmp_path, monkeypatch):
        """Full priority chain: config > env > default for perplexity."""
        config_path = write_config(tmp_path, {
            "providers": {
                "perplexity": {
                    "api_key": "pplx-test",
                    "research_model": "sonar-pro",
                }
            }
        })
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        monkeypatch.setenv("PERPLEXITY_RESEARCH_MODEL", "sonar-env")
        result = config_mod.resolve_research_model("perplexity")
        assert result == "sonar-pro"


# ---------------------------------------------------------------------------
# ProviderSettings model — research_model field
# ---------------------------------------------------------------------------


class TestProviderSettingsModel:
    def test_has_research_model_field(self):
        from sat.api.models import ProviderSettings
        ps = ProviderSettings()
        assert hasattr(ps, "research_model")

    def test_research_model_defaults_to_empty_string(self):
        from sat.api.models import ProviderSettings
        ps = ProviderSettings()
        assert ps.research_model == ""

    def test_research_model_can_be_set(self):
        from sat.api.models import ProviderSettings
        ps = ProviderSettings(research_model="o3-deep-research-2025-06-26")
        assert ps.research_model == "o3-deep-research-2025-06-26"

    def test_backwards_compat_no_research_model(self):
        """Existing code that doesn't pass research_model still works."""
        from sat.api.models import ProviderSettings
        ps = ProviderSettings(api_key="sk-test", default_model="o3")
        assert ps.api_key == "sk-test"
        assert ps.default_model == "o3"
        assert ps.research_model == ""


# ---------------------------------------------------------------------------
# ProviderSettingsResponse model — research_model field
# ---------------------------------------------------------------------------


class TestProviderSettingsResponseModel:
    def test_has_research_model_field(self):
        from sat.api.models import ProviderSettingsResponse
        resp = ProviderSettingsResponse(has_api_key=False)
        assert hasattr(resp, "research_model")

    def test_research_model_defaults_to_empty_string(self):
        from sat.api.models import ProviderSettingsResponse
        resp = ProviderSettingsResponse(has_api_key=False)
        assert resp.research_model == ""

    def test_research_model_can_be_set(self):
        from sat.api.models import ProviderSettingsResponse
        resp = ProviderSettingsResponse(
            has_api_key=True,
            research_model="sonar-deep-research",
            source="config_file",
        )
        assert resp.research_model == "sonar-deep-research"


# ---------------------------------------------------------------------------
# GET /api/config/settings — returns research_model from config file
# ---------------------------------------------------------------------------


class TestGetSettingsResearchModel:
    def test_research_model_field_in_response(self, client, tmp_config_path):
        resp = client.get("/api/config/settings")
        assert resp.status_code == 200
        providers = resp.json()["providers"]
        for name in ["anthropic", "openai", "gemini", "perplexity", "brave"]:
            assert "research_model" in providers[name]

    def test_research_model_from_config_file_returned(self, client, tmp_config_path):
        """GET /api/config/settings returns research_model saved in config file."""
        tmp_config_path.write_text(json.dumps({
            "providers": {
                "openai": {
                    "api_key": "sk-openai-test123",
                    "default_model": "o3",
                    "research_model": "o3-deep-research-2025-06-26",
                }
            }
        }))
        resp = client.get("/api/config/settings")
        assert resp.status_code == 200
        openai_info = resp.json()["providers"]["openai"]
        assert openai_info["research_model"] == "o3-deep-research-2025-06-26"

    def test_research_model_empty_when_not_in_config(self, client, tmp_config_path):
        """When config.json has no research_model, field returns empty string."""
        tmp_config_path.write_text(json.dumps({
            "providers": {
                "openai": {
                    "api_key": "sk-openai-test123",
                    "default_model": "o3",
                }
            }
        }))
        resp = client.get("/api/config/settings")
        openai_info = resp.json()["providers"]["openai"]
        assert openai_info["research_model"] == ""

    def test_no_config_file_research_model_empty(self, client, tmp_config_path):
        """No config file → research_model is empty string."""
        # tmp_config_path fixture points to non-existent file
        resp = client.get("/api/config/settings")
        for name, info in resp.json()["providers"].items():
            assert info["research_model"] == ""


# ---------------------------------------------------------------------------
# PUT /api/config/settings — accepts and persists research_model
# ---------------------------------------------------------------------------


class TestUpdateSettingsResearchModel:
    def test_save_research_model_persists_to_config(self, client, tmp_config_path):
        """PUT /api/config/settings with research_model writes it to config.json."""
        payload = {
            "providers": {
                "openai": {
                    "api_key": "sk-openai-test123456",
                    "default_model": "o3",
                    "research_model": "o3-deep-research-2025-06-26",
                }
            }
        }
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        saved = json.loads(tmp_config_path.read_text())
        assert saved["providers"]["openai"]["research_model"] == "o3-deep-research-2025-06-26"

    def test_save_perplexity_research_model(self, client, tmp_config_path):
        os.environ.pop("PERPLEXITY_API_KEY", None)
        try:
            payload = {
                "providers": {
                    "perplexity": {
                        "api_key": "pplx-testkey123456",
                        "default_model": "sonar-deep-research",
                        "research_model": "sonar-deep-research",
                    }
                }
            }
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            saved = json.loads(tmp_config_path.read_text())
            assert saved["providers"]["perplexity"]["research_model"] == "sonar-deep-research"
        finally:
            os.environ.pop("PERPLEXITY_API_KEY", None)

    def test_save_without_research_model_preserves_defaults(self, client, tmp_config_path):
        """PUT without research_model still saves correctly; field omitted or empty."""
        payload = {
            "providers": {
                "openai": {
                    "api_key": "sk-openai-test123456",
                    "default_model": "o3",
                }
            }
        }
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        saved = json.loads(tmp_config_path.read_text())
        # research_model may be absent or empty; either is acceptable
        openai_data = saved["providers"]["openai"]
        assert openai_data.get("research_model", "") == ""

    def test_save_response_includes_research_model(self, client, tmp_config_path):
        """PUT response includes research_model in providers."""
        payload = {
            "providers": {
                "openai": {
                    "api_key": "sk-openai-test123456",
                    "default_model": "o3",
                    "research_model": "o3-deep-research-2025-06-26",
                }
            }
        }
        resp = client.put("/api/config/settings", json=payload)
        body = resp.json()
        openai_info = body["providers"]["openai"]
        assert openai_info["research_model"] == "o3-deep-research-2025-06-26"

    def test_existing_config_preserved_when_saving_research_model(
        self, client, tmp_config_path
    ):
        """Saving research_model for one provider doesn't disturb other providers."""
        # Pre-populate config with two providers
        tmp_config_path.write_text(json.dumps({
            "providers": {
                "anthropic": {"api_key": "sk-ant-existing", "default_model": "claude-opus-4-6"},
                "openai": {"api_key": "sk-openai-existing", "default_model": "o3"},
            }
        }))
        # Save research_model only for openai
        payload = {
            "providers": {
                "openai": {
                    "api_key": "sk-openai-existing",
                    "default_model": "o3",
                    "research_model": "o3-deep-research-2025-06-26",
                }
            }
        }
        os.environ.pop("OPENAI_API_KEY", None)
        try:
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            saved = json.loads(tmp_config_path.read_text())
            # anthropic entry must still be present
            assert saved["providers"]["anthropic"]["api_key"] == "sk-ant-existing"
            # openai research_model persisted
            assert saved["providers"]["openai"]["research_model"] == "o3-deep-research-2025-06-26"
        finally:
            os.environ.pop("OPENAI_API_KEY", None)

    def test_round_trip_research_model(self, client, tmp_config_path):
        """Research model saved via PUT is returned unchanged via GET."""
        os.environ.pop("OPENAI_API_KEY", None)
        try:
            payload = {
                "providers": {
                    "openai": {
                        "api_key": "sk-openai-roundtrip123",
                        "default_model": "o3",
                        "research_model": "o3-deep-research-2025-06-26",
                    }
                }
            }
            client.put("/api/config/settings", json=payload)
            get_resp = client.get("/api/config/settings")
            openai_info = get_resp.json()["providers"]["openai"]
            assert openai_info["research_model"] == "o3-deep-research-2025-06-26"
        finally:
            os.environ.pop("OPENAI_API_KEY", None)


# ---------------------------------------------------------------------------
# Backwards compatibility — configs without research_model still work
# ---------------------------------------------------------------------------


class TestBackwardsCompatibility:
    def test_old_config_without_research_model_loads_ok(
        self, client, tmp_config_path
    ):
        """Config files without research_model field still parse successfully."""
        tmp_config_path.write_text(json.dumps({
            "providers": {
                "anthropic": {"api_key": "sk-ant-legacy", "default_model": "claude-opus-4-6"},
                "openai": {"api_key": "sk-openai-legacy", "default_model": "o3"},
            }
        }))
        resp = client.get("/api/config/settings")
        assert resp.status_code == 200
        providers = resp.json()["providers"]
        assert providers["anthropic"]["has_api_key"] is True
        assert providers["openai"]["has_api_key"] is True

    def test_old_config_research_model_defaults_to_empty(
        self, client, tmp_config_path
    ):
        """Old config → research_model in response is empty string, not error."""
        tmp_config_path.write_text(json.dumps({
            "providers": {
                "openai": {"api_key": "sk-openai-legacy", "default_model": "o3"},
            }
        }))
        resp = client.get("/api/config/settings")
        openai_info = resp.json()["providers"]["openai"]
        assert openai_info["research_model"] == ""

    def test_resolve_research_model_works_without_config_file(
        self, tmp_path, monkeypatch
    ):
        """resolve_research_model works when config file doesn't exist."""
        config_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(config_mod, "_get_sat_config_path", lambda: config_path)
        # Should not raise; returns default
        result = config_mod.resolve_research_model("perplexity")
        assert result == "sonar-deep-research"

    def test_put_settings_without_research_model_field_accepted(
        self, client, tmp_config_path
    ):
        """PUT with no research_model is accepted (field is optional)."""
        payload = {
            "providers": {
                "anthropic": {
                    "api_key": "sk-ant-nomodel",
                    "default_model": "claude-opus-4-6",
                }
            }
        }
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
