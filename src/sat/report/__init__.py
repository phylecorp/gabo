"""Executive report generation from SAT analysis output.

@decision DEC-REPORT-001
@title ReportBuilder reads manifest.json and assembles Jinja2-rendered reports
@status accepted
@rationale Disk-based artifact loading decouples report generation from pipeline
execution. Reports can be regenerated from any previous run without re-executing
the analysis. The builder loads manifest.json, deserializes each JSON artifact
to the correct Pydantic model, renders technique sections via the renderer
registry, and assembles the final document using Jinja2 templates.
"""

from __future__ import annotations

from pathlib import Path

from sat.report.builder import ReportBuilder


def generate_report(output_dir: Path, fmt: str = "both") -> list[Path]:
    """Generate report from existing analysis output.

    Args:
        output_dir: Path to the SAT output directory containing manifest.json.
        fmt: Output format — "markdown", "html", or "both".

    Returns:
        List of paths to generated report files.
    """
    builder = ReportBuilder(output_dir)
    return builder.write(fmt=fmt)


__all__ = ["generate_report", "ReportBuilder"]
