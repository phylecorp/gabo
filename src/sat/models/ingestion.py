"""Ingestion result models for multimodal evidence parsing.

@decision DEC-INGEST-001: Docling for multimodal parsing.
@title Use Docling library for PDF/DOCX/PPTX/XLSX/HTML/image parsing
@status accepted
@rationale Docling provides unified parsing across document formats with optional OCR.
Falls back to raw text reading when Docling is not installed, keeping the dependency optional.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from sat.models.base import ArtifactResult


class ParsedDocument(BaseModel):
    """A single parsed document from the ingestion phase."""

    source_id: str = Field(description="Short identifier for this source (md5-based)")
    source_name: str = Field(description="Original file name or URL")
    source_type: str = Field(
        description="Detected type: pdf, docx, pptx, xlsx, html, image, audio, text"
    )
    markdown: str = Field(description="Normalized markdown content")
    tables: list[str] = Field(default_factory=list, description="Extracted table representations")
    metadata: dict = Field(default_factory=dict, description="Source-specific metadata")
    parse_warnings: list[str] = Field(default_factory=list, description="Warnings during parsing")


class IngestionResult(ArtifactResult):
    """Result of the evidence ingestion phase."""

    technique_id: str = Field(default="ingestion", description="Phase identifier")
    technique_name: str = Field(default="Evidence Ingestion", description="Phase display name")
    summary: str = Field(default="", description="Brief summary of ingestion results")
    documents: list[ParsedDocument] = Field(default_factory=list, description="Parsed documents")
    combined_markdown: str = Field(default="", description="All documents combined as markdown")
    source_manifest: list[dict] = Field(
        default_factory=list, description="Per-source metadata summary"
    )
    total_estimated_tokens: int = Field(
        default=0, description="Estimated tokens in combined output"
    )
    warnings: list[str] = Field(default_factory=list, description="Warnings during ingestion")
