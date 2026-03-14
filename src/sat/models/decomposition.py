"""Decomposition result models for atomic fact extraction.

@decision DEC-DECOMP-001: LLM-based iterative extraction of atomic claims.
@title Atomic fact decomposition via structured LLM output
@status accepted
@rationale Evidence text can contain many interleaved claims. Decomposing into atomic facts
with source provenance, category, and confidence enables downstream techniques to reason
over individual claims rather than dense paragraphs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class AtomicFact(BaseModel):
    """A single atomic claim extracted from evidence."""

    fact_id: str = Field(description="Sequential identifier (F1, F2, ...)")
    claim: str = Field(description="The atomic claim statement")
    source_ids: list[str] = Field(
        default_factory=list, description="Source document IDs this claim comes from"
    )
    category: str = Field(
        default="fact",
        description="Claim category: fact, opinion, prediction, context",
    )
    confidence: str = Field(default="medium", description="Confidence level: high, medium, low")
    temporal_marker: str | None = Field(default=None, description="Time reference if present")
    entities: list[str] = Field(default_factory=list, description="Named entities mentioned")


class DecompositionResult(ArtifactResult):
    """Result of atomic fact decomposition."""

    technique_id: str = Field(default="decomposition", description="Phase identifier")
    technique_name: str = Field(
        default="Atomic Fact Decomposition", description="Phase display name"
    )
    summary: str = Field(default="", description="Brief summary of decomposition results")
    facts: list[AtomicFact] = Field(default_factory=list, description="Extracted atomic facts")
    total_facts: int = Field(default=0, description="Total facts extracted")
    total_sources: int = Field(default=0, description="Number of source documents processed")
    chunks_processed: int = Field(default=0, description="Number of evidence chunks processed")
    duplicates_removed: int = Field(default=0, description="Facts removed as duplicates")
    formatted_evidence: str = Field(default="", description="Formatted facts as structured text")
    warnings: list[str] = Field(default_factory=list, description="Warnings during decomposition")
