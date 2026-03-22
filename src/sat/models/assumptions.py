"""Key Assumptions Check technique models.

@decision DEC-TECHNIQUE-001
@title Key Assumptions Check schema design
@status accepted
@rationale Structured assumption tracking enables systematic identification
of analytic vulnerabilities. Each assumption captures its confidence basis,
what could undermine it, and impact if wrong. The model separates individual
assumptions (rows) from the overall assessment (result), enabling both granular
tracking and high-level vulnerability identification. This design supports
both initial assumption identification and ongoing monitoring of assumption
validity throughout the analysis lifecycle.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class AssumptionRow(BaseModel):
    """A single key assumption in the analysis."""

    assumption: str = Field(
        description="Clear statement of the assumption being made in the analysis"
    )
    confidence: Literal["High", "Medium", "Low"] = Field(
        description="Analyst's confidence level in this assumption"
    )
    basis_for_confidence: str = Field(
        description="Evidence, reasoning, or sources that support this assumption"
    )
    what_undermines: str = Field(
        description="Specific conditions, events, or evidence that would undermine or invalidate this assumption"
    )
    impact_if_wrong: str = Field(
        description="Consequences for the analysis if this assumption proves incorrect"
    )
    evidence_references: list[str] = Field(
        default_factory=list,
        description="IDs of evidence items that support or relate to this assumption (e.g., D-F1, R-C3)",
    )


class KeyAssumptionsResult(ArtifactResult):
    """Complete Key Assumptions Check artifact.

    Identifies and evaluates the foundational assumptions underlying
    the analysis, highlighting vulnerabilities and monitoring needs.
    """

    analytic_line: str = Field(
        default="", description="The main analytic judgment or hypothesis being examined"
    )
    assumptions: list[AssumptionRow] = Field(
        default_factory=list, description="List of all key assumptions identified in the analysis"
    )
    most_vulnerable: list[str] = Field(
        default_factory=list,
        description="The assumptions most at risk of being wrong, stated clearly for monitoring",
    )
    recommended_monitoring: list[str] = Field(
        default_factory=list,
        description="Specific actions or indicators to track for validating or invalidating key assumptions",
    )
