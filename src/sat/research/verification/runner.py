"""Verification runner: orchestrates fetch -> extract -> assess -> update.

@decision DEC-VERIFY-005: Confidence adjustment table applied by runner, not assessor.
@title Runner owns confidence mutation; assessor returns raw verdicts
@status accepted
@rationale Separation of concerns: assessor returns verdicts (SUPPORTED, etc.),
runner applies the confidence adjustment rules. This makes rules easy to tune
without touching assessment logic, and keeps the assessor pure (input claims,
output verdicts). The adjustment table matches the plan specification.
"""

from __future__ import annotations

import logging

from sat.models.research import ResearchResult
from sat.models.verification import ClaimVerification, FetchResult, VerificationResult
from sat.research.verification.assessor import assess_claims
from sat.research.verification.fetcher import fetch_sources

logger = logging.getLogger(__name__)

# Confidence levels in order from lowest to highest
_CONFIDENCE_LEVELS = ["Low", "Medium", "High"]

# Verdict -> confidence delta: +1, 0, or -1 level
_VERDICT_DELTA: dict[str, int] = {
    "SUPPORTED": +1,
    "PARTIALLY_SUPPORTED": 0,
    "NOT_SUPPORTED": -1,
    "CONTRADICTED": -1,
    "INCONCLUSIVE": 0,
    "UNVERIFIABLE": 0,
}


def _adjust_confidence(confidence: str, delta: int) -> str:
    """Shift confidence by delta levels, clamping to valid range."""
    try:
        idx = _CONFIDENCE_LEVELS.index(confidence)
    except ValueError:
        idx = 1  # Default to Medium if unrecognised
    new_idx = max(0, min(len(_CONFIDENCE_LEVELS) - 1, idx + delta))
    return _CONFIDENCE_LEVELS[new_idx]


def _build_summary(verifications: list[ClaimVerification], sources_fetched: int, sources_failed: int) -> str:
    """Build a human-readable summary of verification outcomes."""
    if not verifications:
        return "No claims were verified."

    counts: dict[str, int] = {}
    for v in verifications:
        counts[v.verdict] = counts.get(v.verdict, 0) + 1

    total = len(verifications)
    parts = []
    for verdict in ["SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "CONTRADICTED", "INCONCLUSIVE", "UNVERIFIABLE"]:
        n = counts.get(verdict, 0)
        if n:
            label = verdict.replace("_", " ").lower()
            parts.append(f"{n} {label}")

    claim_summary = ", ".join(parts) if parts else "no claims assessed"
    return (
        f"Verified {total} claims against {sources_fetched} sources "
        f"({sources_failed} failed to fetch). "
        f"Claims: {claim_summary}."
    )


async def verify_sources(
    research_result: ResearchResult,
    provider_name: str,
    verification_config,
) -> VerificationResult:
    """Run the full source verification pipeline.

    Fetches all source URLs concurrently, extracts text, assesses each claim
    against its cited sources using a cheap LLM, and applies confidence adjustments.

    Args:
        research_result: ResearchResult containing sources and claims.
        provider_name: LLM provider name for verification assessment.
        verification_config: VerificationConfig controlling fetch behaviour.

    Returns:
        VerificationResult with per-source fetch outcomes and per-claim verdicts.
    """
    from sat.research.verification.assessor import CHEAP_MODELS

    # Limit sources per config
    sources_to_fetch = research_result.sources[: verification_config.max_sources]

    # Phase 1: Fetch source URLs
    logger.info("Fetching %d source URLs for verification", len(sources_to_fetch))
    fetch_outcomes = await fetch_sources(
        sources=sources_to_fetch,
        timeout=verification_config.timeout,
        concurrency=verification_config.concurrency,
    )

    # Separate results and content
    fetch_results: list[FetchResult] = []
    source_contents: dict[str, str] = {}
    sources_fetched = 0
    sources_failed = 0

    for source in sources_to_fetch:
        if source.id in fetch_outcomes:
            result, text = fetch_outcomes[source.id]
            fetch_results.append(result)
            if result.status == "success":
                sources_fetched += 1
                source_contents[source.id] = text
            else:
                sources_failed += 1
        else:
            # Source had no URL — skipped
            pass

    # Phase 2: Assess claims against source content
    logger.info(
        "Assessing %d claims against %d sources with content",
        len(research_result.claims),
        len(source_contents),
    )
    model_name = verification_config.model or CHEAP_MODELS.get(
        provider_name, "claude-haiku-4-5-20251001"
    )

    raw_verifications = await assess_claims(
        claims=research_result.claims,
        source_contents=source_contents,
        provider_name=provider_name,
        model_override=verification_config.model,
    )

    # Phase 3: Apply confidence adjustments
    adjusted: list[ClaimVerification] = []
    for v in raw_verifications:
        delta = _VERDICT_DELTA.get(v.verdict, 0)
        new_confidence = _adjust_confidence(v.original_confidence, delta)
        adjusted.append(
            v.model_copy(update={"adjusted_confidence": new_confidence})
        )

    summary = _build_summary(adjusted, sources_fetched, sources_failed)

    return VerificationResult(
        technique_id="verification",
        technique_name="Source Verification",
        summary=summary,
        sources_fetched=sources_fetched,
        sources_failed=sources_failed,
        fetch_results=fetch_results,
        claim_verifications=adjusted,
        verification_model=model_name,
        verification_summary=summary,
    )
