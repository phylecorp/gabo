"""Unit tests for LMStudioProvider (native /api/v1/chat)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from sat.config import ProviderConfig
from sat.providers.base import LLMMessage
from sat.providers.lmstudio import LMStudioProvider
from sat.providers.registry import create_provider


class _TinySchema(BaseModel):
    answer: str


@pytest.fixture
def provider() -> LMStudioProvider:
    return LMStudioProvider(
        ProviderConfig(
            provider="lmstudio",
            model="ibm/granite",
            base_url="http://127.0.0.1:1234",
            api_key="tok",
        )
    )


@pytest.mark.asyncio
async def test_generate_posts_native_v1_chat(provider: LMStudioProvider):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "output": [{"type": "message", "content": "hello"}],
        "stats": {"input_tokens": 2, "total_output_tokens": 1},
    }

    with patch.object(provider._client, "post", new=AsyncMock(return_value=mock_response)) as mock_post:
        result = await provider.generate(
            "sys",
            [LLMMessage(role="user", content="hi")],
            max_tokens=16,
            temperature=0.2,
        )

    assert result.text == "hello"
    assert result.usage.input_tokens == 2
    args, kwargs = mock_post.await_args
    assert args[0] == "/api/v1/chat"
    payload = kwargs["json"]
    assert payload["stream"] is False
    assert payload["store"] is False
    assert payload["system_prompt"] == "sys"
    assert payload["input"] == "hi"
    assert payload["max_output_tokens"] == 16
    assert payload["temperature"] == 0.2


@pytest.mark.asyncio
async def test_generate_ignores_non_message_output(provider: LMStudioProvider):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "output": [
            {"type": "reasoning", "content": "think"},
            {"type": "message", "content": "final"},
        ],
    }

    with patch.object(provider._client, "post", new=AsyncMock(return_value=mock_response)):
        result = await provider.generate("sys", [LLMMessage(role="user", content="hi")])

    assert result.text == "final"


@pytest.mark.asyncio
async def test_generate_structured_json_in_prompt(provider: LMStudioProvider):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "output": [{"type": "message", "content": '{"answer": "yes"}'}],
    }

    with patch.object(provider._client, "post", new=AsyncMock(return_value=mock_response)) as mock_post:
        result = await provider.generate_structured(
            "sys",
            [LLMMessage(role="user", content="q")],
            _TinySchema,
        )

    assert result.answer == "yes"
    payload = mock_post.await_args.kwargs["json"]
    assert payload["store"] is False
    assert "JSON Schema" in payload["system_prompt"]


@pytest.mark.asyncio
async def test_auth_header_when_token_set():
    p = LMStudioProvider(
        ProviderConfig(provider="lmstudio", model="m", api_key="secret-token")
    )
    assert p._client.headers.get("Authorization") == "Bearer secret-token"


def test_create_provider_lmstudio():
    p = create_provider(ProviderConfig(provider="lmstudio", model="m"))
    assert isinstance(p, LMStudioProvider)


def test_default_base_url():
    p = LMStudioProvider(ProviderConfig(provider="lmstudio", model="m"))
    assert p._host == "http://127.0.0.1:1234"
