"""Tests for POST /api/evidence/pool endpoint.

@decision DEC-TEST-POOL-001
@title Tests for synchronous pool creation endpoint
@status accepted
@rationale POST /api/evidence/pool creates a structured EvidencePool from raw text
and/or document sources without LLM calls. Tests verify the full endpoint contract:
paragraph splitting from text, document ingestion (mocked at the ingest_evidence
boundary), empty input, session creation, and session status transitions.

Covers:
- PoolRequest / PoolResponse model contracts
- POST /api/evidence/pool with text only → paragraph-split EvidenceItems with U- prefix
- POST /api/evidence/pool with empty/None text → pool has no items
- POST /api/evidence/pool with evidence_sources → document-derived EvidenceItems
- POST /api/evidence/pool with both text and sources → merged items
- Verify session is created and pool is stored on the session
- Verify session status is "ready" so analyze_curated can be called immediately
- Verify PoolResponse contains session_id and pool fields
- Verify POST /api/evidence/{session_id}/analyze works after pool creation
"""

# @mock-exempt: ingest_evidence is an external-boundary function — it performs
# filesystem I/O (local file parsing via Docling) and HTTP fetches (URL sources).
# Using real file fixtures for multi-format document parsing (PDF, DOCX, images)
# would require heavy optional dependencies and actual binary test fixtures.
# The mock is placed exactly at the public API boundary (sat.ingestion.ingest_evidence),
# not inside any internal module, matching the policy for external service boundaries.

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
from sat.api.models import PoolRequest, PoolResponse
from sat.models.evidence import EvidencePool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8742)


@pytest.fixture()
def client(app):
    return TestClient(app)


def _make_ingestion_result(docs=None):
    """Build a minimal IngestionResult for testing.

    Uses real model objects (IngestionResult, ParsedDocument) — no mocking
    of internals. This is a factory/fixture helper pattern.
    """
    from sat.models.ingestion import IngestionResult

    if docs is None:
        docs = []
    combined = "\n\n".join(
        f"--- Source: {d.source_name} ---\n{d.markdown}" for d in docs
    )
    return IngestionResult(
        documents=docs,
        combined_markdown=combined,
        source_manifest=[
            {
                "name": d.source_name,
                "type": d.source_type,
                "word_count": len(d.markdown.split()),
                "warnings": d.parse_warnings,
            }
            for d in docs
        ],
        total_estimated_tokens=len(combined.split()),
        warnings=[],
        summary=f"Ingested {len(docs)} source(s)",
    )


def _make_parsed_doc(name: str, markdown: str, source_type: str = "text"):
    """Build a real ParsedDocument for use in ingestion result factories."""
    from sat.models.ingestion import ParsedDocument

    return ParsedDocument(
        source_id=name[:8],
        source_name=name,
        source_type=source_type,
        markdown=markdown,
    )


# ---------------------------------------------------------------------------
# Unit: PoolRequest model
# ---------------------------------------------------------------------------


class TestPoolRequestModel:
    def test_pool_request_requires_question(self):
        """PoolRequest requires a question field."""
        with pytest.raises(Exception):
            PoolRequest()  # type: ignore[call-arg]

    def test_pool_request_minimal(self):
        """PoolRequest accepts just a question."""
        req = PoolRequest(question="What happened?")
        assert req.question == "What happened?"
        assert req.name is None
        assert req.evidence is None
        assert req.evidence_sources is None

    def test_pool_request_with_all_fields(self):
        """PoolRequest accepts all optional fields."""
        req = PoolRequest(
            question="Test?",
            name="My Pool",
            evidence="Some text here.",
            evidence_sources=["/tmp/report.pdf"],
        )
        assert req.name == "My Pool"
        assert req.evidence == "Some text here."
        assert req.evidence_sources == ["/tmp/report.pdf"]

    def test_pool_request_evidence_sources_defaults_to_none(self):
        """evidence_sources defaults to None."""
        req = PoolRequest(question="Q?")
        assert req.evidence_sources is None

    def test_pool_request_json_roundtrip(self):
        """PoolRequest survives JSON serialization."""
        req = PoolRequest(
            question="Test?",
            name="Pool",
            evidence="para1\n\npara2",
            evidence_sources=["/tmp/a.pdf"],
        )
        data = req.model_dump()
        restored = PoolRequest(**data)
        assert restored.question == req.question
        assert restored.evidence == req.evidence
        assert restored.evidence_sources == req.evidence_sources


class TestPoolResponseModel:
    def test_pool_response_fields(self):
        """PoolResponse contains session_id and pool."""
        pool = EvidencePool(session_id="abc", question="Q?", status="ready")
        resp = PoolResponse(session_id="abc", pool=pool)
        assert resp.session_id == "abc"
        assert resp.pool is pool

    def test_pool_response_json_serializable(self):
        """PoolResponse is JSON serializable."""
        pool = EvidencePool(session_id="abc", question="Q?", status="ready")
        resp = PoolResponse(session_id="abc", pool=pool)
        data = resp.model_dump()
        assert "session_id" in data
        assert "pool" in data


