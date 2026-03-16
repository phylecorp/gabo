"""Tests for the SAT REST + WebSocket API package.

Tests cover:
- app factory creates a valid FastAPI app
- /api/health returns 200 with status=ok
- /api/techniques returns a non-empty list of technique dicts
- /api/config/providers returns the expected provider names
- /api/runs returns an empty list initially
- /api/runs/{id} returns 404 for unknown run_id
- RunManager.create_run and get_run work correctly
- ActiveRun._handle_event appends to events_log and broadcasts to clients
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
from sat.api.run_manager import ActiveRun, RunManager
from sat.config import AnalysisConfig
from sat.events import StageStarted


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8742)


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def manager():
    return RunManager()


@pytest.fixture()
def minimal_config():
    return AnalysisConfig(question="Is this a test?")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_health_returns_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


# ---------------------------------------------------------------------------
# Techniques
# ---------------------------------------------------------------------------


def test_techniques_returns_list(client):
    resp = client.get("/api/techniques")
    assert resp.status_code == 200
    techniques = resp.json()
    assert isinstance(techniques, list)
    assert len(techniques) > 0
    # Each item should have the expected fields
    first = techniques[0]
    for field in ("id", "name", "category", "description", "order"):
        assert field in first, f"Missing field: {field}"


def test_techniques_categories_valid(client):
    resp = client.get("/api/techniques")
    techniques = resp.json()
    valid_categories = {"diagnostic", "contrarian", "imaginative"}
    for t in techniques:
        assert t["category"] in valid_categories, (
            f"Unexpected category {t['category']!r} for technique {t['id']!r}"
        )


# ---------------------------------------------------------------------------
# Config / providers
# ---------------------------------------------------------------------------


def test_providers_returns_all_known(client):
    # Includes the three LLM providers plus the two research providers.
    resp = client.get("/api/config/providers")
    assert resp.status_code == 200
    providers = resp.json()
    names = {p["name"] for p in providers}
    assert names == {"anthropic", "openai", "gemini", "perplexity", "brave"}


def test_providers_have_required_fields(client):
    resp = client.get("/api/config/providers")
    for p in resp.json():
        assert "name" in p
        assert "has_api_key" in p
        assert "default_model" in p
        assert isinstance(p["has_api_key"], bool)


# ---------------------------------------------------------------------------
# Runs — empty state
# ---------------------------------------------------------------------------


def test_runs_empty_initially(client, tmp_path):
    resp = client.get(f"/api/runs?dir={tmp_path}")
    assert resp.status_code == 200
    assert resp.json() == []


def test_run_not_found_returns_404(client):
    resp = client.get("/api/runs/nonexistentrunid")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RunManager unit tests
# ---------------------------------------------------------------------------


def test_run_manager_create_and_get(manager, minimal_config):
    run = manager.create_run(minimal_config)
    assert run.run_id
    assert len(run.run_id) == 12
    assert manager.get_run(run.run_id) is run


def test_run_manager_get_missing_returns_none(manager):
    assert manager.get_run("notexist") is None


def test_run_manager_list(manager, minimal_config):
    assert manager.list_active_runs() == []
    run1 = manager.create_run(minimal_config)
    run2 = manager.create_run(minimal_config)
    runs = manager.list_active_runs()
    assert len(runs) == 2
    assert run1 in runs
    assert run2 in runs


def test_active_run_initial_status(minimal_config):
    run = ActiveRun("abc123", minimal_config)
    assert run.status == "running"
    assert run.error is None
    assert run.output_dir is None
    assert run.ws_clients == []
    assert run.events_log == []


# ---------------------------------------------------------------------------
# ActiveRun event handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_run_event_appended_to_log(minimal_config):
    run = ActiveRun("abc123", minimal_config)
    event = StageStarted(stage="test_stage", technique_id="acm")
    await run.bus.emit(event)
    assert len(run.events_log) == 1
    entry = run.events_log[0]
    assert entry["type"] == "StageStarted"
    assert entry["data"]["stage"] == "test_stage"
    assert "timestamp" in entry


@pytest.mark.asyncio
async def test_active_run_broadcasts_to_ws_clients(minimal_config):
    run = ActiveRun("abc123", minimal_config)

    # Mock a WebSocket client
    mock_ws = AsyncMock()
    run.ws_clients.append(mock_ws)

    event = StageStarted(stage="broadcast_test")
    await run.bus.emit(event)

    mock_ws.send_json.assert_awaited_once()
    sent = mock_ws.send_json.call_args[0][0]
    assert sent["type"] == "StageStarted"


@pytest.mark.asyncio
async def test_active_run_removes_disconnected_clients(minimal_config):
    run = ActiveRun("abc123", minimal_config)

    # Mock a WS that raises on send (disconnected)
    failing_ws = AsyncMock()
    failing_ws.send_json.side_effect = RuntimeError("disconnected")
    run.ws_clients.append(failing_ws)

    event = StageStarted(stage="disc_test")
    await run.bus.emit(event)

    # The disconnected client should be pruned
    assert failing_ws not in run.ws_clients


# ---------------------------------------------------------------------------
# Artifact endpoint
# ---------------------------------------------------------------------------


def test_artifact_returns_json(client, tmp_path):
    """GET /api/runs/{run_id}/artifact returns the JSON artifact content."""
    # Create output dir structure
    output_dir = tmp_path / "sat-testart"
    output_dir.mkdir()

    # Write a simple artifact JSON
    artifact_data = {"technique_id": "test", "technique_name": "Test", "summary": "Test summary"}
    artifact_file = output_dir / "01-test.json"
    artifact_file.write_text(__import__("json").dumps(artifact_data))

    # Write manifest
    import json as _json
    manifest = {
        "run_id": "testart",
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": ["test"],
        "techniques_completed": ["test"],
        "artifacts": [{
            "technique_id": "test",
            "technique_name": "Test",
            "category": "diagnostic",
            "markdown_path": str(output_dir / "01-test.md"),
            "json_path": str(artifact_file),
        }],
    }
    (output_dir / "manifest.json").write_text(_json.dumps(manifest))

    resp = client.get(f"/api/runs/testart/artifact?path=01-test.json&dir={tmp_path}")
    assert resp.status_code == 200
    assert resp.json()["technique_id"] == "test"


def test_artifact_not_found_returns_404(client, tmp_path):
    """GET /api/runs/{run_id}/artifact returns 404 when the artifact file doesn't exist."""
    import json as _json
    output_dir = tmp_path / "sat-testmiss"
    output_dir.mkdir()

    manifest = {
        "run_id": "testmiss",
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (output_dir / "manifest.json").write_text(_json.dumps(manifest))

    resp = client.get(f"/api/runs/testmiss/artifact?path=nonexistent.json&dir={tmp_path}")
    assert resp.status_code == 404


def test_artifact_path_traversal_rejected(client, tmp_path):
    """GET /api/runs/{run_id}/artifact rejects path traversal attempts with 400."""
    import json as _json
    output_dir = tmp_path / "sat-testtraversal"
    output_dir.mkdir()

    manifest = {
        "run_id": "testtraversal",
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (output_dir / "manifest.json").write_text(_json.dumps(manifest))

    resp = client.get(f"/api/runs/testtraversal/artifact?path=../../etc/passwd&dir={tmp_path}")
    assert resp.status_code == 400


def test_artifact_run_not_found_returns_404(client, tmp_path):
    """GET /api/runs/{run_id}/artifact returns 404 when the run doesn't exist."""
    resp = client.get(f"/api/runs/nosuchrun/artifact?path=something.json&dir={tmp_path}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Download artifact endpoint
# ---------------------------------------------------------------------------


def test_artifact_download_returns_attachment(client, tmp_path):
    """Download endpoint should return file with Content-Disposition attachment."""
    import json

    output_dir = tmp_path / "sat-testdl"
    output_dir.mkdir()
    artifact_data = {"technique_id": "test", "summary": "Test"}
    artifact_file = output_dir / "01-test.json"
    artifact_file.write_text(json.dumps(artifact_data))
    manifest = {
        "run_id": "testdl",
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": ["test"],
        "techniques_completed": ["test"],
        "artifacts": [
            {
                "technique_id": "test",
                "technique_name": "Test",
                "category": "diagnostic",
                "markdown_path": str(output_dir / "01-test.md"),
                "json_path": str(artifact_file),
            }
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.get(f"/api/runs/testdl/artifact/download?path=01-test.json&dir={tmp_path}")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.json()["technique_id"] == "test"


def test_artifact_download_not_found_returns_404(client, tmp_path):
    """Download endpoint returns 404 when the file doesn't exist."""
    import json

    output_dir = tmp_path / "sat-testdl404"
    output_dir.mkdir()
    manifest = {
        "run_id": "testdl404",
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.get(f"/api/runs/testdl404/artifact/download?path=missing.json&dir={tmp_path}")
    assert resp.status_code == 404


def test_artifact_download_path_traversal_rejected(client, tmp_path):
    """Download endpoint rejects path traversal attempts with 400."""
    import json

    output_dir = tmp_path / "sat-testdltraversal"
    output_dir.mkdir()
    manifest = {
        "run_id": "testdltraversal",
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.get(
        f"/api/runs/testdltraversal/artifact/download?path=../../etc/passwd&dir={tmp_path}"
    )
    assert resp.status_code == 400


def test_artifact_download_run_not_found_returns_404(client, tmp_path):
    """Download endpoint returns 404 when the run doesn't exist."""
    resp = client.get(
        f"/api/runs/nosuchrun/artifact/download?path=something.json&dir={tmp_path}"
    )
    assert resp.status_code == 404


def test_artifact_download_html_content_type(client, tmp_path):
    """Download endpoint sets correct content-type for HTML files."""
    import json

    output_dir = tmp_path / "sat-testdlhtml"
    output_dir.mkdir()
    html_file = output_dir / "report.html"
    html_file.write_text("<html><body>test</body></html>")
    manifest = {
        "run_id": "testdlhtml",
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.get(
        f"/api/runs/testdlhtml/artifact/download?path=report.html&dir={tmp_path}"
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "attachment" in resp.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------


def test_export_returns_zip(client, tmp_path):
    """Export endpoint should return a ZIP file containing all run files."""
    import io
    import json
    import zipfile

    output_dir = tmp_path / "sat-testzip"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "testzip",
                "question": "Test?",
                "started_at": "2025-01-01T00:00:00Z",
                "techniques_selected": [],
                "techniques_completed": [],
                "artifacts": [],
            }
        )
    )
    (output_dir / "report.html").write_text("<html>test</html>")

    resp = client.get(f"/api/runs/testzip/export?dir={tmp_path}")
    assert resp.status_code == 200
    assert resp.headers.get("content-type") == "application/zip"
    assert "attachment" in resp.headers.get("content-disposition", "")
    # Verify it's a valid ZIP
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert any("manifest.json" in n for n in names)
    assert any("report.html" in n for n in names)


def test_export_run_not_found_returns_404(client, tmp_path):
    """Export endpoint returns 404 when the run doesn't exist."""
    resp = client.get(f"/api/runs/nosuchrun/export?dir={tmp_path}")
    assert resp.status_code == 404


def test_export_zip_filename_matches_run_dir(client, tmp_path):
    """Export endpoint uses the run directory name as the ZIP filename."""
    import json

    output_dir = tmp_path / "sat-testzip2"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "testzip2",
                "question": "Test?",
                "started_at": "2025-01-01T00:00:00Z",
                "techniques_selected": [],
                "techniques_completed": [],
                "artifacts": [],
            }
        )
    )

    resp = client.get(f"/api/runs/testzip2/export?dir={tmp_path}")
    assert resp.status_code == 200
    content_disp = resp.headers.get("content-disposition", "")
    assert "sat-testzip2.zip" in content_disp


# ---------------------------------------------------------------------------
# Artifact path double-nesting fix
# ---------------------------------------------------------------------------


def test_artifact_with_run_dir_prefix_in_path(client, tmp_path):
    """Artifact endpoint strips leading sat-{run_id}/ prefix to avoid double-nesting.

    The manifest stores paths like sat-{run_id}/01-test.json, but _find_output_dir()
    already returns the sat-{run_id}/ directory. Without the fix, the join produces
    sat-{run_id}/sat-{run_id}/01-test.json (double-nested, 404).
    """
    import json

    run_id = "prefixtest"
    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    artifact_data = {"technique_id": "test", "technique_name": "Test", "summary": "ok"}
    artifact_file = output_dir / "01-test.json"
    artifact_file.write_text(json.dumps(artifact_data))

    manifest = {
        "run_id": run_id,
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": ["test"],
        "techniques_completed": ["test"],
        "artifacts": [
            {
                "technique_id": "test",
                "technique_name": "Test",
                "category": "diagnostic",
                "markdown_path": str(output_dir / "01-test.md"),
                "json_path": str(artifact_file),
            }
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest))

    # Pass path with the run dir prefix — this is the format that causes double-nesting
    prefixed_path = f"sat-{run_id}/01-test.json"
    resp = client.get(
        f"/api/runs/{run_id}/artifact?path={prefixed_path}&dir={tmp_path}"
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json()["technique_id"] == "test"


def test_artifact_download_with_run_dir_prefix_in_path(client, tmp_path):
    """Download endpoint strips leading sat-{run_id}/ prefix to avoid double-nesting."""
    import json

    run_id = "dlprefix"
    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    artifact_data = {"technique_id": "test", "technique_name": "Test", "summary": "ok"}
    artifact_file = output_dir / "01-test.json"
    artifact_file.write_text(json.dumps(artifact_data))

    manifest = {
        "run_id": run_id,
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest))

    prefixed_path = f"sat-{run_id}/01-test.json"
    resp = client.get(
        f"/api/runs/{run_id}/artifact/download?path={prefixed_path}&dir={tmp_path}"
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert "attachment" in resp.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# Report generation endpoint
# ---------------------------------------------------------------------------


def test_generate_report_run_not_found(client, tmp_path):
    """POST /api/runs/{run_id}/report/generate returns 404 when run doesn't exist."""
    resp = client.post(f"/api/runs/nosuchrun/report/generate?dir={tmp_path}")
    assert resp.status_code == 404


def test_generate_report_success(client, tmp_path):
    """POST /api/runs/{run_id}/report/generate returns 200 with generated file paths."""
    import json

    run_id = "reportgen"
    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    manifest = {
        "run_id": run_id,
        "question": "What is the situation?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.post(f"/api/runs/{run_id}/report/generate?dir={tmp_path}&fmt=both")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "paths" in body
    assert len(body["paths"]) == 2  # both markdown + html
    # Verify the report files were actually generated
    assert (output_dir / "report.html").exists()
    assert (output_dir / "report.md").exists()


def test_generate_report_fmt_markdown_only(client, tmp_path):
    """POST /api/runs/{run_id}/report/generate?fmt=markdown generates only .md."""
    import json

    run_id = "reportmd"
    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    manifest = {
        "run_id": run_id,
        "question": "What happened?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest))

    resp = client.post(f"/api/runs/{run_id}/report/generate?dir={tmp_path}&fmt=markdown")
    assert resp.status_code == 200
    body = resp.json()
    assert "paths" in body
    assert len(body["paths"]) == 1
    assert (output_dir / "report.md").exists()
    assert not (output_dir / "report.html").exists()


def test_generate_report_missing_manifest_returns_400(client, tmp_path):
    """POST /api/runs/{run_id}/report/generate returns 400 when manifest is absent.

    The run directory exists (so _find_output_dir succeeds) but manifest.json
    is missing (so generate_report raises FileNotFoundError — mapped to 400).
    We create the directory but skip writing manifest.json. To make _find_output_dir
    find the run, we register the run in the active RunManager via the app's lifespan.
    Since we can't do that in a unit test easily, we use a workaround: write a
    manifest, let _find_output_dir find it, then delete the manifest before calling
    the generate endpoint.
    """
    import json

    run_id = "nomanifest"
    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    # Write manifest temporarily so the run is discoverable
    manifest = {
        "run_id": run_id,
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    # Remove manifest to simulate it missing when generate_report is called
    manifest_path.unlink()

    resp = client.post(f"/api/runs/{run_id}/report/generate?dir={tmp_path}")
    # Run is not findable without manifest.json, so _find_output_dir returns None -> 404
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Bundled synthesis_content and technique_summaries in RunDetail
# ---------------------------------------------------------------------------


def _make_completed_run_dir(tmp_path, run_id: str, *, with_synthesis: bool = True, with_artifacts: bool = True) -> tuple:
    """Helper: create a completed run directory with manifest, synthesis, and artifact JSON files.

    Returns (output_dir, artifact_data, synthesis_data).
    """
    import json as _json

    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    # Artifact JSON
    artifact_data = {
        "technique_id": "key_assumptions_check",
        "technique_name": "Key Assumptions Check",
        "summary": "Key assumption summary text",
        "assumptions": [],
    }
    artifact_file = output_dir / "01-key_assumptions_check.json"
    artifact_file.write_text(_json.dumps(artifact_data))

    # Synthesis JSON
    synthesis_data = {
        "technique_id": "synthesis",
        "technique_name": "Synthesis",
        "summary": "Overall synthesis summary",
        "question": "What is happening?",
        "techniques_applied": ["key_assumptions_check"],
        "key_findings": [],
        "convergent_judgments": [],
        "divergent_signals": [],
        "highest_confidence_assessments": [],
        "remaining_uncertainties": [],
        "intelligence_gaps": [],
        "recommended_next_steps": [],
        "bottom_line_assessment": "Bottom line here",
    }
    synthesis_file = output_dir / "synthesis.json"
    if with_synthesis:
        synthesis_file.write_text(_json.dumps(synthesis_data))

    manifest = {
        "run_id": run_id,
        "question": "What is happening?",
        "started_at": "2025-01-01T00:00:00Z",
        "completed_at": "2025-01-01T01:00:00Z",
        "techniques_selected": ["key_assumptions_check"],
        "techniques_completed": ["key_assumptions_check"],
        "artifacts": [
            {
                "technique_id": "key_assumptions_check",
                "technique_name": "Key Assumptions Check",
                "category": "diagnostic",
                "markdown_path": str(output_dir / "01-key_assumptions_check.md"),
                "json_path": str(artifact_file) if with_artifacts else None,
            }
        ] if with_artifacts else [],
        "synthesis_path": str(synthesis_file) if with_synthesis else None,
    }
    (output_dir / "manifest.json").write_text(_json.dumps(manifest))

    return output_dir, artifact_data, synthesis_data


def test_run_detail_includes_synthesis_content_for_completed_run(client, tmp_path):
    """GET /api/runs/{run_id} bundles synthesis_content for completed runs."""
    run_id = "synthbundle"
    _make_completed_run_dir(tmp_path, run_id, with_synthesis=True)

    resp = client.get(f"/api/runs/{run_id}?dir={tmp_path}")
    assert resp.status_code == 200
    body = resp.json()

    assert "synthesis_content" in body, "synthesis_content field must be present"
    assert body["synthesis_content"] is not None, "synthesis_content must be non-null for completed runs with synthesis"
    assert body["synthesis_content"]["summary"] == "Overall synthesis summary"
    assert body["synthesis_content"]["bottom_line_assessment"] == "Bottom line here"


def test_run_detail_includes_technique_summaries_for_completed_run(client, tmp_path):
    """GET /api/runs/{run_id} bundles technique_summaries for completed runs."""
    run_id = "summbundle"
    _make_completed_run_dir(tmp_path, run_id)

    resp = client.get(f"/api/runs/{run_id}?dir={tmp_path}")
    assert resp.status_code == 200
    body = resp.json()

    assert "technique_summaries" in body, "technique_summaries field must be present"
    assert body["technique_summaries"] is not None, "technique_summaries must be non-null for completed runs with artifacts"
    assert "key_assumptions_check" in body["technique_summaries"]
    assert body["technique_summaries"]["key_assumptions_check"] == "Key assumption summary text"


def test_run_detail_synthesis_content_none_when_no_synthesis_path(client, tmp_path):
    """synthesis_content is None when synthesis_path is absent."""
    run_id = "nosynthpath"
    _make_completed_run_dir(tmp_path, run_id, with_synthesis=False)

    resp = client.get(f"/api/runs/{run_id}?dir={tmp_path}")
    assert resp.status_code == 200
    body = resp.json()

    assert "synthesis_content" in body
    assert body["synthesis_content"] is None


def test_run_detail_synthesis_content_none_when_file_missing(client, tmp_path):
    """synthesis_content is None when synthesis_path is set but file is missing."""
    import json as _json

    run_id = "synthfilemiss"
    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    # synthesis_path points to a non-existent file
    manifest = {
        "run_id": run_id,
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "completed_at": "2025-01-01T01:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
        "synthesis_path": str(output_dir / "synthesis.json"),  # File won't exist
    }
    (output_dir / "manifest.json").write_text(_json.dumps(manifest))
    # synthesis.json is intentionally NOT created

    resp = client.get(f"/api/runs/{run_id}?dir={tmp_path}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["synthesis_content"] is None


def test_run_detail_technique_summaries_none_when_no_artifacts(client, tmp_path):
    """technique_summaries is None when there are no artifacts with json_path."""
    import json as _json

    run_id = "noartifacts"
    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    manifest = {
        "run_id": run_id,
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "completed_at": "2025-01-01T01:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
    }
    (output_dir / "manifest.json").write_text(_json.dumps(manifest))

    resp = client.get(f"/api/runs/{run_id}?dir={tmp_path}")
    assert resp.status_code == 200
    body = resp.json()

    assert "technique_summaries" in body
    assert body["technique_summaries"] is None


def test_run_detail_technique_summaries_skips_missing_files(client, tmp_path):
    """technique_summaries gracefully skips artifacts whose json_path files are missing."""
    import json as _json

    run_id = "summpartial"
    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    # Only one artifact has a real json_path file; the other points to a missing file
    real_data = {"technique_id": "acm", "technique_name": "ACM", "summary": "ACM summary"}
    real_file = output_dir / "01-acm.json"
    real_file.write_text(_json.dumps(real_data))

    manifest = {
        "run_id": run_id,
        "question": "Test?",
        "started_at": "2025-01-01T00:00:00Z",
        "completed_at": "2025-01-01T01:00:00Z",
        "techniques_selected": ["acm", "kac"],
        "techniques_completed": ["acm"],
        "artifacts": [
            {
                "technique_id": "acm",
                "technique_name": "ACM",
                "category": "diagnostic",
                "markdown_path": str(output_dir / "01-acm.md"),
                "json_path": str(real_file),
            },
            {
                "technique_id": "kac",
                "technique_name": "KAC",
                "category": "diagnostic",
                "markdown_path": str(output_dir / "02-kac.md"),
                "json_path": str(output_dir / "02-kac.json"),  # Does NOT exist
            },
        ],
    }
    (output_dir / "manifest.json").write_text(_json.dumps(manifest))

    resp = client.get(f"/api/runs/{run_id}?dir={tmp_path}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["technique_summaries"] is not None
    assert "acm" in body["technique_summaries"]
    assert body["technique_summaries"]["acm"] == "ACM summary"
    # kac file doesn't exist, so it should be absent (not cause an error)
    assert "kac" not in body["technique_summaries"]


def test_run_detail_synthesis_path_prefix_stripped(client, tmp_path):
    """synthesis_path with sat-{run_id}/ prefix is resolved correctly (DEC-API-008)."""
    import json as _json

    run_id = "synthprefix"
    output_dir = tmp_path / f"sat-{run_id}"
    output_dir.mkdir()

    synthesis_data = {
        "technique_id": "synthesis",
        "technique_name": "Synthesis",
        "summary": "Prefixed synthesis summary",
        "question": "What is happening?",
        "techniques_applied": [],
        "key_findings": [],
        "convergent_judgments": [],
        "divergent_signals": [],
        "highest_confidence_assessments": [],
        "remaining_uncertainties": [],
        "intelligence_gaps": [],
        "recommended_next_steps": [],
        "bottom_line_assessment": "Bottom line",
    }
    synthesis_file = output_dir / "synthesis.json"
    synthesis_file.write_text(_json.dumps(synthesis_data))

    # Manifest stores path with the run dir prefix (DEC-API-008 pattern)
    manifest = {
        "run_id": run_id,
        "question": "What is happening?",
        "started_at": "2025-01-01T00:00:00Z",
        "completed_at": "2025-01-01T01:00:00Z",
        "techniques_selected": [],
        "techniques_completed": [],
        "artifacts": [],
        "synthesis_path": f"sat-{run_id}/synthesis.json",  # prefixed path
    }
    (output_dir / "manifest.json").write_text(_json.dumps(manifest))

    resp = client.get(f"/api/runs/{run_id}?dir={tmp_path}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["synthesis_content"] is not None
    assert body["synthesis_content"]["summary"] == "Prefixed synthesis summary"
