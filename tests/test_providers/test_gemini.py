"""Tests for Gemini provider implementation.

@decision DEC-TEST-002: Mock external Gemini API for provider tests.
@mock-exempt: External HTTP API - mocking google.genai.Client to avoid real API calls.
Tests verify protocol compliance, message formatting, and retry logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from sat.config import ProviderConfig
from sat.providers.base import LLMMessage, LLMProvider
from sat.providers.gemini import GeminiProvider, _prepare_schema


class SampleOutputSchema(BaseModel):
    """Test schema for structured output."""

    title: str = Field(description="The title")
    count: int = Field(description="A count")


class SchemaWithDefaults(BaseModel):
    """Schema with default values that would fail Gemini."""

    name: str = ""
    tags: list[str] = Field(default_factory=list)
    count: int = 0


@pytest.fixture
def provider_config():
    """Create a test provider config."""
    return ProviderConfig(
        provider="gemini",
        model="gemini-2.5-pro",
        api_key="test-key",
    )


def test_provider_satisfies_protocol(provider_config):
    """Test that GeminiProvider satisfies the LLMProvider protocol."""
    provider = GeminiProvider(provider_config)
    assert isinstance(provider, LLMProvider)


def test_prepare_schema_removes_nested_defaults():
    """Test that _prepare_schema removes default keys from nested schemas."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "default": ""},
            "tags": {
                "type": "array",
                "default": [],
                "items": {"type": "string", "default": "tag"},
            },
        },
        "$defs": {
            "SubModel": {
                "type": "object",
                "default": {},
                "properties": {
                    "value": {"type": "integer", "default": 0},
                },
            },
        },
    }
    result = _prepare_schema(schema)
    # Top-level properties should not have defaults
    assert "default" not in result["properties"]["name"]
    assert "default" not in result["properties"]["tags"]
    # Nested items should not have defaults
    assert "default" not in result["properties"]["tags"]["items"]
    # $defs should not have defaults
    assert "default" not in result["$defs"]["SubModel"]
    assert "default" not in result["$defs"]["SubModel"]["properties"]["value"]
    # Non-default keys should be preserved
    assert result["properties"]["name"]["type"] == "string"
    assert result["type"] == "object"


def test_prepare_schema_handles_pydantic_model_with_defaults():
    """Test that model_json_schema + _prepare_schema produces a clean schema."""
    schema = SchemaWithDefaults.model_json_schema()
    result = _prepare_schema(schema)
    assert "default" not in result["properties"]["name"]
    assert "default" not in result["properties"]["tags"]
    assert "default" not in result["properties"]["count"]


@pytest.mark.asyncio
async def test_generate(provider_config):
    """Test basic text generation."""
    provider = GeminiProvider(provider_config)

    # Mock the Gemini client response
    mock_response = MagicMock()
    mock_response.text = "Test response"
    mock_response.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=20)

    mock_generate = AsyncMock(return_value=mock_response)

    with patch.object(provider._client.aio.models, "generate_content", new=mock_generate):
        result = await provider.generate(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Hello")],
        )

    assert result.text == "Test response"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 20


@pytest.mark.asyncio
async def test_generate_structured(provider_config):
    """Test structured output generation passes a dict schema (defaults stripped)."""
    provider = GeminiProvider(provider_config)

    # Mock the Gemini client response
    mock_response = MagicMock()
    mock_response.text = '{"title": "Test", "count": 42}'
    mock_response.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=20)

    mock_generate = AsyncMock(return_value=mock_response)

    with patch.object(provider._client.aio.models, "generate_content", new=mock_generate):
        result = await provider.generate_structured(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Generate structured data")],
            output_schema=SampleOutputSchema,
        )

    # Verify the config included response_schema as a dict (not the raw Pydantic class)
    # and that response_mime_type is set correctly
    call_kwargs = mock_generate.call_args.kwargs
    assert call_kwargs["config"].response_mime_type == "application/json"
    schema = call_kwargs["config"].response_schema
    assert isinstance(schema, dict), (
        f"response_schema must be a dict (defaults stripped), got {type(schema)}"
    )
    # Verify no 'default' keys leaked through
    import json

    schema_str = json.dumps(schema)
    assert '"default"' not in schema_str, "response_schema must not contain any 'default' keys"

    assert isinstance(result, SampleOutputSchema)
    assert result.title == "Test"
    assert result.count == 42


@pytest.mark.asyncio
async def test_generate_structured_retry_on_validation_failure(provider_config):
    """Test that structured output retries once on validation failure."""
    provider = GeminiProvider(provider_config)

    # First call returns invalid JSON (missing count field)
    mock_response_invalid = MagicMock()
    mock_response_invalid.text = '{"title": "Test"}'
    mock_response_invalid.usage_metadata = MagicMock(
        prompt_token_count=10, candidates_token_count=20
    )

    # Second call returns valid JSON
    mock_response_valid = MagicMock()
    mock_response_valid.text = '{"title": "Test", "count": 42}'
    mock_response_valid.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=20)

    mock_generate = AsyncMock(side_effect=[mock_response_invalid, mock_response_valid])

    with patch.object(provider._client.aio.models, "generate_content", new=mock_generate):
        result = await provider.generate_structured(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Generate structured data")],
            output_schema=SampleOutputSchema,
        )

    # Should have been called twice (initial + retry)
    assert mock_generate.call_count == 2
    assert isinstance(result, SampleOutputSchema)
    assert result.title == "Test"
    assert result.count == 42


@pytest.mark.asyncio
async def test_generate_handles_missing_usage_metadata(provider_config):
    """Test that generate handles missing usage metadata gracefully."""
    provider = GeminiProvider(provider_config)

    # Mock response without usage_metadata
    mock_response = MagicMock()
    mock_response.text = "Test response"
    del mock_response.usage_metadata  # Remove the attribute

    mock_generate = AsyncMock(return_value=mock_response)

    with patch.object(provider._client.aio.models, "generate_content", new=mock_generate):
        result = await provider.generate(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Hello")],
        )

    assert result.text == "Test response"
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0
