"""Document parsing via Docling with fallback to raw text.

@decision DEC-INGEST-002: Ingestion as Phase -1 in the pipeline.
@title Docling-based document parsing with graceful fallback
@status accepted
@rationale Docling provides high-quality parsing for PDFs, DOCX, PPTX, XLSX, HTML,
images (OCR), and audio. When Docling is not installed, files are read as raw text
with a warning. This keeps docling as an optional dependency.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from sat.models.ingestion import ParsedDocument

# Optional Docling import — graceful fallback to raw text if not installed.
try:
    import docling.document_converter as _docling_mod  # noqa: F401

    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

# Lazy singleton — Docling model loading is expensive; create once.
_converter: object | None = None

EXTENSION_TYPE_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".html": "html",
    ".htm": "html",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".bmp": "image",
    ".tiff": "image",
    ".wav": "audio",
    ".mp3": "audio",
    ".ogg": "audio",
    ".flac": "audio",
}


def _get_converter() -> object:
    """Return the shared DocumentConverter, creating it on first call."""
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter

        _converter = DocumentConverter()
    return _converter


def _detect_source_type(path: Path) -> str:
    """Return a type string based on file extension."""
    return EXTENSION_TYPE_MAP.get(path.suffix.lower(), "text")


def _generate_source_id(name: str) -> str:
    """Return an 8-character hex digest for a source name."""
    return hashlib.md5(name.encode()).hexdigest()[:8]


async def parse_document(source: Path) -> ParsedDocument:
    """Parse a local file into a ParsedDocument.

    Uses Docling when available and the file is non-text; falls back to
    reading the file as UTF-8 text with an error-replacement strategy.
    """
    source_type = _detect_source_type(source)
    source_id = _generate_source_id(source.name)

    if not DOCLING_AVAILABLE and source_type != "text":
        # Docling not installed — try reading as raw text
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
            return ParsedDocument(
                source_id=source_id,
                source_name=source.name,
                source_type=source_type,
                markdown=text,
                parse_warnings=["Docling not installed; read as raw text"],
            )
        except Exception as exc:
            return ParsedDocument(
                source_id=source_id,
                source_name=source.name,
                source_type=source_type,
                markdown="",
                parse_warnings=[f"Docling not installed; failed to read file: {exc}"],
            )

    if DOCLING_AVAILABLE and source_type != "text":
        try:
            converter = _get_converter()
            # Docling's converter.convert() is synchronous and CPU-bound
            # (PDF parsing, OCR). Run it in a thread pool executor so it
            # doesn't block the event loop while other concurrent analyses proceed.
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: converter.convert(str(source))  # type: ignore[union-attr]
            )
            markdown = result.document.export_to_markdown()
            tables: list[str] = []
            if hasattr(result.document, "tables"):
                for table in result.document.tables:
                    if hasattr(table, "export_to_markdown"):
                        tables.append(table.export_to_markdown(doc=result.document))
            metadata: dict = {}
            if hasattr(result.document, "pages"):
                metadata["page_count"] = len(result.document.pages)
            return ParsedDocument(
                source_id=source_id,
                source_name=source.name,
                source_type=source_type,
                markdown=markdown,
                tables=tables,
                metadata=metadata,
            )
        except Exception as exc:
            # Fall through to raw-text fallback
            parse_warnings = [f"Docling parsing failed: {exc}; falling back to raw text"]
            try:
                text = source.read_text(encoding="utf-8", errors="replace")
                return ParsedDocument(
                    source_id=source_id,
                    source_name=source.name,
                    source_type=source_type,
                    markdown=text,
                    parse_warnings=parse_warnings,
                )
            except Exception as read_exc:
                return ParsedDocument(
                    source_id=source_id,
                    source_name=source.name,
                    source_type=source_type,
                    markdown="",
                    parse_warnings=parse_warnings + [f"Raw text fallback also failed: {read_exc}"],
                )

    # Plain text (or Docling available but file is already text)
    try:
        text = source.read_text(encoding="utf-8", errors="replace")
        return ParsedDocument(
            source_id=source_id,
            source_name=source.name,
            source_type=source_type,
            markdown=text,
        )
    except Exception as exc:
        return ParsedDocument(
            source_id=source_id,
            source_name=source.name,
            source_type=source_type,
            markdown="",
            parse_warnings=[f"Failed to read file: {exc}"],
        )


def parse_text(text: str, name: str = "inline", index: int = 0) -> ParsedDocument:
    """Wrap an inline text string as a ParsedDocument."""
    source_id = _generate_source_id(f"{name}-{index}")
    return ParsedDocument(
        source_id=source_id,
        source_name=name,
        source_type="text",
        markdown=text,
    )
