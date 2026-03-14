"""Google Gemini LLM provider implementation.

@decision DEC-LLM-005: Gemini provider with structured output via response_schema.
Uses google.genai SDK with response_schema parameter for structured output.
Converts Pydantic model to JSON schema dict and strips all 'default' keys before
passing as response_schema, because the Gemini API rejects schemas containing
default values (raises ValueError at runtime).
Retries once on validation failure.
"""

from __future__ import annotations

import json
import logging
import time

from google import genai
from pydantic import BaseModel, ValidationError

from sat.config import ProviderConfig
from sat.providers.base import LLMMessage, LLMResult, LLMUsage

logger = logging.getLogger(__name__)


def _prepare_schema(schema: dict) -> dict:
    """Recursively strip unsupported keys from a JSON schema dict.

    The Gemini API rejects schemas containing:
      1. Default values (raises ValueError at runtime).
      2. additionalProperties (raises ValueError).

    Pydantic's model_json_schema() emits these based on field definitions.
    This helper removes those keys so the schema is safe to pass as response_schema.

    Args:
        schema: A JSON schema dict.

    Returns:
        A new dict with unsupported keys removed at every nesting level.
    """
    schema = {k: v for k, v in schema.items() if k not in ("default", "additionalProperties")}
    if "properties" in schema:
        schema["properties"] = {k: _prepare_schema(v) for k, v in schema["properties"].items()}
    if "items" in schema and isinstance(schema["items"], dict):
        schema["items"] = _prepare_schema(schema["items"])
    if "$defs" in schema:
        schema["$defs"] = {k: _prepare_schema(v) for k, v in schema["$defs"].items()}
    if "anyOf" in schema:
        schema["anyOf"] = [_prepare_schema(v) for v in schema["anyOf"]]
    if "oneOf" in schema:
        schema["oneOf"] = [_prepare_schema(v) for v in schema["oneOf"]]
    return schema


class GeminiProvider:
    """LLM provider using the Google Gemini API."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        api_key = config.resolve_api_key()
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai.types.HttpOptions(timeout=1200000),  # 20 min in milliseconds
        )
        self._model = config.resolve_model()

    def _to_api_contents(self, messages: list[LLMMessage]) -> list[genai.types.Content]:
        """Convert messages to Gemini API format."""
        contents = []
        for msg in messages:
            contents.append(
                genai.types.Content(
                    role=msg.role,
                    parts=[genai.types.Part(text=msg.content)],
                )
            )
        return contents

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> LLMResult:
        """Generate a free-form text completion."""
        config = genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        logger.info("Gemini generate: model=%s max_tokens=%d", self._model, max_tokens)
        t0 = time.monotonic()
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._to_api_contents(messages),
            config=config,
        )
        logger.info("Gemini generate: done in %.1fs", time.monotonic() - t0)

        text = response.text or ""

        # Extract usage information if available
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata"):
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0)

        usage = LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
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

        Converts the Pydantic model to a JSON schema dict and strips all
        'default' keys before passing to response_schema. The Gemini API
        raises ValueError for any schema containing default values.
        """
        config = genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_schema=_prepare_schema(output_schema.model_json_schema()),
        )

        logger.info(
            "Gemini generate_structured: model=%s schema=%s max_tokens=%d",
            self._model,
            output_schema.__name__,
            max_tokens,
        )
        t0 = time.monotonic()
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._to_api_contents(messages),
            config=config,
        )
        logger.info("Gemini generate_structured: done in %.1fs", time.monotonic() - t0)

        # Check for non-STOP finish reasons indicating truncation or other issues
        try:
            candidates = response.candidates
            if candidates:
                finish_reason = candidates[0].finish_reason
                # FinishReason.STOP (value 1) is normal; anything else (MAX_TOKENS=2, etc.) is not
                finish_reason_name = getattr(finish_reason, "name", str(finish_reason))
                if finish_reason_name not in ("STOP", "1"):
                    logger.warning(
                        "Gemini generate_structured: non-STOP finish reason: %s "
                        "(max_tokens=%d, schema=%s). Output may be truncated or incomplete.",
                        finish_reason_name,
                        max_tokens,
                        output_schema.__name__,
                    )
        except (AttributeError, IndexError):
            pass  # Response shape varies; skip if not accessible

        text = response.text or "{}"

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
        """Retry once with the validation error appended."""
        logger.info("Retrying structured output with validation error feedback")
        retry_messages = list(original_messages) + [
            LLMMessage(
                role="model",  # Gemini uses "model" instead of "assistant"
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

        config = genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_schema=_prepare_schema(output_schema.model_json_schema()),
        )

        logger.info(
            "Gemini generate_structured retry: model=%s schema=%s",
            self._model,
            output_schema.__name__,
        )
        t0 = time.monotonic()
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._to_api_contents(retry_messages),
            config=config,
        )
        logger.info("Gemini generate_structured retry: done in %.1fs", time.monotonic() - t0)

        text = response.text or "{}"
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
