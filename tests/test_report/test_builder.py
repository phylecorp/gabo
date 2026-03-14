"""Tests for ReportBuilder.

@decision DEC-TEST-REPORT-001
@title Report builder integration tests with fixture data
@status accepted
@rationale End-to-end tests verify that the builder correctly loads manifest.json,
deserializes artifacts to the correct Pydantic models, renders technique sections,
and produces valid markdown and HTML output. Uses tmp_path fixtures with synthetic
manifests and JSON artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sat.models.base import ArtifactManifest, Artifact, ArtifactResult
from sat.models.assumptions import AssumptionRow, KeyAssumptionsResult
from sat.models.ach import ACHResult, ACHHypothesis, ACHEvidence, ACHRating
from sat.models.synthesis import SynthesisResult, TechniqueFinding
from sat.report.builder import ReportBuilder


def _create_manifest(output_dir: Path, artifacts: list[Artifact], **kwargs) -> Path:
    """Helper to write a manifest.json for testing."""
    manifest = ArtifactManifest(
        question="Will AI transform healthcare?",
        run_id="test123",
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


def _write_json_artifact(output_dir: Path, filename: str, result: ArtifactResult) -> str:
    """Write a JSON artifact and return the path string."""
    path = output_dir / filename
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return str(path)


class TestReportBuilder:
    """ReportBuilder should load manifest and generate reports."""

    def _setup_minimal(self, tmp_path):
        """Create a minimal output directory with one technique and synthesis."""
        output_dir = tmp_path / "sat-test123"
        output_dir.mkdir()

        # Write assumptions artifact
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
        assumptions_json = _write_json_artifact(output_dir, "01-assumptions.json", assumptions)

        # Write synthesis
        synthesis = SynthesisResult(
            technique_id="synthesis",
            technique_name="Synthesis",
            summary="Cross-technique synthesis.",
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
        synthesis_json = _write_json_artifact(output_dir, "02-synthesis.json", synthesis)

        artifacts = [
            Artifact(
                technique_id="assumptions",
                technique_name="Key Assumptions Check",
                category="diagnostic",
                markdown_path=str(output_dir / "01-assumptions.md"),
                json_path=assumptions_json,
            ),
            Artifact(
                technique_id="synthesis",
                technique_name="Synthesis",
                category="synthesis",
                markdown_path=str(output_dir / "02-synthesis.md"),
                json_path=synthesis_json,
            ),
        ]
        _create_manifest(
            output_dir,
            artifacts,
            synthesis_path=str(output_dir / "02-synthesis.md"),
            techniques_completed=["assumptions"],
        )
        return output_dir

    def test_loads_manifest(self, tmp_path):
        """Builder should load manifest.json successfully."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        assert builder.manifest.run_id == "test123"
        assert builder.manifest.question == "Will AI transform healthcare?"

    def test_raises_if_no_manifest(self, tmp_path):
        """Builder should raise FileNotFoundError if manifest is missing."""
        with pytest.raises(FileNotFoundError):
            ReportBuilder(tmp_path)

    def test_write_markdown(self, tmp_path):
        """write(fmt='markdown') should produce report.md."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="markdown")

        assert len(paths) == 1
        md_path = paths[0]
        assert md_path.name == "report.md"
        assert md_path.exists()

        content = md_path.read_text()
        assert "Will AI transform healthcare?" in content
        assert "Executive Summary" in content
        assert "AI will transform healthcare, but slower" in content

    def test_write_html(self, tmp_path):
        """write(fmt='html') should produce report.html."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="html")

        assert len(paths) == 1
        html_path = paths[0]
        assert html_path.name == "report.html"
        assert html_path.exists()

        content = html_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "Will AI transform healthcare?" in content
        assert "Executive Summary" in content

    def test_write_both(self, tmp_path):
        """write(fmt='both') should produce both report.md and report.html."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="both")

        assert len(paths) == 2
        names = {p.name for p in paths}
        assert "report.md" in names
        assert "report.html" in names

    def test_markdown_has_technique_details(self, tmp_path):
        """Markdown report should include Methods Used section with technique names."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="markdown")

        content = paths[0].read_text()
        assert "Methods Used" in content
        assert "Key Assumptions Check" in content

    def test_markdown_has_key_findings(self, tmp_path):
        """Markdown report should include key findings with confidence."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="markdown")

        content = paths[0].read_text()
        assert "[MODERATE]" in content
        assert "Rapid adoption" in content

    def test_markdown_has_convergence(self, tmp_path):
        """Markdown report should include convergent judgments."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="markdown")

        content = paths[0].read_text()
        assert "Points of Agreement" in content
        assert "All techniques agree" in content

    def test_html_has_confidence_badges(self, tmp_path):
        """HTML report should include confidence badge spans."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="html")

        content = paths[0].read_text()
        assert "badge-medium" in content
        assert "MODERATE" in content

    def test_html_has_embedded_css(self, tmp_path):
        """HTML should be self-contained with embedded CSS."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="html")

        content = paths[0].read_text()
        assert "<style>" in content
        assert "font-family" in content

    def test_excludes_adversarial_artifacts(self, tmp_path):
        """Report should not include adversarial critique/rebuttal artifacts in Methods Used."""
        output_dir = self._setup_minimal(tmp_path)

        # Add adversarial artifacts to manifest
        critique = ArtifactResult(
            technique_id="assumptions-critique",
            technique_name="Critique",
            summary="Challenge.",
        )
        critique_json = _write_json_artifact(output_dir, "03-assumptions-critique.json", critique)

        # Reload manifest with adversarial artifact
        manifest_data = json.loads((output_dir / "manifest.json").read_text())
        manifest_data["artifacts"].append({
            "technique_id": "assumptions-critique",
            "technique_name": "Critique",
            "category": "adversarial",
            "markdown_path": str(output_dir / "03-assumptions-critique.md"),
            "json_path": critique_json,
        })
        (output_dir / "manifest.json").write_text(json.dumps(manifest_data, indent=2))

        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="markdown")
        content = paths[0].read_text()
        # Methods Used section should not include adversarial artifacts
        # (they may appear in the Artifact Index appendix, which is expected)
        technique_section = content.split("## Methods Used")[1].split("## Appendix")[0]
        assert "assumptions-critique" not in technique_section
        assert "Critique" not in technique_section

    def _setup_with_ach(self, tmp_path):
        """Create an output directory with an ACH artifact that has a diagnosticity matrix."""
        output_dir = tmp_path / "sat-ach123"
        output_dir.mkdir()

        ach = ACHResult(
            technique_id="ach",
            technique_name="Analysis of Competing Hypotheses",
            summary="Two hypotheses evaluated.",
            hypotheses=[
                ACHHypothesis(id="H1", description="Hypothesis one is correct"),
                ACHHypothesis(id="H2", description="Hypothesis two is correct"),
            ],
            evidence=[
                ACHEvidence(id="E1", description="First evidence item shows X", credibility="High", relevance="High"),
                ACHEvidence(id="E2", description="Second evidence item shows Y", credibility="Medium", relevance="Medium"),
            ],
            matrix=[
                ACHRating(evidence_id="E1", hypothesis_id="H1", rating="C", explanation="Consistent"),
                ACHRating(evidence_id="E1", hypothesis_id="H2", rating="I", explanation="Inconsistent"),
                ACHRating(evidence_id="E2", hypothesis_id="H1", rating="N", explanation="Neutral"),
                ACHRating(evidence_id="E2", hypothesis_id="H2", rating="C", explanation="Consistent"),
            ],
            most_likely="H1",
        )
        ach_json = _write_json_artifact(output_dir, "01-ach.json", ach)

        artifacts = [
            Artifact(
                technique_id="ach",
                technique_name="Analysis of Competing Hypotheses",
                category="diagnostic",
                markdown_path=str(output_dir / "01-ach.md"),
                json_path=ach_json,
            ),
        ]
        _create_manifest(output_dir, artifacts, techniques_selected=["ach"], techniques_completed=["ach"])
        return output_dir

    def test_html_has_rendered_tables(self, tmp_path):
        """HTML output should contain <table> elements from markdown rendering (not raw pipe chars)."""
        output_dir = self._setup_with_ach(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="html")
        html = paths[0].read_text()
        # ACH has a diagnosticity matrix table; it should render as HTML <table>, not raw markdown
        assert "<table>" in html or "<th>" in html
        # Raw pipe characters for table rows should NOT appear in the technique-content section
        # (they could appear in other parts, so we check the technique content specifically)
        assert "| H1 | H2 |" not in html

    def test_context_has_confidence_distribution(self, tmp_path):
        """Builder context should include confidence_distribution computed field."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        context = builder._build_context()
        assert "confidence_distribution" in context
        dist = context["confidence_distribution"]
        assert dist == {"High": 0, "Medium": 1, "Low": 0}

    def test_html_has_key_assessment_section(self, tmp_path):
        """HTML report should include the Key Assessment section."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="html")
        content = paths[0].read_text()
        assert 'id="key-assessment"' in content
        assert "Key Assessment" in content
        assert "Supporting Evidence" in content

    def test_html_has_challenges_section(self, tmp_path):
        """HTML report should include the Challenges to This View section."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="html")
        content = paths[0].read_text()
        assert 'id="challenges"' in content
        assert "Challenges to This View" in content

    def test_html_has_confidence_assessment(self, tmp_path):
        """HTML report should include confidence section with distribution bar."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="html")
        content = paths[0].read_text()
        assert 'id="confidence"' in content
        assert "confidence-bar" in content

    def test_html_has_methods_section(self, tmp_path):
        """HTML report should include the Methods Used section."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="html")
        content = paths[0].read_text()
        assert 'id="methods"' in content
        assert "Methods Used" in content

    def test_html_has_dark_mode(self, tmp_path):
        """HTML report should include dark mode CSS."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="html")
        content = paths[0].read_text()
        assert "prefers-color-scheme: dark" in content

    def test_context_has_technique_summary(self, tmp_path):
        """Each technique dict in context should have a 'summary' key."""
        output_dir = self._setup_minimal(tmp_path)
        builder = ReportBuilder(output_dir)
        context = builder._build_context()
        for t in context["techniques"]:
            assert "summary" in t, f"Technique {t.get('id')} missing 'summary' key"

    def test_no_synthesis_produces_placeholder(self, tmp_path):
        """Report without synthesis should show placeholder for BLUF."""
        output_dir = tmp_path / "sat-nosyn"
        output_dir.mkdir()

        result = ArtifactResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="One technique only.",
        )
        json_path = _write_json_artifact(output_dir, "01-assumptions.json", result)

        artifacts = [
            Artifact(
                technique_id="assumptions",
                technique_name="Key Assumptions Check",
                category="diagnostic",
                markdown_path=str(output_dir / "01-assumptions.md"),
                json_path=json_path,
            ),
        ]
        _create_manifest(output_dir, artifacts, techniques_completed=["assumptions"])

        builder = ReportBuilder(output_dir)
        paths = builder.write(fmt="markdown")
        content = paths[0].read_text()
        assert "fewer than 2 techniques completed" in content


class TestGenerateReportFunction:
    """Test the public API generate_report()."""

    def test_generate_report(self, tmp_path):
        """generate_report() should produce report files."""
        output_dir = tmp_path / "sat-api"
        output_dir.mkdir()

        result = KeyAssumptionsResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Test.",
            analytic_line="Test line.",
        )
        json_path = _write_json_artifact(output_dir, "01-assumptions.json", result)

        artifacts = [
            Artifact(
                technique_id="assumptions",
                technique_name="Key Assumptions Check",
                category="diagnostic",
                markdown_path=str(output_dir / "01-assumptions.md"),
                json_path=json_path,
            ),
        ]
        _create_manifest(output_dir, artifacts)

        from sat.report import generate_report

        paths = generate_report(output_dir, fmt="both")
        assert len(paths) == 2
        assert all(p.exists() for p in paths)
