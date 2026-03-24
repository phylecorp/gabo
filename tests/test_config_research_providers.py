"""Tests for Brave and Perplexity research provider support in config routes.

@decision DEC-TEST-CONFIG-RESEARCH-001
@title Tests verify research providers are listed, loaded, saved, and connection-tested
@status accepted
@rationale Brave and Perplexity are web-research providers (not LLM providers) that need
API key management via the Settings UI. These tests verify:
- Both providers appear in _KNOWN_PROVIDERS
- Both providers have entries in _PROVIDER_KEY_ENVS and PROVIDER_API_KEY_ENVS
- GET /api/config/settings returns entries for brave and perplexity
- PUT /api/config/settings persists brave/perplexity keys correctly
- POST /api/config/test-provider handles brave (httpx) and perplexity (openai compat)
- Unknown providers still return success=False with a clear error message

Tests use real FastAPI TestClient and real config path monkey-patching — no mocks
of internal modules. The only mocked boundaries are httpx.get (Brave Search HTTP API)
and openai.OpenAI (Perplexity's OpenAI-compatible API), both of which are external
third-party service calls that require live network access and real credentials.

# @mock-exempt: httpx.get — external Brave Search HTTP API call (api.search.brave.com);
#   real calls would require a paid Brave API key and network access in CI
# @mock-exempt: openai.OpenAI — external Perplexity API call (api.perplexity.ai);
#   Perplexity uses OpenAI-compatible wire protocol but is a third-party service
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
import sat.api.routes.config as config_mod
from sat.config import PROVIDER_API_KEY_ENVS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8743)


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    """Redirect config path to a temp file for isolation."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "_get_config_path", lambda: config_file)
    return config_file


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestKnownProviders:
    def test_brave_in_known_providers(self):
        assert "brave" in config_mod._KNOWN_PROVIDERS

    def test_perplexity_in_known_providers(self):
        assert "perplexity" in config_mod._KNOWN_PROVIDERS

    def test_all_original_providers_still_present(self):
        for p in ("anthropic", "openai", "gemini"):
            assert p in config_mod._KNOWN_PROVIDERS

    def test_brave_in_provider_key_envs(self):
        assert config_mod._PROVIDER_KEY_ENVS.get("brave") == "BRAVE_API_KEY"

    def test_perplexity_in_provider_key_envs(self):
        assert config_mod._PROVIDER_KEY_ENVS.get("perplexity") == "PERPLEXITY_API_KEY"


class TestGlobalProviderApiKeyEnvs:
    """PROVIDER_API_KEY_ENVS in sat.config must include research providers."""

    def test_brave_in_global_envs(self):
        assert PROVIDER_API_KEY_ENVS.get("brave") == "BRAVE_API_KEY"

    def test_perplexity_in_global_envs(self):
        assert PROVIDER_API_KEY_ENVS.get("perplexity") == "PERPLEXITY_API_KEY"


# ---------------------------------------------------------------------------
# GET /api/config/settings — returns providers including brave & perplexity
# ---------------------------------------------------------------------------


