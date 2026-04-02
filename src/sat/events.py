"""Pipeline progress events for real-time visibility.

@decision DEC-EVENTS-001
@title Lightweight async event system for pipeline progress
@status accepted
@rationale Type safety without framework overhead; async matches existing pipeline.
Fire-and-forget handlers — errors logged, never propagated to callers.
Typed dataclass events make it trivial to add new event types without
modifying existing handlers. NullBus provides a zero-overhead no-op path
when no handlers are registered, avoiding the cost of iterating an empty list.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


# --- Event types ---


@dataclass
class PipelineEvent:
    """Base class for all pipeline events."""

    pass


@dataclass
class ResearchStarted(PipelineEvent):
    """Emitted when the research phase begins."""

    provider_names: list[str]
    query: str = ""


@dataclass
class ProviderStarted(PipelineEvent):
    """Emitted when a single research provider begins work."""

    name: str


@dataclass
class ProviderCompleted(PipelineEvent):
    """Emitted when a single research provider returns results."""

    name: str
    citation_count: int
    content_length: int = 0


@dataclass
class ProviderFailed(PipelineEvent):
    """Emitted when a single research provider fails."""

    name: str
    error: str
    transient: bool = False


@dataclass
class ResearchCompleted(PipelineEvent):
    """Emitted when all research is done and evidence is structured."""

    source_count: int
    claim_count: int
    provider_label: str = ""


@dataclass
class StageStarted(PipelineEvent):
    """Emitted when a pipeline stage begins (technique, adversarial step, synthesis)."""

    stage: str
    technique_id: str = ""
    detail: str = ""


@dataclass
class StageCompleted(PipelineEvent):
    """Emitted when a pipeline stage finishes."""

    stage: str
    technique_id: str = ""
    detail: str = ""
    duration_secs: float = 0.0


@dataclass
class ArtifactWritten(PipelineEvent):
    """Emitted when an artifact file is written to disk."""

    path: str
    technique_id: str = ""
    category: str = ""


@dataclass
class EvidenceGatheringStarted(PipelineEvent):
    """Emitted when evidence gathering begins."""

    session_id: str
    has_evidence: bool = False
    research_enabled: bool = False
    decomposition_enabled: bool = False


@dataclass
class EvidenceGatheringCompleted(PipelineEvent):
    """Emitted when evidence gathering finishes."""

    session_id: str
    item_count: int = 0
    source_count: int = 0
    gap_count: int = 0


@dataclass
class ProviderPolling(PipelineEvent):
    """Emitted during research provider polling to signal liveness.

    @decision DEC-RESEARCH-015
    @title ProviderPolling events for liveness feedback during long polling
    @status accepted
    @rationale Deep research providers (OpenAI, Gemini) can poll for 20+ minutes.
    The frontend was frozen showing only a timer. ProviderPolling events emitted
    every Nth poll attempt give the frontend real-time liveness signals without
    flooding the event log. Perplexity (single blocking call) emits one event
    before the API call starts so the frontend knows it's alive. The event carries
    attempt/max_attempts for percentage calculation and status for server-side state.
    """

    name: str         # provider name (e.g., "openai_deep", "gemini_deep", "perplexity")
    attempt: int      # current poll attempt (1-based)
    max_attempts: int # total max poll attempts
    status: str = "" # server-side status if available (e.g., "in_progress")


# --- EventBus ---

EventHandler = Callable[[PipelineEvent], Awaitable[None]]


class EventBus:
    """Simple async event bus. Handlers are fire-and-forget — errors are logged, not raised."""

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def emit(self, event: PipelineEvent) -> None:
        for handler in list(self._handlers):
            try:
                await handler(event)
            except Exception:
                logger.warning("Event handler error for %s", type(event).__name__, exc_info=True)


class _NullBus(EventBus):
    """No-op event bus for when no handlers are registered."""

    async def emit(self, event: PipelineEvent) -> None:
        pass

    def subscribe(self, handler: EventHandler) -> None:
        pass


NullBus = _NullBus()
