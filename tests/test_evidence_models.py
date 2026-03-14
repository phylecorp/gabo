"""Tests for EvidenceItem and EvidencePool models.

@decision DEC-TEST-EVIDENCE-001
@title Unit tests validate EvidenceItem/EvidencePool construction, defaults, and round-trips
@status accepted
@rationale Models are the shared contract between gatherer, formatter, and API layer.
Verifying defaults and serialization here catches regressions early and documents
expected field values for future implementers.

Covers:
- Field defaults and validation
- EvidencePool status field transitions
- Serialization round-trips
"""

from __future__ import annotations

from sat.models.evidence import EvidenceItem, EvidencePool


class TestEvidenceItem:
    def test_defaults(self):
        item = EvidenceItem(
            item_id="D-F1",
            claim="The sky is blue.",
            source="decomposition",
        )
        assert item.item_id == "D-F1"
        assert item.claim == "The sky is blue."
        assert item.source == "decomposition"
        assert item.source_ids == []
        assert item.category == "fact"
        assert item.confidence == "Medium"
        assert item.entities == []
        assert item.verified is False
        assert item.selected is True
        assert item.provider_name is None

    def test_full_construction(self):
        item = EvidenceItem(
            item_id="R-C3",
            claim="GDP grew 2.1% in Q3.",
            source="research",
            source_ids=["S1", "S2"],
            category="analysis",
            confidence="High",
            entities=["GDP", "Q3"],
            verified=True,
            selected=False,
            provider_name="perplexity",
        )
        assert item.source_ids == ["S1", "S2"]
        assert item.verified is True
        assert item.selected is False
        assert item.provider_name == "perplexity"

    def test_serialization_round_trip(self):
        item = EvidenceItem(
            item_id="U-1",
            claim="User provided this.",
            source="user",
        )
        data = item.model_dump()
        restored = EvidenceItem.model_validate(data)
        assert restored == item


class TestEvidencePool:
    def test_defaults(self):
        pool = EvidencePool(session_id="abc123", question="What happened?")
        assert pool.items == []
        assert pool.sources == []
        assert pool.gaps == []
        assert pool.provider_summary == ""
        assert pool.status == "gathering"
        assert pool.error is None

    def test_with_items(self):
        items = [
            EvidenceItem(item_id="D-F1", claim="Fact one.", source="decomposition"),
            EvidenceItem(item_id="R-C1", claim="Research claim.", source="research"),
        ]
        pool = EvidencePool(
            session_id="sess1",
            question="Test question",
            items=items,
            status="ready",
        )
        assert len(pool.items) == 2
        assert pool.status == "ready"

    def test_failed_status_with_error(self):
        pool = EvidencePool(
            session_id="sess2",
            question="Q",
            status="failed",
            error="Research provider unavailable",
        )
        assert pool.status == "failed"
        assert pool.error == "Research provider unavailable"

    def test_sources_as_dicts(self):
        pool = EvidencePool(
            session_id="s",
            question="q",
            sources=[{"id": "S1", "title": "Some source", "url": "https://example.com"}],
        )
        assert pool.sources[0]["id"] == "S1"
