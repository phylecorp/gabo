"""Tests for atomic fact extractor.

@decision DEC-DECOMP-004: Iterative chunked extraction with sequential fact numbering.
@title Tests for decompose_evidence, _format_facts, and _build_source_index
@status accepted
@rationale Verifies chunked extraction, max_facts cap, output format, and source
marker parsing.
"""

from __future__ import annotations

from sat.config import DecompositionConfig
from sat.decomposition.extractor import (
    ChunkExtractionResult,
    _build_source_index,
    _format_facts,
    decompose_evidence,
)
from sat.models.decomposition import AtomicFact


class MockExtractorProvider:
    """Returns a fixed ChunkExtractionResult on every generate_structured call."""

    def __init__(self, facts: list[AtomicFact]):
        self._facts = facts

    async def generate_structured(self, system_prompt, messages, output_schema, **kwargs):
        if output_schema is ChunkExtractionResult:
            # Return fresh copies so fact_ids can be re-assigned
            return ChunkExtractionResult(facts=[f.model_copy() for f in self._facts])
        # For dedup calls return no duplicates
        from sat.decomposition.deduplicator import DeduplicationResponse

        return DeduplicationResponse(duplicate_groups=[])


class TestBuildSourceIndex:
    def test_no_markers_returns_inline(self):
        index_str, name_to_id = _build_source_index("plain text without markers")
        assert "inline" in index_str
        assert "inline" in name_to_id

    def test_single_marker_parsed(self):
        evidence = "--- Source: report.pdf ---\nContent here."
        index_str, name_to_id = _build_source_index(evidence)
        assert "report.pdf" in index_str
        assert "report.pdf" in name_to_id

    def test_multiple_markers_parsed(self):
        evidence = "--- Source: a.txt ---\nContent A.\n\n--- Source: b.txt ---\nContent B."
        index_str, name_to_id = _build_source_index(evidence)
        assert "a.txt" in name_to_id
        assert "b.txt" in name_to_id

    def test_duplicate_markers_deduped(self):
        evidence = "--- Source: same.txt ---\nPart 1.\n\n--- Source: same.txt ---\nPart 2."
        _, name_to_id = _build_source_index(evidence)
        assert list(name_to_id.keys()).count("same.txt") == 1


class TestFormatFacts:
    def test_header_contains_count(self):
        facts = [
            AtomicFact(fact_id="F1", claim="A is true."),
            AtomicFact(fact_id="F2", claim="B is false."),
        ]
        output = _format_facts(facts, "- [abc]: source.txt")
        assert "[Decomposed Evidence: 2 atomic facts" in output

    def test_facts_listed(self):
        facts = [AtomicFact(fact_id="F1", claim="X occurred.")]
        output = _format_facts(facts, "index")
        assert "[F1]" in output
        assert "X occurred." in output

    def test_source_index_section_present(self):
        output = _format_facts([], "- [abc12345]: doc.pdf")
        assert "## Source Index" in output
        assert "doc.pdf" in output

    def test_entity_index_included(self):
        facts = [
            AtomicFact(fact_id="F1", claim="NATO expanded.", entities=["NATO"]),
        ]
        output = _format_facts(facts, "index")
        assert "## Entity Index" in output
        assert "NATO" in output


class TestDecomposeEvidence:
    async def test_single_chunk_extracts_facts(self):
        source_facts = [
            AtomicFact(fact_id="X1", claim="The economy grew.", category="fact", confidence="high"),
            AtomicFact(fact_id="X2", claim="Inflation fell.", category="fact", confidence="medium"),
        ]
        provider = MockExtractorProvider(source_facts)
        config = DecompositionConfig(enabled=True, deduplicate=False)
        result = await decompose_evidence("Some evidence text.", provider, config)
        assert result.total_facts == 2
        assert result.facts[0].fact_id == "F1"
        assert result.facts[1].fact_id == "F2"
        assert result.chunks_processed == 1

    async def test_max_facts_cap(self):
        source_facts = [AtomicFact(fact_id=f"X{i}", claim=f"Claim {i}.") for i in range(10)]
        provider = MockExtractorProvider(source_facts)
        config = DecompositionConfig(enabled=True, max_facts=3, deduplicate=False)
        result = await decompose_evidence("Evidence.", provider, config)
        assert result.total_facts <= 3
        assert len(result.facts) <= 3

    async def test_formatted_evidence_has_marker(self):
        source_facts = [AtomicFact(fact_id="X1", claim="Fact one.")]
        provider = MockExtractorProvider(source_facts)
        config = DecompositionConfig(enabled=True, deduplicate=False)
        result = await decompose_evidence("Evidence text.", provider, config)
        assert "[Decomposed Evidence:" in result.formatted_evidence

    async def test_chunks_processed_counted(self):
        provider = MockExtractorProvider([])
        config = DecompositionConfig(enabled=True, chunk_tokens=1, deduplicate=False)
        # Very small chunk_tokens will produce multiple chunks
        long_text = "word " * 2000
        result = await decompose_evidence(long_text, provider, config)
        assert result.chunks_processed >= 1
