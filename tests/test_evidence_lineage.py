"""Tests for evidence lineage tracking.

@decision DEC-EVIDENCE-005
@title Evidence lineage chain with content hashes and transformation metadata
@status accepted
@rationale Evidence undergoes up to 5 transformations (ingestion, decomposition,
preprocessing, research merge). Without lineage tracking, there's no record of what
each stage produced. These tests verify that the lineage chain records content hashes,
character counts, and stage-specific metadata at each step, and persists correctly as
evidence-lineage.json for post-hoc debugging and auditability.

Covers the EvidenceLineage and LineageEntry models including recording,
content hashing, metadata, ordering, and disk persistence.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sat.evidence.lineage import EvidenceLineage, LineageEntry


class TestLineageEntry:
    """Tests for the LineageEntry pydantic model."""

    def test_required_fields_present(self):
        entry = LineageEntry(
            stage="initial",
            content_hash="abc123",
            char_count=100,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert entry.stage == "initial"
        assert entry.content_hash == "abc123"
        assert entry.char_count == 100
        assert entry.metadata == {}

    def test_metadata_default_empty(self):
        entry = LineageEntry(
            stage="x",
            content_hash="h",
            char_count=0,
            timestamp="t",
        )
        assert entry.metadata == {}


class TestEvidenceLineage:
    """Tests for EvidenceLineage model."""

    def test_record_initial_state(self):
        lineage = EvidenceLineage(run_id="test-123")
        lineage.record("initial", "Some evidence text")
        assert len(lineage.entries) == 1
        entry = lineage.entries[0]
        assert entry.stage == "initial"
        assert entry.char_count == len("Some evidence text")
        assert entry.content_hash  # non-empty
        assert entry.timestamp  # non-empty

    def test_record_none_evidence(self):
        lineage = EvidenceLineage(run_id="test-123")
        lineage.record("initial", None)
        assert lineage.entries[0].char_count == 0
        assert lineage.entries[0].content_hash  # hash of empty string, non-empty

    def test_record_with_metadata(self):
        lineage = EvidenceLineage(run_id="test-123")
        lineage.record("decomposition", "facts here", total_facts=42, chunks=3)
        entry = lineage.entries[0]
        assert entry.metadata["total_facts"] == 42
        assert entry.metadata["chunks"] == 3

    def test_multiple_entries_preserve_order(self):
        lineage = EvidenceLineage(run_id="test-123")
        lineage.record("initial", "raw text")
        lineage.record("ingestion", "ingested text")
        lineage.record("decomposition", "decomposed text")
        assert len(lineage.entries) == 3
        assert [e.stage for e in lineage.entries] == ["initial", "ingestion", "decomposition"]

    def test_content_hash_changes_with_content(self):
        lineage = EvidenceLineage(run_id="test-123")
        lineage.record("initial", "version 1")
        lineage.record("decomposition", "version 2")
        assert lineage.entries[0].content_hash != lineage.entries[1].content_hash

    def test_content_hash_stable_for_same_content(self):
        l1 = EvidenceLineage(run_id="a")
        l2 = EvidenceLineage(run_id="b")
        l1.record("initial", "same text")
        l2.record("initial", "same text")
        assert l1.entries[0].content_hash == l2.entries[0].content_hash

    def test_content_hash_is_16_hex_chars(self):
        lineage = EvidenceLineage(run_id="test")
        lineage.record("initial", "some text")
        # We truncate to 16 chars of SHA-256 hex
        assert len(lineage.entries[0].content_hash) == 16
        assert all(c in "0123456789abcdef" for c in lineage.entries[0].content_hash)

    def test_char_count_matches_text_length(self):
        text = "Hello, world! " * 100
        lineage = EvidenceLineage(run_id="test")
        lineage.record("initial", text)
        assert lineage.entries[0].char_count == len(text)

    def test_empty_lineage_has_no_entries(self):
        lineage = EvidenceLineage(run_id="test")
        assert lineage.entries == []

    def test_write_to_disk(self):
        lineage = EvidenceLineage(run_id="test-123")
        lineage.record("initial", "evidence")
        lineage.record("decomposition", "decomposed", facts=10)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = lineage.write(Path(tmpdir))
            assert path.exists()
            assert path.name == "evidence-lineage.json"
            data = json.loads(path.read_text())
            assert data["run_id"] == "test-123"
            assert len(data["entries"]) == 2
            assert data["entries"][0]["stage"] == "initial"
            assert data["entries"][1]["metadata"]["facts"] == 10

    def test_write_creates_directory(self):
        lineage = EvidenceLineage(run_id="test-123")
        lineage.record("initial", None)

        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "nested" / "dir"
            path = lineage.write(nested)
            assert path.exists()

    def test_write_returns_path_to_json(self):
        lineage = EvidenceLineage(run_id="abc")
        lineage.record("initial", "text")
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            result = lineage.write(out_dir)
            assert result == out_dir / "evidence-lineage.json"

    def test_write_json_is_valid_and_readable(self):
        lineage = EvidenceLineage(run_id="xyz")
        lineage.record("initial", "raw")
        lineage.record("ingestion", "ingested", documents=3, estimated_tokens=5000)
        lineage.record("preprocessing", "preprocessed", original_format="markdown", reduction_applied="none")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = lineage.write(Path(tmpdir))
            data = json.loads(path.read_text(encoding="utf-8"))

        assert data["run_id"] == "xyz"
        assert len(data["entries"]) == 3
        # Check ingestion entry
        ing = data["entries"][1]
        assert ing["stage"] == "ingestion"
        assert ing["metadata"]["documents"] == 3
        assert ing["metadata"]["estimated_tokens"] == 5000
        # Check preprocessing entry
        pre = data["entries"][2]
        assert pre["stage"] == "preprocessing"
        assert pre["metadata"]["original_format"] == "markdown"

    def test_metadata_accepts_mixed_types(self):
        """Metadata supports str, int, float, bool values."""
        lineage = EvidenceLineage(run_id="test")
        lineage.record(
            "preprocessing",
            "text",
            label="value",
            count=42,
            ratio=0.95,
            enabled=True,
        )
        m = lineage.entries[0].metadata
        assert m["label"] == "value"
        assert m["count"] == 42
        assert abs(m["ratio"] - 0.95) < 1e-9
        assert m["enabled"] is True

    def test_pipeline_stages_all_recordable(self):
        """Verify all 5 pipeline stages can be recorded in sequence."""
        lineage = EvidenceLineage(run_id="pipe-test")
        lineage.record("initial", "raw user evidence")
        lineage.record("ingestion", "ingested content", documents=2)
        lineage.record("decomposition", "fact 1\nfact 2", total_facts=10, chunks_processed=2, duplicates_removed=0)
        lineage.record("preprocessing", "preprocessed", original_format="plaintext", reduction_applied="none", original_tokens=500, output_tokens=500)
        lineage.record("research_merge", "evidence + research", claims=5, sources=3)

        stages = [e.stage for e in lineage.entries]
        assert stages == ["initial", "ingestion", "decomposition", "preprocessing", "research_merge"]
