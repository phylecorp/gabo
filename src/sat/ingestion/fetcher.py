"""URL fetching and parsing for evidence ingestion.

@decision DEC-INGEST-003: URL fetching via httpx + Docling.
@title Fetch URLs with httpx, parse with Docling when applicable
@status accepted
@rationale httpx is already a core dependency and provides async HTTP. Content is fetched,
saved to a temp file with the correct extension, and routed through parse_document().
HTML content is parsed directly when Docling is not available.
"""

from __future__ import annotations

import mimetypes
import tempfile
from pathlib import Path

import httpx

from sat.ingestion.parser import parse_document
from sat.models.ingestion import ParsedDocument

MIME_TO_EXT: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/html": ".html",
    "text/plain": ".txt",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}


async def fetch_and_parse(url: str, timeout: float = 30.0) -> ParsedDocument:
    """Fetch a URL and parse its content into a ParsedDocument.

    Downloads the content to a temporary file with the appropriate extension
    based on the Content-Type header, then routes through parse_document().
    On any error, returns a ParsedDocument with an empty markdown and a warning.
    """
    import hashlib

    source_id = hashlib.md5(url.encode()).hexdigest()[:8]

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        ext = MIME_TO_EXT.get(content_type) or mimetypes.guess_extension(content_type) or ".html"
        # mimetypes.guess_extension can return None or odd values — normalise
        if not ext.startswith("."):
            ext = "." + ext

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = Path(tmp.name)

        try:
            doc = await parse_document(tmp_path)
            # Replace tmp filename with the original URL for readability
            return doc.model_copy(update={"source_name": url, "source_id": source_id})
        finally:
            tmp_path.unlink(missing_ok=True)

    except httpx.HTTPStatusError as exc:
        return ParsedDocument(
            source_id=source_id,
            source_name=url,
            source_type="html",
            markdown="",
            parse_warnings=[f"HTTP {exc.response.status_code} fetching {url}"],
        )
    except httpx.TimeoutException:
        return ParsedDocument(
            source_id=source_id,
            source_name=url,
            source_type="html",
            markdown="",
            parse_warnings=[f"Timeout fetching {url}"],
        )
    except Exception as exc:
        return ParsedDocument(
            source_id=source_id,
            source_name=url,
            source_type="html",
            markdown="",
            parse_warnings=[f"Failed to fetch {url}: {exc}"],
        )
