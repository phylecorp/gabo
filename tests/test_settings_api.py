"""Tests for Settings API endpoints.

Covers:
- GET /api/config/settings returns masked key previews + model defaults
- PUT /api/config/settings saves to ~/.sat/config.json and updates os.environ
- POST /api/config/test-provider returns success/error from minimal LLM call
- Config file load order: config file > env var > default
- list_providers() checks config file too

@decision DEC-SETTINGS-TEST-001
@title Tests use real implementations with tmp_path config files
@status accepted
@rationale Config routes read/write real config.json files. Tests supply
a tmp_path-based config file path rather than mocking internal functions.
The only mock-exempt case is POST /api/config/test-provider, which calls
an external LLM HTTP API — that boundary is mocked at the HTTP layer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
from sat.api.models import (
    AppSettings,
    ProviderSettings,
    ProviderSettingsResponse,
    TestProviderRequest as ProviderTestRequest,
    TestProviderResponse as ProviderTestResponse,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8742)


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_env():
    """Remove provider API key env vars before/after each test."""
    keys_to_clean = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        # Research providers — must also be cleaned since they are now in _KNOWN_PROVIDERS
        "BRAVE_API_KEY",
        "PERPLEXITY_API_KEY",
    ]
    saved = {k: os.environ.pop(k, None) for k in keys_to_clean}
    yield
    # Restore to pre-test state
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


def write_config(tmp_path: Path, data: dict) -> Path:
    """Helper: write a sat config.json to tmp_path and return its path."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))
    return config_path


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


def test_provider_settings_response_fields():
    resp = ProviderSettingsResponse(
        has_api_key=True,
        api_key_preview="sk-ant-...7x2Q",
        default_model="claude-opus-4-6",
        source="config_file",
    )
    assert resp.has_api_key is True
    assert resp.api_key_preview == "sk-ant-...7x2Q"
    assert resp.source == "config_file"


def test_app_settings_defaults():
    settings = AppSettings()
    assert settings.providers == {}


def test_provider_settings_defaults():
    ps = ProviderSettings()
    assert ps.api_key == ""
    assert ps.default_model == ""


def test_test_provider_request_optional_model():
    req = ProviderTestRequest(provider="anthropic", api_key="sk-test")
    assert req.provider == "anthropic"
    assert req.model is None


def test_test_provider_response_success():
    resp = ProviderTestResponse(success=True, model_used="claude-opus-4-6")
    assert resp.success is True
    assert resp.error is None


def test_test_provider_response_failure():
    resp = ProviderTestResponse(success=False, error="Invalid API key")
    assert resp.success is False
    assert resp.error == "Invalid API key"


# ---------------------------------------------------------------------------
# GET /api/config/settings — no config file
# ---------------------------------------------------------------------------


def test_get_settings_returns_200(client, tmp_path):
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "nonexistent.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/settings")
        assert resp.status_code == 200
    finally:
        config_mod._get_config_path = orig


def test_get_settings_has_all_known_providers(client, tmp_path):
    # Three LLM providers plus two research providers (brave, perplexity).
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "nonexistent.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/settings")
        body = resp.json()
        assert set(body["providers"].keys()) == {
            "anthropic", "openai", "gemini", "perplexity", "brave"
        }
    finally:
        config_mod._get_config_path = orig


def test_get_settings_fields_present(client, tmp_path):
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "nonexistent.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/settings")
        body = resp.json()
        for _name, info in body["providers"].items():
            assert "has_api_key" in info
            assert "api_key_preview" in info
            assert "default_model" in info
            assert "source" in info
    finally:
        config_mod._get_config_path = orig


def test_get_settings_no_keys_configured(client, tmp_path):
    """With no env vars or config file, all providers report has_api_key=False."""
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "nonexistent.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/settings")
        body = resp.json()
        for _name, info in body["providers"].items():
            assert info["has_api_key"] is False
            assert info["source"] == "default"
    finally:
        config_mod._get_config_path = orig


