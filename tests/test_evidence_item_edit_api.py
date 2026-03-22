"""Tests for PATCH /api/evidence/{session_id}/items/{item_id} endpoint.

@decision DEC-TEST-EDIT-001
@title Tests for evidence item editing PATCH endpoint
@status accepted
@rationale PATCH /api/evidence/{session_id}/items/{item_id} allows users to edit
claim, confidence, and category fields on individual evidence items during the curation
step (before analysis). Tests verify: successful field updates, partial updates (only
provided fields change), 404 for missing session or item, 409 for session not in
'ready' state, and that the model is updated in-place on the session pool.

Covers:
- UpdateEvidenceItemRequest model: optional fields, JSON serialization
- PATCH endpoint: 200 with updated EvidenceItem for valid updates
- PATCH endpoint: 404 for missing session_id
- PATCH endpoint: 404 for missing item_id within a valid session
- PATCH endpoint: 409 when session status is not 'ready' (pool is None)
- Partial update: only non-None fields are changed, others preserved
- Session pool is mutated in-place so GET /api/evidence/{session_id} reflects the change
- Empty PATCH (no fields) is a no-op returning the unchanged item
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
from sat.api.models import UpdateEvidenceItemRequest
from sat.models.evidence import EvidenceItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8742)


@pytest.fixture()
def client(app):
    return TestClient(app)


def _make_item(item_id: str, claim: str = "Test claim", confidence: str = "Medium", category: str = "fact") -> EvidenceItem:
    """Build a minimal EvidenceItem for testing."""
    return EvidenceItem(
        item_id=item_id,
        claim=claim,
        source="user",
        source_ids=[],
        category=category,
        confidence=confidence,
        entities=[],
        verified=False,
        selected=True,
    )


@pytest.fixture()
def ready_session(app, client):
    """Create an evidence session in 'ready' state via POST /api/evidence/pool."""
    resp = client.post(
        "/api/evidence/pool",
        json={
            "question": "What is the threat level?",
            "evidence": "First claim here.\n\nSecond claim here.",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    return body["session_id"], body["pool"]["items"]


# ---------------------------------------------------------------------------
# Unit: UpdateEvidenceItemRequest model
# ---------------------------------------------------------------------------


class TestUpdateEvidenceItemRequest:
    def test_all_fields_optional(self):
        """UpdateEvidenceItemRequest can be instantiated with no fields."""
        req = UpdateEvidenceItemRequest()
        assert req.claim is None
        assert req.confidence is None
        assert req.category is None

    def test_all_fields_provided(self):
        """UpdateEvidenceItemRequest accepts all fields."""
        req = UpdateEvidenceItemRequest(claim="New claim", confidence="High", category="analysis")
        assert req.claim == "New claim"
        assert req.confidence == "High"
        assert req.category == "analysis"

    def test_partial_fields(self):
        """UpdateEvidenceItemRequest accepts partial fields."""
        req = UpdateEvidenceItemRequest(claim="Only claim changed")
        assert req.claim == "Only claim changed"
        assert req.confidence is None
        assert req.category is None

    def test_json_roundtrip(self):
        """UpdateEvidenceItemRequest survives JSON serialization."""
        req = UpdateEvidenceItemRequest(claim="Roundtrip claim", confidence="Low")
        data = req.model_dump()
        restored = UpdateEvidenceItemRequest(**data)
        assert restored.claim == req.claim
        assert restored.confidence == req.confidence
        assert restored.category == req.category


# ---------------------------------------------------------------------------
# PATCH /api/evidence/{session_id}/items/{item_id} — success cases
# ---------------------------------------------------------------------------


class TestPatchEvidenceItemSuccess:
    def test_update_claim_returns_200(self, client, ready_session):
        """PATCH returns 200 with updated item when claim is changed."""
        session_id, items = ready_session
        item_id = items[0]["item_id"]

        resp = client.patch(
            f"/api/evidence/{session_id}/items/{item_id}",
            json={"claim": "Updated claim text"},
        )
        assert resp.status_code == 200

    def test_update_claim_reflects_in_response(self, client, ready_session):
        """Updated claim is returned in the response body."""
        session_id, items = ready_session
        item_id = items[0]["item_id"]

        resp = client.patch(
            f"/api/evidence/{session_id}/items/{item_id}",
            json={"claim": "Updated claim text"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["claim"] == "Updated claim text"
        assert body["item_id"] == item_id

    def test_update_confidence_returns_correct_value(self, client, ready_session):
        """Updated confidence is returned in the response body."""
        session_id, items = ready_session
        item_id = items[0]["item_id"]

        resp = client.patch(
            f"/api/evidence/{session_id}/items/{item_id}",
            json={"confidence": "High"},
        )
        assert resp.status_code == 200
        assert resp.json()["confidence"] == "High"

    def test_update_category_returns_correct_value(self, client, ready_session):
        """Updated category is returned in the response body."""
        session_id, items = ready_session
        item_id = items[0]["item_id"]

        resp = client.patch(
            f"/api/evidence/{session_id}/items/{item_id}",
            json={"category": "opinion"},
        )
        assert resp.status_code == 200
        assert resp.json()["category"] == "opinion"

    def test_update_all_fields_at_once(self, client, ready_session):
        """All three editable fields can be updated in one PATCH."""
        session_id, items = ready_session
        item_id = items[0]["item_id"]

        resp = client.patch(
            f"/api/evidence/{session_id}/items/{item_id}",
            json={
                "claim": "Fully updated claim",
                "confidence": "Low",
                "category": "projection",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["claim"] == "Fully updated claim"
        assert body["confidence"] == "Low"
        assert body["category"] == "projection"

    def test_update_persists_to_session_pool(self, client, ready_session):
        """After PATCH, GET /api/evidence/{session_id} reflects the updated claim."""
        session_id, items = ready_session
        item_id = items[0]["item_id"]
        new_claim = "Persisted claim update"

        patch_resp = client.patch(
            f"/api/evidence/{session_id}/items/{item_id}",
            json={"claim": new_claim},
        )
        assert patch_resp.status_code == 200

        pool_resp = client.get(f"/api/evidence/{session_id}")
        assert pool_resp.status_code == 200
        pool_items = pool_resp.json()["items"]
        updated = next(i for i in pool_items if i["item_id"] == item_id)
        assert updated["claim"] == new_claim

    def test_empty_patch_is_noop(self, client, ready_session):
        """PATCH with no fields returns the unchanged item."""
        session_id, items = ready_session
        item_id = items[0]["item_id"]
        original_claim = items[0]["claim"]

        resp = client.patch(
            f"/api/evidence/{session_id}/items/{item_id}",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["claim"] == original_claim

    def test_partial_update_preserves_other_fields(self, client, ready_session):
        """Updating only claim leaves confidence and category unchanged."""
        session_id, items = ready_session
        item_id = items[0]["item_id"]
        original_confidence = items[0]["confidence"]
        original_category = items[0]["category"]

        resp = client.patch(
            f"/api/evidence/{session_id}/items/{item_id}",
            json={"claim": "Only claim changed"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["confidence"] == original_confidence
        assert body["category"] == original_category

    def test_other_items_unchanged_after_patch(self, client, ready_session):
        """Patching one item does not modify other items in the pool."""
        session_id, items = ready_session
        # Patch the first item
        item_id_0 = items[0]["item_id"]
        item_id_1 = items[1]["item_id"]
        original_claim_1 = items[1]["claim"]

        client.patch(
            f"/api/evidence/{session_id}/items/{item_id_0}",
            json={"claim": "Changed claim"},
        )

        pool_resp = client.get(f"/api/evidence/{session_id}")
        pool_items = pool_resp.json()["items"]
        item_1 = next(i for i in pool_items if i["item_id"] == item_id_1)
        assert item_1["claim"] == original_claim_1


# ---------------------------------------------------------------------------
# PATCH /api/evidence/{session_id}/items/{item_id} — error cases
# ---------------------------------------------------------------------------


class TestPatchEvidenceItemErrors:
    def test_missing_session_returns_404(self, client):
        """PATCH with non-existent session_id returns 404."""
        resp = client.patch(
            "/api/evidence/nonexistent-session/items/U-1",
            json={"claim": "New claim"},
        )
        assert resp.status_code == 404

    def test_missing_item_returns_404(self, client, ready_session):
        """PATCH with non-existent item_id within valid session returns 404."""
        session_id, _ = ready_session

        resp = client.patch(
            f"/api/evidence/{session_id}/items/NONEXISTENT-ITEM",
            json={"claim": "New claim"},
        )
        assert resp.status_code == 404

    def test_session_not_ready_returns_409(self, client, app):
        """PATCH returns 409 when session exists but pool is not ready (pool is None)."""
        # Create a bare session with status != 'ready' by manipulating the manager directly
        evidence_manager = app.state.evidence_manager
        session = evidence_manager.create_session()
        # Session starts with status='gathering' and pool=None

        resp = client.patch(
            f"/api/evidence/{session.session_id}/items/U-1",
            json={"claim": "New claim"},
        )
        assert resp.status_code == 409
