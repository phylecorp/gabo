"""HTML text extractor using stdlib html.parser — no external dependencies.

@decision DEC-VERIFY-002: stdlib html.parser over BeautifulSoup for extraction.
@title Zero-dependency HTML text extraction via HTMLParser subclass
@status accepted
@rationale Source verification must not introduce additional package dependencies.
HTMLParser is sufficient to strip script/style/nav/header/footer tags and
collapse whitespace. Content quality is adequate for LLM-based claim assessment.
"""

from __future__ import annotations

import html.parser


class _TextExtractor(html.parser.HTMLParser):
    """Extract readable text from HTML, skipping noisy structural tags.

    Tags stripped entirely (including content): script, style, nav, header, footer.
    All other tags are ignored but their text content is retained.
    """

    # Tags whose entire subtree (content included) should be suppressed
    _SUPPRESS_TAGS = frozenset({"script", "style", "nav", "header", "footer"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._suppress_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SUPPRESS_TAGS:
            self._suppress_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SUPPRESS_TAGS and self._suppress_depth > 0:
            self._suppress_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._suppress_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)


def extract_text(html: str, max_chars: int = 15000) -> str:
    """Extract readable text from an HTML string.

    Strips script, style, nav, header, and footer tags with all their content,
    collapses whitespace, and truncates to max_chars.

    Args:
        html: Raw HTML content.
        max_chars: Maximum characters to return (default 15000).

    Returns:
        Clean readable text, truncated to max_chars.
    """
    if not html:
        return ""

    extractor = _TextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        # Malformed HTML — return whatever we managed to extract
        pass

    text = extractor.get_text()

    # Collapse multiple internal spaces (inter-word gaps from tag stripping)
    import re
    text = re.sub(r" {2,}", " ", text)

    return text[:max_chars]
