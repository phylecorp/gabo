"""Shared error classification utilities.

@decision DEC-ERR-001
@title Central is_transient_error() replaces duplicated _is_transient / _is_research_transient
@status accepted
@rationale Two functions with 80% overlapping logic were maintained independently:
pipeline.py._is_transient (7 error names) and multi_runner.py._is_research_transient
(6 error names + TimeoutError isinstance check). A shared base set +
caller-extensible extra names ensures consistency while allowing domain-specific
checks (e.g., ResearchRequestFailed for research). The extra_names parameter lets
callers extend the base set without modifying the shared utility.
"""

from __future__ import annotations

_BASE_TRANSIENT_NAMES: frozenset[str] = frozenset(
    {
        "OverloadedError",
        "RateLimitError",
        "InternalServerError",
        "APITimeoutError",
        "APIConnectionError",
        "ServiceUnavailableError",
        "ServerError",
    }
)


def is_transient_error(exc: Exception, extra_names: frozenset[str] | None = None) -> bool:
    """Check if an exception is a transient error worth retrying.

    Args:
        exc: The exception to classify.
        extra_names: Additional exception class names to treat as transient,
            beyond the base set (e.g., research-specific error types).

    Returns:
        True if the exception is transient and a retry might succeed.
    """
    if isinstance(exc, TimeoutError):
        return True
    names = _BASE_TRANSIENT_NAMES | (extra_names or frozenset())
    return type(exc).__name__ in names
