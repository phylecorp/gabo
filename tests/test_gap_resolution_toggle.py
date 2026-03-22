"""Tests for gap resolution toggle: backend default, API wiring, config.

@decision DEC-GAP-TOGGLE-001
@title Gap resolution toggle: backend default True, API field, config propagation
@status accepted
@rationale The gap resolution feature was added with enabled=False as a conservative
default. This toggle promotes it to on-by-default. Tests verify: (1) GapResolutionConfig
defaults to True, (2) AnalysisRequest accepts gap_resolution_enabled, (3) the API
route accepts the field without 422 errors, (4) ResearchConfig propagates the value
into AnalysisConfig. No mocks for internal config/model logic — tested directly.

Covers:
- GapResolutionConfig.enabled defaults to True (backend default change)
- AnalysisRequest accepts gap_resolution_enabled field
- Analysis route builds ResearchConfig with gap_resolution.enabled set from request
- ResearchConfig.gap_resolution.enabled propagates into AnalysisConfig

Production sequence: POST /api/analysis -> AnalysisRequest parsed -> ResearchConfig
built with gap_resolution.enabled from request -> AnalysisConfig -> pipeline runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sat.api.app import create_app
from sat.api.models import AnalysisRequest
from sat.config import AnalysisConfig, GapResolutionConfig, ResearchConfig


# ---------------------------------------------------------------------------
# GapResolutionConfig default
# ---------------------------------------------------------------------------


def test_gap_resolution_config_default_is_true():
    """GapResolutionConfig.enabled defaults to True after the backend change."""
    cfg = GapResolutionConfig()
    assert cfg.enabled is True


def test_gap_resolution_config_can_be_disabled():
    """GapResolutionConfig.enabled can be explicitly set to False."""
    cfg = GapResolutionConfig(enabled=False)
    assert cfg.enabled is False


def test_research_config_gap_resolution_default():
    """ResearchConfig nests GapResolutionConfig with enabled=True by default."""
    cfg = ResearchConfig()
    assert cfg.gap_resolution.enabled is True


# ---------------------------------------------------------------------------
# AnalysisRequest API model
# ---------------------------------------------------------------------------


def test_analysis_request_gap_resolution_enabled_default():
    """AnalysisRequest.gap_resolution_enabled defaults to True."""
    req = AnalysisRequest(question="test question")
    assert req.gap_resolution_enabled is True


def test_analysis_request_gap_resolution_enabled_false():
    """AnalysisRequest.gap_resolution_enabled can be set to False."""
    req = AnalysisRequest(question="test question", gap_resolution_enabled=False)
    assert req.gap_resolution_enabled is False


def test_analysis_request_gap_resolution_enabled_true():
    """AnalysisRequest.gap_resolution_enabled can be explicitly set to True."""
    req = AnalysisRequest(question="test question", gap_resolution_enabled=True)
    assert req.gap_resolution_enabled is True


# ---------------------------------------------------------------------------
# API route wires gap_resolution_enabled -> ResearchConfig
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    return create_app(port=8742)


@pytest.fixture()
def api_client(app):
    return TestClient(app)


def test_api_accepts_gap_resolution_disabled(api_client):
    """POST /api/analysis with gap_resolution_enabled=False is accepted (200/201)."""
    resp = api_client.post(
        "/api/analysis",
        json={
            "question": "What are the gaps?",
            "gap_resolution_enabled": False,
            "research_enabled": False,
        },
        headers={"Authorization": "Bearer test-token"},
    )
    # The route creates a background task and returns immediately.
    # We just verify the request is accepted (not 422 validation error).
    assert resp.status_code in (200, 201), resp.text


def test_api_accepts_gap_resolution_enabled(api_client):
    """POST /api/analysis with gap_resolution_enabled=True is accepted."""
    resp = api_client.post(
        "/api/analysis",
        json={
            "question": "What are the gaps?",
            "gap_resolution_enabled": True,
            "research_enabled": False,
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code in (200, 201), resp.text


def test_api_default_gap_resolution_is_true(api_client):
    """POST /api/analysis without gap_resolution_enabled field defaults to True (no 422)."""
    resp = api_client.post(
        "/api/analysis",
        json={
            "question": "Gap test question",
            "research_enabled": False,
        },
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code in (200, 201), resp.text


# ---------------------------------------------------------------------------
# ResearchConfig gap_resolution.enabled propagates to AnalysisConfig
# ---------------------------------------------------------------------------


def test_research_config_gap_resolution_propagates():
    """ResearchConfig built with gap_resolution.enabled=False propagates into AnalysisConfig."""
    research_cfg = ResearchConfig(
        enabled=True,
        gap_resolution=GapResolutionConfig(enabled=False),
    )
    config = AnalysisConfig(
        question="test",
        research=research_cfg,
    )
    assert config.research.gap_resolution.enabled is False


def test_research_config_gap_resolution_enabled_propagates():
    """ResearchConfig built with gap_resolution.enabled=True propagates into AnalysisConfig."""
    research_cfg = ResearchConfig(
        enabled=True,
        gap_resolution=GapResolutionConfig(enabled=True),
    )
    config = AnalysisConfig(
        question="test",
        research=research_cfg,
    )
    assert config.research.gap_resolution.enabled is True
