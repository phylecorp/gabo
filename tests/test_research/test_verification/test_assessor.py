"""Tests for LLM-based claim assessment.

Mocks the LLM provider to test batching logic, verdict merging, and
UNVERIFIABLE fallback without making real API calls.

# @mock-exempt: create_provider is an external LLM API boundary; mocking it
# avoids real API calls while testing the assessor's batching and verdict logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from sat.models.verification import ClaimVerification
from sat.research.verification.assessor import (
    _SourceAssessment,
    _AssessmentItem,
    assess_claims,
)


def _make_claim(text: str, source_ids: list[str], confidence: str = "Medium"):
    claim = MagicMock()
    claim.claim = text
    claim.source_ids = source_ids
    claim.confidence = confidence
    return claim


class TestAssessClaims:
    async def test_returns_empty_for_no_claims(self):
        results = await assess_claims(
            claims=[],
            source_contents={"S1": "Some content"},
            provider_name="anthropic",
        )
        assert results == []

    async def test_returns_unverifiable_when_no_content(self):
        """Claims whose sources have no fetched content get UNVERIFIABLE."""
        claim = _make_claim("GDP grew 3%", ["S1"], "High")
        results = await assess_claims(
            claims=[claim],
            source_contents={},  # S1 content not available
            provider_name="anthropic",
        )
        assert len(results) == 1
        assert results[0].verdict == "UNVERIFIABLE"
        assert results[0].original_confidence == "High"
        assert results[0].adjusted_confidence == "High"  # runner adjusts, not assessor

    async def test_returns_claim_verifications(self):
        """Happy path: one LLM call per source returns ClaimVerification objects."""
        claim = _make_claim("Inflation was 4% in 2023", ["S1"], "High")
        source_contents = {"S1": "The annual inflation rate for 2023 was 4.1% according to..."}

        mock_assessment = _SourceAssessment(
            assessments=[
                _AssessmentItem(
                    claim="Inflation was 4% in 2023",
                    verdict="SUPPORTED",
                    confidence="High",
                    reasoning="Source directly states 4.1% inflation in 2023.",
                )
            ]
        )

        with patch("sat.research.verification.assessor.create_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.generate_structured = AsyncMock(return_value=mock_assessment)
            mock_create.return_value = mock_provider

            results = await assess_claims(
                claims=[claim],
                source_contents=source_contents,
                provider_name="anthropic",
            )

        assert len(results) == 1
        v = results[0]
        assert isinstance(v, ClaimVerification)
        assert v.verdict == "SUPPORTED"
        assert v.claim == "Inflation was 4% in 2023"
        assert v.original_confidence == "High"

    async def test_batches_claims_per_source(self):
        """Verify exactly one LLM call per source with content, not per claim."""
        claims = [
            _make_claim("Claim A", ["S1"], "High"),
            _make_claim("Claim B", ["S1"], "Medium"),
            _make_claim("Claim C", ["S2"], "Low"),
        ]
        source_contents = {
            "S1": "Content for source 1...",
            "S2": "Content for source 2...",
        }

        call_count = 0

        async def mock_generate_structured(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Return appropriate assessments based on which source is being assessed
            messages = args[1] if len(args) > 1 else kwargs.get("messages", [])
            msg_content = messages[0].content if messages else ""
            if "S1" in msg_content:
                items = [
                    _AssessmentItem(claim="Claim A", verdict="SUPPORTED", confidence="High", reasoning="Found."),
                    _AssessmentItem(claim="Claim B", verdict="PARTIALLY_SUPPORTED", confidence="Medium", reasoning="Partial."),
                ]
            else:
                items = [
                    _AssessmentItem(claim="Claim C", verdict="NOT_SUPPORTED", confidence="Low", reasoning="Not found."),
                ]
            return _SourceAssessment(assessments=items)

        with patch("sat.research.verification.assessor.create_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.generate_structured = mock_generate_structured
            mock_create.return_value = mock_provider

            results = await assess_claims(
                claims=claims,
                source_contents=source_contents,
                provider_name="anthropic",
            )

        # Should have made exactly 2 LLM calls (one per source with content)
        assert call_count == 2
        assert len(results) == 3

    async def test_handles_provider_creation_failure(self):
        """If provider creation fails, all claims get UNVERIFIABLE."""
        claims = [_make_claim("Claim A", ["S1"], "High")]
        source_contents = {"S1": "Some content"}

        with patch(
            "sat.research.verification.assessor.create_provider",
            side_effect=ValueError("No API key"),
        ):
            results = await assess_claims(
                claims=claims,
                source_contents=source_contents,
                provider_name="anthropic",
            )

        assert len(results) == 1
        assert results[0].verdict == "UNVERIFIABLE"

    async def test_verdict_priority_chooses_most_informative(self):
        """When a claim cites multiple sources, pick the highest-priority verdict."""
        claim = _make_claim("Important claim", ["S1", "S2"], "Medium")
        source_contents = {
            "S1": "Content from source 1",
            "S2": "Content from source 2",
        }

        call_results = {
            "S1": _SourceAssessment(assessments=[
                _AssessmentItem(
                    claim="Important claim",
                    verdict="INCONCLUSIVE",
                    confidence="Low",
                    reasoning="Could not determine.",
                )
            ]),
            "S2": _SourceAssessment(assessments=[
                _AssessmentItem(
                    claim="Important claim",
                    verdict="SUPPORTED",
                    confidence="High",
                    reasoning="Clearly stated.",
                )
            ]),
        }
        call_idx = 0

        async def mock_generate(system_prompt, messages, output_schema, **kwargs):
            nonlocal call_idx
            call_idx += 1
            # Check which source is in the message
            msg = messages[0].content if messages else ""
            for k, v in call_results.items():
                if k in msg:
                    return v
            return call_results["S1"]

        with patch("sat.research.verification.assessor.create_provider") as mock_create:
            mock_provider = AsyncMock()
            mock_provider.generate_structured = mock_generate
            mock_create.return_value = mock_provider

            results = await assess_claims(
                claims=[claim],
                source_contents=source_contents,
                provider_name="anthropic",
            )

        # SUPPORTED (priority 6) should beat INCONCLUSIVE (priority 2)
        assert results[0].verdict == "SUPPORTED"
