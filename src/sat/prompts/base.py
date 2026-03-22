"""Prompt building utilities shared across technique prompts.

@decision DEC-PROMPT-BASE-001: Python string templates instead of Jinja2 files.
Prompts are defined as functions returning (system_prompt, user_message) tuples.
Uses Python f-strings and helper functions rather than Jinja2 for simplicity —
Jinja2 would add complexity without benefit since our conditionals are simple
if/else blocks. Templates ship as code, not data files.

@decision DEC-PROMPT-BASE-002: Inject current date as first line of every user message.
Models have no internal clock — without a date they reason from their training
cutoff, producing stale or incorrectly-timed assessments. Injecting today's ISO
date as the very first line grounds all temporal reasoning in the actual present.

@decision DEC-PROMPT-BASE-003: Deterministic formatter replaces LLM-generated evidence strings.
format_research_evidence() renders ResearchResult structured data into deterministic
markdown rather than relying on the LLM-generated formatted_evidence field. This
ensures every claim, source, and gap appears in the pipeline injection — no silent
drops — and makes evidence content predictable for debugging and testing. The
formatted_evidence field is preserved as-is for artifact files (human-readable
LLM prose); only the pipeline injection is changed.
"""

from __future__ import annotations

from datetime import date

from sat.models.base import ArtifactResult
from sat.models.evidence import TechniqueEvidence
from sat.models.research import ResearchResult


def format_research_evidence(result: ResearchResult) -> str:
    """Render a ResearchResult into a deterministic markdown evidence string.

    Produces structured sections for Key Claims, Source Registry, Information
    Gaps, and Verification Summary. Every claim and source appears — no silent
    drops. Sections are omitted (not shown as empty) when the underlying list
    is empty, except that a note is shown when no claims or sources exist.

    Args:
        result: The structured ResearchResult from the deep research phase.

    Returns:
        A deterministic markdown string suitable for pipeline evidence injection.
    """
    parts: list[str] = []

    # --- Key Claims ---
    if result.claims:
        claim_lines = ["## Key Claims\n"]
        for claim in result.claims:
            source_ref = ", ".join(claim.source_ids) if claim.source_ids else "no sources"
            line = f"- **[{claim.confidence}/{claim.category}]** {claim.claim} *(sources: {source_ref})*"
            if claim.verified and claim.verification_verdict:
                line += f" — {claim.verification_verdict}"
            claim_lines.append(line)
        parts.append("\n".join(claim_lines))
    else:
        parts.append("## Key Claims\n\nNone identified.")

    # --- Source Registry ---
    if result.sources:
        source_lines = ["## Source Registry\n"]
        for source in result.sources:
            url_part = f" — {source.url}" if source.url else ""
            source_lines.append(
                f"- **[{source.id}]** {source.title} "
                f"({source.source_type}, reliability: {source.reliability_assessment}){url_part}"
            )
        parts.append("\n".join(source_lines))
    else:
        parts.append("## Source Registry\n\nNone identified.")

    # --- Information Gaps ---
    if result.gaps_identified:
        gap_lines = ["## Information Gaps\n"]
        for gap in result.gaps_identified:
            gap_lines.append(f"- {gap}")
        parts.append("\n".join(gap_lines))

    # --- Verification Summary ---
    if result.verification_status:
        summary_lines = [f"## Verification Summary\n\n**Status:** {result.verification_status}"]
        if result.verification_summary:
            summary_lines.append(f"\n{result.verification_summary}")
        parts.append("\n".join(summary_lines))

    return "\n\n".join(parts)


def format_evidence_section(evidence: TechniqueEvidence | str | None) -> str:
    """Format the evidence section for inclusion in a user message.

    When given TechniqueEvidence with structured items, appends an Evidence Registry
    listing each item's ID, confidence, category, and verification status. This enables
    downstream techniques to cite specific evidence items by ID in their outputs.

    @decision DEC-PROMPT-BASE-005: Evidence registry injection for cross-referencing.
    When structured evidence items are available, the evidence section includes both
    the full text AND a registry of items with IDs. Techniques can then cite D-F1,
    R-C1, etc. in their outputs, creating traceable evidence-to-finding links.
    The registry is injected only when items are present — plain text evidence and
    no-evidence cases are unaffected, preserving full backward compatibility.
    """
    if not evidence:
        return ""
    text = evidence.as_text() if hasattr(evidence, "as_text") else evidence

    parts = [f"\n## Evidence / Context\n\n{text}\n"]

    # Append structured evidence registry when items are available
    if hasattr(evidence, "items") and evidence.items:
        registry_lines = ["\n## Evidence Registry\n"]
        registry_lines.append("Use the IDs below when referencing evidence in your analysis.\n")
        for item in evidence.items:
            verified_tag = " verified" if item.verified else ""
            registry_lines.append(
                f"- **[{item.item_id}]** ({item.confidence}/{item.category}{verified_tag}) {item.claim}"
            )
        parts.append("\n".join(registry_lines))

    return "\n".join(parts)


