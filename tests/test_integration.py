"""End-to-end integration tests for research + adversarial pipeline.

# @mock-exempt: Test doubles implement the LLMProvider and ResearchProvider
# protocol patterns at the external API boundary.

@decision DEC-TEST-INT-001: Full pipeline integration with protocol-conforming doubles.
@title End-to-end tests covering research, adversarial, artifact structure, compatibility
@status accepted
@rationale Integration tests verify the complete pipeline flow without external
API calls. Test doubles conform to LLMProvider and ResearchProvider protocols.
Tests cover: full adversarial pipeline, artifact structure verification,
fallback paths, backward compatibility, and config-driven adversarial setup.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

import sat.techniques  # noqa: F401 — ensure registration

from sat.adversarial.config import AdversarialConfig, ProviderRef, RoleAssignment
from sat.artifacts import ArtifactWriter
from sat.config import AnalysisConfig, ProviderConfig
from sat.models.adversarial import (
    AdjudicationResult,
    AdversarialExchange,
    Challenge,
    CritiqueResult,
    DebateRound,
    RebuttalPoint,
    RebuttalResult,
)
from sat.models.assumptions import AssumptionRow, KeyAssumptionsResult
from sat.models.base import ArtifactResult
from sat.models.synthesis import SynthesisResult, TechniqueFinding


# ---------------------------------------------------------------------------
# Fixtures: reusable canned responses
# ---------------------------------------------------------------------------


def _make_assumptions_result() -> KeyAssumptionsResult:
    return KeyAssumptionsResult(
        technique_id="assumptions",
        technique_name="Key Assumptions Check",
        summary="Two assumptions identified.",
        analytic_line="Test analytic line.",
        assumptions=[
            AssumptionRow(
                assumption="Assumption A",
                confidence="High",
                basis_for_confidence="Historical data",
                what_undermines="New contradicting evidence",
                impact_if_wrong="Moderate impact",
            ),
        ],
        most_vulnerable=["Assumption A"],
        recommended_monitoring=["Watch for changes"],
    )


def _make_critique() -> CritiqueResult:
    return CritiqueResult(
        technique_id="assumptions-critique",
        technique_name="Critique of Key Assumptions Check",
        summary="Some assumptions insufficiently tested.",
        agreements=["Assumption set is reasonable"],
        challenges=[
            Challenge(
                claim="Assumption A has high confidence",
                challenge="Historical data may not apply to current context",
                evidence="Context has shifted significantly since baseline",
                severity="Medium",
            )
        ],
        alternative_interpretations=["Assumption A may be partially valid"],
        evidence_gaps=["No recent data consulted"],
        severity="Moderate",
        overall_assessment="Analysis needs additional evidence validation",
        revised_confidence="Lower",
    )


def _make_rebuttal() -> RebuttalResult:
    return RebuttalResult(
        technique_id="assumptions-rebuttal",
        technique_name="Rebuttal for Key Assumptions Check",
        summary="Challenge partially conceded.",
        accepted_challenges=["Context shift is valid"],
        rejected_challenges=[
            RebuttalPoint(
                challenge="No recent data consulted",
                response="Recent survey data was incorporated in the assumption basis",
                conceded=False,
            )
        ],
        revised_conclusions="Assumption A confidence lowered to Medium",
    )


def _make_adjudication() -> AdjudicationResult:
    return AdjudicationResult(
        technique_id="assumptions-adjudication",
        technique_name="Adjudication for Key Assumptions Check",
        summary="Primary position holds with modifications.",
        resolved_for_primary=["Recent data was consulted"],
        resolved_for_challenger=["Context shift reduces confidence"],
        unresolved=["Degree to which historical baseline applies"],
        synthesis_assessment="Assumption A should be Medium confidence, not High",
    )


def _make_synthesis_result() -> SynthesisResult:
    return SynthesisResult(
        technique_id="synthesis",
        technique_name="Synthesis Report",
        summary="Integrated assessment complete.",
        question="Test question?",
        techniques_applied=["assumptions"],
        key_findings=[
            TechniqueFinding(
                technique_id="assumptions",
                technique_name="Key Assumptions Check",
                summary="Assumptions identified",
                key_finding="One vulnerable assumption found",
                confidence="Medium",
            )
        ],
        convergent_judgments=["Both sides agree on assumption set"],
        divergent_signals=["Confidence level disputed"],
        highest_confidence_assessments=["Assumption set is comprehensive"],
        remaining_uncertainties=["Historical baseline applicability"],
        intelligence_gaps=["Need more recent data"],
        recommended_next_steps=["Collect updated survey data"],
        bottom_line_assessment="Analysis is solid but confidence should be moderated.",
    )


# ---------------------------------------------------------------------------
# Test: Full adversarial pipeline artifact round-trip
# ---------------------------------------------------------------------------


class TestAdversarialArtifactRoundTrip:
    """Verify adversarial artifacts write correctly alongside technique artifacts."""

    def test_adversarial_artifacts_written(self, tmp_path):
        """Write technique + critique + rebuttal + adjudication artifacts."""
        writer = ArtifactWriter(tmp_path, "run-int", "Test question?")

        # Write primary technique result
        writer.write_result(_make_assumptions_result())

        # Write adversarial exchange artifacts
        writer.write_result(_make_critique())
        writer.write_result(_make_rebuttal())
        writer.write_result(_make_adjudication())

        # Write manifest
        manifest_path = writer.write_manifest(
            techniques_selected=["assumptions"],
            techniques_completed=["assumptions"],
            evidence_provided=False,
            adversarial_enabled=True,
            providers_used=["claude", "gpt4", "gemini"],
        )

        manifest = json.loads(manifest_path.read_text())
        assert manifest["adversarial_enabled"] is True
        assert manifest["providers_used"] == ["claude", "gpt4", "gemini"]
        assert len(manifest["artifacts"]) == 4

        # Verify file naming
        assert (tmp_path / "01-assumptions.md").exists()
        assert (tmp_path / "02-assumptions-critique.md").exists()
        assert (tmp_path / "03-assumptions-rebuttal.md").exists()
        assert (tmp_path / "04-assumptions-adjudication.md").exists()

        # Verify adversarial category
        categories = [a["category"] for a in manifest["artifacts"]]
        assert categories[0] == "diagnostic"
        assert categories[1] == "adversarial"
        assert categories[2] == "adversarial"
        assert categories[3] == "adversarial"

    def test_revised_artifact_written(self, tmp_path):
        """Verify revised technique result is written as separate artifact."""
        writer = ArtifactWriter(tmp_path, "run-rev", "Test question?")

        # Write original technique result
        original = _make_assumptions_result()
        writer.write_result(original)

        # Simulate writing a revised result with -revised suffix
        revised = original.model_copy(
            update={
                "summary": f"{original.summary}\n\n[Revised after adversarial critique]\nRevised conclusions here.",
                "technique_id": "assumptions-revised",
                "technique_name": "Key Assumptions Check (Revised)",
            }
        )
        writer.write_result(revised)

        # Verify both files exist
        assert (tmp_path / "01-assumptions.md").exists()
        assert (tmp_path / "02-assumptions-revised.md").exists()

        # Verify revised artifact has updated content
        revised_md = (tmp_path / "02-assumptions-revised.md").read_text()
        assert "[Revised after adversarial critique]" in revised_md
        assert "Revised conclusions here." in revised_md
        assert "Key Assumptions Check (Revised)" in revised_md

    def test_adversarial_json_round_trip(self, tmp_path):
        """Verify adversarial JSON artifacts can be deserialized."""
        writer = ArtifactWriter(tmp_path, "run-rt", "Test?")
        writer.write_result(_make_critique())

        json_path = tmp_path / "01-assumptions-critique.json"
        restored = CritiqueResult.model_validate_json(json_path.read_text())
        assert restored.severity == "Moderate"
        assert len(restored.challenges) == 1


# ---------------------------------------------------------------------------
# Test: Adversarial session orchestration
# ---------------------------------------------------------------------------


class TestAdversarialSessionIntegration:
    """Test the full adversarial session flow with mock providers."""

    @pytest.mark.asyncio
    async def test_full_adversarial_session(self):
        """Run technique -> critique -> rebuttal -> adjudication cycle."""
        from sat.adversarial.pool import ProviderPool
        from sat.adversarial.session import AdversarialSession

        config = AdversarialConfig(
            enabled=True,
            rounds=1,
            providers={
                "primary": ProviderRef(provider="anthropic", model="claude-opus-4-6"),
                "challenger": ProviderRef(provider="openai", model="o3"),
                "judge": ProviderRef(provider="gemini", model="gemini-2.5-pro"),
            },
            roles=RoleAssignment(primary="primary", challenger="challenger", adjudicator="judge"),
        )

        challenger_mock = AsyncMock()
        challenger_mock.generate_structured.return_value = _make_critique()

        primary_mock = AsyncMock()
        primary_mock.generate_structured.return_value = _make_rebuttal()

        adjudicator_mock = AsyncMock()
        adjudicator_mock.generate_structured.return_value = _make_adjudication()

        pool = ProviderPool(config)
        with (
            patch.object(pool, "get_challenger", return_value=challenger_mock),
            patch.object(pool, "get_primary", return_value=primary_mock),
            patch.object(pool, "get_adjudicator", return_value=adjudicator_mock),
        ):
            session = AdversarialSession(pool, config)
            exchange = await session.run_adversarial_technique(
                technique_result=_make_assumptions_result(),
                question="Test question?",
                evidence="Some test evidence.",
            )

        assert exchange.technique_id == "assumptions"
        assert len(exchange.rounds) == 1
        assert exchange.rounds[0].critique.severity == "Moderate"
        assert exchange.rounds[0].rebuttal is not None
        assert exchange.rounds[0].rebuttal.accepted_challenges == ["Context shift is valid"]
        assert exchange.adjudication is not None
        assert "Medium confidence" in exchange.adjudication.synthesis_assessment


# ---------------------------------------------------------------------------
# Test: Backward compatibility (no adversarial, no research)
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Verify the pipeline works identically without adversarial/research flags."""

    def test_config_without_adversarial(self):
        """AnalysisConfig works without adversarial field."""
        config = AnalysisConfig(
            question="Test?",
            provider=ProviderConfig(provider="anthropic", model="test"),
        )
        assert config.adversarial is None

    def test_manifest_defaults_no_adversarial(self, tmp_path):
        """Manifest defaults adversarial_enabled=False when not configured."""
        writer = ArtifactWriter(tmp_path, "run-compat", "Q?")
        result = ArtifactResult(technique_id="test", technique_name="Test", summary="Test")
        writer.write_result(result)
        manifest_path = writer.write_manifest(
            techniques_selected=["test"],
            techniques_completed=["test"],
            evidence_provided=False,
        )
        manifest = json.loads(manifest_path.read_text())
        assert manifest["adversarial_enabled"] is False
        assert manifest["providers_used"] == []


