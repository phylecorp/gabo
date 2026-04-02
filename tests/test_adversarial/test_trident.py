"""Tests for Trident Mode — tri-provider adversarial analysis with IPA.

# @mock-exempt: Test doubles implement the LLMProvider protocol pattern and
# Technique protocol — no external API calls.

@decision DEC-TEST-ADV-005: Trident session tests with mock providers and techniques.
@title Verify trident mode parallel execution, convergence, and fallback
@status accepted
@rationale Trident mode orchestrates four phases with three providers. Tests
verify: (1) parallel critique+investigation, (2) rebuttal, (3) convergence,
(4) enhanced adjudication; plus fallback to dual when no investigator is
configured, and auto-detection of investigator in CLI/config flow.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from sat.adversarial.config import AdversarialConfig, ProviderRef, RoleAssignment
from sat.adversarial.pool import ProviderPool
from sat.adversarial.session import AdversarialSession
from sat.models.adversarial import (
    AdjudicationResult,
    AdversarialExchange,
    Challenge,
    ConvergencePoint,
    ConvergenceResult,
    CritiqueResult,
    DebateRound,
    DivergencePoint,
    RebuttalPoint,
    RebuttalResult,
)
from sat.models.base import ArtifactResult


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_technique_result() -> ArtifactResult:
    return ArtifactResult(
        technique_id="assumptions",
        technique_name="Key Assumptions Check",
        summary="Key assumptions identified: A1, A2, A3.",
    )


def _make_investigator_result() -> ArtifactResult:
    """Investigator re-analysis — slightly different findings."""
    return ArtifactResult(
        technique_id="assumptions-investigator",
        technique_name="Key Assumptions Check (Investigator)",
        summary="Independent re-analysis: A1 confirmed, A2 questioned, A4 identified.",
    )


def _make_critique() -> CritiqueResult:
    return CritiqueResult(
        technique_id="assumptions-critique",
        technique_name="Critique of Key Assumptions Check",
        summary="Assumptions A2 and A3 are weakly supported.",
        agreements=["A1 is well-grounded"],
        challenges=[
            Challenge(
                claim="A2 is stable",
                challenge="No historical precedent cited",
                evidence="Missing source analysis",
                severity="High",
            )
        ],
        alternative_interpretations=["A3 may be a conclusion, not an assumption"],
        evidence_gaps=["No external validation"],
        severity="Moderate",
        overall_assessment="Moderate weaknesses found",
        revised_confidence="Lower",
    )


def _make_rebuttal() -> RebuttalResult:
    return RebuttalResult(
        technique_id="assumptions-rebuttal",
        technique_name="Rebuttal for Key Assumptions Check",
        summary="A2 criticism accepted; A3 framing defended.",
        accepted_challenges=["A2 lacks historical support"],
        rejected_challenges=[
            RebuttalPoint(
                challenge="A3 framing",
                response="A3 is logically prior to the conclusion",
                conceded=False,
            )
        ],
        revised_conclusions="A2 needs re-evaluation; A3 stands",
    )


def _make_convergence() -> ConvergenceResult:
    return ConvergenceResult(
        technique_id="assumptions-convergence",
        technique_name="Convergence Analysis for Key Assumptions Check",
        summary="High convergence on A1; investigator found novel A4.",
        convergence_points=[
            ConvergencePoint(
                claim="A1 is well-supported",
                agreeing_providers=["primary", "investigator"],
                confidence_boost="High",
                reasoning="Independent agreement from two providers",
            )
        ],
        divergence_points=[
            DivergencePoint(
                claim="A2 stability",
                primary_position="Stable under most scenarios",
                investigator_position="Fragile — historical precedent absent",
                challenger_position="Weakly supported",
                significance="Important",
                likely_cause="Different evidence weighting",
            )
        ],
        novel_insights=["Investigator identified A4 as critical assumption primary missed"],
        confidence_delta="A1 confidence increases; A2 confidence decreases",
        analytical_blindspots_identified=["Primary anchored on stated assumptions without exploring implicit ones"],
    )


def _make_adjudication() -> AdjudicationResult:
    return AdjudicationResult(
        technique_id="assumptions-adjudication",
        technique_name="Adjudication for Key Assumptions Check",
        summary="A1 upheld; A2 reassessed; A4 incorporated.",
        resolved_for_primary=["A3 framing is defensible"],
        resolved_for_challenger=["A2 weaknesses are real"],
        unresolved=["Whether A4 changes the overall assessment"],
        synthesis_assessment="A1 solid; A2 needs revision; A4 warrants further analysis",
    )


def _make_trident_config() -> AdversarialConfig:
    """Three-provider trident config."""
    return AdversarialConfig(
        enabled=True,
        rounds=1,
        mode="trident",
        providers={
            "claude": ProviderRef(provider="anthropic", model="claude-opus-4-6"),
            "gpt4": ProviderRef(provider="openai", model="o3"),
            "gemini": ProviderRef(provider="gemini", model="gemini-2.5-pro"),
        },
        roles=RoleAssignment(
            primary="claude",
            challenger="gpt4",
            adjudicator="claude",
            investigator="gemini",
        ),
    )


def _make_dual_config() -> AdversarialConfig:
    """Dual config without investigator."""
    return AdversarialConfig(
        enabled=True,
        rounds=1,
        mode="dual",
        providers={
            "claude": ProviderRef(provider="anthropic", model="claude-opus-4-6"),
            "gpt4": ProviderRef(provider="openai", model="o3"),
        },
        roles=RoleAssignment(primary="claude", challenger="gpt4"),
    )


# ---------------------------------------------------------------------------
# Convergence model tests
# ---------------------------------------------------------------------------


class TestConvergenceModels:
    """Tests for ConvergencePoint, DivergencePoint, ConvergenceResult."""

    def test_convergence_point_serialization(self):
        cp = ConvergencePoint(
            claim="Both agree on X",
            agreeing_providers=["primary", "investigator"],
            confidence_boost="High",
            reasoning="Independent confirmation",
        )
        data = cp.model_dump()
        restored = ConvergencePoint(**data)
        assert restored.claim == "Both agree on X"
        assert restored.confidence_boost == "High"
        assert "primary" in restored.agreeing_providers

    def test_divergence_point_serialization(self):
        dp = DivergencePoint(
            claim="Disagreement on Y",
            primary_position="Y is stable",
            investigator_position="Y is fragile",
            challenger_position="Y needs evidence",
            significance="Critical",
            likely_cause="Different priors",
        )
        data = dp.model_dump()
        restored = DivergencePoint(**data)
        assert restored.significance == "Critical"
        assert restored.investigator_position == "Y is fragile"

    def test_convergence_result_roundtrip(self):
        conv = _make_convergence()
        json_str = conv.model_dump_json()
        restored = ConvergenceResult.model_validate_json(json_str)
        assert restored.technique_id == "assumptions-convergence"
        assert len(restored.convergence_points) == 1
        assert len(restored.divergence_points) == 1
        assert len(restored.novel_insights) == 1
        assert len(restored.analytical_blindspots_identified) == 1

    def test_convergence_result_defaults(self):
        """Empty ConvergenceResult has sensible defaults."""
        conv = ConvergenceResult(
            technique_id="test-convergence",
            technique_name="Convergence Analysis for Test",
            summary="No significant convergence found",
        )
        assert conv.convergence_points == []
        assert conv.divergence_points == []
        assert conv.novel_insights == []
        assert conv.confidence_delta == ""
        assert conv.analytical_blindspots_identified == []


class TestAdversarialExchangeTridentFields:
    """Tests for new trident fields on AdversarialExchange."""

    def test_exchange_with_investigator_and_convergence(self):
        technique_result = _make_technique_result()
        critique = _make_critique()
        rebuttal = _make_rebuttal()
        conv = _make_convergence()
        inv = _make_investigator_result()
        adj = _make_adjudication()

        exchange = AdversarialExchange(
            technique_id="assumptions",
            initial_result=technique_result,
            rounds=[DebateRound(round_number=1, critique=critique, rebuttal=rebuttal)],
            adjudication=adj,
            investigator_result=inv,
            convergence=conv,
        )

        assert exchange.investigator_result is not None
        assert exchange.investigator_result.technique_id == "assumptions-investigator"
        assert exchange.convergence is not None
        assert len(exchange.convergence.convergence_points) == 1

    def test_exchange_backward_compat_no_trident_fields(self):
        """Exchange without trident fields should work (dual mode compat)."""
        technique_result = _make_technique_result()
        critique = _make_critique()

        exchange = AdversarialExchange(
            technique_id="assumptions",
            initial_result=technique_result,
            rounds=[DebateRound(round_number=1, critique=critique)],
        )
        assert exchange.investigator_result is None
        assert exchange.convergence is None
        assert exchange.adjudication is None

    def test_exchange_json_roundtrip_with_convergence(self):
        technique_result = _make_technique_result()
        critique = _make_critique()
        conv = _make_convergence()
        inv = _make_investigator_result()

        exchange = AdversarialExchange(
            technique_id="assumptions",
            initial_result=technique_result,
            rounds=[DebateRound(round_number=1, critique=critique)],
            investigator_result=inv,
            convergence=conv,
        )
        json_str = exchange.model_dump_json()
        restored = AdversarialExchange.model_validate_json(json_str)
        assert restored.convergence is not None
        assert restored.investigator_result is not None
        assert restored.convergence.novel_insights[0].startswith("Investigator")


# ---------------------------------------------------------------------------
# Pool tests for investigator
# ---------------------------------------------------------------------------


class TestPoolInvestigator:
    """Tests for ProviderPool.get_investigator."""

    @patch("sat.adversarial.pool.create_provider")
    def test_get_investigator_returns_provider(self, mock_create):
        mock_create.return_value = MagicMock(name="investigator_provider")
        pool = ProviderPool(_make_trident_config())
        inv = pool.get_investigator()
        assert inv is not None

    def test_get_investigator_none_when_no_investigator_role(self):
        pool = ProviderPool(_make_dual_config())
        assert pool.get_investigator() is None

    def test_get_investigator_none_when_no_roles(self):
        config = _make_dual_config().model_copy(update={"roles": None})
        pool = ProviderPool(config)
        assert pool.get_investigator() is None

    @patch("sat.adversarial.pool.create_provider")
    def test_investigator_cached(self, mock_create):
        mock_create.return_value = MagicMock(name="gemini_provider")
        pool = ProviderPool(_make_trident_config())
        inv1 = pool.get_investigator()
        inv2 = pool.get_investigator()
        assert inv1 is inv2
        assert mock_create.call_count == 1


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestAdversarialConfigTrident:
    """Tests for trident fields in AdversarialConfig and RoleAssignment."""

    def test_config_mode_default_is_dual(self):
        config = AdversarialConfig(
            providers={},
            roles=RoleAssignment(primary="a", challenger="b"),
        )
        assert config.mode == "dual"

    def test_config_mode_trident(self):
        config = AdversarialConfig(
            mode="trident",
            providers={},
            roles=RoleAssignment(primary="a", challenger="b", investigator="c"),
        )
        assert config.mode == "trident"
        assert config.roles is not None
        assert config.roles.investigator == "c"

    def test_role_assignment_investigator_default_none(self):
        role = RoleAssignment(primary="p", challenger="c")
        assert role.investigator is None

    def test_role_assignment_with_investigator(self):
        role = RoleAssignment(primary="p", challenger="c", investigator="i")
        assert role.investigator == "i"


# ---------------------------------------------------------------------------
# Session trident integration tests
# ---------------------------------------------------------------------------


class TestAdversarialSessionTrident:
    """Tests for AdversarialSession._run_trident."""

    def _make_mock_investigator(self) -> AsyncMock:
        """Mock investigator that returns a technique-like result."""
        inv_result = ArtifactResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Investigator independent result",
        )
        mock = AsyncMock()
        mock.generate_structured.return_value = inv_result
        return mock

    async def test_trident_full_cycle(self):
        """Test complete trident cycle: parallel critique+investigate, rebuttal, convergence, adjudication."""
        config = _make_trident_config()
        pool = ProviderPool(config)

        technique_result = _make_technique_result()

        challenger_mock = AsyncMock()
        challenger_mock.generate_structured.return_value = _make_critique()

        primary_mock = AsyncMock()
        # primary answers: rebuttal, then convergence, then adjudication
        primary_mock.generate_structured.side_effect = [
            _make_rebuttal(),
            _make_convergence(),
            _make_adjudication(),
        ]

        investigator_mock = AsyncMock()

        # The investigator calls technique.execute, not generate_structured directly.
        # We patch get_technique so execute returns our inv_result.
        inv_technique_result = ArtifactResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Investigator independent result",
        )
        mock_technique = MagicMock()
        mock_technique.execute = AsyncMock(return_value=inv_technique_result)

        with (
            patch.object(pool, "get_challenger", return_value=challenger_mock),
            patch.object(pool, "get_primary", return_value=primary_mock),
            patch.object(pool, "get_adjudicator", return_value=None),  # primary does adj
            patch.object(pool, "get_investigator", return_value=investigator_mock),
            patch("sat.adversarial.session.get_technique", return_value=mock_technique),
        ):
            session = AdversarialSession(pool, config)
            exchange = await session.run_adversarial_technique(
                technique_result=technique_result,
                question="What are the key assumptions?",
                evidence="Evidence text here.",
            )

        # Verify structure
        assert exchange.technique_id == "assumptions"
        assert len(exchange.rounds) == 1
        assert exchange.rounds[0].critique.severity == "Moderate"
        assert exchange.rounds[0].rebuttal is not None

        # Investigator result should have renamed IDs
        assert exchange.investigator_result is not None
        assert exchange.investigator_result.technique_id == "assumptions-investigator"
        assert "(Investigator)" in exchange.investigator_result.technique_name

        # Convergence should be present
        assert exchange.convergence is not None
        assert len(exchange.convergence.convergence_points) == 1

        # Adjudication present (primary used as fallback)
        assert exchange.adjudication is not None

    async def test_trident_falls_back_to_dual_without_investigator(self):
        """When config.mode=trident but no investigator in pool, falls back to dual."""
        # Trident mode but no investigator in roles
        config = AdversarialConfig(
            enabled=True,
            rounds=1,
            mode="trident",
            providers={
                "claude": ProviderRef(provider="anthropic", model="claude-opus-4-6"),
                "gpt4": ProviderRef(provider="openai", model="o3"),
            },
            roles=RoleAssignment(primary="claude", challenger="gpt4"),
        )
        pool = ProviderPool(config)

        technique_result = _make_technique_result()

        challenger_mock = AsyncMock()
        challenger_mock.generate_structured.return_value = _make_critique()

        primary_mock = AsyncMock()
        primary_mock.generate_structured.return_value = _make_rebuttal()

        with (
            patch.object(pool, "get_challenger", return_value=challenger_mock),
            patch.object(pool, "get_primary", return_value=primary_mock),
            patch.object(pool, "get_adjudicator", return_value=None),
            patch.object(pool, "get_investigator", return_value=None),
        ):
            session = AdversarialSession(pool, config)
            exchange = await session.run_adversarial_technique(
                technique_result=technique_result,
                question="Test question",
            )

        # Should have fallen back to dual — no investigator or convergence
        assert exchange.investigator_result is None
        assert exchange.convergence is None
        assert len(exchange.rounds) == 1

    async def test_dual_mode_dispatch(self):
        """Explicit dual mode should use _run_dual, not _run_trident."""
        config = _make_dual_config()
        pool = ProviderPool(config)

        technique_result = _make_technique_result()

        challenger_mock = AsyncMock()
        challenger_mock.generate_structured.return_value = _make_critique()

        primary_mock = AsyncMock()
        primary_mock.generate_structured.return_value = _make_rebuttal()

        with (
            patch.object(pool, "get_challenger", return_value=challenger_mock),
            patch.object(pool, "get_primary", return_value=primary_mock),
            patch.object(pool, "get_adjudicator", return_value=None),
        ):
            session = AdversarialSession(pool, config)
            exchange = await session.run_adversarial_technique(
                technique_result=technique_result,
                question="Test question",
            )

        assert exchange.investigator_result is None
        assert exchange.convergence is None
        assert len(exchange.rounds) == 1

    async def test_trident_uses_adjudicator_when_configured(self):
        """Trident uses dedicated adjudicator when available (not primary fallback)."""
        config = _make_trident_config()
        pool = ProviderPool(config)
        technique_result = _make_technique_result()

        challenger_mock = AsyncMock()
        challenger_mock.generate_structured.return_value = _make_critique()

        primary_mock = AsyncMock()
        # primary answers rebuttal and convergence only (adjudicator separate)
        primary_mock.generate_structured.side_effect = [
            _make_rebuttal(),
            _make_convergence(),
        ]

        adjudicator_mock = AsyncMock()
        adjudicator_mock.generate_structured.return_value = _make_adjudication()

        investigator_mock = AsyncMock()

        inv_technique_result = ArtifactResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Investigator result",
        )
        mock_technique = MagicMock()
        mock_technique.execute = AsyncMock(return_value=inv_technique_result)

        with (
            patch.object(pool, "get_challenger", return_value=challenger_mock),
            patch.object(pool, "get_primary", return_value=primary_mock),
            patch.object(pool, "get_adjudicator", return_value=adjudicator_mock),
            patch.object(pool, "get_investigator", return_value=investigator_mock),
            patch("sat.adversarial.session.get_technique", return_value=mock_technique),
        ):
            session = AdversarialSession(pool, config)
            exchange = await session.run_adversarial_technique(
                technique_result=technique_result,
                question="Test question",
            )

        # Adjudicator was called
        adjudicator_mock.generate_structured.assert_called_once()
        assert exchange.adjudication is not None
        assert exchange.adjudication.synthesis_assessment.startswith("A1")


# ---------------------------------------------------------------------------
# Prompt tests for convergence and enhanced adjudication
# ---------------------------------------------------------------------------


class TestConvergencePrompt:
    """Tests for build_convergence_prompt and enhanced build_adjudication_prompt."""

    def test_build_convergence_prompt_contains_all_sections(self):
        from sat.prompts.adversarial import build_convergence_prompt

        technique_result = _make_technique_result()
        inv_result = _make_investigator_result()
        critique = _make_critique()
        rebuttal = _make_rebuttal()

        system, msgs = build_convergence_prompt(
            technique_result=technique_result,
            investigator_result=inv_result,
            critique=critique,
            rebuttal=rebuttal,
            question="What are the key assumptions?",
            evidence="Some evidence",
        )

        assert "convergence" in system.lower()
        assert len(msgs) == 1
        user_content = msgs[0].content
        assert "Primary Analysis" in user_content
        assert "Investigator Analysis" in user_content
        assert "Challenger Critique" in user_content
        assert "Primary Rebuttal" in user_content
        assert "Some evidence" in user_content

    def test_build_convergence_prompt_technique_id_in_system(self):
        from sat.prompts.adversarial import build_convergence_prompt

        technique_result = _make_technique_result()
        inv_result = _make_investigator_result()
        critique = _make_critique()
        rebuttal = _make_rebuttal()

        system, _ = build_convergence_prompt(
            technique_result=technique_result,
            investigator_result=inv_result,
            critique=critique,
            rebuttal=rebuttal,
            question="Q",
        )

        assert "assumptions-convergence" in system
        assert "Key Assumptions Check" in system

    def test_build_adjudication_prompt_no_trident_unchanged(self):
        """Without trident params, adjudication prompt has no trident section."""
        from sat.prompts.adversarial import build_adjudication_prompt

        technique_result = _make_technique_result()
        critique = _make_critique()
        rebuttal = _make_rebuttal()

        system, msgs = build_adjudication_prompt(
            technique_result=technique_result,
            critique=critique,
            rebuttal=rebuttal,
            question="Q",
        )

        assert "Trident Mode" not in system
        assert len(msgs) == 1
        user_content = msgs[0].content
        assert "Independent Investigator" not in user_content

    def test_build_adjudication_prompt_with_trident_data(self):
        """With investigator and convergence, adjudication prompt extends system and user msg."""
        from sat.prompts.adversarial import build_adjudication_prompt

        technique_result = _make_technique_result()
        critique = _make_critique()
        rebuttal = _make_rebuttal()
        inv_result = _make_investigator_result()
        conv = _make_convergence()

        system, msgs = build_adjudication_prompt(
            technique_result=technique_result,
            critique=critique,
            rebuttal=rebuttal,
            question="Q",
            investigator_result=inv_result,
            convergence=conv,
        )

        assert "Trident Mode" in system
        user_content = msgs[0].content
        assert "Independent Investigator Analysis" in user_content
        assert "Convergence Analysis" in user_content


# ---------------------------------------------------------------------------
# resolve_investigator_provider tests
# ---------------------------------------------------------------------------


class TestResolveInvestigatorProvider:
    """Tests for config.resolve_investigator_provider."""

    def test_finds_third_provider(self, monkeypatch):
        from sat.config import resolve_investigator_provider

        # anthropic is primary, openai is challenger — gemini should be found
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

        result = resolve_investigator_provider("anthropic", "openai")
        assert result is not None
        prov_name, model = result
        assert prov_name == "gemini"
        assert model  # should have a default model

    def test_returns_none_when_all_taken(self, monkeypatch):
        from sat.config import resolve_investigator_provider

        # All three taken (only three providers known)
        # None will have API keys either
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setattr("sat.config._load_config_file_key", lambda provider: None)

        result = resolve_investigator_provider("anthropic", "openai")
        assert result is None

    def test_returns_none_when_third_has_no_key(self, monkeypatch):
        from sat.config import resolve_investigator_provider

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr("sat.config._load_config_file_key", lambda provider: None)

        result = resolve_investigator_provider("anthropic", "openai")
        assert result is None

    def test_skips_primary_and_challenger(self, monkeypatch):
        from sat.config import resolve_investigator_provider

        # Set all three keys — but primary=anthropic, challenger=gemini
        # So openai should be picked as investigator
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k1")
        monkeypatch.setenv("OPENAI_API_KEY", "k2")
        monkeypatch.setenv("GEMINI_API_KEY", "k3")

        result = resolve_investigator_provider("anthropic", "gemini")
        assert result is not None
        prov_name, _ = result
        assert prov_name == "openai"
