"""Tests for gap-driven iterative research.

@decision DEC-RESEARCH-013
@title Test suite for gap resolver — real implementations, no mocks for internal logic
@status accepted
@rationale _merge_follow_up is tested directly with real ResearchResult objects.
resolve_gaps tests use minimal stub providers (only external boundaries) that mimic
the production sequence: initial research → LLM generates follow-up queries (batch) →
providers run concurrently → structurer produces ResearchResult → merge. Tests verify
the three critical invariants: deduplication correctness, max-query cap enforcement,
and graceful failure handling at each stage.

Production sequence: gap resolution runs after initial research + verification in
pipeline.py. The common path is 1-3 gaps, parallel follow-up queries, 2-5 new claims
merged. Tests cover this path plus early-exit conditions.

NOTE: The new parallel implementation uses generate_structured (not generate) for
query generation, returning a GapQueries object. generate_structured is also called
by the structurer for evidence parsing. Tests must distinguish the two call sites
by inspecting output_schema.
"""

from __future__ import annotations

import pytest

from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.research.gap_resolver import GapQueries, _merge_follow_up, resolve_gaps


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
    """Tests for resolve_gaps function — parallel implementation."""

    @pytest.mark.asyncio
    async def test_no_gaps_returns_unchanged(self):
        """No gaps = no LLM call at all; identity returned."""
        result = _make_result(claims=["A"], gaps=[])
        resolved = await resolve_gaps(result, None, None, max_iterations=2)  # type: ignore
        assert resolved is result  # Identity check — not modified

    @pytest.mark.asyncio
    async def test_stops_on_no_actionable_gaps(self):
        """LLM returns empty queries list → stops immediately, no research call."""
        result = _make_result(claims=["A"], gaps=["Unanswerable gap"])

        class MockLLM:
            async def generate_structured(self, output_schema, **kwargs):
                # Query generation call — return empty query list
                if output_schema is GapQueries:
                    return GapQueries(queries=[])
                # Structurer call should never be reached
                raise AssertionError("Structurer should not be called when no queries generated")

        resolved = await resolve_gaps(result, None, MockLLM(), max_iterations=2)  # type: ignore
        assert len(resolved.claims) == 1  # No new claims — no research occurred

    @pytest.mark.asyncio
    async def test_provider_failure_preserved_gracefully(self):
        """Research provider failure → that query's results skipped, original claims kept."""
        result = _make_result(claims=["A"], gaps=["Gap 1"])

        class MockLLM:
            async def generate_structured(self, output_schema, **kwargs):
                if output_schema is GapQueries:
                    return GapQueries(queries=["follow up query"])
                # Structurer should not be called if research fails
                raise AssertionError("Structurer should not be called after research failure")

        class FailProvider:
            async def research(self, **kwargs):
                raise RuntimeError("Provider down")

        resolved = await resolve_gaps(result, FailProvider(), MockLLM(), max_iterations=2)  # type: ignore
        assert len(resolved.claims) == 1  # Original unchanged

    @pytest.mark.asyncio
    async def test_llm_query_generation_failure_stops_gracefully(self):
        """LLM failure during query generation → stops without crashing."""
        result = _make_result(claims=["A"], gaps=["Gap 1"])

        class FailLLM:
            async def generate_structured(self, **kwargs):
                raise RuntimeError("LLM down")

        resolved = await resolve_gaps(result, None, FailLLM(), max_iterations=2)  # type: ignore
        assert len(resolved.claims) == 1  # Original unchanged

    @pytest.mark.asyncio
    async def test_merges_claims_from_follow_up(self):
        """Full successful parallel resolution merges new claims and clears gaps."""
        from sat.research.base import ResearchResponse

        initial = _make_result(claims=["Claim A"], gaps=["What about claim B?"])
        follow_up_result = _make_result(claims=["Claim B"], gaps=[])

        class MockLLM:
            async def generate_structured(self, output_schema, **kwargs):
                if output_schema is GapQueries:
                    return GapQueries(queries=["follow-up query about claim B"])
                # Structurer call — return the follow-up result
                return follow_up_result

        class MockResearchProvider:
            async def research(self, **kwargs):
                return ResearchResponse(content="Follow-up research content about claim B")

        resolved = await resolve_gaps(initial, MockResearchProvider(), MockLLM(), max_iterations=2)

        claim_texts = [c.claim for c in resolved.claims]
        assert "Claim A" in claim_texts
        assert "Claim B" in claim_texts
        assert resolved.gaps_identified == []

    @pytest.mark.asyncio
    async def test_respects_max_iterations_as_query_cap(self):
        """max_iterations caps the number of parallel queries generated, not loops."""
        from sat.research.base import ResearchResponse

        # 3 gaps but max_iterations=2 → only 2 queries should run
        follow_up_result = _make_result(claims=["Extra Claim"], gaps=[])
        research_call_count = 0

        class MockLLM:
            async def generate_structured(self, output_schema, **kwargs):
                if output_schema is GapQueries:
                    # Return 3 queries — max_iterations=2 should cap to 2
                    return GapQueries(queries=["query 1", "query 2", "query 3"])
                return follow_up_result

        class CountingProvider:
            async def research(self, **kwargs):
                nonlocal research_call_count
                research_call_count += 1
                return ResearchResponse(content="Some research content")

        initial = _make_result(claims=["A"], gaps=["Gap 1", "Gap 2", "Gap 3"])
        await resolve_gaps(initial, CountingProvider(), MockLLM(), max_iterations=2)

        # max_iterations=2 → at most 2 research calls, even though LLM returned 3 queries
        assert research_call_count == 2

    @pytest.mark.asyncio
    async def test_empty_research_response_skipped(self):
        """Empty research response → that query skipped cleanly, no crash."""
        from sat.research.base import ResearchResponse

        result = _make_result(claims=["A"], gaps=["Gap 1"])

        class MockLLM:
            async def generate_structured(self, output_schema, **kwargs):
                if output_schema is GapQueries:
                    return GapQueries(queries=["follow up query"])
                raise AssertionError("Structurer should not be reached for empty response")

        class EmptyProvider:
            async def research(self, **kwargs):
                return ResearchResponse(content="   ")  # Whitespace only

        resolved = await resolve_gaps(result, EmptyProvider(), MockLLM(), max_iterations=2)  # type: ignore
        assert len(resolved.claims) == 1  # No new claims from empty response

    @pytest.mark.asyncio
    async def test_parallel_dedup_across_concurrent_queries(self):
        """Concurrent queries returning the same claim are deduplicated."""
        from sat.research.base import ResearchResponse

        initial = _make_result(claims=["Claim A"], gaps=["Gap 1", "Gap 2"])
        # Both follow-up queries return the same new claim
        shared_result = _make_result(claims=["Shared Claim"], gaps=[])

        class MockLLM:
            async def generate_structured(self, output_schema, **kwargs):
                if output_schema is GapQueries:
                    return GapQueries(queries=["query 1", "query 2"])
                return shared_result

        class MockProvider:
            async def research(self, **kwargs):
                return ResearchResponse(content="Some research content")

        resolved = await resolve_gaps(initial, MockProvider(), MockLLM(), max_iterations=5)

        # "Shared Claim" should appear exactly once despite two queries returning it
        shared_claims = [c for c in resolved.claims if c.claim == "Shared Claim"]
        assert len(shared_claims) == 1


