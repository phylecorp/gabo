"""Outside-In Thinking (STEEP analysis) technique result models.

@decision DEC-STEEP-001
@title STEEP framework for external forces analysis
@status accepted
@rationale Outside-In thinking requires cataloging external forces across five
categories (Social, Technological, Economic, Environmental, Political) with
structured assessment of impact and controllability. The controllability dimension
helps distinguish actionable from contextual forces, critical for strategy.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class STEEPForce(BaseModel):
    """A single external force analyzed through the STEEP framework."""

    category: Literal["Social", "Technological", "Economic", "Environmental", "Political"] = Field(
        description="Which STEEP category this force belongs to"
    )
    force: str = Field(
        description="Short name or label for this force (e.g., 'AI Automation', 'Aging Population')"
    )
    description: str = Field(description="Detailed explanation of this force and its current state")
    impact_on_issue: str = Field(
        description="How this force affects the issue under analysis — direct or indirect effects"
    )
    controllability: Literal["Uncontrollable", "Partially Controllable", "Controllable"] = Field(
        description="The degree to which decision-makers can influence or control this force"
    )
    evidence: str = Field(
        description="Supporting evidence or data that validates the existence and impact of this force"
    )


class OutsideInResult(ArtifactResult):
    """Result of an Outside-In STEEP analysis."""

    issue_description: str = Field(
        default="",
        description="Clear statement of the issue being analyzed from an external perspective",
    )
    forces: list[STEEPForce] = Field(
        default_factory=list, description="All external forces identified across STEEP categories"
    )
    key_external_drivers: list[str] = Field(
        default_factory=list,
        description="The most impactful forces — those with greatest influence on the issue",
    )
    overlooked_factors: list[str] = Field(
        default_factory=list,
        description="External forces that are often missed or underestimated in conventional analysis",
    )
    implications: str = Field(
        default="",
        description="Strategic implications of these external forces — what they mean for decision-making",
    )
