"""Tests for LLM-generated intelligence report.

@decision DEC-TEST-REPORT-LLM-001
@title Test-first implementation of LLM report generation
@status accepted
@rationale Tests verify: prompt construction produces correct structure, write_llm()
calls provider and saves files, fallback to Jinja2 on LLM failure, HTML contains
CSS and rendered markdown. LLM provider is mocked because it is an external boundary
(real calls would require API keys, incur cost, and make tests flaky). All file system
operations and report-building logic use real implementations.

# @mock-exempt: LLMProvider is an external service boundary (LLM API calls).
# Mocking it is required — real calls need API keys, incur cost, and produce
# non-deterministic output that cannot be tested against specific assertions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from sat.models.base import ArtifactManifest, Artifact, ArtifactResult
from sat.models.assumptions import AssumptionRow, KeyAssumptionsResult
from sat.models.synthesis import SynthesisResult, TechniqueFinding
from sat.providers.base import LLMMessage, LLMResult, LLMUsage
from sat.report.builder import ReportBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_artifact(path: Path, result: ArtifactResult) -> str:
    """Write a JSON artifact and return the path string."""
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return str(path)


def _create_manifest(output_dir: Path, artifacts: list[Artifact], **kwargs) -> Path:
    """Write a manifest.json for testing."""
    manifest = ArtifactManifest(
        question="Will AI transform healthcare?",
        run_id="test-llm-001",
        started_at="2025-01-01T00:00:00Z",
        completed_at="2025-01-01T01:00:00Z",
        techniques_selected=kwargs.get("techniques_selected", ["assumptions"]),
        techniques_completed=kwargs.get("techniques_completed", ["assumptions"]),
        artifacts=artifacts,
        synthesis_path=kwargs.get("synthesis_path"),
        evidence_provided=kwargs.get("evidence_provided", True),
    )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest_path


def _setup_minimal_run(tmp_path: Path) -> Path:
    """Create a minimal output directory with assumptions + synthesis artifacts."""
    output_dir = tmp_path / "sat-llm-report-test"
    output_dir.mkdir()

    assumptions = KeyAssumptionsResult(
        technique_id="assumptions",
        technique_name="Key Assumptions Check",
        summary="Two key assumptions identified.",
        analytic_line="AI will transform healthcare.",
        assumptions=[
            AssumptionRow(
                assumption="Technology adoption will be rapid",
                confidence="Medium",
                basis_for_confidence="Historical precedent",
                what_undermines="Regulatory barriers",
                impact_if_wrong="Timeline shifts significantly",
            ),
        ],
        most_vulnerable=["Technology adoption will be rapid"],
    )
    assumptions_path = _write_artifact(output_dir / "01-assumptions.json", assumptions)

    synthesis = SynthesisResult(
        technique_id="synthesis",
        technique_name="Synthesis",
        summary="Cross-technique synthesis complete.",
        question="Will AI transform healthcare?",
        techniques_applied=["assumptions"],
        key_findings=[
            TechniqueFinding(
                technique_id="assumptions",
                technique_name="Key Assumptions Check",
                summary="Assumptions identified.",
                key_finding="Rapid adoption is the most vulnerable assumption.",
                confidence="Medium",
            ),
        ],
        convergent_judgments=["All techniques agree AI will impact healthcare."],
        divergent_signals=["Timeline estimates vary widely."],
        highest_confidence_assessments=["AI will reduce diagnostic errors."],
        remaining_uncertainties=["Speed of regulatory approval."],
        recommended_next_steps=["Monitor FDA pipeline."],
        bottom_line_assessment="AI will transform healthcare, but slower than optimists predict.",
    )
    synthesis_path = _write_artifact(output_dir / "02-synthesis.json", synthesis)

    artifacts = [
        Artifact(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            category="diagnostic",
            markdown_path=str(output_dir / "01-assumptions.md"),
            json_path=assumptions_path,
        ),
        Artifact(
            technique_id="synthesis",
            technique_name="Synthesis",
            category="synthesis",
            markdown_path=str(output_dir / "02-synthesis.md"),
            json_path=synthesis_path,
        ),
    ]
    _create_manifest(
        output_dir,
        artifacts,
        synthesis_path=synthesis_path,
        techniques_completed=["assumptions"],
    )
    return output_dir


def _make_mock_provider(report_text: str) -> MagicMock:
    """Create a mock LLM provider that returns the given report text.

    # @mock-exempt: LLMProvider is an external API boundary — real calls
    # require API keys, incur cost, and produce non-deterministic output.
    """
    provider = MagicMock()
    provider.generate = AsyncMock(
        return_value=LLMResult(
            text=report_text,
            usage=LLMUsage(input_tokens=100, output_tokens=500),
        )
    )
    return provider


# ---------------------------------------------------------------------------
# Tests: prompt module
# ---------------------------------------------------------------------------

class TestReportPrompt:
    """Test sat.prompts.report.build_prompt() structure and content."""

    def test_import(self):
        """The report prompt module should be importable."""
        from sat.prompts import report as report_prompt  # noqa: F401
        assert hasattr(report_prompt, "REPORT_SYSTEM_PROMPT")
        assert hasattr(report_prompt, "build_prompt")

    def test_system_prompt_contains_bluf(self):
        """System prompt should contain BLUF guidance."""
        from sat.prompts.report import REPORT_SYSTEM_PROMPT
        assert "Bottom Line Up Front" in REPORT_SYSTEM_PROMPT or "BLUF" in REPORT_SYSTEM_PROMPT

    def test_system_prompt_contains_estimative_language(self):
        """System prompt should mention estimative language."""
        from sat.prompts.report import REPORT_SYSTEM_PROMPT
        # Should mention likelihood expressions
        assert "likely" in REPORT_SYSTEM_PROMPT.lower()

    def test_system_prompt_contains_report_sections(self):
        """System prompt should define the expected report sections."""
        from sat.prompts.report import REPORT_SYSTEM_PROMPT
        assert "Assessment" in REPORT_SYSTEM_PROMPT
        assert "Challenges" in REPORT_SYSTEM_PROMPT or "Alternative" in REPORT_SYSTEM_PROMPT
        assert "Outlook" in REPORT_SYSTEM_PROMPT or "Indicators" in REPORT_SYSTEM_PROMPT

    def test_build_prompt_returns_tuple(self, tmp_path):
        """build_prompt() should return (system_prompt_str, list[LLMMessage])."""
        from sat.prompts.report import build_prompt

        output_dir = _setup_minimal_run(tmp_path)
        builder = ReportBuilder(output_dir)
        ctx = builder._build_llm_context()

        result = build_prompt(ctx)
        assert isinstance(result, tuple)
        assert len(result) == 2
        system_prompt, messages = result
        assert isinstance(system_prompt, str)
        assert len(system_prompt) > 100
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert isinstance(messages[0], LLMMessage)
        assert messages[0].role == "user"

    def test_user_message_contains_question(self, tmp_path):
        """User message should contain the analytic question."""
        from sat.prompts.report import build_prompt

        output_dir = _setup_minimal_run(tmp_path)
        builder = ReportBuilder(output_dir)
        ctx = builder._build_llm_context()

        _, messages = build_prompt(ctx)
        assert "Will AI transform healthcare?" in messages[0].content

    def test_user_message_contains_synthesis(self, tmp_path):
        """User message should contain synthesis data."""
        from sat.prompts.report import build_prompt

        output_dir = _setup_minimal_run(tmp_path)
        builder = ReportBuilder(output_dir)
        ctx = builder._build_llm_context()

        _, messages = build_prompt(ctx)
        # Synthesis bottom line should appear in user message
        assert "AI will transform healthcare" in messages[0].content

    def test_user_message_contains_technique_artifacts(self, tmp_path):
        """User message should contain technique artifact data."""
        from sat.prompts.report import build_prompt

        output_dir = _setup_minimal_run(tmp_path)
        builder = ReportBuilder(output_dir)
        ctx = builder._build_llm_context()

        _, messages = build_prompt(ctx)
        # Technique artifact should appear in user message
        assert "assumptions" in messages[0].content.lower()

    def test_user_message_contains_date(self, tmp_path):
        """User message should include today's date for temporal grounding."""
        from sat.prompts.report import build_prompt

        output_dir = _setup_minimal_run(tmp_path)
        builder = ReportBuilder(output_dir)
        ctx = builder._build_llm_context()

        _, messages = build_prompt(ctx)
        # Should have a date in ISO format
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", messages[0].content)

    def test_build_llm_context_shape(self, tmp_path):
        """_build_llm_context() should return dict with required keys."""
        output_dir = _setup_minimal_run(tmp_path)
        builder = ReportBuilder(output_dir)
        ctx = builder._build_llm_context()

        assert "question" in ctx
        assert "synthesis" in ctx
        assert "technique_artifacts" in ctx
        assert isinstance(ctx["technique_artifacts"], list)
        assert ctx["question"] == "Will AI transform healthcare?"


