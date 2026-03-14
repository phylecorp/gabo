"""Quality of Information Check technique models.

@decision DEC-TECHNIQUE-002
@title Quality of Information schema design
@status accepted
@rationale Systematic source evaluation prevents overreliance on weak
intelligence. Each source captures reliability, access quality, and
corroboration status. The model distinguishes between individual source
assessment (rows) and aggregate intelligence quality (result). Including
source_type (HUMINT/SIGINT/OSINT/etc) enables pattern detection across
collection disciplines. Gap identification and deception indicators
are surfaced at the result level to highlight collection requirements
and analytic caution flags. This structure supports both initial source
vetting and ongoing source quality reassessment.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class SourceQualityRow(BaseModel):
    """Quality assessment for a single intelligence source."""

    source_id: str = Field(description="Unique identifier for this source (e.g., S1, S2, SOURCE-A)")
    description: str = Field(
        description="Brief description of the source or type of information provided"
    )
    source_type: str = Field(
        description="Intelligence discipline or collection method (e.g., HUMINT, SIGINT, OSINT, IMINT, MASINT, documents)"
    )
    reliability: Literal["High", "Medium", "Low"] = Field(
        description="Overall reliability rating for this source based on track record and credibility"
    )
    access_quality: str = Field(
        description="Assessment of the source's access to the information reported (direct, secondhand, indirect, etc.)"
    )
    corroboration: str = Field(
        description="What other sources or evidence corroborate this source's reporting, if any"
    )
    gaps: str = Field(
        description="Key gaps, limitations, or missing context in this source's reporting"
    )


class QualityOfInfoResult(ArtifactResult):
    """Complete Quality of Information Check artifact.

    Evaluates the reliability and completeness of intelligence sources,
    identifies gaps, and flags potential deception indicators.
    """

    sources: list[SourceQualityRow] = Field(
        default_factory=list,
        description="Detailed assessment of each intelligence source used in the analysis",
    )
    overall_assessment: str = Field(
        default="",
        description="Summary judgment on the overall quality and sufficiency of available intelligence",
    )
    key_gaps: list[str] = Field(
        default_factory=list,
        description="Critical information gaps that limit confidence in the analysis",
    )
    deception_indicators: list[str] = Field(
        default_factory=list,
        description="Potential signs of denial, deception, or manipulation in the intelligence picture",
    )
    collection_requirements: list[str] = Field(
        default_factory=list,
        description="Specific collection tasks or intelligence requirements needed to address gaps",
    )
