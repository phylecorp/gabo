"""Unit tests for OllamaProvider (native /api/chat)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from sat.config import ProviderConfig
from sat.providers.base import LLMMessage
from sat.providers.ollama import OllamaProvider
from sat.providers.registry import create_provider


class _TinySchema(BaseModel):
    answer: str


@pytest.fixture
def provider() -> OllamaProvider:
    return OllamaProvider(
        ProviderConfig(provider="ollama", model="llama3.2", base_url="http://127.0.0.1:11434")
    )


@pytest.mark.asyncio
async def test_generate_posts_native_chat(provider: OllamaProvider):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": "hello"},
        "prompt_eval_count": 3,
        "eval_count": 1,
    }

    with patch.object(provider._client, "post", new=AsyncMock(return_value=mock_response)) as mock_post:
        result = await provider.generate(
            "sys",
            [LLMMessage(role="user", content="hi")],
            max_tokens=32,
            temperature=0.1,
        )

    assert result.text == "hello"
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 1
    mock_post.assert_awaited_once()
    args, kwargs = mock_post.await_args
    assert args[0] == "/api/chat"
    payload = kwargs["json"]
    assert payload["stream"] is False
    assert payload["model"] == "llama3.2"
    assert payload["messages"][0] == {"role": "system", "content": "sys"}
    assert payload["options"]["temperature"] == 0.1
    assert payload["options"]["num_predict"] == 32
    assert "format" not in payload


@pytest.mark.asyncio
async def test_generate_structured_sends_format_schema(provider: OllamaProvider):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": '{"answer": "42"}'},
    }

    with patch.object(provider._client, "post", new=AsyncMock(return_value=mock_response)) as mock_post:
        result = await provider.generate_structured(
            "sys",
            [LLMMessage(role="user", content="q")],
            _TinySchema,
        )

    assert result.answer == "42"
    payload = mock_post.await_args.kwargs["json"]
    assert payload["stream"] is False
    assert isinstance(payload["format"], dict)
    assert payload["format"]["type"] == "object"


@pytest.mark.asyncio
async def test_generate_structured_retries_on_invalid_json(provider: OllamaProvider):
    bad = MagicMock()
    bad.raise_for_status = MagicMock()
    bad.json.return_value = {"message": {"content": "not-json"}}

    good = MagicMock()
    good.raise_for_status = MagicMock()
    good.json.return_value = {"message": {"content": '{"answer": "ok"}'}}

    with patch.object(
        provider._client, "post", new=AsyncMock(side_effect=[bad, good])
    ) as mock_post:
        result = await provider.generate_structured(
            "sys",
            [LLMMessage(role="user", content="q")],
            _TinySchema,
        )

    assert result.answer == "ok"
    assert mock_post.await_count == 2


def test_create_provider_ollama():
    p = create_provider(ProviderConfig(provider="ollama", model="m"))
    assert isinstance(p, OllamaProvider)


def test_default_base_url():
    p = OllamaProvider(ProviderConfig(provider="ollama", model="m"))
    assert p._host == "http://127.0.0.1:11434"
