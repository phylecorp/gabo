"""Adversarial analysis result models.

@decision DEC-ADV-001: Adversarial results as ArtifactResult subclasses.
@title Separate artifacts for critique, rebuttal, and adjudication
@status accepted
@rationale Critique, rebuttal, and adjudication each produce separate artifacts
for provenance. AdversarialExchange wraps the full debate for a single technique.
Each round is independently serializable for artifact writing.

@decision DEC-ADV-005: Trident mode adds investigator and convergence to exchange.
@title ConvergenceResult and investigator_result extend AdversarialExchange
@status accepted
@rationale When three providers participate (trident mode), the investigator runs
an independent re-analysis and ConvergenceResult compares all three perspectives.
Both are optional fields so the model remains backward-compatible with dual mode.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class Challenge(BaseModel):
    """A specific challenge raised by the challenger."""

    claim: str = Field(description="The specific claim or finding being challenged")
    challenge: str = Field(description="The nature of the challenge or critique")
    evidence: str = Field(description="Evidence or reasoning supporting the challenge")
    severity: str = Field(description="Impact if challenge is valid: 'High', 'Medium', 'Low'")


class CritiqueResult(ArtifactResult):
    """Result of a challenger's critique of a technique output."""

    agreements: list[str] = Field(
        default_factory=list, description="Points where the challenger agrees with the primary"
    )
    challenges: list[Challenge] = Field(
        default_factory=list, description="Specific challenges to the primary's analysis"
    )
    alternative_interpretations: list[str] = Field(
        default_factory=list,
        description="Alternative ways to interpret the evidence",
    )
    evidence_gaps: list[str] = Field(
        default_factory=list,
        description="Evidence gaps the primary analysis didn't address",
    )
    severity: str = Field(
        default="Moderate",
        description="Overall severity of the critique: 'Major', 'Moderate', 'Minor'",
    )
    overall_assessment: str = Field(
        default="",
        description="Challenger's overall assessment of the primary's analysis",
    )
    revised_confidence: str = Field(
        default="Same",
        description="Suggested revised confidence: 'Higher', 'Same', 'Lower', 'Much Lower'",
    )


class RebuttalPoint(BaseModel):
    """A rebuttal to a specific challenge."""

    challenge: str = Field(description="The challenge being addressed")
    response: str = Field(description="The primary's response to this challenge")
    conceded: bool = Field(description="Whether the primary concedes this point")


class RebuttalResult(ArtifactResult):
    """Result of the primary's rebuttal to a critique."""

    accepted_challenges: list[str] = Field(
        default_factory=list, description="Challenges the primary accepts as valid"
    )
    rejected_challenges: list[RebuttalPoint] = Field(
        default_factory=list,
        description="Challenges the primary rejects with reasoning",
    )
    revised_conclusions: str = Field(
        default="",
        description="Updated conclusions incorporating accepted challenges",
    )


class AdjudicationResult(ArtifactResult):
    """Result of adjudicator resolving disputed points."""

    resolved_for_primary: list[str] = Field(
        default_factory=list, description="Points resolved in favor of the primary"
    )
    resolved_for_challenger: list[str] = Field(
        default_factory=list,
        description="Points resolved in favor of the challenger",
    )
    unresolved: list[str] = Field(
        default_factory=list, description="Points that remain genuinely uncertain"
    )
    synthesis_assessment: str = Field(default="", description="Adjudicator's integrated assessment")


class DebateRound(BaseModel):
    """A single round of critique and rebuttal."""

    round_number: int = Field(description="Round number (1-indexed)")
    critique: CritiqueResult = Field(description="The challenger's critique")
    rebuttal: RebuttalResult | None = Field(
        default=None, description="The primary's rebuttal, if any"
    )


class ConvergencePoint(BaseModel):
    """A point where independent providers agree."""

    claim: str = Field(description="The claim or conclusion that providers agree on")
    agreeing_providers: list[str] = Field(description="Provider roles that agree")
    confidence_boost: str = Field(description="'High', 'Medium', 'Low'")
    reasoning: str = Field(description="Why this convergence is significant")


class DivergencePoint(BaseModel):
    """A point where independent providers disagree."""

    claim: str = Field(description="The claim or area of disagreement")
    primary_position: str = Field(description="Primary analyst's position")
    investigator_position: str = Field(description="Investigator's independent position")
    challenger_position: str = Field(description="Challenger's position (from critique)")
    significance: str = Field(description="'Critical', 'Important', 'Minor'")
    likely_cause: str = Field(description="Why providers likely disagree")


class ConvergenceResult(ArtifactResult):
    """Result of convergence analysis comparing independent assessments."""

    convergence_points: list[ConvergencePoint] = Field(default_factory=list)
    divergence_points: list[DivergencePoint] = Field(default_factory=list)
    novel_insights: list[str] = Field(
        default_factory=list,
        description="Insights only the investigator found",
    )
    confidence_delta: str = Field(
        default="",
        description="How convergence analysis changes overall confidence",
    )
    analytical_blindspots_identified: list[str] = Field(default_factory=list)


class AdversarialExchange(BaseModel):
    """Complete adversarial exchange for a single technique."""

    technique_id: str = Field(description="Technique that was debated")
    initial_result: ArtifactResult = Field(description="The primary's initial technique output")
    rounds: list[DebateRound] = Field(description="Critique-rebuttal rounds")
    adjudication: AdjudicationResult | None = Field(
        default=None, description="Final adjudication, if any"
    )
    investigator_result: ArtifactResult | None = Field(
        default=None,
        description="Investigator's independent re-analysis (trident mode only)",
    )
    convergence: ConvergenceResult | None = Field(
        default=None,
        description="Convergence analysis result (trident mode only)",
    )
