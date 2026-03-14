"""Tests for the verification runner pipeline.

Mocks fetcher and assessor to test orchestration logic: confidence adjustment,
summary generation, and graceful handling of edge cases.

# @mock-exempt: fetch_sources and assess_claims are mocked to isolate the
# runner's orchestration logic. Each is tested separately in test_fetcher.py
# and test_assessor.py. This follows the unit testing principle of testing
# one layer at a time.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.models.verification import ClaimVerification, FetchResult, VerificationResult
from sat.research.verification.runner import _adjust_confidence, verify_sources


def _make_research_result(
    sources: list | None = None,
    claims: list | None = None,
) -> ResearchResult:
    """Construct a minimal ResearchResult for testing."""
    return ResearchResult(
        technique_id="research",
        technique_name="Research",
        summary="Test research",
        query="test question",
        sources=sources or [],
        claims=claims or [],
        formatted_evidence="Test evidence.",
        research_provider="llm",
        gaps_identified=[],
    )


def _make_source(id: str, url: str | None = "https://example.com") -> ResearchSource:
    return ResearchSource(
        id=id,
        title=f"Source {id}",
        url=url,
        source_type="web",
        reliability_assessment="Medium",
    )


def _make_claim(text: str, source_ids: list[str], confidence: str = "Medium") -> ResearchClaim:
    return ResearchClaim(
        claim=text,
        source_ids=source_ids,
        confidence=confidence,
        category="fact",
    )


def _make_config(enabled: bool = True, max_sources: int = 20):
    cfg = MagicMock()
    cfg.enabled = enabled
    cfg.max_sources = max_sources
    cfg.timeout = 5.0
    cfg.concurrency = 5
    cfg.model = None
    return cfg


class TestAdjustConfidence:
    def test_upgrade_low_to_medium(self):
        assert _adjust_confidence("Low", +1) == "Medium"

    def test_upgrade_medium_to_high(self):
        assert _adjust_confidence("Medium", +1) == "High"

    def test_upgrade_high_stays_high(self):
        assert _adjust_confidence("High", +1) == "High"

    def test_downgrade_high_to_medium(self):
        assert _adjust_confidence("High", -1) == "Medium"

    def test_downgrade_medium_to_low(self):
        assert _adjust_confidence("Medium", -1) == "Low"

    def test_downgrade_low_stays_low(self):
        assert _adjust_confidence("Low", -1) == "Low"

    def test_no_change(self):
        assert _adjust_confidence("Medium", 0) == "Medium"


class TestVerifySources:
    async def test_full_verification_pipeline(self):
        sources = [_make_source("S1")]
        claims = [_make_claim("GDP grew 3%", ["S1"], "Medium")]
        research_result = _make_research_result(sources=sources, claims=claims)
        config = _make_config()

        mock_fetch_results = {
            "S1": (
                FetchResult(source_id="S1", url="https://example.com", status="success", content_length=500),
                "GDP grew by approximately 3% last year...",
            )
        }
        mock_verifications = [
            ClaimVerification(
                claim="GDP grew 3%",
                source_ids=["S1"],
                verdict="SUPPORTED",
                confidence="High",
                reasoning="Directly stated in source.",
                original_confidence="Medium",
                adjusted_confidence="Medium",  # runner will adjust this
            )
        ]

        with (
            patch("sat.research.verification.runner.fetch_sources", AsyncMock(return_value=mock_fetch_results)),
            patch("sat.research.verification.runner.assess_claims", AsyncMock(return_value=mock_verifications)),
        ):
            result = await verify_sources(research_result, "anthropic", config)

        assert isinstance(result, VerificationResult)
        assert result.technique_id == "verification"
        assert result.sources_fetched == 1
        assert result.sources_failed == 0
        assert len(result.claim_verifications) == 1

    async def test_confidence_upgrade_on_supported(self):
        """SUPPORTED verdict upgrades claim confidence by one level."""
        sources = [_make_source("S1")]
        claims = [_make_claim("Claim A", ["S1"], "Low")]
        research_result = _make_research_result(sources=sources, claims=claims)
        config = _make_config()

        mock_fetch = {
            "S1": (
                FetchResult(source_id="S1", url="https://example.com", status="success", content_length=100),
                "Supporting content",
            )
        }
        mock_verifications = [
            ClaimVerification(
                claim="Claim A",
                source_ids=["S1"],
                verdict="SUPPORTED",
                confidence="High",
                reasoning="Found.",
                original_confidence="Low",
                adjusted_confidence="Low",
            )
        ]

        with (
            patch("sat.research.verification.runner.fetch_sources", AsyncMock(return_value=mock_fetch)),
            patch("sat.research.verification.runner.assess_claims", AsyncMock(return_value=mock_verifications)),
        ):
            result = await verify_sources(research_result, "anthropic", config)

        # Low + SUPPORTED (+1) = Medium
        assert result.claim_verifications[0].adjusted_confidence == "Medium"

    async def test_confidence_downgrade_on_not_supported(self):
        """NOT_SUPPORTED verdict downgrades confidence by one level."""
        sources = [_make_source("S1")]
        claims = [_make_claim("Claim A", ["S1"], "High")]
        research_result = _make_research_result(sources=sources, claims=claims)
        config = _make_config()

        mock_fetch = {
            "S1": (
                FetchResult(source_id="S1", url="https://example.com", status="success", content_length=100),
                "Some content",
            )
        }
        mock_verifications = [
            ClaimVerification(
                claim="Claim A",
                source_ids=["S1"],
                verdict="NOT_SUPPORTED",
                confidence="High",
                reasoning="Not found in source.",
                original_confidence="High",
                adjusted_confidence="High",
            )
        ]

        with (
            patch("sat.research.verification.runner.fetch_sources", AsyncMock(return_value=mock_fetch)),
            patch("sat.research.verification.runner.assess_claims", AsyncMock(return_value=mock_verifications)),
        ):
            result = await verify_sources(research_result, "anthropic", config)

        # High + NOT_SUPPORTED (-1) = Medium
        assert result.claim_verifications[0].adjusted_confidence == "Medium"

    async def test_no_change_on_unverifiable(self):
        """UNVERIFIABLE verdict leaves confidence unchanged."""
        sources = [_make_source("S1", url=None)]
        claims = [_make_claim("Claim A", ["S1"], "Medium")]
        research_result = _make_research_result(sources=sources, claims=claims)
        config = _make_config()

        mock_verifications = [
            ClaimVerification(
                claim="Claim A",
                source_ids=["S1"],
                verdict="UNVERIFIABLE",
                confidence="Low",
                reasoning="No content.",
                original_confidence="Medium",
                adjusted_confidence="Medium",
            )
        ]

        with (
            patch("sat.research.verification.runner.fetch_sources", AsyncMock(return_value={})),
            patch("sat.research.verification.runner.assess_claims", AsyncMock(return_value=mock_verifications)),
        ):
            result = await verify_sources(research_result, "anthropic", config)

        # Medium + UNVERIFIABLE (0) = Medium
        assert result.claim_verifications[0].adjusted_confidence == "Medium"

    async def test_handles_no_urls(self):
        """Research result with no URLs still produces a valid VerificationResult."""
        sources = [_make_source("S1", url=None), _make_source("S2", url=None)]
        claims = [_make_claim("Claim A", ["S1"], "High")]
        research_result = _make_research_result(sources=sources, claims=claims)
        config = _make_config()

        mock_verifications = [
            ClaimVerification(
                claim="Claim A",
                source_ids=["S1"],
                verdict="UNVERIFIABLE",
                confidence="Low",
                reasoning="No URLs.",
                original_confidence="High",
                adjusted_confidence="High",
            )
        ]

        with (
            patch("sat.research.verification.runner.fetch_sources", AsyncMock(return_value={})),
            patch("sat.research.verification.runner.assess_claims", AsyncMock(return_value=mock_verifications)),
        ):
            result = await verify_sources(research_result, "anthropic", config)

        assert result.sources_fetched == 0
        assert isinstance(result.verification_summary, str)
        assert len(result.verification_summary) > 0

    async def test_verification_summary_generated(self):
        """Summary string includes claim counts and source counts."""
        sources = [_make_source("S1")]
        claims = [
            _make_claim("Claim A", ["S1"], "Medium"),
            _make_claim("Claim B", ["S1"], "Low"),
        ]
        research_result = _make_research_result(sources=sources, claims=claims)
        config = _make_config()

        mock_fetch = {
            "S1": (
                FetchResult(source_id="S1", url="https://example.com", status="success", content_length=200),
                "Content",
            )
        }
        mock_verifications = [
            ClaimVerification(
                claim="Claim A",
                source_ids=["S1"],
                verdict="SUPPORTED",
                confidence="High",
                reasoning="Found.",
                original_confidence="Medium",
                adjusted_confidence="Medium",
            ),
            ClaimVerification(
                claim="Claim B",
                source_ids=["S1"],
                verdict="NOT_SUPPORTED",
                confidence="Medium",
                reasoning="Not found.",
                original_confidence="Low",
                adjusted_confidence="Low",
            ),
        ]

        with (
            patch("sat.research.verification.runner.fetch_sources", AsyncMock(return_value=mock_fetch)),
            patch("sat.research.verification.runner.assess_claims", AsyncMock(return_value=mock_verifications)),
        ):
            result = await verify_sources(research_result, "anthropic", config)

        summary = result.verification_summary
        assert "2" in summary  # 2 claims
        assert "1" in summary  # 1 source fetched
        # Should mention both verdicts
        assert "supported" in summary.lower() or "not supported" in summary.lower()
