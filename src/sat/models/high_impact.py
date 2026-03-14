"""High-Impact/Low-Probability Analysis technique models.

@decision DEC-MODEL-HI-001: Pathway-based analysis of unlikely consequential events.
Models the High-Impact/Low-Probability method: define the event, explain why it's
considered unlikely, assess its impact, then develop multiple plausible pathways
by which it could occur. Each pathway includes triggers and observable indicators
for monitoring. Deflection factors capture what could prevent the event. This
directly maps the primer's method of postulating pathways, inserting triggers,
and identifying observables.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class Pathway(BaseModel):
    """A plausible pathway by which the unlikely event could occur."""

    name: str = Field(description="Short descriptive name for this pathway")
    description: str = Field(description="How this pathway unfolds — the chain of events")
    triggers: list[str] = Field(
        description="Triggering events that could set this pathway in motion"
    )
    indicators: list[str] = Field(description="Observable signs that this pathway is materializing")
    plausibility: Literal["Possible", "Plausible", "Remote"] = Field(
        description="How plausible this particular pathway is"
    )


class HighImpactResult(ArtifactResult):
    """Complete High-Impact/Low-Probability artifact.

    Explores an unlikely but consequential event by defining it,
    developing plausible pathways to its occurrence, and identifying
    indicators for early warning.
    """

    event_definition: str = Field(
        default="", description="Clear definition of the high-impact event being analyzed"
    )
    why_considered_unlikely: str = Field(
        default="", description="Why this event is currently considered unlikely"
    )
    impact_assessment: str = Field(
        default="", description="Assessment of the consequences if this event were to occur"
    )
    pathways: list[Pathway] = Field(
        default_factory=list, description="Plausible pathways by which this event could come about"
    )
    deflection_factors: list[str] = Field(
        default_factory=list,
        description="Factors that could prevent the event or deflect its trajectory",
    )
    policy_implications: str = Field(
        default="", description="Implications for policy and preparedness"
    )
