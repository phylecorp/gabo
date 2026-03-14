"""Integration tests for pipeline ingestion and decomposition phases.

@decision DEC-INGEST-004: Single entry point classifies and routes sources.
@title Tests for pipeline ingestion and decomposition phase wiring
@status accepted
@rationale Verifies that the ingestion and decomposition phases are correctly
inserted before preprocessing, that evidence is replaced after each phase, that
failures fall back gracefully, and that missing sources skip the ingestion phase.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


from sat.config import AnalysisConfig, DecompositionConfig, IngestionConfig, ProviderConfig
from sat.models.decomposition import AtomicFact
from sat.models.ingestion import IngestionResult, ParsedDocument

# @mock-exempt: ingest_evidence and decompose_evidence are patched at the pipeline
# boundary to avoid real file I/O and LLM calls. This tests that the pipeline
# correctly wires these phases, not the phases themselves (which have their own
# unit tests). The pipeline treats these as external service entry points.


def _minimal_config(**kwargs) -> AnalysisConfig:
    """Build a minimal AnalysisConfig for pipeline testing."""
    defaults = dict(
        question="Test question?",
        techniques=["key_assumptions"],
        provider=ProviderConfig(provider="anthropic", api_key="fake"),
        report=__import__("sat.config", fromlist=["ReportConfig"]).ReportConfig(enabled=False),
        research=__import__("sat.config", fromlist=["ResearchConfig"]).ResearchConfig(
            enabled=False
        ),
        preprocessing=__import__(
            "sat.config", fromlist=["PreprocessingConfig"]
        ).PreprocessingConfig(enabled=False),
        adversarial=None,
    )
    defaults.update(kwargs)
    return AnalysisConfig(**defaults)


class MockPipelineProvider:
    """Minimal mock provider for pipeline tests."""

    async def generate(self, system_prompt, messages, **kwargs):
        from sat.providers.base import LLMResult, LLMUsage

        return LLMResult(text="{}", usage=LLMUsage())

    async def generate_structured(self, system_prompt, messages, output_schema, **kwargs):
        # Return a valid empty result for any schema
        try:
            return output_schema()
        except Exception:
            return output_schema(facts=[])


class TestPipelineIngestionPhase:
    async def test_pipeline_with_ingestion(self, tmp_path):
        """Ingestion phase runs when evidence_sources is set, replacing evidence."""
        txt = tmp_path / "evidence.txt"
        txt.write_text("File-based evidence content.")

        doc = ParsedDocument(
            source_id="abc12345",
            source_name="evidence.txt",
            source_type="text",
            markdown="File-based evidence content.",
        )
        mock_result = IngestionResult(
            documents=[doc],
            combined_markdown="--- Source: evidence.txt ---\nFile-based evidence content.",
            total_estimated_tokens=10,
            summary="Ingested 1 source(s)",
        )

        config = _minimal_config(
            evidence_sources=[str(txt)],
            ingestion=IngestionConfig(enabled=True),
        )

        written_results = []

        with (
            patch("sat.ingestion.ingest_evidence", AsyncMock(return_value=mock_result)),
            patch("sat.pipeline.create_provider", return_value=MockPipelineProvider()),
            patch(
                "sat.pipeline.select_techniques",
                AsyncMock(return_value=["key_assumptions"]),
            ),
            patch("sat.pipeline.get_technique") as mock_get_technique,
            patch(
                "sat.artifacts.ArtifactWriter.write_result",
                side_effect=lambda r: written_results.append(r) or _fake_artifact(),
            ),
            patch("sat.artifacts.ArtifactWriter.write_manifest"),
            patch("sat.artifacts.ArtifactWriter.get_technique_artifacts", return_value=[]),
        ):
            mock_technique = _make_mock_technique()
            mock_get_technique.return_value = mock_technique

            from sat.pipeline import run_analysis

            await run_analysis(config)

        ingestion_results = [r for r in written_results if hasattr(r, "combined_markdown")]
        assert len(ingestion_results) >= 1

    async def test_pipeline_no_sources_skips_ingestion(self):
        """No evidence_sources means ingestion phase is not entered."""
        config = _minimal_config(
            evidence="Direct evidence text.",
            evidence_sources=None,
            ingestion=IngestionConfig(enabled=True),
        )

        with (
            patch("sat.ingestion.ingest_evidence", AsyncMock()) as mock_ingest,
            patch("sat.pipeline.create_provider", return_value=MockPipelineProvider()),
            patch(
                "sat.pipeline.select_techniques",
                AsyncMock(return_value=["key_assumptions"]),
            ),
            patch("sat.pipeline.get_technique", return_value=_make_mock_technique()),
            patch("sat.artifacts.ArtifactWriter.write_result", return_value=_fake_artifact()),
            patch("sat.artifacts.ArtifactWriter.write_manifest"),
            patch("sat.artifacts.ArtifactWriter.get_technique_artifacts", return_value=[]),
        ):
            from sat.pipeline import run_analysis

            await run_analysis(config)
            mock_ingest.assert_not_called()

    async def test_pipeline_ingestion_failure_fallback(self):
        """Ingestion exception is caught; pipeline continues with raw evidence."""
        config = _minimal_config(
            evidence="Fallback evidence.",
            evidence_sources=["http://broken.example.com"],
            ingestion=IngestionConfig(enabled=True),
        )

        with (
            patch("sat.ingestion.ingest_evidence", AsyncMock(side_effect=RuntimeError("boom"))),
            patch("sat.pipeline.create_provider", return_value=MockPipelineProvider()),
            patch(
                "sat.pipeline.select_techniques",
                AsyncMock(return_value=["key_assumptions"]),
            ),
            patch("sat.pipeline.get_technique", return_value=_make_mock_technique()),
            patch("sat.artifacts.ArtifactWriter.write_result", return_value=_fake_artifact()),
            patch("sat.artifacts.ArtifactWriter.write_manifest"),
            patch("sat.artifacts.ArtifactWriter.get_technique_artifacts", return_value=[]),
        ):
            from sat.pipeline import run_analysis

            # Should not raise — failure is caught and logged
            await run_analysis(config)

    async def test_pipeline_with_decomposition(self):
        """Decomposition phase runs when enabled, replacing evidence."""
        from sat.models.decomposition import DecompositionResult

        decomp_result = DecompositionResult(
            facts=[AtomicFact(fact_id="F1", claim="The sky is blue.")],
            total_facts=1,
            chunks_processed=1,
            formatted_evidence="[Decomposed Evidence: 1 atomic facts from 0 sources]\n\n[F1] The sky is blue.",
            summary="Extracted 1 atomic facts from 1 chunk(s)",
        )

        config = _minimal_config(
            evidence="Raw evidence to decompose.",
            decomposition=DecompositionConfig(enabled=True, deduplicate=False),
        )

        written_results = []

        with (
            patch("sat.decomposition.decompose_evidence", AsyncMock(return_value=decomp_result)),
            patch("sat.pipeline.create_provider", return_value=MockPipelineProvider()),
            patch(
                "sat.pipeline.select_techniques",
                AsyncMock(return_value=["key_assumptions"]),
            ),
            patch("sat.pipeline.get_technique", return_value=_make_mock_technique()),
            patch(
                "sat.artifacts.ArtifactWriter.write_result",
                side_effect=lambda r: written_results.append(r) or _fake_artifact(),
            ),
            patch("sat.artifacts.ArtifactWriter.write_manifest"),
            patch("sat.artifacts.ArtifactWriter.get_technique_artifacts", return_value=[]),
        ):
            from sat.pipeline import run_analysis

            await run_analysis(config)

        decomp_results = [
            r
            for r in written_results
            if hasattr(r, "formatted_evidence") and hasattr(r, "total_facts")
        ]
        assert len(decomp_results) >= 1

    async def test_pipeline_decomposition_failure_fallback(self):
        """Decomposition exception is caught; pipeline continues with raw evidence."""
        config = _minimal_config(
            evidence="Evidence that fails decomposition.",
            decomposition=DecompositionConfig(enabled=True),
        )

        with (
            patch(
                "sat.decomposition.decompose_evidence",
                AsyncMock(side_effect=RuntimeError("decomp fail")),
            ),
            patch("sat.pipeline.create_provider", return_value=MockPipelineProvider()),
            patch(
                "sat.pipeline.select_techniques",
                AsyncMock(return_value=["key_assumptions"]),
            ),
            patch("sat.pipeline.get_technique", return_value=_make_mock_technique()),
            patch("sat.artifacts.ArtifactWriter.write_result", return_value=_fake_artifact()),
            patch("sat.artifacts.ArtifactWriter.write_manifest"),
            patch("sat.artifacts.ArtifactWriter.get_technique_artifacts", return_value=[]),
        ):
            from sat.pipeline import run_analysis

            # Should not raise — failure is caught and logged
            await run_analysis(config)


def _fake_artifact():
    """Return a minimal Artifact-like object for ArtifactWriter.write_result mock."""
    from sat.models.base import Artifact

    return Artifact(
        technique_id="test",
        technique_name="Test",
        category="test",
        markdown_path="test.md",
    )


def _make_mock_technique():
    """Return a minimal mock technique for pipeline tests."""
    from sat.models.base import ArtifactResult
    from sat.techniques.base import TechniqueMetadata

    meta = TechniqueMetadata(
        id="key_assumptions",
        name="Key Assumptions Check",
        category="diagnostic",
        description="Test technique",
        order=1,
    )

    class _MockTechnique:
        metadata = meta

        async def execute(self, ctx, provider):
            return ArtifactResult(
                technique_id="key_assumptions",
                technique_name="Key Assumptions Check",
                summary="Mock result",
            )

    return _MockTechnique()
