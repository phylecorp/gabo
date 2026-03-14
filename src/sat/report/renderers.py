"""Technique-specific renderers for executive reports.

@decision DEC-REPORT-002
@title Technique-specific renderer registry with generic fallback
@status accepted
@rationale Each technique gets a dedicated renderer that produces proper markdown
tables and structure. Unknown technique IDs degrade gracefully via the generic
renderer. The registry maps technique_id to a render function. The ACH renderer
is migrated from artifacts.py.
"""

from __future__ import annotations

from typing import Callable

from sat.models.base import ArtifactResult

RendererFunc = Callable[[ArtifactResult], str]
_RENDERERS: dict[str, RendererFunc] = {}


def register_renderer(technique_id: str) -> Callable[[RendererFunc], RendererFunc]:
    """Decorator factory: register a renderer function for a technique ID."""

    def decorator(func: RendererFunc) -> RendererFunc:
        _RENDERERS[technique_id] = func
        return func

    return decorator


def render_technique(technique_id: str, result: ArtifactResult) -> str:
    """Render a technique result to markdown using the registered renderer."""
    renderer = _RENDERERS.get(technique_id, render_generic)
    return renderer(result)


# ---------------------------------------------------------------------------
# Generic renderer (fallback)
# ---------------------------------------------------------------------------


def render_generic(result: ArtifactResult) -> str:
    """Render any ArtifactResult as markdown using field introspection."""
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    base_fields = {"technique_id", "technique_name", "summary"}
    for name, _field_info in type(result).model_fields.items():
        if name in base_fields:
            continue
        value = getattr(result, name)
        if not value and value != 0:
            continue
        title = name.replace("_", " ").title()
        lines.append(f"**{title}**")
        lines.append("")
        lines.extend(_render_value(value))
        lines.append("")

    return "\n".join(lines)


def _render_value(value: object, indent: int = 0) -> list[str]:
    """Render a field value as markdown lines."""
    prefix = "  " * indent
    if isinstance(value, str):
        return [f"{prefix}{value}"]
    if isinstance(value, bool):
        return [f"{prefix}{'Yes' if value else 'No'}"]
    if isinstance(value, (int, float)):
        return [f"{prefix}{value}"]
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, str):
                lines.append(f"{prefix}- {item}")
            elif hasattr(item, "model_dump"):
                lines.extend(_render_model_block(item, indent))
            else:
                lines.append(f"{prefix}- {item}")
        return lines
    if isinstance(value, dict):
        return [f"{prefix}- **{k}**: {v}" for k, v in value.items()]
    if hasattr(value, "model_dump"):
        return _render_model_block(value, indent)
    return [f"{prefix}{value}"]


def _render_model_block(model: object, indent: int = 0) -> list[str]:
    """Render a Pydantic model as a markdown block."""
    lines: list[str] = []
    prefix = "  " * indent
    data = model.model_dump()  # type: ignore[union-attr]
    for key, val in data.items():
        title = key.replace("_", " ").title()
        if isinstance(val, str):
            lines.append(f"{prefix}- **{title}**: {val}")
        elif isinstance(val, list):
            lines.append(f"{prefix}- **{title}**:")
            for item in val:
                lines.append(f"{prefix}  - {item}")
        else:
            lines.append(f"{prefix}- **{title}**: {val}")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Escape helper
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """Escape pipe characters for markdown table cells."""
    return text.replace("|", "\\|").replace("\n", " ")


def _first_sentence(text: str, max_len: int = 100) -> str:
    """Extract the first sentence from text, or truncate to max_len with '...'.

    A sentence boundary is detected as a period followed by a space ('. ').
    If no boundary is found within max_len characters, the text is truncated
    at max_len and '...' is appended.  If the full text is short enough it is
    returned unchanged.
    """
    if len(text) <= max_len:
        return text
    # Look for a period-space boundary within the first max_len characters.
    boundary = text.find(". ", 0, max_len)
    if boundary != -1:
        return text[: boundary + 1]
    # Hard truncate.
    return text[:max_len] + "..."


