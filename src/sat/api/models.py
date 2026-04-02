"""Pydantic request/response models for the SAT REST API.

@decision DEC-API-001
@title Pydantic v2 models mirror AnalysisConfig for clean API contract
@status accepted
@rationale The frontend speaks JSON; the pipeline speaks AnalysisConfig. These
models act as the translation layer — they are what the API exposes and accepts,
not the internal config objects. Keeping them separate avoids leaking internal
implementation details (e.g. PreprocessingConfig, IngestionConfig) into the
public API surface. The routes translate AnalysisRequest -> AnalysisConfig.

@decision DEC-SEC-005
@title Input size limits via Pydantic Field constraints on all request models
@status accepted
@rationale Unbounded string and list fields allow a client to submit arbitrarily
large payloads. This ties up LLM token budgets, exhausts server memory, and can
be used for denial-of-service. Limits are sized to practical maximums:
- question: 50,000 chars (~12,500 tokens) — enough for very detailed questions
- evidence: 500,000 chars (~125,000 tokens) — enough for large documents
- name: 500 chars — human-readable label, no need for more
- techniques: 20 items — there are only ~12 registered techniques
- evidence_sources: 100 items — practical maximum for a single analysis run
- selected_item_ids: 500 items — curated pool items
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from sat.models.evidence import EvidencePool

# Re-usable annotated types for constrained string/list fields
_Question = Annotated[str, Field(max_length=50_000)]
_Name = Annotated[str | None, Field(default=None, max_length=500)]
_Evidence = Annotated[str | None, Field(default=None, max_length=500_000)]
_Techniques = Annotated[list[str] | None, Field(default=None, max_length=20)]
_EvidenceSources = Annotated[
    list[str] | None,
    Field(default=None, max_length=100, description="File paths or URLs to ingest as evidence"),
]


class AnalysisRequest(BaseModel):
    """Request body for POST /api/analysis."""

    question: _Question
    name: _Name = None
    evidence: _Evidence = None
    techniques: _Techniques = None  # None = auto-select
    output_dir: str | None = None  # None → get_default_runs_dir() in the route
    provider: str = "anthropic"
    model: str | None = None
    research_enabled: bool = False
    research_mode: str = "multi"
    adversarial_enabled: bool = False
    adversarial_mode: str = "dual"  # "dual" or "trident"
    adversarial_rounds: int = 1
    report_enabled: bool = True
    report_format: str = "both"
    evidence_sources: _EvidenceSources = None
    gap_resolution_enabled: bool = True


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
    """Full detail for a single analysis run.

    For completed runs, synthesis_content and technique_summaries are inlined
    so the frontend can render immediately without N+1 artifact fetches.
    Both fields default to None for in-progress runs or runs without data.
    """

    artifacts: list[dict]
    synthesis_path: str | None = None
    evidence_path: str | None = None
    synthesis_content: dict | None = None  # Full synthesis JSON, inlined for completed runs
    technique_summaries: dict[str, str] | None = None  # {technique_id: summary_text}


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

    question: _Question
    name: _Name = None
    evidence: _Evidence = None
    research_enabled: bool = True
    research_mode: str = "multi"
    provider: str = "anthropic"
    model: str | None = None
    evidence_sources: _EvidenceSources = None


class EvidenceGatherResponse(BaseModel):
    """Response for a started evidence gathering session."""

    session_id: str
    ws_url: str


class RenameRunRequest(BaseModel):
    """Request body for PATCH /api/runs/{run_id}."""

    name: Annotated[str, Field(max_length=500)]


class CuratedAnalysisRequest(BaseModel):
    """Request body for POST /api/evidence/{session_id}/analyze."""

    selected_item_ids: Annotated[list[str], Field(max_length=500)]
    name: _Name = None
    techniques: _Techniques = None
    provider: str = "anthropic"
    model: str | None = None
    adversarial_enabled: bool = False
    adversarial_mode: str = "dual"
    adversarial_rounds: int = 1
    report_enabled: bool = True
    report_format: str = "both"
    evidence_sources: _EvidenceSources = None


class UpdateEvidenceItemRequest(BaseModel):
    """Request to update fields on an evidence item during curation."""

    claim: str | None = None
    confidence: str | None = None
    category: str | None = None


class CreateEvidenceItemRequest(BaseModel):
    """Request to manually add a new evidence item during curation.

    Allows users to inject their own evidence during the Gather & Review stage
    alongside items surfaced by research or document ingestion. The item is
    assigned a sequential M-N identifier and source='manual'.
    """

    claim: str = Field(..., min_length=1, max_length=5000)
    confidence: str = Field(default="Medium")
    category: str = Field(default="fact")


class PoolRequest(BaseModel):
    """Request body for POST /api/evidence/pool.

    Creates a structured EvidencePool synchronously from raw text and/or
    document sources without any LLM calls. Allows the frontend to build
    a reviewable pool from manually entered evidence or uploaded documents
    before triggering the full analysis pipeline.
    """

    question: _Question
    name: _Name = None
    evidence: _Evidence = None  # raw text entered by user; split into paragraph items
    evidence_sources: _EvidenceSources = None


class PoolResponse(BaseModel):
    """Response for POST /api/evidence/pool."""

    session_id: str
    pool: EvidencePool


class TemplateInfo(BaseModel):
    """Metadata for a single report template (default or custom).

    Custom templates live in ~/.sat/templates/; default templates are bundled
    with the package in src/sat/report/templates/.
    """

    filename: str
    size: int
    modified: str
    is_custom: bool


class TemplateUploadResponse(BaseModel):
    """Response for POST /api/config/templates/upload."""

    filename: str
    size: int
    status: str
