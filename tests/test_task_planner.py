"""Tests for the task planner: LLM-powered section→technique mapping.

@decision DEC-TASK-TEST-002
@title Planner tests use mock LLM provider to avoid live API calls
@status accepted
@rationale The planner makes LLM calls to map sections to techniques. Tests use
a mock LLMProvider that returns pre-crafted JSON responses. This is the appropriate
boundary for mocking: LLMProvider is an external HTTP service boundary (Anthropic,
OpenAI, Gemini APIs). Internal validation logic (_validate_plan, build_analysis_config)
is tested directly without mocks — those functions take plain dicts/models.
This follows the project's mock-gate rules: mocks only for external boundaries.

Tests cover:
- Planner validation rejects unknown technique IDs
- Planner validation ensures all sections have at least one technique
- build_analysis_config produces correct AnalysisConfig
- Mock LLM response → correct TaskPlan output
- Fallback handling when LLM returns malformed JSON
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock  # @mock-exempt: LLMProvider is an external HTTP API boundary (Anthropic/OpenAI/Gemini)

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_mock_provider(response_json: dict | str) -> MagicMock:
    """Create a mock LLMProvider that returns response_json as text.

    # @mock-exempt: LLMProvider calls external HTTP APIs (Anthropic, OpenAI, Gemini).
    # Using a mock avoids live API calls and key requirements in CI.
    """
    if isinstance(response_json, dict):
        text = json.dumps(response_json)
    else:
        text = response_json

    result = MagicMock()
    result.text = text

    provider = MagicMock()
    provider.generate = AsyncMock(return_value=result)
    return provider


def _make_threat_response(
    section_overrides: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """Build a valid planner response for the threat preset."""
    sections = [
        {
            "section_id": "threat_overview",
            "technique_ids": ["quality"],
            "synthesis_needed": False,
            "evidence_gaps": ["recent reporting"],
        },
        {
            "section_id": "capability_assessment",
            "technique_ids": ["ach", "indicators"],
            "synthesis_needed": False,
            "evidence_gaps": [],
        },
        {
            "section_id": "intent_analysis",
            "technique_ids": ["red_team", "assumptions"],
            "synthesis_needed": False,
            "evidence_gaps": [],
        },
        {
            "section_id": "vulnerability_mapping",
            "technique_ids": ["outside_in"],
            "synthesis_needed": False,
            "evidence_gaps": [],
        },
        {
            "section_id": "risk_matrix",
            "technique_ids": ["ach", "alt_futures"],
            "synthesis_needed": True,
            "evidence_gaps": [],
        },
        {
            "section_id": "dissenting_views",
            "technique_ids": ["devils_advocacy"],
            "synthesis_needed": False,
            "evidence_gaps": [],
        },
    ]

    if section_overrides:
        for i, section in enumerate(sections):
            if section["section_id"] in section_overrides:
                sections[i] = {**section, **section_overrides[section["section_id"]]}

    result = {
        "sections": sections,
        "research_queries": ["China naval capability reports 2024"],
        "evidence_gaps": ["recent satellite imagery"],
        "rationale": "Threat assessment requires capability and intent analysis.",
    }
    if extra:
        result.update(extra)
    return result


# ---------------------------------------------------------------------------
# Validation: _validate_plan internals (no mocks needed — pure Python)
# ---------------------------------------------------------------------------


def test_validate_plan_rejects_unknown_technique_ids() -> None:
    """Planner validation filters out unknown technique IDs and uses fallbacks."""
    import sat.techniques  # noqa: F401
    from sat.tasks.planner import _validate_plan
    from sat.tasks.presets import get_preset

    task_type = get_preset("brief")

    raw = {
        "sections": [
            {
                "section_id": "bluf",
                "technique_ids": ["nonexistent_technique", "also_fake"],
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
            {
                "section_id": "supporting_analysis",
                "technique_ids": ["quality", "ach"],
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
            {
                "section_id": "dissenting_views",
                "technique_ids": ["devils_advocacy"],
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
            {
                "section_id": "recommendations",
                "technique_ids": ["indicators"],
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
        ],
        "research_queries": None,
        "evidence_gaps": [],
        "rationale": "Test plan",
    }

    plan = _validate_plan(raw, task_type, "Will the ceasefire hold?")

    # bluf section had only invalid IDs — should fall back to first affinity or assumptions
    bluf_section = next(s for s in plan.sections if s.section_id == "bluf")
    assert len(bluf_section.technique_ids) >= 1
    # All technique IDs in the plan must be valid
    from sat.techniques.registry import list_technique_ids

    valid = set(list_technique_ids())
    for section in plan.sections:
        for tid in section.technique_ids:
            assert tid in valid, f"Invalid technique ID {tid!r} in section {section.section_id}"


def test_validate_plan_ensures_all_sections_covered() -> None:
    """Planner adds fallback mappings for any sections missing from LLM response."""
    import sat.techniques  # noqa: F401
    from sat.tasks.planner import _validate_plan
    from sat.tasks.presets import get_preset

    task_type = get_preset("brief")

    # Only provide 2 of 4 sections
    raw = {
        "sections": [
            {
                "section_id": "bluf",
                "technique_ids": ["assumptions"],
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
            {
                "section_id": "supporting_analysis",
                "technique_ids": ["quality"],
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
        ],
        "research_queries": None,
        "evidence_gaps": [],
        "rationale": "Partial response",
    }

    plan = _validate_plan(raw, task_type, "Test question")

    # All 4 sections must be present
    assert len(plan.sections) == len(task_type.sections)
    section_ids = {s.section_id for s in plan.sections}
    expected_ids = {s.id for s in task_type.sections}
    assert section_ids == expected_ids


def test_validate_plan_techniques_are_ordered() -> None:
    """Planner orders techniques: diagnostic first, then contrarian, then imaginative."""
    import sat.techniques  # noqa: F401
    from sat.tasks.planner import _validate_plan
    from sat.tasks.presets import get_preset
    from sat.techniques.registry import get_technique

    task_type = get_preset("brief")
    raw = {
        "sections": [
            {
                "section_id": "bluf",
                "technique_ids": ["devils_advocacy"],  # contrarian
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
            {
                "section_id": "supporting_analysis",
                "technique_ids": ["alt_futures", "quality"],  # imaginative + diagnostic
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
            {
                "section_id": "dissenting_views",
                "technique_ids": ["assumptions"],  # diagnostic
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
            {
                "section_id": "recommendations",
                "technique_ids": ["indicators"],  # diagnostic
                "synthesis_needed": False,
                "evidence_gaps": [],
            },
        ],
        "research_queries": None,
        "evidence_gaps": [],
        "rationale": "Ordering test",
    }

    plan = _validate_plan(raw, task_type, "Test")

    # Verify ordering: diagnostic before contrarian before imaginative
    category_order = {"diagnostic": 0, "contrarian": 1, "imaginative": 2}
    prev_order = -1
    for tid in plan.techniques:
        t = get_technique(tid)
        cat_order = category_order[t.metadata.category]
        assert cat_order >= prev_order, (
            f"Technique {tid!r} (category {t.metadata.category!r}) "
            f"appears after higher-category technique"
        )
        prev_order = cat_order


# ---------------------------------------------------------------------------
# build_analysis_config (no mocks needed — pure Python)
# ---------------------------------------------------------------------------


def test_build_analysis_config_sets_techniques() -> None:
    """build_analysis_config sets techniques explicitly from the plan."""
    from sat.config import AnalysisConfig, ProviderConfig
    from sat.tasks.models import SectionMapping, TaskPlan
    from sat.tasks.planner import build_analysis_config

    plan = TaskPlan(
        task_type="threat",
        question="What is X's naval capability?",
        sections=[
            SectionMapping(
                section_id="threat_overview",
                technique_ids=["quality", "assumptions"],
                synthesis_needed=False,
            ),
            SectionMapping(
                section_id="capability_assessment",
                technique_ids=["ach", "indicators"],
                synthesis_needed=True,
            ),
        ],
        techniques=["quality", "assumptions", "ach", "indicators"],
        rationale="Test plan",
    )

    base = AnalysisConfig(
        question="What is X's naval capability?",
        provider=ProviderConfig(provider="anthropic"),
    )

    config = build_analysis_config(plan, base)

    assert config.techniques == ["quality", "assumptions", "ach", "indicators"]
    assert config.question == plan.question
    assert config.provider.provider == "anthropic"


def test_build_analysis_config_preserves_base_fields() -> None:
    """build_analysis_config preserves non-technique fields from base_config."""
    from pathlib import Path

    from sat.config import AnalysisConfig, ProviderConfig, ReportConfig
    from sat.tasks.models import SectionMapping, TaskPlan
    from sat.tasks.planner import build_analysis_config

    plan = TaskPlan(
        task_type="brief",
        question="Will the ceasefire hold?",
        sections=[
            SectionMapping(section_id="bluf", technique_ids=["assumptions"]),
            SectionMapping(section_id="supporting_analysis", technique_ids=["quality"]),
            SectionMapping(section_id="dissenting_views", technique_ids=["devils_advocacy"]),
            SectionMapping(section_id="recommendations", technique_ids=["indicators"]),
        ],
        techniques=["assumptions", "quality", "devils_advocacy", "indicators"],
        rationale="Test",
    )

    base = AnalysisConfig(
        question="Original question",
        evidence="Some evidence",
        provider=ProviderConfig(provider="openai", model="gpt-4o"),
        report=ReportConfig(enabled=True, fmt="html"),
        output_dir=Path("/tmp/test-output"),
    )

    config = build_analysis_config(plan, base)

    assert config.question == "Will the ceasefire hold?"
    assert config.techniques == ["assumptions", "quality", "devils_advocacy", "indicators"]
    assert config.evidence == "Some evidence"
    assert config.provider.provider == "openai"
    assert config.report.fmt == "html"


# ---------------------------------------------------------------------------
# Full plan_task() with mock LLM provider (external HTTP boundary)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_task_threat_preset() -> None:
    """plan_task returns a valid TaskPlan for the threat preset."""
    import sat.techniques  # noqa: F401
    from sat.tasks.planner import plan_task
    from sat.tasks.presets import get_preset
    from sat.techniques.registry import list_technique_ids

    task_type = get_preset("threat")
    response = _make_threat_response()
    provider = _make_mock_provider(response)  # @mock-exempt: LLMProvider is external HTTP API

    plan = await plan_task(
        task_type=task_type,
        question="What is China's naval capability in the South China Sea?",
        evidence=None,
        provider=provider,
    )

    assert plan.task_type == "threat"
    assert plan.question == "What is China's naval capability in the South China Sea?"
    assert len(plan.sections) == len(task_type.sections)

    valid = set(list_technique_ids())
    for tid in plan.techniques:
        assert tid in valid

    assert plan.research_queries is not None
    assert len(plan.research_queries) > 0
    provider.generate.assert_called_once()


@pytest.mark.asyncio
async def test_plan_task_handles_markdown_fenced_json() -> None:
    """plan_task handles LLM responses wrapped in markdown code fences."""
    import sat.techniques  # noqa: F401
    from sat.tasks.planner import plan_task
    from sat.tasks.presets import get_preset

    task_type = get_preset("brief")
    inner = {
        "sections": [
            {"section_id": "bluf", "technique_ids": ["assumptions"], "synthesis_needed": False, "evidence_gaps": []},
            {"section_id": "supporting_analysis", "technique_ids": ["quality"], "synthesis_needed": False, "evidence_gaps": []},
            {"section_id": "dissenting_views", "technique_ids": ["devils_advocacy"], "synthesis_needed": False, "evidence_gaps": []},
            {"section_id": "recommendations", "technique_ids": ["indicators"], "synthesis_needed": False, "evidence_gaps": []},
        ],
        "research_queries": None,
        "evidence_gaps": [],
        "rationale": "Quick brief analysis.",
    }
    fenced = f"```json\n{json.dumps(inner)}\n```"
    provider = _make_mock_provider(fenced)  # @mock-exempt: LLMProvider is external HTTP API

    plan = await plan_task(
        task_type=task_type,
        question="Will the ceasefire hold?",
        evidence=None,
        provider=provider,
    )

    assert plan.task_type == "brief"
    assert len(plan.sections) == len(task_type.sections)
    assert "assumptions" in plan.techniques


@pytest.mark.asyncio
async def test_plan_task_fallback_on_invalid_json() -> None:
    """plan_task falls back gracefully when LLM returns non-JSON text."""
    import sat.techniques  # noqa: F401
    from sat.tasks.planner import plan_task
    from sat.tasks.presets import get_preset

    task_type = get_preset("brief")
    provider = _make_mock_provider("I cannot help with that request.")  # @mock-exempt: LLMProvider is external HTTP API

    plan = await plan_task(
        task_type=task_type,
        question="Will the ceasefire hold?",
        evidence=None,
        provider=provider,
    )

    assert plan.task_type == "brief"
    assert len(plan.sections) == len(task_type.sections)
    assert len(plan.techniques) >= 1


@pytest.mark.asyncio
async def test_plan_task_all_sections_covered_even_if_llm_skips_some() -> None:
    """plan_task adds fallback mappings for sections the LLM omitted."""
    import sat.techniques  # noqa: F401
    from sat.tasks.planner import plan_task
    from sat.tasks.presets import get_preset

    task_type = get_preset("threat")  # 6 sections

    # LLM only returns 3 of 6 sections
    partial_response = {
        "sections": [
            {"section_id": "threat_overview", "technique_ids": ["quality"], "synthesis_needed": False, "evidence_gaps": []},
            {"section_id": "capability_assessment", "technique_ids": ["ach"], "synthesis_needed": False, "evidence_gaps": []},
            {"section_id": "intent_analysis", "technique_ids": ["red_team"], "synthesis_needed": False, "evidence_gaps": []},
        ],
        "research_queries": None,
        "evidence_gaps": [],
        "rationale": "Partial response",
    }
    provider = _make_mock_provider(partial_response)  # @mock-exempt: LLMProvider is external HTTP API

    plan = await plan_task(
        task_type=task_type,
        question="What is the adversary's capability?",
        evidence=None,
        provider=provider,
    )

    assert len(plan.sections) == 6
    section_ids = {s.section_id for s in plan.sections}
    expected_ids = {s.id for s in task_type.sections}
    assert section_ids == expected_ids
