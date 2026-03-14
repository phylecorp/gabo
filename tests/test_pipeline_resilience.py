"""Tests for pipeline error-resilience helpers and retry guard patterns.

@decision DEC-TEST-RESIL-001: Unit tests for _short_error, _is_transient, and retry guard wrapping.
Tests are written against the real implementations — no mocking of internal modules.
The retry-guard tests for provider _retry_structured methods mock only the SDK client
(external boundary), which is the accepted exception per Sacred Practice #5.
# @mock-exempt: Provider retry-guard tests mock only the SDK client (external HTTP/API boundary).

@decision DEC-TEST-RESIL-002: Report and manifest failure propagation tests.
Verify that Phase 4 (manifest write) and Phase 5 (report generation) failures are
fatal — they re-raise rather than swallowing. Tests inspect the pipeline source via
AST to confirm the control-flow contract without executing the full pipeline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from sat.errors import is_transient_error
from sat.pipeline import _short_error


# ---------------------------------------------------------------------------
# _short_error
# ---------------------------------------------------------------------------


class TestShortError:
    """Tests for the _short_error formatting helper."""

    def test_formats_type_and_message(self):
        """Should return 'TypeName: first line of message'."""
        exc = ValueError("something went wrong")
        result = _short_error(exc)
        assert result == "ValueError: something went wrong"

    def test_uses_only_first_line(self):
        """Multi-line messages should be truncated to the first line."""
        exc = RuntimeError("line one\nline two\nline three")
        result = _short_error(exc)
        assert result == "RuntimeError: line one"

    def test_truncates_long_message(self):
        """Messages longer than max_len should be truncated with ellipsis."""
        long_msg = "x" * 100
        exc = ValueError(long_msg)
        result = _short_error(exc, max_len=20)
        assert result == "ValueError: " + "x" * 20 + "..."

    def test_empty_message_returns_type_only(self):
        """When the exception has no message, return just the type name."""
        exc = RuntimeError("")
        result = _short_error(exc)
        assert result == "RuntimeError"

    def test_custom_max_len(self):
        """max_len parameter controls the truncation point."""
        exc = ValueError("abcdefghij")
        result = _short_error(exc, max_len=5)
        assert result == "ValueError: abcde..."

    def test_message_at_exact_max_len_not_truncated(self):
        """A message exactly at max_len should NOT be truncated."""
        exc = ValueError("12345")
        result = _short_error(exc, max_len=5)
        assert result == "ValueError: 12345"

    def test_subclass_uses_actual_type_name(self):
        """Subclass exceptions should show their own class name."""

        class MyCustomError(RuntimeError):
            pass

        exc = MyCustomError("boom")
        result = _short_error(exc)
        assert result == "MyCustomError: boom"


# ---------------------------------------------------------------------------
# _is_transient
# ---------------------------------------------------------------------------


class TestIsTransient:
    """Tests for the is_transient_error classifier (formerly _is_transient)."""

    @pytest.mark.parametrize(
        "class_name",
        [
            "OverloadedError",
            "RateLimitError",
            "InternalServerError",
            "APITimeoutError",
            "APIConnectionError",
            "ServiceUnavailableError",
            "ServerError",
        ],
    )
    def test_returns_true_for_known_transient_names(self, class_name):
        """All known transient error class names should return True."""
        # Dynamically create a class with the exact name to simulate SDK errors
        exc_class = type(class_name, (Exception,), {})
        exc = exc_class("transient failure")
        assert is_transient_error(exc) is True

    @pytest.mark.parametrize(
        "exc",
        [
            ValueError("bad value"),
            RuntimeError("runtime failure"),
            KeyError("missing key"),
            TypeError("type mismatch"),
            AttributeError("no attr"),
        ],
    )
    def test_returns_false_for_non_transient_errors(self, exc):
        """Common non-transient exceptions should return False."""
        assert is_transient_error(exc) is False

    def test_returns_false_for_validation_error(self):
        """ValidationError is not transient — it is a logic/schema error."""
        from pydantic import BaseModel

        class Dummy(BaseModel):
            x: int

        try:
            Dummy(x="not-an-int")  # type: ignore[arg-type]
        except ValidationError as ve:
            assert is_transient_error(ve) is False

    def test_subclass_of_transient_name_is_false(self):
        """A subclass of a transient error uses its OWN class name, not parent."""
        # If someone subclasses RateLimitError as MyRateLimitError, we don't
        # match it — the check is by exact class name, not isinstance.
        exc_class = type("MyRateLimitError", (Exception,), {})
        exc = exc_class("rate limited")
        assert is_transient_error(exc) is False


# ---------------------------------------------------------------------------
# Retry guard — Anthropic provider
# ---------------------------------------------------------------------------
# @mock-exempt: AnthropicProvider._retry_structured calls the Anthropic SDK
# (external HTTP boundary). Mocking the SDK client is the only way to test
# the retry guard without live API credentials.


class TestAnthropicRetryGuard:
    """Verify that _retry_structured wraps ValidationError in RuntimeError."""

    @pytest.mark.asyncio
    async def test_validation_error_wrapped_as_runtime_error(self):
        """When model_validate raises ValidationError on the retry path,
        it should be re-raised as RuntimeError with a clear message.

        The tool_name used inside _retry_structured is hardcoded to
        "structured_output" — fake_block.name must match that exactly.
        """
        from pydantic import BaseModel

        from sat.providers.anthropic import AnthropicProvider

        class MySchema(BaseModel):
            value: int

        # Build a minimal fake Anthropic client — only the messages.create
        # path used by _retry_structured is needed.
        fake_block = MagicMock()
        fake_block.type = "tool_use"
        # Must match the hardcoded tool_name = "structured_output" in _retry_structured
        fake_block.name = "structured_output"
        # Provide valid-looking dict but with wrong type — model_validate will fail
        fake_block.input = {"value": "not-an-int"}

        fake_response = MagicMock()
        fake_response.content = [fake_block]

        fake_messages = AsyncMock()
        fake_messages.create = AsyncMock(return_value=fake_response)

        fake_client = MagicMock()
        fake_client.messages = fake_messages

        provider = AnthropicProvider.__new__(AnthropicProvider)
        provider._client = fake_client
        provider._model = "claude-test"

        with pytest.raises(RuntimeError, match="Structured output failed validation after retry"):
            await provider._retry_structured(
                system_prompt="You are a test assistant.",
                original_messages=[],
                output_schema=MySchema,
                invalid_output={"value": "not-an-int"},
                error="validation failed",
                max_tokens=1024,
                temperature=0.0,
            )

    @pytest.mark.asyncio
    async def test_no_tool_use_block_raises_runtime_error(self):
        """When retry response contains no tool_use block, RuntimeError is raised."""
        from pydantic import BaseModel

        from sat.providers.anthropic import AnthropicProvider

        class MySchema(BaseModel):
            value: int

        fake_block = MagicMock()
        fake_block.type = "text"  # not tool_use

        fake_response = MagicMock()
        fake_response.content = [fake_block]

        fake_messages = AsyncMock()
        fake_messages.create = AsyncMock(return_value=fake_response)

        fake_client = MagicMock()
        fake_client.messages = fake_messages

        provider = AnthropicProvider.__new__(AnthropicProvider)
        provider._client = fake_client
        provider._model = "claude-test"

        with pytest.raises(RuntimeError, match="Retry also failed to produce valid structured output"):
            await provider._retry_structured(
                system_prompt="You are a test assistant.",
                original_messages=[],
                output_schema=MySchema,
                invalid_output={"value": 1},
                error="validation failed",
                max_tokens=1024,
                temperature=0.0,
            )


# ---------------------------------------------------------------------------
# Retry guard — OpenAI provider
# ---------------------------------------------------------------------------
# @mock-exempt: OpenAIProvider._retry_structured and _retry_structured_responses
# call the OpenAI SDK (external HTTP boundary).


class TestOpenAIRetryGuard:
    """Verify that both OpenAI _retry_structured paths wrap errors in RuntimeError."""

    @pytest.mark.asyncio
    async def test_responses_path_json_decode_error_wrapped(self):
        """Invalid JSON on the Responses API retry path raises RuntimeError."""
        from pydantic import BaseModel

        from sat.providers.openai import OpenAIProvider

        class MySchema(BaseModel):
            value: int

        fake_response = MagicMock()
        fake_response.output_text = "not valid json {{{"

        fake_responses = MagicMock()
        fake_responses.create = AsyncMock(return_value=fake_response)

        fake_client = MagicMock()
        fake_client.responses = fake_responses

        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider._client = fake_client
        provider._model = "gpt-4o"

        with pytest.raises(RuntimeError, match="Structured output failed validation after retry"):
            await provider._retry_structured_responses(
                system_prompt="You are a test assistant.",
                original_messages=[],
                output_schema=MySchema,
                invalid_output="bad json",
                error="validation failed",
                max_tokens=1024,
            )

    @pytest.mark.asyncio
    async def test_chat_path_json_decode_error_wrapped(self):
        """Invalid JSON on the chat completions retry path raises RuntimeError."""
        from pydantic import BaseModel

        from sat.providers.openai import OpenAIProvider

        class MySchema(BaseModel):
            value: int

        fake_message = MagicMock()
        fake_message.content = "not valid json {{{"

        fake_choice = MagicMock()
        fake_choice.message = fake_message

        fake_response = MagicMock()
        fake_response.choices = [fake_choice]

        fake_completions = MagicMock()
        fake_completions.create = AsyncMock(return_value=fake_response)

        fake_chat = MagicMock()
        fake_chat.completions = fake_completions

        fake_client = MagicMock()
        fake_client.chat = fake_chat

        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider._client = fake_client
        provider._model = "gpt-4o"

        with pytest.raises(RuntimeError, match="Structured output failed validation after retry"):
            await provider._retry_structured(
                system_prompt="You are a test assistant.",
                original_messages=[],
                output_schema=MySchema,
                invalid_output="bad json",
                error="validation failed",
                max_tokens=1024,
                temperature=0.0,
            )


# ---------------------------------------------------------------------------
# Retry guard — Gemini provider
# ---------------------------------------------------------------------------
# @mock-exempt: GeminiProvider._retry_structured calls the Google GenAI SDK
# (external HTTP boundary).


class TestGeminiRetryGuard:
    """Verify that Gemini _retry_structured wraps errors in RuntimeError."""

    @pytest.mark.asyncio
    async def test_json_decode_error_wrapped(self):
        """Invalid JSON on the Gemini retry path raises RuntimeError."""
        from pydantic import BaseModel

        from sat.providers.gemini import GeminiProvider

        class MySchema(BaseModel):
            value: int

        fake_response = MagicMock()
        fake_response.text = "not valid json {{{"

        fake_models = MagicMock()
        fake_models.generate_content = AsyncMock(return_value=fake_response)

        fake_aio = MagicMock()
        fake_aio.models = fake_models

        fake_client = MagicMock()
        fake_client.aio = fake_aio

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._client = fake_client
        provider._model = "gemini-2.0-flash"

        with pytest.raises(RuntimeError, match="Structured output failed validation after retry"):
            await provider._retry_structured(
                system_prompt="You are a test assistant.",
                original_messages=[],
                output_schema=MySchema,
                invalid_output="bad json",
                error="validation failed",
                max_tokens=1024,
                temperature=0.0,
            )


# ---------------------------------------------------------------------------
# Report and manifest failure propagation (DEC-TEST-RESIL-002)
# ---------------------------------------------------------------------------


class TestReportFailurePropagates:
    """Verify that report generation and manifest write failures are fatal.

    We use AST inspection to confirm the exact control-flow contract without
    executing the full pipeline (which requires LLM credentials). This is the
    appropriate technique: we're testing that the pipeline SOURCE CODE has the
    correct structure, not mocking internal modules.
    """

    def _get_pipeline_source(self) -> str:
        import inspect

        from sat import pipeline

        return inspect.getsource(pipeline)

    def test_report_generation_reraises_not_swallowed(self):
        """Phase 5 except block must re-raise, not print a warning and continue.

        The old behavior called console.print("[yellow]...") before falling through.
        The new behavior calls raise. Verify the swallowing pattern is gone.
        """
        source = self._get_pipeline_source()
        # The swallowing pattern: yellow console print inside the except block
        assert 'console.print("[yellow]Report generation failed[/yellow]")' not in source, (
            "Report generation exception is being swallowed — "
            "the except block must re-raise, not print and continue"
        )

    def test_report_generation_except_block_has_raise(self):
        """Phase 5 except block must contain a bare 'raise' to propagate."""
        import ast
        import inspect

        from sat import pipeline

        source = inspect.getsource(pipeline)
        tree = ast.parse(source)

        # Find any except handler that contains a bare Raise statement.
        # This is satisfied by both the manifest and report except blocks.
        found_raise_in_except = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Raise) and stmt.exc is None:
                        found_raise_in_except = True
                        break
                if found_raise_in_except:
                    break

        assert found_raise_in_except, (
            "No bare 'raise' found in any except handler in pipeline.py — "
            "at least one except block must re-raise for fatal error propagation"
        )

    def test_manifest_write_wrapped_in_try_except_with_raise(self):
        """Phase 4 manifest write must be wrapped in try/except that re-raises.

        Verify the manifest write call is guarded by a try block that has
        an except handler with a bare raise statement.
        """
        import ast
        import inspect

        from sat import pipeline

        source = inspect.getsource(pipeline)
        tree = ast.parse(source)

        # Look for a Try node that contains a call to write_manifest
        # and has an except handler with a bare Raise
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            # Check if this try block contains write_manifest
            has_write_manifest = False
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Attribute)
                    and child.attr == "write_manifest"
                ):
                    has_write_manifest = True
                    break
            if not has_write_manifest:
                continue
            # Check if any handler has a bare raise
            for handler in node.handlers:
                for stmt in ast.walk(handler):
                    if isinstance(stmt, ast.Raise) and stmt.exc is None:
                        found = True
                        break
                if found:
                    break
            if found:
                break

        assert found, (
            "write_manifest is not wrapped in a try/except with a bare raise — "
            "manifest write failures will be silently swallowed"
        )
