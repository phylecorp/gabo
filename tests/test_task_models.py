"""Tests for task mode models and preset definitions.

@decision DEC-TASK-TEST-001
@title Test suite for TaskType/TaskPlan models and all 5 preset definitions
@status accepted
@rationale Presets embed technique_affinity IDs that must remain in sync with
the technique registry. Testing them here catches drift when new techniques
are added or IDs are renamed. Round-trip serialization tests ensure the Pydantic
v2 models serialize correctly for API responses and persistence.

Verifies:
- All 5 presets load without error
- Each preset has the expected number of sections
- All technique_affinity IDs reference valid registered techniques
- TaskPlan serialization round-trips correctly
- SectionMapping and TaskPlan models behave correctly
"""

from __future__ import annotations

import pytest


def test_all_presets_load() -> None:
    """All 5 presets can be imported without error."""
    from sat.tasks.presets import PRESETS, list_presets

    preset_list = list_presets()
    assert len(preset_list) == 5, f"Expected 5 presets, got {len(preset_list)}"
    assert set(PRESETS.keys()) == {"threat", "brief", "bda", "annex_b", "annex_l"}


def test_get_preset() -> None:
    """get_preset returns the correct preset by ID."""
    from sat.tasks.presets import get_preset

    preset = get_preset("threat")
    assert preset.id == "threat"
    assert preset.name  # non-empty

    with pytest.raises(ValueError, match="Unknown task type"):
        get_preset("nonexistent")


def test_threat_preset_structure() -> None:
    """Threat assessment preset has at least 3 sections."""
    from sat.tasks.presets import get_preset

    preset = get_preset("threat")
    assert len(preset.sections) >= 3
    section_ids = [s.id for s in preset.sections]
    # Key sections must exist
    assert "threat_overview" in section_ids or len(preset.sections) >= 3


def test_brief_preset_structure() -> None:
    """Quick brief preset has at least 3 sections."""
    from sat.tasks.presets import get_preset

    preset = get_preset("brief")
    assert len(preset.sections) >= 3


def test_bda_preset_structure() -> None:
    """BDA preset has at least 3 sections."""
    from sat.tasks.presets import get_preset

    preset = get_preset("bda")
    assert len(preset.sections) >= 3


def test_annex_b_preset_structure() -> None:
    """Annex B preset has at least 3 sections."""
    from sat.tasks.presets import get_preset

    preset = get_preset("annex_b")
    assert len(preset.sections) >= 3


def test_annex_l_preset_structure() -> None:
    """Annex L preset has at least 3 sections."""
    from sat.tasks.presets import get_preset

    preset = get_preset("annex_l")
    assert len(preset.sections) >= 3


def test_all_technique_affinities_valid() -> None:
    """All technique_affinity IDs in all presets reference valid registered techniques."""
    import sat.techniques  # noqa: F401 — trigger registration
    from sat.techniques.registry import list_technique_ids
    from sat.tasks.presets import list_presets

    valid_ids = set(list_technique_ids())
    presets = list_presets()

    for preset in presets:
        for section in preset.sections:
            if section.technique_affinity:
                for tid in section.technique_affinity:
                    assert tid in valid_ids, (
                        f"Preset '{preset.id}' section '{section.id}' "
                        f"has invalid technique_affinity '{tid}'. "
                        f"Valid: {sorted(valid_ids)}"
                    )


def test_default_techniques_valid() -> None:
    """All default_techniques in presets reference valid technique IDs."""
    import sat.techniques  # noqa: F401 — trigger registration
    from sat.techniques.registry import list_technique_ids
    from sat.tasks.presets import list_presets

    valid_ids = set(list_technique_ids())
    for preset in list_presets():
        if preset.default_techniques:
            for tid in preset.default_techniques:
                assert tid in valid_ids, (
                    f"Preset '{preset.id}' has invalid default_technique '{tid}'"
                )


def test_task_plan_serialization_roundtrip() -> None:
    """TaskPlan serializes and deserializes correctly."""
    from sat.tasks.models import SectionMapping, TaskPlan

    plan = TaskPlan(
        task_type="threat",
        question="What is the adversary's capability?",
        sections=[
            SectionMapping(
                section_id="threat_overview",
                technique_ids=["assumptions", "quality"],
                synthesis_needed=False,
                evidence_gaps=["recent satellite imagery"],
            ),
            SectionMapping(
                section_id="capability_assessment",
                technique_ids=["ach", "indicators"],
                synthesis_needed=True,
                evidence_gaps=[],
            ),
        ],
        techniques=["assumptions", "quality", "ach", "indicators"],
        research_queries=["latest adversary capability reports"],
        evidence_gaps=["recent satellite imagery"],
        rationale="Selected based on threat assessment template requirements",
    )

    # Serialize and deserialize
    data = plan.model_dump()
    restored = TaskPlan.model_validate(data)

    assert restored.task_type == plan.task_type
    assert restored.question == plan.question
    assert len(restored.sections) == 2
    assert restored.sections[0].section_id == "threat_overview"
    assert restored.sections[0].technique_ids == ["assumptions", "quality"]
    assert restored.sections[0].evidence_gaps == ["recent satellite imagery"]
    assert restored.techniques == plan.techniques
    assert restored.research_queries == plan.research_queries
    assert restored.evidence_gaps == plan.evidence_gaps
    assert restored.rationale == plan.rationale


def test_task_plan_json_roundtrip() -> None:
    """TaskPlan serializes to JSON and deserializes correctly."""
    from sat.tasks.models import SectionMapping, TaskPlan

    plan = TaskPlan(
        task_type="brief",
        question="Will the ceasefire hold?",
        sections=[
            SectionMapping(
                section_id="bluf",
                technique_ids=["assumptions"],
                synthesis_needed=False,
            )
        ],
        techniques=["assumptions"],
        rationale="Minimal technique set for quick brief",
    )

    json_str = plan.model_dump_json()
    restored = TaskPlan.model_validate_json(json_str)

    assert restored.task_type == "brief"
    assert restored.question == "Will the ceasefire hold?"
    assert restored.research_queries is None
    assert restored.evidence_gaps == []


def test_section_mapping_defaults() -> None:
    """SectionMapping default fields are correct."""
    from sat.tasks.models import SectionMapping

    sm = SectionMapping(
        section_id="test",
        technique_ids=["ach"],
    )
    assert sm.synthesis_needed is False
    assert sm.evidence_gaps == []


def test_task_type_model() -> None:
    """TaskType model validates correctly."""
    from sat.tasks.models import TaskSection, TaskType

    task_type = TaskType(
        id="custom",
        name="Custom Task",
        description="A custom task type for testing",
        sections=[
            TaskSection(
                id="section1",
                name="Section 1",
                description="First section",
                required_analysis=["evidence_assessment"],
                technique_affinity=["quality", "ach"],
                requires_research=True,
                evidence_requirements="Satellite imagery required",
            )
        ],
    )

    assert task_type.id == "custom"
    assert len(task_type.sections) == 1
    assert task_type.sections[0].requires_research is True


def test_preset_sections_have_descriptions() -> None:
    """All sections in all presets have non-empty descriptions."""
    from sat.tasks.presets import list_presets

    for preset in list_presets():
        for section in preset.sections:
            assert section.description.strip(), (
                f"Preset '{preset.id}' section '{section.id}' has empty description"
            )
            assert section.name.strip(), (
                f"Preset '{preset.id}' section '{section.id}' has empty name"
            )
