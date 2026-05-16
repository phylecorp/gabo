"""Task mode — template-driven analysis for SAT.

@decision DEC-TASK-001
@title Task mode is a wrapper: computes AnalysisConfig, delegates to existing pipeline
@status accepted
@rationale SAT's pipeline already handles technique execution, research, reporting,
and adversarial critique. Task mode inverts the flow: start from a deliverable
template, decompose it into analytical requirements, and compute an AnalysisConfig
that drives the existing run_analysis() unchanged. The tasks package is a pure
orchestration layer — it never modifies pipeline internals. This preserves the
existing pipeline's correctness while adding structured deliverable templates on top.

Architecture:
    TaskType (preset or custom)
        ↓
    plan_task() — LLM maps sections → techniques + evidence gaps
        ↓
    TaskPlan
        ↓
    build_analysis_config() — wraps plan in AnalysisConfig
        ↓
    run_analysis()  ← existing pipeline, unchanged
"""

from __future__ import annotations

from sat.tasks.models import SectionMapping, TaskPlan, TaskSection, TaskType
from sat.tasks.planner import build_analysis_config, plan_task
from sat.tasks.presets import PRESETS, get_preset, list_presets

__all__ = [
    "TaskSection",
    "TaskType",
    "SectionMapping",
    "TaskPlan",
    "plan_task",
    "build_analysis_config",
    "PRESETS",
    "get_preset",
    "list_presets",
]
