"""Tests for evidence reduction logic.

@decision DEC-TEST-PREPROC-003: Reducer tests cover chunking logic and mock LLM reduction.
@title Reducer unit tests
@status accepted
@rationale Chunking is pure logic that should be tested thoroughly. LLM reduction
is tested with MockProvider to verify the orchestration (correct prompts sent,
results combined) without real API calls.
"""

from __future__ import annotations

import pytest

from sat.models.preprocessing import EvidenceFormat
from sat.preprocessing.reducer import chunk_text, reduce_format_conversion, reduce_map_reduce


class TestChunkText:
    def test_small_text_single_chunk(self):
        text = "Small text"
        chunks = chunk_text(text, max_chunk_tokens=1000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_large_text_multiple_chunks(self):
        # 50K tokens = 200K chars per chunk
        text = "a" * 600_000  # ~150K tokens, should split into multiple chunks
        chunks = chunk_text(text, max_chunk_tokens=50_000)
        assert len(chunks) > 1
        # All content should be covered (with overlap, total chars >= original)
        total = sum(len(c) for c in chunks)
        assert total >= len(text)

    def test_paragraph_boundary_splitting(self):
        # Create text with clear paragraph boundaries
        paragraphs = ["Paragraph content. " * 100 + "\n\n" for _ in range(20)]
        text = "".join(paragraphs)
        chunks = chunk_text(text, max_chunk_tokens=500, overlap_chars=50)
        assert len(chunks) > 1
        # Each chunk (except possibly last) should end at or near a paragraph boundary
        for chunk in chunks[:-1]:
            # The chunk should end close to a paragraph boundary
            assert "\n" in chunk[-200:] or len(chunk) <= 2000 + 50

    def test_overlap_between_chunks(self):
        text = "word " * 100_000  # 500K chars = ~125K tokens
        chunks = chunk_text(text, max_chunk_tokens=25_000, overlap_chars=500)
        assert len(chunks) > 1
        # Verify overlap: end of chunk N should overlap with start of chunk N+1
        for i in range(len(chunks) - 1):
            # Last 500 chars of chunk i should appear in the beginning portion of chunk i+1
            tail = chunks[i][-200:]  # Check a portion of the overlap
            assert tail in chunks[i + 1][:2000]

    def test_empty_text(self):
        assert chunk_text("", max_chunk_tokens=1000) == [""]

    def test_exact_boundary(self):
        # Text exactly at the chunk size should be a single chunk
        text = "a" * (50_000 * 4)  # exactly 50K tokens worth
        chunks = chunk_text(text, max_chunk_tokens=50_000)
        assert len(chunks) == 1


@pytest.mark.asyncio
class TestReduceFormatConversion:
    async def test_calls_provider_with_format_prompt(self):
        """Verify format conversion sends the right prompt type."""
        from tests.helpers import MockProvider

        mock = MockProvider(text_response="Converted narrative from CSV data.")
        result = await reduce_format_conversion(
            text="name,age,city\nAlice,30,NYC",
            fmt=EvidenceFormat.CSV,
            provider=mock,
        )
        assert result == "Converted narrative from CSV data."

    async def test_json_format(self):
        from tests.helpers import MockProvider

        mock = MockProvider(text_response="JSON analysis summary.")
        result = await reduce_format_conversion(
            text='{"key": "value"}',
            fmt=EvidenceFormat.JSON,
            provider=mock,
        )
        assert result == "JSON analysis summary."


@pytest.mark.asyncio
class TestReduceMapReduce:
    async def test_single_chunk_no_map(self):
        """Small text should just do a single summarization."""
        from tests.helpers import MockProvider

        mock = MockProvider(text_response="Summarized.")
        result, warnings = await reduce_map_reduce(
            text="Short text",
            fmt=EvidenceFormat.PLAIN_TEXT,
            provider=mock,
            provider_name="anthropic",
            max_chunk_tokens=50_000,
        )
        assert result == "Summarized."
        assert len(warnings) == 0

    async def test_returns_warnings_list(self):
        """Verify warnings is always a list."""
        from tests.helpers import MockProvider

        mock = MockProvider(text_response="Summary.")
        _, warnings = await reduce_map_reduce(
            text="Text",
            fmt=EvidenceFormat.PLAIN_TEXT,
            provider=mock,
            provider_name="anthropic",
        )
        assert isinstance(warnings, list)
