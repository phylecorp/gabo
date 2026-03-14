"""Devil's Advocacy technique models.

@decision DEC-MODEL-DA-001: Structured contrarian challenge with outcome assessment.
Models the Devil's Advocacy process: capture the mainline judgment, enumerate
challenged assumptions with vulnerability ratings, build the alternative case,
and conclude with a three-level outcome (Mainline Holds / Weakened / Overturned).
This maps directly to the primer's method: the advocate must outline the mainline,
select vulnerable assumptions, review evidence quality, highlight contradictory
evidence, and present findings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class ChallengedAssumption(BaseModel):
    """An assumption from the mainline view that has been challenged."""

    assumption: str = Field(description="The specific assumption being challenged")
    challenge: str = Field(description="The argument for why this assumption may be wrong")
    evidence_against: str = Field(
        description="Evidence that contradicts or undermines this assumption"
    )
    vulnerability: Literal["High", "Medium", "Low"] = Field(
        description="How vulnerable this assumption is to being wrong"
    )


class DevilsAdvocacyResult(ArtifactResult):
    """Complete Devil's Advocacy artifact.

    Systematically challenges a dominant analytic judgment by building
    the strongest possible case for an alternative explanation.
    """

    mainline_judgment: str = Field(
        default="", description="The prevailing analytic judgment or consensus being challenged"
    )
    mainline_evidence: list[str] = Field(
        default_factory=list,
        description="Key evidence supporting the mainline judgment",
    )
    challenged_assumptions: list[ChallengedAssumption] = Field(
        default_factory=list,
        description="Assumptions underlying the mainline that have been challenged",
    )
    alternative_hypothesis: str = Field(
        default="",
        description="The best alternative explanation constructed by the Devil's Advocate",
    )
    supporting_evidence_for_alternative: list[str] = Field(
        default_factory=list,
        description="Evidence that supports the alternative hypothesis",
    )
    quality_of_evidence_concerns: list[str] = Field(
        default_factory=list,
        description="Concerns about the quality, reliability, or completeness of the evidence base",
    )
    conclusion: Literal["Mainline Holds", "Mainline Weakened", "Mainline Overturned"] = Field(
        default="Mainline Holds",
        description="Overall assessment of the mainline judgment after the Devil's Advocacy exercise",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="Recommended next steps based on the findings",
    )
