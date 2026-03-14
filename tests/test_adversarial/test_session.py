"""Tests for adversarial session orchestrator.

# @mock-exempt: Test doubles implement the LLMProvider protocol pattern —
# generate_structured returns pre-built domain objects, no external calls.

@decision DEC-TEST-ADV-004: Session orchestration with protocol-conforming test doubles.
@title Verify AdversarialSession critique-rebuttal-adjudication cycle
@status accepted
@rationale The session orchestrates the full debate cycle. We use test doubles
that implement the LLMProvider protocol to return pre-built adversarial results,
verifying the orchestration logic without external API calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from sat.adversarial.config import AdversarialConfig, ProviderRef, RoleAssignment
from sat.adversarial.pool import ProviderPool
from sat.adversarial.session import AdversarialSession
from sat.models.adversarial import (
    AdjudicationResult,
    Challenge,
    CritiqueResult,
    RebuttalPoint,
    RebuttalResult,
)
from sat.models.base import ArtifactResult


def _make_critique() -> CritiqueResult:
    return CritiqueResult(
        technique_id="ach-critique",
        technique_name="Critique of ACH",
        summary="Moderate weaknesses found.",
        agreements=["Good hypothesis set"],
        challenges=[
            Challenge(
                claim="E3 supports H1",
                challenge="E3 is ambiguous",
                evidence="Missing source assessment",
                severity="Medium",
            )
        ],
        alternative_interpretations=["H1 and H2 overlap"],
        evidence_gaps=["No OSINT consulted"],
        severity="Moderate",
        overall_assessment="Needs revision",
        revised_confidence="Lower",
    )


def _make_rebuttal() -> RebuttalResult:
    return RebuttalResult(
        technique_id="ach-rebuttal",
        technique_name="Rebuttal for ACH",
        summary="Partially conceded.",
        accepted_challenges=["E3 ambiguity"],
        rejected_challenges=[
            RebuttalPoint(
                challenge="Missing source assessment",
                response="Addressed in assumptions",
                conceded=False,
            )
        ],
        revised_conclusions="H1 likely but lower confidence",
    )


def _make_adjudication() -> AdjudicationResult:
    return AdjudicationResult(
        technique_id="ach-adjudication",
        technique_name="Adjudication for ACH",
        summary="Primary holds with caveats.",
        resolved_for_primary=["Source assessment present"],
        resolved_for_challenger=["E3 ambiguity valid"],
        unresolved=["H1/H2 exclusivity"],
        synthesis_assessment="H1 most likely, H2 not dismissable",
    )


def _make_config(with_adjudicator: bool = True) -> AdversarialConfig:
    roles = RoleAssignment(
        primary="claude",
        challenger="gpt4",
        adjudicator="gemini" if with_adjudicator else None,
    )
    return AdversarialConfig(
        enabled=True,
        rounds=1,
        providers={
            "claude": ProviderRef(provider="anthropic", model="claude-opus-4-6"),
            "gpt4": ProviderRef(provider="openai", model="o3"),
            "gemini": ProviderRef(provider="gemini", model="gemini-2.5-pro"),
        },
        roles=roles,
    )


def _make_technique_result() -> ArtifactResult:
    return ArtifactResult(
        technique_id="ach",
        technique_name="Analysis of Competing Hypotheses",
        summary="H1 is most likely based on available evidence.",
    )


@pytest.mark.asyncio
async def test_session_full_cycle():
    """Test full critique → rebuttal → adjudication cycle."""
    config = _make_config(with_adjudicator=True)

    # Create mock providers that return appropriate responses
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
            technique_result=_make_technique_result(),
            question="Will AI surpass human intelligence?",
            evidence="Multiple expert forecasts available.",
        )

    assert exchange.technique_id == "ach"
    assert len(exchange.rounds) == 1
    assert exchange.rounds[0].critique.severity == "Moderate"
    assert exchange.rounds[0].rebuttal is not None
    assert exchange.adjudication is not None
    assert exchange.adjudication.synthesis_assessment.startswith("H1")


@pytest.mark.asyncio
async def test_session_without_adjudicator():
    """Test cycle without adjudicator."""
    config = _make_config(with_adjudicator=False)

    challenger_mock = AsyncMock()
    challenger_mock.generate_structured.return_value = _make_critique()

    primary_mock = AsyncMock()
    primary_mock.generate_structured.return_value = _make_rebuttal()

    pool = ProviderPool(config)
    with (
        patch.object(pool, "get_challenger", return_value=challenger_mock),
        patch.object(pool, "get_primary", return_value=primary_mock),
        patch.object(pool, "get_adjudicator", return_value=None),
    ):
        session = AdversarialSession(pool, config)
        exchange = await session.run_adversarial_technique(
            technique_result=_make_technique_result(),
            question="Test question",
        )

    assert exchange.adjudication is None
    assert len(exchange.rounds) == 1


@pytest.mark.asyncio
async def test_session_multiple_rounds():
    """Test multiple critique-rebuttal rounds."""
    config = _make_config(with_adjudicator=False)
    config = config.model_copy(update={"rounds": 2})

    challenger_mock = AsyncMock()
    challenger_mock.generate_structured.return_value = _make_critique()

    primary_mock = AsyncMock()
    primary_mock.generate_structured.return_value = _make_rebuttal()

    pool = ProviderPool(config)
    with (
        patch.object(pool, "get_challenger", return_value=challenger_mock),
        patch.object(pool, "get_primary", return_value=primary_mock),
        patch.object(pool, "get_adjudicator", return_value=None),
    ):
        session = AdversarialSession(pool, config)
        exchange = await session.run_adversarial_technique(
            technique_result=_make_technique_result(),
            question="Test question",
        )

    assert len(exchange.rounds) == 2
    assert exchange.rounds[0].round_number == 1
    assert exchange.rounds[1].round_number == 2