# ---------------------------------------------------------------------------
# POST /api/evidence/pool — endpoint tests (text only)
# ---------------------------------------------------------------------------


class TestPoolEndpointTextOnly:
    def test_missing_question_returns_422(self, client):
        """POST /api/evidence/pool without question returns 422."""
        resp = client.post("/api/evidence/pool", json={})
        assert resp.status_code == 422

    def test_text_only_returns_200(self, client):
        """POST /api/evidence/pool with text returns 200."""
        resp = client.post(
            "/api/evidence/pool",
            json={
                "question": "What is the unemployment rate?",
                "evidence": "Unemployment rose last quarter.\n\nData shows 5% rate.",
            },
        )
        assert resp.status_code == 200

    def test_text_produces_paragraph_split_items(self, client):
        """Text is split on double newlines into U- prefixed EvidenceItems."""
        resp = client.post(
            "/api/evidence/pool",
            json={
                "question": "What happened?",
                "evidence": "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph.",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        items = body["pool"]["items"]
        assert len(items) == 3
        for item in items:
            assert item["item_id"].startswith("U-")
            assert item["source"] == "user"

    def test_text_items_content_matches_paragraphs(self, client):
        """Items claim text matches the original paragraphs."""
        para1 = "Unemployment rose to 5% last quarter."
        para2 = "Inflation is at 3.2% year over year."
        resp = client.post(
            "/api/evidence/pool",
            json={
                "question": "What is the economic situation?",
                "evidence": f"{para1}\n\n{para2}",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        claims = [item["claim"] for item in body["pool"]["items"]]
        assert para1 in claims
        assert para2 in claims

    def test_single_paragraph_produces_one_item(self, client):
        """Single block of text (no double newlines) produces one item."""
        resp = client.post(
            "/api/evidence/pool",
            json={
                "question": "What is the situation?",
                "evidence": "A single paragraph with no double newlines.",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        items = body["pool"]["items"]
        assert len(items) == 1
        assert items[0]["item_id"] == "U-1"

    def test_empty_text_produces_no_items(self, client):
        """Empty string evidence produces zero items."""
        resp = client.post(
            "/api/evidence/pool",
            json={
                "question": "What is the situation?",
                "evidence": "",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pool"]["items"] == []

    def test_no_evidence_produces_no_items(self, client):
        """Omitting evidence entirely produces zero items."""
        resp = client.post(
            "/api/evidence/pool",
            json={"question": "What is the situation?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pool"]["items"] == []


# ---------------------------------------------------------------------------
# POST /api/evidence/pool — session lifecycle
# ---------------------------------------------------------------------------


class TestPoolEndpointSessionLifecycle:
    def test_returns_session_id(self, client):
        """PoolResponse includes a non-empty session_id."""
        resp = client.post(
            "/api/evidence/pool",
            json={"question": "Test?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "session_id" in body
        assert body["session_id"]  # non-empty

    def test_session_status_is_ready(self, client):
        """Session is accessible via GET and its status is 'ready'."""
        resp = client.post(
            "/api/evidence/pool",
            json={
                "question": "What happened?",
                "evidence": "Some evidence text.",
            },
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        pool_resp = client.get(f"/api/evidence/{session_id}")
        assert pool_resp.status_code == 200
        assert pool_resp.json()["status"] == "ready"

    def test_pool_stored_on_session(self, client):
        """Pool items are accessible via GET /api/evidence/{session_id}."""
        resp = client.post(
            "/api/evidence/pool",
            json={
                "question": "What happened?",
                "evidence": "Para one.\n\nPara two.",
            },
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        pool_resp = client.get(f"/api/evidence/{session_id}")
        assert pool_resp.status_code == 200
        pool_body = pool_resp.json()
        assert len(pool_body["items"]) == 2

    def test_session_ready_allows_analyze_curated(self, client):
        """A pool session with status 'ready' can proceed to analyze_curated (200, not 409)."""
        resp = client.post(
            "/api/evidence/pool",
            json={
                "question": "What is the threat level?",
                "evidence": "Some evidence.",
            },
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        analyze_resp = client.post(
            f"/api/evidence/{session_id}/analyze",
            json={"selected_item_ids": []},
        )
        # 200 = queued successfully; 409 = not ready (would be a bug here)
        assert analyze_resp.status_code == 200

    def test_two_pool_requests_get_distinct_session_ids(self, client):
        """Each pool creation gets a unique session ID."""
        resp1 = client.post("/api/evidence/pool", json={"question": "Q1?"})
        resp2 = client.post("/api/evidence/pool", json={"question": "Q2?"})
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["session_id"] != resp2.json()["session_id"]

    def test_pool_response_has_correct_question(self, client):
        """Pool question matches the request question."""
        resp = client.post(
            "/api/evidence/pool",
            json={"question": "What is the unemployment rate in 2024?"},
        )
        assert resp.status_code == 200
        assert resp.json()["pool"]["question"] == "What is the unemployment rate in 2024?"

    def test_pool_status_is_ready_in_response(self, client):
        """Pool status in the immediate response body is 'ready'."""
        resp = client.post(
            "/api/evidence/pool",
            json={"question": "Q?", "evidence": "Evidence text."},
        )
        assert resp.status_code == 200
        assert resp.json()["pool"]["status"] == "ready"

    def test_name_stored_on_session(self, client, app):
        """Name from PoolRequest is stored on the session."""
        resp = client.post(
            "/api/evidence/pool",
            json={"question": "Q?", "name": "My Analysis"},
        )
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        evidence_manager = app.state.evidence_manager
        session = evidence_manager.get_session(session_id)
        assert session is not None
        assert session.name == "My Analysis"


# ---------------------------------------------------------------------------
# POST /api/evidence/pool — document sources (ingest_evidence mocked at boundary)
# ---------------------------------------------------------------------------


class TestPoolEndpointDocumentSources:
    def test_evidence_sources_triggers_ingestion_items_have_document_source(self, client):
        """evidence_sources triggers ingestion; resulting items have 'document' source."""
        doc = _make_parsed_doc("report.pdf", "Key finding: unemployment is at 5%.", "pdf")
        mock_result = _make_ingestion_result([doc])

        with patch(
            "sat.api.routes.evidence.ingest_evidence",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/evidence/pool",
                json={
                    "question": "What is the economic situation?",
                    "evidence_sources": ["/tmp/report.pdf"],
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        items = body["pool"]["items"]
        assert len(items) >= 1
        for item in items:
            assert item["source"] == "document"

    def test_evidence_sources_items_have_doc_prefix(self, client):
        """Document-derived items have 'DOC-' prefixed item_ids."""
        doc = _make_parsed_doc("brief.txt", "Intel from field operatives.", "text")
        mock_result = _make_ingestion_result([doc])

        with patch(
            "sat.api.routes.evidence.ingest_evidence",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/evidence/pool",
                json={
                    "question": "What happened?",
                    "evidence_sources": ["/tmp/brief.txt"],
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        items = body["pool"]["items"]
        assert len(items) == 1
        assert items[0]["item_id"].startswith("DOC-")

    def test_evidence_sources_stored_on_session(self, client, app):
        """evidence_sources from PoolRequest are stored on the session."""
        mock_result = _make_ingestion_result([])

        with patch(
            "sat.api.routes.evidence.ingest_evidence",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/evidence/pool",
                json={
                    "question": "Q?",
                    "evidence_sources": ["/tmp/intel.pdf", "https://example.com/report.html"],
                },
            )

        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        evidence_manager = app.state.evidence_manager
        session = evidence_manager.get_session(session_id)
        assert session is not None
        assert session.evidence_sources == ["/tmp/intel.pdf", "https://example.com/report.html"]

    def test_empty_evidence_sources_list_skips_ingestion(self, client):
        """Empty evidence_sources list does not call ingest_evidence."""
        with patch(
            "sat.api.routes.evidence.ingest_evidence",
            new=AsyncMock(),
        ) as mock_ingest:
            resp = client.post(
                "/api/evidence/pool",
                json={
                    "question": "Q?",
                    "evidence_sources": [],
                },
            )

        assert resp.status_code == 200
        mock_ingest.assert_not_called()
        assert resp.json()["pool"]["items"] == []


# ---------------------------------------------------------------------------
# POST /api/evidence/pool — combined text + sources
# ---------------------------------------------------------------------------


class TestPoolEndpointCombined:
    def test_text_and_sources_both_produce_items(self, client):
        """Both text evidence and document sources produce items in the pool."""
        doc = _make_parsed_doc("doc.pdf", "Document content here.", "pdf")
        mock_result = _make_ingestion_result([doc])

        with patch(
            "sat.api.routes.evidence.ingest_evidence",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/evidence/pool",
                json={
                    "question": "What is the situation?",
                    "evidence": "User typed evidence here.",
                    "evidence_sources": ["/tmp/doc.pdf"],
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        items = body["pool"]["items"]

        sources = {item["source"] for item in items}
        assert "user" in sources
        assert "document" in sources

    def test_empty_sources_and_no_text_produces_empty_pool(self, client):
        """No text and empty evidence_sources list produce an empty pool."""
        resp = client.post(
            "/api/evidence/pool",
            json={
                "question": "Q?",
                "evidence_sources": [],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["pool"]["items"] == []

    def test_multiple_documents_produce_multiple_items(self, client):
        """Multiple documents each produce at least one item."""
        docs = [
            _make_parsed_doc("a.txt", "Finding A from first document.", "text"),
            _make_parsed_doc("b.txt", "Finding B from second document.", "text"),
        ]
        mock_result = _make_ingestion_result(docs)

        with patch(
            "sat.api.routes.evidence.ingest_evidence",
            new=AsyncMock(return_value=mock_result),
        ):
            resp = client.post(
                "/api/evidence/pool",
                json={
                    "question": "What did the docs say?",
                    "evidence_sources": ["/tmp/a.txt", "/tmp/b.txt"],
                },
            )

        assert resp.status_code == 200
        items = resp.json()["pool"]["items"]
        assert len(items) >= 2
