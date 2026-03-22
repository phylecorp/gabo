"""Tests for gap-driven iterative research.

@decision DEC-RESEARCH-013
@title Test suite for gap resolver — real implementations, no mocks for internal logic
@status accepted
@rationale _merge_follow_up is tested directly with real ResearchResult objects.
resolve_gaps tests use minimal stub providers (only external boundaries) that mimic
the production sequence: initial research → LLM generates follow-up query → provider
returns raw response → structurer produces ResearchResult → merge. Tests verify the
three critical invariants: deduplication correctness, iteration cap enforcement, and
graceful failure handling at each stage.

Production sequence: gap resolution runs after initial research + verification in
pipeline.py. The common path is 1-3 gaps, 1 follow-up iteration, 2-5 new claims
merged. Tests cover this path plus early-exit conditions.
"""

from __future__ import annotations

import pytest

from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.research.gap_resolver import _merge_follow_up, resolve_gaps


def _make_result(
    claims: list[str] | None = None,
    gaps: list[str] | None = None,
    sources: list[dict] | None = None,
) -> ResearchResult:
    """Build a minimal ResearchResult for testing."""
    return ResearchResult(
        technique_id="research",
        technique_name="Deep Research",
        summary="Test research",
        query="test query",
        research_provider="test",
        claims=[
            ResearchClaim(claim=c, confidence="Medium", category="fact", source_ids=[])
            for c in (claims or [])
        ],
        sources=[
            ResearchSource(
                id=s.get("id", f"S{i}"),
                title=s.get("title", ""),
                source_type="web",
                reliability_assessment="Medium",
            )
            for i, s in enumerate(sources or [])
        ],
        gaps_identified=gaps or [],
        formatted_evidence="",
    )


class TestMergeFollowUp:
    """Tests for _merge_follow_up deduplication."""

    def test_new_claims_added(self):
        existing = _make_result(claims=["Claim A"])
        follow_up = _make_result(claims=["Claim B"])
        new_claims, new_sources = _merge_follow_up(existing, follow_up)
        assert len(new_claims) == 1
        assert new_claims[0].claim == "Claim B"

    def test_duplicate_claims_excluded(self):
        """Case-insensitive dedup prevents exact duplicate claims."""
        existing = _make_result(claims=["Claim A"])
        follow_up = _make_result(claims=["claim a", "Claim B"])  # "claim a" matches "Claim A"
        new_claims, _ = _merge_follow_up(existing, follow_up)
        assert len(new_claims) == 1
        assert new_claims[0].claim == "Claim B"

    def test_new_sources_added(self):
        existing = _make_result(sources=[{"id": "S1", "title": "Source 1"}])
        follow_up = _make_result(sources=[{"id": "S2", "title": "Source 2"}])
        _, new_sources = _merge_follow_up(existing, follow_up)
        assert len(new_sources) == 1
        assert new_sources[0].id == "S2"

    def test_duplicate_sources_excluded(self):
        """Sources with same ID are not re-added."""
        existing = _make_result(sources=[{"id": "S1", "title": "Source 1"}])
        follow_up = _make_result(
            sources=[
                {"id": "S1", "title": "Source 1 dup"},
                {"id": "S2", "title": "New"},
            ]
        )
        _, new_sources = _merge_follow_up(existing, follow_up)
        assert len(new_sources) == 1
        assert new_sources[0].id == "S2"

    def test_empty_follow_up(self):
        """Empty follow-up returns empty lists — nothing to merge."""
        existing = _make_result(claims=["A"], sources=[{"id": "S1"}])
        follow_up = _make_result()
        new_claims, new_sources = _merge_follow_up(existing, follow_up)
        assert len(new_claims) == 0
        assert len(new_sources) == 0

    def test_whitespace_normalised_in_dedup(self):
        """Leading/trailing whitespace does not create false duplicates."""
        existing = _make_result(claims=["Claim A"])
        follow_up = _make_result(claims=["  Claim A  ", "Claim B"])
        new_claims, _ = _merge_follow_up(existing, follow_up)
        assert len(new_claims) == 1
        assert new_claims[0].claim == "Claim B"

    def test_all_new_when_no_overlap(self):
        existing = _make_result(claims=["A", "B"])
        follow_up = _make_result(claims=["C", "D"])
        new_claims, _ = _merge_follow_up(existing, follow_up)
        assert len(new_claims) == 2


