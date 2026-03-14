"""Evidence curation models for interactive evidence review.

@decision DEC-EVIDENCE-001
@title Unified EvidenceItem model merges decomposition, research, and raw user evidence
@status accepted
@rationale Three evidence sources (AtomicFact from decomposition, ResearchClaim from research,
raw user text) need a common shape for the curation UI. EvidenceItem normalizes them with a
source-type prefix (D- for decomposition, R- for research, U- for user) and adds a `selected`
field for curation. EvidencePool collects items with session metadata.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """A single reviewable evidence item from any source."""

    item_id: str = Field(description="Unique ID with source prefix: D-F1, R-C1, U-1")
    claim: str = Field(description="The evidence claim or fact")
    source: str = Field(description="Source type: 'decomposition', 'research', 'user'")
    source_ids: list[str] = Field(default_factory=list, description="Original source references")
    category: str = Field(default="fact", description="Category: fact, analysis, opinion, projection")
    confidence: str = Field(default="Medium", description="Confidence: High, Medium, Low")
    entities: list[str] = Field(default_factory=list, description="Named entities mentioned")
    verified: bool = Field(default=False, description="Whether claim has been verified")
    selected: bool = Field(default=True, description="Whether item is selected for analysis")
    provider_name: str | None = Field(default=None, description="Research provider name if from research")


class EvidencePool(BaseModel):
    """Collection of evidence items ready for curation."""

    session_id: str = Field(description="Evidence gathering session ID")
    question: str = Field(description="The analytic question")
    items: list[EvidenceItem] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list, description="Source registry from research")
    gaps: list[str] = Field(default_factory=list, description="Information gaps identified")
    provider_summary: str = Field(default="", description="Summary of providers queried")
    status: str = Field(default="gathering", description="gathering, ready, failed")
    error: str | None = Field(default=None)
