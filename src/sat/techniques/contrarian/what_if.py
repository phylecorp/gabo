"""'What If?' Analysis technique implementation."""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.models.what_if import WhatIfResult
from sat.prompts.what_if import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class WhatIfAnalysis(Technique):
    """Assume an event has occurred and reason backward to explain how."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="what_if",
            name="'What If?' Analysis",
            category="contrarian",
            description="Assume an event has occurred and work backward to explain how it came about.",
            order=3,
            dependencies=["assumptions", "indicators", "ach"],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return WhatIfResult

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(WhatIfAnalysis())