class TestGetSettingsResearchProviders:
    def test_brave_in_settings_response(self, client, tmp_config):
        resp = client.get("/api/config/settings")
        assert resp.status_code == 200
        providers = resp.json()["providers"]
        assert "brave" in providers

    def test_perplexity_in_settings_response(self, client, tmp_config):
        resp = client.get("/api/config/settings")
        assert resp.status_code == 200
        providers = resp.json()["providers"]
        assert "perplexity" in providers

    def test_brave_has_expected_shape(self, client, tmp_config):
        resp = client.get("/api/config/settings")
        brave = resp.json()["providers"]["brave"]
        assert "has_api_key" in brave
        assert "api_key_preview" in brave
        assert "default_model" in brave
        assert "source" in brave

    def test_brave_no_key_by_default(self, client, tmp_config, monkeypatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        resp = client.get("/api/config/settings")
        brave = resp.json()["providers"]["brave"]
        assert brave["has_api_key"] is False

    def test_brave_env_key_detected(self, client, tmp_config, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "bsearch-abcdefghij1234")
        resp = client.get("/api/config/settings")
        brave = resp.json()["providers"]["brave"]
        assert brave["has_api_key"] is True
        assert brave["source"] == "environment"

    def test_perplexity_env_key_detected(self, client, tmp_config, monkeypatch):
        monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-abcdefghij1234")
        resp = client.get("/api/config/settings")
        perplexity = resp.json()["providers"]["perplexity"]
        assert perplexity["has_api_key"] is True
        assert perplexity["source"] == "environment"


# ---------------------------------------------------------------------------
# PUT /api/config/settings — save brave & perplexity keys
# ---------------------------------------------------------------------------


class TestUpdateSettingsResearchProviders:
    def test_save_brave_key_persists(self, client, tmp_config):
        os.environ.pop("BRAVE_API_KEY", None)
        try:
            payload = {
                "providers": {
                    "brave": {"api_key": "bsearch-testkey12345", "default_model": ""},
                }
            }
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            data = json.loads(tmp_config.read_text())
            assert data["providers"]["brave"]["api_key"] == "bsearch-testkey12345"
        finally:
            os.environ.pop("BRAVE_API_KEY", None)

    def test_save_perplexity_key_persists(self, client, tmp_config):
        os.environ.pop("PERPLEXITY_API_KEY", None)
        try:
            payload = {
                "providers": {
                    "perplexity": {
                        "api_key": "pplx-testkey12345",
                        "default_model": "sonar-deep-research",
                    },
                }
            }
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            data = json.loads(tmp_config.read_text())
            assert data["providers"]["perplexity"]["api_key"] == "pplx-testkey12345"
        finally:
            os.environ.pop("PERPLEXITY_API_KEY", None)

    def test_save_brave_key_sets_environ(self, client, tmp_config):
        # Use try/finally to ensure env var cleanup even when _apply_to_environ
        # writes to os.environ directly (bypasses monkeypatch teardown).
        os.environ.pop("BRAVE_API_KEY", None)
        try:
            payload = {
                "providers": {
                    "brave": {"api_key": "bsearch-env12345678", "default_model": ""},
                }
            }
            client.put("/api/config/settings", json=payload)
            assert os.environ.get("BRAVE_API_KEY") == "bsearch-env12345678"
        finally:
            os.environ.pop("BRAVE_API_KEY", None)

    def test_save_perplexity_key_sets_environ(self, client, tmp_config):
        # Same pattern: explicit cleanup so env leakage doesn't affect other tests.
        os.environ.pop("PERPLEXITY_API_KEY", None)
        try:
            payload = {
                "providers": {
                    "perplexity": {"api_key": "pplx-env12345678", "default_model": ""},
                }
            }
            client.put("/api/config/settings", json=payload)
            assert os.environ.get("PERPLEXITY_API_KEY") == "pplx-env12345678"
        finally:
            os.environ.pop("PERPLEXITY_API_KEY", None)

    def test_save_brave_response_shows_masked_key(self, client, tmp_config):
        os.environ.pop("BRAVE_API_KEY", None)
        try:
            payload = {
                "providers": {
                    "brave": {"api_key": "bsearch-testkey12345", "default_model": ""},
                }
            }
            resp = client.put("/api/config/settings", json=payload)
            brave = resp.json()["providers"]["brave"]
            assert brave["has_api_key"] is True
            # Masked format is first-6 + '...' + last-4 — so "bsearc...2345"
            assert "bsearc" in brave["api_key_preview"]
            assert "..." in brave["api_key_preview"]
            # Full key must not be in the preview
            assert "testkey12345" not in brave["api_key_preview"]
        finally:
            os.environ.pop("BRAVE_API_KEY", None)


# ---------------------------------------------------------------------------
# POST /api/config/test-provider — brave and perplexity connection tests
# ---------------------------------------------------------------------------


class TestTestProviderBrave:
    # @mock-exempt: httpx.get — external Brave Search HTTP API; requires paid key + network
    def test_brave_success_returns_model_used(self, client, tmp_config):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_response):
            resp = client.post(
                "/api/config/test-provider",
                json={"provider": "brave", "api_key": "bsearch-fakekey12345", "model": ""},
            )
        body = resp.json()
        assert body["success"] is True
        assert body["model_used"] == "brave-search"

    # @mock-exempt: httpx.get — external Brave Search HTTP API; requires paid key + network
    def test_brave_not_unknown_provider(self, client, tmp_config):
        """Brave is now a known provider — must not return unknown-provider error."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_response):
            resp = client.post(
                "/api/config/test-provider",
                json={"provider": "brave", "api_key": "bsearch-fakekey12345", "model": ""},
            )
        body = resp.json()
        assert "unknown provider" not in (body.get("error") or "").lower()

    # @mock-exempt: httpx.get — external Brave Search HTTP API; requires paid key + network
    def test_brave_http_error_returns_failure(self, client, tmp_config):
        import httpx as httpx_lib

        with patch(
            "httpx.get",
            side_effect=httpx_lib.HTTPStatusError(
                "403 Forbidden",
                request=MagicMock(),
                response=MagicMock(status_code=403),
            ),
        ):
            resp = client.post(
                "/api/config/test-provider",
                json={"provider": "brave", "api_key": "bad-key", "model": ""},
            )
        body = resp.json()
        assert body["success"] is False
        assert body["error"]

    # @mock-exempt: httpx.get — external Brave Search HTTP API; requires paid key + network
    def test_brave_test_uses_correct_search_url(self, client, tmp_config):
        """Brave test must hit api.search.brave.com."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_response) as mock_get:
            client.post(
                "/api/config/test-provider",
                json={"provider": "brave", "api_key": "bsearch-fakekey12345", "model": ""},
            )
        call_args = mock_get.call_args
        assert "api.search.brave.com" in call_args[0][0]


