"""Analysis of Competing Hypotheses (ACH) technique models.

@decision DEC-TECHNIQUE-004
@title ACH schema design
@status accepted
@rationale ACH combats confirmation bias by systematically evaluating
evidence against all competing hypotheses. The model separates hypotheses,
evidence items, and ratings into distinct entities to enable matrix-style
analysis. Each evidence item captures credibility and relevance independently
of its diagnostic value. Ratings use a 3-level scale (Consistent/Inconsistent/
Neutral) with explanations, avoiding false precision while capturing the
diagnostic relationship. Inconsistency scores are computed in post-processing
(counting Inconsistent ratings per hypothesis) to identify which hypotheses
are most undermined by available evidence. The model surfaces most_likely
and rejected hypotheses explicitly, along with diagnosticity notes explaining
which evidence was most decisive. Missing_evidence captures gaps that would
materially affect the analysis, supporting collection prioritization.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class ACHEvidence(BaseModel):
    """A single piece of evidence evaluated in the ACH matrix."""

    id: str = Field(description="Unique identifier for this evidence item (e.g., E1, E2, EVD-A)")
    description: str = Field(description="Clear statement of the evidence or information item")
    credibility: Literal["High", "Medium", "Low"] = Field(
        description="Reliability and trustworthiness of this evidence"
    )
    relevance: Literal["High", "Medium", "Low"] = Field(
        description="How directly this evidence bears on the hypotheses being evaluated"
    )
    source_evidence_ids: list[str] = Field(
        default_factory=list,
        description="IDs of original evidence items this was derived from (e.g., D-F1, R-C3). Maps ACH evidence back to the input evidence registry.",
    )


class ACHHypothesis(BaseModel):
    """A single hypothesis being evaluated in the ACH analysis."""

    id: str = Field(description="Unique identifier for this hypothesis (e.g., H1, H2, HYP-A)")
    description: str = Field(
        description="Clear statement of the hypothesis or explanation being considered"
    )


class ACHRating(BaseModel):
    """A single cell in the ACH matrix: how one piece of evidence relates to one hypothesis."""

    evidence_id: str = Field(description="ID of the evidence item being evaluated")
    hypothesis_id: str = Field(
        description="ID of the hypothesis being evaluated against this evidence"
    )
    rating: Literal["C", "I", "N"] = Field(
        description="Relationship between evidence and hypothesis: C=Consistent, I=Inconsistent, N=Neutral/Not Applicable"
    )
    explanation: str = Field(
        description="Brief explanation of why this evidence is consistent, inconsistent, or neutral with respect to this hypothesis"
    )


class ACHResult(ArtifactResult):
    """Complete Analysis of Competing Hypotheses artifact.

    Systematically evaluates all plausible hypotheses against all
    available evidence to identify which hypotheses best explain
    the evidence and which can be rejected.
    """

    hypotheses: list[ACHHypothesis] = Field(
        default_factory=list,
        description="All competing hypotheses being evaluated in this analysis",
    )
    evidence: list[ACHEvidence] = Field(
        default_factory=list, description="All evidence items used to evaluate the hypotheses"
    )
    matrix: list[ACHRating] = Field(
        default_factory=list,
        description="Complete ACH matrix: all evidence-hypothesis relationships and ratings",
    )
    inconsistency_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Computed inconsistency score for each hypothesis (hypothesis_id -> score). Filled in post-processing.",
    )
    most_likely: str = Field(
        default="",
        description="The hypothesis ID that is most consistent with the evidence",
    )
    rejected: list[str] = Field(
        default_factory=list,
        description="Hypothesis IDs that can be rejected or significantly discounted based on the evidence",
    )
    diagnosticity_notes: str = Field(
        default="",
        description="Discussion of which evidence was most diagnostic (distinguished between hypotheses) and why",
    )
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="Key evidence that, if available, would materially affect the analysis or allow rejection of additional hypotheses",
    )
