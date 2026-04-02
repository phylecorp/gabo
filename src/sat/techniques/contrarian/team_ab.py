"""Team A/Team B technique implementation."""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.models.team_ab import TeamABResult
from sat.prompts.team_ab import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register


class TeamAB(Technique):
    """Develop competing cases for rival hypotheses with jury assessment."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="team_ab",
            name="Team A/Team B",
            category="contrarian",
            description="Develop two competing cases for rival hypotheses and assess which is stronger.",
            order=1,
            dependencies=["assumptions", "ach"],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return TeamABResult

    @property
    def temperature(self) -> float | None:
        """Higher temperature enables distinct competing cases for Team A/Team B analysis."""
        return 0.9

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)


register(TeamAB())
