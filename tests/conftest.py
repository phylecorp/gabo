"""Shared test fixtures."""

from __future__ import annotations

import pytest

from tests.helpers import MockProvider

__all__ = ["MockProvider"]


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """Disable auth for all tests; test_auth.py re-enables where needed."""
    monkeypatch.setenv("SAT_DISABLE_AUTH", "1")


@pytest.fixture
def mock_provider():
    """Return a MockProvider factory."""
    return MockProvider
