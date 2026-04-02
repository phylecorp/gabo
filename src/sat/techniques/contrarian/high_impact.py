"""High-Impact/Low-Probability Analysis technique implementation."""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.models.high_impact import HighImpactResult
from sat.prompts.high_impact import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class HighImpactAnalysis(Technique):
    """Explore unlikely but consequential events by developing plausible pathways."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="high_impact",
            name="High-Impact/Low-Probability Analysis",
            category="contrarian",
            description="Explore unlikely but consequential events by developing plausible pathways.",
            order=2,
            dependencies=["assumptions", "indicators"],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return HighImpactResult

    @property
    def temperature(self) -> float | None:
        """Higher temperature enables creative low-probability pathway construction for high-impact analysis."""
        return 0.9

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(HighImpactAnalysis())
