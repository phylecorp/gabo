"""Live integration tests for the Anthropic provider against real APIs.

@decision DEC-TEST-LIVE-001
@title Real-API integration tests deselected by default via -m integration
@status accepted
@rationale See tests/integration/conftest.py for full rationale. This module
exercises the Anthropic tool_use structured output path with both free-text
generation and schema-validated output using claude-haiku-4-5-20251001.

Run with:
    pytest -m integration tests/integration/test_anthropic_live.py
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from sat.providers.base import LLMMessage

SIMPLE_MESSAGES = [
    LLMMessage(
        role="user",
        content="Analyze the following: The sky is blue because of Rayleigh scattering.",
    )
]
SYSTEM_PROMPT = "You are a helpful analyst."


class SimpleAnalysis(BaseModel):
    """Minimal structured output schema for integration tests."""

    title: str
    points: list[str]
    confidence: str = "Medium"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anthropic_generate(anthropic_provider):
    """Free-text generation via Anthropic Messages API."""
    result = await anthropic_provider.generate(SYSTEM_PROMPT, SIMPLE_MESSAGES)
    assert result.text, "Expected non-empty text response"
    assert result.usage.input_tokens > 0, "Expected non-zero input token count"
    assert result.usage.output_tokens > 0, "Expected non-zero output token count"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_anthropic_generate_structured(anthropic_provider):
    """Structured output via Anthropic tool_use path."""
    result = await anthropic_provider.generate_structured(
        SYSTEM_PROMPT, SIMPLE_MESSAGES, output_schema=SimpleAnalysis
    )
    assert isinstance(result, SimpleAnalysis), f"Expected SimpleAnalysis, got {type(result)}"
    assert result.title, "Expected non-empty title"
    assert len(result.points) > 0, "Expected at least one point"