class TestResolveGaps:
    """Tests for resolve_gaps function."""

    @pytest.mark.asyncio
    async def test_no_gaps_returns_unchanged(self):
        """No gaps = no iteration at all; identity returned."""
        result = _make_result(claims=["A"], gaps=[])
        resolved = await resolve_gaps(result, None, None, max_iterations=2)  # type: ignore
        assert resolved is result  # Identity check — not modified

    @pytest.mark.asyncio
    async def test_stops_on_no_actionable_gaps(self):
        """LLM responds NO_ACTIONABLE_GAPS → stops immediately, no research call."""
        result = _make_result(claims=["A"], gaps=["Unanswerable gap"])

        class MockLLM:
            async def generate(self, **kwargs):
                class R:
                    text = "NO_ACTIONABLE_GAPS"
                return R()

        resolved = await resolve_gaps(result, None, MockLLM(), max_iterations=2)  # type: ignore
        assert len(resolved.claims) == 1  # No new claims — no iteration occurred

    @pytest.mark.asyncio
    async def test_provider_failure_stops_gracefully(self):
        """Research provider failure → stops without crashing, original preserved."""
        result = _make_result(claims=["A"], gaps=["Gap 1"])

        class MockLLM:
            async def generate(self, **kwargs):
                class R:
                    text = "follow up query"
                return R()

        class FailProvider:
            async def research(self, **kwargs):
                raise RuntimeError("Provider down")

        resolved = await resolve_gaps(result, FailProvider(), MockLLM(), max_iterations=2)  # type: ignore
        assert len(resolved.claims) == 1  # Original unchanged

    @pytest.mark.asyncio
    async def test_llm_failure_stops_gracefully(self):
        """LLM failure during query generation → stops without crashing."""
        result = _make_result(claims=["A"], gaps=["Gap 1"])

        class FailLLM:
            async def generate(self, **kwargs):
                raise RuntimeError("LLM down")

        resolved = await resolve_gaps(result, None, FailLLM(), max_iterations=2)  # type: ignore
        assert len(resolved.claims) == 1  # Original unchanged

    @pytest.mark.asyncio
    async def test_merges_claims_from_follow_up(self):
        """Full successful iteration merges new claims and updates gaps."""
        from sat.research.base import ResearchResponse

        initial = _make_result(claims=["Claim A"], gaps=["What about claim B?"])
        follow_up_result = _make_result(
            claims=["Claim B"],
            gaps=[],  # No remaining gaps after follow-up
        )

        class MockLLM:
            async def generate(self, **kwargs):
                class R:
                    text = "follow-up query about claim B"
                return R()

            async def generate_structured(self, **kwargs):
                return follow_up_result

        class MockResearchProvider:
            async def research(self, **kwargs):
                return ResearchResponse(content="Follow-up research content about claim B")

        resolved = await resolve_gaps(
            initial, MockResearchProvider(), MockLLM(), max_iterations=2
        )

        claim_texts = [c.claim for c in resolved.claims]
        assert "Claim A" in claim_texts
        assert "Claim B" in claim_texts
        assert resolved.gaps_identified == []

    @pytest.mark.asyncio
    async def test_respects_max_iterations(self):
        """Even with persistent gaps, stops at max_iterations."""
        from sat.research.base import ResearchResponse

        iteration_count = 0
        follow_up_with_gap = _make_result(
            claims=["Extra Claim"],
            gaps=["Still a gap"],
        )

        class MockLLM:
            async def generate(self, **kwargs):
                class R:
                    text = "follow-up query"
                return R()

            async def generate_structured(self, **kwargs):
                nonlocal iteration_count
                iteration_count += 1
                return follow_up_with_gap

        class MockResearchProvider:
            async def research(self, **kwargs):
                return ResearchResponse(content="Some research content")

        initial = _make_result(claims=["A"], gaps=["Gap persists"])
        await resolve_gaps(
            initial, MockResearchProvider(), MockLLM(), max_iterations=2
        )

        # max_iterations=2 means exactly 2 iterations ran
        assert iteration_count == 2

    @pytest.mark.asyncio
    async def test_empty_research_response_stops(self):
        """Empty research response → stops cleanly, no crash."""
        from sat.research.base import ResearchResponse

        result = _make_result(claims=["A"], gaps=["Gap 1"])

        class MockLLM:
            async def generate(self, **kwargs):
                class R:
                    text = "follow up query"
                return R()

        class EmptyProvider:
            async def research(self, **kwargs):
                return ResearchResponse(content="   ")  # Whitespace only

        resolved = await resolve_gaps(result, EmptyProvider(), MockLLM(), max_iterations=2)  # type: ignore
        assert len(resolved.claims) == 1  # No new claims from empty response
