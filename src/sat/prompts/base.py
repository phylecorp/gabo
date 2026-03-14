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


def format_evidence_section(evidence: str | None) -> str:
    """Format the evidence section for inclusion in a user message."""
    if not evidence:
        return ""
    return f"\n## Evidence / Context\n\n{evidence}\n"


def format_prior_results_section(
    prior_results: dict[str, ArtifactResult],
    relevant_ids: list[str] | None = None,
) -> str:
    """Format prior technique results for inclusion in a user message.

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
        sections.append(
            f"### {result.technique_name}\n\n"
            f"**Summary:** {result.summary}\n\n"
            f"**Full output:**\n```json\n{result.model_dump_json(indent=2)}\n```"
        )

    if not sections:
        return ""

    return "\n## Prior Analysis Results\n\n" + "\n\n".join(sections) + "\n"


def build_user_message(
    question: str,
    evidence: str | None = None,
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
