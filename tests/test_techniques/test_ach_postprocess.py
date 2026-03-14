"""Test ACH post-processing (inconsistency score computation).

@decision DEC-TEST-ACH-001: Deterministic post-processing validation.
Tests the weighted inconsistency scoring: High credibility = 1.0 weight,
Medium = 0.5, Low = 0.25. Only "I" ratings increase scores. Verifies that
Consistent and Neutral ratings don't affect scores.
"""

from __future__ import annotations

from sat.models.ach import ACHEvidence, ACHHypothesis, ACHRating, ACHResult
from sat.techniques.diagnostic.ach import ACHTechnique


class TestACHPostProcess:
    """ACH post_process should compute weighted inconsistency scores."""

    def _make_result(self, ratings: list[tuple[str, str, str]], credibilities: dict[str, str]) -> ACHResult:
        """Build an ACHResult for testing."""
        hypotheses = sorted({r[1] for r in ratings})
        evidence_ids = sorted({r[0] for r in ratings})

        return ACHResult(
            technique_id="ach",
            technique_name="ACH",
            summary="Test",
            hypotheses=[ACHHypothesis(id=hid, description=f"Hypothesis {hid}") for hid in hypotheses],
            evidence=[
                ACHEvidence(id=eid, description=f"Evidence {eid}", credibility=credibilities.get(eid, "Medium"), relevance="High")
                for eid in evidence_ids
            ],
            matrix=[
                ACHRating(evidence_id=r[0], hypothesis_id=r[1], rating=r[2], explanation="test")
                for r in ratings
            ],
            most_likely=hypotheses[0],
            rejected=[],
            diagnosticity_notes="test",
            missing_evidence=[],
        )

    def test_basic_scoring(self):
        """Inconsistent ratings should increase the score."""
        result = self._make_result(
            ratings=[
                ("E1", "H1", "C"),
                ("E1", "H2", "I"),
                ("E2", "H1", "I"),
                ("E2", "H2", "C"),
            ],
            credibilities={"E1": "High", "E2": "High"},
        )
        technique = ACHTechnique()
        processed = technique.post_process(result)
        assert isinstance(processed, ACHResult)
        assert processed.inconsistency_scores["H1"] == 1.0
        assert processed.inconsistency_scores["H2"] == 1.0

    def test_credibility_weighting(self):
        """Higher credibility evidence should have more impact."""
        result = self._make_result(
            ratings=[
                ("E1", "H1", "I"),
                ("E2", "H1", "I"),
            ],
            credibilities={"E1": "High", "E2": "Low"},
        )
        technique = ACHTechnique()
        processed = technique.post_process(result)
        assert processed.inconsistency_scores["H1"] == 1.25

    def test_neutral_and_consistent_dont_count(self):
        """Only I ratings should increase scores."""
        result = self._make_result(
            ratings=[
                ("E1", "H1", "C"),
                ("E2", "H1", "N"),
            ],
            credibilities={"E1": "High", "E2": "High"},
        )
        technique = ACHTechnique()
        processed = technique.post_process(result)
        assert processed.inconsistency_scores["H1"] == 0.0
