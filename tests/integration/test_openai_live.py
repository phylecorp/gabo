"""Live integration tests for the OpenAI provider against real APIs.

@decision DEC-TEST-LIVE-001
@title Real-API integration tests deselected by default via -m integration
@status accepted
@rationale See tests/integration/conftest.py for full rationale. This module
covers both the Chat Completions path (gpt-4o-mini) and the Responses API
path (o3-mini / reasoning models), including the structured output variant
that would have caught the additionalProperties: false schema bug.

Run with:
    pytest -m integration tests/integration/test_openai_live.py
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from sat.models.adversarial import CritiqueResult
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
async def test_openai_generate(openai_provider):
    """Free-text generation via Chat Completions API (gpt-4o-mini)."""
    result = await openai_provider.generate(SYSTEM_PROMPT, SIMPLE_MESSAGES)
    assert result.text, "Expected non-empty text response"
    assert result.usage.input_tokens > 0, "Expected non-zero input token count"
    assert result.usage.output_tokens > 0, "Expected non-zero output token count"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_generate_structured(openai_provider):
    """Structured output via Chat Completions API (gpt-4o-mini)."""
    result = await openai_provider.generate_structured(
        SYSTEM_PROMPT, SIMPLE_MESSAGES, output_schema=SimpleAnalysis
    )
    assert isinstance(result, SimpleAnalysis), f"Expected SimpleAnalysis, got {type(result)}"
    assert result.title, "Expected non-empty title"
    assert len(result.points) > 0, "Expected at least one point"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_responses_generate(openai_reasoning_provider):
    """Free-text generation via Responses API (o3-mini reasoning model)."""
    result = await openai_reasoning_provider.generate(SYSTEM_PROMPT, SIMPLE_MESSAGES)
    assert result.text, "Expected non-empty text response"
    assert result.usage.input_tokens > 0, "Expected non-zero input token count"
    assert result.usage.output_tokens > 0, "Expected non-zero output token count"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_responses_generate_structured(openai_reasoning_provider):
    """Structured output via Responses API (o3-mini).

    This is the regression test that would have caught the
    additionalProperties: false schema bug in the Responses API path.
    """
    result = await openai_reasoning_provider.generate_structured(
        SYSTEM_PROMPT, SIMPLE_MESSAGES, output_schema=SimpleAnalysis
    )
    assert isinstance(result, SimpleAnalysis), f"Expected SimpleAnalysis, got {type(result)}"
    assert result.title, "Expected non-empty title"
    assert len(result.points) > 0, "Expected at least one point"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_openai_responses_structured_with_nested_schema(openai_reasoning_provider):
    """Structured output with a complex nested schema via Responses API (o3-mini).

    CritiqueResult has nested Challenge objects and multiple list fields.
    This exercises the strict-schema compliance path for complex schemas.
    """
    result = await openai_reasoning_provider.generate_structured(
        SYSTEM_PROMPT, SIMPLE_MESSAGES, output_schema=CritiqueResult
    )
    assert isinstance(result, CritiqueResult), f"Expected CritiqueResult, got {type(result)}"
