"""Indicators/Signposts of Change technique models.

@decision DEC-TECHNIQUE-003
@title Indicators/Signposts schema design
@status accepted
@rationale Forward-looking indicator tracking enables early warning
of change. Each indicator captures current status on a 5-level scale
(Serious/Substantial/Moderate/Low/Negligible Concern) and trend direction
(Worsening/Stable/Improving). This design supports both snapshot assessment
and trend monitoring over time. The model separates individual indicator
tracking (granular observations) from overall trajectory assessment
(strategic implications). Topic grouping enables indicators to be organized
by theme (military, economic, political, etc). Trigger mechanisms surface
the specific combinations or thresholds that would signal significant change,
supporting early warning and contingency planning.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class Indicator(BaseModel):
    """A single observable indicator or signpost of potential change."""

    topic: str = Field(
        description="Thematic category for this indicator (e.g., Military Activity, Economic Pressure, Political Stability)"
    )
    indicator: str = Field(
        description="Specific observable event, metric, or signpost being tracked"
    )
    current_status: Literal[
        "Serious Concern",
        "Substantial Concern",
        "Moderate Concern",
        "Low Concern",
        "Negligible Concern",
    ] = Field(description="Current assessment level for this indicator")
    trend: Literal["Worsening", "Stable", "Improving"] = Field(
        description="Direction of change for this indicator over recent period"
    )
    notes: str = Field(
        description="Additional context, recent developments, or explanation of the status and trend"
    )


class IndicatorsResult(ArtifactResult):
    """Complete Indicators/Signposts of Change artifact.

    Tracks observable indicators of potential change, enabling early
    warning and systematic monitoring of evolving situations.
    """

    hypothesis_or_scenario: str = Field(
        description="The hypothesis, scenario, or situation being monitored through these indicators"
    )
    indicators: list[Indicator] = Field(
        default_factory=list,
        description="List of all indicators being tracked, with current status and trends",
    )
    trigger_mechanisms: list[str] = Field(
        default_factory=list,
        description="Specific combinations, thresholds, or patterns of indicators that would signal significant change",
    )
    overall_trajectory: str = Field(
        default="",
        description="Summary assessment of the overall direction and implications of indicator trends",
    )
