"""Shared test fixtures."""

from __future__ import annotations

import pytest

from tests.helpers import MockProvider

__all__ = ["MockProvider"]


@pytest.fixture
def mock_provider():
    """Return a MockProvider factory."""
    return MockProvider
