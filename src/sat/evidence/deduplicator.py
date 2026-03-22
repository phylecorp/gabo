"""Cross-source evidence deduplication via LLM-based similarity detection.

@decision DEC-EVIDENCE-004
@title LLM-based semantic deduplication for cross-source evidence items
@status accepted
@rationale Exact text matching misses near-duplicates across sources (e.g., "GDP grew 2.3%
in Q3" vs "Q3 GDP growth was 2.3 percent"). Applying the same LLM-based grouping pattern
as decomposition/deduplicator.py to cross-source evidence items. On LLM failure, returns
items unmodified so the pipeline continues safely.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from sat.models.evidence import EvidenceItem
from sat.providers.base import LLMMessage

logger = logging.getLogger(__name__)

_SOURCE_PRIORITY = {"research": 0, "decomposition": 1, "user": 2}

_DEDUP_SYSTEM = """You are a precise deduplication engine. Given a list of evidence items from multiple sources, identify groups of items that express the SAME factual claim — even if worded differently.

Rules:
- Two items are duplicates only if they convey the same specific factual information
- Different statistics about the same topic are NOT duplicates (e.g., "GDP grew 2.3%" and "GDP grew 1.8% last year" are distinct)
- Items with different scopes, time periods, or specificity are NOT duplicates
- Be conservative: when in doubt, do NOT mark items as duplicates

For each group of duplicates, pick the item with the most precise or complete wording as canonical.

Return your analysis as structured JSON with a `duplicate_groups` array. Each group has:
- `canonical_item_id`: The item_id to keep
- `duplicate_item_ids`: List of item_ids that are near-duplicates of the canonical"""


class DuplicateGroup(BaseModel):
    """A group of near-duplicate evidence items."""

    canonical_item_id: str = Field(description="The item_id to keep")
    duplicate_item_ids: list[str] = Field(
        default_factory=list,
        description="Item IDs that are near-duplicates of the canonical",
    )


class DeduplicationResponse(BaseModel):
    """LLM response for the evidence deduplication pass."""

    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)


async def deduplicate_evidence(
    items: list[EvidenceItem],
    provider: object,
) -> tuple[list[EvidenceItem], int]:
    """Identify and remove semantically duplicate evidence items via LLM.

    For each duplicate group, the canonical item absorbs source_ids from duplicates.
    Priority: research > decomposition > user. On any failure, returns originals.

    Args:
        items: Evidence items to deduplicate (already exact-match deduped).
        provider: LLM provider with generate_structured().

    Returns:
        (deduplicated_items, num_removed)
    """
    if len(items) < 5:
        return items, 0

    # Build compact representation for the LLM
    items_data = [
        {"item_id": item.item_id, "claim": item.claim, "source": item.source} for item in items
    ]
    items_json = json.dumps(items_data, indent=2)

    try:
        system_prompt = _DEDUP_SYSTEM
        messages = [
            LLMMessage(
                role="user",
                content=f"Review these evidence items for semantic duplicates:\n\n{items_json}",
            )
        ]
        response: DeduplicationResponse = await provider.generate_structured(  # type: ignore[union-attr]
            system_prompt=system_prompt,
            messages=messages,
            output_schema=DeduplicationResponse,
        )
    except Exception as exc:
        logger.warning("Evidence deduplication LLM call failed: %s — returning originals", exc)
        return items, 0

    if not response.duplicate_groups:
        return items, 0

    # Build lookup
    item_map: dict[str, EvidenceItem] = {item.item_id: item for item in items}
    ids_to_remove: set[str] = set()

    for group in response.duplicate_groups:
        canonical = item_map.get(group.canonical_item_id)
        if canonical is None:
            continue
        merged_source_ids = list(canonical.source_ids)
        for dup_id in group.duplicate_item_ids:
            dup = item_map.get(dup_id)
            if dup is None:
                continue
            # Merge source_ids from duplicate into canonical
            for sid in dup.source_ids:
                if sid not in merged_source_ids:
                    merged_source_ids.append(sid)
            ids_to_remove.add(dup_id)
        # Update canonical with merged source_ids
        item_map[group.canonical_item_id] = canonical.model_copy(
            update={"source_ids": merged_source_ids}
        )

    deduplicated = [item_map[item.item_id] for item in items if item.item_id not in ids_to_remove]
    return deduplicated, len(ids_to_remove)
