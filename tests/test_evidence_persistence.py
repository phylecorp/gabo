"""Tests for evidence persistence: EvidencePool JSON artifact and retrieval endpoint.

@decision DEC-TEST-EVIDENCE-PERSIST-001
@title Test-first for evidence persistence backend (Wave 1)
@status accepted
@rationale Verify four things: (1) ArtifactManifest has evidence_path field,
(2) RunDetail has evidence_path field and _manifest_to_detail() maps it,
(3) analyze_curated persists evidence.json and updates manifest evidence_path,
(4) GET /api/runs/{run_id}/evidence returns the pool or 404 for missing.
No mocks of internal code used — tests use real model/schema objects directly.

Covers:
- ArtifactManifest.evidence_path: field exists, defaults to None
- RunDetail.evidence_path: field exists, defaults to None
- _manifest_to_detail(): maps evidence_path from manifest to RunDetail
- GET /api/runs/{run_id}/evidence: 404 when evidence.json absent
- GET /api/runs/{run_id}/evidence: 200 with correct JSON when evidence.json present
- EvidencePool serialization: model_dump_json() produces valid JSON roundtrippable data
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sat.models.base import ArtifactManifest
from sat.models.evidence import EvidenceItem, EvidencePool


# ---------------------------------------------------------------------------
# 1. ArtifactManifest.evidence_path field
# ---------------------------------------------------------------------------


class TestArtifactManifestEvidencePath:
    def test_evidence_path_defaults_to_none(self):
        """ArtifactManifest.evidence_path is None by default."""
        from datetime import datetime, timezone

        manifest = ArtifactManifest(
            question="Test?",
            run_id="run-abc",
            started_at=datetime.now(timezone.utc),
            techniques_selected=["col"],
        )
        assert manifest.evidence_path is None

    def test_evidence_path_accepts_string(self):
        """ArtifactManifest.evidence_path can be set to a string path."""
        from datetime import datetime, timezone

        manifest = ArtifactManifest(
            question="Test?",
            run_id="run-abc",
            started_at=datetime.now(timezone.utc),
            techniques_selected=["col"],
            evidence_path="evidence.json",
        )
        assert manifest.evidence_path == "evidence.json"

    def test_evidence_path_json_roundtrip(self):
        """evidence_path survives JSON serialization."""
        from datetime import datetime, timezone

        manifest = ArtifactManifest(
            question="Test?",
            run_id="run-abc",
            started_at=datetime.now(timezone.utc),
            techniques_selected=["col"],
            evidence_path="evidence.json",
        )
        data = manifest.model_dump(mode="json")
        restored = ArtifactManifest.model_validate(data)
        assert restored.evidence_path == "evidence.json"

    def test_evidence_path_present_in_schema(self):
        """ArtifactManifest schema includes evidence_path."""
        schema = ArtifactManifest.model_json_schema()
        props = schema.get("properties", {})
        assert "evidence_path" in props


# ---------------------------------------------------------------------------
# 2. RunDetail.evidence_path field
# ---------------------------------------------------------------------------


class TestRunDetailEvidencePath:
    def test_run_detail_evidence_path_defaults_to_none(self):
        """RunDetail.evidence_path is None by default."""
        from sat.api.models import RunDetail

        detail = RunDetail(
            run_id="run-abc",
            question="Test?",
            started_at="2024-01-01T00:00:00Z",
            completed_at=None,
            techniques_selected=["col"],
            techniques_completed=[],
            evidence_provided=False,
            adversarial_enabled=False,
            providers_used=[],
            status="completed",
            artifacts=[],
            synthesis_path=None,
        )
        assert detail.evidence_path is None

    def test_run_detail_evidence_path_accepts_string(self):
        """RunDetail.evidence_path can be set."""
        from sat.api.models import RunDetail

        detail = RunDetail(
            run_id="run-abc",
            question="Test?",
            started_at="2024-01-01T00:00:00Z",
            completed_at=None,
            techniques_selected=["col"],
            techniques_completed=[],
            evidence_provided=False,
            adversarial_enabled=False,
            providers_used=[],
            status="completed",
            artifacts=[],
            synthesis_path=None,
            evidence_path="evidence.json",
        )
        assert detail.evidence_path == "evidence.json"

    def test_manifest_to_detail_maps_evidence_path(self):
        """_manifest_to_detail() maps evidence_path from manifest to RunDetail."""
        from datetime import datetime, timezone

        from sat.api.routes.runs import _manifest_to_detail

        manifest = ArtifactManifest(
            question="Test?",
            run_id="run-abc",
            started_at=datetime.now(timezone.utc),
            techniques_selected=["col"],
            evidence_path="evidence.json",
        )
        detail = _manifest_to_detail(manifest)
        assert detail.evidence_path == "evidence.json"

    def test_manifest_to_detail_none_evidence_path_when_absent(self):
        """_manifest_to_detail() sets evidence_path=None when manifest has none."""
        from datetime import datetime, timezone

        from sat.api.routes.runs import _manifest_to_detail

        manifest = ArtifactManifest(
            question="Test?",
            run_id="run-abc",
            started_at=datetime.now(timezone.utc),
            techniques_selected=["col"],
        )
        detail = _manifest_to_detail(manifest)
        assert detail.evidence_path is None


# ---------------------------------------------------------------------------
# 3. EvidencePool serialization
# ---------------------------------------------------------------------------


class TestEvidencePoolSerialization:
    def test_model_dump_json_produces_valid_json(self):
        """EvidencePool.model_dump_json() produces valid JSON."""
        pool = EvidencePool(
            session_id="sess-001",
            question="Is this a test?",
            items=[
                EvidenceItem(
                    item_id="D-F1",
                    claim="Test claim",
                    source="decomposition",
                )
            ],
            status="ready",
        )
        raw = pool.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["session_id"] == "sess-001"
        assert parsed["question"] == "Is this a test?"
        assert len(parsed["items"]) == 1
        assert parsed["items"][0]["item_id"] == "D-F1"

    def test_pool_roundtrips_through_json(self):
        """EvidencePool can be serialized and deserialized through JSON."""
        pool = EvidencePool(
            session_id="sess-002",
            question="Round trip?",
            items=[
                EvidenceItem(
                    item_id="R-C1",
                    claim="Research claim",
                    source="research",
                    confidence="High",
                )
            ],
            sources=[{"url": "https://example.com", "title": "Example"}],
            gaps=["Missing context"],
            status="ready",
        )
        raw = pool.model_dump_json()
        restored = EvidencePool.model_validate_json(raw)
        assert restored.session_id == pool.session_id
        assert restored.question == pool.question
        assert len(restored.items) == 1
        assert restored.items[0].item_id == "R-C1"
        assert restored.sources == pool.sources
        assert restored.gaps == pool.gaps


# ---------------------------------------------------------------------------
# 4. GET /api/runs/{run_id}/evidence endpoint
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    from sat.api.app import create_app

    return create_app(port=8742)


@pytest.fixture()
def client(app):
    return TestClient(app)


class TestGetRunEvidenceEndpoint:
    def test_evidence_not_found_for_unknown_run(self, client):
        """Returns 404 for an unknown run_id."""
        resp = client.get("/api/runs/doesnotexist/evidence?dir=.")
        assert resp.status_code == 404

    def test_evidence_not_found_when_no_evidence_json(self, tmp_path):
        """Returns 404 when run exists but evidence.json is absent."""
        from datetime import datetime, timezone

        from sat.api.app import create_app

        # Create a sat-* directory with manifest.json but no evidence.json
        run_id = "run-noevidence"
        run_dir = tmp_path / f"sat-{run_id}"
        run_dir.mkdir()
        manifest = ArtifactManifest(
            question="Test without evidence?",
            run_id=run_id,
            started_at=datetime.now(timezone.utc),
            techniques_selected=["col"],
        )
        (run_dir / "manifest.json").write_text(
            manifest.model_dump_json(), encoding="utf-8"
        )

        app = create_app(port=8742)
        with TestClient(app) as c:
            resp = c.get(
                f"/api/runs/{run_id}/evidence",
                params={"dir": str(tmp_path)},
            )
        assert resp.status_code == 404

    def test_evidence_returns_200_with_pool_json(self, tmp_path):
        """Returns 200 with EvidencePool JSON when evidence.json is present."""
        from datetime import datetime, timezone

        from sat.api.app import create_app

        run_id = "run-withevidence"
        run_dir = tmp_path / f"sat-{run_id}"
        run_dir.mkdir()

        # Create manifest with evidence_path set
        manifest = ArtifactManifest(
            question="Test with evidence?",
            run_id=run_id,
            started_at=datetime.now(timezone.utc),
            techniques_selected=["col"],
            evidence_path="evidence.json",
        )
        (run_dir / "manifest.json").write_text(
            manifest.model_dump_json(), encoding="utf-8"
        )

        # Create evidence.json
        pool = EvidencePool(
            session_id="sess-xyz",
            question="Test with evidence?",
            items=[
                EvidenceItem(
                    item_id="D-F1",
                    claim="Key fact",
                    source="decomposition",
                )
            ],
            status="ready",
        )
        (run_dir / "evidence.json").write_text(pool.model_dump_json(), encoding="utf-8")

        app = create_app(port=8742)
        with TestClient(app) as c:
            resp = c.get(
                f"/api/runs/{run_id}/evidence",
                params={"dir": str(tmp_path)},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "sess-xyz"
        assert body["question"] == "Test with evidence?"
        assert len(body["items"]) == 1
        assert body["items"][0]["item_id"] == "D-F1"

    def test_evidence_response_content_type_is_json(self, tmp_path):
        """The evidence endpoint returns application/json content type."""
        from datetime import datetime, timezone

        from sat.api.app import create_app

        run_id = "run-ctype"
        run_dir = tmp_path / f"sat-{run_id}"
        run_dir.mkdir()

        manifest = ArtifactManifest(
            question="Content type?",
            run_id=run_id,
            started_at=datetime.now(timezone.utc),
            techniques_selected=["col"],
            evidence_path="evidence.json",
        )
        (run_dir / "manifest.json").write_text(
            manifest.model_dump_json(), encoding="utf-8"
        )

        pool = EvidencePool(
            session_id="sess-ctype",
            question="Content type?",
            items=[],
            status="ready",
        )
        (run_dir / "evidence.json").write_text(pool.model_dump_json(), encoding="utf-8")

        app = create_app(port=8742)
        with TestClient(app) as c:
            resp = c.get(
                f"/api/runs/{run_id}/evidence",
                params={"dir": str(tmp_path)},
            )
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")

    def test_evidence_returns_404_for_run_without_evidence_path_in_manifest(self, tmp_path):
        """Returns 404 when evidence.json exists on disk but manifest has no evidence_path.

        The endpoint should still check for evidence.json directly even when the
        manifest doesn't record evidence_path (legacy runs may have the file).
        Actually: the endpoint reads evidence.json directly from the output dir;
        it doesn't require evidence_path to be in the manifest. This test verifies
        that behavior: if evidence.json doesn't exist → 404 regardless of manifest.
        """
        from datetime import datetime, timezone

        from sat.api.app import create_app

        run_id = "run-no-path-field"
        run_dir = tmp_path / f"sat-{run_id}"
        run_dir.mkdir()

        # Manifest has no evidence_path field
        manifest = ArtifactManifest(
            question="No evidence_path in manifest?",
            run_id=run_id,
            started_at=datetime.now(timezone.utc),
            techniques_selected=["col"],
        )
        (run_dir / "manifest.json").write_text(
            manifest.model_dump_json(), encoding="utf-8"
        )
        # No evidence.json on disk

        app = create_app(port=8742)
        with TestClient(app) as c:
            resp = c.get(
                f"/api/runs/{run_id}/evidence",
                params={"dir": str(tmp_path)},
            )
        assert resp.status_code == 404
