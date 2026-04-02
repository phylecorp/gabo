"""Core run state management — tracks active analysis runs and bridges events to WebSocket clients.

@decision DEC-API-002
@title RunManager owns the in-process run registry; filesystem provides persistence
@status accepted
@rationale The RunManager is the authoritative source for *active* runs. Completed
runs are persisted to disk via the pipeline's manifest.json. The runs route reads
both sources (active dict + filesystem scan) so the frontend sees a unified view.
Keeping active state in-process avoids a Redis/DB dependency for the desktop use
case where there is exactly one server process and runs finish within the session.

@decision DEC-CONCURRENCY-002
@title RunManager concurrency cap with FIFO queue — no external scheduler needed
@status accepted
@rationale Desktop use case has a single server process with shared API key budget.
Allowing unlimited concurrent runs causes rate-limit cascade failures. A simple
in-process cap (default 2) with a FIFO deque queue satisfies the requirement without
Redis, Celery, or any external dependency. The queue is purely in-process because
the RunManager already owns all live run state. On completion, _on_run_finished()
pops the oldest queued run and promotes it to running — O(1) dequeue.
Cancelled queued runs are removed by O(n) linear scan (queue depth is tiny, ≤ tens).
"""

from __future__ import annotations

import asyncio
import collections
import dataclasses
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

from sat.config import AnalysisConfig
from sat.events import EventBus, PipelineEvent, StageCompleted


class ActiveRun:
    """Holds all live state for a single in-flight or completed analysis run.

    Bridges EventBus events to connected WebSocket clients and maintains
    an append-only events_log for late-joining clients (catch-up replay).

    Status lifecycle:
        "queued"    → run created but waiting for a concurrency slot
        "running"   → pipeline is executing
        "completed" → pipeline finished successfully
        "failed"    → pipeline raised an unhandled exception
        "cancelled" → run was cancelled before or during execution
    """

    def __init__(self, run_id: str, config: AnalysisConfig) -> None:
        self.run_id = run_id
        self.config = config
        self.name: str | None = config.name
        self.bus = EventBus()
        self.task: asyncio.Task | None = None
        self.ws_clients: list[WebSocket] = []
        self.events_log: list[dict[str, Any]] = []
        self.status: str = "running"  # running, queued, completed, failed, cancelled
        self.error: str | None = None
        self.output_dir: str | None = None
        # Accumulates technique IDs as StageCompleted(stage="analysis") events arrive.
        # Read by GET /api/runs/{run_id} to return real progress for in-flight runs
        # rather than the hardcoded [] that was previously returned (issue #14).
        self.techniques_completed: list[str] = []

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

        # Track analysis technique completions for live dashboard progress (issue #14).
        # Ignore empty technique_id — that signals a pipeline-level stage, not a technique.
        if isinstance(event, StageCompleted) and event.stage == "analysis" and event.technique_id:
            self.techniques_completed.append(event.technique_id)

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