# ---------------------------------------------------------------------------
# Tests: write_llm() method
# ---------------------------------------------------------------------------

class TestWriteLlm:
    """Test ReportBuilder.write_llm() behavior.

    # @mock-exempt: LLMProvider is an external API boundary — real calls
    # require API keys, incur cost, and produce non-deterministic output.
    """

    SAMPLE_REPORT_MD = """# AI Healthcare Transformation: Likely but Slower Than Expected

## Assessment

We assess that AI will likely transform healthcare over the coming decade, though the pace will be slower than technology optimists predict. The evidence base is moderate — multiple analytical approaches converge on AI's transformative potential, but diverge on timeline. Confidence is Moderate, driven primarily by strong technical evidence tempered by significant regulatory uncertainty.

The single most consequential uncertainty is the FDA regulatory pipeline. If approval pathways remain slow, adoption timelines could extend by five to ten years.

## Key Evidence and Analysis

Systematic assumption analysis identified rapid technology adoption as the most vulnerable assumption in the bullish AI transformation case. Historical precedent supports optimism about adoption speed, but regulatory barriers represent a genuine chokepoint.

The convergent judgment across techniques is that AI will reduce diagnostic errors — this finding appears with High confidence. Divergent signals emerge on timing: some analytical approaches suggest near-term impact while others project longer adoption curves.

## Challenges and Alternative Views

The strongest counter-argument is that healthcare AI faces unique deployment barriers — liability concerns, clinical workflow integration costs, and physician resistance — that could substantially delay the transformation timeline. If regulatory approval remains slow and institutional resistance persists, the "transformation" may be incremental rather than disruptive over a decade.

This alternative view is credible but does not overturn the main assessment, because the underlying capability improvements are real and the economic incentives are strong.

## Outlook and Indicators

Watch for FDA approval rate changes for AI diagnostic tools as the leading indicator. Rapid approvals would confirm the bullish case; increasing rejection rates would support the delayed timeline alternative.

## Methodology Note

This assessment applied Key Assumptions Check to identify and stress-test the core assumptions underlying AI transformation claims.
"""

    @pytest.mark.asyncio
    async def test_write_llm_calls_provider(self, tmp_path):
        """write_llm() should call provider.generate() exactly once."""
        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider(self.SAMPLE_REPORT_MD)

        builder = ReportBuilder(output_dir)
        await builder.write_llm(provider=provider, fmt="markdown")

        provider.generate.assert_called_once()
        call_args = provider.generate.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_write_llm_saves_report_md(self, tmp_path):
        """write_llm() with fmt='markdown' should save report.md."""
        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider(self.SAMPLE_REPORT_MD)

        builder = ReportBuilder(output_dir)
        paths = await builder.write_llm(provider=provider, fmt="markdown")

        md_path = output_dir / "report.md"
        assert md_path.exists(), "report.md should be written"
        assert any(p.name == "report.md" for p in paths)

    @pytest.mark.asyncio
    async def test_write_llm_report_md_contains_llm_content(self, tmp_path):
        """report.md should contain the LLM-generated text."""
        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider(self.SAMPLE_REPORT_MD)

        builder = ReportBuilder(output_dir)
        await builder.write_llm(provider=provider, fmt="markdown")

        content = (output_dir / "report.md").read_text()
        assert "AI Healthcare Transformation" in content
        assert "Moderate" in content

    @pytest.mark.asyncio
    async def test_write_llm_saves_report_html(self, tmp_path):
        """write_llm() with fmt='html' should save report.html."""
        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider(self.SAMPLE_REPORT_MD)

        builder = ReportBuilder(output_dir)
        paths = await builder.write_llm(provider=provider, fmt="html")

        html_path = output_dir / "report.html"
        assert html_path.exists(), "report.html should be written"
        assert any(p.name == "report.html" for p in paths)

    @pytest.mark.asyncio
    async def test_write_llm_html_has_css(self, tmp_path):
        """LLM-generated report.html should contain CSS styling."""
        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider(self.SAMPLE_REPORT_MD)

        builder = ReportBuilder(output_dir)
        await builder.write_llm(provider=provider, fmt="html")

        content = (output_dir / "report.html").read_text()
        assert "<style>" in content
        assert "font-family" in content

    @pytest.mark.asyncio
    async def test_write_llm_html_contains_rendered_markdown(self, tmp_path):
        """HTML output should have rendered markdown (h1 tag from report title)."""
        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider(self.SAMPLE_REPORT_MD)

        builder = ReportBuilder(output_dir)
        await builder.write_llm(provider=provider, fmt="html")

        content = (output_dir / "report.html").read_text()
        # The markdown title should be rendered as an <h1>
        assert "<h1>" in content
        assert "AI Healthcare Transformation" in content

    @pytest.mark.asyncio
    async def test_write_llm_both_produces_two_files(self, tmp_path):
        """write_llm() with fmt='both' should produce report.md and report.html."""
        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider(self.SAMPLE_REPORT_MD)

        builder = ReportBuilder(output_dir)
        paths = await builder.write_llm(provider=provider, fmt="both")

        names = {p.name for p in paths}
        assert "report.md" in names
        assert "report.html" in names

    @pytest.mark.asyncio
    async def test_write_llm_uses_higher_temperature(self, tmp_path):
        """write_llm() should use temperature=0.4 (slightly higher for creative prose)."""
        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider(self.SAMPLE_REPORT_MD)

        builder = ReportBuilder(output_dir)
        await builder.write_llm(provider=provider, fmt="markdown")

        call_kwargs = provider.generate.call_args[1]  # keyword args
        assert call_kwargs.get("temperature", 0.3) >= 0.4, (
            "Report generation should use temperature >= 0.4 for creative prose"
        )

    @pytest.mark.asyncio
    async def test_write_llm_fallback_on_provider_error(self, tmp_path):
        """write_llm() should fall back to Jinja2 write() if provider raises."""
        output_dir = _setup_minimal_run(tmp_path)

        # Provider that always fails
        provider = MagicMock()
        provider.generate = AsyncMock(side_effect=RuntimeError("API unavailable"))

        builder = ReportBuilder(output_dir)
        paths = await builder.write_llm(provider=provider, fmt="markdown")

        # Should have fallen back to Jinja2 — report.md should still exist
        assert len(paths) > 0
        md_path = output_dir / "report.md"
        assert md_path.exists(), "Fallback should produce report.md via Jinja2"

    @pytest.mark.asyncio
    async def test_write_llm_fallback_content_is_jinja2_style(self, tmp_path):
        """Fallback output should have the Jinja2 report structure (Executive Summary)."""
        output_dir = _setup_minimal_run(tmp_path)

        provider = MagicMock()
        provider.generate = AsyncMock(side_effect=RuntimeError("API unavailable"))

        builder = ReportBuilder(output_dir)
        await builder.write_llm(provider=provider, fmt="markdown")

        content = (output_dir / "report.md").read_text()
        # Jinja2 report has "Executive Summary" section
        assert "Executive Summary" in content


