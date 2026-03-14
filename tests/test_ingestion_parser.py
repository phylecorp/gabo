"""Tests for ingestion document parser.

@decision DEC-INGEST-002: Docling-based document parsing with graceful fallback.
@title Tests for parse_document, parse_text, and helper functions
@status accepted
@rationale Verifies that text files are read correctly, non-text files warn when
Docling is not installed, source IDs are deterministic, and type detection works.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from sat.ingestion.parser import (
    _detect_source_type,
    _generate_source_id,
    parse_document,
    parse_text,
)

# @mock-exempt: DOCLING_AVAILABLE is patched to simulate the optional external
# library being absent. This is the only way to test the fallback path without
# actually uninstalling docling; it mocks an external dependency boundary, not
# internal application logic.


class TestGenerateSourceId:
    def test_returns_8_chars(self):
        sid = _generate_source_id("hello.txt")
        assert len(sid) == 8

    def test_deterministic(self):
        assert _generate_source_id("foo.pdf") == _generate_source_id("foo.pdf")

    def test_different_names_give_different_ids(self):
        assert _generate_source_id("a.txt") != _generate_source_id("b.txt")

    def test_hex_characters_only(self):
        sid = _generate_source_id("report.docx")
        assert all(c in "0123456789abcdef" for c in sid)


class TestDetectSourceType:
    def test_pdf(self):
        assert _detect_source_type(Path("doc.pdf")) == "pdf"

    def test_docx(self):
        assert _detect_source_type(Path("doc.docx")) == "docx"

    def test_pptx(self):
        assert _detect_source_type(Path("slide.pptx")) == "pptx"

    def test_xlsx(self):
        assert _detect_source_type(Path("data.xlsx")) == "xlsx"

    def test_html(self):
        assert _detect_source_type(Path("page.html")) == "html"
        assert _detect_source_type(Path("page.htm")) == "html"

    def test_image(self):
        assert _detect_source_type(Path("photo.png")) == "image"
        assert _detect_source_type(Path("photo.jpg")) == "image"
        assert _detect_source_type(Path("photo.jpeg")) == "image"

    def test_audio(self):
        assert _detect_source_type(Path("sound.wav")) == "audio"
        assert _detect_source_type(Path("sound.mp3")) == "audio"

    def test_text_default(self):
        assert _detect_source_type(Path("readme.txt")) == "text"
        assert _detect_source_type(Path("notes.md")) == "text"
        assert _detect_source_type(Path("unknown.xyz")) == "text"


class TestParseText:
    def test_basic(self):
        doc = parse_text("Hello world", name="test", index=0)
        assert doc.markdown == "Hello world"
        assert doc.source_name == "test"
        assert doc.source_type == "text"
        assert len(doc.source_id) == 8

    def test_default_name(self):
        doc = parse_text("data")
        assert doc.source_name == "inline"

    def test_different_indices_give_different_ids(self):
        doc0 = parse_text("same text", name="src", index=0)
        doc1 = parse_text("same text", name="src", index=1)
        assert doc0.source_id != doc1.source_id


class TestParseDocument:
    async def test_parse_text_file(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("This is test evidence.")
            tmp_path = Path(f.name)
        try:
            doc = await parse_document(tmp_path)
            assert doc.markdown == "This is test evidence."
            assert doc.source_type == "text"
            assert doc.parse_warnings == []
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_parse_non_text_no_docling(self):
        """Without Docling, non-text files are read as raw text with a warning."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", mode="wb", delete=False) as f:
            f.write(b"%PDF-1.4 fake pdf content")
            tmp_path = Path(f.name)
        try:
            with patch("sat.ingestion.parser.DOCLING_AVAILABLE", False):
                doc = await parse_document(tmp_path)
            assert doc.source_type == "pdf"
            assert any("Docling not installed" in w for w in doc.parse_warnings)
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_parse_txt_file_no_docling_no_warning(self):
        """Plain text files never need Docling — no warning even if unavailable."""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("plain text")
            tmp_path = Path(f.name)
        try:
            with patch("sat.ingestion.parser.DOCLING_AVAILABLE", False):
                doc = await parse_document(tmp_path)
            assert doc.markdown == "plain text"
            assert doc.parse_warnings == []
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_parse_docling_table_export_uses_doc_arg(self):
        """Docling table export passes doc= argument to avoid deprecation warning."""
        from unittest.mock import MagicMock, patch

        mock_table = MagicMock()
        mock_table.export_to_markdown = MagicMock(return_value="| col | val |")

        mock_document = MagicMock()
        mock_document.export_to_markdown.return_value = "# Doc"
        mock_document.tables = [mock_table]
        mock_document.pages = []

        mock_result = MagicMock()
        mock_result.document = mock_document

        mock_converter = MagicMock()
        mock_converter.convert.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".pdf", mode="wb", delete=False) as f:
            f.write(b"%PDF-1.4 fake")
            tmp_path = Path(f.name)
        try:
            with patch("sat.ingestion.parser.DOCLING_AVAILABLE", True), patch(
                "sat.ingestion.parser._get_converter", return_value=mock_converter
            ):
                await parse_document(tmp_path)
            # Verify export_to_markdown was called with doc= keyword arg (fixes deprecation)
            mock_table.export_to_markdown.assert_called_once_with(doc=mock_document)
        finally:
            tmp_path.unlink(missing_ok=True)

