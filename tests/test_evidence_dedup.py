"""Tests for cross-source evidence semantic deduplication.

@decision DEC-EVIDENCE-004
@title Test suite for LLM-based semantic deduplication of cross-source evidence items
@status accepted
@rationale Validates the deduplicate_evidence() function behavior: skip on small lists,
graceful failure on LLM errors, correct source_id merging, and silent skip of invalid IDs.
Tests use mock providers to avoid LLM calls and exercise the full production code path.
"""

from __future__ import annotations

import pytest

from sat.models.evidence import EvidenceItem
from sat.evidence.deduplicator import (
    DuplicateGroup,
    DeduplicationResponse,
    deduplicate_evidence,
)


def _make_item(
    item_id: str, claim: str, source: str = "research", source_ids: list[str] | None = None
) -> EvidenceItem:
    return EvidenceItem(
        item_id=item_id,
        claim=claim,
        source=source,
        source_ids=source_ids or [],
        confidence="Medium",
    )


class TestDeduplicateEvidence:
    """Tests for deduplicate_evidence()."""

    @pytest.mark.asyncio
    async def test_skips_small_lists(self):
        """Lists under 5 items are returned unchanged."""
        items = [_make_item(f"R-C{i}", f"Claim {i}") for i in range(4)]
        result, removed = await deduplicate_evidence(items, None)
        assert result == items
        assert removed == 0

    @pytest.mark.asyncio
    async def test_returns_originals_on_provider_failure(self):
        """LLM failure returns original items."""
        items = [_make_item(f"R-C{i}", f"Claim {i}") for i in range(6)]

        class FailProvider:
            async def generate_structured(self, **kwargs):
                raise RuntimeError("LLM down")

        result, removed = await deduplicate_evidence(items, FailProvider())
        assert result == items
        assert removed == 0

    @pytest.mark.asyncio
    async def test_removes_duplicates_from_response(self):
        """When LLM identifies duplicates, they are removed and source_ids merged."""
        items = [
            _make_item("D-F1", "GDP grew 2.3% in Q3", source="decomposition", source_ids=["src-1"]),
            _make_item(
                "R-C1", "Q3 GDP growth was 2.3 percent", source="research", source_ids=["src-2"]
            ),
            _make_item("R-C2", "Inflation fell to 3.1%", source="research"),
            _make_item("D-F2", "Trade deficit widened", source="decomposition"),
            _make_item("U-1", "Market sentiment positive", source="user"),
        ]

        class MockProvider:
            async def generate_structured(self, **kwargs):
                return DeduplicationResponse(
                    duplicate_groups=[
                        DuplicateGroup(canonical_item_id="R-C1", duplicate_item_ids=["D-F1"]),
                    ]
                )

        result, removed = await deduplicate_evidence(items, MockProvider())
        assert removed == 1
        assert len(result) == 4
        # D-F1 should be removed
        result_ids = [item.item_id for item in result]
        assert "D-F1" not in result_ids
        assert "R-C1" in result_ids
        # R-C1 should have merged source_ids
        rc1 = next(item for item in result if item.item_id == "R-C1")
        assert "src-1" in rc1.source_ids
        assert "src-2" in rc1.source_ids

    @pytest.mark.asyncio
    async def test_empty_groups_no_change(self):
        """Empty duplicate_groups means no changes."""
        items = [_make_item(f"R-C{i}", f"Claim {i}") for i in range(6)]

        class MockProvider:
            async def generate_structured(self, **kwargs):
                return DeduplicationResponse(duplicate_groups=[])

        result, removed = await deduplicate_evidence(items, MockProvider())
        assert result == items
        assert removed == 0

    @pytest.mark.asyncio
    async def test_invalid_ids_ignored(self):
        """Groups referencing non-existent IDs are silently skipped."""
        items = [_make_item(f"R-C{i}", f"Claim {i}") for i in range(5)]

        class MockProvider:
            async def generate_structured(self, **kwargs):
                return DeduplicationResponse(
                    duplicate_groups=[
                        DuplicateGroup(
                            canonical_item_id="NONEXISTENT", duplicate_item_ids=["R-C1"]
                        ),
                    ]
                )

        result, removed = await deduplicate_evidence(items, MockProvider())
        assert len(result) == 5
        assert removed == 0