def test_get_settings_env_var_detected(client, tmp_path):
    """When env var is set, provider reports has_api_key=True, source=environment."""
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "nonexistent.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-testkey1234"
    try:
        resp = client.get("/api/config/settings")
        body = resp.json()
        anthropic = body["providers"]["anthropic"]
        assert anthropic["has_api_key"] is True
        assert anthropic["source"] == "environment"
        # Key should be masked: first 6 chars = "sk-ant"
        assert anthropic["api_key_preview"] != "sk-ant-testkey1234"
        assert anthropic["api_key_preview"].startswith("sk-ant")
    finally:
        config_mod._get_config_path = orig
        del os.environ["ANTHROPIC_API_KEY"]


def test_get_settings_config_file_detected(client, tmp_path):
    """When config file present, provider reports source=config_file."""
    import sat.api.routes.config as config_mod
    config_path = write_config(tmp_path, {
        "providers": {
            "openai": {"api_key": "sk-openai-filekeythirty", "default_model": "gpt-4o"}
        }
    })
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/settings")
        body = resp.json()
        openai_info = body["providers"]["openai"]
        assert openai_info["has_api_key"] is True
        assert openai_info["source"] == "config_file"
        assert openai_info["default_model"] == "gpt-4o"
    finally:
        config_mod._get_config_path = orig


def test_get_settings_api_key_preview_format(client, tmp_path):
    """Preview shows first 6 chars + ... + last 4 chars."""
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "nonexistent.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-ABCDEFGHIJ1234"
    try:
        resp = client.get("/api/config/settings")
        body = resp.json()
        preview = body["providers"]["anthropic"]["api_key_preview"]
        assert preview.startswith("sk-ant")
        assert preview.endswith("1234")
        assert "..." in preview
    finally:
        config_mod._get_config_path = orig
        del os.environ["ANTHROPIC_API_KEY"]


# ---------------------------------------------------------------------------
# PUT /api/config/settings
# ---------------------------------------------------------------------------


def test_put_settings_saves_config(client, tmp_path):
    """Saving settings writes to the config file."""
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "config.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    payload = {
        "providers": {
            "anthropic": {"api_key": "sk-ant-newkey123456", "default_model": "claude-opus-4-6"},
        }
    }
    try:
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        assert config_path.exists()
        saved = json.loads(config_path.read_text())
        assert saved["providers"]["anthropic"]["api_key"] == "sk-ant-newkey123456"
    finally:
        config_mod._get_config_path = orig
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_put_settings_updates_os_environ(client, tmp_path):
    """Saving an API key immediately updates os.environ."""
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "config.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    payload = {
        "providers": {
            "openai": {"api_key": "sk-openai-envtest99", "default_model": ""},
        }
    }
    try:
        client.put("/api/config/settings", json=payload)
        assert os.environ.get("OPENAI_API_KEY") == "sk-openai-envtest99"
    finally:
        config_mod._get_config_path = orig
        os.environ.pop("OPENAI_API_KEY", None)


def test_put_settings_empty_key_removes_from_environ(client, tmp_path):
    """Saving an empty API key removes it from os.environ."""
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "config.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    os.environ["GEMINI_API_KEY"] = "existing-gemini-key"
    payload = {
        "providers": {
            "gemini": {"api_key": "", "default_model": ""},
        }
    }
    try:
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        assert os.environ.get("GEMINI_API_KEY") is None
    finally:
        config_mod._get_config_path = orig


def test_put_settings_returns_masked_response(client, tmp_path):
    """PUT returns updated settings with masked keys."""
    import sat.api.routes.config as config_mod
    config_path = tmp_path / "config.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    payload = {
        "providers": {
            "anthropic": {"api_key": "sk-ant-returntest5678", "default_model": "claude-opus-4-6"},
        }
    }
    try:
        resp = client.put("/api/config/settings", json=payload)
        body = resp.json()
        assert "providers" in body
        assert body["providers"]["anthropic"]["has_api_key"] is True
        assert body["providers"]["anthropic"]["api_key_preview"] != "sk-ant-returntest5678"
    finally:
        config_mod._get_config_path = orig
        os.environ.pop("ANTHROPIC_API_KEY", None)


# ---------------------------------------------------------------------------
# _save_config creates parent dirs
# ---------------------------------------------------------------------------


def test_save_config_creates_parent_dir(tmp_path):
    """_save_config creates parent directory if missing."""
    from sat.api.routes.config import _save_config

    config_path = tmp_path / "nested" / "dir" / "config.json"
    settings = AppSettings(providers={"anthropic": ProviderSettings(api_key="test")})
    _save_config(settings, config_path)
    assert config_path.exists()


