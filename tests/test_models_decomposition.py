"""Tests for decomposition result models.

@decision DEC-DECOMP-001: LLM-based iterative extraction of atomic claims.
@title Tests for AtomicFact and DecompositionResult models
@status accepted
@rationale Verifies model construction, defaults, serialization round-trips, and
JSON schema generation for the decomposition result models.
"""

from __future__ import annotations

from sat.models.decomposition import AtomicFact, DecompositionResult


class TestAtomicFact:
    def test_defaults(self):
        fact = AtomicFact(fact_id="F1", claim="The sky is blue.")
        assert fact.source_ids == []
        assert fact.category == "fact"
        assert fact.confidence == "medium"
        assert fact.temporal_marker is None
        assert fact.entities == []

    def test_construction_with_all_fields(self):
        fact = AtomicFact(
            fact_id="F3",
            claim="Inflation rose 3% in Q1 2024.",
            source_ids=["abc123"],
            category="fact",
            confidence="high",
            temporal_marker="Q1 2024",
            entities=["inflation"],
        )
        assert fact.fact_id == "F3"
        assert fact.temporal_marker == "Q1 2024"
        assert "inflation" in fact.entities

    def test_serialization_roundtrip(self):
        fact = AtomicFact(
            fact_id="F5",
            claim="Policy X will fail.",
            source_ids=["src1", "src2"],
            category="prediction",
            confidence="low",
        )
        data = fact.model_dump()
        restored = AtomicFact(**data)
        assert restored.fact_id == fact.fact_id
        assert restored.claim == fact.claim
        assert restored.source_ids == fact.source_ids

    def test_json_schema_generation(self):
        schema = AtomicFact.model_json_schema()
        assert "fact_id" in schema["properties"]
        assert "claim" in schema["properties"]
        assert "category" in schema["properties"]


class TestDecompositionResult:
    def test_defaults(self):
        result = DecompositionResult()
        assert result.technique_id == "decomposition"
        assert result.technique_name == "Atomic Fact Decomposition"
        assert result.summary == ""
        assert result.facts == []
        assert result.total_facts == 0
        assert result.total_sources == 0
        assert result.chunks_processed == 0
        assert result.duplicates_removed == 0
        assert result.formatted_evidence == ""
        assert result.warnings == []

    def test_construction_with_facts(self):
        facts = [
            AtomicFact(fact_id="F1", claim="A is true."),
            AtomicFact(fact_id="F2", claim="B is false."),
        ]
        result = DecompositionResult(
            facts=facts,
            total_facts=2,
            total_sources=1,
            chunks_processed=1,
            duplicates_removed=0,
            formatted_evidence="[Decomposed Evidence: 2 atomic facts]\n\n[F1] A is true.",
            summary="Extracted 2 atomic facts from 1 chunk(s)",
        )
        assert len(result.facts) == 2
        assert result.total_facts == 2
        assert result.chunks_processed == 1

    def test_serialization_roundtrip(self):
        fact = AtomicFact(fact_id="F1", claim="X occurred.")
        result = DecompositionResult(
            facts=[fact],
            total_facts=1,
            total_sources=1,
            chunks_processed=1,
            formatted_evidence="[F1] X occurred.",
            summary="1 fact",
        )
        data = result.model_dump()
        restored = DecompositionResult(**data)
        assert restored.technique_id == "decomposition"
        assert len(restored.facts) == 1
        assert restored.facts[0].fact_id == "F1"

    def test_json_schema_generation(self):
        schema = DecompositionResult.model_json_schema()
        assert "facts" in schema["properties"]
        assert "total_facts" in schema["properties"]
        assert "formatted_evidence" in schema["properties"]
