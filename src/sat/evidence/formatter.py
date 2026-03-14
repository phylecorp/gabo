"""Format curated evidence items into the structured text that techniques expect.

@decision DEC-EVIDENCE-003
@title format_curated_evidence produces deterministic evidence string from selected items
@status accepted
@rationale Techniques expect a plain string of evidence. After curation, only selected
items need to be formatted. The output mirrors the decomposition format (facts with
source/confidence/category annotations) so existing technique prompts work unchanged.
"""

from __future__ import annotations

from collections import defaultdict

from sat.models.evidence import EvidenceItem


def format_curated_evidence(
    items: list[EvidenceItem],
    sources: list[dict],
    gaps: list[str],
) -> str:
    """Render selected evidence items into a structured text block for technique prompts.

    Produces output structurally similar to the decomposition extractor's _format_facts()
    and format_research_evidence() from prompts/base.py. Only items with selected=True
    are included.

    Args:
        items: All evidence items from the pool.
        sources: Source registry dicts from research (may be empty).
        gaps: Information gaps list (may be empty).

    Returns:
        A structured markdown string ready to be injected as config.evidence.
    """
    selected = [item for item in items if item.selected]

    if not selected:
        return ""

    n = len(selected)

    # Categorize items by source type for the header
    decomp_count = sum(1 for i in selected if i.source == "decomposition")
    research_count = sum(1 for i in selected if i.source == "research")
    user_count = sum(1 for i in selected if i.source == "user")

    source_summary_parts = []
    if decomp_count:
        source_summary_parts.append(f"{decomp_count} decomposed")
    if research_count:
        source_summary_parts.append(f"{research_count} researched")
    if user_count:
        source_summary_parts.append(f"{user_count} user-provided")
    source_summary = ", ".join(source_summary_parts) if source_summary_parts else "curated"

    lines: list[str] = [
        f"[Curated Evidence: {n} items ({source_summary})]",
        "",
        "## Facts",
        "",
    ]

    for item in selected:
        src_str = ", ".join(item.source_ids) if item.source_ids else item.source
        verified_flag = " [VERIFIED]" if item.verified else ""
        lines.append(
            f"[{item.item_id}] {item.claim} "
            f"(Source: {src_str}, Confidence: {item.confidence}, "
            f"Category: {item.category}){verified_flag}"
        )

    # Source Registry section (from research results)
    if sources:
        lines += [
            "",
            "## Source Registry",
            "",
        ]
        for src in sources:
            url_part = f" — {src['url']}" if src.get("url") else ""
            lines.append(
                f"- **[{src['id']}]** {src['title']} "
                f"({src.get('source_type', 'unknown')}, "
                f"reliability: {src.get('reliability_assessment', 'Unknown')}){url_part}"
            )

    # Information Gaps section
    if gaps:
        lines += [
            "",
            "## Information Gaps",
            "",
        ]
        for gap in gaps:
            lines.append(f"- {gap}")

    # Entity index (from items that have entity metadata)
    entity_facts: dict[str, list[str]] = defaultdict(list)
    for item in selected:
        for entity in item.entities:
            entity_facts[entity].append(item.item_id)

    if entity_facts:
        lines += [
            "",
            "## Entity Index",
            "",
        ]
        for entity in sorted(entity_facts):
            lines.append(f"{entity}: {', '.join(entity_facts[entity])}")

    return "\n".join(lines)
