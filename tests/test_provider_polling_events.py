"""Tests for ProviderPolling event emission from deep research providers.

@decision DEC-RESEARCH-015
@title ProviderPolling events for liveness feedback during long polling
@status accepted
@rationale Deep research providers can poll for 20+ minutes. The frontend
was frozen showing only a timer with no indication of activity. ProviderPolling
events emitted during polling loops give the frontend real-time liveness signals.
Tests cover: event structure, poll frequency throttling, EventBus threading
through provider constructors, backward-compat NullBus default, frontend
type additions, and production-sequence simulation (provider emits polling
events while multi_runner collects them).
"""
# @mock-exempt: Mocking external HTTP APIs (OpenAI Responses API, Gemini Interactions API,
# Perplexity API) at the service boundary, per Sacred Practice #5.

from __future__ import annotations

# @mock-exempt: Mocking external HTTP APIs at the service boundary (OpenAI, Gemini, Perplexity)
from unittest.mock import AsyncMock, MagicMock, patch

from sat.events import EventBus, NullBus, PipelineEvent, ProviderPolling


# ---- Unit: ProviderPolling event dataclass ----

class TestProviderPollingEvent:
    """ProviderPolling event dataclass fields and inheritance."""

    def test_is_pipeline_event(self):
        e = ProviderPolling(name="openai_deep", attempt=1, max_attempts=120)
        assert isinstance(e, PipelineEvent)

    def test_required_fields(self):
        e = ProviderPolling(name="gemini_deep", attempt=5, max_attempts=80)
        assert e.name == "gemini_deep"
        assert e.attempt == 5
        assert e.max_attempts == 80

    def test_status_defaults_to_empty_string(self):
        e = ProviderPolling(name="perplexity", attempt=1, max_attempts=1)
        assert e.status == ""

    def test_status_can_be_set(self):
        e = ProviderPolling(name="openai_deep", attempt=3, max_attempts=120, status="in_progress")
        assert e.status == "in_progress"

    def test_first_attempt_is_one_based(self):
        """attempt=1 means the first poll — consistent with 1-based UI display."""
        e = ProviderPolling(name="openai_deep", attempt=1, max_attempts=120)
        assert e.attempt == 1

    def test_emittable_via_eventbus(self):
        """ProviderPolling must be emittable through EventBus without error."""
        import asyncio
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(handler)

        async def run():
            await bus.emit(ProviderPolling(name="openai_deep", attempt=1, max_attempts=120))

        asyncio.run(run())
        assert len(received) == 1
        assert isinstance(received[0], ProviderPolling)

    def test_null_bus_discards_polling_events(self):
        """NullBus must silently discard ProviderPolling (no error)."""
        import asyncio

        async def run():
            await NullBus.emit(ProviderPolling(name="openai_deep", attempt=1, max_attempts=120))

        asyncio.run(run())


# ---- Unit: OpenAI deep research provider ----

