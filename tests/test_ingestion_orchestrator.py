"""Tests for the ingestion orchestrator.

@decision DEC-INGEST-004: Single entry point classifies and routes sources.
@title Tests for ingest_evidence orchestration logic
@status accepted
@rationale Verifies that files, inline evidence, and mixed sources are correctly
assembled into an IngestionResult with proper source markers and warnings for
missing paths.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sat.config import IngestionConfig
from sat.ingestion.orchestrator import ingest_evidence


class TestIngestEvidence:
    async def test_ingest_single_file(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("File evidence content.")
            tmp_path = Path(f.name)
        try:
            result = await ingest_evidence([str(tmp_path)])
            assert len(result.documents) == 1
            assert result.documents[0].markdown == "File evidence content."
            assert result.warnings == []
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_ingest_inline_only(self):
        result = await ingest_evidence([], inline_evidence="Inline text here.")
        assert len(result.documents) == 1
        assert result.documents[0].markdown == "Inline text here."
        assert result.documents[0].source_name == "inline"

    async def test_ingest_mixed_file_and_inline(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("From file.")
            tmp_path = Path(f.name)
        try:
            result = await ingest_evidence([str(tmp_path)], inline_evidence="From inline.")
            assert len(result.documents) == 2
            # File comes first, inline appended last
            assert result.documents[0].markdown == "From file."
            assert result.documents[1].markdown == "From inline."
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_missing_source_produces_warning(self):
        result = await ingest_evidence(["/nonexistent/path/file.txt"])
        assert len(result.documents) == 0
        assert any("Source not found" in w for w in result.warnings)

    async def test_combined_markdown_has_source_markers(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("Content A.")
            path_a = Path(f.name)
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("Content B.")
            path_b = Path(f.name)
        try:
            result = await ingest_evidence([str(path_a), str(path_b)])
            assert "--- Source:" in result.combined_markdown
            assert "Content A." in result.combined_markdown
            assert "Content B." in result.combined_markdown
        finally:
            path_a.unlink(missing_ok=True)
            path_b.unlink(missing_ok=True)

    async def test_empty_sources_and_no_inline(self):
        result = await ingest_evidence([])
        assert result.documents == []
        assert result.combined_markdown == ""
        assert result.total_estimated_tokens == 0

    async def test_summary_contains_count(self):
        result = await ingest_evidence([], inline_evidence="some text")
        assert "1 source" in result.summary

    async def test_custom_config_respected(self):
        config = IngestionConfig(enabled=True, fetch_timeout=5.0)
        result = await ingest_evidence([], inline_evidence="test", config=config)
        assert len(result.documents) == 1
