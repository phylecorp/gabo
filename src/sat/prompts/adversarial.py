"""Prompts for adversarial critique, rebuttal, adjudication, and convergence.

@decision DEC-PROMPT-ADV-001: Structured debate prompts with role framing.
@title Critique/rebuttal/adjudication prompt templates
@status accepted
@rationale Each prompt frames the model in a specific role: rigorous peer reviewer,
defending analyst, or impartial judge. Template substitution for technique_id and
technique_name keeps artifacts traceable. Prompts reference the technique output
and original context to ground the debate in evidence.

@decision DEC-PROMPT-ADV-002: ACH-specific formatting and critique guidance.
@title Render ACH results as markdown tables in adversarial prompts
@status accepted
@rationale JSON dumps of ACHResult are hard for LLMs to reason over because the
matrix is a flat list of rating objects. Rendering the primary technique result as
markdown tables (hypotheses, evidence, diagnosticity matrix) makes cell-level
references natural in the critique. Only the primary ACHResult is rendered as
tables; critique/rebuttal/adjudication results remain JSON since they are not ACH
matrix artifacts. ACH-specific instructions are appended to the critique system
prompt to direct the reviewer toward matrix-level analysis.

@decision DEC-PROMPT-ADV-003: Convergence prompt compares primary+investigator+challenger.
@title Three-perspective convergence analysis prompt
@status accepted
@rationale When two independent analysts reach the same conclusion by different
reasoning paths, that is the strongest confidence signal in intelligence analysis.
The convergence prompt receives all three perspectives and identifies agreement,
disagreement, novel insights, and analytical blindspots. The enhanced adjudication
prompt also receives these when available to produce a richer final judgment.
"""

from __future__ import annotations

from sat.models.ach import ACHResult
from sat.models.base import ArtifactResult
from sat.providers.base import LLMMessage


# ACH-specific guidance appended to the critique system prompt
_ACH_CRITIQUE_GUIDANCE = """

## ACH-Specific Review Guidance

When reviewing an Analysis of Competing Hypotheses result:
- Reference specific matrix cells (e.g., "E3 is rated C for H2 but should be I because...")
- Challenge whether the hypothesis set is exhaustive — are there plausible explanations the analyst omitted?
- Evaluate whether evidence credibility ratings are appropriate given the source and context"""


def _format_for_critique(result: ArtifactResult) -> str:
    """Format a technique result for embedding in adversarial prompts.

    For ACHResult: renders hypotheses and diagnosticity matrix as markdown tables,
    making cell-level references natural for the critique model.
    For all other types: returns the JSON dump used by the generic prompt builders.
    """
    if isinstance(result, ACHResult):
        from sat.artifacts import _render_ach_markdown

        return _render_ach_markdown(result)
    return result.model_dump_json(indent=2)


CRITIQUE_SYSTEM_PROMPT = """You are a rigorous peer reviewer of intelligence analysis.

You have been given the output of a structured analytic technique applied to a question. \
Your task is to critically evaluate the analysis with the goal of strengthening it.

## Your Approach

1. **Identify Agreements**: What did the analyst get right? What conclusions are well-supported?
2. **Challenge Weaknesses**: Where is the reasoning weak, evidence insufficient, or conclusions \
premature?
3. **Offer Alternatives**: What alternative interpretations of the evidence exist?
4. **Find Gaps**: What evidence was overlooked or unavailable?
5. **Assess Severity**: How significant are your challenges? Could they change the conclusions?

## Rules
- Be specific — reference particular claims, evidence, or reasoning steps
- Be constructive — the goal is better analysis, not scoring points
- Distinguish between methodological issues and substantive disagreements
- Consider cognitive biases the analyst may have fallen into
- Don't manufacture disagreement where the analysis is sound

## Output Fields
- technique_id: Use "{technique_id}-critique" format
- technique_name: "Critique of {technique_name}"
- summary: Brief overview of your critique
- agreements: Points where you agree with the analysis
- challenges: Specific challenges (each with claim, challenge, evidence, severity)
- alternative_interpretations: Different ways to read the evidence
- evidence_gaps: Missing evidence the analysis didn't address
- severity: Overall severity ("Major", "Moderate", "Minor")
- overall_assessment: Your overall evaluation
- revised_confidence: Should confidence go "Higher", stay "Same", go "Lower", or "Much Lower"?"""


