"""Tests for OpenAI provider implementation.

@decision DEC-TEST-001: Mock external OpenAI API for provider tests.
@mock-exempt: External HTTP API - mocking openai.AsyncOpenAI client to avoid real API calls.
Tests verify protocol compliance, message formatting, reasoning model handling, and retry logic.
Dual-path routing: reasoning models (explicit allowlist) use responses.create, others use
chat.completions.create with max_completion_tokens.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from sat.config import ProviderConfig
from sat.providers.base import LLMMessage, LLMProvider
from sat.providers.openai import OpenAIProvider, _prepare_strict_schema


class SampleOutputSchema(BaseModel):
    """Test schema for structured output."""

    title: str = Field(description="The title")
    count: int = Field(description="A count")


@pytest.fixture
def provider_config():
    """Create a test provider config."""
    return ProviderConfig(
        provider="openai",
        model="gpt-4",
        api_key="test-key",
    )


@pytest.fixture
def reasoning_provider_config():
    """Create a test provider config for reasoning models."""
    return ProviderConfig(
        provider="openai",
        model="o1-preview",
        api_key="test-key",
    )


@pytest.fixture
def o3_provider_config():
    """Create a test provider config for o3 reasoning models."""
    return ProviderConfig(provider="openai", model="o3", api_key="test-key")


def test_provider_satisfies_protocol(provider_config):
    """Test that OpenAIProvider satisfies the LLMProvider protocol."""
    provider = OpenAIProvider(provider_config)
    assert isinstance(provider, LLMProvider)


@pytest.mark.asyncio
async def test_generate(provider_config):
    """Test basic text generation."""
    provider = OpenAIProvider(provider_config)

    # Mock the OpenAI client
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

    mock_create = AsyncMock(return_value=mock_response)
    with patch.object(provider._client.chat.completions, "create", new=mock_create):
        result = await provider.generate(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Hello")],
        )

    # Verify max_completion_tokens (not max_tokens) was sent to the API
    call_kwargs = mock_create.call_args.kwargs
    assert "max_completion_tokens" in call_kwargs
    assert "max_tokens" not in call_kwargs

    assert result.text == "Test response"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 20


@pytest.mark.asyncio
async def test_generate_reasoning_model(o3_provider_config):
    """Test that reasoning models use responses.create with instructions and input."""
    provider = OpenAIProvider(o3_provider_config)

    mock_response = MagicMock()
    mock_response.output_text = "Reasoning response"
    mock_response.usage = MagicMock(input_tokens=10, output_tokens=20)

    mock_create = AsyncMock(return_value=mock_response)

    with patch.object(provider._client.responses, "create", new=mock_create):
        result = await provider.generate(
            system_prompt="You are a reasoning assistant",
            messages=[LLMMessage(role="user", content="Think deeply")],
        )

    # Verify the call was made correctly
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["model"] == "o3"
    # System prompt goes to instructions, not messages
    assert call_kwargs["instructions"] == "You are a reasoning assistant"
    # input is list of message dicts without system/developer message
    assert call_kwargs["input"] == [{"role": "user", "content": "Think deeply"}]
    # max_output_tokens instead of max_tokens
    assert "max_output_tokens" in call_kwargs
    # Verify temperature is not in kwargs
    assert "temperature" not in call_kwargs
    # store=False for privacy
    assert call_kwargs["store"] is False

    assert result.text == "Reasoning response"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 20


@pytest.mark.asyncio
async def test_generate_structured(provider_config):
    """Test structured output generation."""
    provider = OpenAIProvider(provider_config)

    # Mock the OpenAI client
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"title": "Test", "count": 42}'))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

    with patch.object(
        provider._client.chat.completions, "create", new=AsyncMock(return_value=mock_response)
    ):
        result = await provider.generate_structured(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Generate structured data")],
            output_schema=SampleOutputSchema,
        )

    assert isinstance(result, SampleOutputSchema)
    assert result.title == "Test"
    assert result.count == 42


@pytest.mark.asyncio
async def test_generate_structured_retry_on_validation_failure(provider_config):
    """Test that structured output retries once on validation failure."""
    provider = OpenAIProvider(provider_config)

    # First call returns invalid JSON
    mock_response_invalid = MagicMock()
    mock_response_invalid.choices = [
        MagicMock(message=MagicMock(content='{"title": "Test"}'))
    ]  # missing count
    mock_response_invalid.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

    # Second call returns valid JSON
    mock_response_valid = MagicMock()
    mock_response_valid.choices = [
        MagicMock(message=MagicMock(content='{"title": "Test", "count": 42}'))
    ]
    mock_response_valid.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

    mock_create = AsyncMock(side_effect=[mock_response_invalid, mock_response_valid])

    with patch.object(provider._client.chat.completions, "create", new=mock_create):
        result = await provider.generate_structured(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Generate structured data")],
            output_schema=SampleOutputSchema,
        )

    # Should have been called twice (initial + retry)
    assert mock_create.call_count == 2
    assert isinstance(result, SampleOutputSchema)
    assert result.title == "Test"
    assert result.count == 42


@pytest.mark.asyncio
async def test_generate_structured_reasoning_model(o3_provider_config):
    """Test structured output with reasoning models uses responses.create with text format."""
    provider = OpenAIProvider(o3_provider_config)

    mock_response = MagicMock()
    mock_response.output_text = '{"title": "Reasoning Test", "count": 99}'
    mock_response.usage = MagicMock(input_tokens=10, output_tokens=20)

    mock_create = AsyncMock(return_value=mock_response)

    with patch.object(provider._client.responses, "create", new=mock_create):
        result = await provider.generate_structured(
            system_prompt="You are a reasoning assistant",
            messages=[LLMMessage(role="user", content="Generate structured data")],
            output_schema=SampleOutputSchema,
        )

    # Verify temperature is omitted
    call_kwargs = mock_create.call_args.kwargs
    assert "temperature" not in call_kwargs
    # Verify text format config for structured output
    assert "text" in call_kwargs
    text_config = call_kwargs["text"]
    assert text_config["format"]["type"] == "json_schema"
    assert text_config["format"]["name"] == "SampleOutputSchema"
    assert text_config["format"]["strict"] is True
    # Verify instructions carries system prompt
    assert call_kwargs["instructions"] == "You are a reasoning assistant"
    # store=False for privacy
    assert call_kwargs["store"] is False

    assert isinstance(result, SampleOutputSchema)
    assert result.title == "Reasoning Test"
    assert result.count == 99


@pytest.mark.asyncio
async def test_generate_structured_retry_on_validation_failure_reasoning(o3_provider_config):
    """Test that structured output retries once on validation failure for reasoning models."""
    provider = OpenAIProvider(o3_provider_config)

    # First call returns invalid JSON (missing count)
    mock_response_invalid = MagicMock()
    mock_response_invalid.output_text = '{"title": "Test"}'
    mock_response_invalid.usage = MagicMock(input_tokens=10, output_tokens=20)

    # Second call returns valid JSON
    mock_response_valid = MagicMock()
    mock_response_valid.output_text = '{"title": "Test", "count": 42}'
    mock_response_valid.usage = MagicMock(input_tokens=10, output_tokens=20)

    mock_create = AsyncMock(side_effect=[mock_response_invalid, mock_response_valid])

    with patch.object(provider._client.responses, "create", new=mock_create):
        result = await provider.generate_structured(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Generate structured data")],
            output_schema=SampleOutputSchema,
        )

    # Should have been called twice (initial + retry)
    assert mock_create.call_count == 2
    assert isinstance(result, SampleOutputSchema)
    assert result.title == "Test"
    assert result.count == 42


def test_is_reasoning_model_detection():
    """Test that known allowlist models are reasoning; others (including o3-deep-research) are not."""
    reasoning_models = ["o1", "o1-mini", "o1-pro", "o3", "o3-mini", "o3-pro", "o4-mini"]
    non_reasoning_models = ["gpt-4o", "gpt-4", "gpt-3.5-turbo", "o3-deep-research", "o1-preview"]

    for model in reasoning_models:
        config = ProviderConfig(provider="openai", model=model, api_key="test-key")
        provider = OpenAIProvider(config)
        assert provider._is_reasoning_model(), f"Expected {model} to be a reasoning model"

    for model in non_reasoning_models:
        config = ProviderConfig(provider="openai", model=model, api_key="test-key")
        provider = OpenAIProvider(config)
        assert not provider._is_reasoning_model(), f"Expected {model} to NOT be a reasoning model"


@pytest.mark.asyncio
async def test_responses_api_not_called_for_non_reasoning(provider_config):
    """Test that responses.create is NOT called for non-reasoning models."""
    provider = OpenAIProvider(provider_config)

    # Mock chat.completions.create to return valid response
    mock_chat_response = MagicMock()
    mock_chat_response.choices = [MagicMock(message=MagicMock(content="Chat response"))]
    mock_chat_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

    mock_chat_create = AsyncMock(return_value=mock_chat_response)
    mock_responses_create = AsyncMock()

    with (
        patch.object(provider._client.chat.completions, "create", new=mock_chat_create),
        patch.object(provider._client.responses, "create", new=mock_responses_create),
    ):
        result = await provider.generate(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Hello")],
        )

    # responses.create should NOT have been called
    mock_responses_create.assert_not_called()
    # chat.completions.create should have been called
    mock_chat_create.assert_called_once()
    assert result.text == "Chat response"


def test_strict_schema_preparation():
    """Test that _prepare_strict_schema produces a fully strict-compliant schema.

    Verifies: additionalProperties: false on all objects, all properties in required,
    no default keys, no title keys. Uses a schema with nested objects, defaults,
    and titles to exercise all branches of _make_strict.
    """
    raw_schema = {
        "title": "TopLevel",
        "type": "object",
        "properties": {
            "name": {"title": "Name", "type": "string"},
            "score": {"title": "Score", "type": "number", "default": 0.0},
            "nested": {
                "title": "Nested",
                "type": "object",
                "properties": {
                    "flag": {"title": "Flag", "type": "boolean", "default": False},
                    "tags": {
                        "title": "Tags",
                        "type": "array",
                        "items": {"title": "Tag", "type": "string"},
                    },
                },
            },
        },
        "$defs": {
            "Inner": {
                "title": "Inner",
                "type": "object",
                "properties": {
                    "value": {"title": "Value", "type": "integer", "default": 42},
                },
            }
        },
    }

    result = _prepare_strict_schema(raw_schema)

    # Input must not be mutated
    assert raw_schema["title"] == "TopLevel"
    assert raw_schema["properties"]["score"]["default"] == 0.0

    # Top-level object: additionalProperties and full required
    assert result["additionalProperties"] is False
    assert set(result["required"]) == {"name", "score", "nested"}

    # No title or default at top level
    assert "title" not in result
    assert "default" not in result

    # Scalar property: no title, no default
    assert "title" not in result["properties"]["name"]
    assert "title" not in result["properties"]["score"]
    assert "default" not in result["properties"]["score"]

    # Nested object: additionalProperties and full required
    nested = result["properties"]["nested"]
    assert "title" not in nested
    assert nested["additionalProperties"] is False
    assert set(nested["required"]) == {"flag", "tags"}
    assert "default" not in nested["properties"]["flag"]
    assert "title" not in nested["properties"]["flag"]

    # Array items: title stripped
    tags_prop = nested["properties"]["tags"]
    assert "title" not in tags_prop
    assert "title" not in tags_prop["items"]

    # $defs entry: additionalProperties and full required
    inner = result["$defs"]["Inner"]
    assert "title" not in inner
    assert inner["additionalProperties"] is False
    assert inner["required"] == ["value"]
    assert "default" not in inner["properties"]["value"]
    assert "title" not in inner["properties"]["value"]


@pytest.mark.asyncio
async def test_responses_api_schema_is_strict(o3_provider_config):
    """Test that the schema passed to responses.create is fully strict-compliant.

    Verifies that _prepare_strict_schema is applied before the Responses API call,
    so the schema has additionalProperties: false and all properties in required.
    SampleOutputSchema has two properties (title, count) — both must appear in required.
    """
    provider = OpenAIProvider(o3_provider_config)

    mock_response = MagicMock()
    mock_response.output_text = '{"title": "Strict Test", "count": 7}'
    mock_response.usage = MagicMock(input_tokens=5, output_tokens=10)

    mock_create = AsyncMock(return_value=mock_response)

    with patch.object(provider._client.responses, "create", new=mock_create):
        await provider.generate_structured(
            system_prompt="You are a test assistant",
            messages=[LLMMessage(role="user", content="Generate structured data")],
            output_schema=SampleOutputSchema,
        )

    call_kwargs = mock_create.call_args.kwargs
    schema = call_kwargs["text"]["format"]["schema"]

    # Must have additionalProperties: false on the top-level object
    assert schema.get("additionalProperties") is False, (
        "Schema missing additionalProperties: false — Responses API will reject it"
    )

    # All properties must be in required
    props = set(schema.get("properties", {}).keys())
    required = set(schema.get("required", []))
    assert props == required, (
        f"Schema required {required!r} does not cover all properties {props!r}"
    )

    # No default values anywhere in top-level properties
    for prop_name, prop_def in schema.get("properties", {}).items():
        assert "default" not in prop_def, (
            f"Property '{prop_name}' still has a default — Responses API strict mode forbids this"
        )


@pytest.mark.asyncio
async def test_o3_deep_research_not_routed_as_reasoning_model():
    """Test that o3-deep-research is NOT routed through the Responses API.

    o3-deep-research starts with "o3" but is not in the explicit _REASONING_MODELS allowlist
    and does not support json_schema structured output via responses.create.
    It must go through chat.completions, never responses.create.
    """
    config = ProviderConfig(provider="openai", model="o3-deep-research", api_key="test-key")
    provider = OpenAIProvider(config)

    # Confirm the model is not classified as a reasoning model
    assert not provider._is_reasoning_model(), (
        "o3-deep-research must NOT be a reasoning model — it does not support "
        "json_schema via the Responses API"
    )

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Deep research response"))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

    mock_chat_create = AsyncMock(return_value=mock_response)
    mock_responses_create = AsyncMock()

    with (
        patch.object(provider._client.chat.completions, "create", new=mock_chat_create),
        patch.object(provider._client.responses, "create", new=mock_responses_create),
    ):
        result = await provider.generate(
            system_prompt="You are a research assistant",
            messages=[LLMMessage(role="user", content="Research this topic")],
        )

    # Must have gone through chat.completions, not responses
    mock_responses_create.assert_not_called()
    mock_chat_create.assert_called_once()

    # Must use max_completion_tokens
    call_kwargs = mock_chat_create.call_args.kwargs
    assert "max_completion_tokens" in call_kwargs
    assert "max_tokens" not in call_kwargs

    assert result.text == "Deep research response"


def test_is_reasoning_model_date_versioned():
    """Test that date-versioned model IDs are correctly identified as reasoning models.

    OpenAI publishes versioned model IDs like o3-2025-04-16 and o4-mini-2025-04-16.
    These must route to the Responses API, not chat.completions, to avoid a 404 error.
    The fix strips the -YYYY-MM-DD suffix before checking the allowlist.
    """
    # Versioned reasoning models — base name is in _REASONING_MODELS
    versioned_reasoning = [
        "o3-2025-04-16",
        "o3-mini-2025-04-16",
        "o4-mini-2025-04-16",
        "o1-2024-12-17",
        "o1-mini-2024-09-12",
        "o1-pro-2025-03-19",
        "o3-pro-2025-06-10",
    ]

    for model in versioned_reasoning:
        config = ProviderConfig(provider="openai", model=model, api_key="test-key")
        provider = OpenAIProvider(config)
        assert provider._is_reasoning_model(), (
            f"Expected versioned model {model!r} to be a reasoning model — "
            "it would fail with 404 on chat.completions"
        )

    # Versioned non-reasoning models — base name is NOT in allowlist
    versioned_non_reasoning = [
        "gpt-4o-2024-08-06",
        "gpt-4-2024-04-09",
        "o3-deep-research-2025-06-26",  # base is o3-deep-research, not in allowlist
        "o1-preview-2024-09-12",        # base is o1-preview, not in allowlist
    ]

    for model in versioned_non_reasoning:
        config = ProviderConfig(provider="openai", model=model, api_key="test-key")
        provider = OpenAIProvider(config)
        assert not provider._is_reasoning_model(), (
            f"Expected versioned model {model!r} to NOT be a reasoning model"
        )


@pytest.mark.asyncio
async def test_versioned_reasoning_model_routes_to_responses_api():
    """Test that a date-versioned reasoning model (e.g. o3-2025-04-16) routes to responses.create.

    This is the production-critical path: when OpenAI publishes a dated snapshot of a
    reasoning model, it must still use the Responses API or the call fails with 404.
    """
    config = ProviderConfig(provider="openai", model="o3-2025-04-16", api_key="test-key")
    provider = OpenAIProvider(config)

    mock_response = MagicMock()
    mock_response.output_text = "Versioned reasoning response"
    mock_response.usage = MagicMock(input_tokens=10, output_tokens=20)

    mock_responses_create = AsyncMock(return_value=mock_response)
    mock_chat_create = AsyncMock()

    with (
        patch.object(provider._client.responses, "create", new=mock_responses_create),
        patch.object(provider._client.chat.completions, "create", new=mock_chat_create),
    ):
        result = await provider.generate(
            system_prompt="You are a reasoning assistant",
            messages=[LLMMessage(role="user", content="Think deeply")],
        )

    # Must go through responses.create, not chat.completions
    mock_responses_create.assert_called_once()
    mock_chat_create.assert_not_called()

    # Verify the versioned model ID is passed as-is to the API
    call_kwargs = mock_responses_create.call_args.kwargs
    assert call_kwargs["model"] == "o3-2025-04-16"
    assert call_kwargs["instructions"] == "You are a reasoning assistant"
    assert "temperature" not in call_kwargs
    assert call_kwargs["store"] is False

    assert result.text == "Versioned reasoning response"


@pytest.mark.asyncio
async def test_versioned_deep_research_routes_to_chat_completions():
    """Test that o3-deep-research-YYYY-MM-DD is NOT routed to the Responses API.

    o3-deep-research does not support json_schema via responses.create. Even when
    date-versioned, the base name o3-deep-research is not in the allowlist, so it
    must go through chat.completions.
    """
    config = ProviderConfig(
        provider="openai", model="o3-deep-research-2025-06-26", api_key="test-key"
    )
    provider = OpenAIProvider(config)

    assert not provider._is_reasoning_model(), (
        "o3-deep-research-2025-06-26 must NOT be a reasoning model"
    )

    mock_chat_response = MagicMock()
    mock_chat_response.choices = [MagicMock(message=MagicMock(content="Deep research versioned"))]
    mock_chat_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)

    mock_chat_create = AsyncMock(return_value=mock_chat_response)
    mock_responses_create = AsyncMock()

    with (
        patch.object(provider._client.chat.completions, "create", new=mock_chat_create),
        patch.object(provider._client.responses, "create", new=mock_responses_create),
    ):
        result = await provider.generate(
            system_prompt="You are a research assistant",
            messages=[LLMMessage(role="user", content="Research this")],
        )

    mock_responses_create.assert_not_called()
    mock_chat_create.assert_called_once()
    assert result.text == "Deep research versioned"
