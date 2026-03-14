"""Prompts for atomic fact decomposition.

@decision DEC-DECOMP-002: Decomposition as optional pipeline phase.
@title LLM prompts for fact extraction and deduplication
@status accepted
@rationale Follows the established prompt pattern (Python f-strings, tuple return).
Date injection per DEC-PROMPT-BASE-002. Source index included so facts reference
specific documents.
"""

from __future__ import annotations

from datetime import date

from sat.providers.base import LLMMessage

_EXTRACTION_SYSTEM = """\
You are an expert analyst extracting atomic facts from evidence text.

Extract every distinct, verifiable claim as a separate atomic fact. Each fact must be:
- Self-contained (understandable without context)
- Atomic (one claim per fact)
- Faithful to the source (no paraphrasing that changes meaning)

For each fact provide:
- claim: The atomic claim statement (complete sentence)
- source_ids: List of source IDs from the source index that support this claim
- category: One of: fact, opinion, prediction, context
- confidence: One of: high, medium, low
- temporal_marker: Time reference if present (null if none)
- entities: Named entities mentioned (people, places, organizations, dates)

Return a JSON object with a "facts" array. Each element must have all fields above.
Do NOT re-extract facts already listed in the prior facts list.
"""

_DEDUP_SYSTEM = """\
You are an expert at identifying near-duplicate claims in a fact list.

Review the provided facts (as JSON) and identify groups of facts that express
essentially the same claim with minor wording differences.

For each group of near-duplicates, nominate one canonical fact (the most complete
and precise wording) and list the others as duplicates.

Return a JSON object with a "duplicate_groups" array. Each element must have:
- canonical_fact_id: The fact_id to keep (string, e.g. "F3")
- duplicate_fact_ids: List of fact_ids that are near-duplicates of the canonical (e.g. ["F7", "F12"])

Only include groups with at least one duplicate. If no duplicates exist, return
{"duplicate_groups": []}.
"""


def build_decomposition_prompt(
    evidence_chunk: str,
    prior_facts: list[str],
    source_index: str,
) -> tuple[str, list[LLMMessage]]:
    """Build the extraction prompt for one evidence chunk.

    Args:
        evidence_chunk: The text to extract facts from.
        prior_facts: Already-extracted facts (shown to avoid re-extraction).
        source_index: Formatted source index string for provenance.

    Returns:
        (system_prompt, [user_message])
    """
    today = date.today().isoformat()
    prior_section = ""
    if prior_facts:
        prior_lines = "\n".join(prior_facts)
        prior_section = f"\n\n## Already Extracted (do NOT re-extract)\n\n{prior_lines}"

    user_msg = (
        f"Today's date: {today}\n\n"
        f"## Source Index\n\n{source_index}{prior_section}\n\n"
        f"## Evidence\n\n{evidence_chunk}"
    )
    return _EXTRACTION_SYSTEM, [LLMMessage(role="user", content=user_msg)]


def build_dedup_prompt(facts_json: str) -> tuple[str, list[LLMMessage]]:
    """Build the deduplication prompt.

    Args:
        facts_json: JSON string of the full facts list.

    Returns:
        (system_prompt, [user_message])
    """
    user_msg = f"Review these facts for near-duplicates:\n\n{facts_json}"
    return _DEDUP_SYSTEM, [LLMMessage(role="user", content=user_msg)]
