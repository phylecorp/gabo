"""Tests for HTML text extraction.

Covers the extract_text() function and _TextExtractor class.
No external dependencies — all stdlib.
"""

from __future__ import annotations

from sat.research.verification.extractor import extract_text


class TestExtractText:
    def test_strips_script_tags(self):
        html = "<p>Hello</p><script>alert('xss')</script><p>World</p>"
        result = extract_text(html)
        assert "Hello" in result
        assert "World" in result
        assert "alert" not in result
        assert "xss" not in result

    def test_strips_style_tags(self):
        html = "<p>Content</p><style>.foo { color: red; }</style><p>More</p>"
        result = extract_text(html)
        assert "Content" in result
        assert "More" in result
        assert "color" not in result
        assert ".foo" not in result

    def test_strips_nav_header_footer(self):
        html = (
            "<header>Site Header</header>"
            "<nav>Navigation Links</nav>"
            "<main><p>Main article content</p></main>"
            "<footer>Footer text</footer>"
        )
        result = extract_text(html)
        assert "Main article content" in result
        assert "Site Header" not in result
        assert "Navigation Links" not in result
        assert "Footer text" not in result

    def test_collapses_whitespace(self):
        html = "<p>Word1   Word2</p><p>Word3</p>"
        result = extract_text(html)
        # Should not have multiple consecutive spaces between words
        assert "  " not in result
        assert "Word1" in result
        assert "Word2" in result
        assert "Word3" in result

    def test_truncates_at_max_chars(self):
        # Generate HTML longer than max_chars
        html = "<p>" + "A" * 20000 + "</p>"
        result = extract_text(html, max_chars=100)
        assert len(result) <= 100

    def test_handles_empty_html(self):
        result = extract_text("")
        assert result == ""

    def test_handles_none_like_empty(self):
        # Passing empty string directly
        result = extract_text("   ")
        # Whitespace-only HTML produces empty or whitespace output
        assert result.strip() == ""

    def test_preserves_paragraph_text(self):
        html = (
            "<html><body>"
            "<h1>Title</h1>"
            "<p>First paragraph with important content.</p>"
            "<p>Second paragraph with more details.</p>"
            "</body></html>"
        )
        result = extract_text(html)
        assert "Title" in result
        assert "First paragraph with important content" in result
        assert "Second paragraph with more details" in result

    def test_nested_suppressed_tags(self):
        """Nested script/style inside nav should also be suppressed."""
        html = (
            "<nav><script>var x=1;</script><a>Link</a></nav>"
            "<p>Real content</p>"
        )
        result = extract_text(html)
        assert "Real content" in result
        assert "var x" not in result
        assert "Link" not in result

    def test_default_max_chars_is_15000(self):
        html = "<p>" + "B" * 20000 + "</p>"
        result = extract_text(html)
        assert len(result) <= 15000
