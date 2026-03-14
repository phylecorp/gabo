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
"""

from __future__ import annotations

import functools
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import markdown as markdown_lib
from jinja2 import Environment, FileSystemLoader

from sat.models.base import ArtifactManifest, ArtifactResult
from sat.report.descriptions import CATEGORY_DESCRIPTIONS, TECHNIQUE_DESCRIPTIONS
from sat.report.renderers import render_technique

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
        # Fallback: try loading from synthesis_path in manifest
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
        template_dir = Path(__file__).parent / "templates"
        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
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
