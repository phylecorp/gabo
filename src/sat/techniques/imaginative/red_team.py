"""Red Team Analysis technique implementation."""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.models.red_team import RedTeamResult
from sat.prompts.red_team import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class RedTeamAnalysis(Technique):
    """Think like the adversary by role-playing their perspective."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="red_team",
            name="Red Team Analysis",
            category="imaginative",
            description="Think like the adversary to understand their likely actions.",
            order=2,
            dependencies=["assumptions", "ach", "outside_in"],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return RedTeamResult

    @property
    def temperature(self) -> float | None:
        """Higher temperature enables adversarial creative thinking for red team analysis."""
        return 0.9

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(RedTeamAnalysis())
