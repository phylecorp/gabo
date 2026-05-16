"""Pydantic v2 models for task mode — template-driven analysis.

@decision DEC-TASK-001
@title Task mode is a wrapper: computes AnalysisConfig, delegates to existing pipeline
@status accepted
@rationale SAT's pipeline already handles technique execution, research, reporting,
and adversarial critique. Task mode inverts the flow: start from a deliverable
template, decompose it into analytical requirements, and compute an AnalysisConfig
that drives the existing run_analysis() unchanged. These models represent the
deliverable template structure (TaskType/TaskSection), the planner's execution
plan (TaskPlan/SectionMapping), and are kept strictly separate from AnalysisConfig
to avoid coupling the template domain to the pipeline domain.

The wrapper architecture means:
- TaskType defines what a deliverable looks like
- TaskPlan maps template requirements to technique/research selections
- AnalysisConfig is what the existing pipeline receives (built by build_analysis_config)
- The pipeline never knows about task mode — it just runs with explicit techniques
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TaskSection(BaseModel):
    """One section of a deliverable template.

    Sections define what the deliverable requires, not how to produce it.
    The planner maps sections to techniques; the pipeline executes them.
    technique_affinity provides hints to the planner — they are not hard constraints.
    """

    id: str
    """Unique identifier within the task type, e.g. 'threat_overview'."""

    name: str
    """Human-readable section name, e.g. 'Threat Overview'."""

    description: str
    """What this section should contain — used in the planner prompt."""

    required_analysis: list[str]
    """Types of analysis needed, e.g. ['evidence_assessment', 'hypothesis_evaluation']."""

    technique_affinity: list[str] | None = None
    """Preferred technique IDs — hints to the planner, not hard constraints."""

    requires_research: bool = False
    """Whether this section typically benefits from external research."""

    evidence_requirements: str | None = None
    """Description of what evidence is needed to fill this section well."""


class TaskType(BaseModel):
    """A deliverable template definition.

    Defines the structure of an intelligence product. The planner uses this
    to map analytical requirements to SAT techniques.
    """

    id: str
    """Unique identifier, e.g. 'threat', 'brief', 'bda', 'annex_b', 'annex_l'."""

    name: str
    """Human-readable name, e.g. 'Threat Assessment'."""

    description: str
    """When and why to use this task type."""

    sections: list[TaskSection]
    """Ordered list of sections in this deliverable."""

    default_techniques: list[str] | None = None
    """Baseline technique set. The planner may add/remove based on the question."""

    output_template: str | None = None
    """Jinja2 template filename for Phase 2 rendering (not used in Phase 1)."""


class SectionMapping(BaseModel):
    """Maps a template section to the technique outputs that fill it.

    Produced by the planner for each section in the TaskType. Captures
    which techniques cover each section and what evidence is missing.
    """

    section_id: str
    """References TaskSection.id in the parent TaskType."""

    technique_ids: list[str]
    """Technique IDs whose outputs feed this section."""

    synthesis_needed: bool = False
    """Whether an LLM should synthesize across multiple technique outputs."""

    evidence_gaps: list[str] = Field(default_factory=list)
    """Specific evidence missing that would improve this section."""


class TaskPlan(BaseModel):
    """The planner's complete execution plan for a task.

    Output of plan_task(). Consumed by build_analysis_config() to produce
    an AnalysisConfig that the existing pipeline runs unchanged.
    """

    task_type: str
    """ID of the TaskType this plan is for."""

    question: str
    """The analytic question driving this task."""

    sections: list[SectionMapping]
    """One SectionMapping per section in the TaskType."""

    techniques: list[str]
    """Union of all technique_ids across all sections — what the pipeline will run."""

    research_queries: list[str] | None = None
    """Targeted research queries to fill evidence gaps, if research is enabled."""

    evidence_gaps: list[str] = Field(default_factory=list)
    """Aggregate evidence gaps across all sections — surfaced to the user."""

    rationale: str
    """Why this plan was chosen — included in output for analyst review."""
