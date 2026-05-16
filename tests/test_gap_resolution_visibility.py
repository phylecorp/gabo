"""Tests for gap resolution visibility: models, origin propagation, and gather integration.

@decision DEC-TEST-GAP-VIS-001
@title Test suite proves end-to-end origin propagation + GapResolutionSummary model
@status accepted
@rationale Gap resolution visibility requires:
  1. EvidenceItem.origin field accepted and round-trips through JSON
  2. GapResolutionSummary model validates correctly
  3. EvidencePool.gap_resolution field accepted with backward compat
  4. _build_items_from_research_result() propagates origin from ResearchClaim
  5. EvidencePool without gap_resolution round-trips (backward compat)

Tests are unit-level and use no external LLM or network calls.
"""

from __future__ import annotations

from sat.models.evidence import EvidenceItem, EvidencePool, GapResolutionSummary


# ---------------------------------------------------------------------------
# EvidenceItem.origin field
# ---------------------------------------------------------------------------


class TestEvidenceItemOriginField:
    def test_origin_default_is_none(self):
        """EvidenceItem.origin defaults to None (backward compat)."""
        item = EvidenceItem(item_id="R-C1", claim="Test claim.", source="research")
        assert item.origin is None

    def test_origin_accepted_when_set(self):
        """EvidenceItem.origin accepts a gap resolution string."""
        item = EvidenceItem(
            item_id="R-C2",
            claim="Gap-filled claim.",
            source="research",
            origin="gap_resolution_query_1",
        )
        assert item.origin == "gap_resolution_query_1"

    def test_origin_roundtrips_json(self):
        """EvidenceItem.origin survives JSON serialization round-trip."""
        item = EvidenceItem(
            item_id="R-C3",
            claim="Another claim.",
            source="research",
            origin="gap_resolution_query_2",
        )
        data = item.model_dump_json()
        restored = EvidenceItem.model_validate_json(data)
        assert restored.origin == "gap_resolution_query_2"

    def test_origin_none_roundtrips_json(self):
        """EvidenceItem with origin=None serializes and deserializes cleanly."""
        item = EvidenceItem(item_id="D-F1", claim="Decomposed fact.", source="decomposition")
        data = item.model_dump_json()
        restored = EvidenceItem.model_validate_json(data)
        assert restored.origin is None

    def test_existing_items_without_origin_field_deserialize_ok(self):
        """Old JSON without 'origin' field deserializes without error (backward compat)."""
        # Simulate old JSON that has no origin field
        old_json = (
            '{"item_id": "R-C1", "claim": "Old claim.", "source": "research", '
            '"source_ids": [], "category": "fact", "confidence": "Medium", '
            '"entities": [], "verified": false, "selected": true, "provider_name": null, '
            '"source_urls": []}'
        )
        item = EvidenceItem.model_validate_json(old_json)
        assert item.origin is None
        assert item.claim == "Old claim."


# ---------------------------------------------------------------------------
# GapResolutionSummary model
# ---------------------------------------------------------------------------


class TestGapResolutionSummary:
    def test_minimal_construction(self):
        """GapResolutionSummary can be constructed with just ran=False."""
        summary = GapResolutionSummary(ran=False)
        assert summary.ran is False
        assert summary.original_gaps == []
        assert summary.queries_run == 0
        assert summary.claims_added == 0
        assert summary.sources_added == 0

    def test_full_construction(self):
        """GapResolutionSummary accepts all fields."""
        summary = GapResolutionSummary(
            ran=True,
            original_gaps=["Gap A", "Gap B"],
            queries_run=2,
            claims_added=5,
            sources_added=3,
        )
        assert summary.ran is True
        assert len(summary.original_gaps) == 2
        assert summary.queries_run == 2
        assert summary.claims_added == 5
        assert summary.sources_added == 3

    def test_roundtrip_json(self):
        """GapResolutionSummary survives JSON round-trip."""
        summary = GapResolutionSummary(
            ran=True,
            original_gaps=["Missing data on X"],
            queries_run=1,
            claims_added=3,
            sources_added=2,
        )
        data = summary.model_dump_json()
        restored = GapResolutionSummary.model_validate_json(data)
        assert restored.ran is True
        assert restored.original_gaps == ["Missing data on X"]
        assert restored.queries_run == 1

    def test_ran_false_no_claims(self):
        """GapResolutionSummary with ran=False and zero counts is valid."""
        summary = GapResolutionSummary(ran=False, queries_run=0, claims_added=0, sources_added=0)
        assert summary.ran is False


# ---------------------------------------------------------------------------
# EvidencePool.gap_resolution field
# ---------------------------------------------------------------------------


