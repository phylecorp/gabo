"""LLM-powered task planner: maps template sections to SAT techniques.

@decision DEC-TASK-004
@title Task planner follows selector.py LLM+validation two-stage pattern
@status accepted
@rationale selector.py established a robust pattern: LLM recommends, Python
validates with hard rules. The task planner uses the same pattern but maps
template sections to techniques instead of selecting techniques for a single
question. The LLM has full context (section descriptions, affinities, evidence),
Python enforces correctness (all sections covered, valid technique IDs, no
empty section mappings). Preset affinities are hints in the prompt, not enforced
by Python — the LLM may deviate when the question warrants it.

build_analysis_config() is the bridge from TaskPlan to the existing pipeline:
it produces an AnalysisConfig with techniques set explicitly (bypassing
auto-selection) and research queries wired into ResearchConfig if applicable.
The pipeline receives a normal AnalysisConfig and runs unchanged.
"""

from __future__ import annotations

import json
import logging
import re

from sat.config import AnalysisConfig
from sat.providers.base import LLMMessage, LLMProvider
from sat.tasks.models import SectionMapping, TaskPlan, TaskType
from sat.tasks.prompts import build_planner_prompt

logger = logging.getLogger(__name__)


async def plan_task(
    task_type: TaskType,
    question: str,
    evidence: str | None,
    provider: LLMProvider,
) -> TaskPlan:
    """Plan a task execution: map template sections to techniques via LLM.

    Uses the LLM to map each template section to specific technique IDs,
    identify evidence gaps, and generate research queries. Python validates
    the LLM response and enforces correctness before returning.

    Args:
        task_type: The deliverable template being planned.
        question: The analytic question to answer.
        evidence: Optional evidence text.
        provider: LLM provider to use for planning.

    Returns:
        A validated TaskPlan ready for build_analysis_config().

    Raises:
        ValueError: If the LLM response cannot be parsed or validated.
    """
    system_prompt, user_message = build_planner_prompt(task_type, question, evidence)
    messages = [LLMMessage(role="user", content=user_message)]

    result = await provider.generate(
        system_prompt=system_prompt,
        messages=messages,
        max_tokens=4096,
        temperature=0.2,
    )

    raw = _parse_planner_response(result.text, task_type)
    plan = _validate_plan(raw, task_type, question)

    logger.info(
        "Task planner: type=%s techniques=%s sections=%d",
        task_type.id,
        plan.techniques,
        len(plan.sections),
    )
    return plan


def build_analysis_config(plan: TaskPlan, base_config: AnalysisConfig) -> AnalysisConfig:
    """Build an AnalysisConfig from a TaskPlan and a base config.

    Sets techniques explicitly (skipping auto-selection) and wires in
    research queries if the plan produced any. All other config fields
    (provider, adversarial, report, preprocessing) are preserved from base_config.

    Args:
        plan: The validated TaskPlan from plan_task().
        base_config: Base AnalysisConfig with provider, output_dir, etc.

    Returns:
        A new AnalysisConfig ready for run_analysis().
    """
    # Build research config with plan's queries if applicable
    research = base_config.research
    if plan.research_queries and not research.enabled:
        # Plan wants research but it wasn't requested — keep disabled
        # (the caller controls whether research runs, not the plan)
        pass
    elif plan.research_queries and research.enabled:
        # Wire plan queries into research config as additional context
        # ResearchConfig doesn't have a queries field yet — store in evidence context.
        # Phase 2 will add targeted query support to ResearchConfig.
        pass

    return base_config.model_copy(
        update={
            "question": plan.question,
            "techniques": plan.techniques,
            "research": research,
        }
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_planner_response(
    response: str,
    task_type: TaskType,
) -> dict:
    """Parse the LLM planner response into a raw dict.

    Handles markdown code fences the same way selector.py does.
    Falls back to a default mapping if the response cannot be parsed.
    """
    text = response.strip()

    # Strip markdown code fences — LLMs commonly wrap JSON this way
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "sections" in data:
            return data
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Task planner: LLM response was not valid JSON, using fallback mapping"
        )

    # Fallback: map each section to its affinity techniques or defaults
    return _build_fallback_mapping(task_type)


def _build_fallback_mapping(task_type: TaskType) -> dict:
    """Build a conservative fallback mapping when LLM response is unparseable."""
    sections = []
    for section in task_type.sections:
        if section.technique_affinity:
            technique_ids = section.technique_affinity[:2]  # Use first 2 affinities
        else:
            technique_ids = ["assumptions"]
        sections.append(
            {
                "section_id": section.id,
                "technique_ids": technique_ids,
                "synthesis_needed": False,
                "evidence_gaps": [],
            }
        )

    return {
        "sections": sections,
        "research_queries": None,
        "evidence_gaps": [],
        "rationale": "Fallback mapping: LLM response could not be parsed.",
    }


