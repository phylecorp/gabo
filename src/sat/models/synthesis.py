"""Synthesis Report result models.

@decision DEC-SYNTHESIS-001
@title Cross-technique synthesis with convergence and divergence tracking
@status accepted
@rationale Synthesis integrates findings from multiple techniques. We track both
convergent judgments (where techniques agree) and divergent signals (where they
produce tension). Confidence levels on individual findings help prioritize
assessments. Intelligence gaps and next steps ensure synthesis is actionable
rather than purely analytical. The bottom_line_assessment is the single most
important output — a clear judgment for decision-makers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from sat.models.base import ArtifactResult


class TechniqueFinding(ArtifactResult):
    """A key finding from a single technique, with confidence assessment."""

    technique_id: str = Field(
        description="Identifier of the technique that produced this finding (e.g., 'brainstorming', 'red_team')"
    )
    technique_name: str = Field(description="Human-readable name of the technique")
    key_finding: str = Field(
        description="The finding itself — a specific insight or conclusion from this technique"
    )
    confidence: Literal["High", "Medium", "Low"] = Field(
        description="Confidence level in this finding based on evidence strength and technique limitations"
    )
    evidence_references: list[str] = Field(
        default_factory=list,
        description="IDs of original evidence items that support this finding (e.g., D-F1, R-C3)",
    )


class SynthesisResult(ArtifactResult):
    """Result of synthesizing findings across multiple techniques."""

    question: str = Field(description="The original question or issue that the analysis addressed")
    techniques_applied: list[str] = Field(
        default_factory=list,
        description="List of technique IDs that were applied in this analysis",
    )
    key_findings: list[TechniqueFinding] = Field(
        default_factory=list,
        description="Important findings from each technique, with confidence assessments",
    )
    convergent_judgments: list[str] = Field(
        default_factory=list,
        description="Areas where multiple techniques agree — reinforced conclusions with higher confidence",
    )
    divergent_signals: list[str] = Field(
        default_factory=list,
        description="Areas where techniques produce tension or contradiction — unresolved complexity",
    )
    highest_confidence_assessments: list[str] = Field(
        default_factory=list,
        description="The most solid conclusions — findings with strong evidence and technique agreement",
    )
    remaining_uncertainties: list[str] = Field(
        default_factory=list,
        description="Key uncertainties that persist even after analysis — irreducible unknowns",
    )
    intelligence_gaps: list[str] = Field(
        default_factory=list,
        description="Missing information that would improve the analysis — specific data or research needs",
    )
    recommended_next_steps: list[str] = Field(
        default_factory=list,
        description="Actionable next steps for decision-makers or analysts — what to do with these findings",
    )
    bottom_line_assessment: str = Field(
        default="",
        description="The single most important judgment — a clear, concise answer to the original question",
    )
