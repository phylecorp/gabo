"""Tests for the stable runs directory feature.

Verifies that analysis runs write to ~/.sat/runs/ by default instead of
relying on the current working directory ('.'), which is unpredictable in
packaged Electron apps launched from Finder on macOS.

@decision DEC-RUNS-001
@title get_default_runs_dir() returns ~/.sat/runs/ as the stable write location
@status accepted
@rationale In packaged Electron apps, CWD is typically '/' (inherited from the
OS launcher), causing 'Permission denied' errors when the backend tries to
create output directories under the CWD. ~/.sat/runs/ is always writable by
the running user and is stable across app restarts. The function creates the
directory on first call (mode 0o700) so no manual setup is required.

Design note: get_default_runs_dir() respects a SAT_RUNS_DIR environment
variable when set, making it overrideable in tests without mocking any
internal code.  Tests set SAT_RUNS_DIR=<tmp_path> via monkeypatch.setenv.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
from sat.config import get_default_runs_dir


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def runs_dir(tmp_path):
    """A temporary runs directory injected via SAT_RUNS_DIR."""
    d = tmp_path / "runs"
    d.mkdir(mode=0o700)
    return d


@pytest.fixture()
def client(monkeypatch, runs_dir):
    """API client with auth disabled and SAT_RUNS_DIR overridden."""
    monkeypatch.setenv("SAT_DISABLE_AUTH", "1")
    monkeypatch.setenv("SAT_RUNS_DIR", str(runs_dir))
    app = create_app(port=8742)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# get_default_runs_dir() — core utility
# ---------------------------------------------------------------------------


def test_get_default_runs_dir_returns_home_sat_runs():
    """get_default_runs_dir() returns ~/.sat/runs/ when SAT_RUNS_DIR is not set."""
    expected = Path.home() / ".sat" / "runs"
    result = get_default_runs_dir()
    assert result == expected, f"Expected {expected}, got {result}"


def test_get_default_runs_dir_creates_directory(monkeypatch, tmp_path):
    """get_default_runs_dir() creates the directory if it does not exist."""
    target = tmp_path / "newdir"
    assert not target.exists()
    monkeypatch.setenv("SAT_RUNS_DIR", str(target))
    result = get_default_runs_dir()
    assert result.exists(), "get_default_runs_dir() must create the directory"
    assert result.is_dir()


def test_get_default_runs_dir_idempotent(monkeypatch, tmp_path):
    """get_default_runs_dir() does not raise if the directory already exists."""
    target = tmp_path / "existing"
    target.mkdir(mode=0o700)
    monkeypatch.setenv("SAT_RUNS_DIR", str(target))
    # Should not raise even though directory already exists
    result = get_default_runs_dir()
    assert result.is_dir()


def test_get_default_runs_dir_permissions(monkeypatch, tmp_path):
    """get_default_runs_dir() creates the directory with mode 0o700."""
    target = tmp_path / "perms_test"
    monkeypatch.setenv("SAT_RUNS_DIR", str(target))
    result = get_default_runs_dir()
    mode = stat.S_IMODE(result.stat().st_mode)
    assert mode == 0o700, f"Expected 0o700 permissions, got {oct(mode)}"


def test_get_default_runs_dir_env_override(monkeypatch, tmp_path):
    """SAT_RUNS_DIR env var overrides the default ~/.sat/runs/ path."""
    custom = tmp_path / "custom_runs"
    monkeypatch.setenv("SAT_RUNS_DIR", str(custom))
    result = get_default_runs_dir()
    assert result == custom, f"Expected {custom}, got {result}"


# ---------------------------------------------------------------------------
# AnalysisRequest.output_dir defaults to None
# ---------------------------------------------------------------------------


def test_analysis_request_output_dir_default_is_none():
    """AnalysisRequest.output_dir defaults to None, not '.'."""
    from sat.api.models import AnalysisRequest

    req = AnalysisRequest(question="Is this a test?")
    assert req.output_dir is None, (
        f"output_dir should default to None, got {req.output_dir!r}"
    )


# ---------------------------------------------------------------------------
# POST /api/analysis uses default runs dir when output_dir is omitted
# ---------------------------------------------------------------------------


def test_analysis_post_uses_default_runs_dir_when_output_dir_omitted(client, runs_dir):
    """POST /api/analysis without output_dir is accepted (uses default runs dir)."""
    import sat.techniques  # noqa: F401 — trigger registration
    from sat.techniques.registry import list_technique_ids

    valid_ids = list_technique_ids()
    if not valid_ids:
        pytest.skip("No techniques registered")

    payload = {
        "question": "Test question for stable dir",
        "provider": "anthropic",
        "techniques": [valid_ids[0]],
    }
    resp = client.post("/api/analysis", json=payload)
    assert resp.status_code == 200, (
        f"Expected 200 for analysis without output_dir, got {resp.status_code}: {resp.text}"
    )


def test_analysis_post_uses_default_runs_dir_when_output_dir_is_null(client, runs_dir):
    """POST /api/analysis with output_dir: null is accepted."""
    import sat.techniques  # noqa: F401 — trigger registration
    from sat.techniques.registry import list_technique_ids

    valid_ids = list_technique_ids()
    if not valid_ids:
        pytest.skip("No techniques registered")

    payload = {
        "question": "Test question for stable dir",
        "provider": "anthropic",
        "techniques": [valid_ids[0]],
        "output_dir": None,
    }
    resp = client.post("/api/analysis", json=payload)
    assert resp.status_code == 200, (
        f"Expected 200 for analysis with output_dir=null, got {resp.status_code}: {resp.text}"
    )


def test_analysis_post_explicit_dot_still_accepted(client, runs_dir):
    """POST /api/analysis with explicit output_dir='.' still accepted (CLI compat)."""
    import sat.techniques  # noqa: F401 — trigger registration
    from sat.techniques.registry import list_technique_ids

    valid_ids = list_technique_ids()
    if not valid_ids:
        pytest.skip("No techniques registered")

    payload = {
        "question": "Test question",
        "provider": "anthropic",
        "techniques": [valid_ids[0]],
        "output_dir": ".",
    }
    resp = client.post("/api/analysis", json=payload)
    assert resp.status_code == 200, (
        f"Expected 200 for explicit output_dir='.', got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# GET /api/runs uses default runs dir when dir is omitted
# ---------------------------------------------------------------------------


def test_list_runs_uses_default_runs_dir_when_dir_omitted(client, runs_dir):
    """GET /api/runs without ?dir= scans SAT_RUNS_DIR for manifests."""
    run_id = "test-stable-dir-run"
    run_dir = runs_dir / f"sat-{run_id}"
    run_dir.mkdir()
    manifest = {
        "run_id": run_id,
        "question": "Stable dir test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.get("/api/runs")
    assert resp.status_code == 200
    runs = resp.json()
    run_ids = [r["run_id"] for r in runs]
    assert run_id in run_ids, (
        f"Expected run {run_id!r} in list from default runs dir, got {run_ids}"
    )


def test_get_run_uses_default_runs_dir_when_dir_omitted(client, runs_dir):
    """GET /api/runs/{id} without ?dir= finds runs in SAT_RUNS_DIR."""
    run_id = "get-run-stable-test"
    run_dir = runs_dir / f"sat-{run_id}"
    run_dir.mkdir()
    manifest = {
        "run_id": run_id,
        "question": "Get run stable dir test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200, (
        f"Expected 200 for run in default runs dir, got {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    assert data["run_id"] == run_id


# ---------------------------------------------------------------------------
# Security: output_dir path traversal still rejected
# ---------------------------------------------------------------------------


def test_output_dir_dotdot_still_rejected(client, runs_dir):
    """Path traversal via output_dir='../../etc' still rejected after refactor."""
    payload = {
        "question": "Test question",
        "output_dir": "../../etc",
        "provider": "anthropic",
    }
    resp = client.post("/api/analysis", json=payload)
    assert resp.status_code in (400, 422), (
        f"Expected 400/422 for path traversal in output_dir, got {resp.status_code}"
    )


def test_output_dir_absolute_outside_runs_dir_rejected(client, runs_dir, tmp_path):
    """Absolute output_dir that falls outside the default runs dir is rejected."""
    outside = tmp_path / "totally_different_dir"
    outside.mkdir()
    payload = {
        "question": "Test question",
        "output_dir": str(outside),
        "provider": "anthropic",
    }
    resp = client.post("/api/analysis", json=payload)
    assert resp.status_code in (400, 422), (
        f"Expected 400/422 for absolute path outside runs dir, got {resp.status_code}"
    )


def test_output_dir_within_runs_dir_accepted(client, runs_dir):
    """Absolute output_dir that is within the default runs dir is accepted."""
    import sat.techniques  # noqa: F401 — trigger registration
    from sat.techniques.registry import list_technique_ids

    valid_ids = list_technique_ids()
    if not valid_ids:
        pytest.skip("No techniques registered")

    subdir = runs_dir / "mysubdir"
    subdir.mkdir()

    payload = {
        "question": "Test question",
        "output_dir": str(subdir),
        "provider": "anthropic",
        "techniques": [valid_ids[0]],
    }
    resp = client.post("/api/analysis", json=payload)
    assert resp.status_code == 200, (
        f"Expected 200 for path within runs dir, got {resp.status_code}: {resp.text}"
    )
