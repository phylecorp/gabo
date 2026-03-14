"""'What If?' Analysis technique models.

@decision DEC-MODEL-WI-001: Backward-reasoning scenario construction.
Models the What If? method: assume the event has occurred, then reason backward
to construct how it could have come about. ScenarioSteps capture the chain of
argumentation with enabling factors at each stage. The backward_reasoning field
captures the primer's "think backwards from the event" instruction. Multiple
alternative pathways are identified, with indicators for monitoring. This
technique shifts focus from "whether" to "how," which is captured in the
probability_reassessment field.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class ScenarioStep(BaseModel):
    """A single step in the chain of argumentation for how the event could occur."""

    step_number: int = Field(description="Sequential step number in the chain of events")
    description: str = Field(description="What happens at this step in the scenario")
    enabling_factors: list[str] = Field(
        description="Conditions or factors that enable this step to occur"
    )


class WhatIfResult(ArtifactResult):
    """Complete 'What If?' Analysis artifact.

    Assumes a specific event has occurred and works backward to explain
    how it could have come about, identifying pathways and indicators.
    """

    assumed_event: str = Field(default="", description="The event that is assumed to have occurred")
    conventional_view: str = Field(
        default="",
        description="The current conventional analytic line about why this event is unlikely",
    )
    triggering_events: list[str] = Field(
        default_factory=list,
        description="Initial triggering events that could set the scenario in motion",
    )
    chain_of_argumentation: list[ScenarioStep] = Field(
        default_factory=list,
        description="Step-by-step chain of events explaining how the assumed event came about",
    )
    backward_reasoning: str = Field(
        default="",
        description="Analysis working backward from the event: what must have happened at each stage",
    )
    alternative_pathways: list[str] = Field(
        default_factory=list,
        description="Other plausible pathways to the same outcome",
    )
    indicators: list[str] = Field(
        default_factory=list,
        description="Observable signs that would suggest this scenario is beginning to unfold",
    )
    consequences: str = Field(
        default="", description="Assessment of the positive and negative consequences of the event"
    )
    probability_reassessment: str = Field(
        default="", description="How the exercise changes the assessment of the event's likelihood"
    )