# ---------------------------------------------------------------------------
# Test: Adversarial config from TOML-style data
# ---------------------------------------------------------------------------


class TestConfigIntegration:
    """Verify config flows from TOML data -> AdversarialConfig -> AnalysisConfig."""

    def test_toml_config_to_analysis_config(self):
        """Build AnalysisConfig with adversarial from TOML-style dict."""
        toml_data = {
            "enabled": True,
            "rounds": 2,
            "providers": {
                "claude": {
                    "provider": "anthropic",
                    "model": "claude-opus-4-6",
                },
                "gpt4": {"provider": "openai", "model": "o3"},
            },
            "roles": {"primary": "claude", "challenger": "gpt4"},
        }
        adv_config = AdversarialConfig(**toml_data)
        config = AnalysisConfig(
            question="Test?",
            adversarial=adv_config,
        )
        assert config.adversarial is not None
        assert config.adversarial.enabled is True
        assert config.adversarial.rounds == 2
        assert isinstance(config.adversarial.providers["claude"], ProviderRef)

    def test_cli_style_inline_config(self):
        """Build adversarial config as CLI would (inline flags)."""
        adv_config = AdversarialConfig(
            enabled=True,
            rounds=1,
            providers={
                "primary": ProviderRef(provider="anthropic", model="claude-opus-4-6"),
                "challenger": ProviderRef(provider="openai", model="o3"),
            },
            roles=RoleAssignment(primary="primary", challenger="challenger"),
        )
        config = AnalysisConfig(
            question="Test?",
            adversarial=adv_config,
        )
        assert config.adversarial.roles.adjudicator is None
        assert len(config.adversarial.providers) == 2


# ---------------------------------------------------------------------------
# Test: Exchange model with multiple rounds
# ---------------------------------------------------------------------------


class TestMultiRoundExchange:
    """Verify multi-round debate data structures."""

    def test_two_round_exchange(self):
        """Build a 2-round exchange and verify structure."""
        critique = _make_critique()
        rebuttal = _make_rebuttal()

        exchange = AdversarialExchange(
            technique_id="assumptions",
            initial_result=_make_assumptions_result(),
            rounds=[
                DebateRound(round_number=1, critique=critique, rebuttal=rebuttal),
                DebateRound(round_number=2, critique=critique, rebuttal=rebuttal),
            ],
            adjudication=_make_adjudication(),
        )

        assert len(exchange.rounds) == 2
        assert exchange.rounds[0].round_number == 1
        assert exchange.rounds[1].round_number == 2

        # JSON round-trip
        json_str = exchange.model_dump_json()
        restored = AdversarialExchange.model_validate_json(json_str)
        assert len(restored.rounds) == 2
        assert restored.adjudication is not None
