"""Tests for POST /api/evidence/pool/import endpoint.

@decision DEC-TEST-IMPORT-001
@title Tests for evidence pool import endpoint (re-analyze flow)
@status accepted
@rationale POST /api/evidence/pool/import accepts a complete EvidencePool verbatim
and returns it under a fresh session_id. This enables the re-analyze flow: a prior
run's evidence pool is carried forward to a new analysis session without any LLM
calls or re-gathering. Tests verify: successful import, fresh session_id, items
preserved, session status is 'ready', and empty pool import works.

Covers:
- POST /api/evidence/pool/import: 200 with new session_id and preserved pool
- POST /api/evidence/pool/import: session_id in response differs from input
- POST /api/evidence/pool/import: items count preserved
- POST /api/evidence/pool/import: item fields preserved (IDs, claims, metadata)
- POST /api/evidence/pool/import: session status is 'ready' immediately
- POST /api/evidence/pool/import: GET /api/evidence/{session_id} returns imported pool
- POST /api/evidence/pool/import: empty pool import succeeds
- POST /api/evidence/pool/import: 422 for missing required fields (question)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8743)


@pytest.fixture()
def client(app):
    return TestClient(app)


def _make_pool_payload(
    session_id: str = "prior-session-abc",
    question: str = "What is the threat level?",
    items: list[dict] | None = None,
) -> dict:
    """Build a minimal EvidencePool JSON payload for import."""
    if items is None:
        items = [
            {
                "item_id": "D-F1",
                "claim": "Threat level is elevated",
                "source": "decomposition",
                "source_ids": [],
                "category": "fact",
                "confidence": "High",
                "entities": ["Threat"],
                "verified": False,
                "selected": True,
                "provider_name": None,
            },
            {
                "item_id": "R-C1",
                "claim": "Recent incidents suggest escalation",
                "source": "research",
                "source_ids": ["https://example.com"],
                "category": "analysis",
                "confidence": "Medium",
                "entities": [],
                "verified": True,
                "selected": True,
                "provider_name": "perplexity",
            },
        ]
    return {
        "session_id": session_id,
        "question": question,
        "items": items,
        "sources": [{"url": "https://example.com", "title": "Example"}],
        "gaps": ["More data needed on X"],
        "provider_summary": "1 provider queried",
        "status": "ready",
        "error": None,
    }


# ---------------------------------------------------------------------------
# POST /api/evidence/pool/import — success cases
# ---------------------------------------------------------------------------


class TestImportPoolSuccess:
    def test_import_returns_200(self, client):
        """POST /api/evidence/pool/import returns 200 for a valid pool."""
        resp = client.post("/api/evidence/pool/import", json=_make_pool_payload())
        assert resp.status_code == 200

    def test_import_returns_session_id(self, client):
        """Import response contains a non-empty session_id."""
        resp = client.post("/api/evidence/pool/import", json=_make_pool_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert "session_id" in body
        assert body["session_id"]  # non-empty

    def test_import_returns_pool(self, client):
        """Import response contains a pool object."""
        resp = client.post("/api/evidence/pool/import", json=_make_pool_payload())
        body = resp.json()
        assert "pool" in body
        assert isinstance(body["pool"], dict)

    def test_import_session_id_is_fresh(self, client):
        """Imported session_id must differ from the prior run's session_id."""
        prior_session_id = "prior-run-session-xyz"
        payload = _make_pool_payload(session_id=prior_session_id)
        resp = client.post("/api/evidence/pool/import", json=payload)
        body = resp.json()
        assert body["session_id"] != prior_session_id

    def test_import_pool_session_id_matches_response(self, client):
        """Pool's session_id in response matches top-level session_id."""
        resp = client.post("/api/evidence/pool/import", json=_make_pool_payload())
        body = resp.json()
        assert body["pool"]["session_id"] == body["session_id"]

    def test_import_items_count_preserved(self, client):
        """Item count in imported pool matches original."""
        payload = _make_pool_payload()
        original_count = len(payload["items"])
        resp = client.post("/api/evidence/pool/import", json=payload)
        body = resp.json()
        assert len(body["pool"]["items"]) == original_count

    def test_import_item_ids_preserved(self, client):
        """Item IDs are preserved exactly from the original pool."""
        payload = _make_pool_payload()
        original_ids = [item["item_id"] for item in payload["items"]]
        resp = client.post("/api/evidence/pool/import", json=payload)
        body = resp.json()
        imported_ids = [item["item_id"] for item in body["pool"]["items"]]
        assert imported_ids == original_ids

    def test_import_item_claims_preserved(self, client):
        """Item claims are preserved exactly from the original pool."""
        payload = _make_pool_payload()
        original_claims = [item["claim"] for item in payload["items"]]
        resp = client.post("/api/evidence/pool/import", json=payload)
        body = resp.json()
        imported_claims = [item["claim"] for item in body["pool"]["items"]]
        assert imported_claims == original_claims

    def test_import_item_metadata_preserved(self, client):
        """Item metadata (confidence, category, source, verified) is preserved."""
        payload = _make_pool_payload()
        first_item = payload["items"][0]
        resp = client.post("/api/evidence/pool/import", json=payload)
        body = resp.json()
        imported_first = body["pool"]["items"][0]
        assert imported_first["confidence"] == first_item["confidence"]
        assert imported_first["category"] == first_item["category"]
        assert imported_first["source"] == first_item["source"]
        assert imported_first["verified"] == first_item["verified"]
        assert imported_first["selected"] == first_item["selected"]

    def test_import_question_preserved(self, client):
        """Question is preserved from the original pool."""
        question = "Is there an imminent threat to the region?"
        payload = _make_pool_payload(question=question)
        resp = client.post("/api/evidence/pool/import", json=payload)
        body = resp.json()
        assert body["pool"]["question"] == question

    def test_import_session_immediately_ready(self, client, app):
        """Imported session is immediately in 'ready' status — no gathering needed."""
        resp = client.post("/api/evidence/pool/import", json=_make_pool_payload())
        body = resp.json()
        session_id = body["session_id"]

        # Look up the session directly via the evidence manager
        evidence_manager = app.state.evidence_manager
        session = evidence_manager.get_session(session_id)
        assert session is not None
        assert session.status == "ready"

    def test_import_session_pool_accessible_via_get(self, client):
        """After import, GET /api/evidence/{session_id} returns the imported pool."""
        payload = _make_pool_payload()
        import_resp = client.post("/api/evidence/pool/import", json=payload)
        session_id = import_resp.json()["session_id"]

        get_resp = client.get(f"/api/evidence/{session_id}")
        assert get_resp.status_code == 200
        pool = get_resp.json()
        assert pool["question"] == payload["question"]
        assert len(pool["items"]) == len(payload["items"])

    def test_import_two_sessions_get_different_ids(self, client):
        """Two separate imports produce two distinct session IDs."""
        resp1 = client.post("/api/evidence/pool/import", json=_make_pool_payload())
        resp2 = client.post("/api/evidence/pool/import", json=_make_pool_payload())
        assert resp1.json()["session_id"] != resp2.json()["session_id"]


