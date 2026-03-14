"""Tests for sat.errors — shared transient error classification.

@decision DEC-ERR-002: Tests validate base set, extensibility via extra_names,
TimeoutError isinstance check, and that programming errors are not transient.
Tests are written against the real implementation — no mocks needed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sat.errors import is_transient_error


# ---------------------------------------------------------------------------
# Base transient names
# ---------------------------------------------------------------------------


class TestIsTransientErrorBaseNames:
    """All names in _BASE_TRANSIENT_NAMES return True."""

    @pytest.mark.parametrize(
        "class_name",
        [
            "OverloadedError",
            "RateLimitError",
            "InternalServerError",
            "APITimeoutError",
            "APIConnectionError",
            "ServiceUnavailableError",
            "ServerError",
        ],
    )
    def test_base_name_returns_true(self, class_name: str) -> None:
        """Every class name in the base set should be classified as transient."""
        exc_class = type(class_name, (Exception,), {})
        exc = exc_class("transient failure")
        assert is_transient_error(exc) is True


# ---------------------------------------------------------------------------
# extra_names parameter
# ---------------------------------------------------------------------------


class TestIsTransientErrorExtraNames:
    """extra_names allows callers to extend the base set."""

    def test_extra_name_returns_true(self) -> None:
        """A name in extra_names should be classified as transient."""
        exc_class = type("ResearchRequestFailed", (Exception,), {})
        exc = exc_class("research failed")
        extras: frozenset[str] = frozenset({"ResearchRequestFailed"})
        assert is_transient_error(exc, extras) is True

    def test_extra_name_not_transient_without_extra(self) -> None:
        """Without extra_names, a non-base name should return False."""
        exc_class = type("ResearchRequestFailed", (Exception,), {})
        exc = exc_class("research failed")
        assert is_transient_error(exc) is False

    def test_multiple_extra_names(self) -> None:
        """Multiple names can be passed in extra_names."""
        for name in ("TimeoutException", "ConnectError"):
            exc_class = type(name, (Exception,), {})
            exc = exc_class("connection issue")
            extras: frozenset[str] = frozenset({"TimeoutException", "ConnectError"})
            assert is_transient_error(exc, extras) is True

    def test_none_extra_names_uses_base_only(self) -> None:
        """Passing None as extra_names behaves identically to no extra_names."""
        exc_class = type("OverloadedError", (Exception,), {})
        exc = exc_class("overloaded")
        assert is_transient_error(exc, None) is True


# ---------------------------------------------------------------------------
# TimeoutError isinstance check
# ---------------------------------------------------------------------------


class TestIsTransientErrorTimeoutError:
    """TimeoutError (and subclasses) are transient via isinstance check."""

    def test_timeout_error_returns_true(self) -> None:
        """Built-in TimeoutError is transient."""
        assert is_transient_error(TimeoutError("timed out")) is True

    def test_asyncio_timeout_error_returns_true(self) -> None:
        """asyncio.TimeoutError is a subclass of TimeoutError — must be transient."""
        import asyncio

        exc = asyncio.TimeoutError()
        assert is_transient_error(exc) is True

    def test_timeout_error_subclass_returns_true(self) -> None:
        """Custom subclasses of TimeoutError are transient via isinstance."""
        exc_class = type("MyTimeoutError", (TimeoutError,), {})
        exc = exc_class("custom timeout")
        assert is_transient_error(exc) is True


# ---------------------------------------------------------------------------
# Programming errors are NOT transient
# ---------------------------------------------------------------------------


class TestIsTransientErrorProgrammingErrors:
    """TypeError, AttributeError, etc. are not transient — they should surface."""

    @pytest.mark.parametrize(
        "exc",
        [
            ValueError("bad value"),
            RuntimeError("runtime failure"),
            KeyError("missing key"),
            TypeError("type mismatch"),
            AttributeError("no attribute"),
            NotImplementedError("not implemented"),
            OSError("os error"),
        ],
    )
    def test_common_errors_return_false(self, exc: Exception) -> None:
        """Common non-transient exceptions should return False."""
        assert is_transient_error(exc) is False

    def test_validation_error_is_not_transient(self) -> None:
        """ValidationError is a logic/schema error — never transient."""
        from pydantic import BaseModel

        class Dummy(BaseModel):
            x: int

        try:
            Dummy(x="not-an-int")  # type: ignore[arg-type]
        except ValidationError as ve:
            assert is_transient_error(ve) is False

    def test_subclass_with_different_name_not_transient(self) -> None:
        """A subclass of a transient error uses its OWN name, not parent's."""
        exc_class = type("MyRateLimitError", (Exception,), {})
        exc = exc_class("rate limited")
        assert is_transient_error(exc) is False
