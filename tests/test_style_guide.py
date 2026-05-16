"""Tests for style guide and exemplar loading + prompt injection.

@decision DEC-TEST-STYLE-001
@title Test suite for user-configurable style guide and exemplar feature
@status accepted
@rationale Verifies that load_style_guide() and load_exemplar() in config.py
correctly read from configurable paths (overridden via monkeypatch in tests),
handle missing/empty files, and return trimmed content when present. Also verifies
that build_prompt() in report.py and synthesis.py inject the style guide and
exemplar into the system prompt at the correct positions (style before exemplar,
synthesis receives style guide only — not exemplar since it produces structured JSON).
"""
import pytest

import sat.config as config_mod
from sat.prompts.report import REPORT_SYSTEM_PROMPT


@pytest.fixture
def style_dir(tmp_path, monkeypatch):
    """Redirect style guide and exemplar paths to a temp directory."""
    monkeypatch.setattr(config_mod, "_get_style_guide_path", lambda: tmp_path / "style_guide.md")
    monkeypatch.setattr(config_mod, "_get_exemplar_path", lambda: tmp_path / "exemplar.md")
    return tmp_path


class TestLoadStyleGuide:
    def test_missing_returns_none(self, style_dir):
        assert config_mod.load_style_guide() is None

    def test_empty_returns_none(self, style_dir):
        (style_dir / "style_guide.md").write_text("   \n  ")
        assert config_mod.load_style_guide() is None

    def test_present_returns_content(self, style_dir):
        (style_dir / "style_guide.md").write_text("Use short sentences.")
        assert config_mod.load_style_guide() == "Use short sentences."


class TestLoadExemplar:
    def test_missing_returns_none(self, style_dir):
        assert config_mod.load_exemplar() is None

    def test_empty_returns_none(self, style_dir):
        (style_dir / "exemplar.md").write_text("")
        assert config_mod.load_exemplar() is None

    def test_present_returns_content(self, style_dir):
        (style_dir / "exemplar.md").write_text("The agency assessed with high confidence...")
        assert config_mod.load_exemplar() == "The agency assessed with high confidence..."


class TestReportPromptInjection:
    """Test that style guide and exemplar are injected into report prompts."""

    def _build(self, style_dir, style_text=None, exemplar_text=None):
        if style_text:
            (style_dir / "style_guide.md").write_text(style_text)
        if exemplar_text:
            (style_dir / "exemplar.md").write_text(exemplar_text)

        from sat.prompts.report import build_prompt
        ctx = {
            "question": "Test question",
            "synthesis": None,
            "technique_artifacts": [],
            "evidence": None,
        }
        system_prompt, messages = build_prompt(ctx)
        return system_prompt

    def test_no_style_returns_base(self, style_dir):
        prompt = self._build(style_dir)
        assert prompt == REPORT_SYSTEM_PROMPT

    def test_style_guide_injected(self, style_dir):
        prompt = self._build(style_dir, style_text="Be terse.")
        assert "## User Style Guide" in prompt
        assert "Be terse." in prompt
        assert prompt.startswith(REPORT_SYSTEM_PROMPT)

    def test_exemplar_injected(self, style_dir):
        prompt = self._build(style_dir, exemplar_text="The directorate concluded...")
        assert "## Writing Exemplar" in prompt
        assert "The directorate concluded..." in prompt

    def test_both_injected(self, style_dir):
        prompt = self._build(style_dir, style_text="Be terse.", exemplar_text="Example text.")
        assert "## User Style Guide" in prompt
        assert "## Writing Exemplar" in prompt
        # Style guide should come before exemplar
        sg_idx = prompt.index("## User Style Guide")
        ex_idx = prompt.index("## Writing Exemplar")
        assert sg_idx < ex_idx


class TestSynthesisPromptInjection:
    """Test that style guide is injected into synthesis prompts (but not exemplar)."""

    def test_style_guide_injected(self, style_dir):
        (style_dir / "style_guide.md").write_text("Write plainly.")

        from sat.prompts.synthesis import build_prompt, SYNTHESIS_SYSTEM_PROMPT
        from sat.techniques.base import TechniqueContext

        ctx = TechniqueContext(
            question="Test question",
            evidence=None,
            prior_results=[],
        )
        system_prompt, messages = build_prompt(ctx)
        assert "## User Style Guide" in system_prompt
        assert "Write plainly." in system_prompt
        assert system_prompt.startswith(SYNTHESIS_SYSTEM_PROMPT)

    def test_no_exemplar_in_synthesis(self, style_dir):
        (style_dir / "exemplar.md").write_text("Some exemplar text.")

        from sat.prompts.synthesis import build_prompt
        from sat.techniques.base import TechniqueContext

        ctx = TechniqueContext(
            question="Test question",
            evidence=None,
            prior_results=[],
        )
        system_prompt, messages = build_prompt(ctx)
        assert "Writing Exemplar" not in system_prompt
        assert "Some exemplar text." not in system_prompt
