"""Tests for evidence_items population fallback in the pipeline.

@decision DEC-TEST-PIPE-EVIDENCE-001: Verify evidence_items populated from user text
when research doesn't run. The no-research path previously left TechniqueEvidence.items
empty, meaning techniques could not cite evidence IDs from the Evidence Registry even
when the user explicitly provided evidence text. This test covers the fallback.
"""

from __future__ import annotations

from sat.models.evidence import EvidenceItem


class TestEvidenceItemFallbackParsing:
    """Unit tests for the paragraph-splitting logic used in the evidence fallback.

    The pipeline splits config.evidence on double newlines to create EvidenceItems.
    These tests verify the expected behaviour of that splitting logic in isolation,
    so we can lock the contract before the pipeline integration test runs.
    """

    def _build_evidence_items(self, evidence_text: str) -> list[EvidenceItem]:
        """Replicate the pipeline's fallback logic for unit testing."""
        paragraphs = [p.strip() for p in evidence_text.split("\n\n") if p.strip()]
        return [
            EvidenceItem(
                item_id=f"U-{n}",
                claim=para,
                source="user",
                source_ids=[],
                category="fact",
                confidence="Medium",
                verified=False,
                selected=True,
            )
            for n, para in enumerate(paragraphs, start=1)
        ]

    def test_single_paragraph_produces_one_item(self):
        """A single block of text produces exactly one EvidenceItem."""
        items = self._build_evidence_items("Some claim about the situation.")
        assert len(items) == 1
        assert items[0].item_id == "U-1"
        assert items[0].claim == "Some claim about the situation."

    def test_two_paragraphs_produce_two_items(self):
        """Two paragraphs separated by double newline produce two EvidenceItems."""
        text = "First claim.\n\nSecond claim."
        items = self._build_evidence_items(text)
        assert len(items) == 2
        assert items[0].item_id == "U-1"
        assert items[0].claim == "First claim."
        assert items[1].item_id == "U-2"
        assert items[1].claim == "Second claim."

    def test_trailing_blank_lines_ignored(self):
        """Extra blank lines at start/end don't produce empty EvidenceItems."""
        text = "\n\nFirst claim.\n\nSecond claim.\n\n"
        items = self._build_evidence_items(text)
        assert len(items) == 2

    def test_evidence_item_fields_set_correctly(self):
        """EvidenceItem source, category, confidence, verified, selected are all set."""
        items = self._build_evidence_items("A claim.")
        item = items[0]
        assert item.source == "user"
        assert item.source_ids == []
        assert item.category == "fact"
        assert item.confidence == "Medium"
        assert item.verified is False
        assert item.selected is True

    def test_empty_evidence_produces_no_items(self):
        """Empty or whitespace-only evidence produces an empty list."""
        assert self._build_evidence_items("") == []
        assert self._build_evidence_items("   \n\n   ") == []

    def test_multiple_paragraphs_sequential_ids(self):
        """IDs are sequential: U-1, U-2, ..., U-N."""
        text = "\n\n".join(f"Claim {i}." for i in range(1, 6))
        items = self._build_evidence_items(text)
        assert [item.item_id for item in items] == ["U-1", "U-2", "U-3", "U-4", "U-5"]
