"""Brainstorming technique implementation."""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.models.brainstorming import BrainstormingResult
from sat.prompts.brainstorming import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class Brainstorming(Technique):
    """Generate a wide range of ideas and hypotheses through structured brainstorming."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="brainstorming",
            name="Brainstorming",
            category="imaginative",
            description="Generate a wide range of ideas and hypotheses through divergent thinking.",
            order=0,
            dependencies=[],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return BrainstormingResult

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(Brainstorming())
