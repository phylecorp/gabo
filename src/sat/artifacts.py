"""Artifact writer: produces Markdown + JSON files for each technique result.

@decision DEC-ART-001: Numbered .md + .json + manifest.json output format.
Each technique produces {nn}-{technique-id}.md and {nn}-{technique-id}.json.
Numbering reflects execution order. The Markdown file is human-readable; the
JSON file is machine-readable and round-trips through the Pydantic model.
manifest.json records the full run metadata.

@decision DEC-ART-002: ACH-specific markdown renderer for diagnosticity matrix.
The generic _render_markdown produces bullet-list output that obscures the
core ACH matrix structure. A dedicated _render_ach_markdown function produces
proper markdown tables — hypotheses, evidence, and the full diagnosticity matrix
with one column per hypothesis plus a computed Diagnostic Value column. Diagnostic
Value is HIGH when ratings differ across hypotheses (the evidence discriminates),
LOW when all ratings are the same (the evidence doesn't discriminate). The
isinstance dispatch in _render_markdown keeps callers unaware of the specialisation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sat.models.ach import ACHResult
from sat.models.base import Artifact, ArtifactManifest, ArtifactResult
from sat.models.synthesis import SynthesisResult
from sat.techniques.registry import get_technique

# Adversarial result types for category detection
_ADVERSARIAL_SUFFIXES = ("-critique", "-rebuttal", "-adjudication", "-investigator", "-convergence")


def _ach_diagnostic_value(ratings: list[str]) -> str:
    """Compute diagnostic value for one evidence row.

    Returns "HIGH" if ratings differ across hypotheses (the evidence
    discriminates between them), "LOW" if all ratings are identical.
    An empty or single-hypothesis row is LOW by convention.
    """
    if len(set(ratings)) > 1:
        return "HIGH"
    return "LOW"


def _render_ach_markdown(result: ACHResult) -> str:
    """Render an ACHResult as a Markdown document with proper diagnosticity tables.

    Produces:
    - A hypotheses table (ID, Hypothesis)
    - An evidence table (ID, Description, Credibility, Relevance)
    - A diagnosticity matrix table (Evidence | H1 | H2 | ... | Diagnostic Value)
    - An inconsistency scores table (Hypothesis, Score, Assessment)
    - Most Likely, Rejected, Diagnosticity Notes, Missing Evidence sections
    """
    lines: list[str] = [
        f"# {result.technique_name}",
        "",
        f"**Technique:** {result.technique_id}",
        "",
        "## Summary",
        "",
        result.summary,
        "",
    ]

    # --- Hypotheses table ---
    lines += ["## Hypotheses", ""]
    if result.hypotheses:
        lines += [
            "| ID | Hypothesis |",
            "|----|------------|",
        ]
        for h in result.hypotheses:
            lines.append(f"| {h.id} | {h.description} |")
    else:
        lines.append("_No hypotheses recorded._")
    lines.append("")

    # --- Evidence table ---
    lines += ["## Evidence", ""]
    if result.evidence:
        lines += [
            "| ID | Description | Credibility | Relevance |",
            "|----|-------------|-------------|-----------|",
        ]
        for e in result.evidence:
            lines.append(f"| {e.id} | {e.description} | {e.credibility} | {e.relevance} |")
    else:
        lines.append("_No evidence recorded._")
    lines.append("")

    # --- Diagnosticity matrix ---
    lines += ["## Diagnosticity Matrix", ""]
    if result.hypotheses and result.evidence and result.matrix:
        hyp_ids = [h.id for h in result.hypotheses]
        # Index ratings by (evidence_id, hypothesis_id) for O(1) lookup
        rating_index: dict[tuple[str, str], str] = {
            (r.evidence_id, r.hypothesis_id): r.rating for r in result.matrix
        }

        # Header
        hyp_cols = " | ".join(hyp_ids)
        lines.append(f"| Evidence | {hyp_cols} | Diagnostic Value |")
        sep_cols = " | ".join("----" for _ in hyp_ids)
        lines.append(f"|----------|{sep_cols}|-----------------:|")

        for e in result.evidence:
            row_ratings = [rating_index.get((e.id, h_id), "—") for h_id in hyp_ids]
            # Only include real rating values when computing diagnostic value
            real_ratings = [r for r in row_ratings if r != "—"]
            diag = _ach_diagnostic_value(real_ratings) if real_ratings else "LOW"
            cell_text = f"| {e.id}: {e.description} | " + " | ".join(row_ratings) + f" | {diag} |"
            lines.append(cell_text)
    else:
        lines.append("_No matrix data recorded._")
    lines.append("")

    # --- Inconsistency scores table ---
    lines += ["## Inconsistency Scores", ""]
    if result.inconsistency_scores:
        lines += [
            "| Hypothesis | Score | Assessment |",
            "|------------|------:|------------|",
        ]
        sorted_scores = sorted(result.inconsistency_scores.items(), key=lambda kv: kv[1])
        n = len(sorted_scores)
        for i, (h_id, score) in enumerate(sorted_scores):
            if i == n - 1 and n > 1:
                assessment = "Most inconsistent"
            elif i == 0 and n > 1:
                assessment = "Least inconsistent"
            else:
                assessment = ""
            lines.append(f"| {h_id} | {score:.2f} | {assessment} |")
    else:
        lines.append("_Inconsistency scores not yet computed._")
    lines.append("")

    # --- Most Likely ---
    lines += ["## Most Likely", ""]
    if result.most_likely:
        # Look up description for the most-likely hypothesis
        hyp_map = {h.id: h.description for h in result.hypotheses}
        desc = hyp_map.get(result.most_likely, "")
        if desc:
            lines.append(f"{result.most_likely} — {desc}")
        else:
            lines.append(result.most_likely)
    else:
        lines.append("_Not determined._")
    lines.append("")

    # --- Rejected ---
    lines += ["## Rejected", ""]
    if result.rejected:
        hyp_map = {h.id: h.description for h in result.hypotheses}
        # Count inconsistency ratings per rejected hypothesis
        incon_counts: dict[str, int] = {}
        for r in result.matrix:
            if r.rating == "I":
                incon_counts[r.hypothesis_id] = incon_counts.get(r.hypothesis_id, 0) + 1
        for h_id in result.rejected:
            desc = hyp_map.get(h_id, "")
            count = incon_counts.get(h_id, 0)
            if desc and count:
                lines.append(
                    f"- {h_id} — {desc} ({count} inconsistenc{'y' if count == 1 else 'ies'})"
                )
            elif desc:
                lines.append(f"- {h_id} — {desc}")
            else:
                lines.append(f"- {h_id}")
    else:
        lines.append("_None rejected._")
    lines.append("")

    # --- Diagnosticity Notes ---
    lines += ["## Diagnosticity Notes", ""]
    if result.diagnosticity_notes:
        lines.append(result.diagnosticity_notes)
    else:
        lines.append("_Not provided._")
    lines.append("")

    # --- Missing Evidence ---
    lines += ["## Missing Evidence", ""]
    if result.missing_evidence:
        for item in result.missing_evidence:
            lines.append(f"- {item}")
    else:
        lines.append("_None identified._")
    lines.append("")

    return "\n".join(lines)


def _render_markdown(result: ArtifactResult) -> str:
    """Render an ArtifactResult as a Markdown document."""
    if isinstance(result, ACHResult):
        return _render_ach_markdown(result)

    lines = [
        f"# {result.technique_name}",
        "",
        f"**Technique:** {result.technique_id}",
        "",
        "## Summary",
        "",
        result.summary,
        "",
    ]

    # Render all fields except the base ones
    base_fields = {"technique_id", "technique_name", "summary"}
    for name, field_info in type(result).model_fields.items():
        if name in base_fields:
            continue
        value = getattr(result, name)
        title = name.replace("_", " ").title()
        lines.append(f"## {title}")
        lines.append("")
        lines.extend(_render_value(value))
        lines.append("")

    return "\n".join(lines)


def _render_value(value: object, indent: int = 0) -> list[str]:
    """Render a field value as Markdown lines."""
    prefix = "  " * indent

    if isinstance(value, str):
        return [f"{prefix}{value}"]

    if isinstance(value, bool):
        return [f"{prefix}{'Yes' if value else 'No'}"]

    if isinstance(value, (int, float)):
        return [f"{prefix}{value}"]

    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, str):
                lines.append(f"{prefix}- {item}")
            elif hasattr(item, "model_dump"):
                lines.extend(_render_model(item, indent))
                lines.append("")
            else:
                lines.append(f"{prefix}- {item}")
        return lines

    if isinstance(value, dict):
        lines = []
        for k, v in value.items():
            lines.append(f"{prefix}- **{k}**: {v}")
        return lines

    if hasattr(value, "model_dump"):
        return _render_model(value, indent)

    return [f"{prefix}{value}"]


def _render_model(model: object, indent: int = 0) -> list[str]:
    """Render a Pydantic model as Markdown."""
    lines = []
    prefix = "  " * indent
    data = model.model_dump()  # type: ignore[union-attr]
    for key, val in data.items():
        title = key.replace("_", " ").title()
        if isinstance(val, str):
            lines.append(f"{prefix}- **{title}**: {val}")
        elif isinstance(val, list):
            lines.append(f"{prefix}- **{title}**:")
            for item in val:
                lines.append(f"{prefix}  - {item}")
        else:
            lines.append(f"{prefix}- **{title}**: {val}")
    return lines


class ArtifactWriter:
    """Writes technique results as Markdown + JSON artifacts to disk."""

    def __init__(self, output_dir: Path, run_id: str, question: str, name: str | None = None) -> None:
        self.output_dir = output_dir
        self.run_id = run_id
        self.question = question
        self.name = name
        self._counter = 0
        self._artifacts: list[Artifact] = []
        self._started_at = datetime.now(timezone.utc)

    def write_result(self, result: ArtifactResult) -> Artifact:
        """Write a technique result as .md and .json files.

        Returns the Artifact record.
        """
        self._counter += 1
        prefix = f"{self._counter:02d}-{result.technique_id}"

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Write Markdown
        md_path = self.output_dir / f"{prefix}.md"
        md_content = _render_markdown(result)
        md_path.write_text(md_content, encoding="utf-8")

        # Write JSON
        json_path = self.output_dir / f"{prefix}.json"
        json_path.write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # Determine category
        category = "synthesis"
        if any(result.technique_id.endswith(s) for s in _ADVERSARIAL_SUFFIXES):
            category = "adversarial"
        else:
            try:
                technique = get_technique(result.technique_id)
                category = technique.metadata.category
            except ValueError:
                if isinstance(result, SynthesisResult):
                    category = "synthesis"

        artifact = Artifact(
            technique_id=result.technique_id,
            technique_name=result.technique_name,
            category=category,
            markdown_path=str(md_path),
            json_path=str(json_path),
        )
        self._artifacts.append(artifact)
        return artifact

    def get_technique_artifacts(self) -> list[Artifact]:
        """Return artifacts for core technique results only.

        Filters out adversarial artifacts (critique, rebuttal, adjudication),
        revised artifacts, preprocessing, research, and synthesis — leaving
        only the primary technique outputs suitable for user-facing listings.
        """
        _REVISED_SUFFIX = "-revised"
        _NON_TECHNIQUE_IDS = {"preprocessing", "research", "synthesis", "verification"}
        return [
            a
            for a in self._artifacts
            if not any(a.technique_id.endswith(s) for s in _ADVERSARIAL_SUFFIXES)
            and not a.technique_id.endswith(_REVISED_SUFFIX)
            and a.technique_id not in _NON_TECHNIQUE_IDS
        ]

    def write_manifest(
        self,
        techniques_selected: list[str],
        techniques_completed: list[str],
        evidence_provided: bool,
        synthesis_path: str | None = None,
        adversarial_enabled: bool = False,
        providers_used: list[str] | None = None,
    ) -> Path:
        """Write the manifest.json summarizing the run."""
        manifest = ArtifactManifest(
            question=self.question,
            name=self.name,
            run_id=self.run_id,
            started_at=self._started_at,
            completed_at=datetime.now(timezone.utc),
            techniques_selected=techniques_selected,
            techniques_completed=techniques_completed,
            artifacts=self._artifacts,
            synthesis_path=synthesis_path,
            evidence_provided=evidence_provided,
            adversarial_enabled=adversarial_enabled,
            providers_used=providers_used or [],
        )

        manifest_path = self.output_dir / "manifest.json"
        manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return manifest_path
