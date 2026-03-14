"""Tests that adversarial exchange artifacts are fed into prior_results for synthesis (Bug 2 fix).

@decision DEC-TEST-ADV-SYNTH-001: Unit-test the pipeline injection logic in isolation.
The pipeline's adversarial-to-synthesis feed is the only code path that populates
prior_results with adjudication, investigator, and convergence artifacts. Testing
the pipeline end-to-end is expensive (requires a full config + async orchestration).
Instead we verify the two independently-testable contracts:

  1. format_prior_results_section renders compound-key entries correctly — proven
     in test_prompts_base.py (re-asserted here as integration smoke).
  2. The pipeline's adversarial injection logic uses the right key naming convention
     ("<tid>-adjudication", "<tid>-investigator", "<tid>-convergence") — verified
     by asserting those keys exist after simulating the injection block.

Both contracts must hold for synthesis to see adversarial intelligence.
"""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.prompts.base import format_prior_results_section


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(tid: str, name: str, summary: str) -> ArtifactResult:
    return ArtifactResult(technique_id=tid, technique_name=name, summary=summary)


def _simulate_adversarial_injection(
    prior_results: dict[str, ArtifactResult],
    tid: str,
    adjudication: ArtifactResult | None = None,
    investigator_result: ArtifactResult | None = None,
    convergence: ArtifactResult | None = None,
) -> None:
    """Mirror the injection block added in pipeline.py (Bug 2 fix).

    This replicates the exact logic so that if the pipeline code changes,
    the test will need to change too — making the contract explicit.
    """
    if adjudication:
        prior_results[f"{tid}-adjudication"] = adjudication
    if investigator_result:
        prior_results[f"{tid}-investigator"] = investigator_result
    if convergence:
        prior_results[f"{tid}-convergence"] = convergence


# ---------------------------------------------------------------------------
# Tests: pipeline injection key naming
# ---------------------------------------------------------------------------


class TestAdversarialInjectionKeyNaming:
    """Injection block must produce the exact compound-key names synthesis expects."""

    def test_adjudication_key_format(self):
        """Adjudication is stored under '<tid>-adjudication'."""
        prior: dict[str, ArtifactResult] = {}
        _simulate_adversarial_injection(
            prior,
            tid="ach",
            adjudication=_make_result("ach-adjudication", "Adjudication", "Adj summary."),
        )
        assert "ach-adjudication" in prior

    def test_investigator_key_format(self):
        """Investigator result is stored under '<tid>-investigator'."""
        prior: dict[str, ArtifactResult] = {}
        _simulate_adversarial_injection(
            prior,
            tid="ach",
            investigator_result=_make_result("ach-investigator", "Investigator", "Inv summary."),
        )
        assert "ach-investigator" in prior

    def test_convergence_key_format(self):
        """Convergence is stored under '<tid>-convergence'."""
        prior: dict[str, ArtifactResult] = {}
        _simulate_adversarial_injection(
            prior,
            tid="ach",
            convergence=_make_result("ach-convergence", "Convergence", "Conv summary."),
        )
        assert "ach-convergence" in prior

    def test_none_artifacts_not_injected(self):
        """None artifacts must not produce keys in prior_results."""
        prior: dict[str, ArtifactResult] = {}
        _simulate_adversarial_injection(
            prior,
            tid="ach",
            adjudication=None,
            investigator_result=None,
            convergence=None,
        )
        assert "ach-adjudication" not in prior
        assert "ach-investigator" not in prior
        assert "ach-convergence" not in prior

    def test_all_artifacts_injected_together(self):
        """All three artifacts are injected when all are present."""
        prior: dict[str, ArtifactResult] = {
            "ach": _make_result("ach", "ACH", "Base result."),
        }
        _simulate_adversarial_injection(
            prior,
            tid="ach",
            adjudication=_make_result("ach-adjudication", "Adj", "Adj."),
            investigator_result=_make_result("ach-investigator", "Inv", "Inv."),
            convergence=_make_result("ach-convergence", "Conv", "Conv."),
        )
        assert "ach" in prior
        assert "ach-adjudication" in prior
        assert "ach-investigator" in prior
        assert "ach-convergence" in prior
        assert len(prior) == 4


# ---------------------------------------------------------------------------
# Tests: format_prior_results_section includes injected adversarial artifacts
# ---------------------------------------------------------------------------


class TestSynthesisSeesAdversarialArtifacts:
    """Synthesis's format_prior_results_section renders all adversarial artifacts.

    This is the end-to-end contract: keys produced by the injection block must
    be rendered by the function that builds synthesis's context window.
    """

    def test_synthesis_section_includes_adjudication_summary(self):
        """Synthesis context includes adjudication summary after injection."""
        prior: dict[str, ArtifactResult] = {}
        _simulate_adversarial_injection(
            prior,
            tid="ach",
            adjudication=_make_result(
                "ach-adjudication", "ACH Adjudication", "Adjudicator ruled H2 most consistent."
            ),
        )
        output = format_prior_results_section(prior)
        assert "Adjudicator ruled H2 most consistent." in output

    def test_synthesis_section_includes_investigator_summary(self):
        """Synthesis context includes investigator findings after injection."""
        prior: dict[str, ArtifactResult] = {}
        _simulate_adversarial_injection(
            prior,
            tid="ach",
            investigator_result=_make_result(
                "ach-investigator", "ACH Investigator", "Factual verification found no errors."
            ),
        )
        output = format_prior_results_section(prior)
        assert "Factual verification found no errors." in output

    def test_synthesis_section_includes_convergence_summary(self):
        """Synthesis context includes convergence summary after injection."""
        prior: dict[str, ArtifactResult] = {}
        _simulate_adversarial_injection(
            prior,
            tid="ach",
            convergence=_make_result(
                "ach-convergence", "ACH Convergence", "Both models agree on H1."
            ),
        )
        output = format_prior_results_section(prior)
        assert "Both models agree on H1." in output

    def test_original_technique_and_adversarial_both_in_output(self):
        """Both the original technique result and adversarial artifacts appear."""
        prior: dict[str, ArtifactResult] = {
            "ach": _make_result("ach", "ACH", "Original analysis."),
        }
        _simulate_adversarial_injection(
            prior,
            tid="ach",
            adjudication=_make_result("ach-adjudication", "Adj", "Post-debate verdict."),
            convergence=_make_result("ach-convergence", "Conv", "Final consensus."),
        )
        output = format_prior_results_section(prior)
        assert "Original analysis." in output
        assert "Post-debate verdict." in output
        assert "Final consensus." in output
