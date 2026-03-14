"""Adversarial session orchestrator.

@decision DEC-ADV-004: Session manages the full critique-rebuttal-adjudication cycle.
@title Per-technique adversarial debate orchestrator
@status accepted
@rationale Runs per-technique: primary's output is critiqued by challenger, primary
rebuts, optionally adjudicator resolves. Multiple rounds supported via config.rounds.
Returns AdversarialExchange with all artifacts for writing.

@decision DEC-ADV-007: Dual/trident dispatch based on config.mode.
@title _run_dual extracts original logic; _run_trident adds IPA with investigator
@status accepted
@rationale Dual mode is unchanged: N critique-rebuttal rounds then optional
adjudication. Trident mode runs critique+investigation in parallel (asyncio.gather),
then rebuttal, then convergence analysis, then enhanced adjudication that sees all
three perspectives. If investigator is unavailable, trident falls back to dual.
"""

from __future__ import annotations

import asyncio
import logging
import time

from sat.adversarial.config import AdversarialConfig
from sat.adversarial.pool import ProviderPool
from sat.models.adversarial import (
    AdjudicationResult,
    AdversarialExchange,
    ConvergenceResult,
    CritiqueResult,
    DebateRound,
    RebuttalResult,
)
from sat.models.base import ArtifactResult
from sat.prompts.adversarial import (
    build_adjudication_prompt,
    build_convergence_prompt,
    build_critique_prompt,
    build_rebuttal_prompt,
)
from sat.techniques.base import TechniqueContext
from sat.techniques.registry import get_technique

logger = logging.getLogger(__name__)


