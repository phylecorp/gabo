"""Tests for adversarial analysis data models.

@decision DEC-TEST-ADV-001: Adversarial model serialization and validation tests.
@title Verify Challenge, CritiqueResult, RebuttalResult, AdjudicationResult round-trip
@status accepted
@rationale These models are the contract between adversarial session orchestration
and artifact writing. Verifying serialization ensures the pipeline can persist
and reload adversarial results correctly.
"""

from __future__ import annotations

from sat.models.adversarial import (
    AdjudicationResult,
    AdversarialExchange,
    Challenge,
    CritiqueResult,
    DebateRound,
    RebuttalPoint,
    RebuttalResult,
)
from sat.models.base import ArtifactResult


def _make_critique() -> CritiqueResult:
    return CritiqueResult(
        technique_id="ach-critique",
        technique_name="Critique of ACH",
        summary="The ACH analysis has moderate weaknesses.",
        agreements=["Hypothesis set is comprehensive"],
        challenges=[
            Challenge(
                claim="Evidence E3 strongly supports H1",
                challenge="E3 is also consistent with H2",
                evidence="Source reliability assessment missing",
                severity="Medium",
            )
        ],
        alternative_interpretations=["H1 and H2 may not be mutually exclusive"],
        evidence_gaps=["No open-source intelligence was consulted"],
        severity="Moderate",
        overall_assessment="Analysis is reasonable but evidence weighting needs revision",
        revised_confidence="Lower",
    )


def _make_rebuttal() -> RebuttalResult:
    return RebuttalResult(
        technique_id="ach-rebuttal",
        technique_name="Rebuttal for ACH",
        summary="Most challenges are addressed; one conceded.",
        accepted_challenges=["E3 ambiguity is valid"],
        rejected_challenges=[
            RebuttalPoint(
                challenge="Source reliability assessment missing",
                response="Source reliability was addressed in the assumptions section",
                conceded=False,
            )
        ],
        revised_conclusions="H1 remains most likely but with reduced confidence",
    )


def _make_adjudication() -> AdjudicationResult:
    return AdjudicationResult(
        technique_id="ach-adjudication",
        technique_name="Adjudication for ACH",
        summary="Primary's analysis holds with caveats.",
        resolved_for_primary=["Source reliability was addressed"],
        resolved_for_challenger=["E3 ambiguity weakens H1 support"],
        unresolved=["Whether H1 and H2 are truly mutually exclusive"],
        synthesis_assessment="H1 is most likely but H2 cannot be dismissed",
    )


def test_critique_result_serialization():
    critique = _make_critique()
    data = critique.model_dump()
    restored = CritiqueResult(**data)
    assert restored.severity == "Moderate"
    assert len(restored.challenges) == 1
    assert restored.challenges[0].severity == "Medium"


def test_rebuttal_result_serialization():
    rebuttal = _make_rebuttal()
    data = rebuttal.model_dump()
    restored = RebuttalResult(**data)
    assert len(restored.accepted_challenges) == 1
    assert not restored.rejected_challenges[0].conceded


def test_adjudication_result_serialization():
    adj = _make_adjudication()
    data = adj.model_dump()
    restored = AdjudicationResult(**data)
    assert len(restored.resolved_for_challenger) == 1
    assert len(restored.unresolved) == 1


def test_debate_round_structure():
    critique = _make_critique()
    rebuttal = _make_rebuttal()
    rnd = DebateRound(round_number=1, critique=critique, rebuttal=rebuttal)
    assert rnd.round_number == 1
    assert rnd.critique.severity == "Moderate"
    assert rnd.rebuttal is not None
    assert rnd.rebuttal.revised_conclusions.startswith("H1")


def test_debate_round_without_rebuttal():
    critique = _make_critique()
    rnd = DebateRound(round_number=1, critique=critique)
    assert rnd.rebuttal is None


def test_adversarial_exchange_full():
    critique = _make_critique()
    rebuttal = _make_rebuttal()
    adj = _make_adjudication()
    initial = ArtifactResult(technique_id="ach", technique_name="ACH", summary="Initial result")
    exchange = AdversarialExchange(
        technique_id="ach",
        initial_result=initial,
        rounds=[DebateRound(round_number=1, critique=critique, rebuttal=rebuttal)],
        adjudication=adj,
    )
    data = exchange.model_dump()
    assert data["technique_id"] == "ach"
    assert len(data["rounds"]) == 1
    assert data["adjudication"]["synthesis_assessment"].startswith("H1")


def test_adversarial_exchange_json_roundtrip():
    critique = _make_critique()
    initial = ArtifactResult(technique_id="ach", technique_name="ACH", summary="Initial")
    exchange = AdversarialExchange(
        technique_id="ach",
        initial_result=initial,
        rounds=[DebateRound(round_number=1, critique=critique)],
        adjudication=None,
    )
    json_str = exchange.model_dump_json()
    restored = AdversarialExchange.model_validate_json(json_str)
    assert restored.technique_id == "ach"
    assert restored.adjudication is None
    assert len(restored.rounds) == 1
