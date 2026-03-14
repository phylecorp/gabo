"""Tests for ingestion result models.

@decision DEC-INGEST-001: Docling for multimodal parsing.
@title Tests for ParsedDocument and IngestionResult models
@status accepted
@rationale Verifies model construction, defaults, serialization round-trips, and
JSON schema generation for the ingestion result models.
"""

from __future__ import annotations

from sat.models.ingestion import IngestionResult, ParsedDocument


class TestParsedDocument:
    def test_defaults(self):
        doc = ParsedDocument(
            source_id="abc12345", source_name="test.txt", source_type="text", markdown="hello"
        )
        assert doc.tables == []
        assert doc.metadata == {}
        assert doc.parse_warnings == []

    def test_construction_with_all_fields(self):
        doc = ParsedDocument(
            source_id="abc12345",
            source_name="report.pdf",
            source_type="pdf",
            markdown="# Report\n\nContent here.",
            tables=["| col1 | col2 |\n|------|------|\n| a    | b    |"],
            metadata={"page_count": 5},
            parse_warnings=["OCR used"],
        )
        assert doc.source_id == "abc12345"
        assert doc.source_type == "pdf"
        assert len(doc.tables) == 1
        assert doc.metadata["page_count"] == 5
        assert "OCR used" in doc.parse_warnings

    def test_serialization_roundtrip(self):
        doc = ParsedDocument(
            source_id="ff001122",
            source_name="data.html",
            source_type="html",
            markdown="<content>",
            tables=["| a | b |"],
            metadata={"url": "https://example.com"},
            parse_warnings=["slow fetch"],
        )
        data = doc.model_dump()
        restored = ParsedDocument(**data)
        assert restored.source_id == doc.source_id
        assert restored.markdown == doc.markdown
        assert restored.tables == doc.tables

    def test_json_schema_generation(self):
        schema = ParsedDocument.model_json_schema()
        assert "source_id" in schema["properties"]
        assert "markdown" in schema["properties"]
        assert "tables" in schema["properties"]


class TestIngestionResult:
    def test_defaults(self):
        result = IngestionResult()
        assert result.technique_id == "ingestion"
        assert result.technique_name == "Evidence Ingestion"
        assert result.summary == ""
        assert result.documents == []
        assert result.combined_markdown == ""
        assert result.source_manifest == []
        assert result.total_estimated_tokens == 0
        assert result.warnings == []

    def test_construction_with_documents(self):
        doc = ParsedDocument(
            source_id="a1b2c3d4", source_name="f.txt", source_type="text", markdown="evidence"
        )
        result = IngestionResult(
            documents=[doc],
            combined_markdown="evidence",
            total_estimated_tokens=100,
            summary="Ingested 1 source",
        )
        assert len(result.documents) == 1
        assert result.total_estimated_tokens == 100

    def test_serialization_roundtrip(self):
        doc = ParsedDocument(
            source_id="a1b2c3d4", source_name="f.txt", source_type="text", markdown="hi"
        )
        result = IngestionResult(
            documents=[doc],
            combined_markdown="hi",
            source_manifest=[{"name": "f.txt", "type": "text"}],
            total_estimated_tokens=5,
            warnings=["slow"],
            summary="1 doc",
        )
        data = result.model_dump()
        restored = IngestionResult(**data)
        assert restored.technique_id == "ingestion"
        assert len(restored.documents) == 1
        assert restored.documents[0].source_id == "a1b2c3d4"

    def test_json_schema_generation(self):
        schema = IngestionResult.model_json_schema()
        assert "documents" in schema["properties"]
        assert "combined_markdown" in schema["properties"]
        assert "source_manifest" in schema["properties"]
