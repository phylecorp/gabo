"""Integration tests for the evidence preprocessor.

@decision DEC-TEST-PREPROC-004: Integration tests verify full preprocessing pipeline.
@title Preprocessor integration tests with MockProvider
@status accepted
@rationale Tests verify the orchestrator correctly routes evidence through
detect -> measure -> reduce -> format, using MockProvider to avoid real API calls.
Covers passthrough (plain text under budget), format conversion (CSV under budget),
and map-reduce path verification.
"""

from __future__ import annotations

import pytest

from sat.config import PreprocessingConfig
from sat.models.preprocessing import EvidenceFormat
from sat.preprocessing.preprocessor import (
    _extract_sources,
    preprocess_evidence,
)
from tests.helpers import MockProvider


class TestExtractSources:
    def test_finds_sources(self):
        text = "--- Source: report.txt ---\ncontent\n\n--- Source: notes/meeting.md ---\nmore"
        assert _extract_sources(text) == ["report.txt", "notes/meeting.md"]

    def test_no_sources(self):
        assert _extract_sources("just plain text") == []


@pytest.mark.asyncio
class TestPreprocessEvidence:
    async def test_passthrough_plain_text_under_budget(self):
        """Plain text under budget should pass through without LLM calls."""
        mock = MockProvider(text_response="should not be called")
        config = PreprocessingConfig(enabled=True)

        result = await preprocess_evidence(
            evidence="This is simple plain text evidence.",
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        assert result.original_format == EvidenceFormat.PLAIN_TEXT
        assert result.reduction_applied == "none"
        assert "This is simple plain text evidence." in result.formatted_evidence
        assert result.technique_id == "preprocessing"
        assert result.technique_name == "Evidence Preprocessing"
        assert len(result.warnings) == 0

    async def test_csv_format_conversion(self):
        """CSV under budget should get format conversion."""
        mock = MockProvider(text_response="Narrative summary of the CSV data with 3 rows.")
        config = PreprocessingConfig(enabled=True)

        csv_text = "name,age,city\nAlice,30,NYC\nBob,25,LA\nCharlie,35,Chicago"
        result = await preprocess_evidence(
            evidence=csv_text,
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        assert result.original_format == EvidenceFormat.CSV
        assert result.reduction_applied == "format_conversion"
        assert "Narrative summary" in result.formatted_evidence

    async def test_json_format_conversion(self):
        """JSON under budget should get format conversion."""
        mock = MockProvider(text_response="JSON data analysis summary.")
        config = PreprocessingConfig(enabled=True)

        json_text = '{"users": [{"name": "Alice"}, {"name": "Bob"}]}'
        result = await preprocess_evidence(
            evidence=json_text,
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        assert result.original_format == EvidenceFormat.JSON
        assert result.reduction_applied == "format_conversion"

    async def test_log_format_conversion(self):
        """Log file under budget should get format conversion."""
        mock = MockProvider(text_response="Log analysis: 5 events over 4 seconds.")
        config = PreprocessingConfig(enabled=True)

        log_text = """2024-01-15T10:30:00Z INFO Starting application
2024-01-15T10:30:01Z DEBUG Loading config
2024-01-15T10:30:02Z WARN Connection slow
2024-01-15T10:30:03Z ERROR Failed to connect
2024-01-15T10:30:04Z INFO Retrying..."""
        result = await preprocess_evidence(
            evidence=log_text,
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        assert result.original_format == EvidenceFormat.LOG_FILE
        assert result.reduction_applied == "format_conversion"

    async def test_multi_file_preserves_sources(self):
        """Multi-file evidence should extract source names."""
        mock = MockProvider(text_response="should not be called")
        config = PreprocessingConfig(enabled=True)

        text = (
            "--- Source: report.txt ---\nContent here.\n\n--- Source: data.csv ---\nMore content."
        )
        result = await preprocess_evidence(
            evidence=text,
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        assert result.original_format == EvidenceFormat.MULTI_FILE
        assert result.sources_preserved == ["report.txt", "data.csv"]
        # Multi-file under budget is plain text category, so passthrough
        assert result.reduction_applied == "none"

    async def test_force_format_override(self):
        """force_format should override auto-detection."""
        mock = MockProvider(text_response="Forced CSV conversion.")
        config = PreprocessingConfig(enabled=True, force_format="csv")

        # This text would normally detect as plain text
        result = await preprocess_evidence(
            evidence="This is actually CSV data trust me",
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        assert result.original_format == EvidenceFormat.CSV
        assert result.reduction_applied == "format_conversion"

    async def test_provenance_header_added(self):
        """Output should have a provenance header."""
        mock = MockProvider(text_response="should not be called")
        config = PreprocessingConfig(enabled=True)

        result = await preprocess_evidence(
            evidence="Simple text.",
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        assert "[Evidence preprocessed:" in result.formatted_evidence
        assert "format=plain_text" in result.formatted_evidence
        assert "reduction=none" in result.formatted_evidence

    async def test_map_reduce_for_oversized(self):
        """Oversized evidence should trigger map-reduce."""
        mock = MockProvider(text_response="Reduced summary.")
        # Set a very small budget to force map-reduce
        config = PreprocessingConfig(enabled=True, budget_fraction=0.0001, max_chunk_tokens=100)

        # Create text larger than the tiny budget
        big_text = "Important fact. " * 5000  # ~80K chars = ~20K tokens
        result = await preprocess_evidence(
            evidence=big_text,
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        assert result.reduction_applied == "map_reduce"

    async def test_result_has_correct_artifact_fields(self):
        """PreprocessingResult should have all ArtifactResult fields for artifact writing."""
        mock = MockProvider(text_response="should not be called")
        config = PreprocessingConfig(enabled=True)

        result = await preprocess_evidence(
            evidence="Test text.",
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        # ArtifactResult required fields
        assert result.technique_id == "preprocessing"
        assert result.technique_name == "Evidence Preprocessing"
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

    async def test_force_format_invalid_falls_back(self):
        """Invalid force_format should fall back to auto-detect."""
        mock = MockProvider(text_response="should not be called")
        config = PreprocessingConfig(enabled=True, force_format="nonexistent_format")

        result = await preprocess_evidence(
            evidence="Just plain text.",
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        # Should fall back to auto-detect (plain text)
        assert result.original_format == EvidenceFormat.PLAIN_TEXT
        assert result.reduction_applied == "none"

    async def test_provenance_header_includes_sources_for_multi_file(self):
        """Provenance header should list sources for multi-file evidence."""
        mock = MockProvider(text_response="should not be called")
        config = PreprocessingConfig(enabled=True)

        text = "--- Source: a.txt ---\nAAA\n\n--- Source: b.txt ---\nBBB"
        result = await preprocess_evidence(
            evidence=text,
            provider=mock,
            provider_name="anthropic",
            config=config,
        )

        assert "[Sources: a.txt, b.txt]" in result.formatted_evidence
