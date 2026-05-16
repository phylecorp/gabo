"""Evidence curation models for interactive evidence review.

@decision DEC-EVIDENCE-001
@title Unified EvidenceItem model merges decomposition, research, and raw user evidence
@status accepted
@rationale Three evidence sources (AtomicFact from decomposition, ResearchClaim from research,
raw user text) need a common shape for the curation UI. EvidenceItem normalizes them with a
source-type prefix (D- for decomposition, R- for research, U- for user) and adds a `selected`
field for curation. EvidencePool collects items with session metadata.

@decision DEC-EVIDENCE-005
@title GapResolutionSummary and EvidenceItem.origin expose gap resolution to the UI
@status accepted
@rationale The backend gap resolver tags claims with origin="gap_resolution_query_N" and
merges new sources, but this information was discarded before reaching the frontend. Two
additions make it visible: (1) EvidenceItem.origin propagates the tag from ResearchClaim to
EvidenceItem so the curation UI can display a "gap fill" badge; (2) GapResolutionSummary on
EvidencePool carries the before/after delta (queries_run, claims_added, sources_added) so the
UI can render a summary section. Both fields are optional with None defaults for full backward
compatibility with existing persisted evidence.json files.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    """A single reviewable evidence item from any source."""

    item_id: str = Field(description="Unique ID with source prefix: D-F1, R-C1, U-1")
    claim: str = Field(description="The evidence claim or fact")
    source: str = Field(description="Source type: 'decomposition', 'research', 'user'")
    source_ids: list[str] = Field(default_factory=list, description="Original source references")
    category: str = Field(
        default="fact", description="Category: fact, analysis, opinion, projection"
    )
    confidence: str = Field(default="Medium", description="Confidence: High, Medium, Low")
    entities: list[str] = Field(default_factory=list, description="Named entities mentioned")
    verified: bool = Field(default=False, description="Whether claim has been verified")
    selected: bool = Field(default=True, description="Whether item is selected for analysis")
    provider_name: str | None = Field(
        default=None, description="Research provider name if from research"
    )
    source_urls: list[str] = Field(
        default_factory=list,
        description="URLs of sources backing this evidence item, for syndication detection",
    )
    origin: str | None = Field(
        default=None,
        description="Pipeline stage origin, e.g. 'gap_resolution_query_1'",
    )


class GapResolutionSummary(BaseModel):
    """Summary of gap resolution results for UI display.

    Attached to EvidencePool.gap_resolution after gather_evidence() runs gap
    resolution. The before/after delta (claims_added, sources_added) lets the
    UI show how much new evidence gap resolution contributed.
    """

    ran: bool = Field(description="Whether gap resolution executed")
    original_gaps: list[str] = Field(
        default_factory=list,
        description="Gaps identified before resolution (resolver clears them from result)",
    )
    queries_run: int = Field(default=0, description="Number of follow-up queries executed")
    claims_added: int = Field(default=0, description="New claims from gap resolution")
    sources_added: int = Field(default=0, description="New sources from gap resolution")


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
    gap_resolution: GapResolutionSummary | None = Field(
        default=None,
        description="Gap resolution results if ran; None when disabled or not yet run",
    )


@dataclass
class TechniqueEvidence:
    """Evidence container carrying both text and structured items for technique consumption.

    @decision DEC-EVIDENCE-003
    @title TechniqueEvidence carries parallel text + structured channels
    @status accepted
    @rationale Techniques that need only text (most techniques) call .as_text(). Techniques
    that need structured access (ACH, Quality of Sources) access .items directly for evidence
    IDs, confidence ratings, and categories. The text channel is always populated; the items
    channel may be empty (e.g., quick-run path with no gatherer/research).
    """

    text: str
    items: list[EvidenceItem] = dc_field(default_factory=list)

    def as_text(self) -> str:
        """Return the text representation of this evidence."""
        return self.text

    def __str__(self) -> str:
        return self.text

    def __bool__(self) -> bool:
        return bool(self.text)

    @classmethod
    def from_text(cls, text: str) -> "TechniqueEvidence":
        """Create from a plain text string with no structured items."""
        return cls(text=text, items=[])

    @classmethod
    def from_pool(cls, pool: EvidencePool, text: str) -> "TechniqueEvidence":
        """Create from an EvidencePool, using selected items only."""
        selected = [item for item in pool.items if item.selected]
        return cls(text=text, items=selected)
