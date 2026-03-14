"""Analysis of Competing Hypotheses (ACH) technique implementation.

@decision DEC-TECH-ACH-001: Deterministic post-processing for inconsistency scores.
The LLM generates the matrix of evidence-hypothesis ratings. Post-processing
computes weighted inconsistency scores: each "I" rating counts as 1.0 for
High-credibility evidence, 0.5 for Medium, and 0.25 for Low. This separates
the analytical judgment (LLM) from the computation (Python), following the
thin-technique principle from DEC-TECH-001.

@decision DEC-TECH-ACH-002: Override max_tokens to 16384 for ACH.
A full ACH matrix — 4-6 hypotheses × 8-12 evidence items — requires 6000-8000
tokens minimum. The provider default of 4096 silently truncates mid-matrix,
producing empty or partial inconsistency_scores. 16384 gives headroom for large
analyses (many hypotheses, verbose evidence) without being unreasonably large.
"""

from __future__ import annotations

from sat.models.ach import ACHResult
from sat.models.base import ArtifactResult
from sat.prompts.ach import build_prompt
from sat.providers.base import LLMMessage
from sat.techniques.base import Technique, TechniqueContext, TechniqueMetadata
from sat.techniques.registry import register

CREDIBILITY_WEIGHTS = {"High": 1.0, "Medium": 0.5, "Low": 0.25}


class ACHTechnique(Technique):
    """Systematically evaluate competing hypotheses against available evidence."""

    @property
    def metadata(self) -> TechniqueMetadata:
        return TechniqueMetadata(
            id="ach",
            name="Analysis of Competing Hypotheses",
            category="diagnostic",
            description="Array evidence against multiple hypotheses to find the best explanation.",
            order=2,
            dependencies=["assumptions", "quality"],
        )

    @property
    def output_schema(self) -> type[ArtifactResult]:
        return ACHResult

    @property
    def max_tokens(self) -> int:
        """ACH needs 6000-8000+ tokens for a full hypothesis matrix; use 16384."""
        return 16384

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        return build_prompt(ctx)

    def post_process(self, result: ArtifactResult) -> ArtifactResult:
        """Compute weighted inconsistency scores from the ACH matrix."""
        assert isinstance(result, ACHResult)

        evidence_cred = {e.id: e.credibility for e in result.evidence}
        scores: dict[str, float] = {h.id: 0.0 for h in result.hypotheses}

        for rating in result.matrix:
            if rating.rating == "I":
                weight = CREDIBILITY_WEIGHTS.get(
                    evidence_cred.get(rating.evidence_id, "Medium"), 0.5
                )
                scores[rating.hypothesis_id] = scores.get(rating.hypothesis_id, 0.0) + weight

        result.inconsistency_scores = scores
        return result


register(ACHTechnique())
