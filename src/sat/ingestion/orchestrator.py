"""Evidence ingestion orchestrator — single entry point for all sources.

@decision DEC-INGEST-004: Single entry point classifies and routes sources.
@title Orchestrator for evidence ingestion
@status accepted
@rationale A single async function handles source classification (URL vs file vs directory),
routes to the appropriate parser, combines results with source markers, and produces
the IngestionResult. URLs are fetched concurrently; files are parsed sequentially
(Docling models are not thread-safe).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sat.config import IngestionConfig
from sat.ingestion.fetcher import fetch_and_parse
from sat.ingestion.parser import parse_document, parse_text
from sat.models.ingestion import IngestionResult, ParsedDocument
from sat.preprocessing.measurer import estimate_tokens

logger = logging.getLogger(__name__)


async def ingest_evidence(
    sources: list[str],
    inline_evidence: str | None = None,
    config: IngestionConfig | None = None,
) -> IngestionResult:
    """Ingest files, directories, and URLs into a combined IngestionResult.

    Source classification:
    - URLs (http:// or https://) are fetched concurrently via httpx.
    - Directories are recursed and each file is parsed sequentially.
    - Files are parsed sequentially (Docling is not thread-safe).
    - Missing/invalid paths produce a warning and are skipped.

    If inline_evidence is provided it is appended as an additional "inline" source.
    The combined_markdown field has each document's content wrapped with
    ``--- Source: <name> ---`` markers for downstream multi-file detection.
    """
    config = config or IngestionConfig()
    documents: list[ParsedDocument] = []
    warnings: list[str] = []

    url_sources: list[str] = []
    file_sources: list[Path] = []

    for s in sources:
        if s.startswith("http://") or s.startswith("https://"):
            url_sources.append(s)
        else:
            p = Path(s)
            if p.is_dir():
                for child in sorted(p.rglob("*")):
                    if child.is_file() and not child.name.startswith("."):
                        file_sources.append(child)
            elif p.is_file():
                file_sources.append(p)
            else:
                warnings.append(f"Source not found: {s}")

    # Fetch URLs concurrently
    if url_sources:
        url_tasks = [fetch_and_parse(url, config.fetch_timeout) for url in url_sources]
        url_results = await asyncio.gather(*url_tasks, return_exceptions=True)
        for url, result in zip(url_sources, url_results):
            if isinstance(result, Exception):
                logger.warning("URL fetch failed for %s: %s", url, result)
                warnings.append(f"Failed to fetch {url}: {result}")
            else:
                documents.append(result)

    # Parse files sequentially
    for file_path in file_sources:
        doc = await parse_document(file_path)
        documents.append(doc)

    # Append inline evidence as a final pseudo-document
    if inline_evidence:
        documents.append(parse_text(inline_evidence, "inline", 0))

    # Build combined markdown with source markers
    parts: list[str] = []
    for doc in documents:
        parts.append(f"--- Source: {doc.source_name} ---\n{doc.markdown}")
    combined_markdown = "\n\n".join(parts)

    total_tokens = estimate_tokens(combined_markdown)

    source_manifest = [
        {
            "name": doc.source_name,
            "type": doc.source_type,
            "word_count": len(doc.markdown.split()),
            "warnings": doc.parse_warnings,
        }
        for doc in documents
    ]

    summary = f"Ingested {len(documents)} source(s), ~{total_tokens} tokens"

    return IngestionResult(
        documents=documents,
        combined_markdown=combined_markdown,
        source_manifest=source_manifest,
        total_estimated_tokens=total_tokens,
        warnings=warnings,
        summary=summary,
    )
