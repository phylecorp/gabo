"""Simple in-memory sliding-window rate limiter for API endpoints.

@decision DEC-SEC-004
@title In-memory sliding-window rate limiter with no external dependencies
@status accepted
@rationale SAT is a single-process desktop application — no Redis or shared
state is needed. A simple per-key counter with a 60-second sliding window is
sufficient to prevent abuse of expensive endpoints (LLM calls, evidence gather).
The clock is injectable for deterministic testing without patching time.time.
Thread-safety is not a concern for the asyncio event loop context; if this is
ever used from threads, add a threading.Lock around _windows.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable


class RequestRateLimiter:
    """Sliding-window rate limiter keyed by an arbitrary string.

    Each key gets an independent counter. Requests within the current
    60-second window are counted; once the window expires (the oldest
    request is more than ``window_seconds`` ago) the counter resets.

    Args:
        max_per_minute: Maximum allowed requests per 60-second window per key.
        window_seconds: Length of the sliding window in seconds. Default 60.
        clock: Callable returning the current time as a float (seconds since
               epoch). Injectable for testing without patching ``time.time``.
    """

    def __init__(
        self,
        max_per_minute: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._max = max_per_minute
        self._window = window_seconds
        self._clock: Callable[[], float] = clock if clock is not None else time.time
        # key -> list of timestamps of requests within the current window
        self._windows: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Return True if the request for *key* is within the rate limit.

        Advances the window by dropping timestamps older than ``window_seconds``,
        then checks whether the count is below the limit. If allowed, records the
        current timestamp. This method is idempotent for the same timestamp only
        when the window is full — callers must not retry without checking.
        """
        now = self._clock()
        cutoff = now - self._window

        # Drop timestamps that fell outside the window
        self._windows[key] = [t for t in self._windows[key] if t > cutoff]

        if len(self._windows[key]) >= self._max:
            return False

        self._windows[key].append(now)
        return True
