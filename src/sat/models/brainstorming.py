"""Brainstorming technique result models.

@decision DEC-BRAINSTORM-001
@title Brainstorming model with clustered ideas
@status accepted
@rationale Structured divergent thinking: capture raw ideas with provenance,
cluster them by theme, and surface priority areas and unconventional insights.
The clustering step ensures ideas are organized for synthesis downstream.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class Idea(BaseModel):
    """A single brainstormed idea with provenance."""

    id: str = Field(description="Unique identifier for this idea (e.g., I1, I2, I3)")
    text: str = Field(description="The idea itself, stated clearly and concisely")
    source_rationale: str = Field(
        description="What prompted this idea — the line of thinking or trigger that generated it"
    )


class IdeaCluster(BaseModel):
    """A thematic cluster of related ideas."""

    name: str = Field(
        description="Name of this cluster theme (e.g., 'Technological Disruption', 'Policy Levers')"
    )
    ideas: list[Idea] = Field(description="Ideas belonging to this cluster")
    significance: str = Field(
        description="Why this cluster matters — its relevance to the focal question"
    )


class BrainstormingResult(ArtifactResult):
    """Result of a brainstorming session on a focal question."""

    focal_question: str = Field(
        default="", description="The question or problem that drove this brainstorming session"
    )
    divergent_ideas: list[Idea] = Field(
        default_factory=list,
        description="All ideas generated during brainstorming, in order of generation",
    )
    clusters: list[IdeaCluster] = Field(
        default_factory=list, description="Ideas grouped into thematic clusters for organization"
    )
    priority_areas: list[str] = Field(
        default_factory=list,
        description="The most important themes or directions identified from the clusters",
    )
    unconventional_insights: list[str] = Field(
        default_factory=list,
        description="Non-obvious or creative insights that emerged — ideas that challenge assumptions",
    )