# ---------------------------------------------------------------------------
# POST /api/evidence/pool/import — empty pool
# ---------------------------------------------------------------------------


class TestImportEmptyPool:
    def test_empty_pool_import_succeeds(self, client):
        """Importing a pool with no items succeeds."""
        payload = _make_pool_payload(items=[])
        resp = client.post("/api/evidence/pool/import", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["pool"]["items"] == []
        assert body["session_id"]  # still gets a session

    def test_empty_pool_session_is_ready(self, client, app):
        """Empty pool import session is immediately 'ready'."""
        payload = _make_pool_payload(items=[])
        resp = client.post("/api/evidence/pool/import", json=payload)
        session_id = resp.json()["session_id"]
        evidence_manager = app.state.evidence_manager
        session = evidence_manager.get_session(session_id)
        assert session.status == "ready"


# ---------------------------------------------------------------------------
# POST /api/evidence/pool/import — imported session usable for analysis
# ---------------------------------------------------------------------------


class TestImportSessionUsableForAnalysis:
    def test_imported_session_is_analyzable(self, client):
        """An imported session can be used as input to POST /{session_id}/analyze.

        We only verify the analyze endpoint accepts the session (returns 200 and
        run_id), not that the full pipeline runs — that would require real LLM keys.
        The endpoint accepts 'ready' sessions; if the session is missing or not ready
        it returns 4xx. A 200 with run_id proves the session is properly wired.

        Sources are left empty to avoid the formatter's id/title/source_type constraint
        — the integration being tested here is session wiring, not evidence formatting.
        """
        # Import a pool with no sources to avoid formatter key constraints
        payload = _make_pool_payload()
        payload["sources"] = []  # Empty sources: avoid formatter expecting id/title/source_type
        import_resp = client.post("/api/evidence/pool/import", json=payload)
        assert import_resp.status_code == 200
        session_id = import_resp.json()["session_id"]

        # Try to start analysis — should be accepted (200), not rejected (4xx)
        analyze_resp = client.post(
            f"/api/evidence/{session_id}/analyze",
            json={
                "selected_item_ids": ["D-F1", "R-C1"],
                "provider": "anthropic",
            },
        )
        # 200 means the session was found and accepted; pipeline is queued
        assert analyze_resp.status_code == 200
        body = analyze_resp.json()
        assert "run_id" in body


# ---------------------------------------------------------------------------
# POST /api/evidence/pool/import — error cases
# ---------------------------------------------------------------------------


class TestImportPoolErrors:
    def test_missing_question_returns_422(self, client):
        """POST without 'question' field returns 422 (validation error)."""
        payload = _make_pool_payload()
        del payload["question"]
        resp = client.post("/api/evidence/pool/import", json=payload)
        assert resp.status_code == 422

    def test_missing_session_id_returns_422(self, client):
        """POST without 'session_id' field returns 422 (validation error)."""
        payload = _make_pool_payload()
        del payload["session_id"]
        resp = client.post("/api/evidence/pool/import", json=payload)
        assert resp.status_code == 422
