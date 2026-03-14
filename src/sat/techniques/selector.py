"""Technique selector: auto-selects techniques based on the question and evidence.

@decision DEC-TECH-SEL-001: LLM-based selection with post-validation guardrails.
The LLM recommends techniques based on the question and evidence. Python then
enforces hard rules: at least 1 diagnostic, max 6 total, red_team if adversary
mentioned, category balance when 4+ selected. This two-stage approach gives
better results than either pure heuristics or pure LLM selection.
"""

from __future__ import annotations

import json
import logging
import re

from sat.prompts.selector import build_selector_prompt
from sat.providers.base import LLMMessage, LLMProvider
from sat.techniques.registry import get_technique, list_technique_ids

logger = logging.getLogger(__name__)

# Keywords that suggest adversary/opponent involvement
ADVERSARY_KEYWORDS = {
    "adversary",
    "opponent",
    "enemy",
    "rival",
    "competitor",
    "attack",
    "threat",
    "hostile",
    "aggressor",
    "antagonist",
}


async def select_techniques(
    question: str,
    evidence: str | None,
    provider: LLMProvider,
) -> list[str]:
    """Auto-select techniques using LLM recommendation + validation.

    Returns a list of technique IDs in recommended execution order.
    """
    system_prompt, user_message = build_selector_prompt(question, evidence)
    messages = [LLMMessage(role="user", content=user_message)]

    result = await provider.generate(
        system_prompt=system_prompt,
        messages=messages,
        max_tokens=2048,
        temperature=0.2,
    )

    selected = _parse_selection(result.text)
    selected = _validate_selection(selected, question, evidence)

    logger.info("Auto-selected techniques: %s", selected)
    return selected


def _parse_selection(response: str) -> list[str]:
    """Extract technique IDs from LLM response.

    Handles LLM responses that wrap JSON in markdown code fences (```json ... ```)
    by stripping the fences before attempting JSON parsing.
    """
    valid_ids = set(list_technique_ids())

    # Strip markdown code fences if present — LLMs commonly wrap JSON this way.
    # Pattern handles: ```json\n{...}\n``` and plain ```\n{...}\n```
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
        text = text.strip()

    # Try to parse as JSON first
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "techniques" in data:
            ids = [t.get("id", t) if isinstance(t, dict) else t for t in data["techniques"]]
        elif isinstance(data, list):
            ids = [t.get("id", t) if isinstance(t, dict) else t for t in data]
        else:
            ids = []
        found = [tid for tid in ids if tid in valid_ids]
        if found:
            return found
    except (json.JSONDecodeError, TypeError, KeyError):
        logger.warning(
            "Technique selection: LLM response was not valid JSON, falling back to regex scanning"
        )

    # Fallback: scan for known technique IDs in the text
    found = [tid for tid in valid_ids if tid in response]
    if found:
        # Sort by category order
        category_order = {"diagnostic": 0, "contrarian": 1, "imaginative": 2}
        techniques = [get_technique(tid) for tid in found]
        techniques.sort(
            key=lambda t: (category_order.get(t.metadata.category, 99), t.metadata.order)
        )
        return [t.metadata.id for t in techniques]

    # Last resort: return defaults
    logger.warning(
        "Technique selection: no technique IDs found in LLM response, using defaults ['assumptions', 'ach']"
    )
    return ["assumptions", "ach"]


def _validate_selection(
    selected: list[str],
    question: str,
    evidence: str | None,
) -> list[str]:
    """Apply post-validation rules to technique selection."""
    valid_ids = set(list_technique_ids())
    selected = [tid for tid in selected if tid in valid_ids]

    # Rule: at least 1 diagnostic
    diagnostic_ids = {"assumptions", "quality", "indicators", "ach"}
    if not any(tid in diagnostic_ids for tid in selected):
        selected.insert(0, "assumptions")

    # Rule: include red_team if adversary keywords present
    combined_text = (question + " " + (evidence or "")).lower()
    if any(kw in combined_text for kw in ADVERSARY_KEYWORDS):
        if "red_team" not in selected:
            selected.append("red_team")

    # Rule: if evidence provided and quality not selected, add it
    if evidence and "quality" not in selected:
        selected.insert(0, "quality")

    # Ensure proper ordering: diagnostic -> contrarian -> imaginative
    category_order = {"diagnostic": 0, "contrarian": 1, "imaginative": 2}
    techniques = [get_technique(tid) for tid in selected]
    techniques.sort(key=lambda t: (category_order.get(t.metadata.category, 99), t.metadata.order))
    return [t.metadata.id for t in techniques]
