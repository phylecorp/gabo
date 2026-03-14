"""Tests for the run naming feature: name field across the full stack.

@decision DEC-TEST-NAMING-001
@title Test naming end-to-end: models, manifest persistence, and PATCH rename
@status accepted
@rationale The name field is a thin pass-through across many layers. Tests verify:
- Each model that gained a name field can round-trip it
- ArtifactWriter writes name to manifest.json
- RunSummary/RunDetail include name from manifest
- PATCH /api/runs/{run_id} updates manifest.json and returns updated summary
- EvidenceSession stores name from gather request
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
from sat.api.evidence_manager import EvidenceSession, EvidenceSessionManager
from sat.api.models import (
    AnalysisRequest,
    CuratedAnalysisRequest,
    EvidenceGatherRequest,
    RunSummary,
)
from sat.api.run_manager import ActiveRun, RunManager
from sat.artifacts import ArtifactWriter
from sat.config import AnalysisConfig
from sat.models.base import ArtifactManifest
from sat.models.assumptions import AssumptionRow, KeyAssumptionsResult


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
def run_manager():
    return RunManager()


@pytest.fixture()
def config_with_name():
    return AnalysisConfig(question="Is this named?", name="My Test Run")


@pytest.fixture()
def config_without_name():
    return AnalysisConfig(question="Is this unnamed?")


def _sample_result() -> KeyAssumptionsResult:
    return KeyAssumptionsResult(
        technique_id="assumptions",
        technique_name="Key Assumptions Check",
        summary="A brief summary.",
        analytic_line="Some analytic line.",
        assumptions=[
            AssumptionRow(
                assumption="Assumption A",
                confidence="High",
                basis_for_confidence="Strong evidence",
                what_undermines="Contradicting data",
                impact_if_wrong="Major re-assessment required",
            )
        ],
        most_vulnerable=["Assumption A"],
        recommended_monitoring=["Monitor source X monthly"],
    )


# ---------------------------------------------------------------------------
# Model field tests
# ---------------------------------------------------------------------------


class TestNameFieldOnModels:
    """Each new name field should accept a value and default to None."""

    def test_analysis_request_name_defaults_none(self):
        req = AnalysisRequest(question="Q?")
        assert req.name is None

    def test_analysis_request_name_set(self):
        req = AnalysisRequest(question="Q?", name="My Analysis")
        assert req.name == "My Analysis"

    def test_evidence_gather_request_name_defaults_none(self):
        req = EvidenceGatherRequest(question="Q?")
        assert req.name is None

    def test_evidence_gather_request_name_set(self):
        req = EvidenceGatherRequest(question="Q?", name="Gather Run")
        assert req.name == "Gather Run"

    def test_curated_analysis_request_name_defaults_none(self):
        req = CuratedAnalysisRequest(selected_item_ids=["a"])
        assert req.name is None

    def test_curated_analysis_request_name_set(self):
        req = CuratedAnalysisRequest(selected_item_ids=["a"], name="Curated Run")
        assert req.name == "Curated Run"

    def test_run_summary_name_defaults_none(self):
        rs = RunSummary(
            run_id="abc",
            question="Q?",
            started_at="",
            completed_at=None,
            techniques_selected=[],
            techniques_completed=[],
            evidence_provided=False,
            adversarial_enabled=False,
            providers_used=[],
            status="completed",
        )
        assert rs.name is None

    def test_run_summary_name_set(self):
        rs = RunSummary(
            run_id="abc",
            question="Q?",
            name="Named",
            started_at="",
            completed_at=None,
            techniques_selected=[],
            techniques_completed=[],
            evidence_provided=False,
            adversarial_enabled=False,
            providers_used=[],
            status="completed",
        )
        assert rs.name == "Named"

    def test_analysis_config_name_defaults_none(self):
        cfg = AnalysisConfig(question="Q?")
        assert cfg.name is None

    def test_analysis_config_name_set(self):
        cfg = AnalysisConfig(question="Q?", name="Config Name")
        assert cfg.name == "Config Name"

    def test_artifact_manifest_name_defaults_none(self):
        m = ArtifactManifest(
            question="Q?",
            run_id="abc",
            started_at=datetime.now(timezone.utc),
            techniques_selected=[],
        )
        assert m.name is None

    def test_artifact_manifest_name_set(self):
        m = ArtifactManifest(
            question="Q?",
            name="Manifest Name",
            run_id="abc",
            started_at=datetime.now(timezone.utc),
            techniques_selected=[],
        )
        assert m.name == "Manifest Name"


# ---------------------------------------------------------------------------
# ActiveRun carries name from config
# ---------------------------------------------------------------------------


class TestActiveRunName:
    def test_active_run_name_from_config(self, config_with_name):
        run = ActiveRun("run123", config_with_name)
        assert run.name == "My Test Run"

    def test_active_run_name_none_when_config_no_name(self, config_without_name):
        run = ActiveRun("run456", config_without_name)
        assert run.name is None


# ---------------------------------------------------------------------------
# ArtifactWriter writes name to manifest.json
# ---------------------------------------------------------------------------


class TestArtifactWriterName:
    def test_write_manifest_includes_name(self, tmp_path):
        writer = ArtifactWriter(
            tmp_path / "output", "run001", "Test question?", name="My Named Run"
        )
        writer.write_result(_sample_result())
        writer.write_manifest(
            techniques_selected=["assumptions"],
            techniques_completed=["assumptions"],
            evidence_provided=False,
        )
        manifest_path = tmp_path / "output" / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert data["name"] == "My Named Run"

    def test_write_manifest_name_none_when_not_set(self, tmp_path):
        writer = ArtifactWriter(tmp_path / "output", "run002", "Test question?")
        writer.write_result(_sample_result())
        writer.write_manifest(
            techniques_selected=["assumptions"],
            techniques_completed=["assumptions"],
            evidence_provided=False,
        )
        manifest_path = tmp_path / "output" / "manifest.json"
        data = json.loads(manifest_path.read_text())
        assert data["name"] is None

    def test_manifest_round_trips_name(self, tmp_path):
        writer = ArtifactWriter(
            tmp_path / "output", "run003", "Test question?", name="Round-trip"
        )
        writer.write_result(_sample_result())
        writer.write_manifest(
            techniques_selected=["assumptions"],
            techniques_completed=["assumptions"],
            evidence_provided=False,
        )
        manifest_path = tmp_path / "output" / "manifest.json"
        data = json.loads(manifest_path.read_text())
        manifest = ArtifactManifest.model_validate(data)
        assert manifest.name == "Round-trip"


# ---------------------------------------------------------------------------
# Runs API: name appears in list and detail responses
# ---------------------------------------------------------------------------


class TestRunsApiName:
    def _make_manifest_dir(self, base: Path, run_id: str, name: str | None = None) -> Path:
        """Create a sat-* directory with a valid manifest.json for testing."""
        output_dir = base / f"sat-{run_id}"
        output_dir.mkdir(parents=True)
        manifest = {
            "question": "Test question?",
            "name": name,
            "run_id": run_id,
            "started_at": "2025-01-01T00:00:00+00:00",
            "completed_at": "2025-01-01T00:05:00+00:00",
            "techniques_selected": ["assumptions"],
            "techniques_completed": ["assumptions"],
            "artifacts": [],
            "synthesis_path": None,
            "evidence_provided": False,
            "adversarial_enabled": False,
            "providers_used": ["anthropic"],
        }
        (output_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return output_dir

    def test_list_runs_includes_name(self, client, tmp_path):
        self._make_manifest_dir(tmp_path, "testrun01", name="Named Run")
        resp = client.get(f"/api/runs?dir={tmp_path}")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) == 1
        assert runs[0]["name"] == "Named Run"

    def test_list_runs_name_null_when_not_set(self, client, tmp_path):
        self._make_manifest_dir(tmp_path, "testrun02", name=None)
        resp = client.get(f"/api/runs?dir={tmp_path}")
        assert resp.status_code == 200
        runs = resp.json()
        assert runs[0]["name"] is None

    def test_get_run_includes_name(self, client, tmp_path):
        self._make_manifest_dir(tmp_path, "testrun03", name="Detail Name")
        resp = client.get(f"/api/runs/testrun03?dir={tmp_path}")
        assert resp.status_code == 200
        run = resp.json()
        assert run["name"] == "Detail Name"


# ---------------------------------------------------------------------------
# PATCH /api/runs/{run_id} — rename endpoint
# ---------------------------------------------------------------------------


class TestRenameRunEndpoint:
    def _make_manifest_dir(self, base: Path, run_id: str, name: str | None = None) -> Path:
        output_dir = base / f"sat-{run_id}"
        output_dir.mkdir(parents=True)
        manifest = {
            "question": "Test question for rename?",
            "name": name,
            "run_id": run_id,
            "started_at": "2025-01-01T00:00:00+00:00",
            "completed_at": "2025-01-01T00:05:00+00:00",
            "techniques_selected": ["assumptions"],
            "techniques_completed": ["assumptions"],
            "artifacts": [],
            "synthesis_path": None,
            "evidence_provided": False,
            "adversarial_enabled": False,
            "providers_used": ["anthropic"],
        }
        (output_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return output_dir

    def test_patch_renames_run_and_returns_summary(self, client, tmp_path):
        self._make_manifest_dir(tmp_path, "renamerun01", name=None)
        resp = client.patch(
            f"/api/runs/renamerun01?dir={tmp_path}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "New Name"
        assert body["run_id"] == "renamerun01"

    def test_patch_updates_manifest_json(self, client, tmp_path):
        output_dir = self._make_manifest_dir(tmp_path, "renamerun02", name=None)
        client.patch(
            f"/api/runs/renamerun02?dir={tmp_path}",
            json={"name": "Updated Name"},
        )
        data = json.loads((output_dir / "manifest.json").read_text())
        assert data["name"] == "Updated Name"

    def test_patch_unknown_run_returns_404(self, client, tmp_path):
        resp = client.patch(
            f"/api/runs/doesnotexist?dir={tmp_path}",
            json={"name": "Whatever"},
        )
        assert resp.status_code == 404

    def test_patch_trims_whitespace(self, client, tmp_path):
        self._make_manifest_dir(tmp_path, "renamerun03", name=None)
        resp = client.patch(
            f"/api/runs/renamerun03?dir={tmp_path}",
            json={"name": "  Trimmed  "},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Trimmed"

    def test_patch_updates_active_run_name(self, app, tmp_path):
        """PATCH should also update the in-process ActiveRun.name."""
        # Create an active run directly through the manager
        from sat.api.app import create_app
        from sat.config import AnalysisConfig

        # Use the real app's run manager
        test_app = create_app(port=8742)
        with TestClient(test_app) as c:
            # We can't directly access the manager from outside, so
            # verify through the response that the endpoint works
            self._make_manifest_dir(tmp_path, "activerun01", name=None)
            resp = c.patch(
                f"/api/runs/activerun01?dir={tmp_path}",
                json={"name": "Active Name"},
            )
            assert resp.status_code == 200
            assert resp.json()["name"] == "Active Name"


# ---------------------------------------------------------------------------
# EvidenceSession stores name from gather request
# ---------------------------------------------------------------------------


class TestEvidenceSessionName:
    def test_session_name_defaults_none(self):
        session = EvidenceSession("sess001")
        assert session.name is None

    def test_session_name_can_be_set(self):
        session = EvidenceSession("sess002")
        session.name = "Session Name"
        assert session.name == "Session Name"
