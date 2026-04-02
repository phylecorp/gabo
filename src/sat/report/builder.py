"""Report builder: loads artifacts and assembles executive reports.

Loads manifest.json from an output directory, deserializes each JSON artifact
to the correct Pydantic model, renders technique sections via the renderer
registry, and assembles the final document using Jinja2 templates.

@decision DEC-REPORT-004
@title Narrative analytical report structure — additive to artifacts, not a summary of them
@status accepted
@rationale Restructured report from IC-jargon intelligence brief into a plain-language
narrative analytical product. The report is additive: it explains the conclusion, traces the
evidence, and identifies challenges — rather than dumping full artifact content. Key sections:
Executive Summary (single occurrence of bottom line), Key Assessment (supporting evidence),
Challenges to This View (divergent signals and low-confidence findings), Confidence (distribution
bar with plain-language narrative), Next Steps, Methods Used (brief per-technique summaries, no
full content), and Appendix. The template uses result.summary for per-technique narrative;
rendered_content is preserved in context for potential future use but not rendered in the main body.

@decision DEC-REPORT-005
@title LLM-generated report as primary path, Jinja2 as fallback
@status accepted
@rationale write_llm() sends all structured data (synthesis JSON, full technique artifact JSONs,
evidence, question) to an LLM provider and saves the generated prose as report.md/report.html.
The HTML wrapper reuses the same CSS from report.html.j2 for visual consistency. If the LLM
call fails for any reason (API error, timeout, import error), write_llm() transparently falls
back to the existing Jinja2 write() path. This ensures reports are always generated even when
the LLM is unavailable.
"""

from __future__ import annotations

import functools
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sat.providers.base import LLMProvider

import markdown as markdown_lib
from jinja2 import Environment, FileSystemLoader

from sat.models.base import ArtifactManifest, ArtifactResult
from sat.report.descriptions import CATEGORY_DESCRIPTIONS, TECHNIQUE_DESCRIPTIONS
from sat.report.renderers import render_technique
from sat.utils.resources import get_resource_path

logger = logging.getLogger(__name__)

# Suffixes and IDs to exclude from report technique sections
_ADVERSARIAL_SUFFIXES = ("-critique", "-rebuttal", "-adjudication", "-investigator", "-convergence")
_REVISED_SUFFIX = "-revised"
_NON_TECHNIQUE_IDS = {"preprocessing", "research", "synthesis", "verification"}


@functools.lru_cache(maxsize=1)
def _get_model_registry() -> dict[str, type[ArtifactResult]]:
    """Lazy-load the model registry to avoid circular imports."""
    from sat.models.ach import ACHResult
    from sat.models.alt_futures import AltFuturesResult
    from sat.models.assumptions import KeyAssumptionsResult
    from sat.models.brainstorming import BrainstormingResult
    from sat.models.devils_advocacy import DevilsAdvocacyResult
    from sat.models.high_impact import HighImpactResult
    from sat.models.indicators import IndicatorsResult
    from sat.models.outside_in import OutsideInResult
    from sat.models.quality import QualityOfInfoResult
    from sat.models.red_team import RedTeamResult
    from sat.models.synthesis import SynthesisResult
    from sat.models.team_ab import TeamABResult
    from sat.models.what_if import WhatIfResult

    return {
        "ach": ACHResult,
        "alt_futures": AltFuturesResult,
        "assumptions": KeyAssumptionsResult,
        "brainstorming": BrainstormingResult,
        "devils_advocacy": DevilsAdvocacyResult,
        "high_impact": HighImpactResult,
        "indicators": IndicatorsResult,
        "outside_in": OutsideInResult,
        "quality": QualityOfInfoResult,
        "red_team": RedTeamResult,
        "team_ab": TeamABResult,
        "what_if": WhatIfResult,
        "synthesis": SynthesisResult,
    }


