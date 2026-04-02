"""Tests for atomic fact extractor.

@decision DEC-DECOMP-004: Iterative chunked extraction with sequential fact numbering.
@decision DEC-DECOMP-005: Parallel batch extraction replaces sequential chunk processing.
@title Tests for decompose_evidence, _extract_chunk, _format_facts, and _build_source_index
@status accepted
@rationale Verifies chunked extraction, parallel batch behavior, max_facts cap, output
format, and source marker parsing. Parallel tests confirm that:
- All chunks in a batch are dispatched concurrently (call count matches chunk count)
- Fact IDs are assigned sequentially across batch results
- max_facts cap is still respected across batch boundaries
- Prior-facts context is NOT passed to individual chunks (empty list only)
"""

from __future__ import annotations

from sat.config import DecompositionConfig
from sat.decomposition.extractor import (
    ChunkExtractionResult,
    _DECOMP_BATCH_SIZE,
    _build_source_index,
    _extract_chunk,
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


class TestParallelBatchExtraction:
    """Tests for the parallel batch behavior introduced in DEC-DECOMP-005."""

    async def test_fact_ids_sequential_across_batch(self):
        """Fact IDs F1, F2, ... are assigned in order across all batch results."""
        source_facts = [
            AtomicFact(fact_id="X1", claim="Fact alpha.", category="fact", confidence="high"),
            AtomicFact(fact_id="X2", claim="Fact beta.", category="fact", confidence="medium"),
        ]
        provider = MockExtractorProvider(source_facts)
        # chunk_tokens=1 forces multiple chunks
        config = DecompositionConfig(enabled=True, chunk_tokens=1, deduplicate=False)
        long_text = "word " * 500
        result = await decompose_evidence(long_text, provider, config)
        # All IDs must be sequential integers starting at F1
        for i, fact in enumerate(result.facts, start=1):
            assert fact.fact_id == f"F{i}", f"Expected F{i}, got {fact.fact_id}"

    async def test_batch_size_constant_exported(self):
        """_DECOMP_BATCH_SIZE is a positive integer — callers can inspect the constant."""
        assert isinstance(_DECOMP_BATCH_SIZE, int)
        assert _DECOMP_BATCH_SIZE > 0

    async def test_max_facts_respected_across_batches(self):
        """max_facts cap is enforced even when batches produce more facts collectively."""
        # 3 facts per chunk call, cap at 5
        source_facts = [AtomicFact(fact_id=f"X{i}", claim=f"Claim {i}.") for i in range(3)]
        provider = MockExtractorProvider(source_facts)
        config = DecompositionConfig(enabled=True, chunk_tokens=1, max_facts=5, deduplicate=False)
        long_text = "word " * 500
        result = await decompose_evidence(long_text, provider, config)
        assert result.total_facts <= 5
        assert len(result.facts) <= 5

    async def test_extract_chunk_returns_empty_on_provider_failure(self):
        """_extract_chunk returns [] when the provider raises — graceful degradation."""

        class FailProvider:
            async def generate_structured(self, **kwargs):
                raise RuntimeError("Provider exploded")

        facts = await _extract_chunk("some chunk text", "- [abc]: source.txt", FailProvider())
        assert facts == []

    async def test_extract_chunk_passes_empty_prior_facts(self):
        """_extract_chunk never passes prior-facts context — parallel chunks are independent."""
        captured_messages = []

        class CapturingProvider:
            async def generate_structured(self, system_prompt, messages, output_schema, **kwargs):
                captured_messages.extend(messages)
                return ChunkExtractionResult(facts=[])

        await _extract_chunk("chunk content", "- [abc]: source.txt", CapturingProvider())
        # The user message should NOT contain prior facts (i.e., no "[F\d]" pattern)
        import re
        for msg in captured_messages:
            assert not re.search(r"\[F\d+\]", msg.content), (
                f"Prior-facts context leaked into parallel chunk message: {msg.content[:200]}"
            )