REBUTTAL_SYSTEM_PROMPT = """You are an intelligence analyst defending your work while \
remaining intellectually honest.

You've received a critique of your analysis. You must respond to each challenge:

1. **Accept Valid Points**: If a challenge is valid, acknowledge it and explain how it changes \
your conclusions
2. **Rebut Invalid Points**: If a challenge is mistaken, explain why with specific evidence
3. **Revise Conclusions**: Produce updated conclusions incorporating any accepted challenges

## Rules
- Be honest — concede points that have merit
- Be specific — reference the evidence that supports your position
- Don't be defensive for its own sake — the goal is accurate analysis
- Distinguish between challenges that affect conclusions and those that don't

## Output Fields
- technique_id: Use "{technique_id}-rebuttal" format
- technique_name: "Rebuttal for {technique_name}"
- summary: Brief summary of your response
- accepted_challenges: Challenges you accept as valid
- rejected_challenges: Challenges you reject, each with reasoning and whether you concede
- revised_conclusions: Updated conclusions incorporating accepted challenges"""


ADJUDICATION_SYSTEM_PROMPT = """You are an impartial judge evaluating a debate between two \
intelligence analysts.

You've seen the original analysis, a critique, and a rebuttal. Your task is to render a \
fair judgment.

1. **Resolve Each Dispute**: For each contested point, determine which side has the stronger \
argument
2. **Identify the Unresolvable**: Some disagreements reflect genuine uncertainty — flag these
3. **Synthesize**: Produce an integrated assessment capturing the strongest elements of both

## Rules
- Base judgments on evidence quality and reasoning strength, not authority
- Genuine uncertainty is a valid conclusion — don't force resolution
- Consider whether the debate revealed new insights neither side initially had
- Be specific about which points you resolve and why

## Output Fields
- technique_id: Use "{technique_id}-adjudication" format
- technique_name: "Adjudication for {technique_name}"
- summary: Brief overview of your adjudication
- resolved_for_primary: Points where the primary analyst's position is stronger
- resolved_for_challenger: Points where the challenger's position is stronger
- unresolved: Points that remain genuinely uncertain
- synthesis_assessment: Integrated assessment combining the strongest elements"""


CONVERGENCE_SYSTEM_PROMPT = """You are an analytical methodologist performing convergence analysis.

You have been given three independent perspectives on the same analytic question:
1. **Primary Analysis**: The initial structured technique output
2. **Investigator Analysis**: An independent re-analysis using the same technique by a different provider
3. **Challenger Critique**: A critical review of the primary analysis (with rebuttal)

Your task is to identify where these independent assessments converge and diverge.

## Why This Matters
When two analysts independently reach the same conclusion through different reasoning paths, \
that's the strongest confidence signal in intelligence analysis. Conversely, genuine disagreements \
between independent analysts reveal real analytical uncertainty.

## Your Analysis
1. **Convergence Points**: Where do primary and investigator agree?
2. **Divergence Points**: Where do they disagree?
3. **Novel Insights**: What did the investigator find that the primary missed?
4. **Analytical Blindspots**: What biases/gaps does comparison reveal?
5. **Confidence Delta**: How should overall confidence change?

## Output Fields
- technique_id: "{technique_id}-convergence"
- technique_name: "Convergence Analysis for {technique_name}"
- summary: Brief overview of convergence findings
- convergence_points: Points where providers agree (each with claim, agreeing_providers, confidence_boost, reasoning)
- divergence_points: Points of disagreement (each with claim, primary_position, investigator_position, challenger_position, significance, likely_cause)
- novel_insights: Insights only the investigator found
- confidence_delta: How convergence analysis changes overall confidence
- analytical_blindspots_identified: Biases or gaps revealed by comparison"""


def build_critique_prompt(
    technique_result: ArtifactResult,
    question: str,
    evidence: str | None = None,
) -> tuple[str, list[LLMMessage]]:
    """Build the critique prompt for the challenger."""
    content = f"## Original Question\n\n{question}\n\n"
    if evidence:
        content += f"## Evidence\n\n{evidence}\n\n"
    content += "## Analysis to Critique\n\n"
    content += (
        f"**Technique:** {technique_result.technique_name} ({technique_result.technique_id})\n\n"
    )
    formatted = _format_for_critique(technique_result)
    if isinstance(technique_result, ACHResult):
        content += f"**Output:**\n\n{formatted}"
    else:
        content += f"**Output:**\n```json\n{formatted}\n```"

    system = CRITIQUE_SYSTEM_PROMPT.replace(
        "{technique_id}", technique_result.technique_id
    ).replace("{technique_name}", technique_result.technique_name)

    # Add ACH-specific critique guidance when reviewing an ACH result
    if isinstance(technique_result, ACHResult):
        system += _ACH_CRITIQUE_GUIDANCE

    return system, [LLMMessage(role="user", content=content)]


