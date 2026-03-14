"""Devil's Advocacy technique implementation."""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.models.devils_advocacy import DevilsAdvocacyResult
from sat.prompts.devils_advocacy import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class DevilsAdvocacy(Technique):
    """Challenge a prevailing judgment by building the strongest alternative case."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="devils_advocacy",
            name="Devil's Advocacy",
            category="contrarian",
            description="Challenge a dominant view by building the best case against it.",
            order=0,
            dependencies=["assumptions", "ach"],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return DevilsAdvocacyResult

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(DevilsAdvocacy())
