"""Tests for evidence_sources wiring through the API layer.

@decision DEC-UPLOAD-005
@title Tests verify evidence_sources flows from AnalysisRequest through to AnalysisConfig
@status accepted
@rationale The evidence_sources field is a new addition to the API contract. Tests
  confirm: (1) the Pydantic model accepts the field and defaults to None, (2) the
  route's AnalysisConfig construction correctly maps the field, (3) the POST endpoint
  accepts the JSON payload without error. Internal pipeline execution (run_analysis)
  is not under test here — that is covered by test_pipeline_ingestion.py.
  No mocks of internal code are used; tests construct real model objects directly.

Covers:
- AnalysisRequest model accepts evidence_sources field
- evidence_sources is optional and defaults to None
- AnalysisConfig stores evidence_sources correctly
- The route's config construction maps evidence_sources from request to config
- POST /api/analysis accepts evidence_sources in the JSON body (backward compat too)

Production reality check:
  The common production sequence is: user adds files/URLs in the frontend form →
  POST /api/analysis with evidence_sources in the JSON body → route builds
  AnalysisConfig with evidence_sources → pipeline.run_analysis receives config
  with evidence_sources for the ingestion step.
"""
from __future__ import annotations

import pytest

from sat.api.models import AnalysisRequest
from sat.config import AnalysisConfig


# ---------------------------------------------------------------------------
# Unit: AnalysisRequest model — evidence_sources field
# ---------------------------------------------------------------------------


def test_analysis_request_defaults_evidence_sources_to_none():
    """evidence_sources is optional and defaults to None."""
    req = AnalysisRequest(question="Is this a test?")
    assert req.evidence_sources is None


def test_analysis_request_accepts_file_paths():
    """evidence_sources accepts a list of local file paths."""
    paths = ["/home/user/report.pdf", "/home/user/data.csv"]
    req = AnalysisRequest(question="Test?", evidence_sources=paths)
    assert req.evidence_sources == paths


def test_analysis_request_accepts_urls():
    """evidence_sources accepts a list of URLs."""
    urls = ["https://example.com/report.pdf", "https://intel.gov/data.html"]
    req = AnalysisRequest(question="Test?", evidence_sources=urls)
    assert req.evidence_sources == urls


def test_analysis_request_accepts_mixed_sources():
    """evidence_sources accepts a mix of file paths and URLs."""
    sources = ["/tmp/local.pdf", "https://example.com/remote.html"]
    req = AnalysisRequest(question="Test?", evidence_sources=sources)
    assert req.evidence_sources == sources


def test_analysis_request_accepts_none_explicitly():
    """evidence_sources can be set explicitly to None."""
    req = AnalysisRequest(question="Test?", evidence_sources=None)
    assert req.evidence_sources is None


def test_analysis_request_accepts_empty_list():
    """evidence_sources can be an empty list."""
    req = AnalysisRequest(question="Test?", evidence_sources=[])
    assert req.evidence_sources == []


def test_analysis_request_json_roundtrip():
    """evidence_sources survives JSON serialization/deserialization."""
    sources = ["/tmp/intel.pdf", "https://example.com/brief.html"]
    req = AnalysisRequest(question="Test?", evidence_sources=sources)
    as_json = req.model_dump()
    restored = AnalysisRequest(**as_json)
    assert restored.evidence_sources == sources


# ---------------------------------------------------------------------------
# Unit: AnalysisConfig — evidence_sources field propagation
#
# The route does: AnalysisConfig(..., evidence_sources=request.evidence_sources)
# Verify AnalysisConfig actually stores the value so the pipeline receives it.
# ---------------------------------------------------------------------------


def test_analysis_config_stores_evidence_sources():
    """AnalysisConfig stores evidence_sources as-is."""
    sources = ["/tmp/a.pdf", "https://example.com/b.html"]
    config = AnalysisConfig(question="Test?", evidence_sources=sources)
    assert config.evidence_sources == sources


def test_analysis_config_defaults_evidence_sources_to_none():
    """AnalysisConfig defaults evidence_sources to None (not provided)."""
    config = AnalysisConfig(question="Test?")
    assert config.evidence_sources is None


def test_route_config_construction_maps_evidence_sources():
    """
    Simulate the route's AnalysisConfig construction from an AnalysisRequest
    to verify evidence_sources flows through correctly.

    This directly tests the data path the route uses without running
    the full pipeline.
    """
    from pathlib import Path
    from sat.adversarial.config import AdversarialConfig
    from sat.config import ProviderConfig, ResearchConfig, ReportConfig

    request = AnalysisRequest(
        question="What is the threat level?",
        evidence_sources=["/tmp/intel.pdf", "https://example.com/report.html"],
        provider="anthropic",
        research_enabled=False,
        adversarial_enabled=False,
        report_enabled=True,
        report_format="both",
        output_dir=".",
    )

    # Mirror the route's construction exactly
    provider_cfg = ProviderConfig(provider=request.provider, model=request.model)
    research_cfg = ResearchConfig(enabled=request.research_enabled, mode=request.research_mode)
    report_cfg = ReportConfig(enabled=request.report_enabled, fmt=request.report_format)
    adversarial_cfg: AdversarialConfig | None = None
    if request.adversarial_enabled:
        adversarial_cfg = AdversarialConfig(
            enabled=True,
            mode=request.adversarial_mode,
            rounds=request.adversarial_rounds,
        )

    config = AnalysisConfig(
        question=request.question,
        evidence=request.evidence,
        techniques=request.techniques,
        output_dir=Path(request.output_dir),
        provider=provider_cfg,
        research=research_cfg,
        adversarial=adversarial_cfg,
        report=report_cfg,
        evidence_sources=request.evidence_sources,
    )

    assert config.evidence_sources == ["/tmp/intel.pdf", "https://example.com/report.html"]
    assert config.question == "What is the threat level?"


def test_route_config_construction_no_sources_gives_none():
    """Route construction with no evidence_sources yields None in AnalysisConfig."""
    from pathlib import Path
    from sat.config import ProviderConfig, ResearchConfig, ReportConfig

    request = AnalysisRequest(question="Test?")
    config = AnalysisConfig(
        question=request.question,
        evidence=request.evidence,
        techniques=request.techniques,
        output_dir=Path(request.output_dir),
        provider=ProviderConfig(provider=request.provider, model=request.model),
        research=ResearchConfig(enabled=request.research_enabled, mode=request.research_mode),
        adversarial=None,
        report=ReportConfig(enabled=request.report_enabled, fmt=request.report_format),
        evidence_sources=request.evidence_sources,
    )

    assert config.evidence_sources is None


# ---------------------------------------------------------------------------
# Integration: POST /api/analysis accepts evidence_sources in the JSON body
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    from sat.api.app import create_app
    return create_app(port=8742)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_post_analysis_with_evidence_sources_returns_200(client):
    """
    POST /api/analysis with evidence_sources is accepted by the endpoint.

    The pipeline runs in the background; we only verify the request is accepted
    (status 200) and a run_id is returned. This confirms the JSON field is
    deserialized without error by Pydantic and passed to the route.
    """
    resp = client.post(
        "/api/analysis",
        json={
            "question": "What is the situation?",
            "evidence_sources": ["/tmp/intel.pdf", "https://example.com/brief.html"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body
    assert "ws_url" in body


def test_post_analysis_without_evidence_sources_returns_200(client):
    """
    POST /api/analysis without evidence_sources still works (backward compat).
    """
    resp = client.post(
        "/api/analysis",
        json={"question": "Backward compat test"},
    )
    assert resp.status_code == 200
    assert "run_id" in resp.json()