# @decision DEC-PROMPT-BASE-004: Technique-aware prior results formatting.
# Instead of dumping full model_dump_json (which wastes tokens on structural
# metadata like technique_id and technique_name), extract only analytically
# relevant fields per technique type. Downstream techniques need the analytical
# content, not the schema scaffolding. Fallback includes all non-base fields
# for unknown technique types.
_TECHNIQUE_KEY_FIELDS: dict[str, list[str]] = {
    "assumptions": ["assumptions", "most_vulnerable"],
    "ach": [
        "hypotheses",
        "evidence",
        "most_likely",
        "rejected",
        "diagnosticity_notes",
        "inconsistency_scores",
    ],
    "quality": ["sources", "overall_assessment", "key_gaps", "deception_indicators"],
    "indicators": ["indicators", "trigger_mechanisms", "overall_trajectory"],
    "devils_advocacy": [
        "challenged_assumptions",
        "alternative_hypothesis",
        "supporting_evidence_for_alternative",
        "conclusion",
    ],
    "red_team": [
        "adversary_identity",
        "first_person_memo",
        "predicted_actions",
        "key_motivations",
        "constraints_on_adversary",
    ],
    "brainstorming": ["divergent_ideas", "clusters", "priority_areas", "unconventional_insights"],
    "alt_futures": ["key_uncertainties", "scenarios", "x_axis", "y_axis"],
    "outside_in": ["forces", "key_external_drivers", "overlooked_factors", "implications"],
    "what_if": [
        "assumed_event",
        "chain_of_argumentation",
        "alternative_pathways",
        "indicators",
        "probability_reassessment",
    ],
    "high_impact": ["event_definition", "pathways", "deflection_factors", "policy_implications"],
    "team_ab": ["team_a", "team_b", "debate_points", "jury_assessment"],
}

_BASE_FIELDS = {"technique_id", "technique_name", "summary"}


def _format_field_value(value: object) -> str:
    """Format a field value as compact readable text."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if not value:
            return "None"
        if isinstance(value[0], str):
            return "; ".join(str(v) for v in value)
        if isinstance(value[0], dict):
            items = []
            for item in value:
                parts = [
                    f"{k}: {v}" for k, v in item.items() if v is not None and k not in _BASE_FIELDS
                ]
                if parts:
                    items.append(", ".join(parts))
            return "\n  - " + "\n  - ".join(items) if items else "None"
        return str(value)
    if isinstance(value, dict):
        if not value:
            return "None"
        parts = [f"{k}: {v}" for k, v in value.items()]
        return "; ".join(parts)
    return str(value)


def format_prior_results_section(
    prior_results: dict[str, ArtifactResult],
    relevant_ids: list[str] | None = None,
) -> str:
    """Format prior technique results for inclusion in a user message.

    Uses technique-aware field extraction to include only analytically relevant
    content, reducing token waste from structural metadata and schema fields.

    Args:
        prior_results: All prior results keyed by technique_id.
        relevant_ids: If provided, only include these technique IDs.
                      If None, include all.
    """
    if not prior_results:
        return ""

    ids_to_include = relevant_ids if relevant_ids else list(prior_results.keys())
    sections = []

    for tid in ids_to_include:
        if tid not in prior_results:
            continue
        result = prior_results[tid]
        section_parts = [
            f"### {result.technique_name}\n",
            f"**Summary:** {result.summary}\n",
        ]

        # Extract technique-specific key fields
        key_fields = _TECHNIQUE_KEY_FIELDS.get(tid)
        data = result.model_dump()

        if key_fields:
            field_parts = []
            for field_name in key_fields:
                if field_name in data and data[field_name]:
                    label = field_name.replace("_", " ").title()
                    field_parts.append(f"**{label}:** {_format_field_value(data[field_name])}")
            if field_parts:
                section_parts.append("\n".join(field_parts))
        else:
            # Fallback for unknown techniques: all non-base fields
            field_parts = []
            for field_name, value in data.items():
                if field_name not in _BASE_FIELDS and value:
                    label = field_name.replace("_", " ").title()
                    field_parts.append(f"**{label}:** {_format_field_value(value)}")
            if field_parts:
                section_parts.append("\n".join(field_parts))

        sections.append("\n".join(section_parts))

    if not sections:
        return ""

    return "\n## Prior Analysis Results\n\n" + "\n\n".join(sections) + "\n"


def build_user_message(
    question: str,
    evidence: TechniqueEvidence | str | None = None,
    prior_results: dict[str, ArtifactResult] | None = None,
    relevant_prior_ids: list[str] | None = None,
) -> str:
    """Build the standard user message with question, evidence, and prior results.

    The current date is injected as the first line to ground the model's temporal
    reasoning in the present rather than its training cutoff.
    """
    parts = [
        f"Today's date is {date.today().isoformat()}.\n",
        f"## Analytic Question\n\n{question}\n",
    ]
    parts.append(format_evidence_section(evidence))
    if prior_results:
        parts.append(format_prior_results_section(prior_results, relevant_prior_ids))
    return "\n".join(part for part in parts if part)