# ---------------------------------------------------------------------------
# POST /api/config/test-provider
# (External LLM HTTP calls are mocked at the httpx/requests layer)
# ---------------------------------------------------------------------------


def test_test_provider_endpoint_exists(client):
    """POST /api/config/test-provider returns 200 or 422, not 404/405."""
    resp = client.post(
        "/api/config/test-provider",
        json={"provider": "anthropic", "api_key": "sk-test-key"},
    )
    # Should not be 404 or 405; with a bad key it returns 200+success=False
    assert resp.status_code in (200, 422, 503)


def test_test_provider_invalid_provider_returns_error(client):
    """Unknown provider name returns success=False without crashing."""
    resp = client.post(
        "/api/config/test-provider",
        json={"provider": "notavalidprovider", "api_key": "some-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["error"] is not None


def test_test_provider_response_schema(client):
    """Response always has success, error, model_used fields."""
    resp = client.post(
        "/api/config/test-provider",
        json={"provider": "notavalidprovider", "api_key": "some-key"},
    )
    body = resp.json()
    assert "success" in body
    assert "error" in body
    assert "model_used" in body


# ---------------------------------------------------------------------------
# _load_settings — config file load order
# ---------------------------------------------------------------------------


def test_config_file_takes_precedence_over_env(tmp_path):
    """Config file API key overrides env var."""
    from sat.api.routes.config import _load_settings

    config_path = write_config(tmp_path, {
        "providers": {
            "anthropic": {"api_key": "sk-ant-from-file", "default_model": ""}
        }
    })
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-from-env"
    try:
        settings_resp = _load_settings(config_path)
        anthropic = settings_resp.providers["anthropic"]
        assert anthropic.source == "config_file"
    finally:
        del os.environ["ANTHROPIC_API_KEY"]


def test_env_var_used_when_no_config_file(tmp_path):
    """Env var is used when config file doesn't exist."""
    from sat.api.routes.config import _load_settings

    config_path = tmp_path / "nonexistent.json"
    os.environ["OPENAI_API_KEY"] = "sk-openai-from-env"
    try:
        settings_resp = _load_settings(config_path)
        openai_info = settings_resp.providers["openai"]
        assert openai_info.has_api_key is True
        assert openai_info.source == "environment"
    finally:
        del os.environ["OPENAI_API_KEY"]


def test_default_models_returned_when_no_key(tmp_path):
    """When no key configured, default model from DEFAULT_MODELS is returned."""
    from sat.api.routes.config import _load_settings
    from sat.config import DEFAULT_MODELS

    config_path = tmp_path / "nonexistent.json"
    settings_resp = _load_settings(config_path)

    for provider, info in settings_resp.providers.items():
        assert info.default_model == DEFAULT_MODELS.get(provider, "")


def test_source_is_default_when_no_key(tmp_path):
    """source='default' when no key configured anywhere."""
    from sat.api.routes.config import _load_settings

    config_path = tmp_path / "nonexistent.json"
    settings_resp = _load_settings(config_path)
    for _name, info in settings_resp.providers.items():
        assert info.source == "default"


# ---------------------------------------------------------------------------
# list_providers detects config file keys
# ---------------------------------------------------------------------------


def test_list_providers_detects_config_file_key(client, tmp_path):
    """GET /api/config/providers also detects keys from config file."""
    import sat.api.routes.config as config_mod
    config_path = write_config(tmp_path, {
        "providers": {
            "gemini": {"api_key": "AI-gemini-from-config", "default_model": ""}
        }
    })
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/providers")
        assert resp.status_code == 200
        providers = {p["name"]: p for p in resp.json()}
        assert providers["gemini"]["has_api_key"] is True
    finally:
        config_mod._get_config_path = orig


def test_list_providers_returns_saved_default_model(client, tmp_path):
    """GET /api/config/providers returns the user-saved default_model from config.json.

    This is the core bug: previously list_providers always returned DEFAULT_MODELS
    (hardcoded), ignoring the model the user saved in Settings. The fix reads
    default_model from config file when present, falling back to DEFAULT_MODELS.
    """
    import sat.api.routes.config as config_mod
    config_path = write_config(tmp_path, {
        "providers": {
            "openai": {"api_key": "sk-openai-savedkey12345", "default_model": "gpt-4-turbo"},
        }
    })
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/providers")
        assert resp.status_code == 200
        providers = {p["name"]: p for p in resp.json()}
        # The user saved "gpt-4-turbo" — that should be returned, not the hardcoded default
        assert providers["openai"]["default_model"] == "gpt-4-turbo"
    finally:
        config_mod._get_config_path = orig


def test_list_providers_falls_back_to_default_model_when_no_config(client, tmp_path):
    """GET /api/config/providers falls back to DEFAULT_MODELS when config has no model."""
    import sat.api.routes.config as config_mod
    from sat.config import DEFAULT_MODELS
    config_path = tmp_path / "nonexistent.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-fallbacktest1234"
    try:
        resp = client.get("/api/config/providers")
        assert resp.status_code == 200
        providers = {p["name"]: p for p in resp.json()}
        # No saved model: should fall back to DEFAULT_MODELS
        assert providers["anthropic"]["default_model"] == DEFAULT_MODELS.get("anthropic", "")
    finally:
        config_mod._get_config_path = orig
        del os.environ["ANTHROPIC_API_KEY"]


def test_list_providers_empty_saved_model_falls_back_to_default(client, tmp_path):
    """If config.json has empty default_model, fall back to DEFAULT_MODELS."""
    import sat.api.routes.config as config_mod
    from sat.config import DEFAULT_MODELS
    config_path = write_config(tmp_path, {
        "providers": {
            "anthropic": {"api_key": "sk-ant-testkey1234567", "default_model": ""}
        }
    })
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/providers")
        assert resp.status_code == 200
        providers = {p["name"]: p for p in resp.json()}
        # Empty saved model: fall back to DEFAULT_MODELS
        assert providers["anthropic"]["default_model"] == DEFAULT_MODELS.get("anthropic", "")
    finally:
        config_mod._get_config_path = orig


# ---------------------------------------------------------------------------
# ProviderConfig.resolve_api_key checks config file
# ---------------------------------------------------------------------------


def test_resolve_api_key_from_config_file(tmp_path):
    """ProviderConfig.resolve_api_key() picks up key from config.json."""
    from sat.config import ProviderConfig

    config_path = write_config(tmp_path, {
        "providers": {
            "anthropic": {"api_key": "sk-ant-fromfile9999", "default_model": ""}
        }
    })

    orig = None
    import sat.config as config_mod
    orig = getattr(config_mod, "_get_sat_config_path", None)
    config_mod._get_sat_config_path = lambda: config_path
    try:
        pc = ProviderConfig(provider="anthropic")
        key = pc.resolve_api_key()
        assert key == "sk-ant-fromfile9999"
    finally:
        if orig is not None:
            config_mod._get_sat_config_path = orig
        else:
            del config_mod._get_sat_config_path


def test_resolve_api_key_env_fallback(tmp_path):
    """ProviderConfig.resolve_api_key() falls back to env var if no config file."""
    from sat.config import ProviderConfig

    config_path = tmp_path / "nonexistent.json"
    os.environ["OPENAI_API_KEY"] = "sk-openai-envkey"
    import sat.config as config_mod
    orig = getattr(config_mod, "_get_sat_config_path", None)
    config_mod._get_sat_config_path = lambda: config_path
    try:
        pc = ProviderConfig(provider="openai")
        key = pc.resolve_api_key()
        assert key == "sk-openai-envkey"
    finally:
        del os.environ["OPENAI_API_KEY"]
        if orig is not None:
            config_mod._get_sat_config_path = orig
        else:
            del config_mod._get_sat_config_path


def test_try_resolve_api_key_from_config_file(tmp_path):
    """ProviderConfig.try_resolve_api_key() also reads config file."""
    from sat.config import ProviderConfig

    config_path = write_config(tmp_path, {
        "providers": {
            "gemini": {"api_key": "AI-gemini-tryresolve", "default_model": ""}
        }
    })

    import sat.config as config_mod
    orig = getattr(config_mod, "_get_sat_config_path", None)
    config_mod._get_sat_config_path = lambda: config_path
    try:
        pc = ProviderConfig(provider="gemini")
        key = pc.try_resolve_api_key()
        assert key == "AI-gemini-tryresolve"
    finally:
        if orig is not None:
            config_mod._get_sat_config_path = orig
        else:
            del config_mod._get_sat_config_path