class TestTestProviderPerplexity:
    # @mock-exempt: openai.OpenAI — external Perplexity API (api.perplexity.ai); third-party service
    def test_perplexity_success_returns_sonar_model(self, client, tmp_config):
        mock_completion = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        with patch("openai.OpenAI", return_value=mock_client):
            resp = client.post(
                "/api/config/test-provider",
                json={"provider": "perplexity", "api_key": "pplx-fakekey12345", "model": ""},
            )
        body = resp.json()
        assert body["success"] is True
        assert body["model_used"] == "sonar"

    # @mock-exempt: openai.OpenAI — external Perplexity API (api.perplexity.ai); third-party service
    def test_perplexity_uses_perplexity_base_url(self, client, tmp_config):
        """Perplexity test must use api.perplexity.ai as base URL."""
        mock_completion = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        with patch("openai.OpenAI", return_value=mock_client) as mock_openai:
            client.post(
                "/api/config/test-provider",
                json={"provider": "perplexity", "api_key": "pplx-fakekey12345", "model": ""},
            )
        call_kwargs = mock_openai.call_args[1]
        assert "perplexity.ai" in call_kwargs.get("base_url", "")

    # @mock-exempt: openai.OpenAI — external Perplexity API (api.perplexity.ai); third-party service
    def test_perplexity_auth_error_returns_failure(self, client, tmp_config):
        import openai as openai_lib

        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = openai_lib.AuthenticationError(
                "Invalid API key",
                response=MagicMock(status_code=401),
                body={},
            )
            mock_openai_cls.return_value = mock_client
            resp = client.post(
                "/api/config/test-provider",
                json={"provider": "perplexity", "api_key": "pplx-badkey", "model": ""},
            )
        body = resp.json()
        assert body["success"] is False
        assert body["error"]

    # @mock-exempt: openai.OpenAI — external Perplexity API (api.perplexity.ai); third-party service
    def test_perplexity_not_unknown_provider(self, client, tmp_config):
        """Perplexity is now known — must not return unknown-provider error."""
        mock_completion = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        with patch("openai.OpenAI", return_value=mock_client):
            resp = client.post(
                "/api/config/test-provider",
                json={"provider": "perplexity", "api_key": "pplx-fakekey12345", "model": ""},
            )
        body = resp.json()
        assert "unknown provider" not in (body.get("error") or "").lower()


class TestTestProviderUnknown:
    def test_unknown_provider_still_returns_error(self, client, tmp_config):
        resp = client.post(
            "/api/config/test-provider",
            json={"provider": "nonexistent", "api_key": "somekey", "model": ""},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "unknown provider" in body["error"].lower()


# ---------------------------------------------------------------------------
# GET /api/config/providers — brave & perplexity appear in provider list
# ---------------------------------------------------------------------------


class TestTestProviderGemini:
    """Verify the Gemini test-provider handler uses the google.genai SDK (not google.generativeai).

    # @mock-exempt: google.genai.Client — external Gemini API; requires real credentials + network
    """

    def test_gemini_success_returns_model_used(self, client, tmp_config):
        """A mocked successful Gemini call returns success=True with the requested model."""
        mock_client = MagicMock()
        with patch("google.genai.Client", return_value=mock_client):
            resp = client.post(
                "/api/config/test-provider",
                json={"provider": "gemini", "api_key": "AI-fakekey12345", "model": "gemini-2.0-flash"},
            )
        body = resp.json()
        assert body["success"] is True
        assert body["model_used"] == "gemini-2.0-flash"

    def test_gemini_uses_new_sdk_client(self, client, tmp_config):
        """The handler must construct a google.genai.Client (new SDK), not use google.generativeai."""
        mock_client = MagicMock()
        with patch("google.genai.Client", return_value=mock_client) as mock_cls:
            client.post(
                "/api/config/test-provider",
                json={"provider": "gemini", "api_key": "AI-fakekey12345", "model": "gemini-2.0-flash"},
            )
        # Client must have been constructed with the api_key
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1]
        assert call_kwargs.get("api_key") == "AI-fakekey12345"

    def test_gemini_calls_generate_content_on_models(self, client, tmp_config):
        """generate_content must be called via client.models (new SDK pattern)."""
        mock_client = MagicMock()
        with patch("google.genai.Client", return_value=mock_client):
            client.post(
                "/api/config/test-provider",
                json={"provider": "gemini", "api_key": "AI-fakekey12345", "model": "gemini-2.0-flash"},
            )
        mock_client.models.generate_content.assert_called_once()

    def test_gemini_auth_error_returns_failure(self, client, tmp_config):
        """API key errors propagate as success=False with a non-empty error message."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API key not valid")
        with patch("google.genai.Client", return_value=mock_client):
            resp = client.post(
                "/api/config/test-provider",
                json={"provider": "gemini", "api_key": "bad-key", "model": "gemini-2.0-flash"},
            )
        body = resp.json()
        assert body["success"] is False
        assert body["error"]


class TestListProvidersResearch:
    def test_brave_in_provider_list(self, client, tmp_config):
        resp = client.get("/api/config/providers")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "brave" in names

    def test_perplexity_in_provider_list(self, client, tmp_config):
        resp = client.get("/api/config/providers")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "perplexity" in names
