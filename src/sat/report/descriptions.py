"""Technique descriptions for executive reports.

Brief explanations of each structured analytic technique, drawn from
CIA Tradecraft Primer concepts. Used in the Methodology and Technique
Details sections of the executive report.
"""

from __future__ import annotations

TECHNIQUE_DESCRIPTIONS: dict[str, str] = {
    "assumptions": (
        "Key Assumptions Check identifies and evaluates the foundational assumptions "
        "underlying an analytic line. By surfacing hidden premises and assessing their "
        "vulnerability, it reveals where the analysis is most at risk of being wrong."
    ),
    "quality": (
        "Quality of Information Check evaluates the reliability, access, and "
        "corroboration of intelligence sources. It identifies gaps in the evidence "
        "base and flags potential deception indicators that could undermine confidence."
    ),
    "indicators": (
        "Indicators and Signposts of Change tracks observable events and metrics "
        "that signal whether a situation is evolving toward or away from a particular "
        "outcome. It enables early warning and systematic monitoring."
    ),
    "ach": (
        "Analysis of Competing Hypotheses (ACH) combats confirmation bias by "
        "systematically evaluating all evidence against every plausible hypothesis. "
        "It identifies which hypotheses are most inconsistent with the evidence, "
        "rather than seeking to confirm a favored explanation."
    ),
    "devils_advocacy": (
        "Devil's Advocacy systematically challenges a dominant analytic judgment "
        "by building the strongest possible case for an alternative explanation. "
        "It tests whether the prevailing view can withstand rigorous scrutiny."
    ),
    "team_ab": (
        "Team A/Team B structures a formal debate between two groups defending "
        "competing hypotheses. An independent jury evaluates which team presents "
        "the stronger case, surfacing the strongest arguments for each position."
    ),
    "red_team": (
        "Red Team Analysis adopts an adversary's perspective through deep role-play, "
        "producing a first-person strategic memo from the adversary's viewpoint. "
        "It reveals motivations, constraints, and likely actions that distance-based "
        "analysis often misses."
    ),
    "alt_futures": (
        "Alternative Futures Analysis uses a 2x2 matrix of key uncertainties to "
        "generate four distinct plausible scenarios. Each scenario includes indicators "
        "for monitoring which future is emerging, supporting strategic hedging."
    ),
    "high_impact": (
        "High-Impact/Low-Probability Analysis explores unlikely but consequential "
        "events by developing multiple plausible pathways by which they could occur. "
        "It identifies triggers and observable indicators for early warning."
    ),
    "what_if": (
        "What If? Analysis assumes a specific event has occurred and reasons backward "
        "to construct how it could have come about. By shifting from 'whether' to 'how', "
        "it often reveals that supposedly unlikely events have plausible pathways."
    ),
    "brainstorming": (
        "Structured Brainstorming generates a broad range of ideas through divergent "
        "thinking, then clusters them into themes. It surfaces unconventional insights "
        "and creative possibilities that structured analysis might overlook."
    ),
    "outside_in": (
        "Outside-In Thinking (STEEP Analysis) examines how external forces across "
        "Social, Technological, Economic, Environmental, and Political dimensions "
        "affect the issue. It prevents tunnel vision by forcing attention to the "
        "broader context."
    ),
}

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "diagnostic": (
        "Diagnostic techniques structure the evaluation of evidence and assumptions. "
        "They make analytic reasoning transparent and testable, helping analysts "
        "avoid common cognitive pitfalls like confirmation bias and anchoring."
    ),
    "contrarian": (
        "Contrarian techniques deliberately challenge established analytic lines. "
        "They force consideration of alternative explanations and stress-test the "
        "dominant view, guarding against groupthink and premature closure."
    ),
    "imaginative": (
        "Imaginative techniques explore what could happen rather than what has "
        "happened. They generate alternative scenarios, identify early warning "
        "indicators, and expand the range of possibilities under consideration."
    ),
}
