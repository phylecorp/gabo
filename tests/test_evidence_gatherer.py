"""Tests for evidence gatherer internals and gather_evidence() integration.

@decision DEC-TEST-EVIDENCE-003
@title Gatherer tests cover deduplication logic, user-item splitting, and pool assembly
@status accepted
@rationale The merge-and-deduplicate logic is the most complex part of the gatherer.
Tests use internal helpers directly (not mocking them) to verify the priority order
(research > decomposition > user) and that duplicate detection uses normalized claim text.
The gather_evidence() smoke test verifies the full async path with no external calls.

Covers:
- _split_to_user_items: paragraph splitting, item IDs, fallback for single paragraph
- _merge_and_deduplicate: priority order, exact-text dedup, all-unique passthrough
- gather_evidence() with no evidence and research disabled: returns empty pool quickly
- Events emitted: EvidenceGatheringStarted and EvidenceGatheringCompleted
"""

from __future__ import annotations

import pytest

from sat.config import DecompositionConfig, ResearchConfig
from sat.events import EventBus, PipelineEvent
from sat.evidence.gatherer import _merge_and_deduplicate, _split_to_user_items
from sat.models.evidence import EvidenceItem


# ---------------------------------------------------------------------------
# _split_to_user_items
# ---------------------------------------------------------------------------


