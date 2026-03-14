"""Tests for format_curated_evidence().

@decision DEC-TEST-EVIDENCE-002
@title Formatter tests verify deterministic output structure for technique injection
@status accepted
@rationale format_curated_evidence() output is injected as config.evidence into
existing technique prompts. Tests ensure: only selected items appear, source
registry and gaps sections are included, empty selections return empty string.

Covers:
- Only selected items appear in output
- Source registry section from research sources
- Information gaps section
- Entity index from item metadata
- Empty selection returns empty string
- Output contains key structural markers
"""

from __future__ import annotations

from sat.evidence.formatter import format_curated_evidence
from sat.models.evidence import EvidenceItem


def _make_item(item_id: str, claim: str, source: str = "decomposition", selected: bool = True, **kwargs) -> EvidenceItem:
    return EvidenceItem(item_id=item_id, claim=claim, source=source, selected=selected, **kwargs)


class TestFormatCuratedEvidence:
    def test_empty_selection_returns_empty_string(self):
        items = [_make_item("D-F1", "Some fact.", selected=False)]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert result == ""

    def test_all_deselected_returns_empty_string(self):
        items = [
            _make_item("D-F1", "Fact A.", selected=False),
            _make_item("D-F2", "Fact B.", selected=False),
        ]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert result == ""

    def test_single_selected_item_appears(self):
        items = [_make_item("D-F1", "The economy contracted.")]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert "D-F1" in result
        assert "The economy contracted." in result

    def test_only_selected_items_appear(self):
        items = [
            _make_item("D-F1", "Selected fact.", selected=True),
            _make_item("D-F2", "Deselected fact.", selected=False),
        ]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert "Selected fact." in result
        assert "Deselected fact." not in result

    def test_header_contains_item_count(self):
        items = [
            _make_item("D-F1", "Fact one."),
            _make_item("R-C1", "Research claim.", source="research"),
        ]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert "2 items" in result

    def test_source_registry_section_included(self):
        items = [_make_item("R-C1", "A claim.", source="research")]
        sources = [
            {
                "id": "S1",
                "title": "Reuters",
                "url": "https://reuters.com/article",
                "source_type": "news",
                "reliability_assessment": "High",
            }
        ]
        result = format_curated_evidence(items, sources=sources, gaps=[])
        assert "## Source Registry" in result
        assert "S1" in result
        assert "Reuters" in result

    def test_gaps_section_included(self):
        items = [_make_item("D-F1", "Some fact.")]
        gaps = ["No information on Q4 data.", "Missing demographic breakdown."]
        result = format_curated_evidence(items, sources=[], gaps=gaps)
        assert "## Information Gaps" in result
        assert "No information on Q4 data." in result

    def test_entity_index_included_when_entities_present(self):
        items = [_make_item("D-F1", "GDP grew.", entities=["GDP", "Economy"])]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert "## Entity Index" in result
        assert "GDP" in result
        assert "Economy" in result

    def test_no_entity_index_when_no_entities(self):
        items = [_make_item("D-F1", "Generic statement.")]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert "## Entity Index" not in result

    def test_verified_flag_appears_for_verified_items(self):
        items = [_make_item("R-C1", "Verified fact.", verified=True)]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert "[VERIFIED]" in result

    def test_no_verified_flag_for_unverified_items(self):
        items = [_make_item("D-F1", "Unverified fact.", verified=False)]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert "[VERIFIED]" not in result

    def test_confidence_appears_in_output(self):
        items = [_make_item("D-F1", "A fact.", confidence="High")]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert "Confidence: High" in result

    def test_category_appears_in_output(self):
        items = [_make_item("R-C1", "An analysis.", source="research", category="analysis")]
        result = format_curated_evidence(items, sources=[], gaps=[])
        assert "Category: analysis" in result

    def test_source_type_summary_in_header(self):
        items = [
            _make_item("D-F1", "Decomposed.", source="decomposition"),
            _make_item("R-C1", "Researched.", source="research"),
            _make_item("U-1", "User text.", source="user"),
        ]
        result = format_curated_evidence(items, sources=[], gaps=[])
        # Header should mention decomposed, researched, user-provided
        assert "decomposed" in result
        assert "researched" in result
        assert "user-provided" in result
