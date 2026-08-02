"""LM Studio LLM provider via native REST API v1 (POST /api/v1/chat, GET /api/v1/models).

Does not use OpenAI-compatible /v1 endpoints or legacy /api/v0. Uses httpx
against LM Studio's native v1 contract (recommended since LM Studio 0.4.0).
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
    DEFAULT_LMSTUDIO_HOST,
    LOCAL_HTTP_TIMEOUT,
    extract_json_text,
    normalize_host,
)

logger = logging.getLogger(__name__)


class LMStudioProvider:
    """LLM provider using LM Studio's native /api/v1 HTTP API."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._host = normalize_host(config.resolve_base_url() or DEFAULT_LMSTUDIO_HOST)
        self._model = config.resolve_model()
        headers: dict[str, str] = {}
        token = config.try_resolve_api_key()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=self._host,
            timeout=LOCAL_HTTP_TIMEOUT,
            headers=headers,
        )

    def _build_input(self, messages: list[LLMMessage]) -> str:
        """Flatten conversation turns into a single user ``input`` string.

        LM Studio ``/api/v1/chat`` does not accept assistant messages in the
        request body (unlike OpenAI-compat). Multi-turn history is therefore
        inlined as labeled turns in one user string.
        """
        if len(messages) == 1 and messages[0].role == "user":
            return messages[0].content
        parts: list[str] = []
        for msg in messages:
            label = msg.role.upper()
            parts.append(f"{label}: {msg.content}")
        return "\n\n".join(parts)

    def _extract_message_text(self, data: dict[str, Any]) -> str:
        """Concatenate ``output`` items with type == message."""
        parts: list[str] = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                content = item.get("content")
                if content:
                    parts.append(str(content))
        if parts:
            return "\n".join(parts)
        # Fallback for unexpected shapes
        return str(data.get("content") or data.get("text") or "")

    def _usage_from_response(self, data: dict[str, Any]) -> LLMUsage:
        stats = data.get("stats") or {}
        return LLMUsage(
            input_tokens=int(stats.get("input_tokens") or 0),
            output_tokens=int(stats.get("total_output_tokens") or 0),
        )

    async def _chat(
        self,
        *,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "input": self._build_input(messages),
            "stream": False,
            "store": False,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system_prompt:
            payload["system_prompt"] = system_prompt

        logger.info(
            "LM Studio /api/v1/chat: model=%s store=false",
            self._model,
        )
        t0 = time.monotonic()
        response = await self._client.post("/api/v1/chat", json=payload)
        response.raise_for_status()
        data = response.json()
        logger.info("LM Studio /api/v1/chat: done in %.1fs", time.monotonic() - t0)
        return data

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> LLMResult:
        """Generate a text completion via POST /api/v1/chat."""
        data = await self._chat(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return LLMResult(
            text=self._extract_message_text(data),
            usage=self._usage_from_response(data),
        )

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[BaseModel],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> BaseModel:
        """Generate structured output via JSON-in-prompt (no native json_schema)."""
        schema_json = output_schema.model_json_schema()
        structured_system = (
            f"{system_prompt}\n\n"
            "You must reply with ONLY a single JSON object that validates against "
            "this JSON Schema. No markdown fences, no commentary.\n"
            f"Schema: {schema_json}"
        )

        data = await self._chat(
            system_prompt=structured_system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = self._extract_message_text(data)
        try:
            return output_schema.model_validate_json(extract_json_text(content))
        except (ValidationError, ValueError) as first_err:
            logger.warning(
                "LM Studio structured output validation failed (%s); retrying",
                first_err,
            )
            retry_messages = [
                *messages,
                LLMMessage(role="assistant", content=content),
                LLMMessage(
                    role="user",
                    content=(
                        "Your previous response was not valid JSON for the required schema. "
                        f"Error: {first_err}. "
                        "Reply with ONLY a JSON object matching the schema — no markdown."
                    ),
                ),
            ]
            data = await self._chat(
                system_prompt=structured_system,
                messages=retry_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = self._extract_message_text(data)
            return output_schema.model_validate_json(extract_json_text(content))

    async def aclose(self) -> None:
        await self._client.aclose()
