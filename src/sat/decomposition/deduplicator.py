"""Fact deduplication via LLM-based similarity detection.

@decision DEC-DECOMP-003: Formatted facts as pipeline evidence.
@title LLM-based deduplication of atomic facts
@status accepted
@rationale Facts extracted from overlapping chunks may contain near-duplicates.
LLM identifies semantic duplicates and merges their source_ids into the canonical fact.
Conservative: on LLM failure, return original facts unmodified.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from sat.decomposition.prompts import build_dedup_prompt
from sat.models.decomposition import AtomicFact

logger = logging.getLogger(__name__)


class DuplicateGroup(BaseModel):
    """A group of near-duplicate facts with a nominated canonical."""

    canonical_fact_id: str = Field(description="The fact_id to keep")
    duplicate_fact_ids: list[str] = Field(
        default_factory=list, description="Fact IDs that are near-duplicates of the canonical"
    )


class DeduplicationResponse(BaseModel):
    """LLM response for the deduplication pass."""

    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)


async def deduplicate_facts(
    facts: list[AtomicFact],
    provider: object,
) -> tuple[list[AtomicFact], int]:
    """Identify and remove near-duplicate facts via LLM.

    For each duplicate group returned by the LLM, the canonical fact has all
    source_ids from duplicates merged into it, and the duplicates are dropped.
    On any LLM or parsing failure, returns the original list unmodified with 0
    removals so the pipeline continues safely.

    Args:
        facts: List of AtomicFact objects to deduplicate.
        provider: LLM provider implementing generate_structured().

    Returns:
        (deduplicated_facts, num_removed)
    """
    if len(facts) < 5:
        return facts, 0

    facts_data = [f.model_dump() for f in facts]
    facts_json = json.dumps(facts_data, indent=2)

    try:
        system_prompt, messages = build_dedup_prompt(facts_json)
        response: DeduplicationResponse = await provider.generate_structured(  # type: ignore[union-attr]
            system_prompt=system_prompt,
            messages=messages,
            output_schema=DeduplicationResponse,
        )
    except Exception as exc:
        logger.warning("Deduplication LLM call failed: %s — returning originals", exc)
        return facts, 0

    if not response.duplicate_groups:
        return facts, 0

    # Build lookup by fact_id
    fact_map: dict[str, AtomicFact] = {f.fact_id: f for f in facts}
    ids_to_remove: set[str] = set()

    for group in response.duplicate_groups:
        canonical = fact_map.get(group.canonical_fact_id)
        if canonical is None:
            continue
        merged_source_ids = list(canonical.source_ids)
        for dup_id in group.duplicate_fact_ids:
            dup = fact_map.get(dup_id)
            if dup is None:
                continue
            for sid in dup.source_ids:
                if sid not in merged_source_ids:
                    merged_source_ids.append(sid)
            ids_to_remove.add(dup_id)
        # Update canonical with merged source_ids
        fact_map[group.canonical_fact_id] = canonical.model_copy(
            update={"source_ids": merged_source_ids}
        )

    deduplicated = [fact_map[f.fact_id] for f in facts if f.fact_id not in ids_to_remove]
    return deduplicated, len(ids_to_remove)
