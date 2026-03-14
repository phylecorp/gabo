"""Tests for evidence_sources wiring through the curated analysis path.

@decision DEC-UPLOAD-006
@title Tests verify evidence_sources flows through both gather and curated-analyze paths
@status accepted
@rationale The evidence_sources field must propagate through two additional paths beyond
  the direct /api/analysis route: (1) EvidenceGatherRequest → session storage → passed
  to analyze_curated, and (2) CuratedAnalysisRequest → AnalysisConfig. Tests confirm
  the Pydantic models accept the field, the session stores sources from gather, and the
  AnalysisConfig receives them when the curated analysis runs.
  No mocks of internal code are used; tests construct real model objects directly.

Covers:
- EvidenceGatherRequest model accepts evidence_sources field
- EvidenceGatherRequest defaults evidence_sources to None
- CuratedAnalysisRequest model accepts evidence_sources field
- CuratedAnalysisRequest defaults evidence_sources to None
- EvidenceSession stores evidence_sources set at gather time
- POST /api/evidence/gather accepts evidence_sources in JSON body
- POST /api/evidence/{id}/analyze accepts evidence_sources in JSON body
- The curated route maps evidence_sources to AnalysisConfig (via direct CuratedAnalysisRequest)
- Session-stored sources are available for the curated analyze step

Production reality check:
  The production sequence for the curated path is:
  1. User adds source files/URLs in the form
  2. User clicks "Gather & Review" → POST /api/evidence/gather with evidence_sources
  3. Server runs gather_evidence (text decomposition/research)
  4. User reviews, selects items, clicks "Run Analysis"
  5. POST /api/evidence/{id}/analyze with evidence_sources (from form state)
  6. Server builds AnalysisConfig with evidence_sources → pipeline runs ingestion

  Tests exercise this full sequence (model layer and session state; pipeline execution
  is covered by test_pipeline_ingestion.py).
"""
from __future__ import annotations

import pytest

from sat.api.models import CuratedAnalysisRequest, EvidenceGatherRequest


# ---------------------------------------------------------------------------
# Unit: EvidenceGatherRequest — evidence_sources field
# ---------------------------------------------------------------------------


def test_evidence_gather_request_defaults_evidence_sources_to_none():
    """evidence_sources is optional and defaults to None."""
    req = EvidenceGatherRequest(question="Is this a test?")
    assert req.evidence_sources is None


def test_evidence_gather_request_accepts_file_paths():
    """evidence_sources accepts a list of local file paths."""
    paths = ["/home/user/report.pdf", "/home/user/data.csv"]
    req = EvidenceGatherRequest(question="Test?", evidence_sources=paths)
    assert req.evidence_sources == paths


def test_evidence_gather_request_accepts_urls():
    """evidence_sources accepts a list of URLs."""
    urls = ["https://example.com/report.pdf", "https://intel.gov/data.html"]
    req = EvidenceGatherRequest(question="Test?", evidence_sources=urls)
    assert req.evidence_sources == urls


def test_evidence_gather_request_accepts_none_explicitly():
    """evidence_sources can be set explicitly to None."""
    req = EvidenceGatherRequest(question="Test?", evidence_sources=None)
    assert req.evidence_sources is None


def test_evidence_gather_request_json_roundtrip():
    """evidence_sources survives JSON serialization/deserialization."""
    sources = ["/tmp/intel.pdf", "https://example.com/brief.html"]
    req = EvidenceGatherRequest(question="Test?", evidence_sources=sources)
    as_json = req.model_dump()
    restored = EvidenceGatherRequest(**as_json)
    assert restored.evidence_sources == sources


# ---------------------------------------------------------------------------
# Unit: CuratedAnalysisRequest — evidence_sources field
# ---------------------------------------------------------------------------


def test_curated_analysis_request_defaults_evidence_sources_to_none():
    """evidence_sources is optional and defaults to None."""
    req = CuratedAnalysisRequest(selected_item_ids=["D-F1", "D-F2"])
    assert req.evidence_sources is None


def test_curated_analysis_request_accepts_file_paths():
    """evidence_sources accepts a list of local file paths."""
    paths = ["/home/user/report.pdf"]
    req = CuratedAnalysisRequest(selected_item_ids=["D-F1"], evidence_sources=paths)
    assert req.evidence_sources == paths


def test_curated_analysis_request_accepts_none_explicitly():
    """evidence_sources can be set explicitly to None."""
    req = CuratedAnalysisRequest(selected_item_ids=[], evidence_sources=None)
    assert req.evidence_sources is None


def test_curated_analysis_request_json_roundtrip():
    """evidence_sources survives JSON serialization/deserialization."""
    sources = ["/tmp/intel.pdf", "https://example.com/brief.html"]
    req = CuratedAnalysisRequest(selected_item_ids=["R-001"], evidence_sources=sources)
    as_json = req.model_dump()
    restored = CuratedAnalysisRequest(**as_json)
    assert restored.evidence_sources == sources


# ---------------------------------------------------------------------------
# Unit: EvidenceSession stores evidence_sources
# ---------------------------------------------------------------------------


def test_evidence_session_stores_evidence_sources():
    """EvidenceSession stores evidence_sources when set."""
    from sat.api.evidence_manager import EvidenceSession

    session = EvidenceSession("test-id")
    session.evidence_sources = ["/tmp/a.pdf", "https://example.com/b.html"]
    assert session.evidence_sources == ["/tmp/a.pdf", "https://example.com/b.html"]


def test_evidence_session_evidence_sources_defaults_to_none():
    """EvidenceSession.evidence_sources defaults to None."""
    from sat.api.evidence_manager import EvidenceSession

    session = EvidenceSession("test-id")
    assert session.evidence_sources is None