class TestSplitToUserItems:
    def test_single_paragraph(self):
        items = _split_to_user_items("Just one paragraph here.")
        assert len(items) == 1
        assert items[0].item_id == "U-1"
        assert items[0].claim == "Just one paragraph here."
        assert items[0].source == "user"
        assert items[0].selected is True

    def test_multiple_paragraphs(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        items = _split_to_user_items(text)
        assert len(items) == 3
        assert items[0].item_id == "U-1"
        assert items[1].item_id == "U-2"
        assert items[2].item_id == "U-3"
        assert items[0].claim == "First paragraph."
        assert items[2].claim == "Third paragraph."

    def test_empty_paragraphs_skipped(self):
        text = "Para one.\n\n\n\nPara two."
        items = _split_to_user_items(text)
        assert len(items) == 2

    def test_whitespace_only_skipped(self):
        text = "Real content.\n\n   \n\nMore content."
        items = _split_to_user_items(text)
        assert len(items) == 2

    def test_defaults(self):
        items = _split_to_user_items("Single fact.")
        assert items[0].confidence == "Medium"
        assert items[0].category == "fact"
        assert items[0].source_ids == []
        assert items[0].entities == []


# ---------------------------------------------------------------------------
# _merge_and_deduplicate
# ---------------------------------------------------------------------------


def _make_item(item_id: str, claim: str, source: str) -> EvidenceItem:
    return EvidenceItem(item_id=item_id, claim=claim, source=source)


class TestMergeAndDeduplicate:
    def test_no_duplicates_all_returned(self):
        decomp = [_make_item("D-F1", "Fact A.", "decomposition")]
        research = [_make_item("R-C1", "Claim B.", "research")]
        user = [_make_item("U-1", "User text.", "user")]
        result = _merge_and_deduplicate(decomp, research, user)
        assert len(result) == 3

    def test_empty_inputs(self):
        result = _merge_and_deduplicate([], [], [])
        assert result == []

    def test_only_research_items(self):
        research = [
            _make_item("R-C1", "Claim one.", "research"),
            _make_item("R-C2", "Claim two.", "research"),
        ]
        result = _merge_and_deduplicate([], research, [])
        assert len(result) == 2

    def test_research_wins_over_decomposition_duplicate(self):
        """When research and decomp have same claim, research item is kept."""
        claim = "The market declined 5% last quarter."
        decomp = [_make_item("D-F1", claim, "decomposition")]
        research = [_make_item("R-C1", claim, "research")]
        result = _merge_and_deduplicate(decomp, research, [])
        assert len(result) == 1
        assert result[0].source == "research"
        assert result[0].item_id == "R-C1"

    def test_research_wins_over_user_duplicate(self):
        claim = "Unemployment rose to 6%."
        user = [_make_item("U-1", claim, "user")]
        research = [_make_item("R-C1", claim, "research")]
        result = _merge_and_deduplicate([], research, user)
        assert len(result) == 1
        assert result[0].source == "research"

    def test_decomposition_wins_over_user_duplicate(self):
        claim = "Inflation is at 3.2%."
        user = [_make_item("U-1", claim, "user")]
        decomp = [_make_item("D-F1", claim, "decomposition")]
        result = _merge_and_deduplicate(decomp, [], user)
        assert len(result) == 1
        assert result[0].source == "decomposition"

    def test_case_insensitive_dedup(self):
        decomp = [_make_item("D-F1", "The market rose.", "decomposition")]
        research = [_make_item("R-C1", "THE MARKET ROSE.", "research")]
        result = _merge_and_deduplicate(decomp, research, [])
        assert len(result) == 1
        assert result[0].source == "research"

    def test_output_order_decomp_then_research_then_user(self):
        """Surviving items appear in stable order: decomp → research → user."""
        decomp = [_make_item("D-F1", "Unique decomp fact.", "decomposition")]
        research = [_make_item("R-C1", "Unique research claim.", "research")]
        user = [_make_item("U-1", "Unique user text.", "user")]
        result = _merge_and_deduplicate(decomp, research, user)
        assert result[0].source == "decomposition"
        assert result[1].source == "research"
        assert result[2].source == "user"


# ---------------------------------------------------------------------------
# gather_evidence() — async smoke test, no external calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gather_evidence_no_evidence_no_research():
    """With no evidence and research disabled, returns empty pool immediately."""
    from tests.helpers import MockProvider

    from sat.evidence.gatherer import gather_evidence

    provider = MockProvider(text_response="{}")
    pool = await gather_evidence(
        question="What is the status?",
        evidence=None,
        research_config=ResearchConfig(enabled=False),
        decomposition_config=DecompositionConfig(enabled=False),
        provider=provider,
    )
    assert pool.status == "ready"
    assert pool.items == []
    assert pool.question == "What is the status?"
    assert pool.session_id  # non-empty


@pytest.mark.asyncio
async def test_gather_evidence_emits_start_and_complete_events():
    """gather_evidence emits EvidenceGatheringStarted and EvidenceGatheringCompleted."""
    from tests.helpers import MockProvider

    from sat.evidence.gatherer import gather_evidence

    provider = MockProvider(text_response="{}")
    captured: list[PipelineEvent] = []
    bus = EventBus()

    async def capture(event: PipelineEvent) -> None:
        captured.append(event)

    bus.subscribe(capture)

    await gather_evidence(
        question="Test question",
        evidence=None,
        research_config=ResearchConfig(enabled=False),
        decomposition_config=DecompositionConfig(enabled=False),
        provider=provider,
        events=bus,
    )

    types = [type(e).__name__ for e in captured]
    assert "EvidenceGatheringStarted" in types
    assert "EvidenceGatheringCompleted" in types


@pytest.mark.asyncio
async def test_gather_evidence_user_items_from_evidence_no_decomp():
    """When evidence provided and decomposition disabled, user items are created."""
    from tests.helpers import MockProvider

    from sat.evidence.gatherer import gather_evidence

    provider = MockProvider(text_response="{}")
    evidence_text = "First paragraph of evidence.\n\nSecond paragraph of evidence."

    pool = await gather_evidence(
        question="Analyze this.",
        evidence=evidence_text,
        research_config=ResearchConfig(enabled=False),
        decomposition_config=DecompositionConfig(enabled=False),
        provider=provider,
    )

    assert pool.status == "ready"
    assert len(pool.items) == 2
    assert all(item.source == "user" for item in pool.items)
    assert pool.items[0].item_id == "U-1"
    assert pool.items[1].item_id == "U-2"
