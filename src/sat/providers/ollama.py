"""Ollama LLM provider via native REST API (POST /api/chat, GET /api/tags).

Does not use OpenAI-compatible /v1 endpoints — those can diverge as OpenAI
updates its API. Uses httpx against Ollama's stable native contract.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from sat.config import ProviderConfig
from sat.providers.base import LLMMessage, LLMResult, LLMUsage
from sat.providers.local_http import (
    DEFAULT_OLLAMA_HOST,
    LOCAL_HTTP_TIMEOUT,
    extract_json_text,
    normalize_host,
    schema_for_ollama_format,
)

logger = logging.getLogger(__name__)


class OllamaProvider:
    """LLM provider using Ollama's native HTTP API."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._host = normalize_host(config.resolve_base_url() or DEFAULT_OLLAMA_HOST)
        self._model = config.resolve_model()
        self._client = httpx.AsyncClient(
            base_url=self._host,
            timeout=LOCAL_HTTP_TIMEOUT,
        )

    def _build_messages(
        self, system_prompt: str, messages: list[LLMMessage]
    ) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        for msg in messages:
            result.append({"role": msg.role, "content": msg.content})
        return result

    def _usage_from_response(self, data: dict[str, Any]) -> LLMUsage:
        return LLMUsage(
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
        )

    async def _chat(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        format: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if format is not None:
            payload["format"] = format

        logger.info(
            "Ollama /api/chat: model=%s messages=%d format=%s",
            self._model,
            len(messages),
            "yes" if format is not None else "no",
        )
        t0 = time.monotonic()
        response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        logger.info("Ollama /api/chat: done in %.1fs", time.monotonic() - t0)
        return data

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> LLMResult:
        """Generate a text completion via POST /api/chat."""
        data = await self._chat(
            messages=self._build_messages(system_prompt, messages),
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = (data.get("message") or {}).get("content") or ""
        return LLMResult(text=content, usage=self._usage_from_response(data))

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[BaseModel],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> BaseModel:
        """Generate structured output using Ollama's native ``format`` schema."""
        schema = schema_for_ollama_format(output_schema.model_json_schema())
        api_messages = self._build_messages(system_prompt, messages)

        data = await self._chat(
            messages=api_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            format=schema,
        )
        content = (data.get("message") or {}).get("content") or ""
        try:
            return output_schema.model_validate_json(extract_json_text(content))
        except (ValidationError, ValueError) as first_err:
            logger.warning(
                "Ollama structured output validation failed (%s); retrying",
                first_err,
            )
            retry_messages = [
                *api_messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not valid JSON for the required schema. "
                        f"Error: {first_err}. "
                        "Reply with ONLY a JSON object matching the schema — no markdown."
                    ),
                },
            ]
            data = await self._chat(
                messages=retry_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                format=schema,
            )
            content = (data.get("message") or {}).get("content") or ""
            return output_schema.model_validate_json(extract_json_text(content))

    async def aclose(self) -> None:
        await self._client.aclose()
