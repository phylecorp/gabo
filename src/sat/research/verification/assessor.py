"""LLM-based claim assessment against fetched source content.

@decision DEC-VERIFY-004: Cheap model for verification, batched per source.
@title One LLM call per source to assess all claims citing that source
@status accepted
@rationale Verification is a secondary pass. Cheap models reduce cost.
Batching by source reduces total API calls from O(claims) to O(sources).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field, model_validator

from sat.config import ProviderConfig
from sat.models.verification import ClaimVerification
from sat.providers.registry import create_provider

logger = logging.getLogger(__name__)

CHEAP_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
}

# @decision DEC-VERIFY-005: Parallel claim assessment bounded by semaphore.
# Assessing each source sequentially wastes wall-clock time when sources are
# independent. asyncio.gather + Semaphore runs up to _ASSESS_CONCURRENCY sources
# concurrently while still bounding API call rate.
_ASSESS_CONCURRENCY = 5  # max concurrent source assessments

VALID_VERDICTS = frozenset(
    {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "NOT_SUPPORTED",
        "CONTRADICTED",
        "INCONCLUSIVE",
        "UNVERIFIABLE",
    }
)

VALID_CONFIDENCES = frozenset({"High", "Medium", "Low"})

_SYSTEM_PROMPT = (
    "You are a fact-checking assistant. Given a source document and a list of claims "
    "that cite this source, assess each claim against the source content.\n\n"
    "For each claim, provide:\n"
    "- verdict: one of SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, CONTRADICTED, "
    "INCONCLUSIVE (content exists but cannot confirm or deny), UNVERIFIABLE (source "
    "content is insufficient to assess)\n"
    "- confidence: High, Medium, or Low confidence in your verdict\n"
    "- reasoning: one sentence explaining the verdict\n\n"
    "Be conservative -- only SUPPORTED if the source clearly states or strongly implies "
    "the claim. Use PARTIALLY_SUPPORTED if the source addresses part of the claim. "
    "Use UNVERIFIABLE if the source content is too short, paywalled, or off-topic."
)


class _AssessmentItem(BaseModel):
    claim: str = Field(description="The claim text (as provided)")
    verdict: str = Field(
        description="SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED, CONTRADICTED, INCONCLUSIVE, or UNVERIFIABLE"
    )
    confidence: str = Field(description="High, Medium, or Low")
    reasoning: str = Field(description="One-sentence explanation of the verdict")


class _SourceAssessment(BaseModel):
    assessments: list[_AssessmentItem] = Field(description="Assessment for each claim")

    @model_validator(mode="before")
    @classmethod
    def _parse_json_strings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        for key, value in data.items():
            if isinstance(value, str) and value.strip() and value.strip()[0] in ("[", "{"):
                try:
                    data[key] = json.loads(value)
                except (json.JSONDecodeError, ValueError):
                    pass  # @defprog-exempt: invalid JSON strings pass through; Pydantic validates downstream
        return data


def _build_user_message(source_id: str, source_content: str, claims: list) -> str:
    """Build the user message for a single source batch."""
    sep = "\n"
    claims_block = sep.join(f"{i + 1}. {claim.claim}" for i, claim in enumerate(claims))
    content_preview = source_content[:8000] if source_content else "[No content available]"
    newline = "\n"
    return (
        f"Source ID: {source_id}{newline}"
        f"Source Content (excerpt):{newline}{content_preview}{newline}{newline}"
        f"Claims citing this source:{newline}{claims_block}"
    )


def _sanitize_verdict(verdict: str) -> str:
    """Ensure verdict is one of the allowed values."""
    upper = verdict.strip().upper()
    if upper in VALID_VERDICTS:
        return upper
    return "INCONCLUSIVE"


def _sanitize_confidence(confidence: str) -> str:
    """Ensure confidence is one of the allowed values."""
    title = confidence.strip().title()
    if title in VALID_CONFIDENCES:
        return title
    return "Low"


async def assess_claims(
    claims: list,
    source_contents: dict[str, str],
    provider_name: str,
    model_override: str | None = None,
) -> list[ClaimVerification]:
    """Assess claims against their cited source content using a cheap LLM.

    Batches claims per source -- one LLM call per source with content. Claims
    with no fetchable source content get UNVERIFIABLE verdicts without an LLM call.

    Args:
        claims: List of ResearchClaim objects (.claim, .source_ids, .confidence).
        source_contents: Dict mapping source_id -> extracted text content.
        provider_name: LLM provider name.
        model_override: Override the cheap model for this provider.

    Returns:
        List of ClaimVerification objects, one per input claim.
    """
    if not claims:
        return []

    model = model_override or CHEAP_MODELS.get(provider_name, "claude-haiku-4-5-20251001")
    provider_config = ProviderConfig(provider=provider_name, model=model)
    try:
        provider = create_provider(provider_config)
    except Exception as exc:
        logger.warning("Could not create verification provider: %s", exc)
        return [
            ClaimVerification(
                claim=c.claim,
                source_ids=c.source_ids,
                verdict="UNVERIFIABLE",
                confidence="Low",
                reasoning="Verification provider unavailable.",
                original_confidence=c.confidence,
                adjusted_confidence=c.confidence,
            )
            for c in claims
        ]

    source_to_claims: dict[str, list] = defaultdict(list)
    for claim in claims:
        for sid in claim.source_ids:
            if sid in source_contents and source_contents[sid]:
                source_to_claims[sid].append(claim)

    claim_assessments: dict[str, list[_AssessmentItem]] = defaultdict(list)

    from sat.providers.base import LLMMessage

    sem = asyncio.Semaphore(_ASSESS_CONCURRENCY)

    async def _assess_source(source_id: str, source_claims: list) -> None:
        async with sem:
            content = source_contents.get(source_id, "")
            user_msg = _build_user_message(source_id, content, source_claims)
            messages = [LLMMessage(role="user", content=user_msg)]
            try:
                assessment: _SourceAssessment = await provider.generate_structured(
                    system_prompt=_SYSTEM_PROMPT,
                    messages=messages,
                    output_schema=_SourceAssessment,
                    max_tokens=2048,
                    temperature=0.1,
                )
                for item in assessment.assessments:
                    claim_assessments[item.claim].append(item)
            except Exception as exc:
                logger.warning("Assessment failed for source %s: %s", source_id, exc)
                for claim in source_claims:
                    claim_assessments[claim.claim].append(
                        _AssessmentItem(
                            claim=claim.claim,
                            verdict="INCONCLUSIVE",
                            confidence="Low",
                            reasoning=f"Assessment error: {exc}",
                        )
                    )

    await asyncio.gather(
        *[_assess_source(sid, sc) for sid, sc in source_to_claims.items()]
    )

    _VERDICT_PRIORITY = {
        "SUPPORTED": 6,
        "PARTIALLY_SUPPORTED": 5,
        "CONTRADICTED": 4,
        "NOT_SUPPORTED": 3,
        "INCONCLUSIVE": 2,
        "UNVERIFIABLE": 1,
    }

    results: list[ClaimVerification] = []
    for claim in claims:
        items = claim_assessments.get(claim.claim, [])

        if not items:
            results.append(
                ClaimVerification(
                    claim=claim.claim,
                    source_ids=claim.source_ids,
                    verdict="UNVERIFIABLE",
                    confidence="Low",
                    reasoning="No fetchable source content available for cited sources.",
                    original_confidence=claim.confidence,
                    adjusted_confidence=claim.confidence,
                )
            )
            continue

        best = max(items, key=lambda x: _VERDICT_PRIORITY.get(_sanitize_verdict(x.verdict), 0))
        verdict = _sanitize_verdict(best.verdict)
        confidence = _sanitize_confidence(best.confidence)

        results.append(
            ClaimVerification(
                claim=claim.claim,
                source_ids=claim.source_ids,
                verdict=verdict,
                confidence=confidence,
                reasoning=best.reasoning,
                original_confidence=claim.confidence,
                adjusted_confidence=claim.confidence,
            )
        )

    return results
