"""Alternative Futures Analysis technique result models.

@decision DEC-FUTURES-001
@title 2x2 scenario matrix with quadrant narratives
@status accepted
@rationale Alternative Futures uses a 2x2 matrix defined by two key uncertainty
axes (x and y). Each quadrant represents a distinct plausible future scenario.
We enforce exactly 4 scenarios (one per quadrant) and require both axis labels
and quadrant labels to maintain structural clarity. Indicators are observables
that signal which future is emerging — critical for monitoring and adaptation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class FuturesAxis(BaseModel):
    """One axis of uncertainty in the 2x2 scenario matrix."""

    name: str = Field(
        description="Name of this uncertainty dimension (e.g., 'Economic Growth', 'Regulatory Environment')"
    )
    low_label: str = Field(
        description="Label for the low end of this axis (e.g., 'Slow Growth', 'Minimal Regulation')"
    )
    high_label: str = Field(
        description="Label for the high end of this axis (e.g., 'Rapid Growth', 'Heavy Regulation')"
    )


class ScenarioQuadrant(BaseModel):
    """One quadrant scenario in the 2x2 matrix — a plausible future."""

    quadrant_label: str = Field(
        description="Quadrant position label (e.g., 'High Growth / Low Stability', 'Low Growth / High Stability')"
    )
    scenario_name: str = Field(
        description="Colorful, memorable name for this scenario (e.g., 'The Wild West', 'Fortress Economy')"
    )
    narrative: str = Field(
        description="Detailed story of how this future unfolds — events, dynamics, and consequences"
    )
    indicators: list[str] = Field(
        default_factory=list,
        description="Observable signals that would indicate this scenario is emerging — early warning signs",
    )
    policy_implications: str = Field(
        description="What this scenario means for strategy, policy, or decision-making"
    )


class AltFuturesResult(ArtifactResult):
    """Result of an Alternative Futures scenario analysis."""

    focal_issue: str = Field(
        default="", description="The strategic issue or question driving this futures analysis"
    )
    key_uncertainties: list[str] = Field(
        default_factory=list,
        description="Major uncertainties identified before selecting the two axes — context for axis choice",
    )
    x_axis: FuturesAxis | None = Field(
        default=None, description="The horizontal axis of the 2x2 matrix — first key uncertainty"
    )
    y_axis: FuturesAxis | None = Field(
        default=None, description="The vertical axis of the 2x2 matrix — second key uncertainty"
    )
    scenarios: list[ScenarioQuadrant] = Field(
        default_factory=list,
        description="Exactly four scenario quadrants — one for each combination of axis extremes",
    )
    cross_cutting_indicators: list[str] = Field(
        default_factory=list,
        description="Indicators relevant to multiple scenarios — signals that don't discriminate cleanly",
    )
    strategic_implications: str = Field(
        default="",
        description="Overall strategic implications across all scenarios — robust strategies or hedges",
    )