# ---------------------------------------------------------------------------
# ACH renderer (migrated from artifacts.py)
# ---------------------------------------------------------------------------


def _ach_diagnostic_value(ratings: list[str]) -> str:
    if len(set(ratings)) > 1:
        return "HIGH"
    return "LOW"


@register_renderer("ach")
def render_ach(result: ArtifactResult) -> str:
    """Render ACH with diagnosticity matrix tables.

    Evidence uses a compact card layout (one card per evidence item) because
    description text is typically 30-80 words — too long for table cells.
    The matrix and hypotheses sections remain as compact tables since their
    cells contain only short IDs and ratings.

    Guards prevent meaningless placeholder data from appearing:
    - Inconsistency scores are hidden when all values are 0.0 or identical.
    - most_likely is hidden when empty.
    - rejected is hidden when the list is empty.
    """
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    # Hypotheses table (compact — IDs + short descriptions)
    lines += ["**Hypotheses**", ""]
    if hasattr(result, "hypotheses") and result.hypotheses:
        lines += ["| ID | Hypothesis |", "|----|------------|"]
        for h in result.hypotheses:
            lines.append(f"| {h.id} | {_esc(h.description)} |")
    else:
        lines.append("_No hypotheses recorded._")
    lines.append("")

    # Evidence — card layout (descriptions are prose, not suited to table cells)
    lines += ["**Evidence**", ""]
    if hasattr(result, "evidence") and result.evidence:
        for e in result.evidence:
            headline = _first_sentence(e.description)
            lines.append(f"#### {e.id}: {headline}")
            lines.append("")
            lines.append(f"**Credibility**: {e.credibility} | **Relevance**: {e.relevance}")
            lines.append("")
            # Show full description when it extends beyond the headline
            if e.description.strip() != headline.strip():
                lines.append(e.description)
                lines.append("")
    else:
        lines.append("_No evidence recorded._")
        lines.append("")

    # Diagnosticity matrix (compact — IDs and single-letter ratings)
    lines += ["**Diagnosticity Matrix**", ""]
    if (
        hasattr(result, "hypotheses")
        and hasattr(result, "evidence")
        and hasattr(result, "matrix")
        and result.hypotheses
        and result.evidence
        and result.matrix
    ):
        hyp_ids = [h.id for h in result.hypotheses]
        rating_index: dict[tuple[str, str], str] = {
            (r.evidence_id, r.hypothesis_id): r.rating for r in result.matrix
        }
        hyp_cols = " | ".join(hyp_ids)
        lines.append(f"| Evidence | {hyp_cols} | Diagnostic Value |")
        sep_cols = " | ".join("----" for _ in hyp_ids)
        lines.append(f"|----------|{sep_cols}|-----------------:|")
        for e in result.evidence:
            row_ratings = [rating_index.get((e.id, h_id), "\u2014") for h_id in hyp_ids]
            real_ratings = [r for r in row_ratings if r != "\u2014"]
            diag = _ach_diagnostic_value(real_ratings) if real_ratings else "LOW"
            lines.append(f"| {e.id} | " + " | ".join(row_ratings) + f" | {diag} |")
    else:
        lines.append("_No matrix data recorded._")
    lines.append("")

    # Inconsistency scores — guard: skip if all values are 0.0 or all identical
    if hasattr(result, "inconsistency_scores") and result.inconsistency_scores:
        scores = result.inconsistency_scores
        score_values = list(scores.values())
        all_zero = all(v == 0.0 for v in score_values)
        all_identical = len(set(score_values)) <= 1
        if not all_zero and not all_identical:
            lines += ["**Inconsistency Scores**", ""]
            lines += ["| Hypothesis | Score | Assessment |", "|------------|------:|------------|"]
            sorted_scores = sorted(scores.items(), key=lambda kv: kv[1])
            n = len(sorted_scores)
            for i, (h_id, score) in enumerate(sorted_scores):
                if i == n - 1 and n > 1:
                    assessment = "Most inconsistent"
                elif i == 0 and n > 1:
                    assessment = "Least inconsistent"
                else:
                    assessment = ""
                lines.append(f"| {h_id} | {score:.2f} | {assessment} |")
            lines.append("")

    # Most likely — guard: skip empty string
    if hasattr(result, "most_likely") and result.most_likely:
        hyp_map = {h.id: h.description for h in result.hypotheses} if result.hypotheses else {}
        desc = hyp_map.get(result.most_likely, "")
        label = f"{result.most_likely} \u2014 {desc}" if desc else result.most_likely
        lines += [f"**Most Likely**: {label}", ""]

    # Rejected — guard: skip empty list
    if hasattr(result, "rejected") and result.rejected:
        lines.append("**Rejected**")
        lines.append("")
        for h_id in result.rejected:
            lines.append(f"- {h_id}")
        lines.append("")

    if hasattr(result, "diagnosticity_notes") and result.diagnosticity_notes:
        lines += ["**Diagnosticity Notes**", "", result.diagnosticity_notes, ""]

    if hasattr(result, "missing_evidence") and result.missing_evidence:
        lines.append("**Missing Evidence**")
        lines.append("")
        for item in result.missing_evidence:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Indicators renderer
