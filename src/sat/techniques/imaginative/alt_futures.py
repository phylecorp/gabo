"""Alternative Futures Analysis technique implementation."""

from __future__ import annotations

from sat.models.alt_futures import AltFuturesResult
from sat.models.base import ArtifactResult
from sat.prompts.alt_futures import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class AltFuturesAnalysis(Technique):
    """Develop multiple plausible future scenarios using a 2x2 matrix."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="alt_futures",
            name="Alternative Futures Analysis",
            category="imaginative",
            description="Develop multiple plausible futures using a 2x2 scenario matrix.",
            order=3,
            dependencies=["outside_in", "assumptions"],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return AltFuturesResult

    @property
    def temperature(self) -> float | None:
        """Higher temperature enables diverse scenario generation for alternative futures."""
        return 0.9

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(AltFuturesAnalysis())
