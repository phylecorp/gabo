"""Tests for pipeline event system.

@decision DEC-EVENTS-001: Typed dataclass events with async EventBus.
Tests verify fire-and-forget error isolation and NullBus no-op behavior.
"""

import logging

import pytest

from sat.events import (
    ArtifactWritten,
    EventBus,
    NullBus,
    PipelineEvent,
    ProviderCompleted,
    ProviderFailed,
    ResearchCompleted,
    ResearchStarted,
    StageCompleted,
    StageStarted,
    _NullBus,
)


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(handler)
        event = ResearchStarted(provider_names=["openai"], query="test")
        await bus.emit(event)
        assert len(received) == 1
        assert received[0] is event

    @pytest.mark.asyncio
    async def test_multiple_handlers(self):
        bus = EventBus()
        received_a, received_b = [], []

        async def handler_a(event):
            received_a.append(event)

        async def handler_b(event):
            received_b.append(event)

        bus.subscribe(handler_a)
        bus.subscribe(handler_b)
        await bus.emit(ProviderCompleted(name="test", citation_count=5))
        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_handler_error_does_not_propagate(self):
        bus = EventBus()

        async def bad_handler(event):
            raise ValueError("boom")

        received = []

        async def good_handler(event):
            received.append(event)

        bus.subscribe(bad_handler)
        bus.subscribe(good_handler)
        await bus.emit(ResearchStarted(provider_names=[], query=""))
        # good_handler still called despite bad_handler raising
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_handler_error_logged_at_warning(self, caplog):
        """Handler errors should be logged at WARNING, not DEBUG."""
        bus = EventBus()

        async def bad_handler(event):
            raise RuntimeError("handler broke")

        bus.subscribe(bad_handler)
        with caplog.at_level(logging.WARNING, logger="sat.events"):
            await bus.emit(ResearchStarted(provider_names=[], query=""))

        assert any(
            record.levelno == logging.WARNING and "Event handler error" in record.getMessage()
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_subscribe_during_emit_is_safe(self):
        """Subscribing a new handler while emit is iterating must not raise.

        list(self._handlers) in emit() prevents RuntimeError when subscribe()
        is called by a handler during iteration.
        """
        bus = EventBus()
        received_first = []
        received_late = []

        async def late_handler(e):
            received_late.append(e)

        async def handler_that_subscribes(event):
            received_first.append(event)
            bus.subscribe(late_handler)

        bus.subscribe(handler_that_subscribes)
        event = ResearchStarted(provider_names=["x"], query="q")
        await bus.emit(event)

        assert len(received_first) == 1
        assert len(received_late) == 0

    @pytest.mark.asyncio
    async def test_null_bus_is_noop(self):
        """NullBus should not raise and should silently discard events."""
        NullBus.subscribe(lambda e: None)
        await NullBus.emit(ResearchStarted(provider_names=[], query=""))
        # No assertion needed — just verify no exception is raised

    @pytest.mark.asyncio
    async def test_null_bus_does_not_call_subscribed_handlers(self):
        """NullBus.subscribe is a no-op — the handler is never stored or called."""
        null_bus = _NullBus()
        called = []

        async def handler(event):
            called.append(event)

        null_bus.subscribe(handler)
        await null_bus.emit(ResearchStarted(provider_names=["x"], query="q"))
        assert len(called) == 0

    @pytest.mark.asyncio
    async def test_emit_no_handlers(self):
        """Emitting with no handlers should be a no-op."""
        bus = EventBus()
        # Should not raise
        await bus.emit(ResearchStarted(provider_names=[], query=""))

    @pytest.mark.asyncio
    async def test_multiple_events_emit_order(self):
        """Events should be received in emission order."""
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(handler)

        e1 = ResearchStarted(provider_names=["a"], query="q1")
        e2 = ProviderCompleted(name="a", citation_count=3)
        e3 = ResearchCompleted(source_count=2, claim_count=5)

        await bus.emit(e1)
        await bus.emit(e2)
        await bus.emit(e3)

        assert received == [e1, e2, e3]


class TestEventDataclasses:
    def test_research_started_fields(self):
        e = ResearchStarted(provider_names=["a", "b"], query="q")
        assert e.provider_names == ["a", "b"]
        assert e.query == "q"

    def test_provider_completed_fields(self):
        e = ProviderCompleted(name="openai", citation_count=10, content_length=5000)
        assert e.name == "openai"
        assert e.citation_count == 10
        assert e.content_length == 5000

    def test_provider_completed_defaults(self):
        e = ProviderCompleted(name="brave", citation_count=5)
        assert e.content_length == 0

    def test_provider_failed_fields(self):
        e = ProviderFailed(name="openai", error="timeout", transient=True)
        assert e.name == "openai"
        assert e.error == "timeout"
        assert e.transient is True

    def test_provider_failed_default_transient(self):
        e = ProviderFailed(name="openai", error="bad key")
        assert e.transient is False

    def test_research_completed_fields(self):
        e = ResearchCompleted(source_count=5, claim_count=12, provider_label="multi(openai,brave)")
        assert e.source_count == 5
        assert e.claim_count == 12
        assert e.provider_label == "multi(openai,brave)"

    def test_research_completed_defaults(self):
        e = ResearchCompleted(source_count=3, claim_count=7)
        assert e.provider_label == ""

    def test_stage_started_fields(self):
        e = StageStarted(stage="critique", technique_id="ach", detail="round 1")
        assert e.stage == "critique"
        assert e.technique_id == "ach"
        assert e.detail == "round 1"

    def test_stage_started_defaults(self):
        e = StageStarted(stage="structuring")
        assert e.technique_id == ""
        assert e.detail == ""

    def test_stage_completed_fields(self):
        e = StageCompleted(stage="synthesis", technique_id="", detail="", duration_secs=3.5)
        assert e.duration_secs == 3.5

    def test_artifact_written_fields(self):
        e = ArtifactWritten(path="/out/01-ach.md", technique_id="ach", category="diagnostic")
        assert e.path == "/out/01-ach.md"
        assert e.technique_id == "ach"
        assert e.category == "diagnostic"

    def test_pipeline_event_is_base(self):
        """All event types should inherit from PipelineEvent."""
        for cls in [
            ResearchStarted,
            ProviderCompleted,
            ProviderFailed,
            ResearchCompleted,
            StageStarted,
            StageCompleted,
            ArtifactWritten,
        ]:
            # ResearchStarted requires provider_names and query
            if cls is ResearchStarted:
                e = cls(provider_names=[], query="")
            elif cls is ProviderCompleted:
                e = cls(name="x", citation_count=0)
            elif cls is ProviderFailed:
                e = cls(name="x", error="err")
            elif cls is ResearchCompleted:
                e = cls(source_count=0, claim_count=0)
            elif cls is StageStarted or cls is StageCompleted:
                e = cls(stage="test")
            elif cls is ArtifactWritten:
                e = cls(path="/tmp/x")
            assert isinstance(e, PipelineEvent), f"{cls.__name__} is not a PipelineEvent"
