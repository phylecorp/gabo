"""Tests for adversarial prompt builders.

@decision DEC-TEST-ADV-005: Prompt builder output verification.
@title Verify critique, rebuttal, and adjudication prompt structure
@status accepted
@rationale Prompt builders produce the system prompts and user messages that
drive the adversarial debate. Testing ensures correct template substitution,
evidence inclusion, and message structure.
"""

from __future__ import annotations

from sat.models.adversarial import (
    Challenge,
    CritiqueResult,
    RebuttalResult,
)
from sat.models.base import ArtifactResult
from sat.prompts.adversarial import (
    build_adjudication_prompt,
    build_critique_prompt,
    build_rebuttal_prompt,
)


def _make_technique_result() -> ArtifactResult:
    return ArtifactResult(
        technique_id="ach",
        technique_name="Analysis of Competing Hypotheses",
        summary="H1 is most likely.",
    )


def _make_critique() -> CritiqueResult:
    return CritiqueResult(
        technique_id="ach-critique",
        technique_name="Critique of ACH",
        summary="Moderate issues found.",
        agreements=["Good hypothesis set"],
        challenges=[
            Challenge(
                claim="E3 supports H1",
                challenge="E3 is ambiguous",
                evidence="Missing assessment",
                severity="Medium",
            )
        ],
        alternative_interpretations=["H1/H2 overlap"],
        evidence_gaps=["No OSINT"],
        severity="Moderate",
        overall_assessment="Needs work",
        revised_confidence="Lower",
    )


def _make_rebuttal() -> RebuttalResult:
    return RebuttalResult(
        technique_id="ach-rebuttal",
        technique_name="Rebuttal for ACH",
        summary="Partially conceded.",
        accepted_challenges=["E3 ambiguity"],
        rejected_challenges=[],
        revised_conclusions="H1 likely with caveats",
    )


def test_critique_prompt_structure():
    system, msgs = build_critique_prompt(
        technique_result=_make_technique_result(),
        question="Will AI surpass humans?",
        evidence="Expert forecasts available.",
    )
    assert "ach-critique" in system
    assert "Analysis of Competing Hypotheses" in system
    assert len(msgs) == 1
    assert msgs[0].role == "user"
    assert "Will AI surpass humans?" in msgs[0].content
    assert "Expert forecasts available." in msgs[0].content


def test_critique_prompt_without_evidence():
    system, msgs = build_critique_prompt(
        technique_result=_make_technique_result(),
        question="Test question",
    )
    assert "Evidence" not in msgs[0].content
    assert "Test question" in msgs[0].content


def test_rebuttal_prompt_includes_critique():
    system, msgs = build_rebuttal_prompt(
        technique_result=_make_technique_result(),
        critique=_make_critique(),
        question="Test question",
    )
    assert "ach-rebuttal" in system
    assert "Critique Received" in msgs[0].content
    assert "Your Original Analysis" in msgs[0].content


def test_adjudication_prompt_includes_all():
    system, msgs = build_adjudication_prompt(
        technique_result=_make_technique_result(),
        critique=_make_critique(),
        rebuttal=_make_rebuttal(),
        question="Test question",
        evidence="Some evidence.",
    )
    assert "ach-adjudication" in system
    assert "Primary Analysis" in msgs[0].content
    assert "Critique" in msgs[0].content
    assert "Rebuttal" in msgs[0].content
    assert "Some evidence." in msgs[0].content


# ---------------------------------------------------------------------------
# _format_for_critique tests
# ---------------------------------------------------------------------------


