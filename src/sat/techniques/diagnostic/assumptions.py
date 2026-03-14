"""Key Assumptions Check technique implementation."""

from __future__ import annotations

from sat.models.assumptions import KeyAssumptionsResult
from sat.models.base import ArtifactResult
from sat.prompts.assumptions import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class KeyAssumptionsCheck(Technique):
    """Identify and challenge key assumptions underlying an analytic judgment."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="assumptions",
            name="Key Assumptions Check",
            category="diagnostic",
            description="Identify and challenge key working assumptions underlying the analytic line.",
            order=1,
            dependencies=["quality"],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return KeyAssumptionsResult

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(KeyAssumptionsCheck())
