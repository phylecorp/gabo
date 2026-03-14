"""Tests for stop-reason truncation warning logging in all three providers (Bug 3B fix).

@decision DEC-TEST-STOPWARN-001: Use unittest.mock to simulate truncated API responses.
Each provider's generate_structured() must log a WARNING when the API signals that
the response was truncated (stop_reason=max_tokens for Anthropic, finish_reason=length
for OpenAI chat, status=incomplete for OpenAI responses, non-STOP finish_reason for
Gemini). Mocking the API client lets us verify the warning without live API calls.

# @mock-exempt: Provider API clients are external dependencies (network, API keys,
# cost). Mocking them here tests observability behaviour, not LLM logic.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from sat.config import ProviderConfig
from sat.models.base import ArtifactResult


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_config(
    provider: str = "anthropic", model: str = "claude-3-5-sonnet-20241022"
) -> ProviderConfig:
    return ProviderConfig(provider=provider, model=model, api_key="test-key")


def _make_minimal_result() -> dict:
    """Minimal valid ArtifactResult JSON that passes model validation."""
    return {
        "technique_id": "test",
        "technique_name": "Test",
        "summary": "Test summary",
    }


# ---------------------------------------------------------------------------
# Anthropic: stop_reason == "max_tokens"
# ---------------------------------------------------------------------------


class TestAnthropicTruncationWarning:
    """AnthropicProvider.generate_structured warns when stop_reason == 'max_tokens'."""

    @pytest.mark.asyncio
    async def test_warns_on_max_tokens_stop_reason(self, caplog):
        """A warning is logged when Anthropic signals max_tokens truncation."""
        from sat.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider.__new__(AnthropicProvider)
        provider._config = _make_config()
        provider._model = "claude-3-5-sonnet-20241022"

        # Build a fake tool_use block in the response
        tool_block = SimpleNamespace(
            type="tool_use",
            name="structured_output",
            input=_make_minimal_result(),
        )
        fake_response = SimpleNamespace(
            stop_reason="max_tokens",
            content=[tool_block],
        )

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=fake_response)
        provider._client = mock_client

        with caplog.at_level(logging.WARNING, logger="sat.providers.anthropic"):
            await provider.generate_structured(
                system_prompt="sys",
                messages=[],
                output_schema=ArtifactResult,
                max_tokens=128,
            )

        assert any(
            "max_tokens" in r.message and r.levelno == logging.WARNING for r in caplog.records
        ), f"Expected truncation WARNING; got records: {[r.message for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_no_warn_on_stop_reason(self, caplog):
        """No truncation warning is logged when stop_reason is 'end_turn'."""
        from sat.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider.__new__(AnthropicProvider)
        provider._config = _make_config()
        provider._model = "claude-3-5-sonnet-20241022"

        tool_block = SimpleNamespace(
            type="tool_use",
            name="structured_output",
            input=_make_minimal_result(),
        )
        fake_response = SimpleNamespace(
            stop_reason="end_turn",
            content=[tool_block],
        )

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=fake_response)
        provider._client = mock_client

        with caplog.at_level(logging.WARNING, logger="sat.providers.anthropic"):
            await provider.generate_structured(
                system_prompt="sys",
                messages=[],
                output_schema=ArtifactResult,
                max_tokens=4096,
            )

        truncation_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "truncat" in r.message.lower()
        ]
        assert not truncation_warnings, (
            f"Unexpected truncation warning on end_turn: {[r.message for r in truncation_warnings]}"
        )


# ---------------------------------------------------------------------------
# OpenAI chat path: finish_reason == "length"
# ---------------------------------------------------------------------------


class TestOpenAIChatTruncationWarning:
    """OpenAIProvider.generate_structured warns on chat finish_reason=length."""

    @pytest.mark.asyncio
    async def test_warns_on_finish_reason_length(self, caplog):
        """A warning is logged when the chat path signals length truncation."""
        from sat.providers.openai import OpenAIProvider

        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider._config = _make_config("openai", "gpt-4o")
        provider._model = "gpt-4o"

        import json as _json

        choice = SimpleNamespace(
            finish_reason="length",
            message=SimpleNamespace(content=_json.dumps(_make_minimal_result())),
        )
        fake_response = SimpleNamespace(choices=[choice], usage=None)

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
        provider._client = mock_client

        with caplog.at_level(logging.WARNING, logger="sat.providers.openai"):
            await provider.generate_structured(
                system_prompt="sys",
                messages=[],
                output_schema=ArtifactResult,
                max_tokens=128,
            )

        assert any(
            "length" in r.message and r.levelno == logging.WARNING for r in caplog.records
        ), f"Expected truncation WARNING; got records: {[r.message for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_no_warn_on_stop_finish_reason(self, caplog):
        """No truncation warning when finish_reason is 'stop'."""
        from sat.providers.openai import OpenAIProvider

        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider._config = _make_config("openai", "gpt-4o")
        provider._model = "gpt-4o"

        import json as _json

        choice = SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content=_json.dumps(_make_minimal_result())),
        )
        fake_response = SimpleNamespace(choices=[choice], usage=None)

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
        provider._client = mock_client

        with caplog.at_level(logging.WARNING, logger="sat.providers.openai"):
            await provider.generate_structured(
                system_prompt="sys",
                messages=[],
                output_schema=ArtifactResult,
                max_tokens=4096,
            )

        truncation_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "truncat" in r.message.lower()
        ]
        assert not truncation_warnings, (
            f"Unexpected truncation warning on 'stop': {[r.message for r in truncation_warnings]}"
        )


# ---------------------------------------------------------------------------
# OpenAI responses path: status == "incomplete"
# ---------------------------------------------------------------------------


class TestOpenAIResponsesTruncationWarning:
    """OpenAIProvider warns on responses-path status=incomplete."""

    @pytest.mark.asyncio
    async def test_warns_on_incomplete_status(self, caplog):
        """A warning is logged when the responses path returns status=incomplete."""
        from sat.providers.openai import OpenAIProvider

        provider = OpenAIProvider.__new__(OpenAIProvider)
        provider._config = _make_config("openai", "o3")
        provider._model = "o3"

        import json as _json

        fake_response = SimpleNamespace(
            status="incomplete",
            output_text=_json.dumps(_make_minimal_result()),
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

        mock_client = MagicMock()
        mock_client.responses.create = AsyncMock(return_value=fake_response)
        provider._client = mock_client

        with caplog.at_level(logging.WARNING, logger="sat.providers.openai"):
            await provider.generate_structured(
                system_prompt="sys",
                messages=[],
                output_schema=ArtifactResult,
                max_tokens=128,
            )

        assert any(
            "incomplete" in r.message and r.levelno == logging.WARNING for r in caplog.records
        ), f"Expected incomplete WARNING; got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Gemini: non-STOP finish_reason
# ---------------------------------------------------------------------------


class TestGeminiTruncationWarning:
    """GeminiProvider.generate_structured warns on non-STOP finish reasons."""

    @pytest.mark.asyncio
    async def test_warns_on_max_tokens_finish_reason(self, caplog):
        """A warning is logged when Gemini returns a MAX_TOKENS finish reason."""
        from sat.providers.gemini import GeminiProvider

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._config = _make_config("gemini", "gemini-2.0-flash")
        provider._model = "gemini-2.0-flash"

        import json as _json

        # Simulate a finish_reason enum with name="MAX_TOKENS"
        max_tokens_reason = SimpleNamespace(name="MAX_TOKENS")
        candidate = SimpleNamespace(finish_reason=max_tokens_reason)
        fake_response = SimpleNamespace(
            text=_json.dumps(_make_minimal_result()),
            candidates=[candidate],
        )

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)
        provider._client = mock_client

        with caplog.at_level(logging.WARNING, logger="sat.providers.gemini"):
            await provider.generate_structured(
                system_prompt="sys",
                messages=[],
                output_schema=ArtifactResult,
                max_tokens=128,
            )

        assert any(
            "MAX_TOKENS" in r.message and r.levelno == logging.WARNING for r in caplog.records
        ), f"Expected truncation WARNING; got: {[r.message for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_no_warn_on_stop_finish_reason(self, caplog):
        """No truncation warning when Gemini returns STOP finish reason."""
        from sat.providers.gemini import GeminiProvider

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._config = _make_config("gemini", "gemini-2.0-flash")
        provider._model = "gemini-2.0-flash"

        import json as _json

        stop_reason = SimpleNamespace(name="STOP")
        candidate = SimpleNamespace(finish_reason=stop_reason)
        fake_response = SimpleNamespace(
            text=_json.dumps(_make_minimal_result()),
            candidates=[candidate],
        )

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)
        provider._client = mock_client

        with caplog.at_level(logging.WARNING, logger="sat.providers.gemini"):
            await provider.generate_structured(
                system_prompt="sys",
                messages=[],
                output_schema=ArtifactResult,
                max_tokens=4096,
            )

        truncation_warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING
            and ("truncat" in r.message.lower() or "STOP" in r.message or "MAX_TOKENS" in r.message)
        ]
        assert not truncation_warnings, (
            f"Unexpected truncation warning on STOP: {[r.message for r in truncation_warnings]}"
        )
