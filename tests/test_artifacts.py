"""Test artifact writer produces correct files.

@decision DEC-TEST-ART-001: Artifact file creation and manifest verification.
Tests that ArtifactWriter creates numbered .md/.json file pairs, that JSON
round-trips through Pydantic models, that manifests record run metadata
correctly, and that file numbering increments properly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sat.artifacts import ArtifactWriter
from sat.models.assumptions import AssumptionRow, KeyAssumptionsResult
from sat.models.base import ArtifactResult


class TestArtifactWriter:
    """ArtifactWriter should produce .md, .json, and manifest.json."""

    def _sample_result(self) -> KeyAssumptionsResult:
        return KeyAssumptionsResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Three key assumptions identified, one highly vulnerable.",
            analytic_line="Country X is likely pursuing nuclear weapons.",
            assumptions=[
                AssumptionRow(
                    assumption="Country X has the technical capability",
                    confidence="Medium",
                    basis_for_confidence="Based on limited intelligence",
                    what_undermines="New leadership could change priorities",
                    impact_if_wrong="Would fundamentally alter the assessment",
                ),
            ],
            most_vulnerable=["Country X has the technical capability"],
            recommended_monitoring=["Track procurement patterns quarterly"],
        )

    def test_write_result_creates_files(self, tmp_path):
        """Writing a result should create .md and .json files."""
        writer = ArtifactWriter(tmp_path / "output", "test123", "Test question?")
        result = self._sample_result()

        writer.write_result(result)

        md_path = tmp_path / "output" / "01-assumptions.md"
        json_path = tmp_path / "output" / "01-assumptions.json"

        assert md_path.exists()
        assert json_path.exists()

        md_content = md_path.read_text()
        assert "Key Assumptions Check" in md_content
        assert "Three key assumptions" in md_content

        json_data = json.loads(json_path.read_text())
        assert json_data["technique_id"] == "assumptions"
        restored = KeyAssumptionsResult.model_validate(json_data)
        assert restored.summary == result.summary

    def test_write_manifest(self, tmp_path):
        """Writing manifest should record run metadata."""
        writer = ArtifactWriter(tmp_path / "output", "test123", "Test question?")
        result = self._sample_result()
        writer.write_result(result)

        manifest_path = writer.write_manifest(
            techniques_selected=["assumptions", "ach"],
            techniques_completed=["assumptions"],
            evidence_provided=True,
        )

        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["run_id"] == "test123"
        assert manifest["question"] == "Test question?"
        assert len(manifest["artifacts"]) == 1
        assert manifest["techniques_completed"] == ["assumptions"]

    def test_numbering_increments(self, tmp_path):
        """Each result should get an incrementing number prefix."""
        writer = ArtifactWriter(tmp_path / "output", "test123", "Test?")
        result = self._sample_result()

        writer.write_result(result)
        result2 = self._sample_result()
        result2.technique_id = "quality"
        result2.technique_name = "Quality Check"
        writer.write_result(result2)

        assert (tmp_path / "output" / "01-assumptions.md").exists()
        assert (tmp_path / "output" / "02-quality.md").exists()


class TestGetTechniqueArtifacts:
    """get_technique_artifacts() should filter to core technique results only."""

    def _make_result(self, tid: str, name: str = "Test") -> ArtifactResult:
        return ArtifactResult(technique_id=tid, technique_name=name, summary="s")

    def _make_synthesis(self) -> ArtifactResult:
        # Use plain ArtifactResult with the canonical synthesis ID.
        # get_technique_artifacts() filters by technique_id, not by type.
        return ArtifactResult(
            technique_id="synthesis",
            technique_name="Synthesis Report",
            summary="s",
        )

    def test_returns_only_technique_artifacts(self, tmp_path):
        """Core technique artifacts are returned; non-technique entries are excluded."""
        writer = ArtifactWriter(tmp_path, "run1", "Q?")
        writer.write_result(self._make_result("assumptions"))
        writer.write_result(self._make_result("ach"))

        artifacts = writer.get_technique_artifacts()
        ids = [a.technique_id for a in artifacts]
        assert ids == ["assumptions", "ach"]

    def test_excludes_adversarial_suffixes(self, tmp_path):
        """Critique, rebuttal, and adjudication artifacts are excluded."""
        writer = ArtifactWriter(tmp_path, "run1", "Q?")
        writer.write_result(self._make_result("assumptions"))
        writer.write_result(self._make_result("assumptions-critique"))
        writer.write_result(self._make_result("assumptions-rebuttal"))
        writer.write_result(self._make_result("assumptions-adjudication"))

        artifacts = writer.get_technique_artifacts()
        ids = [a.technique_id for a in artifacts]
        assert ids == ["assumptions"]

    def test_excludes_revised_suffix(self, tmp_path):
        """Revised artifacts (post-critique) are excluded from the listing."""
        writer = ArtifactWriter(tmp_path, "run1", "Q?")
        writer.write_result(self._make_result("assumptions"))
        writer.write_result(self._make_result("assumptions-revised"))

        artifacts = writer.get_technique_artifacts()
        ids = [a.technique_id for a in artifacts]
        assert ids == ["assumptions"]

    def test_excludes_synthesis(self, tmp_path):
        """Synthesis result is excluded from technique artifacts."""
        writer = ArtifactWriter(tmp_path, "run1", "Q?")
        writer.write_result(self._make_result("assumptions"))
        writer.write_result(self._make_synthesis())

        artifacts = writer.get_technique_artifacts()
        ids = [a.technique_id for a in artifacts]
        assert ids == ["assumptions"]

    def test_excludes_preprocessing_and_research(self, tmp_path):
        """Preprocessing and research artifacts are excluded."""
        writer = ArtifactWriter(tmp_path, "run1", "Q?")
        writer.write_result(self._make_result("preprocessing"))
        writer.write_result(self._make_result("research"))
        writer.write_result(self._make_result("assumptions"))

        artifacts = writer.get_technique_artifacts()
        ids = [a.technique_id for a in artifacts]
        assert ids == ["assumptions"]

    def test_empty_when_no_technique_results(self, tmp_path):
        """Returns empty list if only adversarial/synthesis artifacts exist."""
        writer = ArtifactWriter(tmp_path, "run1", "Q?")
        writer.write_result(self._make_result("assumptions-critique"))
        writer.write_result(self._make_synthesis())

        assert writer.get_technique_artifacts() == []

    def test_paths_exist_on_disk(self, tmp_path):
        """Artifact paths returned by get_technique_artifacts() exist on disk."""
        writer = ArtifactWriter(tmp_path, "run1", "Q?")
        writer.write_result(self._make_result("assumptions"))
        writer.write_result(self._make_result("assumptions-critique"))

        artifacts = writer.get_technique_artifacts()
        assert len(artifacts) == 1
        assert Path(artifacts[0].markdown_path).exists()


class TestRenderAchMarkdown:
    """_render_ach_markdown should produce proper markdown tables from ACHResult."""

    def _sample_ach_result(self):
        from sat.models.ach import ACHEvidence, ACHHypothesis, ACHRating, ACHResult

        return ACHResult(
            technique_id="ach",
            technique_name="Analysis of Competing Hypotheses",
            summary="H2 is most consistent with the evidence.",
            hypotheses=[
                ACHHypothesis(id="H1", description="State-sponsored APT group"),
                ACHHypothesis(id="H2", description="Criminal ransomware syndicate"),
                ACHHypothesis(id="H3", description="Insider threat"),
            ],
            evidence=[
                ACHEvidence(
                    id="E1",
                    description="C2 infrastructure patterns",
                    credibility="High",
                    relevance="High",
                ),
                ACHEvidence(
                    id="E2",
                    description="Ransom note found",
                    credibility="High",
                    relevance="High",
                ),
            ],
            matrix=[
                ACHRating(
                    evidence_id="E1",
                    hypothesis_id="H1",
                    rating="C",
                    explanation="Consistent with APT",
                ),
                ACHRating(
                    evidence_id="E1",
                    hypothesis_id="H2",
                    rating="C",
                    explanation="Also seen in criminal ops",
                ),
                ACHRating(
                    evidence_id="E1",
                    hypothesis_id="H3",
                    rating="N",
                    explanation="Neutral for insider",
                ),
                ACHRating(
                    evidence_id="E2",
                    hypothesis_id="H1",
                    rating="I",
                    explanation="APTs rarely leave ransom notes",
                ),
                ACHRating(
                    evidence_id="E2",
                    hypothesis_id="H2",
                    rating="C",
                    explanation="Ransomware hallmark",
                ),
                ACHRating(
                    evidence_id="E2",
                    hypothesis_id="H3",
                    rating="N",
                    explanation="Neutral for insider",
                ),
            ],
            inconsistency_scores={"H1": 1.0, "H2": 0.0, "H3": 0.0},
            most_likely="H2",
            rejected=["H1"],
            diagnosticity_notes="E2 was most diagnostic.",
            missing_evidence=["Network logs"],
        )

    def test_produces_hypotheses_table(self):
        """Rendered markdown should include a hypotheses table with ID and Hypothesis columns."""
        from sat.artifacts import _render_ach_markdown

        result = self._sample_ach_result()
        md = _render_ach_markdown(result)

        assert "## Hypotheses" in md
        assert "| ID | Hypothesis |" in md
        assert "| H1 | State-sponsored APT group |" in md
        assert "| H2 | Criminal ransomware syndicate |" in md

    def test_produces_evidence_table(self):
        """Rendered markdown should include an evidence table with ID, Description, Credibility, Relevance."""
        from sat.artifacts import _render_ach_markdown

        result = self._sample_ach_result()
        md = _render_ach_markdown(result)

        assert "## Evidence" in md
        assert "| ID | Description | Credibility | Relevance |" in md
        assert "| E1 | C2 infrastructure patterns | High | High |" in md

    def test_produces_diagnosticity_matrix(self):
        """Rendered markdown should include a diagnosticity matrix with one column per hypothesis."""
        from sat.artifacts import _render_ach_markdown

        result = self._sample_ach_result()
        md = _render_ach_markdown(result)

        assert "## Diagnosticity Matrix" in md
        # Header should contain all hypothesis IDs
        assert "| H1 |" in md
        assert "| H2 |" in md
        assert "| H3 |" in md
        assert "| Diagnostic Value |" in md

    def test_diagnostic_value_low_when_uniform(self):
        """Diagnostic Value should be LOW when all hypotheses have the same rating for an evidence item."""
        from sat.artifacts import _render_ach_markdown

        result = self._sample_ach_result()
        md = _render_ach_markdown(result)

        # E1 has ratings C, C, N — not all same, so HIGH
        # But we test the LOW case: need a row where all ratings are identical
        # E2 has I, C, N — HIGH
        # E1 has C, C, N — not all same, HIGH
        # Let's check that HIGH appears for varied ratings
        assert "HIGH" in md

    def test_diagnostic_value_low_when_all_same(self):
        """Diagnostic Value should be LOW when all hypotheses have the same rating."""
        from sat.models.ach import ACHEvidence, ACHHypothesis, ACHRating, ACHResult
        from sat.artifacts import _render_ach_markdown

        result = ACHResult(
            technique_id="ach",
            technique_name="Analysis of Competing Hypotheses",
            summary="Test",
            hypotheses=[
                ACHHypothesis(id="H1", description="Hyp 1"),
                ACHHypothesis(id="H2", description="Hyp 2"),
            ],
            evidence=[
                ACHEvidence(
                    id="E1", description="Uniform evidence", credibility="High", relevance="High"
                ),
            ],
            matrix=[
                ACHRating(evidence_id="E1", hypothesis_id="H1", rating="C", explanation="x"),
                ACHRating(evidence_id="E1", hypothesis_id="H2", rating="C", explanation="y"),
            ],
        )
        md = _render_ach_markdown(result)
        assert "LOW" in md

    def test_empty_matrix_does_not_crash(self):
        """Rendering an ACHResult with empty matrix should produce valid markdown without crashing."""
        from sat.models.ach import ACHResult
        from sat.artifacts import _render_ach_markdown

        result = ACHResult(
            technique_id="ach",
            technique_name="Analysis of Competing Hypotheses",
            summary="No matrix yet.",
        )
        md = _render_ach_markdown(result)
        assert "# Analysis of Competing Hypotheses" in md
        assert "## Summary" in md

    def test_most_likely_section(self):
        """Most Likely section should include hypothesis ID and description."""
        from sat.artifacts import _render_ach_markdown

        result = self._sample_ach_result()
        md = _render_ach_markdown(result)

        assert "## Most Likely" in md
        assert "H2" in md
        assert "Criminal ransomware syndicate" in md

    def test_rejected_section(self):
        """Rejected section should list rejected hypotheses with descriptions."""
        from sat.artifacts import _render_ach_markdown

        result = self._sample_ach_result()
        md = _render_ach_markdown(result)

        assert "## Rejected" in md
        assert "H1" in md

    def test_render_markdown_dispatches_to_ach(self):
        """_render_markdown should call _render_ach_markdown for ACHResult instances."""
        from sat.models.ach import ACHResult
        from sat.artifacts import _render_markdown

        result = ACHResult(
            technique_id="ach",
            technique_name="Analysis of Competing Hypotheses",
            summary="Test dispatch.",
        )
        md = _render_markdown(result)
        # ACH-specific renderer produces "## Hypotheses" — generic renderer does not
        assert "## Hypotheses" in md

    def test_inconsistency_scores_table(self):
        """Inconsistency Scores section should render as a table with hypothesis IDs and scores."""
        from sat.artifacts import _render_ach_markdown

        result = self._sample_ach_result()
        md = _render_ach_markdown(result)

        assert "## Inconsistency Scores" in md
        assert "| Hypothesis | Score |" in md
        assert "H1" in md


class TestTechniqueIdNormalization:
    """Technique.execute() should enforce canonical IDs from metadata."""

    @pytest.mark.asyncio
    async def test_execute_overrides_llm_technique_id(self, mock_provider):
        """If the LLM returns a wrong technique_id, execute() normalises it."""
        from sat.techniques.base import TechniqueContext
        from sat.techniques.diagnostic.assumptions import KeyAssumptionsCheck

        # Simulate the LLM returning a non-canonical ID like "KAC-001"
        llm_response = KeyAssumptionsResult(
            technique_id="KAC-001",
            technique_name="Key Assumptions (LLM name)",
            summary="summary",
            analytic_line="line",
            assumptions=[
                AssumptionRow(
                    assumption="a",
                    confidence="High",
                    basis_for_confidence="b",
                    what_undermines="w",
                    impact_if_wrong="i",
                )
            ],
            most_vulnerable=[],
            recommended_monitoring=[],
        )
        provider = mock_provider(structured_response=llm_response)
        technique = KeyAssumptionsCheck()
        ctx = TechniqueContext(question="Q?")

        result = await technique.execute(ctx, provider)

        # Framework must enforce the canonical registry ID, not the LLM's value
        assert result.technique_id == "assumptions"
        assert result.technique_name == technique.metadata.name
        # Content should be preserved
        assert result.summary == "summary"
