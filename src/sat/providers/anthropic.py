"""Anthropic Claude LLM provider implementation.

@decision DEC-LLM-003: Uses Anthropic structured output API for schema-validated responses.
Passes Pydantic model's JSON Schema via the response_format parameter.
Falls back to parsing JSON from text if structured output is unavailable.
Retries once on validation failure with the error appended to the conversation.
"""

from __future__ import annotations

import json
import logging
import time

import anthropic
from pydantic import BaseModel, ValidationError

from sat.config import ProviderConfig
from sat.providers.base import LLMMessage, LLMResult, LLMUsage

logger = logging.getLogger(__name__)


def _deep_deserialize(value: object) -> object:
    """Recursively parse JSON-encoded strings that look like arrays or objects.

    Walks dicts and lists at every depth level.  When a ``str`` value begins
    with ``[`` or ``{``, attempts ``json.loads``; on success the parsed result
    is recursed into so nested double-encoding is also handled.  Malformed JSON
    strings and all other types are returned unchanged.

    A ``DEBUG``-level log is emitted on each successful parse so the correction
    is traceable without polluting production logs.
    """
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped[0] in ("[", "{"):
            try:
                parsed = json.loads(value)
                logger.debug("_deep_deserialize: parsed JSON string -> %r", type(parsed).__name__)
                return _deep_deserialize(parsed)
            except json.JSONDecodeError:
                return value
        return value
    if isinstance(value, dict):
        return {k: _deep_deserialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_deserialize(item) for item in value]
    return value


class AnthropicProvider:
    """LLM provider using the Anthropic Claude API."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        api_key = config.resolve_api_key()
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=config.base_url,
            timeout=1200.0,  # 20 minutes — long tasks are expected
            max_retries=5,  # SDK retries 429/529/5xx with exponential backoff
        )
        self._model = config.resolve_model()

    def _to_api_messages(self, messages: list[LLMMessage]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> LLMResult:
        """Generate a free-form text completion."""
        logger.info("Anthropic generate: model=%s max_tokens=%d", self._model, max_tokens)
        t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=self._to_api_messages(messages),
        )
        logger.info("Anthropic generate: done in %.1fs", time.monotonic() - t0)
        text = response.content[0].text
        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return LLMResult(text=text, usage=usage)

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[BaseModel],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> BaseModel:
        """Generate a structured, schema-validated output.

        Uses Anthropic's tool_use pattern: defines a single tool whose
        input_schema is the Pydantic model's JSON schema, then forces
        the model to call that tool.
        """
        schema = output_schema.model_json_schema()
        tool_name = "structured_output"

        tool_def = {
            "name": tool_name,
            "description": f"Produce the structured analysis output as a {output_schema.__name__}.",
            "input_schema": schema,
        }

        logger.info(
            "Anthropic generate_structured: model=%s schema=%s max_tokens=%d",
            self._model,
            output_schema.__name__,
            max_tokens,
        )
        t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=self._to_api_messages(messages),
            tools=[tool_def],
            tool_choice={"type": "tool", "name": tool_name},
        )
        logger.info("Anthropic generate_structured: done in %.1fs", time.monotonic() - t0)

        if response.stop_reason == "max_tokens":
            logger.warning(
                "Anthropic generate_structured: response truncated at max_tokens=%d "
                "(schema=%s). Increase max_tokens to avoid partial output.",
                max_tokens,
                output_schema.__name__,
            )

        # Extract the tool use block
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                try:
                    return output_schema.model_validate(self._deserialize_tool_input(block.input))
                except ValidationError as e:
                    logger.warning("Structured output validation failed: %s", e)
                    return await self._retry_structured(
                        system_prompt,
                        messages,
                        output_schema,
                        self._deserialize_tool_input(block.input),
                        str(e),
                        max_tokens,
                        temperature,
                    )

        raise RuntimeError("No tool_use block found in Anthropic response")

    @staticmethod
    def _deserialize_tool_input(data: dict) -> dict:
        """Pre-parse any JSON-string values that should be lists or dicts, recursively.

        Anthropic occasionally serializes nested arrays/objects as raw JSON
        strings inside a tool_use input block.  Pydantic then rejects them
        because it sees a ``str`` where it expects a ``list`` or ``dict``.

        This helper recursively walks the entire structure — dicts, lists, and
        nested combinations — and JSON-parses any string value that begins with
        ``[`` or ``{``.  Malformed JSON strings are preserved as-is.  A debug
        log is emitted each time a correction is applied so the fix is visible
        without being noisy in production.
        """
        result = _deep_deserialize(data)
        if not isinstance(result, dict):
            raise TypeError(
                f"Expected dict from _deep_deserialize, got {type(result).__name__}"
            )
        return result

    async def _retry_structured(
        self,
        system_prompt: str,
        original_messages: list[LLMMessage],
        output_schema: type[BaseModel],
        invalid_output: dict,
        error: str,
        max_tokens: int,
        temperature: float,
    ) -> BaseModel:
        """Retry once with the validation error appended."""
        logger.info("Retrying structured output with validation error feedback")
        retry_messages = list(original_messages) + [
            LLMMessage(
                role="assistant",
                content=f"I produced this output:\n{json.dumps(invalid_output, indent=2)}",
            ),
            LLMMessage(
                role="user",
                content=(
                    f"That output failed validation with this error:\n{error}\n\n"
                    "Please fix the output to conform to the required schema."
                ),
            ),
        ]

        schema = output_schema.model_json_schema()
        tool_name = "structured_output"
        tool_def = {
            "name": tool_name,
            "description": f"Produce the structured analysis output as a {output_schema.__name__}.",
            "input_schema": schema,
        }

        logger.info(
            "Anthropic generate_structured retry: model=%s schema=%s",
            self._model,
            output_schema.__name__,
        )
        t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=self._to_api_messages(retry_messages),
            tools=[tool_def],
            tool_choice={"type": "tool", "name": tool_name},
        )
        logger.info("Anthropic generate_structured retry: done in %.1fs", time.monotonic() - t0)

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                try:
                    return output_schema.model_validate(self._deserialize_tool_input(block.input))
                except ValidationError as e:
                    logger.error(
                        "Structured output retry also failed validation (schema=%s): %s",
                        output_schema.__name__, e,
                    )
                    raise RuntimeError(
                        f"Structured output failed validation after retry "
                        f"(schema={output_schema.__name__}): {e}"
                    ) from e

        raise RuntimeError("Retry also failed to produce valid structured output")
