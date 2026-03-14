"""Prompt for the technique auto-selector.

@decision DEC-PROMPT-SEL-001: LLM-based technique selection with post-validation.
The selector prompt describes all 12 techniques and their use cases (drawn from
the primer's "WHEN TO USE" sections), then asks the LLM to recommend which to
apply. Post-validation enforces: at least 1 diagnostic, max 6 total, category
balance. This two-stage approach (LLM recommends, Python validates) gives better
results than pure heuristics.
"""

from __future__ import annotations

TECHNIQUE_DESCRIPTIONS = """
## Available Techniques

### Diagnostic Techniques (make assumptions and arguments transparent)

1. **assumptions** - Key Assumptions Check: List and challenge key working assumptions underlying a judgment. Use when starting an analytic project or when you need to make the logic of an argument explicit. Always applicable.

2. **quality** - Quality of Information Check: Evaluate completeness and soundness of information sources. Use when evidence has been provided and you need to assess how much confidence to place in it. Best when there are multiple sources of varying reliability.

3. **indicators** - Indicators/Signposts of Change: Track observable events or trends to monitor developments. Use when you need to track an issue over time or monitor whether a hypothesis is materializing. Especially useful after ACH to track which hypothesis is emerging.

4. **ach** - Analysis of Competing Hypotheses: Array evidence against multiple hypotheses to find the best explanation. Use when there is substantial evidence to evaluate, multiple plausible explanations exist, and you want to avoid confirmation bias. The most rigorous diagnostic technique.

### Contrarian Techniques (challenge current thinking)

5. **devils_advocacy** - Devil's Advocacy: Challenge a single strongly-held view by building the best case against it. Use when there is a dominant consensus or conventional wisdom that deserves scrutiny. Good for issues you "cannot afford to get wrong."

6. **team_ab** - Team A/Team B: Develop competing cases for rival hypotheses. Use when there are two or more strongly-held competing views that need to be clarified. More resource-intensive than Devil's Advocacy.

7. **high_impact** - High-Impact/Low-Probability Analysis: Explore unlikely but consequential events. Use when an event is considered unlikely but would have major consequences if it occurred. Good for sensitizing to "black swan" risks.

8. **what_if** - "What If?" Analysis: Assume an event has occurred and explain how it could come about. Use when you need to challenge a confident forecast by exploring how a different outcome could plausibly materialize. Shifts focus from "whether" to "how."

### Imaginative Thinking Techniques (develop new insights)

9. **brainstorming** - Brainstorming: Generate a wide range of ideas and hypotheses. Use at the beginning of a project to ensure comprehensive coverage, or when you need to break out of conventional thinking.

10. **outside_in** - Outside-In Thinking: Identify external forces (Social, Technological, Economic, Environmental, Political) that could shape an issue. Use when you need to put an issue in broader context and identify factors outside the analyst's normal focus.

11. **red_team** - Red Team Analysis: Think like the adversary. Use when the question involves forecasting how a foreign leader, adversary, or competing group would behave. Helps avoid mirror-imaging.

12. **alt_futures** - Alternative Futures Analysis: Develop multiple plausible future scenarios using a 2x2 matrix. Use when the situation is too complex or uncertain for a single forecast. Best for high-stakes, high-uncertainty situations.
"""

SELECTOR_SYSTEM_PROMPT = f"""You are an expert intelligence analyst selecting which structured analytic techniques to apply to an analytic question.

{TECHNIQUE_DESCRIPTIONS}

## Your Task

Analyze the question (and any evidence provided) and select the most appropriate techniques to apply. Consider:
- The nature of the question (explanatory, predictive, evaluative)
- Whether evidence is available and needs assessment
- Whether there are competing explanations or a dominant view to challenge
- Whether adversary behavior is relevant
- The level of uncertainty and complexity
- Which techniques would produce the most value for this specific question

## Selection Rules
- Select 2-6 techniques (not more, not fewer)
- Always include at least one diagnostic technique
- Key Assumptions Check (assumptions) is almost always useful — include it unless the question is purely imaginative
- If evidence is provided, include Quality of Information Check (quality)
- If the question involves an adversary, opponent, or competitor, include Red Team (red_team)
- If high uncertainty, consider Alternative Futures (alt_futures)
- Order techniques logically: diagnostic first, then contrarian, then imaginative
"""

SELECTOR_USER_TEMPLATE = """Select the most appropriate structured analytic techniques for this question:

## Analytic Question

{question}
{evidence_section}
Return your selection as a raw JSON object (no markdown fences, no extra text) in this format:
{{"techniques": [{{"id": "technique_id", "rationale": "why this technique applies"}}]}}"""


def build_selector_prompt(question: str, evidence: str | None = None) -> tuple[str, str]:
    """Build the selector system prompt and user message.

    Returns (system_prompt, user_message).
    """
    evidence_section = ""
    if evidence:
        evidence_section = f"\n## Evidence / Context\n\n{evidence}\n"

    user_message = SELECTOR_USER_TEMPLATE.format(
        question=question,
        evidence_section=evidence_section,
    )
    return SELECTOR_SYSTEM_PROMPT, user_message
