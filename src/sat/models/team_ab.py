"""Team A/Team B technique models.

@decision DEC-MODEL-TAB-001: Dual-team debate structure with jury assessment.
Models the Team A/Team B process from the primer: two teams develop the best
case for competing hypotheses, then a jury assesses which is stronger. Each team
position includes its hypothesis, key assumptions, evidence, argument, and
acknowledged weaknesses. Debate points capture specific topics of disagreement
and their resolution. The jury assessment provides an independent evaluation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class TeamPosition(BaseModel):
    """The position developed by one team."""

    team: Literal["A", "B"] = Field(description="Which team developed this position")
    hypothesis: str = Field(description="The hypothesis this team is defending")
    key_assumptions: list[str] = Field(
        default_factory=list,
        description="Key assumptions underlying this team's argument",
    )
    key_evidence: list[str] = Field(
        default_factory=list,
        description="Most important evidence supporting this team's position",
    )
    argument: str = Field(description="The team's full argument for their hypothesis")
    acknowledged_weaknesses: list[str] = Field(
        default_factory=list,
        description="Weaknesses in their own position that the team acknowledges",
    )


class DebatePoint(BaseModel):
    """A specific point of contention between the two teams."""

    topic: str = Field(description="The specific topic or issue being debated")
    team_a_position: str = Field(description="Team A's stance on this point")
    team_b_position: str = Field(description="Team B's stance on this point")
    resolution: str = Field(
        description="How this point of contention was resolved, or why it remains unresolved"
    )


class TeamABResult(ArtifactResult):
    """Complete Team A/Team B artifact.

    Presents two competing analytical positions, their debate,
    and an independent jury assessment of which case is stronger.
    """

    team_a: TeamPosition | None = Field(
        default=None, description="Team A's complete position and argument"
    )
    team_b: TeamPosition | None = Field(
        default=None, description="Team B's complete position and argument"
    )
    debate_points: list[DebatePoint] = Field(
        default_factory=list, description="Key points of contention that emerged during the debate"
    )
    jury_assessment: str = Field(
        default="", description="The independent jury's overall assessment of both arguments"
    )
    stronger_case: Literal["A", "B", "Indeterminate"] = Field(
        default="Indeterminate", description="Which team presented the stronger case"
    )
    areas_of_agreement: list[str] = Field(
        default_factory=list,
        description="Points where both teams agree despite their different conclusions",
    )
    recommended_research: list[str] = Field(
        default_factory=list,
        description="Research and collection priorities identified through the debate",
    )
