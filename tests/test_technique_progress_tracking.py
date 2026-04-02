"""Tests for technique progress tracking in ActiveRun — issue #14.

Verifies that ActiveRun accumulates StageCompleted(stage="analysis") events
so that GET /api/runs/{run_id} can return real progress instead of hardcoded [].

@decision DEC-PROGRESS-001
@title Track analysis technique completions in ActiveRun for live dashboard visibility
@status accepted
@rationale The dashboard polls REST every 10s (not WebSocket), so the REST endpoint
must return real progress for in-flight runs. ActiveRun._handle_event already
processes all events; we extend it to maintain a techniques_completed list that
the runs route reads directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sat.api.run_manager import ActiveRun, RunManager
from sat.config import AnalysisConfig, ProviderConfig
from sat.events import StageCompleted, StageStarted, ResearchCompleted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(question: str = "What are the risks?") -> AnalysisConfig:
    return AnalysisConfig(
        question=question,
        output_dir=Path("."),
        provider=ProviderConfig(provider="anthropic"),
    )


def _make_active_run(question: str = "What are the risks?") -> ActiveRun:
    return ActiveRun(run_id="test123", config=_make_config(question))


# ---------------------------------------------------------------------------
# ActiveRun.techniques_completed — initial state
# ---------------------------------------------------------------------------


class TestActiveRunTechniquesCompletedInit:
    def test_techniques_completed_starts_empty(self):
        """ActiveRun must have techniques_completed initialised to an empty list."""
        run = _make_active_run()
        assert hasattr(run, "techniques_completed"), (
            "ActiveRun must expose a techniques_completed attribute"
        )
        assert run.techniques_completed == []

    def test_techniques_completed_is_a_list(self):
        run = _make_active_run()
        assert isinstance(run.techniques_completed, list)


# ---------------------------------------------------------------------------
# ActiveRun._handle_event — accumulation of analysis completions
# ---------------------------------------------------------------------------


class TestActiveRunHandleEvent:
    @pytest.mark.asyncio
    async def test_analysis_stage_completed_appends_technique_id(self):
        """StageCompleted(stage='analysis', technique_id='ach') must be appended."""
        run = _make_active_run()
        await run._handle_event(StageCompleted(stage="analysis", technique_id="ach"))
        assert "ach" in run.techniques_completed

    @pytest.mark.asyncio
    async def test_multiple_analysis_completions_accumulate(self):
        """Multiple analysis completions must all appear in techniques_completed."""
        run = _make_active_run()
        tids = ["ach", "indicators", "assumptions"]
        for tid in tids:
            await run._handle_event(StageCompleted(stage="analysis", technique_id=tid))
        assert run.techniques_completed == tids

    @pytest.mark.asyncio
    async def test_critique_stage_completed_does_not_accumulate(self):
        """StageCompleted(stage='critique') must NOT be counted as technique completion."""
        run = _make_active_run()
        await run._handle_event(StageCompleted(stage="critique", technique_id="ach"))
        assert run.techniques_completed == []

    @pytest.mark.asyncio
    async def test_stage_started_does_not_accumulate(self):
        """StageStarted events must not affect techniques_completed."""
        run = _make_active_run()
        await run._handle_event(StageStarted(stage="analysis", technique_id="ach"))
        assert run.techniques_completed == []

    @pytest.mark.asyncio
    async def test_non_stage_event_does_not_accumulate(self):
        """Unrelated events (e.g. ResearchCompleted) must not affect techniques_completed."""
        run = _make_active_run()
        await run._handle_event(ResearchCompleted(source_count=5, claim_count=10))
        assert run.techniques_completed == []

    @pytest.mark.asyncio
    async def test_events_still_appended_to_events_log(self):
        """Existing events_log behaviour must be preserved alongside new tracking."""
        run = _make_active_run()
        event = StageCompleted(stage="analysis", technique_id="ach")
        await run._handle_event(event)
        assert len(run.events_log) == 1
        assert run.events_log[0]["type"] == "StageCompleted"

    @pytest.mark.asyncio
    async def test_analysis_completed_order_preserved(self):
        """techniques_completed must reflect the emission order, not sorted order."""
        run = _make_active_run()
        ordered = ["scenario_analysis", "ach", "indicators"]
        for tid in ordered:
            await run._handle_event(StageCompleted(stage="analysis", technique_id=tid))
        assert run.techniques_completed == ordered

    @pytest.mark.asyncio
    async def test_empty_technique_id_analysis_event_is_ignored(self):
        """StageCompleted(stage='analysis', technique_id='') should not add empty string."""
        run = _make_active_run()
        await run._handle_event(StageCompleted(stage="analysis", technique_id=""))
        # An empty technique_id is meaningless; it must not pollute the list
        assert run.techniques_completed == []


# ---------------------------------------------------------------------------
# Integration: RunManager.create_run returns ActiveRun with tracking
# ---------------------------------------------------------------------------


class TestRunManagerCreatesRunWithTracking:
    def test_create_run_has_techniques_completed(self):
        """Runs created via RunManager must also have techniques_completed."""
        manager = RunManager()
        run = manager.create_run(_make_config())
        assert hasattr(run, "techniques_completed")
        assert run.techniques_completed == []

    @pytest.mark.asyncio
    async def test_create_run_techniques_completed_accumulates_via_bus(self):
        """Events emitted on run.bus must flow through to techniques_completed."""
        manager = RunManager()
        run = manager.create_run(_make_config())
        # Emit through the bus (the production path)
        await run.bus.emit(StageCompleted(stage="analysis", technique_id="ach"))
        assert run.techniques_completed == ["ach"]

    @pytest.mark.asyncio
    async def test_create_run_critique_does_not_accumulate_via_bus(self):
        """Critique events on the bus must not affect techniques_completed."""
        manager = RunManager()
        run = manager.create_run(_make_config())
        await run.bus.emit(StageCompleted(stage="critique", technique_id="ach"))
        assert run.techniques_completed == []
