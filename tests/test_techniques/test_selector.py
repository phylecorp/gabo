"""Test technique selector validation logic.

@decision DEC-TEST-SEL-001: Selector validation rule enforcement.
Tests parsing of LLM responses (JSON and fallback text scanning) and
post-validation rules: at least 1 diagnostic, max 6 techniques, red_team
for adversary questions, quality when evidence provided, proper ordering.
"""

from __future__ import annotations

import logging

import sat.techniques  # noqa: F401

from sat.techniques.selector import _parse_selection, _validate_selection


class TestSelectorParsing:
    """Test parsing of LLM responses into technique IDs."""

    def test_parse_json_object(self):
        response = '{"techniques": [{"id": "assumptions"}, {"id": "ach"}]}'
        assert _parse_selection(response) == ["assumptions", "ach"]

    def test_parse_json_list(self):
        response = '["assumptions", "ach", "indicators"]'
        result = _parse_selection(response)
        assert set(result) == {"assumptions", "ach", "indicators"}

    def test_parse_plain_text_fallback(self):
        response = "I recommend using assumptions and ach for this question."
        result = _parse_selection(response)
        assert "assumptions" in result
        assert "ach" in result

    def test_parse_invalid_returns_defaults(self):
        response = "I have no idea what you're asking."
        result = _parse_selection(response)
        assert "assumptions" in result

    def test_json_parse_failure_logs_warning(self, caplog):
        """When JSON parse fails and we fall back to regex, a WARNING is logged."""
        response = "I recommend assumptions and ach for this analysis."
        with caplog.at_level(logging.WARNING, logger="sat.techniques.selector"):
            result = _parse_selection(response)
        assert "assumptions" in result
        warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("not valid JSON" in msg or "falling back" in msg for msg in warning_messages)

    def test_no_techniques_found_logs_warning(self, caplog):
        """When no technique IDs are found anywhere, a WARNING is logged before returning defaults."""
        response = "I have absolutely no relevant techniques to suggest here."
        with caplog.at_level(logging.WARNING, logger="sat.techniques.selector"):
            result = _parse_selection(response)
        assert "assumptions" in result
        warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("defaults" in msg or "no technique" in msg for msg in warning_messages)


    def test_parse_fenced_json_backtick_json(self, caplog):
        """LLM response wrapped in ```json ... ``` fences parses cleanly without warning."""
        response = '''```json
{"techniques": [{"id": "assumptions"}, {"id": "ach"}]}
```'''
        with caplog.at_level(logging.WARNING, logger="sat.techniques.selector"):
            result = _parse_selection(response)
        assert "assumptions" in result
        assert "ach" in result
        # No JSON parse warning — fences should be stripped before json.loads
        warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("not valid JSON" in msg for msg in warning_messages)

    def test_parse_fenced_json_plain_backtick(self, caplog):
        """LLM response wrapped in plain ``` fences (no language tag) parses cleanly."""
        response = '''```
{"techniques": [{"id": "assumptions"}, {"id": "brainstorming"}]}
```'''
        with caplog.at_level(logging.WARNING, logger="sat.techniques.selector"):
            result = _parse_selection(response)
        assert "assumptions" in result
        assert "brainstorming" in result
        warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("not valid JSON" in msg for msg in warning_messages)

    def test_parse_fenced_json_no_trailing_newline(self, caplog):
        """Fenced JSON without trailing newline before closing fence parses correctly."""
        response = '''```json
{"techniques": [{"id": "ach"}]}```'''
        with caplog.at_level(logging.WARNING, logger="sat.techniques.selector"):
            result = _parse_selection(response)
        assert "ach" in result
        warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("not valid JSON" in msg for msg in warning_messages)


class TestSelectorValidation:
    """Test post-validation rules."""

    def test_ensures_at_least_one_diagnostic(self):
        result = _validate_selection(["brainstorming", "red_team"], "question", None)
        diagnostic_ids = {"assumptions", "quality", "indicators", "ach"}
        assert any(tid in diagnostic_ids for tid in result)

    def test_adds_red_team_for_adversary_questions(self):
        result = _validate_selection(
            ["assumptions", "ach"],
            "How will the adversary respond to our sanctions?",
            None,
        )
        assert "red_team" in result

    def test_adds_quality_when_evidence_provided(self):
        result = _validate_selection(
            ["assumptions", "ach"],
            "Test question",
            "Some intelligence report evidence",
        )
        assert "quality" in result

    def test_preserves_correct_ordering(self):
        result = _validate_selection(
            ["brainstorming", "ach", "assumptions"],
            "question",
            None,
        )
        ach_idx = result.index("ach")
        brain_idx = result.index("brainstorming")
        assert ach_idx < brain_idx
