"""Prompt builder for the task planner LLM call.

@decision DEC-TASK-003
@title Planner prompt reuses TECHNIQUE_DESCRIPTIONS from selector prompt
@status accepted
@rationale TECHNIQUE_DESCRIPTIONS in src/sat/prompts/selector.py is the single
authoritative description of all 12 techniques. Reusing it in the task planner
ensures consistency — if a technique description changes, both the selector and
the planner see the update. The planner prompt adds template-specific context
(section descriptions, affinity hints) on top of the shared technique catalog.
This follows the same LLM+validation two-stage pattern as selector.py:
LLM maps sections to techniques, Python validates the result.
"""

from __future__ import annotations

from sat.prompts.selector import TECHNIQUE_DESCRIPTIONS
from sat.tasks.models import TaskType

PLANNER_SYSTEM_PROMPT = f"""You are an expert intelligence analyst planning how to produce a structured intelligence deliverable.

You will be given:
1. A deliverable template with sections, each describing what analytical content it needs
2. The available structured analytic techniques (SATs) and what each does
3. An analytic question and optionally some evidence

Your task is to map each template section to the specific techniques that should fill it.

{TECHNIQUE_DESCRIPTIONS}

## Planning Rules

- Every section must be mapped to at least one technique
- Use technique_affinity hints as starting points, but adjust based on the specific question
- A section may need multiple techniques if it requires composite analysis
- Mark synthesis_needed=true when a section draws from 3+ techniques or needs integrated prose
- Identify specific evidence gaps for each section that would improve the analysis
- Generate research queries only for sections marked requires_research=true, or for critical gaps
- The techniques list should be the deduplicated union of all section technique_ids
- Order techniques: diagnostic first (assumptions, quality, indicators, ach), then contrarian, then imaginative
- Keep the total technique count between 2 and 8 — be selective
- Provide a concise rationale explaining the overall plan

## Output Format

Return a raw JSON object (no markdown fences, no extra text) in exactly this format:
{{
  "sections": [
    {{
      "section_id": "the_section_id",
      "technique_ids": ["technique_id_1", "technique_id_2"],
      "synthesis_needed": false,
      "evidence_gaps": ["specific gap 1", "specific gap 2"]
    }}
  ],
  "research_queries": ["query 1", "query 2"],
  "evidence_gaps": ["overall gap 1", "overall gap 2"],
  "rationale": "Why this plan was chosen"
}}

research_queries should be null if no research is needed.
evidence_gaps at the top level are the most important gaps across all sections.
"""


def build_planner_prompt(
    task_type: TaskType,
    question: str,
    evidence: str | None = None,
) -> tuple[str, str]:
    """Build the system prompt and user message for the task planner LLM call.

    Args:
        task_type: The TaskType being planned for.
        question: The analytic question.
        evidence: Optional evidence text to consider.

    Returns:
        (system_prompt, user_message) tuple.
    """
    # Build section descriptions with affinity hints
    sections_text = _format_sections(task_type)

    evidence_section = ""
    if evidence:
        evidence_section = f"\n## Available Evidence\n\n{evidence}\n"

    user_message = f"""Plan the analysis for this {task_type.name} deliverable.

## Analytic Question

{question}
{evidence_section}
## Template: {task_type.name}

{task_type.description}

## Sections to Fill

{sections_text}

Map each section to the techniques that should fill it. Follow the planning rules in the system prompt.
Return raw JSON only — no markdown, no extra text."""

    return PLANNER_SYSTEM_PROMPT, user_message


def _format_sections(task_type: TaskType) -> str:
    """Format task type sections for inclusion in the planner prompt."""
    lines = []
    for i, section in enumerate(task_type.sections, 1):
        lines.append(f"### Section {i}: {section.name} (id: {section.id})")
        lines.append(f"**Description:** {section.description}")
        lines.append(f"**Required analysis:** {', '.join(section.required_analysis)}")

        if section.technique_affinity:
            affinities = ", ".join(section.technique_affinity)
            lines.append(f"**Technique affinity hints:** {affinities} (hints only — adjust as needed)")
        else:
            lines.append("**Technique affinity hints:** none — use your judgment")

        if section.requires_research:
            lines.append("**Requires research:** yes")

        if section.evidence_requirements:
            lines.append(f"**Evidence needed:** {section.evidence_requirements}")

        lines.append("")

    return "\n".join(lines)
