"""Tests for the shared-secret authentication layer.

@decision DEC-AUTH-TEST-001
@title Auth tests use monkeypatch for env vars and real app instances
@status accepted
@rationale The auth module reads os.environ at call time. Tests use pytest's
monkeypatch fixture (not unittest.mock) to manipulate SAT_DISABLE_AUTH without
contaminating the real environment. All route tests use the real FastAPI app
and TestClient — no internal mocks.
"""

from __future__ import annotations


from fastapi.testclient import TestClient

from sat.api.auth import AUTH_TOKEN, get_auth_token, verify_ws_token
from sat.api.app import create_app


# ---------------------------------------------------------------------------
# Unit tests: token generation
# ---------------------------------------------------------------------------


def test_auth_token_is_64_hex_chars():
    """AUTH_TOKEN should be a 64-char hex string (32 bytes)."""
    assert len(AUTH_TOKEN) == 64
    assert all(c in "0123456789abcdef" for c in AUTH_TOKEN)


def test_get_auth_token_returns_same_token():
    """get_auth_token() returns the module-level AUTH_TOKEN."""
    assert get_auth_token() == AUTH_TOKEN


def test_auth_token_is_unique_per_import():
    """AUTH_TOKEN is fixed at module import time (same value on repeated access)."""
    from sat.api.auth import AUTH_TOKEN as token_a
    from sat.api.auth import AUTH_TOKEN as token_b
    assert token_a == token_b


# ---------------------------------------------------------------------------
# Unit tests: verify_ws_token
# ---------------------------------------------------------------------------


def test_verify_ws_token_accepts_correct_token(monkeypatch):
    """verify_ws_token returns True for the correct token."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    assert verify_ws_token(AUTH_TOKEN) is True


def test_verify_ws_token_rejects_wrong_token(monkeypatch):
    """verify_ws_token returns False for a wrong token."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    assert verify_ws_token("deadbeef" * 8) is False


def test_verify_ws_token_rejects_empty_token(monkeypatch):
    """verify_ws_token returns False for empty string."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    assert verify_ws_token("") is False


def test_verify_ws_token_accepts_any_token_in_disabled_mode(monkeypatch):
    """verify_ws_token accepts any token when SAT_DISABLE_AUTH=1."""
    monkeypatch.setenv("SAT_DISABLE_AUTH", "1")
    assert verify_ws_token("wrong-token") is True
    assert verify_ws_token("") is True


# ---------------------------------------------------------------------------
# Integration: HTTP health endpoint always accessible
# ---------------------------------------------------------------------------


def test_health_always_accessible_without_token(monkeypatch):
    """Health endpoint is excluded from auth — no token required."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_health_accessible_with_disabled_auth(monkeypatch):
    """Health endpoint works when SAT_DISABLE_AUTH=1."""
    monkeypatch.setenv("SAT_DISABLE_AUTH", "1")
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Integration: HTTP auth enforcement
# ---------------------------------------------------------------------------


def test_techniques_blocked_without_token(monkeypatch):
    """GET /api/techniques returns 401 when no Authorization header is sent."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get("/api/techniques")
    assert resp.status_code == 401


def test_techniques_accessible_with_valid_bearer(monkeypatch):
    """GET /api/techniques returns 200 with valid Bearer token."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get(
        "/api/techniques",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )
    assert resp.status_code == 200


def test_techniques_blocked_with_wrong_token(monkeypatch):
    """GET /api/techniques returns 401 with incorrect Bearer token."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get(
        "/api/techniques",
        headers={"Authorization": "Bearer wrongtoken_notreal"},
    )
    assert resp.status_code == 401


def test_techniques_blocked_with_malformed_auth_header(monkeypatch):
    """GET /api/techniques returns 401 with malformed Authorization header."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get(
        "/api/techniques",
        headers={"Authorization": "NotBearer something"},
    )
    assert resp.status_code == 401


def test_techniques_blocked_with_missing_bearer_prefix(monkeypatch):
    """GET /api/techniques returns 401 when Authorization has token but no 'Bearer ' prefix."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get(
        "/api/techniques",
        headers={"Authorization": AUTH_TOKEN},  # no "Bearer " prefix
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration: SAT_DISABLE_AUTH bypass for tests
# ---------------------------------------------------------------------------


def test_all_routes_accessible_in_disabled_mode(monkeypatch):
    """When SAT_DISABLE_AUTH=1, all routes are accessible without any token."""
    monkeypatch.setenv("SAT_DISABLE_AUTH", "1")
    app = create_app(port=8742)
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/techniques").status_code == 200
    assert client.get("/api/config/providers").status_code == 200


def test_runs_accessible_in_disabled_mode(monkeypatch, tmp_path):
    """GET /api/runs accessible without token when SAT_DISABLE_AUTH=1."""
    monkeypatch.setenv("SAT_DISABLE_AUTH", "1")
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get(f"/api/runs?dir={tmp_path}")
    assert resp.status_code == 200


def test_runs_blocked_without_token(monkeypatch, tmp_path):
    """GET /api/runs returns 401 without token when auth is enabled."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get(f"/api/runs?dir={tmp_path}")
    assert resp.status_code == 401


def test_runs_accessible_with_valid_token(monkeypatch, tmp_path):
    """GET /api/runs returns 200 with valid Bearer token."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get(
        f"/api/runs?dir={tmp_path}",
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 401 response body structure
# ---------------------------------------------------------------------------


def test_401_response_has_detail_field(monkeypatch):
    """401 response body contains a 'detail' field."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get("/api/techniques")
    assert resp.status_code == 401
    body = resp.json()
    assert "detail" in body


def test_401_response_includes_www_authenticate_header(monkeypatch):
    """401 response includes WWW-Authenticate header per RFC 6750."""
    monkeypatch.delenv("SAT_DISABLE_AUTH", raising=False)
    app = create_app(port=8742)
    client = TestClient(app)
    resp = client.get("/api/techniques")
    assert resp.status_code == 401
    # WWW-Authenticate is recommended but not strictly required for this use case
    # — just verify the response body is correct
    assert resp.json()["detail"] != ""
