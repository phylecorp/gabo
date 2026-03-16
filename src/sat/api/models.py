"""Pydantic request/response models for the SAT REST API.

@decision DEC-API-001
@title Pydantic v2 models mirror AnalysisConfig for clean API contract
@status accepted
@rationale The frontend speaks JSON; the pipeline speaks AnalysisConfig. These
models act as the translation layer — they are what the API exposes and accepts,
not the internal config objects. Keeping them separate avoids leaking internal
implementation details (e.g. PreprocessingConfig, IngestionConfig) into the
public API surface. The routes translate AnalysisRequest -> AnalysisConfig.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sat.models.evidence import EvidencePool


class AnalysisRequest(BaseModel):
    """Request body for POST /api/analysis."""

    question: str
    name: str | None = None
    evidence: str | None = None
    techniques: list[str] | None = None  # None = auto-select
    output_dir: str = "."
    provider: str = "anthropic"
    model: str | None = None
    research_enabled: bool = False
    research_mode: str = "multi"
    adversarial_enabled: bool = False
    adversarial_mode: str = "dual"  # "dual" or "trident"
    adversarial_rounds: int = 1
    report_enabled: bool = True
    report_format: str = "both"
    evidence_sources: list[str] | None = Field(
        default=None, description="File paths or URLs to ingest as evidence"
    )


class AnalysisResponse(BaseModel):
    """Response for a successfully started analysis run."""

    run_id: str
    ws_url: str
    queue_position: int | None = None


class ConcurrencyStatusResponse(BaseModel):
    """Snapshot of the RunManager concurrency state."""

    running: int
    queued: int
    max_concurrent: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"


class TechniqueInfo(BaseModel):
    """Public metadata for a single technique."""

    id: str
    name: str
    category: str
    description: str
    order: int


class ProviderInfo(BaseModel):
    """Availability info for a single LLM provider."""

    name: str
    has_api_key: bool
    default_model: str


class RunSummary(BaseModel):
    """Summary of an analysis run (list view)."""

    run_id: str
    question: str
    name: str | None = None
    started_at: str
    completed_at: str | None
    techniques_selected: list[str]
    techniques_completed: list[str]
    evidence_provided: bool
    adversarial_enabled: bool
    providers_used: list[str]
    status: str  # "queued", "running", "completed", "failed", "cancelled"


class RunDetail(RunSummary):
    """Full detail for a single analysis run."""

    artifacts: list[dict]
    synthesis_path: str | None = None
    evidence_path: str | None = None


class ProviderSettings(BaseModel):
    """Settings for a single LLM provider."""

    api_key: str = ""
    default_model: str = ""
    research_model: str = ""


class AppSettings(BaseModel):
    """Application settings (provider API keys and models)."""

    providers: dict[str, ProviderSettings] = {}


class ProviderSettingsResponse(BaseModel):
    """Provider settings with masked key preview."""

    has_api_key: bool
    api_key_preview: str = ""
    default_model: str = ""
    research_model: str = ""
    source: str = "default"  # "config_file", "environment", "default"


class SettingsResponse(BaseModel):
    """Full settings response."""

    providers: dict[str, ProviderSettingsResponse] = {}


class TestProviderRequest(BaseModel):
    """Request to test a provider API key."""

    provider: str
    api_key: str
    model: str | None = None


class TestProviderResponse(BaseModel):
    """Result of a provider API key test."""

    success: bool
    error: str | None = None
    model_used: str | None = None


class EvidenceGatherRequest(BaseModel):
    """Request body for POST /api/evidence/gather."""

    question: str
    name: str | None = None
    evidence: str | None = None
    research_enabled: bool = True
    research_mode: str = "multi"
    provider: str = "anthropic"
    model: str | None = None
    evidence_sources: list[str] | None = Field(
        default=None, description="File paths or URLs to ingest as evidence"
    )


class EvidenceGatherResponse(BaseModel):
    """Response for a started evidence gathering session."""

    session_id: str
    ws_url: str


class RenameRunRequest(BaseModel):
    """Request body for PATCH /api/runs/{run_id}."""

    name: str


class CuratedAnalysisRequest(BaseModel):
    """Request body for POST /api/evidence/{session_id}/analyze."""

    selected_item_ids: list[str]
    name: str | None = None
    techniques: list[str] | None = None
    provider: str = "anthropic"
    model: str | None = None
    adversarial_enabled: bool = False
    adversarial_mode: str = "dual"
    adversarial_rounds: int = 1
    report_enabled: bool = True
    report_format: str = "both"
    evidence_sources: list[str] | None = Field(
        default=None, description="File paths or URLs to ingest as evidence"
    )


class PoolRequest(BaseModel):
    """Request body for POST /api/evidence/pool.

    Creates a structured EvidencePool synchronously from raw text and/or
    document sources without any LLM calls. Allows the frontend to build
    a reviewable pool from manually entered evidence or uploaded documents
    before triggering the full analysis pipeline.
    """

    question: str
    name: str | None = None
    evidence: str | None = None  # raw text entered by user; split into paragraph items
    evidence_sources: list[str] | None = Field(
        default=None, description="File paths or URLs to ingest as evidence documents"
    )


class PoolResponse(BaseModel):
    """Response for POST /api/evidence/pool."""

    session_id: str
    pool: EvidencePool