def build_rebuttal_prompt(
    technique_result: ArtifactResult,
    critique: ArtifactResult,
    question: str,
    evidence: str | None = None,
) -> tuple[str, list[LLMMessage]]:
    """Build the rebuttal prompt for the primary."""
    content = f"## Original Question\n\n{question}\n\n"
    if evidence:
        content += f"## Evidence\n\n{evidence}\n\n"
    formatted = _format_for_critique(technique_result)
    if isinstance(technique_result, ACHResult):
        content += f"## Your Original Analysis\n\n{formatted}\n\n"
    else:
        content += f"## Your Original Analysis\n\n```json\n{formatted}\n```\n\n"
    content += f"## Critique Received\n\n```json\n{critique.model_dump_json(indent=2)}\n```"

    system = REBUTTAL_SYSTEM_PROMPT.replace(
        "{technique_id}", technique_result.technique_id
    ).replace("{technique_name}", technique_result.technique_name)

    return system, [LLMMessage(role="user", content=content)]


def build_adjudication_prompt(
    technique_result: ArtifactResult,
    critique: ArtifactResult,
    rebuttal: ArtifactResult,
    question: str,
    evidence: str | None = None,
    investigator_result: ArtifactResult | None = None,
    convergence: ArtifactResult | None = None,
) -> tuple[str, list[LLMMessage]]:
    """Build the adjudication prompt for the judge.

    When investigator_result and convergence are provided (trident mode), they
    are appended to the user message and the system prompt is extended to instruct
    the adjudicator to incorporate convergence findings.
    """
    content = f"## Original Question\n\n{question}\n\n"
    if evidence:
        content += f"## Evidence\n\n{evidence}\n\n"
    formatted = _format_for_critique(technique_result)
    if isinstance(technique_result, ACHResult):
        content += f"## Primary Analysis\n\n{formatted}\n\n"
    else:
        content += f"## Primary Analysis\n\n```json\n{formatted}\n```\n\n"
    content += f"## Critique\n\n```json\n{critique.model_dump_json(indent=2)}\n```\n\n"
    content += f"## Rebuttal\n\n```json\n{rebuttal.model_dump_json(indent=2)}\n```"

    if investigator_result is not None:
        content += (
            f"\n\n## Independent Investigator Analysis\n\n"
            f"```json\n{investigator_result.model_dump_json(indent=2)}\n```"
        )
    if convergence is not None:
        content += (
            f"\n\n## Convergence Analysis\n\n"
            f"```json\n{convergence.model_dump_json(indent=2)}\n```"
        )

    system = ADJUDICATION_SYSTEM_PROMPT.replace(
        "{technique_id}", technique_result.technique_id
    ).replace("{technique_name}", technique_result.technique_name)

    if investigator_result is not None or convergence is not None:
        system += """

## Trident Mode — Convergence Integration

You also have an independent investigator's re-analysis and a convergence analysis comparing \
all perspectives. Use these when resolving disputes:
- Points where primary and investigator BOTH agree carry higher evidential weight
- Points where they diverge represent genuine analytical uncertainty — flag these in unresolved
- Novel insights from the investigator that the primary missed should be reflected in your synthesis"""

    return system, [LLMMessage(role="user", content=content)]


def build_convergence_prompt(
    technique_result: ArtifactResult,
    investigator_result: ArtifactResult,
    critique: ArtifactResult,
    rebuttal: ArtifactResult,
    question: str,
    evidence: str | None = None,
) -> tuple[str, list[LLMMessage]]:
    """Build the convergence analysis prompt.

    Compares primary, investigator, and challenger perspectives to identify
    convergence points, divergence points, novel insights, and analytical blindspots.
    """
    content = f"## Original Question\n\n{question}\n\n"
    if evidence:
        content += f"## Evidence\n\n{evidence}\n\n"

    formatted = _format_for_critique(technique_result)
    if isinstance(technique_result, ACHResult):
        content += f"## 1. Primary Analysis\n\n{formatted}\n\n"
    else:
        content += f"## 1. Primary Analysis\n\n```json\n{formatted}\n```\n\n"

    formatted_inv = _format_for_critique(investigator_result)
    if isinstance(investigator_result, ACHResult):
        content += f"## 2. Investigator Analysis (Independent)\n\n{formatted_inv}\n\n"
    else:
        content += (
            f"## 2. Investigator Analysis (Independent)\n\n"
            f"```json\n{formatted_inv}\n```\n\n"
        )

    content += (
        f"## 3. Challenger Critique\n\n"
        f"```json\n{critique.model_dump_json(indent=2)}\n```\n\n"
    )
    content += (
        f"## 4. Primary Rebuttal\n\n"
        f"```json\n{rebuttal.model_dump_json(indent=2)}\n```"
    )

    system = CONVERGENCE_SYSTEM_PROMPT.replace(
        "{technique_id}", technique_result.technique_id
    ).replace("{technique_name}", technique_result.technique_name)

    return system, [LLMMessage(role="user", content=content)]
