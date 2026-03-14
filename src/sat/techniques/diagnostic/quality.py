"""Quality of Information Check technique implementation."""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.models.quality import QualityOfInfoResult
from sat.prompts.quality import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class QualityOfInfoCheck(Technique):
    """Evaluate completeness and soundness of available information sources."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="quality",
            name="Quality of Information Check",
            category="diagnostic",
            description="Evaluate the accuracy, completeness, and reliability of information sources.",
            order=0,
            dependencies=[],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return QualityOfInfoResult

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(QualityOfInfoCheck())