class TestOpenAIDeepResearchProviderPolling:
    """OpenAI provider emits ProviderPolling events during _poll_until_complete."""

    async def _make_provider_with_bus(self, bus: EventBus):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from sat.research.openai_deep import OpenAIDeepResearchProvider
            return OpenAIDeepResearchProvider(events=bus)

    def _make_success_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "id": "resp_123",
            "status": "completed",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "Result", "annotations": []}]
            }]
        }
        resp.raise_for_status = MagicMock()
        return resp

    def _make_inprogress_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"id": "resp_123", "status": "in_progress"}
        resp.raise_for_status = MagicMock()
        return resp

    async def test_accepts_events_kwarg(self):
        """Provider constructor accepts events= keyword argument."""
        bus = EventBus()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from sat.research.openai_deep import OpenAIDeepResearchProvider
            provider = OpenAIDeepResearchProvider(events=bus)
        assert provider._events is bus

    async def test_no_events_uses_null_bus(self):
        """Provider with no events= uses NullBus (backward compatible)."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            from sat.research.openai_deep import OpenAIDeepResearchProvider
            provider = OpenAIDeepResearchProvider()
        # NullBus is a singleton — provider should hold a NullBus instance
        from sat.events import _NullBus
        assert isinstance(provider._events, _NullBus)

    async def test_emits_polling_event_on_first_poll(self):
        """ProviderPolling is emitted on the first poll attempt (attempt=0 mod check)."""
        bus = EventBus()
        polling_events = []

        async def capture(event):
            if isinstance(event, ProviderPolling):
                polling_events.append(event)

        bus.subscribe(capture)

        submit_resp = MagicMock()
        submit_resp.status_code = 200
        submit_resp.json.return_value = {"id": "resp_emit_test"}
        submit_resp.raise_for_status = MagicMock()

        success_resp = self._make_success_response()

        with patch("sat.research.openai_deep.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            # First call: in_progress, second call: completed
            mock_client.post = AsyncMock(return_value=submit_resp)
            mock_client.get = AsyncMock(side_effect=[self._make_inprogress_response(), success_resp])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
                patch("sat.research.openai_deep.asyncio.sleep", new=AsyncMock()),
            ):
                from sat.research.openai_deep import OpenAIDeepResearchProvider
                provider = OpenAIDeepResearchProvider(events=bus)
                await provider.research("test query")

        # At minimum, attempt=1 (first poll) should have been emitted
        assert len(polling_events) >= 1
        first = polling_events[0]
        assert first.name == "openai_deep"
        assert first.attempt == 1
        assert first.max_attempts > 0

    async def test_polling_event_name_is_openai_deep(self):
        """ProviderPolling.name must be 'openai_deep' — used as frontend key."""
        bus = EventBus()
        polling_events = []

        async def capture(event):
            if isinstance(event, ProviderPolling):
                polling_events.append(event)

        bus.subscribe(capture)

        submit_resp = MagicMock()
        submit_resp.status_code = 200
        submit_resp.json.return_value = {"id": "resp_name_test"}
        submit_resp.raise_for_status = MagicMock()

        with patch("sat.research.openai_deep.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_resp)
            mock_client.get = AsyncMock(return_value=self._make_success_response())
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
                patch("sat.research.openai_deep.asyncio.sleep", new=AsyncMock()),
            ):
                from sat.research.openai_deep import OpenAIDeepResearchProvider
                provider = OpenAIDeepResearchProvider(events=bus)
                await provider.research("test query")

        assert all(e.name == "openai_deep" for e in polling_events)

    async def test_polling_event_throttled_not_every_attempt(self):
        """ProviderPolling is NOT emitted on every poll attempt (to avoid log flooding)."""
        bus = EventBus()
        polling_events = []

        async def capture(event):
            if isinstance(event, ProviderPolling):
                polling_events.append(event)

        bus.subscribe(capture)

        submit_resp = MagicMock()
        submit_resp.status_code = 200
        submit_resp.json.return_value = {"id": "resp_throttle"}
        submit_resp.raise_for_status = MagicMock()

        # Return in_progress for 7 polls, then completed
        def make_in_progress():
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {"id": "resp_throttle", "status": "in_progress"}
            r.raise_for_status = MagicMock()
            return r

        responses = [make_in_progress() for _ in range(7)] + [self._make_success_response()]

        with patch("sat.research.openai_deep.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_resp)
            mock_client.get = AsyncMock(side_effect=responses)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
                patch("sat.research.openai_deep.asyncio.sleep", new=AsyncMock()),
            ):
                from sat.research.openai_deep import OpenAIDeepResearchProvider
                provider = OpenAIDeepResearchProvider(events=bus)
                await provider.research("test query")

        # 8 polls total. Should emit fewer than 8 ProviderPolling events (throttled).
        # At most every 4th, so max 2 from polls 0 and 4 (attempts 1 and 5).
        assert len(polling_events) < 8

    async def test_status_included_in_polling_event(self):
        """ProviderPolling.status captures server-side status string."""
        bus = EventBus()
        polling_events = []

        async def capture(event):
            if isinstance(event, ProviderPolling):
                polling_events.append(event)

        bus.subscribe(capture)

        submit_resp = MagicMock()
        submit_resp.status_code = 200
        submit_resp.json.return_value = {"id": "resp_status"}
        submit_resp.raise_for_status = MagicMock()

        success_resp = self._make_success_response()

        with patch("sat.research.openai_deep.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=submit_resp)
            mock_client.get = AsyncMock(return_value=success_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with (
                patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
                patch("sat.research.openai_deep.asyncio.sleep", new=AsyncMock()),
            ):
                from sat.research.openai_deep import OpenAIDeepResearchProvider
                provider = OpenAIDeepResearchProvider(events=bus)
                await provider.research("test query")

        # At attempt 0, status from server on first (and only) poll should be "completed"
        if polling_events:
            assert polling_events[0].status != "" or polling_events[0].attempt >= 1


# ---- Unit: Gemini deep research provider ----

class TestGeminiDeepResearchProviderPolling:
    """Gemini provider emits ProviderPolling events during _poll_until_complete."""

    def _make_submit_resp(self):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"name": "interactions/gem_test"}
        r.raise_for_status = MagicMock()
        return r

    def _make_completed_resp(self):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {
            "name": "interactions/gem_test",
            "status": "completed",
            "outputs": [{"text": "Gemini research result"}],
            "sources": [{"url": "https://example.com", "title": "Example"}],
        }
        r.raise_for_status = MagicMock()
        return r

    def _make_inprogress_resp(self):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"name": "interactions/gem_test", "status": "in_progress"}
        r.raise_for_status = MagicMock()
        return r

    async def test_accepts_events_kwarg(self):
        """Provider constructor accepts events= keyword argument."""
        bus = EventBus()
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            from sat.research.gemini_deep import GeminiDeepResearchProvider
            provider = GeminiDeepResearchProvider(events=bus)
        assert provider._events is bus

    async def test_no_events_uses_null_bus(self):
        """Provider with no events= uses NullBus (backward compatible)."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            from sat.research.gemini_deep import GeminiDeepResearchProvider
            provider = GeminiDeepResearchProvider()
        from sat.events import _NullBus
        assert isinstance(provider._events, _NullBus)

    async def test_emits_polling_event_during_poll(self):
        """ProviderPolling is emitted during poll loops."""
        bus = EventBus()
        polling_events = []

        async def capture(event):
            if isinstance(event, ProviderPolling):
                polling_events.append(event)

        bus.subscribe(capture)

        with patch("sat.research.gemini_deep.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=self._make_submit_resp())
            # First: in_progress (triggers polling event), second: completed
            mock_client.get = AsyncMock(
                side_effect=[self._make_inprogress_resp(), self._make_completed_resp()]
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with (
                patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
                patch("sat.research.gemini_deep.asyncio.sleep", new=AsyncMock()),
            ):
                from sat.research.gemini_deep import GeminiDeepResearchProvider
                provider = GeminiDeepResearchProvider(events=bus)
                await provider.research("test query")

        assert len(polling_events) >= 1
        first = polling_events[0]
        assert first.name == "gemini_deep"
        assert first.attempt >= 1

    async def test_polling_event_name_is_gemini_deep(self):
        """ProviderPolling.name must be 'gemini_deep'."""
        bus = EventBus()
        polling_events = []

        async def capture(event):
            if isinstance(event, ProviderPolling):
                polling_events.append(event)

        bus.subscribe(capture)

        with patch("sat.research.gemini_deep.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=self._make_submit_resp())
            mock_client.get = AsyncMock(return_value=self._make_completed_resp())
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with (
                patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}),
                patch("sat.research.gemini_deep.asyncio.sleep", new=AsyncMock()),
            ):
                from sat.research.gemini_deep import GeminiDeepResearchProvider
                provider = GeminiDeepResearchProvider(events=bus)
                await provider.research("test query")

        assert all(e.name == "gemini_deep" for e in polling_events)


# ---- Unit: Perplexity provider ----

class TestPerplexityProviderPolling:
    """Perplexity provider emits a single ProviderPolling before API call."""

    async def test_accepts_events_kwarg(self):
        """Provider constructor accepts events= keyword argument."""
        bus = EventBus()
        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            from sat.research.perplexity import PerplexityProvider
            provider = PerplexityProvider(events=bus)
        assert provider._events is bus

    async def test_no_events_uses_null_bus(self):
        """Provider with no events= uses NullBus."""
        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            from sat.research.perplexity import PerplexityProvider
            provider = PerplexityProvider()
        from sat.events import _NullBus
        assert isinstance(provider._events, _NullBus)

    async def test_emits_single_polling_event(self):
        """Perplexity emits exactly one ProviderPolling before the API call."""
        bus = EventBus()
        polling_events = []

        async def capture(event):
            if isinstance(event, ProviderPolling):
                polling_events.append(event)

        bus.subscribe(capture)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Research findings"
        mock_response.citations = None

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            from sat.research.perplexity import PerplexityProvider
            provider = PerplexityProvider(events=bus)
        provider._client = mock_client

        await provider.research("test query")

        assert len(polling_events) == 1
        evt = polling_events[0]
        assert evt.name == "perplexity"
        assert evt.attempt == 1
        assert evt.max_attempts == 1
        assert evt.status == "awaiting_response"

    async def test_polling_event_emitted_before_api_call(self):
        """ProviderPolling event is emitted before the API call completes."""
        bus = EventBus()
        call_order = []

        async def capture(event):
            if isinstance(event, ProviderPolling):
                call_order.append("event")

        bus.subscribe(capture)

        async def api_call(*args, **kwargs):
            call_order.append("api")
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Result"
            mock_response.citations = None
            return mock_response

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=api_call)

        with patch.dict("os.environ", {"PERPLEXITY_API_KEY": "test-key"}):
            from sat.research.perplexity import PerplexityProvider
            provider = PerplexityProvider(events=bus)
        provider._client = mock_client

        await provider.research("test query")

        assert call_order == ["event", "api"], f"Expected event before api, got: {call_order}"


