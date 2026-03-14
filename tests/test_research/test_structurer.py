"""Tests for evidence structurer: URL backfill, structure_evidence, and coverage validation.

@decision DEC-TEST-RESEARCH-005: In-memory doubles for structurer URL backfill tests.
@title Structurer backfill, integration, and coverage validation tests
@status accepted
@rationale Tests verify that _backfill_urls correctly matches sources to citations
by title (exact and substring, case-insensitive), skips already-populated URLs,
handles empty citation lists gracefully, and that structure_evidence wires backfill
correctly. Uses in-memory test doubles — no unittest.mock.

Also covers _validate_extraction_coverage: low claim density, low source coverage,
and zero gaps on complex queries each trigger logger.warning. Normal extractions
produce no warnings.
"""
# @mock-exempt: Uses in-memory test doubles implementing provider protocols,
# not unittest.mock. These are equivalent to the conftest MockProvider pattern.

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.providers.base import LLMMessage
from sat.research.base import ResearchResponse, SearchResult
from sat.research.structurer import (
    _backfill_urls,
    _validate_extraction_coverage,
    structure_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(sources: list[ResearchSource]) -> ResearchResult:
    """Build a minimal ResearchResult with the given sources."""
    return ResearchResult(
        technique_id="research",
        technique_name="Deep Research",
        summary="Test summary",
        query="test query",
        sources=sources,
        claims=[],
        formatted_evidence="test evidence",
        research_provider="mock",
        gaps_identified=[],
    )


def _make_source(id: str, title: str, url: str | None = None) -> ResearchSource:
    return ResearchSource(
        id=id,
        title=title,
        url=url,
        source_type="web",
        reliability_assessment="Medium",
        retrieved_at=datetime.now(timezone.utc),
    )


def _make_citation(title: str, url: str) -> SearchResult:
    return SearchResult(title=title, url=url, snippet="snippet")


# ---------------------------------------------------------------------------
# Unit tests: _backfill_urls
# ---------------------------------------------------------------------------


class TestBackfillUrls:
    """Unit tests for _backfill_urls()."""

    def test_exact_title_match_backfills_url(self):
        source = _make_source("S1", "OpenAI Research Paper", url=None)
        citation = _make_citation("OpenAI Research Paper", "https://openai.com/paper")
        result = _make_result([source])

        updated = _backfill_urls(result, [citation])

        assert updated.sources[0].url == "https://openai.com/paper"

    def test_case_insensitive_exact_match(self):
        source = _make_source("S1", "openai research paper", url=None)
        citation = _make_citation("OpenAI Research Paper", "https://openai.com/paper")
        result = _make_result([source])

        updated = _backfill_urls(result, [citation])

        assert updated.sources[0].url == "https://openai.com/paper"

    def test_substring_match_source_in_citation(self):
        # Source title is a substring of citation title
        source = _make_source("S1", "AI Safety", url=None)
        citation = _make_citation("AI Safety: A Comprehensive Review", "https://example.com/safety")
        result = _make_result([source])

        updated = _backfill_urls(result, [citation])

        assert updated.sources[0].url == "https://example.com/safety"

    def test_substring_match_citation_in_source(self):
        # Citation title is a substring of source title
        source = _make_source("S1", "AI Safety: A Comprehensive Review 2024", url=None)
        citation = _make_citation("AI Safety", "https://example.com/safety")
        result = _make_result([source])

        updated = _backfill_urls(result, [citation])

        assert updated.sources[0].url == "https://example.com/safety"

    def test_skips_sources_that_already_have_urls(self):
        source = _make_source("S1", "OpenAI Research Paper", url="https://existing.com")
        citation = _make_citation("OpenAI Research Paper", "https://openai.com/paper")
        result = _make_result([source])

        updated = _backfill_urls(result, [citation])

        # Must not overwrite the existing URL
        assert updated.sources[0].url == "https://existing.com"

    def test_empty_citations_returns_unchanged_result(self):
        source = _make_source("S1", "Some Source", url=None)
        result = _make_result([source])

        updated = _backfill_urls(result, [])

        assert updated.sources[0].url is None

    def test_no_match_leaves_url_none(self):
        source = _make_source("S1", "Totally Different Title", url=None)
        citation = _make_citation("Something Else Entirely", "https://example.com")
        result = _make_result([source])

        updated = _backfill_urls(result, [citation])

        assert updated.sources[0].url is None

    def test_multiple_sources_matched_independently(self):
        sources = [
            _make_source("S1", "Source Alpha", url=None),
            _make_source("S2", "Source Beta", url=None),
            _make_source("S3", "Source Gamma", url="https://already.com"),
        ]
        citations = [
            _make_citation("Source Alpha", "https://alpha.com"),
            _make_citation("Source Beta Extended Title", "https://beta.com"),
            _make_citation("Source Gamma", "https://gamma.com"),
        ]
        result = _make_result(sources)

        updated = _backfill_urls(result, citations)

        assert updated.sources[0].url == "https://alpha.com"
        assert updated.sources[1].url == "https://beta.com"
        # S3 already had a URL — must not be overwritten
        assert updated.sources[2].url == "https://already.com"

    def test_returns_new_result_object(self):
        """_backfill_urls must return a model_copy, not mutate in place."""
        source = _make_source("S1", "Source Alpha", url=None)
        citation = _make_citation("Source Alpha", "https://alpha.com")
        result = _make_result([source])

        updated = _backfill_urls(result, [citation])

        # updated is a new object
        assert updated is not result
        # Original sources list is not mutated
        assert result.sources[0].url is None

    def test_exact_match_preferred_over_substring(self):
        """When one citation exactly matches, prefer it over a different substring match."""
        source = _make_source("S1", "AI Safety", url=None)
        citations = [
            _make_citation("AI Safety: Extended Report", "https://extended.com"),
            _make_citation("AI Safety", "https://exact.com"),
        ]
        result = _make_result([source])

        updated = _backfill_urls(result, citations)

        assert updated.sources[0].url == "https://exact.com"


# ---------------------------------------------------------------------------
# Integration test: structure_evidence wires backfill
# ---------------------------------------------------------------------------


class MockLLMForStructurer:
    """In-memory test double: returns ResearchResult with url=None on sources."""

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ResearchResult:
        return ResearchResult(
            technique_id="research",
            technique_name="Deep Research",
            summary="AI research summary",
            query="AI capabilities",
            sources=[
                ResearchSource(
                    id="S1",
                    title="OpenAI Blog Post",
                    url=None,  # Simulates LLM dropping URL
                    source_type="web",
                    reliability_assessment="Medium",
                ),
                ResearchSource(
                    id="S2",
                    title="DeepMind Paper",
                    url=None,  # Simulates LLM dropping URL
                    source_type="academic",
                    reliability_assessment="High",
                ),
            ],
            claims=[
                ResearchClaim(
                    claim="AI is advancing rapidly",
                    source_ids=["S1"],
                    confidence="High",
                    category="fact",
                ),
            ],
            formatted_evidence="AI capabilities are growing rapidly.",
            research_provider="mock",
            gaps_identified=[],
        )


class TestStructureEvidence:
    """Integration test: structure_evidence backfills URLs from citations."""

    async def test_backfill_applied_when_citations_present(self):
        raw = ResearchResponse(
            content="AI research content...",
            citations=[
                SearchResult(
                    title="OpenAI Blog Post",
                    url="https://openai.com/blog",
                    snippet="OpenAI publishes...",
                ),
                SearchResult(
                    title="DeepMind Paper",
                    url="https://deepmind.com/paper",
                    snippet="DeepMind research...",
                ),
            ],
        )
        llm = MockLLMForStructurer()

        result = await structure_evidence(
            raw=raw,
            query="AI capabilities",
            provider=llm,
            research_provider_name="test_provider",
        )

        # URLs should be backfilled from citations
        url_map = {s.title: s.url for s in result.sources}
        assert url_map["OpenAI Blog Post"] == "https://openai.com/blog"
        assert url_map["DeepMind Paper"] == "https://deepmind.com/paper"

    async def test_no_backfill_when_no_citations(self):
        raw = ResearchResponse(
            content="AI research content...",
            citations=[],  # No citations
        )
        llm = MockLLMForStructurer()

        result = await structure_evidence(
            raw=raw,
            query="AI capabilities",
            provider=llm,
            research_provider_name="test_provider",
        )

        # No citations → no backfill; sources stay as LLM returned them
        for source in result.sources:
            assert source.url is None

    async def test_research_provider_name_set(self):
        raw = ResearchResponse(content="content", citations=[])
        llm = MockLLMForStructurer()

        result = await structure_evidence(
            raw=raw,
            query="test query",
            provider=llm,
            research_provider_name="perplexity",
        )

        assert result.research_provider == "perplexity"


# ---------------------------------------------------------------------------
# Helpers for TestValidateExtractionCoverage
# ---------------------------------------------------------------------------


def _make_coverage_result(
    claims: list[ResearchClaim] | None = None,
    sources: list[ResearchSource] | None = None,
    gaps: list[str] | None = None,
) -> ResearchResult:
    return ResearchResult(
        technique_id="research",
        technique_name="Deep Research",
        summary="summary",
        query="test query",
        sources=sources or [],
        claims=claims or [],
        formatted_evidence="evidence",
        research_provider="mock",
        gaps_identified=gaps or [],
    )


def _make_claim(claim: str = "A claim", source_ids: list[str] | None = None) -> ResearchClaim:
    return ResearchClaim(
        claim=claim,
        source_ids=source_ids or ["S1"],
        confidence="Medium",
        category="fact",
    )


def _make_cov_source(id: str) -> ResearchSource:
    return ResearchSource(
        id=id,
        title=f"Source {id}",
        url=None,
        source_type="web",
        reliability_assessment="Medium",
        retrieved_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidateExtractionCoverage:
    """_validate_extraction_coverage emits targeted warnings for thin extractions."""

    def test_low_claim_density_triggers_warning(self, caplog: pytest.LogCaptureFixture):
        """Raw content >2000 chars with <3 claims triggers a warning."""
        result = _make_coverage_result(claims=[_make_claim()])  # 1 claim
        with caplog.at_level("WARNING", logger="sat.research.structurer"):
            _validate_extraction_coverage(
                raw_content_length=3000,
                citation_count=0,
                result=result,
                query="some query",
            )
        assert any("Low claim density" in r.message for r in caplog.records)

    def test_low_source_coverage_triggers_warning(self, caplog: pytest.LogCaptureFixture):
        """Structured sources < half of citation count triggers a warning."""
        result = _make_coverage_result(sources=[_make_cov_source("S1")])  # 1 source
        with caplog.at_level("WARNING", logger="sat.research.structurer"):
            _validate_extraction_coverage(
                raw_content_length=100,
                citation_count=6,  # 1 < 6/2 = 3
                result=result,
                query="some query",
            )
        assert any("Low source coverage" in r.message for r in caplog.records)

    def test_zero_gaps_on_complex_query_triggers_warning(self, caplog: pytest.LogCaptureFixture):
        """A query >20 chars with zero gaps triggers a warning."""
        result = _make_coverage_result(gaps=[])
        with caplog.at_level("WARNING", logger="sat.research.structurer"):
            _validate_extraction_coverage(
                raw_content_length=100,
                citation_count=0,
                result=result,
                query="A sufficiently long query about a complex topic",
            )
        assert any("Zero gaps" in r.message for r in caplog.records)

    def test_normal_extraction_does_not_trigger_warnings(self, caplog: pytest.LogCaptureFixture):
        """Well-extracted result with adequate claims, sources, and gaps is silent."""
        claims = [_make_claim(f"Claim {i}") for i in range(5)]
        sources = [_make_cov_source(f"S{i}") for i in range(4)]
        result = _make_coverage_result(
            claims=claims,
            sources=sources,
            gaps=["Some gap"],
        )
        with caplog.at_level("WARNING", logger="sat.research.structurer"):
            _validate_extraction_coverage(
                raw_content_length=500,  # Under 2000 threshold — no claim density check
                citation_count=4,  # sources(4) >= citations(4)/2 — no source coverage warning
                result=result,
                query="short q",  # Under 20 chars — no gap warning
            )
        warning_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert not any(
            kw in msg
            for msg in warning_messages
            for kw in ("Low claim density", "Low source coverage", "Zero gaps")
        )

    def test_empty_raw_content_no_claim_density_warning(self, caplog: pytest.LogCaptureFixture):
        """Raw content length 0 does not trigger claim density warning (below threshold)."""
        result = _make_coverage_result(claims=[])
        with caplog.at_level("WARNING", logger="sat.research.structurer"):
            _validate_extraction_coverage(
                raw_content_length=0,
                citation_count=0,
                result=result,
                query="q",
            )
        assert not any("Low claim density" in r.message for r in caplog.records)

    def test_zero_citations_no_source_coverage_warning(self, caplog: pytest.LogCaptureFixture):
        """Zero citations does not trigger source coverage warning (no denominator)."""
        result = _make_coverage_result(sources=[])
        with caplog.at_level("WARNING", logger="sat.research.structurer"):
            _validate_extraction_coverage(
                raw_content_length=100,
                citation_count=0,
                result=result,
                query="some query",
            )
        assert not any("Low source coverage" in r.message for r in caplog.records)

    def test_short_query_no_gap_warning(self, caplog: pytest.LogCaptureFixture):
        """Query <=20 chars with zero gaps does not trigger gap warning."""
        result = _make_coverage_result(gaps=[])
        with caplog.at_level("WARNING", logger="sat.research.structurer"):
            _validate_extraction_coverage(
                raw_content_length=100,
                citation_count=0,
                result=result,
                query="short query",  # 11 chars, under 20
            )
        assert not any("Zero gaps" in r.message for r in caplog.records)