class TestClaimOriginTagging:
    """Tests for origin tagging on gap-resolution claims."""

    @pytest.mark.asyncio
    async def test_new_claims_tagged_with_query_origin(self):
        """Claims from gap resolution carry origin='gap_resolution_query_N'."""
        from sat.research.base import ResearchResponse

        initial = _make_result(claims=["Claim A"], gaps=["What about B?"])
        follow_up_result = _make_result(claims=["Claim B"], gaps=[])

        class MockLLM:
            async def generate_structured(self, output_schema, **kwargs):
                if output_schema is GapQueries:
                    return GapQueries(queries=["follow-up query"])
                return follow_up_result

        class MockProvider:
            async def research(self, **kwargs):
                return ResearchResponse(content="Research content about B")

        resolved = await resolve_gaps(initial, MockProvider(), MockLLM(), max_iterations=2)

        gap_claims = [c for c in resolved.claims if c.claim == "Claim B"]
        assert len(gap_claims) == 1
        assert gap_claims[0].origin == "gap_resolution_query_1"

    @pytest.mark.asyncio
    async def test_original_claims_have_no_origin(self):
        """Claims from initial research retain origin=None (not modified)."""
        from sat.research.base import ResearchResponse

        initial = _make_result(claims=["Claim A"], gaps=["What about B?"])
        follow_up_result = _make_result(claims=["Claim B"], gaps=[])

        class MockLLM:
            async def generate_structured(self, output_schema, **kwargs):
                if output_schema is GapQueries:
                    return GapQueries(queries=["follow-up query"])
                return follow_up_result

        class MockProvider:
            async def research(self, **kwargs):
                return ResearchResponse(content="Research content about B")

        resolved = await resolve_gaps(initial, MockProvider(), MockLLM(), max_iterations=2)

        original_claims = [c for c in resolved.claims if c.claim == "Claim A"]
        assert len(original_claims) == 1
        assert original_claims[0].origin is None

    @pytest.mark.asyncio
    async def test_second_query_origin_label(self):
        """Claims from second parallel query carry 'gap_resolution_query_2'."""
        from sat.research.base import ResearchResponse

        initial = _make_result(claims=["Claim A"], gaps=["Need B", "Need C"])
        # Two different follow-up results keyed by call order
        follow_up_b = _make_result(claims=["Claim B"], gaps=[])
        follow_up_c = _make_result(claims=["Claim C"], gaps=[])
        call_count = 0

        class MockLLM:
            async def generate_structured(self, output_schema, **kwargs):
                nonlocal call_count
                if output_schema is GapQueries:
                    return GapQueries(queries=["query for B", "query for C"])
                # Structurer calls: first returns B, second returns C
                call_count += 1
                return follow_up_b if call_count == 1 else follow_up_c

        class MockProvider:
            async def research(self, **kwargs):
                return ResearchResponse(content="Some research content")

        resolved = await resolve_gaps(initial, MockProvider(), MockLLM(), max_iterations=3)

        claim_b = [c for c in resolved.claims if c.claim == "Claim B"]
        claim_c = [c for c in resolved.claims if c.claim == "Claim C"]
        assert len(claim_b) == 1
        assert len(claim_c) == 1
        # Both carry their respective query-index origin labels
        assert claim_b[0].origin == "gap_resolution_query_1"
        assert claim_c[0].origin == "gap_resolution_query_2"


