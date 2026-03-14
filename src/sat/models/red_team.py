"""Red Team Analysis technique result models.

@decision DEC-REDTEAM-001
@title Red Team adversary role-play structure
@status accepted
@rationale Red Team analysis requires deep role-play: we embody an adversary,
understand their cultural/political/organizational context, and produce a
first-person memo AS them. The memo is the core artifact — it forces authentic
perspective-taking rather than analytical distance. Supporting fields capture
motivations, constraints, and predicted actions to aid synthesis.
"""

from __future__ import annotations

from sat.models.base import ArtifactResult
from pydantic import Field


class RedTeamResult(ArtifactResult):
    """Result of a Red Team adversarial role-play analysis."""

    adversary_identity: str = Field(
        default="",
        description="Who we are role-playing as — the adversary's identity, role, or organization",
    )
    adversary_context: str = Field(
        default="",
        description="The adversary's cultural, political, organizational, or strategic milieu — their worldview",
    )
    perception_of_threats: str = Field(
        default="",
        description="What this adversary perceives as threats to their interests or goals",
    )
    perception_of_opportunities: str = Field(
        default="",
        description="What this adversary sees as opportunities to exploit or advance their position",
    )
    first_person_memo: str = Field(
        default="",
        description="The main artifact: a memo written AS the adversary, in their voice, expressing their strategic view. This is first-person role-play, not third-person analysis.",
    )
    predicted_actions: list[str] = Field(
        default_factory=list,
        description="Specific actions this adversary is likely to take, based on their motivations and constraints",
    )
    key_motivations: list[str] = Field(
        default_factory=list,
        description="Core drivers behind the adversary's behavior — what they value, fear, or seek",
    )
    constraints_on_adversary: list[str] = Field(
        default_factory=list,
        description="Factors that limit the adversary's freedom of action — resources, politics, ethics, risks",
    )