def _make_ach_technique_result():
    from sat.models.ach import ACHEvidence, ACHHypothesis, ACHRating, ACHResult

    return ACHResult(
        technique_id="ach",
        technique_name="Analysis of Competing Hypotheses",
        summary="H2 is most consistent.",
        hypotheses=[
            ACHHypothesis(id="H1", description="State-sponsored APT"),
            ACHHypothesis(id="H2", description="Criminal syndicate"),
        ],
        evidence=[
            ACHEvidence(
                id="E1",
                description="C2 infrastructure",
                credibility="High",
                relevance="High",
            ),
        ],
        matrix=[
            ACHRating(evidence_id="E1", hypothesis_id="H1", rating="C", explanation="Fits APT"),
            ACHRating(
                evidence_id="E1", hypothesis_id="H2", rating="I", explanation="Rare for criminals"
            ),
        ],
        most_likely="H2",
    )


def test_format_for_critique_returns_markdown_tables_for_ach():
    """_format_for_critique should return markdown tables for ACHResult, not JSON."""
    from sat.prompts.adversarial import _format_for_critique

    result = _make_ach_technique_result()
    formatted = _format_for_critique(result)

    # Should contain markdown table structure, not raw JSON
    assert "| ID | Hypothesis |" in formatted
    assert "H1" in formatted
    assert "H2" in formatted
    # Should NOT be wrapped in a json code block
    assert "```json" not in formatted


def test_format_for_critique_returns_json_for_non_ach():
    """_format_for_critique should return JSON for non-ACH ArtifactResult types."""
    from sat.prompts.adversarial import _format_for_critique

    result = ArtifactResult(
        technique_id="assumptions",
        technique_name="Key Assumptions Check",
        summary="Three assumptions identified.",
    )
    formatted = _format_for_critique(result)

    # Should be JSON output
    assert '"technique_id"' in formatted
    assert "assumptions" in formatted


def test_critique_prompt_uses_markdown_for_ach():
    """build_critique_prompt should embed markdown tables (not JSON) for ACHResult."""
    result = _make_ach_technique_result()
    _system, msgs = build_critique_prompt(
        technique_result=result,
        question="Who is responsible?",
        evidence="Network logs available.",
    )
    content = msgs[0].content
    # Markdown tables should appear in the user message
    assert "| ID | Hypothesis |" in content
    assert "```json" not in content


def test_critique_system_prompt_has_ach_guidance():
    """build_critique_prompt should add ACH-specific guidance to system prompt when technique is ACH."""
    result = _make_ach_technique_result()
    system, _msgs = build_critique_prompt(
        technique_result=result,
        question="Who is responsible?",
    )
    # ACH-specific guidance lines should appear
    assert (
        "matrix cells" in system.lower()
        or "e.g., 'E3 is rated" in system
        or "matrix cell" in system
    )
    assert "exhaustive" in system.lower()
    assert "credibility" in system.lower()


def test_critique_system_prompt_no_ach_guidance_for_non_ach():
    """build_critique_prompt should NOT add ACH-specific guidance for non-ACH techniques."""
    result = ArtifactResult(
        technique_id="assumptions",
        technique_name="Key Assumptions Check",
        summary="Three assumptions.",
    )
    system, _msgs = build_critique_prompt(
        technique_result=result,
        question="Test?",
    )
    # The ACH-specific cell-reference instruction should not appear for non-ACH
    assert "E3 is rated" not in system


def test_rebuttal_prompt_uses_markdown_for_ach():
    """build_rebuttal_prompt should embed markdown tables for ACHResult primary analysis."""
    result = _make_ach_technique_result()
    _system, msgs = build_rebuttal_prompt(
        technique_result=result,
        critique=_make_critique(),
        question="Who is responsible?",
    )
    content = msgs[0].content
    assert "| ID | Hypothesis |" in content
    # Critique is not an ACHResult so it should still be JSON
    assert '"technique_id"' in content


def test_adjudication_prompt_uses_markdown_for_ach():
    """build_adjudication_prompt should embed markdown tables for ACHResult primary analysis."""
    result = _make_ach_technique_result()
    _system, msgs = build_adjudication_prompt(
        technique_result=result,
        critique=_make_critique(),
        rebuttal=_make_rebuttal(),
        question="Who is responsible?",
    )
    content = msgs[0].content
    assert "| ID | Hypothesis |" in content