def _slugify(text: str) -> str:
    """Convert text to a URL-safe anchor slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _basename(path: str) -> str:
    """Jinja2 filter: extract filename from a path."""
    return Path(path).name


def _is_synthesis_artifact(technique_id: str) -> bool:
    """Return True if this technique_id represents a synthesis result."""
    tid = technique_id.lower()
    return tid == "synthesis" or tid.startswith("synthesis-")


def _is_technique_artifact(technique_id: str) -> bool:
    """Return True if this artifact ID represents a core technique."""
    if any(technique_id.endswith(s) for s in _ADVERSARIAL_SUFFIXES):
        return False
    if technique_id.endswith(_REVISED_SUFFIX):
        return False
    if technique_id in _NON_TECHNIQUE_IDS:
        return False
    if _is_synthesis_artifact(technique_id):
        return False
    return True


class ReportBuilder:
    """Builds executive reports from SAT analysis output on disk."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self._artifact_cache: dict[str, ArtifactResult] = {}
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> ArtifactManifest:
        manifest_path = self.output_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No manifest.json found in {self.output_dir}")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ArtifactManifest.model_validate(data)

    def _load_artifact(self, json_path: str) -> ArtifactResult:
        """Load and deserialize a JSON artifact to the correct Pydantic model."""
        if json_path in self._artifact_cache:
            return self._artifact_cache[json_path]
        path = Path(json_path)
        if not path.is_absolute():
            # Manifest paths may be relative to CWD or include the output dir name.
            # Try output_dir/path first, then output_dir.parent/path, then just path.
            candidates = [
                self.output_dir / path,
                self.output_dir.parent / path,
                path,
            ]
            for candidate in candidates:
                if candidate.exists():
                    path = candidate
                    break
            else:
                path = self.output_dir / path.name
        data = json.loads(path.read_text(encoding="utf-8"))
        technique_id = data.get("technique_id", "")
        registry = _get_model_registry()
        # Normalize synthesis-like IDs (e.g. "SYNTHESIS-001") to registry key
        registry_key = "synthesis" if _is_synthesis_artifact(technique_id) else technique_id
        model_cls = registry.get(registry_key, ArtifactResult)
        result = model_cls.model_validate(data)
        self._artifact_cache[json_path] = result
        return result

    def _resolve_technique_name(self, technique_id: str) -> str:
        """Resolve a technique ID to its human-readable name via the registry."""
        try:
            import sat.techniques  # noqa: F401 — ensure registration
            from sat.techniques.registry import get_technique

            return get_technique(technique_id).metadata.name
        except (ValueError, ImportError):
            return technique_id.replace("_", " ").title()

    def _resolve_technique_category(self, technique_id: str) -> str:
        """Resolve a technique ID to its category."""
        try:
            import sat.techniques  # noqa: F401
            from sat.techniques.registry import get_technique

            return get_technique(technique_id).metadata.category
        except (ValueError, ImportError):
            return "unknown"

    def _build_context(self) -> dict:
        """Build the Jinja2 template context from manifest and artifacts."""
        # Load synthesis result
        synthesis = None
        # Find synthesis artifact — match by technique_id pattern (synthesis or SYNTHESIS-*)
        for artifact in self.manifest.artifacts:
            if _is_synthesis_artifact(artifact.technique_id) and artifact.json_path:
                try:
                    synthesis = self._load_artifact(artifact.json_path)
                    break
                except Exception:
                    logger.debug("Could not load synthesis from %s", artifact.json_path)
        # Fallback: try loading from synthesis_path in manifest.
        # New manifests store the .json path directly; old manifests stored the .md path.
        # .with_suffix(".json") is a no-op for .json paths and converts .md paths to .json —
        # preserving backward compatibility with runs produced before this fix.
        if synthesis is None and self.manifest.synthesis_path:
            synth_json = Path(self.manifest.synthesis_path).with_suffix(".json")
            for candidate in [synth_json, self.output_dir.parent / synth_json, self.output_dir / synth_json.name]:
                if candidate.exists():
                    try:
                        synthesis = self._load_artifact(str(candidate))
                        break
                    except Exception:
                        pass

        # Load technique artifacts
        techniques = []
        for artifact in self.manifest.artifacts:
            if not _is_technique_artifact(artifact.technique_id):
                continue
            if not artifact.json_path:
                continue
            try:
                result = self._load_artifact(artifact.json_path)
                name = self._resolve_technique_name(artifact.technique_id)
                category = self._resolve_technique_category(artifact.technique_id)
                rendered = render_technique(artifact.technique_id, result)
                description = TECHNIQUE_DESCRIPTIONS.get(artifact.technique_id, "")
                techniques.append({
                    "id": artifact.technique_id,
                    "name": name,
                    "category": category,
                    "anchor": _slugify(name),
                    "description": description,
                    "rendered_content": rendered,
                    "summary": result.summary or "",
                })
            except Exception:
                logger.exception("Failed to load artifact %s", artifact.technique_id)

        # Build synthesis fields with defaults
        bottom_line = ""
        key_findings = []
        convergent_judgments = []
        divergent_signals = []
        highest_confidence = []
        remaining_uncertainties = []
        recommended_next_steps = []
        intelligence_gaps = []

        if synthesis and hasattr(synthesis, "bottom_line_assessment"):
            synth_data = synthesis.model_dump()
            bottom_line = synth_data.get("bottom_line_assessment", "") or ""
            key_findings = synth_data.get("key_findings", []) or []
            convergent_judgments = synth_data.get("convergent_judgments", []) or []
            divergent_signals = synth_data.get("divergent_signals", []) or []
            highest_confidence = synth_data.get("highest_confidence_assessments", []) or []
            remaining_uncertainties = synth_data.get("remaining_uncertainties", []) or []
            recommended_next_steps = synth_data.get("recommended_next_steps", []) or []
            intelligence_gaps = synth_data.get("intelligence_gaps", []) or []

        # Computed fields for intelligence brief
        high_confidence_findings = [f for f in key_findings if f.get("confidence") == "High"]
        medium_confidence_findings = [f for f in key_findings if f.get("confidence") == "Medium"]
        low_confidence_findings = [f for f in key_findings if f.get("confidence") == "Low"]

        confidence_distribution = {
            "High": len(high_confidence_findings),
            "Medium": len(medium_confidence_findings),
            "Low": len(low_confidence_findings),
        }

        total_techniques = len(self.manifest.techniques_completed)

        # Build artifact index for appendix
        artifact_index = []
        for artifact in self.manifest.artifacts:
            artifact_index.append({
                "technique_id": artifact.technique_id,
                "technique_name": artifact.technique_name,
                "category": artifact.category,
                "markdown_path": artifact.markdown_path,
                "json_path": artifact.json_path or "",
            })

        now = datetime.now(timezone.utc)
        completed = self.manifest.completed_at or now

        return {
            "question": self.manifest.question,
            "run_id": self.manifest.run_id,
            "date": completed.strftime("%Y-%m-%d"),
            "datetime": completed.strftime("%Y-%m-%d %H:%M UTC"),
            "bottom_line_assessment": bottom_line,
            "key_findings": key_findings,
            "high_confidence_findings": high_confidence_findings,
            "medium_confidence_findings": medium_confidence_findings,
            "low_confidence_findings": low_confidence_findings,
            "confidence_distribution": confidence_distribution,
            "total_techniques": total_techniques,
            "convergent_judgments": convergent_judgments,
            "divergent_signals": divergent_signals,
            "highest_confidence_assessments": highest_confidence,
            "remaining_uncertainties": remaining_uncertainties,
            "recommended_next_steps": recommended_next_steps,
            "intelligence_gaps": intelligence_gaps,
            "techniques": techniques,
            "artifacts": artifact_index,
            "techniques_completed": len(self.manifest.techniques_completed),
            "techniques_selected": len(self.manifest.techniques_selected),
            "evidence_provided": self.manifest.evidence_provided,
            "adversarial_enabled": self.manifest.adversarial_enabled,
            "category_descriptions": CATEGORY_DESCRIPTIONS,
            "technique_descriptions": TECHNIQUE_DESCRIPTIONS,
        }

    def write(self, fmt: str = "both") -> list[Path]:
        """Render and write report files.

        Args:
            fmt: "markdown", "html", or "both"

        Returns:
            List of paths to generated files.
        """
        context = self._build_context()
        # @decision DEC-TEMPLATE-003
        # Custom dir searched first so user templates shadow bundled defaults.
        # Checked at each write() call — no restart required after upload.
        default_dir = get_resource_path(__file__, "templates")
        custom_dir = Path.home() / ".sat" / "templates"
        search_path: list[str] = []
        if custom_dir.exists() and custom_dir.is_dir():
            search_path.append(str(custom_dir))
        search_path.append(str(default_dir))
        env = Environment(
            loader=FileSystemLoader(search_path),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        env.filters["basename"] = _basename
        env.filters["slugify"] = _slugify
        env.filters["md"] = lambda text: markdown_lib.markdown(
            text,
            extensions=["tables", "fenced_code"],
        )
        env.filters["md_inline"] = (
            lambda text: markdown_lib.markdown(text, extensions=["tables"])
            .removeprefix("<p>")
            .removesuffix("</p>")
            .strip()
            if text
            else ""
        )

        paths: list[Path] = []

        if fmt in ("markdown", "both"):
            template = env.get_template("report.md.j2")
            md_content = template.render(**context)
            md_path = self.output_dir / "report.md"
            md_path.write_text(md_content, encoding="utf-8")
            paths.append(md_path)

        if fmt in ("html", "both"):
            template = env.get_template("report.html.j2")
            html_content = template.render(**context)
            html_path = self.output_dir / "report.html"
            html_path.write_text(html_content, encoding="utf-8")
            paths.append(html_path)

        return paths

    def _build_llm_context(self) -> dict:
        """Build the context dict for the LLM report prompt.

        Returns a dict with:
            - question: str — the analytic question
            - synthesis: dict | None — serialized synthesis result
            - technique_artifacts: list[dict] — each has 'id', 'name', 'data'
            - evidence: str | None — evidence string from manifest metadata
        """
        # Load synthesis result
        synthesis_data: dict | None = None
        for artifact in self.manifest.artifacts:
            if _is_synthesis_artifact(artifact.technique_id) and artifact.json_path:
                try:
                    result = self._load_artifact(artifact.json_path)
                    synthesis_data = result.model_dump()
                    break
                except Exception:
                    logger.debug("Could not load synthesis for LLM context from %s", artifact.json_path)

        # Collect full technique artifact JSONs
        technique_artifacts: list[dict] = []
        for artifact in self.manifest.artifacts:
            if not _is_technique_artifact(artifact.technique_id):
                continue
            if not artifact.json_path:
                continue
            try:
                result = self._load_artifact(artifact.json_path)
                name = self._resolve_technique_name(artifact.technique_id)
                technique_artifacts.append({
                    "id": artifact.technique_id,
                    "name": name,
                    "data": result.model_dump(),
                })
            except Exception:
                logger.debug("Could not load artifact %s for LLM context", artifact.technique_id)

        # @decision DEC-REPORT-006: Read evidence.txt from output_dir for report context.
        # Pipeline writes evidence.txt after all transformations (DEC-PIPE-005).
        # Reading from disk avoids bloating manifest.json with large evidence strings.
        evidence_text: str | None = None
        evidence_path = self.output_dir / "evidence.txt"
        if evidence_path.exists():
            try:
                evidence_text = evidence_path.read_text(encoding="utf-8")
            except Exception:
                logger.debug("Could not read evidence.txt from %s", evidence_path)

        return {
            "question": self.manifest.question,
            "synthesis": synthesis_data,
            "technique_artifacts": technique_artifacts,
            "evidence": evidence_text,
        }

    async def write_llm(self, provider: "LLMProvider", fmt: str = "both") -> list[Path]:
        """Generate report using an LLM provider, falling back to Jinja2 on failure.

        Sends the full structured context (synthesis, technique artifact JSONs, question)
        to the LLM provider and saves the generated prose as report.md and/or report.html.
        The HTML output wraps the rendered markdown in the same CSS as report.html.j2.

        Args:
            provider: LLM provider instance with a generate() method.
            fmt: "markdown", "html", or "both"

        Returns:
            List of paths to generated files (same contract as write()).
        """
        try:
            from sat.prompts.report import build_prompt

            ctx = self._build_llm_context()
            system_prompt, messages = build_prompt(ctx)

            result = await provider.generate(
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=4096,
                temperature=0.4,
            )
            report_md = result.text

        except Exception:
            logger.warning(
                "LLM report generation failed — falling back to Jinja2 template",
                exc_info=True,
            )
            return self.write(fmt=fmt)

        paths: list[Path] = []

        if fmt in ("markdown", "both"):
            md_path = self.output_dir / "report.md"
            md_path.write_text(report_md, encoding="utf-8")
            paths.append(md_path)

        if fmt in ("html", "both"):
            html_path = self.output_dir / "report.html"
            html_content = self._wrap_markdown_as_html(report_md)
            html_path.write_text(html_content, encoding="utf-8")
            paths.append(html_path)

        return paths

    def _wrap_markdown_as_html(self, markdown_text: str) -> str:
        """Convert LLM-generated markdown to a self-contained HTML document.

        Renders markdown to HTML and wraps it in the same CSS as report.html.j2,
        producing a visually consistent self-contained report file.

        Args:
            markdown_text: The markdown content to render.

        Returns:
            A complete HTML document string.
        """
        body_html = markdown_lib.markdown(
            markdown_text,
            extensions=["tables", "fenced_code"],
        )

        # Read the CSS block from the existing HTML template (lines between <style> and </style>)
        template_path = get_resource_path(__file__, "templates/report.html.j2")
        css_block = self._extract_css_from_template(template_path)

        question_escaped = self.manifest.question.replace("<", "&lt;").replace(">", "&gt;")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{question_escaped} — Intelligence Assessment</title>
<style>
{css_block}
</style>
</head>
<body>
<div class="container">
<div class="report-content">
{body_html}
</div>
<div class="footer">
  <p>Generated by Gabo &mdash; LLM Intelligence Assessment</p>
</div>
</div>
<script>
window.addEventListener('beforeprint', function() {{
  document.querySelectorAll('details').forEach(function(d) {{ d.open = true; }});
}});
</script>
</body>
</html>"""

    @staticmethod
    def _extract_css_from_template(template_path: Path) -> str:
        """Extract the CSS content between <style> and </style> from an HTML template.

        Args:
            template_path: Path to the Jinja2 HTML template file.

        Returns:
            The raw CSS text (without the <style> tags themselves).
        """
        try:
            content = template_path.read_text(encoding="utf-8")
            start = content.find("<style>")
            end = content.find("</style>")
            if start != -1 and end != -1:
                return content[start + len("<style>"):end]
        except Exception:
            logger.debug("Could not extract CSS from template %s", template_path)
        # Minimal fallback CSS if template extraction fails
        return """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       font-size: 16px; line-height: 1.7; color: #1f2937; background: #fff; margin: 0; }
.container { max-width: 54rem; margin: 0 auto; padding: 2rem 1.5rem; }
h1 { font-size: 2rem; } h2 { font-size: 1.5rem; border-bottom: 2px solid #e5e7eb; }
p { margin: 0 0 1rem; }
"""
