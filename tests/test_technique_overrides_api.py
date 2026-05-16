"""Tests for Phase 2: technique_overrides in settings API and default_temperature in TechniqueInfo.

Covers:
- TechniqueOverrideSettings model in sat.api.models
- AppSettings.technique_overrides field present
- SettingsResponse.technique_overrides field present
- GET /api/config/settings includes technique_overrides from config.json
- PUT /api/config/settings persists technique_overrides to config.json
- PUT /api/config/settings cleans up empty overrides (both None → omit)
- PUT /api/config/settings omits technique_overrides key when all entries cleared
- GET /api/techniques includes default_temperature field per technique

@decision DEC-TECH-OVERRIDE-API-001
@title API layer for technique overrides mirrors config.py model but stays separate
@status accepted
@rationale The API-layer TechniqueOverrideSettings and the config-layer TechniqueOverride
  have identical fields by design, but are kept separate. The API model belongs to the
  HTTP boundary and can evolve independently (e.g., add display hints, validation messages).
  The config model owns the persistence contract. Keeping them separate prevents accidental
  coupling between the storage format and the HTTP API surface.
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
    SettingsResponse,
    TechniqueOverrideSettings,
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
        "BRAVE_API_KEY",
        "PERPLEXITY_API_KEY",
    ]
    saved = {k: os.environ.pop(k, None) for k in keys_to_clean}
    yield
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
# TechniqueOverrideSettings model
# ---------------------------------------------------------------------------


class TestTechniqueOverrideSettingsModel:
    """TechniqueOverrideSettings Pydantic model validates correctly."""

    def test_defaults_are_none(self):
        """Both fields default to None."""
        override = TechniqueOverrideSettings()
        assert override.model is None
        assert override.temperature is None

    def test_model_set(self):
        override = TechniqueOverrideSettings(model="gpt-4o")
        assert override.model == "gpt-4o"
        assert override.temperature is None

    def test_temperature_set(self):
        override = TechniqueOverrideSettings(temperature=0.7)
        assert override.model is None
        assert override.temperature == 0.7

    def test_both_set(self):
        override = TechniqueOverrideSettings(model="claude-opus-4-6", temperature=0.9)
        assert override.model == "claude-opus-4-6"
        assert override.temperature == 0.9

    def test_temperature_lower_bound(self):
        """temperature=0.0 is valid."""
        override = TechniqueOverrideSettings(temperature=0.0)
        assert override.temperature == 0.0

    def test_temperature_upper_bound(self):
        """temperature=2.0 is valid."""
        override = TechniqueOverrideSettings(temperature=2.0)
        assert override.temperature == 2.0

    def test_temperature_below_lower_raises(self):
        """temperature < 0 raises ValidationError."""
        with pytest.raises(Exception):
            TechniqueOverrideSettings(temperature=-0.1)

    def test_temperature_above_upper_raises(self):
        """temperature > 2.0 raises ValidationError."""
        with pytest.raises(Exception):
            TechniqueOverrideSettings(temperature=2.1)


# ---------------------------------------------------------------------------
# AppSettings.technique_overrides field
# ---------------------------------------------------------------------------


class TestAppSettingsTechniqueOverrides:
    """AppSettings has technique_overrides field that accepts dict[str, TechniqueOverrideSettings]."""

    def test_default_is_empty_dict(self):
        settings = AppSettings()
        assert settings.technique_overrides == {}

    def test_can_set_overrides(self):
        settings = AppSettings(
            technique_overrides={
                "brainstorming": TechniqueOverrideSettings(model="gpt-4o", temperature=0.7),
            }
        )
        assert "brainstorming" in settings.technique_overrides
        assert settings.technique_overrides["brainstorming"].model == "gpt-4o"

    def test_parses_from_dict(self):
        """AppSettings can be created from a plain dict (as FastAPI receives it)."""
        settings = AppSettings.model_validate({
            "technique_overrides": {
                "ach": {"model": "claude-sonnet-4-6"},
                "red_team": {"temperature": 1.2},
            }
        })
        assert settings.technique_overrides["ach"].model == "claude-sonnet-4-6"
        assert settings.technique_overrides["red_team"].temperature == 1.2


# ---------------------------------------------------------------------------
# SettingsResponse.technique_overrides field
# ---------------------------------------------------------------------------


class TestSettingsResponseTechniqueOverrides:
    """SettingsResponse has technique_overrides field."""

    def test_default_is_empty_dict(self):
        resp = SettingsResponse()
        assert resp.technique_overrides == {}

    def test_can_hold_overrides(self):
        resp = SettingsResponse(
            technique_overrides={
                "brainstorming": TechniqueOverrideSettings(model="gpt-4o"),
            }
        )
        assert resp.technique_overrides["brainstorming"].model == "gpt-4o"


# ---------------------------------------------------------------------------
# GET /api/config/settings — technique_overrides
# ---------------------------------------------------------------------------


class TestGetSettingsTechniqueOverrides:
    """GET /api/config/settings returns technique_overrides from config.json."""

    def test_empty_when_no_config_file(self, client, tmp_path):
        """technique_overrides is empty dict when no config file exists."""
        import sat.api.routes.config as config_mod
        config_path = tmp_path / "nonexistent.json"
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        try:
            resp = client.get("/api/config/settings")
            assert resp.status_code == 200
            body = resp.json()
            assert "technique_overrides" in body
            assert body["technique_overrides"] == {}
        finally:
            config_mod._get_config_path = orig

    def test_returns_overrides_from_config(self, client, tmp_path):
        """technique_overrides from config.json appear in GET response."""
        import sat.api.routes.config as config_mod
        config_path = write_config(tmp_path, {
            "technique_overrides": {
                "brainstorming": {"model": "gpt-4o", "temperature": 0.7},
                "ach": {"model": "claude-sonnet-4-6"},
            }
        })
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        try:
            resp = client.get("/api/config/settings")
            assert resp.status_code == 200
            body = resp.json()
            overrides = body["technique_overrides"]
            assert "brainstorming" in overrides
            assert overrides["brainstorming"]["model"] == "gpt-4o"
            assert overrides["brainstorming"]["temperature"] == 0.7
            assert "ach" in overrides
            assert overrides["ach"]["model"] == "claude-sonnet-4-6"
            assert overrides["ach"]["temperature"] is None
        finally:
            config_mod._get_config_path = orig

    def test_model_only_override_has_null_temperature(self, client, tmp_path):
        """model-only override has temperature=null in response."""
        import sat.api.routes.config as config_mod
        config_path = write_config(tmp_path, {
            "technique_overrides": {
                "ach": {"model": "o3"},
            }
        })
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        try:
            resp = client.get("/api/config/settings")
            body = resp.json()
            assert body["technique_overrides"]["ach"]["model"] == "o3"
            assert body["technique_overrides"]["ach"]["temperature"] is None
        finally:
            config_mod._get_config_path = orig

    def test_temperature_only_override_has_null_model(self, client, tmp_path):
        """temperature-only override has model=null in response."""
        import sat.api.routes.config as config_mod
        config_path = write_config(tmp_path, {
            "technique_overrides": {
                "red_team": {"temperature": 1.2},
            }
        })
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        try:
            resp = client.get("/api/config/settings")
            body = resp.json()
            assert body["technique_overrides"]["red_team"]["model"] is None
            assert body["technique_overrides"]["red_team"]["temperature"] == 1.2
        finally:
            config_mod._get_config_path = orig

    def test_ignores_providers_key_still_works(self, client, tmp_path):
        """Config file with both providers and technique_overrides works correctly."""
        import sat.api.routes.config as config_mod
        config_path = write_config(tmp_path, {
            "providers": {
                "openai": {"api_key": "sk-openai-test12345678", "default_model": "gpt-4o"}
            },
            "technique_overrides": {
                "brainstorming": {"temperature": 0.9},
            }
        })
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        try:
            resp = client.get("/api/config/settings")
            assert resp.status_code == 200
            body = resp.json()
            assert body["providers"]["openai"]["default_model"] == "gpt-4o"
            assert body["technique_overrides"]["brainstorming"]["temperature"] == 0.9
        finally:
            config_mod._get_config_path = orig


# ---------------------------------------------------------------------------
# PUT /api/config/settings — technique_overrides
# ---------------------------------------------------------------------------


class TestPutSettingsTechniqueOverrides:
    """PUT /api/config/settings persists technique_overrides correctly."""

    def test_saves_technique_overrides_to_config(self, client, tmp_path):
        """PUT with technique_overrides writes them to config.json."""
        import sat.api.routes.config as config_mod
        config_path = tmp_path / "config.json"
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        payload = {
            "providers": {},
            "technique_overrides": {
                "brainstorming": {"model": "gpt-4o", "temperature": 0.7},
            }
        }
        try:
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            saved = json.loads(config_path.read_text())
            assert "technique_overrides" in saved
            assert saved["technique_overrides"]["brainstorming"]["model"] == "gpt-4o"
            assert saved["technique_overrides"]["brainstorming"]["temperature"] == 0.7
        finally:
            config_mod._get_config_path = orig

    def test_put_returns_technique_overrides_in_response(self, client, tmp_path):
        """PUT response body includes technique_overrides."""
        import sat.api.routes.config as config_mod
        config_path = tmp_path / "config.json"
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        payload = {
            "providers": {},
            "technique_overrides": {
                "ach": {"model": "claude-sonnet-4-6"},
            }
        }
        try:
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert "technique_overrides" in body
            assert body["technique_overrides"]["ach"]["model"] == "claude-sonnet-4-6"
        finally:
            config_mod._get_config_path = orig

    def test_empty_overrides_omits_key_from_config(self, client, tmp_path):
        """PUT with no technique_overrides omits the key from config.json."""
        import sat.api.routes.config as config_mod
        config_path = tmp_path / "config.json"
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        payload = {"providers": {}, "technique_overrides": {}}
        try:
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            if config_path.exists():
                saved = json.loads(config_path.read_text())
                assert "technique_overrides" not in saved or saved.get("technique_overrides") == {}
        finally:
            config_mod._get_config_path = orig

    def test_all_none_values_entry_is_cleaned(self, client, tmp_path):
        """An entry where both model and temperature are null is cleaned up and not persisted."""
        import sat.api.routes.config as config_mod
        config_path = tmp_path / "config.json"
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        payload = {
            "providers": {},
            "technique_overrides": {
                "brainstorming": {"model": None, "temperature": None},
            }
        }
        try:
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            if config_path.exists():
                saved = json.loads(config_path.read_text())
                # brainstorming with all-None values must be cleaned up
                overrides = saved.get("technique_overrides", {})
                assert "brainstorming" not in overrides
        finally:
            config_mod._get_config_path = orig

    def test_clears_old_overrides_when_all_none(self, client, tmp_path):
        """Sending all-None overrides removes all entries and omits the key."""
        import sat.api.routes.config as config_mod
        # Pre-populate with overrides
        config_path = write_config(tmp_path, {
            "technique_overrides": {
                "brainstorming": {"model": "gpt-4o", "temperature": 0.7},
            }
        })
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        # Clear by sending all-None
        payload = {
            "providers": {},
            "technique_overrides": {
                "brainstorming": {"model": None, "temperature": None},
            }
        }
        try:
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            saved = json.loads(config_path.read_text())
            assert "technique_overrides" not in saved
        finally:
            config_mod._get_config_path = orig

    def test_partial_overrides_preserved(self, client, tmp_path):
        """Entries with at least one non-None value are kept."""
        import sat.api.routes.config as config_mod
        config_path = tmp_path / "config.json"
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        payload = {
            "providers": {},
            "technique_overrides": {
                "brainstorming": {"model": "gpt-4o", "temperature": None},
                "ach": {"model": None, "temperature": None},
            }
        }
        try:
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            saved = json.loads(config_path.read_text())
            overrides = saved.get("technique_overrides", {})
            # brainstorming has model set → should be kept
            assert "brainstorming" in overrides
            # ach has both None → should be cleaned
            assert "ach" not in overrides
        finally:
            config_mod._get_config_path = orig

    def test_round_trip_save_then_load(self, client, tmp_path):
        """Full round-trip: PUT technique_overrides, then GET returns same values."""
        import sat.api.routes.config as config_mod
        config_path = tmp_path / "config.json"
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        payload = {
            "providers": {},
            "technique_overrides": {
                "brainstorming": {"model": "gpt-4o", "temperature": 0.8},
                "red_team": {"temperature": 1.1},
            }
        }
        try:
            put_resp = client.put("/api/config/settings", json=payload)
            assert put_resp.status_code == 200

            get_resp = client.get("/api/config/settings")
            assert get_resp.status_code == 200
            body = get_resp.json()
            overrides = body["technique_overrides"]
            assert overrides["brainstorming"]["model"] == "gpt-4o"
            assert overrides["brainstorming"]["temperature"] == 0.8
            assert overrides["red_team"]["model"] is None
            assert overrides["red_team"]["temperature"] == 1.1
        finally:
            config_mod._get_config_path = orig

    def test_providers_preserved_when_saving_overrides(self, client, tmp_path):
        """Saving technique_overrides does not clobber existing provider config."""
        import sat.api.routes.config as config_mod
        config_path = write_config(tmp_path, {
            "providers": {
                "anthropic": {"api_key": "sk-ant-existingkey1234", "default_model": "claude-opus-4-6"}
            }
        })
        orig = config_mod._get_config_path
        config_mod._get_config_path = lambda: config_path
        payload = {
            "providers": {},
            "technique_overrides": {
                "brainstorming": {"model": "gpt-4o"},
            }
        }
        try:
            resp = client.put("/api/config/settings", json=payload)
            assert resp.status_code == 200
            saved = json.loads(config_path.read_text())
            # Provider config must survive
            assert saved["providers"]["anthropic"]["api_key"] == "sk-ant-existingkey1234"
            assert saved["technique_overrides"]["brainstorming"]["model"] == "gpt-4o"
        finally:
            config_mod._get_config_path = orig
            os.environ.pop("ANTHROPIC_API_KEY", None)


# ---------------------------------------------------------------------------
# GET /api/techniques — default_temperature field
# ---------------------------------------------------------------------------


class TestTechniqueInfoDefaultTemperature:
    """GET /api/techniques includes default_temperature field for each technique."""

    def test_default_temperature_field_present(self, client):
        """All technique items have a default_temperature field."""
        resp = client.get("/api/techniques")
        assert resp.status_code == 200
        techniques = resp.json()
        assert len(techniques) > 0
        for t in techniques:
            assert "default_temperature" in t, (
                f"Technique {t.get('id', '?')!r} is missing default_temperature field"
            )

    def test_imaginative_techniques_have_temperature(self, client):
        """Imaginative category techniques have a non-None default_temperature."""
        resp = client.get("/api/techniques")
        techniques = resp.json()
        imaginative = [t for t in techniques if t["category"] == "imaginative"]
        assert len(imaginative) > 0, "Expected at least one imaginative technique"
        for t in imaginative:
            assert t["default_temperature"] is not None, (
                f"Imaginative technique {t['id']!r} should have a non-None default_temperature"
            )

    def test_contrarian_techniques_have_temperature(self, client):
        """Contrarian category techniques have a non-None default_temperature."""
        resp = client.get("/api/techniques")
        techniques = resp.json()
        contrarian = [t for t in techniques if t["category"] == "contrarian"]
        assert len(contrarian) > 0, "Expected at least one contrarian technique"
        for t in contrarian:
            assert t["default_temperature"] is not None, (
                f"Contrarian technique {t['id']!r} should have a non-None default_temperature"
            )

    def test_diagnostic_techniques_have_null_temperature(self, client):
        """Diagnostic category techniques have default_temperature=null."""
        resp = client.get("/api/techniques")
        techniques = resp.json()
        diagnostic = [t for t in techniques if t["category"] == "diagnostic"]
        assert len(diagnostic) > 0, "Expected at least one diagnostic technique"
        for t in diagnostic:
            # Diagnostic techniques return None (use provider default)
            assert t["default_temperature"] is None, (
                f"Diagnostic technique {t['id']!r} should have default_temperature=null, "
                f"got {t['default_temperature']!r}"
            )

    def test_brainstorming_temperature_value(self, client):
        """Brainstorming technique reports default_temperature=0.9."""
        resp = client.get("/api/techniques")
        techniques = {t["id"]: t for t in resp.json()}
        assert "brainstorming" in techniques, "brainstorming technique not found"
        assert techniques["brainstorming"]["default_temperature"] == 0.9

    def test_ach_temperature_is_null(self, client):
        """ACH (diagnostic) reports default_temperature=null."""
        resp = client.get("/api/techniques")
        techniques = {t["id"]: t for t in resp.json()}
        assert "ach" in techniques, "ach technique not found"
        assert techniques["ach"]["default_temperature"] is None