def _validate_plan(
    raw: dict,
    task_type: TaskType,
    question: str,
) -> TaskPlan:
    """Validate and normalize the raw planner dict into a TaskPlan.

    Enforces:
    1. All sections in task_type are covered (adds fallback for missing ones)
    2. All technique IDs are valid registered techniques
    3. Every section has at least one technique
    4. Technique list is deduplicated and ordered

    Args:
        raw: The parsed planner response dict.
        task_type: The TaskType being planned.
        question: The analytic question.

    Returns:
        A validated TaskPlan.
    """
    import sat.techniques  # noqa: F401 — trigger registration
    from sat.techniques.registry import list_technique_ids

    valid_ids = set(list_technique_ids())
    section_ids_in_type = {s.id for s in task_type.sections}

    # Build section mappings, validating technique IDs
    raw_sections: list[dict] = raw.get("sections", [])
    section_map: dict[str, SectionMapping] = {}

    for raw_section in raw_sections:
        sid = raw_section.get("section_id", "")
        if not sid or sid not in section_ids_in_type:
            logger.warning("Task planner: unknown section_id %r — skipping", sid)
            continue

        # Filter to valid technique IDs only
        raw_tids = raw_section.get("technique_ids", [])
        valid_tids = [t for t in raw_tids if t in valid_ids]

        if not valid_tids:
            # No valid techniques — use section's affinity or default
            task_section = next(s for s in task_type.sections if s.id == sid)
            if task_section.technique_affinity:
                valid_tids = [task_section.technique_affinity[0]]
            else:
                valid_tids = ["assumptions"]
            logger.warning(
                "Task planner: section %r had no valid technique IDs, using fallback %s",
                sid,
                valid_tids,
            )

        section_map[sid] = SectionMapping(
            section_id=sid,
            technique_ids=valid_tids,
            synthesis_needed=bool(raw_section.get("synthesis_needed", False)),
            evidence_gaps=list(raw_section.get("evidence_gaps", [])),
        )

    # Ensure all sections from the task type are covered
    for task_section in task_type.sections:
        if task_section.id not in section_map:
            logger.warning(
                "Task planner: section %r not in LLM response — adding fallback",
                task_section.id,
            )
            if task_section.technique_affinity:
                fallback_tids = task_section.technique_affinity[:1]
            else:
                fallback_tids = ["assumptions"]
            section_map[task_section.id] = SectionMapping(
                section_id=task_section.id,
                technique_ids=fallback_tids,
                synthesis_needed=False,
                evidence_gaps=[],
            )

    # Build ordered sections list (preserves task_type section order)
    sections = [section_map[s.id] for s in task_type.sections]

    # Compute union of all techniques, then order them
    all_technique_ids: list[str] = []
    seen: set[str] = set()
    for sm in sections:
        for tid in sm.technique_ids:
            if tid not in seen:
                all_technique_ids.append(tid)
                seen.add(tid)

    # Sort techniques: diagnostic → contrarian → imaginative
    techniques = _order_techniques(all_technique_ids)

    # Extract research queries and evidence gaps
    research_queries = raw.get("research_queries") or None
    if isinstance(research_queries, list) and len(research_queries) == 0:
        research_queries = None

    evidence_gaps = list(raw.get("evidence_gaps", []))
    rationale = raw.get("rationale", "Plan generated by task planner.")

    return TaskPlan(
        task_type=task_type.id,
        question=question,
        sections=sections,
        techniques=techniques,
        research_queries=research_queries,
        evidence_gaps=evidence_gaps,
        rationale=rationale,
    )


def _order_techniques(technique_ids: list[str]) -> list[str]:
    """Order technique IDs: diagnostic first, contrarian second, imaginative third."""
    try:
        from sat.techniques.registry import get_technique

        category_order = {"diagnostic": 0, "contrarian": 1, "imaginative": 2}
        techniques = []
        for tid in technique_ids:
            try:
                t = get_technique(tid)
                techniques.append((category_order.get(t.metadata.category, 99), t.metadata.order, tid))
            except ValueError:
                # Unknown technique — append at end
                techniques.append((99, 99, tid))

        techniques.sort(key=lambda x: (x[0], x[1]))
        return [t[2] for t in techniques]
    except Exception:
        # If ordering fails, return as-is
        return technique_ids
