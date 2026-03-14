"""OpenAI LLM provider implementation.

@decision DEC-LLM-004: OpenAI provider with dual-path routing for reasoning models.
Non-reasoning models (gpt-4, gpt-4o, etc.) use chat.completions.create with response_format
JSON schema for structured output and temperature support.
Chat completions calls use max_completion_tokens (not max_tokens) — newer models such as
GPT-5.2 reject max_tokens on the chat completions API.
Reasoning models are identified via an explicit allowlist (_REASONING_MODELS) rather than
prefix matching. Prefix matching is too broad — e.g. o3-deep-research starts with "o3"
but does NOT support json_schema structured output via the Responses API.
Date-versioned model IDs (e.g. o3-2025-04-16) are handled by stripping the -YYYY-MM-DD
suffix before checking the allowlist. This keeps the explicit allowlist approach (excluding
o3-deep-research) while supporting OpenAI's versioned model naming convention.
Known reasoning models (o1, o1-mini, o1-pro, o3, o3-mini, o3-pro, o4-mini) use the newer
responses.create API with:
  - instructions param for system prompt
  - input param (list of role/content dicts) for conversation
  - max_output_tokens instead of max_tokens (Responses API naming)
  - text.format json_schema config for structured output
  - store=False to avoid persisting request data
  - No temperature parameter (not supported by reasoning models)
Both paths retry once on structured output validation failure, sending the error
back as a user message to elicit a corrected response.

@decision DEC-LLM-006: Strict schema preparation for OpenAI structured output.
Pydantic's model_json_schema() produces schemas that violate OpenAI strict mode requirements:
  - No additionalProperties key (required to be false on all objects)
  - Only explicitly-required fields in required (all properties must be listed)
  - Fields with defaults carry a "default" key (not allowed in strict mode)
  - Descriptive "title" keys are present but unnecessary
The Responses API (used by reasoning models) rejects non-compliant schemas outright.
The Chat Completions API auto-fixes these, but for correctness and consistency we apply
_prepare_strict_schema() on all four schema call sites — both API paths, both primary
and retry calls.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import time

import openai
from pydantic import BaseModel, ValidationError

from sat.config import ProviderConfig
from sat.providers.base import LLMMessage, LLMResult, LLMUsage

logger = logging.getLogger(__name__)

# Reasoning models that support the Responses API with json_schema structured output.
# Prefix-matching is too broad — e.g. o3-deep-research does NOT support json_schema.
_REASONING_MODELS = frozenset({"o1", "o1-mini", "o1-pro", "o3", "o3-mini", "o3-pro", "o4-mini"})

# Matches a trailing date version suffix like -2025-04-16.
# Used by _is_reasoning_model() to normalize versioned model IDs (e.g. o3-2025-04-16 → o3)
# before checking against _REASONING_MODELS, so dated snapshots route correctly to the
# Responses API without broadening the allowlist.
_DATE_SUFFIX_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def _make_strict(node: dict) -> None:
    """Recursively make a JSON schema node strict-compliant (mutates in place).

    Removes title and default keys, enforces additionalProperties: false on all
    object nodes, and ensures every property key is listed in required.
    Recurses into $defs, properties, array items, and anyOf/oneOf variants.
    """
    node.pop("title", None)
    node.pop("default", None)

    if "$defs" in node:
        for defn in node["$defs"].values():
            _make_strict(defn)

    if node.get("type") == "object" and "properties" in node:
        node["additionalProperties"] = False
        node["required"] = list(node["properties"].keys())
        for prop in node["properties"].values():
            _make_strict(prop)

    if node.get("type") == "array" and "items" in node:
        _make_strict(node["items"])

    for key in ("anyOf", "oneOf"):
        if key in node:
            for variant in node[key]:
                _make_strict(variant)


def _prepare_strict_schema(schema: dict) -> dict:
    """Prepare a Pydantic JSON schema for OpenAI strict mode.

    Returns a deep copy of the schema with all strict-mode requirements applied:
    - additionalProperties: false on every object node
    - All property keys present in required
    - No default values
    - No title keys

    The input schema is not mutated.
    """
    schema = copy.deepcopy(schema)
    _make_strict(schema)
    return schema


class OpenAIProvider:
    """LLM provider using the OpenAI API."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        api_key = config.resolve_api_key()
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=config.base_url,
            timeout=1200.0,  # 20 minutes — long tasks are expected
            max_retries=5,  # SDK retries 429/5xx with exponential backoff
        )
        self._model = config.resolve_model()

    def _is_reasoning_model(self) -> bool:
        """Check if the model uses the Responses API path.

        Strips a trailing date version suffix (e.g. -2025-04-16) before checking the
        allowlist, so versioned model IDs like o3-2025-04-16 are correctly identified
        as reasoning models and routed to responses.create rather than chat.completions.
        Date-versioned non-reasoning models (e.g. o3-deep-research-2025-06-26) are
        handled correctly because their base name is not in _REASONING_MODELS.
        """
        base = _DATE_SUFFIX_RE.sub("", self._model)
        return base in _REASONING_MODELS

    def _to_api_messages(self, system_prompt: str, messages: list[LLMMessage]) -> list[dict]:
        """Convert messages to OpenAI chat.completions API format.

        Uses "system" role for standard models. This method is used only for the
        chat.completions path — reasoning models use _to_responses_input instead.
        """
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend([{"role": m.role, "content": m.content} for m in messages])
        return api_messages

    def _to_responses_input(self, messages: list[LLMMessage]) -> list[dict]:
        """Convert messages to Responses API input format.

        System prompt is excluded here — it goes to the 'instructions' parameter.
        Only user/assistant turns are included.
        """
        return [{"role": m.role, "content": m.content} for m in messages]

    async def _generate_responses(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int,
    ) -> LLMResult:
        """Call responses.create for reasoning models (o1/o3/o4-mini).

        Uses instructions for system prompt, input for conversation turns,
        max_output_tokens for token limit, and store=False for privacy.
        Temperature is not passed as reasoning models do not support it.
        """
        logger.info("OpenAI responses generate: model=%s max_tokens=%d", self._model, max_tokens)
        t0 = time.monotonic()
        response = await self._client.responses.create(
            model=self._model,
            instructions=system_prompt,
            input=self._to_responses_input(messages),
            max_output_tokens=max_tokens,
            store=False,
        )
        logger.info("OpenAI responses generate: done in %.1fs", time.monotonic() - t0)
        return LLMResult(
            text=response.output_text,
            usage=LLMUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )

    async def _generate_structured_responses(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[BaseModel],
        max_tokens: int,
    ) -> BaseModel:
        """Call responses.create with json_schema text format for reasoning models.

        The text.format config instructs the model to return JSON conforming to the
        given schema. Output is parsed and validated; on failure retries once.
        """
        schema = _prepare_strict_schema(output_schema.model_json_schema())

        logger.info(
            "OpenAI responses generate_structured: model=%s schema=%s max_tokens=%d",
            self._model,
            output_schema.__name__,
            max_tokens,
        )
        t0 = time.monotonic()
        response = await self._client.responses.create(
            model=self._model,
            instructions=system_prompt,
            input=self._to_responses_input(messages),
            max_output_tokens=max_tokens,
            store=False,
            text={
                "format": {
                    "type": "json_schema",
                    "name": output_schema.__name__,
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        logger.info("OpenAI responses generate_structured: done in %.1fs", time.monotonic() - t0)

        if hasattr(response, "status") and response.status == "incomplete":
            logger.warning(
                "OpenAI responses generate_structured: response incomplete (truncated) "
                "at max_tokens=%d (schema=%s). Increase max_tokens to avoid partial output.",
                max_tokens,
                output_schema.__name__,
            )

        text = response.output_text

        try:
            data = json.loads(text)
            return output_schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Structured output validation failed (responses path): %s", e)
            return await self._retry_structured_responses(
                system_prompt, messages, output_schema, text, str(e), max_tokens
            )

    async def _retry_structured_responses(
        self,
        system_prompt: str,
        original_messages: list[LLMMessage],
        output_schema: type[BaseModel],
        invalid_output: str,
        error: str,
        max_tokens: int,
    ) -> BaseModel:
        """Retry responses.create once with validation error feedback appended."""
        logger.info("Retrying structured output (responses path) with validation error feedback")
        retry_messages = list(original_messages) + [
            LLMMessage(
                role="assistant",
                content=f"I produced this output:\n{invalid_output}",
            ),
            LLMMessage(
                role="user",
                content=(
                    f"That output failed validation with this error:\n{error}\n\n"
                    "Please fix the output to conform to the required schema."
                ),
            ),
        ]

        schema = _prepare_strict_schema(output_schema.model_json_schema())

        logger.info(
            "OpenAI responses generate_structured retry: model=%s schema=%s",
            self._model,
            output_schema.__name__,
        )
        t0 = time.monotonic()
        response = await self._client.responses.create(
            model=self._model,
            instructions=system_prompt,
            input=self._to_responses_input(retry_messages),
            max_output_tokens=max_tokens,
            store=False,
            text={
                "format": {
                    "type": "json_schema",
                    "name": output_schema.__name__,
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        logger.info(
            "OpenAI responses generate_structured retry: done in %.1fs", time.monotonic() - t0
        )

        text = response.output_text
        try:
            data = json.loads(text)
            return output_schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                "Structured output retry also failed validation (schema=%s): %s",
                output_schema.__name__, e,
            )
            raise RuntimeError(
                f"Structured output failed validation after retry "
                f"(schema={output_schema.__name__}): {e}"
            ) from e

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> LLMResult:
        """Generate a free-form text completion.

        Reasoning models (o1/o3/o4-mini) are routed to the Responses API.
        All other models use chat.completions with temperature support.
        """
        if self._is_reasoning_model():
            return await self._generate_responses(system_prompt, messages, max_tokens)

        logger.info("OpenAI chat generate: model=%s max_tokens=%d", self._model, max_tokens)
        t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=self._to_api_messages(system_prompt, messages),
            max_completion_tokens=max_tokens,
            temperature=temperature,
        )
        logger.info("OpenAI chat generate: done in %.1fs", time.monotonic() - t0)

        text = response.choices[0].message.content or ""
        usage = LLMUsage(
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
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

        Reasoning models (o1/o3/o4-mini) are routed to the Responses API path.
        All other models use chat.completions with response_format json_schema.
        Both paths retry once on validation failure.
        """
        if self._is_reasoning_model():
            return await self._generate_structured_responses(
                system_prompt, messages, output_schema, max_tokens
            )

        schema = _prepare_strict_schema(output_schema.model_json_schema())

        logger.info(
            "OpenAI chat generate_structured: model=%s schema=%s max_tokens=%d",
            self._model,
            output_schema.__name__,
            max_tokens,
        )
        t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=self._to_api_messages(system_prompt, messages),
            max_completion_tokens=max_tokens,
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
        )
        logger.info("OpenAI chat generate_structured: done in %.1fs", time.monotonic() - t0)

        finish_reason = response.choices[0].finish_reason if response.choices else None
        if finish_reason == "length":
            logger.warning(
                "OpenAI chat generate_structured: response truncated (finish_reason=length) "
                "at max_tokens=%d (schema=%s). Increase max_tokens to avoid partial output.",
                max_tokens,
                output_schema.__name__,
            )

        text = response.choices[0].message.content or "{}"

        try:
            data = json.loads(text)
            return output_schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Structured output validation failed: %s", e)
            return await self._retry_structured(
                system_prompt, messages, output_schema, text, str(e), max_tokens, temperature
            )

    async def _retry_structured(
        self,
        system_prompt: str,
        original_messages: list[LLMMessage],
        output_schema: type[BaseModel],
        invalid_output: str,
        error: str,
        max_tokens: int,
        temperature: float,
    ) -> BaseModel:
        """Retry chat.completions once with the validation error appended.

        This method is only called for non-reasoning models — reasoning models use
        _retry_structured_responses. Temperature is always included here.
        """
        logger.info("Retrying structured output with validation error feedback")
        retry_messages = list(original_messages) + [
            LLMMessage(
                role="assistant",
                content=f"I produced this output:\n{invalid_output}",
            ),
            LLMMessage(
                role="user",
                content=(
                    f"That output failed validation with this error:\n{error}\n\n"
                    "Please fix the output to conform to the required schema."
                ),
            ),
        ]

        schema = _prepare_strict_schema(output_schema.model_json_schema())

        logger.info(
            "OpenAI chat generate_structured retry: model=%s schema=%s",
            self._model,
            output_schema.__name__,
        )
        t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=self._to_api_messages(system_prompt, retry_messages),
            max_completion_tokens=max_tokens,
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "schema": schema,
                    "strict": True,
                },
            },
        )
        logger.info("OpenAI chat generate_structured retry: done in %.1fs", time.monotonic() - t0)

        text = response.choices[0].message.content or "{}"
        try:
            data = json.loads(text)
            return output_schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                "Structured output retry also failed validation (schema=%s): %s",
                output_schema.__name__, e,
            )
            raise RuntimeError(
                f"Structured output failed validation after retry "
                f"(schema={output_schema.__name__}): {e}"
            ) from e