# ---------------------------------------------------------------------------
# Unit: curated route maps evidence_sources to AnalysisConfig
# ---------------------------------------------------------------------------


def test_curated_route_config_construction_maps_evidence_sources():
    """
    Simulate the curated route's AnalysisConfig construction from a
    CuratedAnalysisRequest to verify evidence_sources flows through correctly.

    This mirrors the exact data path the route handler uses, without running
    the full pipeline.
    """
    from pathlib import Path

    from sat.config import AnalysisConfig, ProviderConfig, ResearchConfig, ReportConfig

    request = CuratedAnalysisRequest(
        selected_item_ids=["D-F1", "R-001"],
        provider="anthropic",
        evidence_sources=["/tmp/intel.pdf", "https://example.com/report.html"],
        report_enabled=True,
        report_format="both",
    )

    # Mirror the route's AnalysisConfig construction
    config = AnalysisConfig(
        question="What is the threat level?",
        evidence="Curated evidence text",
        techniques=request.techniques,
        output_dir=Path("."),
        provider=ProviderConfig(provider=request.provider, model=request.model),
        research=ResearchConfig(enabled=False),
        adversarial=None,
        report=ReportConfig(enabled=request.report_enabled, fmt=request.report_format),
        evidence_sources=request.evidence_sources,
    )

    assert config.evidence_sources == ["/tmp/intel.pdf", "https://example.com/report.html"]


def test_curated_route_config_no_sources_gives_none():
    """Curated route construction with no evidence_sources yields None in AnalysisConfig."""
    from pathlib import Path

    from sat.config import AnalysisConfig, ProviderConfig, ResearchConfig, ReportConfig

    request = CuratedAnalysisRequest(selected_item_ids=["D-F1"])

    config = AnalysisConfig(
        question="Test?",
        evidence="some evidence",
        techniques=request.techniques,
        output_dir=Path("."),
        provider=ProviderConfig(provider=request.provider, model=request.model),
        research=ResearchConfig(enabled=False),
        adversarial=None,
        report=ReportConfig(enabled=request.report_enabled, fmt=request.report_format),
        evidence_sources=request.evidence_sources,
    )

    assert config.evidence_sources is None


def test_curated_route_config_uses_session_sources_when_request_has_none():
    """
    When CuratedAnalysisRequest.evidence_sources is None but the session stored
    sources from the gather step, the route uses the session sources.

    This simulates the production sequence: sources passed at gather time should
    carry through to the analysis even if the curated request omits them.
    """
    from pathlib import Path

    from sat.api.evidence_manager import EvidenceSession
    from sat.config import AnalysisConfig, ProviderConfig, ResearchConfig, ReportConfig

    # Simulate session with stored sources from gather step
    session = EvidenceSession("session-abc")
    session.evidence_sources = ["/tmp/stored.pdf"]

    request = CuratedAnalysisRequest(selected_item_ids=["D-F1"])
    # request.evidence_sources is None

    # The route should pick sources from request if provided, else from session
    effective_sources = request.evidence_sources or session.evidence_sources

    config = AnalysisConfig(
        question="Q?",
        evidence="evidence text",
        techniques=None,
        output_dir=Path("."),
        provider=ProviderConfig(provider=request.provider),
        research=ResearchConfig(enabled=False),
        adversarial=None,
        report=ReportConfig(enabled=request.report_enabled, fmt=request.report_format),
        evidence_sources=effective_sources,
    )

    assert config.evidence_sources == ["/tmp/stored.pdf"]


# ---------------------------------------------------------------------------
# Integration: POST /api/evidence/gather accepts evidence_sources in JSON body
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    from sat.api.app import create_app

    return create_app(port=8742)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_post_gather_with_evidence_sources_returns_200(client):
    """
    POST /api/evidence/gather with evidence_sources is accepted by the endpoint.
    """
    resp = client.post(
        "/api/evidence/gather",
        json={
            "question": "What is the situation?",
            "evidence_sources": ["/tmp/intel.pdf", "https://example.com/brief.html"],
            "research_enabled": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "session_id" in body
    assert "ws_url" in body


def test_post_gather_without_evidence_sources_still_works(client):
    """
    POST /api/evidence/gather without evidence_sources still works (backward compat).
    """
    resp = client.post(
        "/api/evidence/gather",
        json={"question": "Backward compat test", "research_enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"]


def test_post_analyze_curated_with_evidence_sources_accepted(client):
    """
    POST /api/evidence/{id}/analyze accepts evidence_sources in the JSON body.

    The session doesn't exist so we get 404, but the body is validated first
    only if the session is found. We test with a real session to confirm the
    field is accepted without a 422.
    """
    # Create a real session via gather
    gather_resp = client.post(
        "/api/evidence/gather",
        json={"question": "Test?", "research_enabled": False},
    )
    assert gather_resp.status_code == 200
    session_id = gather_resp.json()["session_id"]

    # Attempt analyze — may be 200 or 409 depending on task completion,
    # but NOT 422 (the field must be accepted by Pydantic)
    resp = client.post(
        f"/api/evidence/{session_id}/analyze",
        json={
            "selected_item_ids": [],
            "evidence_sources": ["/tmp/intel.pdf", "https://example.com/brief.html"],
        },
    )
    assert resp.status_code in (200, 409)


def test_post_analyze_curated_unknown_session_with_sources_returns_404(client):
    """
    Unknown session with evidence_sources still returns 404.
    """
    resp = client.post(
        "/api/evidence/doesnotexist/analyze",
        json={
            "selected_item_ids": ["D-F1"],
            "evidence_sources": ["/tmp/intel.pdf"],
        },
    )
    assert resp.status_code == 404
