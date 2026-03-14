"""Tests for atomic fact deduplication.

@decision DEC-DECOMP-003: LLM-based deduplication of atomic facts.
@title Tests for deduplicate_facts
@status accepted
@rationale Verifies the skip-under-5 short-circuit, LLM duplicate merging,
and failure-safe fallback behaviour.
"""

from __future__ import annotations

from sat.decomposition.deduplicator import DeduplicationResponse, DuplicateGroup, deduplicate_facts
from sat.models.decomposition import AtomicFact


def _make_facts(n: int) -> list[AtomicFact]:
    return [AtomicFact(fact_id=f"F{i + 1}", claim=f"Claim {i + 1}.") for i in range(n)]


class MockProviderDedup:
    """Minimal mock that returns a fixed DeduplicationResponse."""

    def __init__(self, response: DeduplicationResponse):
        self._response = response

    async def generate_structured(self, system_prompt, messages, output_schema, **kwargs):
        return self._response


class MockProviderError:
    """Mock that raises on generate_structured."""

    async def generate_structured(self, system_prompt, messages, output_schema, **kwargs):
        raise RuntimeError("LLM unavailable")


class TestDeduplicateFacts:
    async def test_skip_under_five(self):
        facts = _make_facts(4)
        result, removed = await deduplicate_facts(facts, MockProviderError())
        assert result == facts
        assert removed == 0

    async def test_no_duplicates_returns_originals(self):
        facts = _make_facts(6)
        response = DeduplicationResponse(duplicate_groups=[])
        provider = MockProviderDedup(response)
        result, removed = await deduplicate_facts(facts, provider)
        assert len(result) == 6
        assert removed == 0

    async def test_dedup_merges_sources_and_removes_duplicates(self):
        facts = [
            AtomicFact(fact_id="F1", claim="A is true.", source_ids=["src1"]),
            AtomicFact(fact_id="F2", claim="A is true (reworded).", source_ids=["src2"]),
            AtomicFact(fact_id="F3", claim="B is false.", source_ids=["src3"]),
            AtomicFact(fact_id="F4", claim="C happened.", source_ids=["src4"]),
            AtomicFact(fact_id="F5", claim="D occurred.", source_ids=["src5"]),
        ]
        response = DeduplicationResponse(
            duplicate_groups=[DuplicateGroup(canonical_fact_id="F1", duplicate_fact_ids=["F2"])]
        )
        provider = MockProviderDedup(response)
        result, removed = await deduplicate_facts(facts, provider)
        assert removed == 1
        assert len(result) == 4
        # F2 should be gone
        ids = [f.fact_id for f in result]
        assert "F2" not in ids
        assert "F1" in ids
        # F1 should have merged source_ids
        f1 = next(f for f in result if f.fact_id == "F1")
        assert "src1" in f1.source_ids
        assert "src2" in f1.source_ids

    async def test_failure_returns_original(self):
        facts = _make_facts(7)
        result, removed = await deduplicate_facts(facts, MockProviderError())
        assert result == facts
        assert removed == 0

    async def test_unknown_canonical_skipped(self):
        facts = _make_facts(6)
        # Reference a non-existent canonical — should be silently skipped
        response = DeduplicationResponse(
            duplicate_groups=[DuplicateGroup(canonical_fact_id="F99", duplicate_fact_ids=["F1"])]
        )
        provider = MockProviderDedup(response)
        result, removed = await deduplicate_facts(facts, provider)
        # F99 doesn't exist, group is skipped — but F1 is still in ids_to_remove
        # because we never check canonical existence before adding duplicates.
        # Actually our implementation skips the group entirely if canonical not found.
        assert len(result) == 6