class TestMultiResearchAdapterUnit:
    """Unit tests for MultiResearchAdapter."""

    @pytest.mark.asyncio
    async def test_adapter_merges_responses_from_multiple_providers(self):
        """Adapter calls all providers, merges results into a single ResearchResponse."""
        from sat.research.base import ResearchResponse, SearchResult
        from sat.research.multi_runner import MultiResearchAdapter

        class FakeProviderA:
            async def research(self, query, context=None, max_sources=10):
                return ResearchResponse(
                    content="Provider A content",
                    citations=[SearchResult(title="A1", url="http://a1.com", snippet="a")],
                )

        class FakeProviderB:
            async def research(self, query, context=None, max_sources=10):
                return ResearchResponse(
                    content="Provider B content",
                    citations=[SearchResult(title="B1", url="http://b1.com", snippet="b")],
                )

        class FakeLLM:
            pass

        adapter = MultiResearchAdapter(llm_provider=FakeLLM())  # type: ignore

        # Monkey-patch discover_providers to return our fakes
        import sat.research.multi_runner as mr_module

        original = mr_module.discover_providers

        def fake_discover(llm_provider=None):
            return [("provider_a", FakeProviderA()), ("provider_b", FakeProviderB())]

        mr_module.discover_providers = fake_discover
        try:
            response = await adapter.research(query="test query", max_sources=5)
        finally:
            mr_module.discover_providers = original

        assert "Provider A content" in response.content
        assert "Provider B content" in response.content
        assert len(response.citations) == 2

    @pytest.mark.asyncio
    async def test_adapter_raises_when_all_providers_fail(self):
        """Adapter raises RuntimeError when every provider raises."""
        from sat.research.multi_runner import MultiResearchAdapter

        class FailProvider:
            async def research(self, **kwargs):
                raise RuntimeError("down")

        class FakeLLM:
            pass

        adapter = MultiResearchAdapter(llm_provider=FakeLLM())  # type: ignore

        import sat.research.multi_runner as mr_module

        original = mr_module.discover_providers

        def fake_discover(llm_provider=None):
            return [("fail_a", FailProvider()), ("fail_b", FailProvider())]

        mr_module.discover_providers = fake_discover
        try:
            with pytest.raises(RuntimeError, match="All research providers failed"):
                await adapter.research(query="test query")
        finally:
            mr_module.discover_providers = original

    @pytest.mark.asyncio
    async def test_adapter_raises_when_no_providers(self):
        """Adapter raises ValueError when discover_providers returns empty list."""
        from sat.research.multi_runner import MultiResearchAdapter

        class FakeLLM:
            pass

        adapter = MultiResearchAdapter(llm_provider=FakeLLM())  # type: ignore

        import sat.research.multi_runner as mr_module

        original = mr_module.discover_providers

        def fake_discover(llm_provider=None):
            return []

        mr_module.discover_providers = fake_discover
        try:
            with pytest.raises(ValueError, match="No research providers available"):
                await adapter.research(query="test query")
        finally:
            mr_module.discover_providers = original

    @pytest.mark.asyncio
    async def test_adapter_partial_failure_uses_successes(self):
        """If one provider fails but another succeeds, result uses the success."""
        from sat.research.base import ResearchResponse, SearchResult
        from sat.research.multi_runner import MultiResearchAdapter

        class GoodProvider:
            async def research(self, query, context=None, max_sources=10):
                return ResearchResponse(
                    content="Good content",
                    citations=[SearchResult(title="G1", url="http://g1.com", snippet="g")],
                )

        class BadProvider:
            async def research(self, **kwargs):
                raise RuntimeError("down")

        class FakeLLM:
            pass

        adapter = MultiResearchAdapter(llm_provider=FakeLLM())  # type: ignore

        import sat.research.multi_runner as mr_module

        original = mr_module.discover_providers

        def fake_discover(llm_provider=None):
            return [("good", GoodProvider()), ("bad", BadProvider())]

        mr_module.discover_providers = fake_discover
        try:
            response = await adapter.research(query="test query")
        finally:
            mr_module.discover_providers = original

        assert "Good content" in response.content
        assert len(response.citations) == 1


class TestConfigDefaults:
    """Tests that config defaults match the bumped values."""

    def test_gap_resolution_max_iterations_default(self):
        from sat.config import GapResolutionConfig

        cfg = GapResolutionConfig()
        assert cfg.max_iterations == 3

    def test_gap_resolution_max_sources_per_iteration_default(self):
        from sat.config import GapResolutionConfig

        cfg = GapResolutionConfig()
        assert cfg.max_sources_per_iteration == 10

    def test_research_config_max_sources_default(self):
        from sat.config import ResearchConfig

        cfg = ResearchConfig()
        assert cfg.max_sources == 20
