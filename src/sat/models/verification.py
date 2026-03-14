"""Verification result models for source verification phase.

@decision DEC-VERIFY-001: Verification as separate artifact with claim-level granularity.
@title Claim-by-claim verification against fetched source content
@status accepted
@rationale Each claim is assessed against its cited sources independently.
Verdicts allow confidence adjustment without discarding unverifiable claims.
The VerificationResult is written as its own artifact so verification history
is preserved independently from the annotated research result.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class FetchResult(BaseModel):
    """Result of fetching a source URL."""

    source_id: str = Field(description="Source ID from ResearchResult (e.g. 'S1')")
    url: str = Field(description="URL that was fetched")
    status: str = Field(description="'success', 'failed', 'timeout', 'blocked'")
    content_length: int = Field(default=0, description="Length of extracted text in chars")
    error: str | None = Field(default=None, description="Error message if fetch failed")


class ClaimVerification(BaseModel):
    """Verification of a single claim against its cited sources."""

    claim: str = Field(description="The claim text being verified")
    source_ids: list[str] = Field(description="Source IDs cited for this claim")
    verdict: str = Field(
        description=(
            "SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, "
            "CONTRADICTED, INCONCLUSIVE, UNVERIFIABLE"
        )
    )
    confidence: str = Field(description="Confidence in verdict: 'High', 'Medium', 'Low'")
    reasoning: str = Field(description="Brief explanation of the verdict")
    original_confidence: str = Field(description="Original claim confidence before verification")
    adjusted_confidence: str = Field(description="Adjusted confidence after verification")


class VerificationResult(ArtifactResult):
    """Result of source verification phase."""

    sources_fetched: int = Field(description="Number of sources successfully fetched")
    sources_failed: int = Field(description="Number of sources that failed to fetch")
    fetch_results: list[FetchResult] = Field(description="Per-source fetch outcomes")
    claim_verifications: list[ClaimVerification] = Field(
        description="Per-claim verification results"
    )
    verification_model: str = Field(description="Model used for verification assessment")
    verification_summary: str = Field(
        description="Human-readable summary of verification outcomes"
    )