# ---------------------------------------------------------------------------
# Tests: generate_report_llm() public API
# ---------------------------------------------------------------------------

class TestGenerateReportLlm:
    """Test the public generate_report_llm() async function.

    # @mock-exempt: LLMProvider is an external API boundary — real calls
    # require API keys, incur cost, and produce non-deterministic output.
    """

    @pytest.mark.asyncio
    async def test_generate_report_llm_returns_paths(self, tmp_path):
        """generate_report_llm() should return list of Path objects."""
        from sat.report import generate_report_llm

        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider("# Test Report\n\nThis is the assessment.\n")

        paths = await generate_report_llm(output_dir, provider=provider, fmt="markdown")

        assert isinstance(paths, list)
        assert len(paths) > 0
        assert all(isinstance(p, Path) for p in paths)

    @pytest.mark.asyncio
    async def test_generate_report_llm_file_exists(self, tmp_path):
        """generate_report_llm() output file should exist on disk."""
        from sat.report import generate_report_llm

        output_dir = _setup_minimal_run(tmp_path)
        provider = _make_mock_provider("# Test\n\nContent.\n")

        paths = await generate_report_llm(output_dir, provider=provider, fmt="markdown")

        for p in paths:
            assert p.exists(), f"Expected {p} to exist"

    @pytest.mark.asyncio
    async def test_generate_report_llm_fallback_on_failure(self, tmp_path):
        """generate_report_llm() should fall back gracefully if provider fails."""
        from sat.report import generate_report_llm

        output_dir = _setup_minimal_run(tmp_path)
        provider = MagicMock()
        provider.generate = AsyncMock(side_effect=Exception("Network error"))

        # Should not raise — should fall back to Jinja2
        paths = await generate_report_llm(output_dir, provider=provider, fmt="markdown")

        assert len(paths) > 0

    def test_generate_report_llm_is_in_all(self):
        """generate_report_llm should be exported from sat.report.__all__."""
        import sat.report as report_module
        assert "generate_report_llm" in report_module.__all__
