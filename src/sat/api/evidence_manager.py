"""Evidence session management — tracks active evidence gathering sessions.

@decision DEC-API-007
@title EvidenceSessionManager mirrors RunManager pattern for evidence gathering
@status accepted
@rationale Evidence gathering is a separate lifecycle from analysis. Sessions are created
on gather request, populated asynchronously, then consumed by the analyze endpoint.
The 1-hour TTL prevents stale sessions from accumulating.
"""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

from sat.events import EventBus, PipelineEvent
from sat.models.evidence import EvidencePool

# Session TTL: 1 hour in seconds
_SESSION_TTL_SECS = 3600


class EvidenceSession:
    """Holds all live state for a single evidence gathering session.

    Bridges EventBus events to connected WebSocket clients and maintains
    an append-only events_log for late-joining clients (catch-up replay).
    The pool is populated once gather_evidence() completes.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.pool: EvidencePool | None = None
        self.bus = EventBus()
        self.task: asyncio.Task | None = None
        self.ws_clients: list[WebSocket] = []
        self.events_log: list[dict[str, Any]] = []
        self.status: str = "gathering"  # gathering, ready, failed
        self.error: str | None = None
        self.created_at: datetime = datetime.now(UTC)
        # Sources provided at gather time; carried forward to the analyze step
        # so evidence ingestion runs even when CuratedAnalysisRequest omits them.
        self.evidence_sources: list[str] | None = None
        # Name label provided at gather time; carried forward to the analyze step.
        self.name: str | None = None

        # Subscribe our handler to bridge events to WS clients
        self.bus.subscribe(self._handle_event)

    async def _handle_event(self, event: PipelineEvent) -> None:
        """Serialize event to dict, append to log, and broadcast to all WS clients."""
        event_dict: dict[str, Any] = {
            "type": type(event).__name__,
            "data": dataclasses.asdict(event),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.events_log.append(event_dict)

        # Broadcast to all connected WS clients; prune disconnected ones
        disconnected: list[WebSocket] = []
        for ws in list(self.ws_clients):
            try:
                await ws.send_json(event_dict)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in self.ws_clients:
                self.ws_clients.remove(ws)


class EvidenceSessionManager:
    """In-process registry of EvidenceSession instances.

    Thread-safety note: all access happens from the single asyncio event loop
    that FastAPI/uvicorn runs, so no locking is needed.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, EvidenceSession] = {}

    def create_session(self) -> EvidenceSession:
        """Create a new EvidenceSession, register it, and return it."""
        session_id = uuid.uuid4().hex[:12]
        session = EvidenceSession(session_id)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> EvidenceSession | None:
        """Look up a session by ID. Returns None if not found."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[EvidenceSession]:
        """Return all sessions in insertion order."""
        return list(self._sessions.values())

    def cleanup_stale(self) -> int:
        """Remove sessions older than the TTL. Returns count removed."""
        now = datetime.now(UTC)
        stale = [
            sid
            for sid, session in self._sessions.items()
            if (now - session.created_at).total_seconds() > _SESSION_TTL_SECS
        ]
        for sid in stale:
            del self._sessions[sid]
        return len(stale)
