"""Shared fixtures for integration tests against real LLM provider APIs.

@decision DEC-TEST-LIVE-001: Integration test suite isolated under tests/integration/ with pytest marker.
@title Real-API integration tests deselected by default via -m 'not integration'
@status accepted
@rationale Provider bugs (wrong schema format, wrong API route) cannot be caught by mocks.
A dedicated integration suite with the 'integration' marker lets CI skip real API calls by
default while allowing explicit runs via `pytest -m integration`. Each fixture skips when
the required API key or package is absent, so the suite is safe to collect without credentials.

Integration tests are excluded from default pytest runs. To run them:
    pytest -m integration

Each provider fixture skips automatically if the required API key env var
is not set, so the full suite can be collected without all keys present.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from sat.config import ProviderConfig
from sat.providers.registry import create_provider

# Load .env at module import time so env vars are available during fixture setup.
load_dotenv()


# ---------------------------------------------------------------------------
# Provider fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def openai_provider():
    """OpenAI provider using gpt-4o-mini.

    Skips if the openai package is not installed or OPENAI_API_KEY is unset.
    """
    pytest.importorskip("openai")
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    config = ProviderConfig(provider="openai", model="gpt-4o-mini")
    return create_provider(config)


@pytest.fixture
def openai_reasoning_provider():
    """OpenAI reasoning provider using o3-mini (routes through Responses API).

    Skips if the openai package is not installed or OPENAI_API_KEY is unset.
    """
    pytest.importorskip("openai")
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")
    config = ProviderConfig(provider="openai", model="o3-mini")
    return create_provider(config)


@pytest.fixture
def anthropic_provider():
    """Anthropic provider using claude-haiku-4-5-20251001.

    Skips if the anthropic package is not installed or ANTHROPIC_API_KEY is unset.
    """
    pytest.importorskip("anthropic")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    config = ProviderConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    return create_provider(config)


@pytest.fixture
def gemini_provider():
    """Gemini provider using gemini-2.5-flash.

    Skips if the google-genai package is not installed or GEMINI_API_KEY is unset.
    """
    pytest.importorskip("google.genai")
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")
    config = ProviderConfig(provider="gemini", model="gemini-2.5-flash")
    return create_provider(config)
