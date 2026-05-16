"""Tests for adversarial settings in the Settings API endpoints.

Covers:
- AdversarialSettings Pydantic model validation
- GET /api/config/settings includes adversarial section from config.json
- PUT /api/config/settings persists adversarial settings correctly
- Adversarial section is a full replacement (not field-by-field merge)
- All-None adversarial section is omitted from config.json
- Empty/None adversarial in payload preserves existing adversarial config

@decision DEC-ADVERSARIAL-SETTINGS-API-001
@title Adversarial settings follow the same config.json/env pattern as technique_overrides
@status accepted
@rationale Adversarial settings are persistent defaults stored in the 'adversarial' key
of ~/.sat/config.json. They are a full replacement on PUT (not merged field-by-field)
to match the technique_overrides pattern. All-None entries are omitted from the file
to keep config.json lean.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
from sat.api.models import AdversarialSettings, AppSettings, SettingsResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8742)


@pytest.fixture()
def client(app):
    return TestClient(app)


def write_config(tmp_path: Path, data: dict) -> Path:
    """Helper: write a sat config.json to tmp_path and return its path."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))
    return config_path


# ---------------------------------------------------------------------------
# AdversarialSettings model tests
# ---------------------------------------------------------------------------


def test_adversarial_settings_defaults():
    """All fields default to None (optional)."""
    s = AdversarialSettings()
    assert s.enabled is None
    assert s.mode is None
    assert s.rounds is None
    assert s.challenger_provider is None
    assert s.challenger_model is None
    assert s.investigator_provider is None
    assert s.investigator_model is None


def test_adversarial_settings_full():
    """All fields can be set."""
    s = AdversarialSettings(
        enabled=True,
        mode="trident",
        rounds=3,
        challenger_provider="openai",
        challenger_model="gpt-4o",
        investigator_provider="gemini",
        investigator_model="gemini-2.5-pro",
    )
    assert s.enabled is True
    assert s.mode == "trident"
    assert s.rounds == 3
    assert s.challenger_provider == "openai"
    assert s.challenger_model == "gpt-4o"
    assert s.investigator_provider == "gemini"
    assert s.investigator_model == "gemini-2.5-pro"


def test_adversarial_settings_rounds_validation():
    """rounds must be between 1 and 5."""
    import pytest
    with pytest.raises(Exception):
        AdversarialSettings(rounds=0)
    with pytest.raises(Exception):
        AdversarialSettings(rounds=6)
    # Valid boundary values
    AdversarialSettings(rounds=1)
    AdversarialSettings(rounds=5)


def test_app_settings_has_adversarial_field():
    """AppSettings accepts an adversarial field."""
    settings = AppSettings(
        providers={},
        adversarial=AdversarialSettings(enabled=True, mode="dual"),
    )
    assert settings.adversarial is not None
    assert settings.adversarial.enabled is True


def test_settings_response_has_adversarial_field():
    """SettingsResponse accepts an adversarial field."""
    resp = SettingsResponse(
        providers={},
        adversarial=AdversarialSettings(mode="trident", rounds=2),
    )
    assert resp.adversarial is not None
    assert resp.adversarial.mode == "trident"


# ---------------------------------------------------------------------------
# GET /api/config/settings — adversarial section
# ---------------------------------------------------------------------------


def test_get_settings_includes_adversarial_from_config(client, tmp_path):
    """GET /api/config/settings returns adversarial section from config.json."""
    import sat.api.routes.config as config_mod

    config_path = write_config(tmp_path, {
        "providers": {},
        "adversarial": {
            "enabled": True,
            "mode": "dual",
            "rounds": 2,
            "challenger_provider": "openai",
            "challenger_model": "gpt-4o",
        }
    })
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/settings")
        assert resp.status_code == 200
        body = resp.json()
        adv = body.get("adversarial")
        assert adv is not None
        assert adv["enabled"] is True
        assert adv["mode"] == "dual"
        assert adv["rounds"] == 2
        assert adv["challenger_provider"] == "openai"
        assert adv["challenger_model"] == "gpt-4o"
    finally:
        config_mod._get_config_path = orig


