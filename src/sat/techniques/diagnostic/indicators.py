"""Indicators/Signposts of Change technique implementation."""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.models.indicators import IndicatorsResult
from sat.prompts.indicators import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class IndicatorsCheck(Technique):
    """Develop indicators to monitor which hypothesis or scenario is emerging."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="indicators",
            name="Indicators/Signposts of Change",
            category="diagnostic",
            description="Track observable events or trends to monitor which future is emerging.",
            order=3,
            dependencies=["ach", "assumptions"],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return IndicatorsResult

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(IndicatorsCheck())