class RunManager:
    """In-process registry of ActiveRun instances with a concurrency cap and queue.

    Thread-safety note: all access happens from the single asyncio event loop
    that FastAPI/uvicorn runs, so no locking is needed.

    Concurrency model:
        - max_concurrent running tasks at a time (default: 2)
        - Additional tasks are queued in FIFO order
        - On each run completion, _on_run_finished() promotes the next queued run
    """

    def __init__(self, max_concurrent: int = 2) -> None:
        self._runs: dict[str, ActiveRun] = {}
        self._max_concurrent = max_concurrent
        # Stores execute callables for queued runs — (run_id, execute_fn) pairs
        self._pending_queue: collections.deque[tuple[str, Callable[[], Coroutine]]] = (
            collections.deque()
        )
        # Track the number of actively running tasks (avoids scanning all runs)
        self._active_count: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def running_count(self) -> int:
        """Number of tasks currently executing (promoted by start_or_queue)."""
        return self._active_count

    @property
    def concurrency_status(self) -> dict[str, int]:
        """Snapshot of concurrency state."""
        return {
            "running_count": self.running_count,
            "queued_count": sum(1 for r in self._runs.values() if r.status == "queued"),
            "max_concurrent": self._max_concurrent,
        }

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_run(self, config: AnalysisConfig) -> ActiveRun:
        """Create a new ActiveRun, register it, and return it.

        The run is created with status="running" by default. Callers that
        want queuing behaviour should call start_or_queue() after creation.
        """
        run_id = uuid.uuid4().hex[:12]
        run = ActiveRun(run_id, config)
        self._runs[run_id] = run
        return run

    def get_run(self, run_id: str) -> ActiveRun | None:
        """Look up a run by ID. Returns None if not found."""
        return self._runs.get(run_id)

    def list_active_runs(self) -> list[ActiveRun]:
        """Return all runs (running and completed) in insertion order."""
        return list(self._runs.values())

    def remove_run(self, run_id: str) -> bool:
        """Remove a run from the in-process registry.

        Returns True if the run was found and removed, False if not present.
        Does not touch the filesystem — the caller is responsible for that.
        """
        if run_id in self._runs:
            del self._runs[run_id]
            return True
        return False

    # ------------------------------------------------------------------
    # Concurrency management
    # ------------------------------------------------------------------

    def start_or_queue(
        self,
        run: ActiveRun,
        execute_fn: Callable[[], Coroutine],
    ) -> None:
        """Start *run* immediately if under cap; otherwise queue it.

        If under the concurrency cap, wraps execute_fn in a Task (via
        asyncio.create_task) and marks the run as "running". If at cap,
        marks the run as "queued" and stores it in _pending_queue for
        promotion by _on_run_finished().

        A "run_queued" event is broadcast when the run enters the queue so
        the frontend can update the run card to show queued state.
        A "run_started" event is broadcast when a queued run is promoted so
        the frontend can update the run card to show running state.
        """
        if self.running_count < self._max_concurrent:
            self._start_run(run, execute_fn)
        else:
            run.status = "queued"
            self._pending_queue.append((run.run_id, execute_fn))
            asyncio.create_task(
                self._broadcast_status(run, "run_queued", {"run_id": run.run_id})
            )

    def _start_run(
        self,
        run: ActiveRun,
        execute_fn: Callable[[], Coroutine],
    ) -> None:
        """Unconditionally start a run as a background task."""
        run.status = "running"
        self._active_count += 1

        async def _wrapper() -> None:
            try:
                await execute_fn()
            except asyncio.CancelledError:
                # Task was cancelled — status already set to "cancelled" by cancel_run()
                raise
            except Exception:
                # Execute fn raised — it should have set status to "failed" itself,
                # but if it didn't, we mark it here to ensure running_count decrements.
                if run.status == "running":
                    run.status = "failed"
                raise
            else:
                # Execute fn completed successfully — mark as completed if not already
                # changed (e.g. to "cancelled").
                if run.status == "running":
                    run.status = "completed"
            finally:
                self._active_count = max(0, self._active_count - 1)
                self._on_run_finished(run.run_id)

        run.task = asyncio.create_task(_wrapper())

    def _on_run_finished(self, run_id: str) -> None:
        """Called when a run completes or fails. Promotes the next queued run."""
        # Promote the oldest queued run if one exists
        while self._pending_queue:
            next_run_id, next_fn = self._pending_queue.popleft()
            next_run = self._runs.get(next_run_id)
            if next_run is None or next_run.status == "cancelled":
                # Run was removed or cancelled — skip and try the next one
                continue
            # Broadcast run_started before kicking off the task
            asyncio.create_task(
                self._broadcast_status(
                    next_run, "run_started", {"run_id": next_run.run_id}
                )
            )
            self._start_run(next_run, next_fn)
            break

        # Remove finished run from active registry — filesystem manifest is now
        # the sole source of truth for completed/failed runs.
        #
        # @decision DEC-API-002 (amendment)
        # Cancelled runs are intentionally kept in _runs because they have no
        # on-disk manifest to fall back to. Only "completed" and "failed" runs
        # have written a manifest.json before _on_run_finished is called.
        run = self._runs.get(run_id)
        if run and run.status in ("completed", "failed"):
            del self._runs[run_id]

    async def _broadcast_status(
        self, run: ActiveRun, event_type: str, data: dict[str, Any]
    ) -> None:
        """Broadcast a status event to all WS clients connected to *run*."""
        event_dict: dict[str, Any] = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        run.events_log.append(event_dict)
        disconnected: list[WebSocket] = []
        for ws in list(run.ws_clients):
            try:
                await ws.send_json(event_dict)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in run.ws_clients:
                run.ws_clients.remove(ws)

    def cancel_run(self, run_id: str) -> bool:
        """Cancel a queued or running run.

        - Queued: remove from queue, set status to "cancelled". Returns True.
        - Running: cancel the asyncio task, set status to "cancelled". Returns True.
        - Completed/failed/not found: return False (nothing to cancel).
        """
        run = self._runs.get(run_id)
        if run is None:
            return False

        if run.status == "queued":
            # Remove from queue — linear scan (queue depth is tiny)
            self._pending_queue = collections.deque(
                (rid, fn) for rid, fn in self._pending_queue if rid != run_id
            )
            run.status = "cancelled"
            return True

        if run.status == "running":
            run.status = "cancelled"
            if run.task is not None and not run.task.done():
                run.task.cancel()
            return True

        return False

    def queue_position(self, run_id: str) -> int | None:
        """Return the 0-based position of *run_id* in the pending queue.

        Returns None if the run is not currently queued.
        """
        for i, (rid, _) in enumerate(self._pending_queue):
            if rid == run_id:
                return i
        return None