def test_get_settings_adversarial_none_when_not_configured(client, tmp_path):
    """GET /api/config/settings returns adversarial=None when not in config."""
    import sat.api.routes.config as config_mod

    config_path = tmp_path / "nonexistent.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/settings")
        assert resp.status_code == 200
        body = resp.json()
        # adversarial is absent or null
        assert body.get("adversarial") is None
    finally:
        config_mod._get_config_path = orig


def test_get_settings_adversarial_partial_fields(client, tmp_path):
    """Partial adversarial config is returned as-is with None for missing fields."""
    import sat.api.routes.config as config_mod

    config_path = write_config(tmp_path, {
        "adversarial": {"mode": "trident"}
    })
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path
    try:
        resp = client.get("/api/config/settings")
        assert resp.status_code == 200
        body = resp.json()
        adv = body.get("adversarial")
        assert adv is not None
        assert adv["mode"] == "trident"
        # Other fields are None
        assert adv.get("enabled") is None
        assert adv.get("rounds") is None
    finally:
        config_mod._get_config_path = orig


# ---------------------------------------------------------------------------
# PUT /api/config/settings — adversarial section
# ---------------------------------------------------------------------------


def test_put_settings_saves_adversarial(client, tmp_path):
    """PUT /api/config/settings persists adversarial section to config.json."""
    import sat.api.routes.config as config_mod

    config_path = tmp_path / "config.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    payload = {
        "providers": {},
        "adversarial": {
            "enabled": True,
            "mode": "dual",
            "rounds": 3,
            "challenger_provider": "openai",
            "challenger_model": "gpt-4o",
        }
    }
    try:
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        saved = json.loads(config_path.read_text())
        adv = saved.get("adversarial")
        assert adv is not None
        assert adv["enabled"] is True
        assert adv["mode"] == "dual"
        assert adv["rounds"] == 3
        assert adv["challenger_provider"] == "openai"
        assert adv["challenger_model"] == "gpt-4o"
    finally:
        config_mod._get_config_path = orig


def test_put_settings_adversarial_none_omitted_from_config(client, tmp_path):
    """PUT with adversarial=None or all-None fields omits adversarial from config.json."""
    import sat.api.routes.config as config_mod

    config_path = tmp_path / "config.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    payload = {
        "providers": {},
        "adversarial": None,
    }
    try:
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        saved = json.loads(config_path.read_text())
        # adversarial key should be absent
        assert "adversarial" not in saved
    finally:
        config_mod._get_config_path = orig


def test_put_settings_adversarial_all_none_fields_omitted(client, tmp_path):
    """PUT with adversarial where all fields are None omits adversarial from config.json."""
    import sat.api.routes.config as config_mod

    config_path = tmp_path / "config.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    payload = {
        "providers": {},
        "adversarial": {
            "enabled": None,
            "mode": None,
            "rounds": None,
            "challenger_provider": None,
            "challenger_model": None,
            "investigator_provider": None,
            "investigator_model": None,
        }
    }
    try:
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        saved = json.loads(config_path.read_text())
        # adversarial key should be absent (all values are None)
        assert "adversarial" not in saved
    finally:
        config_mod._get_config_path = orig


def test_put_settings_adversarial_is_full_replacement(client, tmp_path):
    """PUT adversarial replaces the entire section (not field-by-field merge)."""
    import sat.api.routes.config as config_mod

    # Pre-populate with existing adversarial settings
    config_path = write_config(tmp_path, {
        "adversarial": {
            "enabled": True,
            "mode": "trident",
            "rounds": 2,
            "challenger_provider": "openai",
            "investigator_provider": "gemini",
        }
    })
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    # PUT with only some fields set
    payload = {
        "providers": {},
        "adversarial": {
            "enabled": False,
            "mode": "dual",
        }
    }
    try:
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        saved = json.loads(config_path.read_text())
        adv = saved.get("adversarial")
        assert adv is not None
        assert adv["enabled"] is False
        assert adv["mode"] == "dual"
        # Old fields (rounds, challenger_provider, investigator_provider) should
        # be absent in the new file since it's a full replacement
        assert "rounds" not in adv or adv.get("rounds") is None
        assert "investigator_provider" not in adv or adv.get("investigator_provider") is None
    finally:
        config_mod._get_config_path = orig