class TestEvidencePoolGapResolutionField:
    def test_gap_resolution_defaults_to_none(self):
        """EvidencePool.gap_resolution is None by default."""
        pool = EvidencePool(session_id="abc123", question="What happened?")
        assert pool.gap_resolution is None

    def test_gap_resolution_accepted_when_set(self):
        """EvidencePool accepts a GapResolutionSummary."""
        summary = GapResolutionSummary(ran=True, queries_run=1, claims_added=2, sources_added=1)
        pool = EvidencePool(
            session_id="abc123",
            question="What happened?",
            gap_resolution=summary,
        )
        assert pool.gap_resolution is not None
        assert pool.gap_resolution.ran is True
        assert pool.gap_resolution.claims_added == 2

    def test_gap_resolution_roundtrips_json(self):
        """EvidencePool with gap_resolution survives JSON round-trip."""
        summary = GapResolutionSummary(
            ran=True,
            original_gaps=["Gap 1"],
            queries_run=1,
            claims_added=4,
            sources_added=2,
        )
        pool = EvidencePool(
            session_id="abc123",
            question="Test?",
            gap_resolution=summary,
        )
        data = pool.model_dump_json()
        restored = EvidencePool.model_validate_json(data)
        assert restored.gap_resolution is not None
        assert restored.gap_resolution.ran is True
        assert restored.gap_resolution.claims_added == 4

    def test_pool_without_gap_resolution_roundtrips_json(self):
        """Old EvidencePool JSON without gap_resolution field deserializes OK (backward compat)."""
        old_json = (
            '{"session_id": "abc", "question": "Old question", "items": [], '
            '"sources": [], "gaps": [], "provider_summary": "", "status": "ready", "error": null}'
        )
        pool = EvidencePool.model_validate_json(old_json)
        assert pool.gap_resolution is None
        assert pool.question == "Old question"


# ---------------------------------------------------------------------------
# _build_items_from_research_result() — origin propagation
# ---------------------------------------------------------------------------


class TestBuildItemsFromResearchResultOriginPropagation:
    """Test that _build_items_from_research_result propagates claim.origin to EvidenceItem.origin."""

    def _make_research_result(self, claims_data: list[dict]) -> object:
        """Build a minimal duck-typed ResearchResult-like object for testing."""
        from types import SimpleNamespace

        claims = []
        for i, d in enumerate(claims_data, start=1):
            claim = SimpleNamespace(
                claim=d.get("claim", f"Claim {i}"),
                source_ids=d.get("source_ids", []),
                category=d.get("category", "fact"),
                confidence=d.get("confidence", "Medium"),
                verified=d.get("verified", False),
                origin=d.get("origin", None),
            )
            claims.append(claim)

        return SimpleNamespace(
            claims=claims,
            sources=[],
            research_provider="test_provider",
            gaps_identified=[],
        )

    def test_origin_none_when_claim_has_no_origin(self):
        """When claim.origin is None, EvidenceItem.origin is None."""
        from sat.evidence.gatherer import _build_items_from_research_result

        research_result = self._make_research_result([
            {"claim": "Standard research claim.", "origin": None},
        ])
        items = _build_items_from_research_result(research_result)
        assert len(items) == 1
        assert items[0].origin is None

    def test_origin_propagated_from_gap_resolution_claim(self):
        """When claim.origin='gap_resolution_query_1', EvidenceItem.origin is set."""
        from sat.evidence.gatherer import _build_items_from_research_result

        research_result = self._make_research_result([
            {"claim": "Gap-filled claim A.", "origin": "gap_resolution_query_1"},
            {"claim": "Gap-filled claim B.", "origin": "gap_resolution_query_2"},
        ])
        items = _build_items_from_research_result(research_result)
        assert len(items) == 2
        assert items[0].origin == "gap_resolution_query_1"
        assert items[1].origin == "gap_resolution_query_2"

    def test_mixed_origin_and_none(self):
        """Mix of standard and gap-resolution claims propagates correctly."""
        from sat.evidence.gatherer import _build_items_from_research_result

        research_result = self._make_research_result([
            {"claim": "Standard claim.", "origin": None},
            {"claim": "Gap claim.", "origin": "gap_resolution_query_1"},
            {"claim": "Another standard.", "origin": None},
        ])
        items = _build_items_from_research_result(research_result)
        assert items[0].origin is None
        assert items[1].origin == "gap_resolution_query_1"
        assert items[2].origin is None

    def test_claim_without_origin_attribute_defaults_none(self):
        """If claim object has no origin attribute at all, EvidenceItem.origin is None."""
        from sat.evidence.gatherer import _build_items_from_research_result

        # Create a claim that has no origin attribute
        from types import SimpleNamespace
        claim_no_origin = SimpleNamespace(
            claim="No origin attr claim.",
            source_ids=[],
            category="fact",
            confidence="High",
            verified=False,
            # Deliberately omit 'origin' attribute
        )
        research_result = SimpleNamespace(
            claims=[claim_no_origin],
            sources=[],
            research_provider="test",
            gaps_identified=[],
        )
        items = _build_items_from_research_result(research_result)
        assert len(items) == 1
        assert items[0].origin is None


# ---------------------------------------------------------------------------
# Backward compatibility: EvidencePool round-trip with additional fields
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_evidence_pool_with_all_new_fields_validates(self):
        """EvidencePool with gap_resolution + items with origin validates cleanly."""
        item = EvidenceItem(
            item_id="R-C1",
            claim="Some claim.",
            source="research",
            origin="gap_resolution_query_1",
        )
        summary = GapResolutionSummary(
            ran=True,
            original_gaps=["Missing data"],
            queries_run=1,
            claims_added=1,
            sources_added=0,
        )
        pool = EvidencePool(
            session_id="sess1",
            question="What happened?",
            items=[item],
            gap_resolution=summary,
        )
        # Round-trip through JSON
        data = pool.model_dump_json()
        restored = EvidencePool.model_validate_json(data)
        assert len(restored.items) == 1
        assert restored.items[0].origin == "gap_resolution_query_1"
        assert restored.gap_resolution is not None
        assert restored.gap_resolution.ran is True
