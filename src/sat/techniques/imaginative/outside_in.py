"""Outside-In Thinking (STEEP analysis) technique implementation."""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.models.outside_in import OutsideInResult
from sat.prompts.outside_in import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class OutsideInThinking(Technique):
    """Identify external STEEP forces that could shape the issue."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="outside_in",
            name="Outside-In Thinking",
            category="imaginative",
            description="Identify external STEEP forces that could shape the issue.",
            order=1,
            dependencies=[],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return OutsideInResult

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(OutsideInThinking())