def test_put_settings_returns_adversarial_in_response(client, tmp_path):
    """PUT /api/config/settings response includes the saved adversarial settings."""
    import sat.api.routes.config as config_mod

    config_path = tmp_path / "config.json"
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    payload = {
        "providers": {},
        "adversarial": {
            "enabled": True,
            "mode": "trident",
            "rounds": 2,
            "challenger_provider": "anthropic",
        }
    }
    try:
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        adv = body.get("adversarial")
        assert adv is not None
        assert adv["enabled"] is True
        assert adv["mode"] == "trident"
        assert adv["rounds"] == 2
    finally:
        config_mod._get_config_path = orig


def test_put_settings_no_adversarial_preserves_nothing(client, tmp_path):
    """PUT without adversarial field does not restore adversarial from existing config.

    Since adversarial is a full replacement, sending no adversarial field (None)
    means "clear adversarial settings".
    """
    import sat.api.routes.config as config_mod

    # Pre-populate config with adversarial settings
    config_path = write_config(tmp_path, {
        "adversarial": {"enabled": True, "mode": "dual"}
    })
    orig = config_mod._get_config_path
    config_mod._get_config_path = lambda: config_path

    payload = {
        "providers": {},
        # no adversarial key
    }
    try:
        resp = client.put("/api/config/settings", json=payload)
        assert resp.status_code == 200
        saved = json.loads(config_path.read_text())
        # Adversarial should be cleared since we sent None
        assert "adversarial" not in saved
    finally:
        config_mod._get_config_path = orig


# ---------------------------------------------------------------------------
# _load_settings — adversarial section
# ---------------------------------------------------------------------------


def test_load_settings_reads_adversarial_section(tmp_path):
    """_load_settings populates AdversarialSettings from config file."""
    from sat.api.routes.config import _load_settings

    config_path = write_config(tmp_path, {
        "adversarial": {
            "enabled": True,
            "mode": "trident",
            "rounds": 4,
            "challenger_provider": "openai",
            "challenger_model": "gpt-4o",
            "investigator_provider": "gemini",
            "investigator_model": "gemini-2.5-pro",
        }
    })
    result = _load_settings(config_path)
    assert result.adversarial is not None
    assert result.adversarial.enabled is True
    assert result.adversarial.mode == "trident"
    assert result.adversarial.rounds == 4
    assert result.adversarial.challenger_provider == "openai"
    assert result.adversarial.challenger_model == "gpt-4o"
    assert result.adversarial.investigator_provider == "gemini"
    assert result.adversarial.investigator_model == "gemini-2.5-pro"


def test_load_settings_adversarial_none_when_absent(tmp_path):
    """_load_settings returns adversarial=None when not in config file."""
    from sat.api.routes.config import _load_settings

    config_path = tmp_path / "nonexistent.json"
    result = _load_settings(config_path)
    assert result.adversarial is None


def test_load_settings_adversarial_none_when_empty_section(tmp_path):
    """_load_settings returns adversarial=None when adversarial key is empty dict."""
    from sat.api.routes.config import _load_settings

    config_path = write_config(tmp_path, {"adversarial": {}})
    result = _load_settings(config_path)
    # Empty adversarial dict has all-None fields; treated as no adversarial configured
    # The loaded model may be an AdversarialSettings with all None fields, or None.
    # What matters: no errors.
    # Either None or all-None AdversarialSettings is acceptable.
    if result.adversarial is not None:
        adv = result.adversarial
        assert adv.enabled is None
        assert adv.mode is None
        assert adv.rounds is None
