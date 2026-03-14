"""Test the analysis pipeline with mock provider.

@decision DEC-TEST-PIPE-001: Pipeline integration with mock LLM provider.
Tests technique execution with a mock provider that returns canned structured
responses, and verifies the full artifact round-trip (execute -> write -> read).
"""

from __future__ import annotations

import json

import pytest

import sat.techniques  # noqa: F401

from sat.artifacts import ArtifactWriter
from sat.models.assumptions import AssumptionRow, KeyAssumptionsResult
from sat.techniques.base import TechniqueContext
from sat.techniques.diagnostic.assumptions import KeyAssumptionsCheck


class TestTechniqueExecution:
    """Test individual technique execution with mock provider."""

    @pytest.mark.asyncio
    async def test_assumptions_execute(self, mock_provider):
        """KeyAssumptionsCheck should call generate_structured and return result."""
        expected = KeyAssumptionsResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Two key assumptions found.",
            analytic_line="Test analytic line.",
            assumptions=[
                AssumptionRow(
                    assumption="Test assumption",
                    confidence="Medium",
                    basis_for_confidence="Limited data",
                    what_undermines="Could change if conditions shift",
                    impact_if_wrong="Would alter the assessment",
                ),
            ],
            most_vulnerable=["Test assumption"],
            recommended_monitoring=["Watch for changes"],
        )

        provider = mock_provider(structured_response=expected)
        technique = KeyAssumptionsCheck()
        ctx = TechniqueContext(question="Test question?")

        result = await technique.execute(ctx, provider)
        assert isinstance(result, KeyAssumptionsResult)
        assert result.summary == "Two key assumptions found."


class TestPipelineIntegration:
    """Test the artifact writer + technique integration."""

    def test_full_artifact_round_trip(self, tmp_path):
        """Write a result and verify the full round trip."""
        result = KeyAssumptionsResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Test summary",
            analytic_line="Test analytic line.",
            assumptions=[],
            most_vulnerable=[],
            recommended_monitoring=[],
        )

        writer = ArtifactWriter(tmp_path, "run1", "Q?")
        writer.write_result(result)
        manifest_path = writer.write_manifest(
            techniques_selected=["assumptions"],
            techniques_completed=["assumptions"],
            evidence_provided=False,
        )

        manifest = json.loads(manifest_path.read_text())
        assert manifest["techniques_completed"] == ["assumptions"]
        assert len(manifest["artifacts"]) == 1

        json_path = tmp_path / "01-assumptions.json"
        restored = KeyAssumptionsResult.model_validate_json(json_path.read_text())
        assert restored.technique_id == "assumptions"
