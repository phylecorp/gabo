"""Research result models for deep research phase.

@decision DEC-RESEARCH-001: Research results as ArtifactResult subclass.
@title Structured evidence with source provenance
@status accepted
@rationale Research produces structured evidence with source provenance. The
formatted_evidence string is injected into the pipeline as config.evidence.
The full ResearchResult is preserved as an artifact for provenance tracking.
Techniques never know evidence came from research — they see the same str|None.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class ResearchSource(BaseModel):
    """A source discovered during research."""

    id: str = Field(description="Unique identifier for this source (e.g. 'S1', 'S2')")
    title: str = Field(description="Title or headline of the source")
    url: str | None = Field(default=None, description="URL if available")
    source_type: str = Field(description="Type: 'web', 'academic', 'news', 'government', etc.")
    reliability_assessment: str = Field(
        description="Assessment of source reliability: 'High', 'Medium', 'Low', 'Unknown'"
    )
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchClaim(BaseModel):
    """A factual claim extracted from research with source attribution."""

    claim: str = Field(description="The factual claim or finding")
    source_ids: list[str] = Field(description="IDs of sources supporting this claim")
    confidence: str = Field(description="Confidence level: 'High', 'Medium', 'Low'")
    category: str = Field(description="Category: 'fact', 'analysis', 'opinion', 'projection'")
    verified: bool = Field(default=False, description="Whether this claim has been verified")
    verification_verdict: str | None = Field(
        default=None, description="Verification verdict if verified"
    )
    origin: str | None = Field(
        default=None,
        description="Pipeline stage that produced this claim, e.g. 'gap_resolution_iter_1'",
    )


class ResearchResult(ArtifactResult):
    """Result of deep research phase with structured evidence and provenance."""

    query: str = Field(description="The research query derived from the analytic question")
    sources: list[ResearchSource] = Field(description="Sources discovered during research")
    claims: list[ResearchClaim] = Field(
        description="Factual claims extracted with source attribution"
    )
    formatted_evidence: str = Field(
        description="Evidence formatted for injection into analysis pipeline"
    )
    research_provider: str = Field(
        description="Research backend used: 'perplexity', 'brave', 'llm'"
    )
    gaps_identified: list[str] = Field(description="Information gaps identified during research")
    verification_status: str | None = Field(
        default=None, description="'verified', 'partial', 'unverified'"
    )
    verified_confidence: str | None = Field(
        default=None, description="Overall confidence after verification"
    )
    verification_summary: str | None = Field(
        default=None, description="Human-readable verification summary"
    )