class AdversarialSession:
    """Orchestrates adversarial analysis for technique outputs."""

    def __init__(self, pool: ProviderPool, config: AdversarialConfig) -> None:
        self._pool = pool
        self._config = config

    async def run_adversarial_technique(
        self,
        technique_result: ArtifactResult,
        question: str,
        evidence: str | None = None,
    ) -> AdversarialExchange:
        """Run adversarial analysis on a single technique's output.

        Dispatches to _run_dual or _run_trident based on config.mode.

        Args:
            technique_result: The primary's output for this technique
            question: The analytic question
            evidence: Available evidence

        Returns:
            AdversarialExchange with all debate rounds and optional adjudication
        """
        if self._config.mode == "trident":
            return await self._run_trident(technique_result, question, evidence)
        return await self._run_dual(technique_result, question, evidence)

    async def _run_dual(
        self,
        technique_result: ArtifactResult,
        question: str,
        evidence: str | None = None,
    ) -> AdversarialExchange:
        """Run dual-mode adversarial analysis: N rounds of critique-rebuttal, optional adjudication."""
        challenger = self._pool.get_challenger()
        primary = self._pool.get_primary()
        rounds: list[DebateRound] = []

        last_critique: CritiqueResult | None = None

        for round_num in range(1, self._config.rounds + 1):
            logger.info(
                "Adversarial round %d for %s",
                round_num,
                technique_result.technique_id,
            )

            # Step 1: Challenger critiques
            logger.info(
                "[%s] Round %d/%d: challenger critiquing...",
                technique_result.technique_id,
                round_num,
                self._config.rounds,
            )
            t0 = time.monotonic()
            critique_prompt, critique_msgs = build_critique_prompt(
                technique_result=technique_result,
                question=question,
                evidence=evidence,
            )
            critique = await challenger.generate_structured(
                system_prompt=critique_prompt,
                messages=critique_msgs,
                output_schema=CritiqueResult,
                max_tokens=16384,
            )
            assert isinstance(critique, CritiqueResult)
            last_critique = critique
            logger.info(
                "[%s] Round %d/%d: critique done in %.1fs",
                technique_result.technique_id,
                round_num,
                self._config.rounds,
                time.monotonic() - t0,
            )

            # Step 2: Primary rebuts
            logger.info(
                "[%s] Round %d/%d: primary rebutting...",
                technique_result.technique_id,
                round_num,
                self._config.rounds,
            )
            t0 = time.monotonic()
            rebuttal_prompt, rebuttal_msgs = build_rebuttal_prompt(
                technique_result=technique_result,
                critique=critique,
                question=question,
                evidence=evidence,
            )
            rebuttal = await primary.generate_structured(
                system_prompt=rebuttal_prompt,
                messages=rebuttal_msgs,
                output_schema=RebuttalResult,
                max_tokens=16384,
            )
            assert isinstance(rebuttal, RebuttalResult)
            logger.info(
                "[%s] Round %d/%d: rebuttal done in %.1fs",
                technique_result.technique_id,
                round_num,
                self._config.rounds,
                time.monotonic() - t0,
            )

            rounds.append(
                DebateRound(
                    round_number=round_num,
                    critique=critique,
                    rebuttal=rebuttal,
                )
            )

        # Step 3: Optional adjudication
        adjudication = None
        adjudicator = self._pool.get_adjudicator()
        if adjudicator and last_critique and rounds:
            last_rebuttal = rounds[-1].rebuttal
            if last_rebuttal:
                logger.info("[%s] Adjudicating...", technique_result.technique_id)
                t0 = time.monotonic()
                adj_prompt, adj_msgs = build_adjudication_prompt(
                    technique_result=technique_result,
                    critique=last_critique,
                    rebuttal=last_rebuttal,
                    question=question,
                    evidence=evidence,
                )
                adjudication = await adjudicator.generate_structured(
                    system_prompt=adj_prompt,
                    messages=adj_msgs,
                    output_schema=AdjudicationResult,
                    max_tokens=8192,
                )
                assert isinstance(adjudication, AdjudicationResult)
                logger.info(
                    "[%s] Adjudication done in %.1fs",
                    technique_result.technique_id,
                    time.monotonic() - t0,
                )

        return AdversarialExchange(
            technique_id=technique_result.technique_id,
            initial_result=technique_result,
            rounds=rounds,
            adjudication=adjudication,
        )

    async def _run_trident(
        self,
        technique_result: ArtifactResult,
        question: str,
        evidence: str | None = None,
    ) -> AdversarialExchange:
        """Run trident-mode adversarial analysis: parallel critique+investigation,
        rebuttal, convergence, enhanced adjudication.

        Falls back to dual mode if no investigator is configured.
        """
        investigator_provider = self._pool.get_investigator()
        if investigator_provider is None:
            logger.warning(
                "Trident mode requested but no investigator configured — falling back to dual"
            )
            return await self._run_dual(technique_result, question, evidence)

        challenger = self._pool.get_challenger()
        primary = self._pool.get_primary()

        # Phase 1: Parallel — critique AND independent investigation
        logger.info(
            "Trident Phase 1: parallel critique+investigation for %s — waiting...",
            technique_result.technique_id,
        )
        t0 = time.monotonic()

        technique = get_technique(technique_result.technique_id)
        inv_ctx = TechniqueContext(question=question, evidence=evidence)

        async def do_critique() -> CritiqueResult:
            critique_prompt, critique_msgs = build_critique_prompt(
                technique_result=technique_result,
                question=question,
                evidence=evidence,
            )
            result = await challenger.generate_structured(
                system_prompt=critique_prompt,
                messages=critique_msgs,
                output_schema=CritiqueResult,
                max_tokens=16384,
            )
            assert isinstance(result, CritiqueResult)
            logger.info(
                "[%s] Trident critique finished in %.1fs",
                technique_result.technique_id,
                time.monotonic() - t0,
            )
            return result

        async def do_investigation() -> ArtifactResult:
            result = await technique.execute(inv_ctx, investigator_provider)
            logger.info(
                "[%s] Trident investigation finished in %.1fs",
                technique_result.technique_id,
                time.monotonic() - t0,
            )
            return result

        critique_result, inv_result = await asyncio.gather(do_critique(), do_investigation())
        logger.info("Trident Phase 1: done in %.1fs", time.monotonic() - t0)

        # Fix investigator identity — technique.execute overwrites with canonical ID
        inv_result = inv_result.model_copy(
            update={
                "technique_id": f"{technique_result.technique_id}-investigator",
                "technique_name": f"{technique_result.technique_name} (Investigator)",
            }
        )

        # Phase 2: Rebuttal
        logger.info("Trident Phase 2: rebuttal for %s — waiting...", technique_result.technique_id)
        t0 = time.monotonic()
        rebuttal_prompt, rebuttal_msgs = build_rebuttal_prompt(
            technique_result=technique_result,
            critique=critique_result,
            question=question,
            evidence=evidence,
        )
        rebuttal_result = await primary.generate_structured(
            system_prompt=rebuttal_prompt,
            messages=rebuttal_msgs,
            output_schema=RebuttalResult,
            max_tokens=16384,
        )
        assert isinstance(rebuttal_result, RebuttalResult)
        logger.info("Trident Phase 2: done in %.1fs", time.monotonic() - t0)

        rounds = [
            DebateRound(
                round_number=1,
                critique=critique_result,
                rebuttal=rebuttal_result,
            )
        ]

        # Phase 3: Convergence analysis
        logger.info(
            "Trident Phase 3: convergence analysis for %s — waiting...",
            technique_result.technique_id,
        )
        t0 = time.monotonic()
        conv_prompt, conv_msgs = build_convergence_prompt(
            technique_result=technique_result,
            investigator_result=inv_result,
            critique=critique_result,
            rebuttal=rebuttal_result,
            question=question,
            evidence=evidence,
        )
        convergence = await primary.generate_structured(
            system_prompt=conv_prompt,
            messages=conv_msgs,
            output_schema=ConvergenceResult,
            max_tokens=8192,
        )
        assert isinstance(convergence, ConvergenceResult)
        logger.info("Trident Phase 3: done in %.1fs", time.monotonic() - t0)

        # Phase 4: Enhanced adjudication with all perspectives
        logger.info(
            "Trident Phase 4: adjudication for %s — waiting...", technique_result.technique_id
        )
        t0 = time.monotonic()
        adj_prompt, adj_msgs = build_adjudication_prompt(
            technique_result=technique_result,
            critique=critique_result,
            rebuttal=rebuttal_result,
            question=question,
            evidence=evidence,
            investigator_result=inv_result,
            convergence=convergence,
        )
        adjudicator = self._pool.get_adjudicator()
        adj_provider = adjudicator if adjudicator is not None else primary
        adjudication = await adj_provider.generate_structured(
            system_prompt=adj_prompt,
            messages=adj_msgs,
            output_schema=AdjudicationResult,
            max_tokens=8192,
        )
        assert isinstance(adjudication, AdjudicationResult)
        logger.info("Trident Phase 4: done in %.1fs", time.monotonic() - t0)

        return AdversarialExchange(
            technique_id=technique_result.technique_id,
            initial_result=technique_result,
            rounds=rounds,
            adjudication=adjudication,
            investigator_result=inv_result,
            convergence=convergence,
        )