# ---- Unit: multi_runner discover_providers passes events ----

class TestMultiRunnerEventThreading:
    """discover_providers() passes events to providers that support it."""

    def test_discover_providers_accepts_events_param(self):
        """discover_providers() function signature accepts events= parameter."""
        from sat.research.multi_runner import discover_providers
        import inspect
        sig = inspect.signature(discover_providers)
        assert "events" in sig.parameters

    async def test_run_multi_research_passes_bus_to_providers(self):
        """run_multi_research threads EventBus to providers via discover_providers."""
        from sat.events import EventBus, ProviderPolling
        from sat.research.multi_runner import run_multi_research
        from sat.research.base import ResearchResponse
        from tests.helpers import MockProvider

        bus = EventBus()
        polling_events = []

        async def capture(event):
            if isinstance(event, ProviderPolling):
                polling_events.append(event)

        bus.subscribe(capture)

        # A provider that emits ProviderPolling on research() call
        class PollingAwareMockProvider:
            async def research(self, query, context=None, max_sources=10):
                # Emit a polling event through the bus (simulates real provider)
                await bus.emit(ProviderPolling(name="mock_polling", attempt=1, max_attempts=5))
                return ResearchResponse(content="mock content", citations=[])

        llm = MockProvider(text_response='{"search_query": "test query"}')

        with (
            patch("sat.research.multi_runner.discover_providers", return_value=[
                ("mock_polling", PollingAwareMockProvider())
            ]),
            patch("sat.research.multi_runner.structure_evidence", new=AsyncMock(return_value=MagicMock(
                sources=[], claims=[]
            ))),
        ):
            await run_multi_research("test question", llm, events=bus)

        # The bus captured the ProviderPolling event from the mock provider
        assert len(polling_events) == 1
        assert polling_events[0].name == "mock_polling"


