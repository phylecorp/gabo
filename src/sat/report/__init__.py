"""Executive report generation from SAT analysis output.

@decision DEC-REPORT-001
@title ReportBuilder reads manifest.json and assembles Jinja2-rendered reports
@status accepted
@rationale Disk-based artifact loading decouples report generation from pipeline
execution. Reports can be regenerated from any previous run without re-executing
the analysis. The builder loads manifest.json, deserializes each JSON artifact
to the correct Pydantic model, renders technique sections via the renderer
registry, and assembles the final document using Jinja2 templates.

@decision DEC-REPORT-006
@title generate_report_llm() as async public API for LLM-generated reports
@status accepted
@rationale The async wrapper mirrors generate_report() but delegates to write_llm(),
which uses an LLM provider to produce prose-driven intelligence assessments rather
than Jinja2 template output. Falls back to generate_report() on any failure so
callers never need to handle two separate error paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sat.report.builder import ReportBuilder

if TYPE_CHECKING:
    from sat.providers.base import LLMProvider


def generate_report(output_dir: Path, fmt: str = "both") -> list[Path]:
    """Generate report from existing analysis output using Jinja2 templates.

    Args:
        output_dir: Path to the SAT output directory containing manifest.json.
        fmt: Output format — "markdown", "html", or "both".

    Returns:
        List of paths to generated report files.
    """
    builder = ReportBuilder(output_dir)
    return builder.write(fmt=fmt)


async def generate_report_llm(
    output_dir: Path,
    provider: "LLMProvider",
    fmt: str = "both",
) -> list[Path]:
    """Generate an LLM-written intelligence assessment from existing analysis output.

    Sends the full structured data (synthesis, technique artifact JSONs, question) to
    the LLM provider and saves the generated prose as report.md and/or report.html.
    Falls back to Jinja2 generate_report() on any failure.

    Args:
        output_dir: Path to the SAT output directory containing manifest.json.
        provider: LLM provider instance (must implement LLMProvider protocol).
        fmt: Output format — "markdown", "html", or "both".

    Returns:
        List of paths to generated report files.
    """
    builder = ReportBuilder(output_dir)
    return await builder.write_llm(provider=provider, fmt=fmt)


__all__ = ["generate_report", "generate_report_llm", "ReportBuilder"]
