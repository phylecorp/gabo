"""Tests for the new EvidenceGathering* event types.

@decision DEC-TEST-EVIDENCE-004
@title Event dataclass tests verify field presence and EventBus dispatch
@status accepted
@rationale EvidenceGatheringStarted and EvidenceGatheringCompleted are new
event types added to events.py. These tests confirm the dataclass fields are
correct and that the EventBus dispatches them to subscribers as expected.
"""

from __future__ import annotations

import dataclasses

import pytest

from sat.events import (
    EventBus,
    EvidenceGatheringCompleted,
    EvidenceGatheringStarted,
    PipelineEvent,
)


class TestEvidenceGatheringStarted:
    def test_required_field(self):
        event = EvidenceGatheringStarted(session_id="abc")
        assert event.session_id == "abc"

    def test_defaults(self):
        event = EvidenceGatheringStarted(session_id="x")
        assert event.has_evidence is False
        assert event.research_enabled is False
        assert event.decomposition_enabled is False

    def test_full_construction(self):
        event = EvidenceGatheringStarted(
            session_id="s1",
            has_evidence=True,
            research_enabled=True,
            decomposition_enabled=True,
        )
        assert event.has_evidence is True
        assert event.research_enabled is True
        assert event.decomposition_enabled is True

    def test_is_pipeline_event(self):
        event = EvidenceGatheringStarted(session_id="s")
        assert isinstance(event, PipelineEvent)

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(EvidenceGatheringStarted)


class TestEvidenceGatheringCompleted:
    def test_required_field(self):
        event = EvidenceGatheringCompleted(session_id="abc")
        assert event.session_id == "abc"

    def test_defaults(self):
        event = EvidenceGatheringCompleted(session_id="x")
        assert event.item_count == 0
        assert event.source_count == 0
        assert event.gap_count == 0

    def test_full_construction(self):
        event = EvidenceGatheringCompleted(
            session_id="s2",
            item_count=15,
            source_count=5,
            gap_count=3,
        )
        assert event.item_count == 15
        assert event.source_count == 5
        assert event.gap_count == 3

    def test_is_pipeline_event(self):
        event = EvidenceGatheringCompleted(session_id="s")
        assert isinstance(event, PipelineEvent)


@pytest.mark.asyncio
async def test_evidence_events_dispatched_via_bus():
    """EventBus correctly dispatches EvidenceGathering* events to subscribers."""
    bus = EventBus()
    received: list[PipelineEvent] = []

    async def handler(event: PipelineEvent) -> None:
        received.append(event)

    bus.subscribe(handler)

    await bus.emit(EvidenceGatheringStarted(session_id="s1", has_evidence=True))
    await bus.emit(EvidenceGatheringCompleted(session_id="s1", item_count=5))

    assert len(received) == 2
    assert isinstance(received[0], EvidenceGatheringStarted)
    assert isinstance(received[1], EvidenceGatheringCompleted)
    assert received[0].session_id == "s1"
    assert received[1].item_count == 5
