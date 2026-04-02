"""Tests for POST /api/evidence/{session_id}/items endpoint.

@decision DEC-TEST-CREATE-001
@title Tests for manual evidence item creation POST endpoint
@status accepted
@rationale POST /api/evidence/{session_id}/items allows users to add their own evidence
items during the curation step (Gather & Review stage). Tests verify: successful creation,
sequential M-N IDs, source='manual', persistence to session pool, 404 for missing session,
409 for session not ready, and Pydantic validation for required claim field.

Covers:
- CreateEvidenceItemRequest model: required claim, defaults, min_length validation
- POST endpoint: 200 with new EvidenceItem for valid requests
- POST endpoint: auto-assigns M-1, M-2, ... IDs sequentially
- POST endpoint: new item has source='manual', selected=True
- POST endpoint: persists to pool so GET /api/evidence/{session_id} reflects the new item
- POST endpoint: 404 for missing session_id
- POST endpoint: 409 when session status is not 'ready'
- POST endpoint: 422 when claim is empty string (min_length=1 violated)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
from sat.api.models import CreateEvidenceItemRequest


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
def ready_session(client):
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
# Unit: CreateEvidenceItemRequest model
# ---------------------------------------------------------------------------


class TestCreateEvidenceItemRequest:
    def test_claim_required(self):
        """CreateEvidenceItemRequest requires claim field."""
        with pytest.raises(Exception):  # ValidationError from pydantic
            CreateEvidenceItemRequest()

    def test_claim_required_present(self):
        """CreateEvidenceItemRequest accepts a valid claim."""
        req = CreateEvidenceItemRequest(claim="Some claim text")
        assert req.claim == "Some claim text"

    def test_confidence_defaults_to_medium(self):
        """CreateEvidenceItemRequest defaults confidence to 'Medium'."""
        req = CreateEvidenceItemRequest(claim="Some claim")
        assert req.confidence == "Medium"

    def test_category_defaults_to_fact(self):
        """CreateEvidenceItemRequest defaults category to 'fact'."""
        req = CreateEvidenceItemRequest(claim="Some claim")
        assert req.category == "fact"

    def test_custom_confidence(self):
        """CreateEvidenceItemRequest accepts custom confidence."""
        req = CreateEvidenceItemRequest(claim="Claim", confidence="High")
        assert req.confidence == "High"

    def test_custom_category(self):
        """CreateEvidenceItemRequest accepts custom category."""
        req = CreateEvidenceItemRequest(claim="Claim", category="analysis")
        assert req.category == "analysis"

    def test_empty_claim_rejected(self):
        """CreateEvidenceItemRequest rejects empty string for claim (min_length=1)."""
        with pytest.raises(Exception):
            CreateEvidenceItemRequest(claim="")

    def test_claim_at_max_length(self):
        """CreateEvidenceItemRequest accepts claim at exactly max_length (5000 chars)."""
        long_claim = "x" * 5000
        req = CreateEvidenceItemRequest(claim=long_claim)
        assert len(req.claim) == 5000

    def test_claim_exceeds_max_length_rejected(self):
        """CreateEvidenceItemRequest rejects claim over 5000 chars."""
        with pytest.raises(Exception):
            CreateEvidenceItemRequest(claim="x" * 5001)


# ---------------------------------------------------------------------------
# POST /api/evidence/{session_id}/items — success cases
# ---------------------------------------------------------------------------


class TestPostEvidenceItemSuccess:
    def test_create_item_returns_200(self, client, ready_session):
        """POST returns 200 when creating a new evidence item."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": "My manually added evidence"},
        )
        assert resp.status_code == 200

    def test_created_item_has_claim(self, client, ready_session):
        """Created item body contains the submitted claim."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": "Specific claim content"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["claim"] == "Specific claim content"

    def test_created_item_has_manual_source(self, client, ready_session):
        """Created item has source='manual'."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": "Manual evidence"},
        )
        assert resp.status_code == 200
        assert resp.json()["source"] == "manual"

    def test_first_item_gets_m1_id(self, client, ready_session):
        """First manually created item gets ID 'M-1'."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": "First manual item"},
        )
        assert resp.status_code == 200
        assert resp.json()["item_id"] == "M-1"

    def test_second_item_gets_m2_id(self, client, ready_session):
        """Second manually created item gets ID 'M-2'."""
        session_id, _ = ready_session

        client.post(f"/api/evidence/{session_id}/items", json={"claim": "First"})
        resp = client.post(f"/api/evidence/{session_id}/items", json={"claim": "Second"})
        assert resp.status_code == 200
        assert resp.json()["item_id"] == "M-2"

    def test_created_item_is_selected_by_default(self, client, ready_session):
        """Created item has selected=True by default."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": "New item"},
        )
        assert resp.json()["selected"] is True

    def test_created_item_default_confidence_medium(self, client, ready_session):
        """Created item without explicit confidence gets 'Medium'."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": "New item"},
        )
        assert resp.json()["confidence"] == "Medium"

    def test_created_item_default_category_fact(self, client, ready_session):
        """Created item without explicit category gets 'fact'."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": "New item"},
        )
        assert resp.json()["category"] == "fact"

    def test_custom_confidence_and_category(self, client, ready_session):
        """Created item accepts custom confidence and category."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": "Projection item", "confidence": "High", "category": "projection"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["confidence"] == "High"
        assert body["category"] == "projection"

    def test_created_item_persists_to_pool(self, client, ready_session):
        """After POST, GET /api/evidence/{session_id} includes the new item."""
        session_id, _ = ready_session
        claim = "Persisted manual evidence"

        post_resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": claim},
        )
        assert post_resp.status_code == 200
        new_item_id = post_resp.json()["item_id"]

        pool_resp = client.get(f"/api/evidence/{session_id}")
        assert pool_resp.status_code == 200
        pool_items = pool_resp.json()["items"]
        item_ids = [i["item_id"] for i in pool_items]
        assert new_item_id in item_ids

        new_item = next(i for i in pool_items if i["item_id"] == new_item_id)
        assert new_item["claim"] == claim

    def test_existing_items_unaffected_by_create(self, client, ready_session):
        """Creating a new item does not change existing items in the pool."""
        session_id, original_items = ready_session
        original_count = len(original_items)

        client.post(f"/api/evidence/{session_id}/items", json={"claim": "New addition"})

        pool_resp = client.get(f"/api/evidence/{session_id}")
        pool_items = pool_resp.json()["items"]
        assert len(pool_items) == original_count + 1

        # Original item claims preserved
        original_claims = {i["claim"] for i in original_items}
        pool_claims = {i["claim"] for i in pool_items}
        assert original_claims.issubset(pool_claims)


# ---------------------------------------------------------------------------
# POST /api/evidence/{session_id}/items — error cases
# ---------------------------------------------------------------------------


class TestPostEvidenceItemErrors:
    def test_missing_session_returns_404(self, client):
        """POST with non-existent session_id returns 404."""
        resp = client.post(
            "/api/evidence/nonexistent-session/items",
            json={"claim": "New claim"},
        )
        assert resp.status_code == 404

    def test_session_not_ready_returns_409(self, client, app):
        """POST returns 409 when session exists but pool is not ready."""
        evidence_manager = app.state.evidence_manager
        session = evidence_manager.create_session()
        # Session starts with status='gathering' and pool=None

        resp = client.post(
            f"/api/evidence/{session.session_id}/items",
            json={"claim": "New claim"},
        )
        assert resp.status_code == 409

    def test_empty_claim_returns_422(self, client, ready_session):
        """POST with empty claim returns 422 (Pydantic validation error)."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"claim": ""},
        )
        assert resp.status_code == 422

    def test_missing_claim_returns_422(self, client, ready_session):
        """POST with no claim field returns 422."""
        session_id, _ = ready_session

        resp = client.post(
            f"/api/evidence/{session_id}/items",
            json={"confidence": "High"},
        )
        assert resp.status_code == 422