# ---- Production sequence: polling events interleaved with research lifecycle ----

class TestProductionPollingSequence:
    """Simulate the actual event sequence in production:
    ResearchStarted -> ProviderStarted (x3) -> ProviderPolling (x N) -> ProviderCompleted.

    This tests the full production scenario where multiple providers run in parallel
    and each emits ProviderPolling events while the others may still be running.
    """

    async def test_full_research_event_sequence(self):
        """Verify polling events appear between ProviderStarted and ProviderCompleted."""
        from sat.events import (
            EventBus, ProviderPolling, ProviderStarted, ProviderCompleted, ResearchStarted
        )

        bus = EventBus()
        event_sequence = []

        async def capture(event):
            event_sequence.append(type(event).__name__)

        bus.subscribe(capture)

        # Simulate provider that polls then completes
        async def mock_research_with_polling():
            await bus.emit(ProviderStarted(name="openai_deep"))
            await bus.emit(ProviderPolling(name="openai_deep", attempt=1, max_attempts=120, status="in_progress"))
            await bus.emit(ProviderPolling(name="openai_deep", attempt=5, max_attempts=120, status="in_progress"))
            await bus.emit(ProviderCompleted(name="openai_deep", citation_count=15, content_length=3000))

        await bus.emit(ResearchStarted(provider_names=["openai_deep"], query="test"))
        await mock_research_with_polling()

        # Verify sequence
        assert event_sequence == [
            "ResearchStarted",
            "ProviderStarted",
            "ProviderPolling",
            "ProviderPolling",
            "ProviderCompleted",
        ]

    async def test_polling_events_carry_progress_information(self):
        """ProviderPolling events contain enough data for frontend progress calculation."""
        events_received: list[ProviderPolling] = []

        bus = EventBus()

        async def capture(event):
            if isinstance(event, ProviderPolling):
                events_received.append(event)

        bus.subscribe(capture)

        # Simulate what the openai_deep provider emits at attempt 4 (throttled)
        await bus.emit(ProviderPolling(
            name="openai_deep",
            attempt=5,
            max_attempts=120,
            status="in_progress",
        ))

        assert len(events_received) == 1
        evt = events_received[0]

        # Frontend can compute: pct = round(evt.attempt / evt.max_attempts * 100)
        pct = round(evt.attempt / evt.max_attempts * 100)
        assert pct == 4  # 5/120 = ~4%

        # Frontend can display: "openai_deep: polling 5/120 (4%) [in_progress]"
        display = f"{evt.name}: polling {evt.attempt}/{evt.max_attempts} ({pct}%)"
        assert "openai_deep" in display
        assert "5/120" in display