# ---------------------------------------------------------------------------

_TREND_ARROWS = {"Worsening": "\u2197", "Stable": "\u2192", "Improving": "\u2199"}


@register_renderer("indicators")
def render_indicators(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "hypothesis_or_scenario") and result.hypothesis_or_scenario:
        lines += [f"**Monitoring**: {result.hypothesis_or_scenario}", ""]

    if hasattr(result, "indicators") and result.indicators:
        lines += [
            "| Topic | Indicator | Status | Trend | Notes |",
            "|-------|-----------|--------|-------|-------|",
        ]
        for ind in result.indicators:
            arrow = _TREND_ARROWS.get(ind.trend, "")
            lines.append(
                f"| {_esc(ind.topic)} | {_esc(ind.indicator)} "
                f"| {ind.current_status} | {arrow} {ind.trend} | {_esc(ind.notes)} |"
            )
        lines.append("")

    if hasattr(result, "trigger_mechanisms") and result.trigger_mechanisms:
        lines.append("**Trigger Mechanisms**")
        lines.append("")
        for t in result.trigger_mechanisms:
            lines.append(f"- {t}")
        lines.append("")

    if hasattr(result, "overall_trajectory") and result.overall_trajectory:
        lines += ["**Overall Trajectory**", "", result.overall_trajectory, ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Alternative Futures renderer
# ---------------------------------------------------------------------------


@register_renderer("alt_futures")
def render_alt_futures(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "focal_issue") and result.focal_issue:
        lines += [f"**Focal Issue**: {result.focal_issue}", ""]

    if hasattr(result, "key_uncertainties") and result.key_uncertainties:
        lines.append("**Key Uncertainties**")
        lines.append("")
        for u in result.key_uncertainties:
            lines.append(f"- {u}")
        lines.append("")

    # Axes
    if hasattr(result, "x_axis") and result.x_axis:
        lines.append(
            f"**X Axis** ({result.x_axis.name}): "
            f"{result.x_axis.low_label} \u2194 {result.x_axis.high_label}"
        )
    if hasattr(result, "y_axis") and result.y_axis:
        lines.append(
            f"**Y Axis** ({result.y_axis.name}): "
            f"{result.y_axis.low_label} \u2194 {result.y_axis.high_label}"
        )
    if hasattr(result, "x_axis") and result.x_axis:
        lines.append("")

    # Scenarios
    if hasattr(result, "scenarios") and result.scenarios:
        for i, s in enumerate(result.scenarios, 1):
            lines.append(f"**Scenario {i}: {s.scenario_name}** ({s.quadrant_label})")
            lines.append("")
            lines.append(s.narrative)
            lines.append("")
            if s.indicators:
                lines.append("*Indicators*:")
                for ind in s.indicators:
                    lines.append(f"- {ind}")
                lines.append("")
            if s.policy_implications:
                lines.append(f"*Policy Implications*: {s.policy_implications}")
                lines.append("")

    if hasattr(result, "cross_cutting_indicators") and result.cross_cutting_indicators:
        lines.append("**Cross-Cutting Indicators**")
        lines.append("")
        for c in result.cross_cutting_indicators:
            lines.append(f"- {c}")
        lines.append("")

    if hasattr(result, "strategic_implications") and result.strategic_implications:
        lines += ["**Strategic Implications**", "", result.strategic_implications, ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Key Assumptions renderer
# ---------------------------------------------------------------------------


@register_renderer("assumptions")
def render_assumptions(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "analytic_line") and result.analytic_line:
        lines += [f"**Analytic Line**: {result.analytic_line}", ""]

    if hasattr(result, "assumptions") and result.assumptions:
        for i, a in enumerate(result.assumptions, 1):
            headline = _first_sentence(a.assumption)
            lines.append(f"#### {i}. {headline}")
            lines.append("")
            lines.append(
                f"**Confidence**: {a.confidence} | **Impact if Wrong**: {a.impact_if_wrong}"
            )
            lines.append("")
            lines.append(f"**Basis**: {a.basis_for_confidence}")
            lines.append("")
            lines.append(f"**What Could Undermine**: {a.what_undermines}")
            lines.append("")

    if hasattr(result, "most_vulnerable") and result.most_vulnerable:
        lines.append("**Most Vulnerable Assumptions**")
        lines.append("")
        for v in result.most_vulnerable:
            lines.append(f"- {v}")
        lines.append("")

    if hasattr(result, "recommended_monitoring") and result.recommended_monitoring:
        lines.append("**Recommended Monitoring**")
        lines.append("")
        for m in result.recommended_monitoring:
            lines.append(f"- {m}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Quality of Information renderer
# ---------------------------------------------------------------------------


@register_renderer("quality")
def render_quality(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "sources") and result.sources:
        for s in result.sources:
            headline = _first_sentence(s.description)
            lines.append(f"#### {headline}")
            lines.append("")
            lines.append(f"**Type**: {s.source_type} | **Reliability**: {s.reliability}")
            lines.append("")
            lines.append(f"**Access**: {s.access_quality}")
            lines.append("")
            lines.append(f"**Corroboration**: {s.corroboration}")
            lines.append("")
            lines.append(f"**Gaps**: {s.gaps}")
            lines.append("")

    if hasattr(result, "overall_assessment") and result.overall_assessment:
        lines += ["**Overall Assessment**", "", result.overall_assessment, ""]

    if hasattr(result, "key_gaps") and result.key_gaps:
        lines.append("**Key Gaps**")
        lines.append("")
        for g in result.key_gaps:
            lines.append(f"- {g}")
        lines.append("")

    if hasattr(result, "deception_indicators") and result.deception_indicators:
        lines.append("**Deception Indicators**")
        lines.append("")
        for d in result.deception_indicators:
            lines.append(f"- {d}")
        lines.append("")

    if hasattr(result, "collection_requirements") and result.collection_requirements:
        lines.append("**Collection Requirements**")
        lines.append("")
        for c in result.collection_requirements:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Red Team renderer
# ---------------------------------------------------------------------------


@register_renderer("red_team")
def render_red_team(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "adversary_identity") and result.adversary_identity:
        lines += [f"**Adversary**: {result.adversary_identity}", ""]

    if hasattr(result, "adversary_context") and result.adversary_context:
        lines += [f"**Context**: {result.adversary_context}", ""]

    if hasattr(result, "perception_of_threats") and result.perception_of_threats:
        lines += [f"**Perceived Threats**: {result.perception_of_threats}", ""]

    if hasattr(result, "perception_of_opportunities") and result.perception_of_opportunities:
        lines += [f"**Perceived Opportunities**: {result.perception_of_opportunities}", ""]

    if hasattr(result, "first_person_memo") and result.first_person_memo:
        lines.append("**First-Person Memo**")
        lines.append("")
        for memo_line in result.first_person_memo.split("\n"):
            lines.append(f"> {memo_line}")
        lines.append("")

    if hasattr(result, "predicted_actions") and result.predicted_actions:
        lines.append("**Predicted Actions**")
        lines.append("")
        for a in result.predicted_actions:
            lines.append(f"- {a}")
        lines.append("")

    if hasattr(result, "key_motivations") and result.key_motivations:
        lines.append("**Key Motivations**")
        lines.append("")
        for m in result.key_motivations:
            lines.append(f"- {m}")
        lines.append("")

    if hasattr(result, "constraints_on_adversary") and result.constraints_on_adversary:
        lines.append("**Constraints**")
        lines.append("")
        for c in result.constraints_on_adversary:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Team A/B renderer
# ---------------------------------------------------------------------------


@register_renderer("team_ab")
def render_team_ab(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    for attr, label in [("team_a", "Team A"), ("team_b", "Team B")]:
        team = getattr(result, attr, None)
        if team:
            lines.append(f"**{label}: {team.hypothesis}**")
            lines.append("")
            if team.argument:
                lines += [team.argument, ""]
            if team.key_assumptions:
                lines.append(f"*{label} Assumptions*:")
                for a in team.key_assumptions:
                    lines.append(f"- {a}")
                lines.append("")
            if team.key_evidence:
                lines.append(f"*{label} Evidence*:")
                for e in team.key_evidence:
                    lines.append(f"- {e}")
                lines.append("")
            if team.acknowledged_weaknesses:
                lines.append(f"*{label} Acknowledged Weaknesses*:")
                for w in team.acknowledged_weaknesses:
                    lines.append(f"- {w}")
                lines.append("")

    if hasattr(result, "debate_points") and result.debate_points:
        lines += [
            "**Debate Points**",
            "",
            "| Topic | Team A | Team B | Resolution |",
            "|-------|--------|--------|------------|",
        ]
        for dp in result.debate_points:
            lines.append(
                f"| {_esc(dp.topic)} | {_esc(dp.team_a_position)} "
                f"| {_esc(dp.team_b_position)} | {_esc(dp.resolution)} |"
            )
        lines.append("")

    if hasattr(result, "jury_assessment") and result.jury_assessment:
        lines += ["**Jury Assessment**", "", result.jury_assessment, ""]

    if hasattr(result, "stronger_case") and result.stronger_case:
        lines.append(f"**Stronger Case**: Team {result.stronger_case}")
        lines.append("")

    if hasattr(result, "areas_of_agreement") and result.areas_of_agreement:
        lines.append("**Areas of Agreement**")
        lines.append("")
        for a in result.areas_of_agreement:
            lines.append(f"- {a}")
        lines.append("")

    if hasattr(result, "recommended_research") and result.recommended_research:
        lines.append("**Recommended Research**")
        lines.append("")
        for r in result.recommended_research:
            lines.append(f"- {r}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Devil's Advocacy renderer
# ---------------------------------------------------------------------------

_VERDICT_BADGES = {
    "Mainline Holds": "Mainline Holds \u2713",
    "Mainline Weakened": "Mainline Weakened \u26a0",
    "Mainline Overturned": "Mainline Overturned \u2717",
}


@register_renderer("devils_advocacy")
def render_devils_advocacy(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "mainline_judgment") and result.mainline_judgment:
        lines += ["**Mainline Judgment**", "", result.mainline_judgment, ""]

    if hasattr(result, "mainline_evidence") and result.mainline_evidence:
        lines.append("**Mainline Evidence**")
        lines.append("")
        for e in result.mainline_evidence:
            lines.append(f"- {e}")
        lines.append("")

    if hasattr(result, "challenged_assumptions") and result.challenged_assumptions:
        lines += ["**Challenged Assumptions**", ""]
        for ca in result.challenged_assumptions:
            headline = _first_sentence(ca.assumption)
            lines.append(f"#### {headline}")
            lines.append("")
            lines.append(f"**Vulnerability**: {ca.vulnerability}")
            lines.append("")
            lines.append(f"**Challenge**: {ca.challenge}")
            lines.append("")
            lines.append(f"**Evidence Against**: {ca.evidence_against}")
            lines.append("")

    if hasattr(result, "alternative_hypothesis") and result.alternative_hypothesis:
        lines += ["**Alternative Hypothesis**", "", result.alternative_hypothesis, ""]

    if (
        hasattr(result, "supporting_evidence_for_alternative")
        and result.supporting_evidence_for_alternative
    ):
        lines.append("**Supporting Evidence for Alternative**")
        lines.append("")
        for e in result.supporting_evidence_for_alternative:
            lines.append(f"- {e}")
        lines.append("")

    if hasattr(result, "quality_of_evidence_concerns") and result.quality_of_evidence_concerns:
        lines.append("**Evidence Quality Concerns**")
        lines.append("")
        for c in result.quality_of_evidence_concerns:
            lines.append(f"- {c}")
        lines.append("")

    if hasattr(result, "conclusion") and result.conclusion:
        badge = _VERDICT_BADGES.get(result.conclusion, result.conclusion)
        lines += [f"**Verdict: {badge}**", ""]

    if hasattr(result, "recommended_actions") and result.recommended_actions:
        lines.append("**Recommended Actions**")
        lines.append("")
        for a in result.recommended_actions:
            lines.append(f"- {a}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# High-Impact/Low-Probability renderer
# ---------------------------------------------------------------------------

_PLAUSIBILITY_BADGES = {
    "Possible": "\u26a0 Possible",
    "Plausible": "\u2714 Plausible",
    "Remote": "\u2b58 Remote",
}


@register_renderer("high_impact")
def render_high_impact(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "event_definition") and result.event_definition:
        lines += ["**Event Definition**", "", result.event_definition, ""]

    if hasattr(result, "why_considered_unlikely") and result.why_considered_unlikely:
        lines += ["**Why Considered Unlikely**", "", result.why_considered_unlikely, ""]

    if hasattr(result, "impact_assessment") and result.impact_assessment:
        lines += ["**Impact Assessment**", "", result.impact_assessment, ""]

    if hasattr(result, "pathways") and result.pathways:
        lines.append("**Pathways**")
        lines.append("")
        for p in result.pathways:
            badge = _PLAUSIBILITY_BADGES.get(p.plausibility, p.plausibility)
            lines.append(f"*{p.name}* [{badge}]")
            lines.append("")
            lines.append(p.description)
            lines.append("")
            if p.triggers:
                lines.append("Triggers:")
                for t in p.triggers:
                    lines.append(f"- {t}")
                lines.append("")
            if p.indicators:
                lines.append("Indicators:")
                for ind in p.indicators:
                    lines.append(f"- {ind}")
                lines.append("")

    if hasattr(result, "deflection_factors") and result.deflection_factors:
        lines.append("**Deflection Factors**")
        lines.append("")
        for d in result.deflection_factors:
            lines.append(f"- {d}")
        lines.append("")

    if hasattr(result, "policy_implications") and result.policy_implications:
        lines += ["**Policy Implications**", "", result.policy_implications, ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# What-If renderer
# ---------------------------------------------------------------------------


@register_renderer("what_if")
def render_what_if(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "assumed_event") and result.assumed_event:
        lines += ["**Assumed Event**", "", result.assumed_event, ""]

    if hasattr(result, "conventional_view") and result.conventional_view:
        lines += ["**Conventional View**", "", result.conventional_view, ""]

    if hasattr(result, "triggering_events") and result.triggering_events:
        lines.append("**Triggering Events**")
        lines.append("")
        for t in result.triggering_events:
            lines.append(f"- {t}")
        lines.append("")

    if hasattr(result, "chain_of_argumentation") and result.chain_of_argumentation:
        lines.append("**Chain of Argumentation**")
        lines.append("")
        for step in result.chain_of_argumentation:
            lines.append(f"{step.step_number}. {step.description}")
            if step.enabling_factors:
                for f in step.enabling_factors:
                    lines.append(f"   - {f}")
        lines.append("")

    if hasattr(result, "backward_reasoning") and result.backward_reasoning:
        lines += ["**Backward Reasoning**", "", result.backward_reasoning, ""]

    if hasattr(result, "alternative_pathways") and result.alternative_pathways:
        lines.append("**Alternative Pathways**")
        lines.append("")
        for p in result.alternative_pathways:
            lines.append(f"- {p}")
        lines.append("")

    if hasattr(result, "indicators") and result.indicators:
        lines.append("**Indicators**")
        lines.append("")
        for ind in result.indicators:
            lines.append(f"- {ind}")
        lines.append("")

    if hasattr(result, "consequences") and result.consequences:
        lines += ["**Consequences**", "", result.consequences, ""]

    if hasattr(result, "probability_reassessment") and result.probability_reassessment:
        lines += ["**Probability Reassessment**", "", result.probability_reassessment, ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Brainstorming renderer
# ---------------------------------------------------------------------------


@register_renderer("brainstorming")
def render_brainstorming(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "focal_question") and result.focal_question:
        lines += [f"**Focal Question**: {result.focal_question}", ""]

    if hasattr(result, "clusters") and result.clusters:
        for cluster in result.clusters:
            lines.append(f"**{cluster.name}**")
            lines.append("")
            if cluster.significance:
                lines.append(f"*{cluster.significance}*")
                lines.append("")
            for idea in cluster.ideas:
                lines.append(f"- **{idea.id}**: {idea.text}")
            lines.append("")
    elif hasattr(result, "divergent_ideas") and result.divergent_ideas:
        lines.append("**Ideas**")
        lines.append("")
        for idea in result.divergent_ideas:
            lines.append(f"- **{idea.id}**: {idea.text}")
        lines.append("")

    if hasattr(result, "priority_areas") and result.priority_areas:
        lines.append("**Priority Areas**")
        lines.append("")
        for p in result.priority_areas:
            lines.append(f"- {p}")
        lines.append("")

    if hasattr(result, "unconventional_insights") and result.unconventional_insights:
        lines.append("**Unconventional Insights**")
        lines.append("")
        for u in result.unconventional_insights:
            lines.append(f"- {u}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Outside-In (STEEP) renderer
# ---------------------------------------------------------------------------


@register_renderer("outside_in")
def render_outside_in(result: ArtifactResult) -> str:
    lines: list[str] = []
    if result.summary:
        lines += [result.summary, ""]

    if hasattr(result, "issue_description") and result.issue_description:
        lines += [f"**Issue**: {result.issue_description}", ""]

    if hasattr(result, "forces") and result.forces:
        lines += [
            "| Category | Force | Impact | Controllability |",
            "|----------|-------|--------|-----------------|",
        ]
        for f in result.forces:
            lines.append(
                f"| {f.category} | {_esc(f.force)} "
                f"| {_esc(f.impact_on_issue)} | {f.controllability} |"
            )
        lines.append("")

    if hasattr(result, "key_external_drivers") and result.key_external_drivers:
        lines.append("**Key External Drivers**")
        lines.append("")
        for d in result.key_external_drivers:
            lines.append(f"- {d}")
        lines.append("")

    if hasattr(result, "overlooked_factors") and result.overlooked_factors:
        lines.append("**Overlooked Factors**")
        lines.append("")
        for o in result.overlooked_factors:
            lines.append(f"- {o}")
        lines.append("")

    if hasattr(result, "implications") and result.implications:
        lines += ["**Implications**", "", result.implications, ""]

    return "\n".join(lines)
