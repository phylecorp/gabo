"""Tests for .env support and API key resolution.

@decision DEC-TEST-ENV-001
@title .env support and optional API key resolution tests
@status accepted
@rationale Tests that load_dotenv() is called during CLI initialization and that
try_resolve_api_key() provides optional key resolution (returns None instead of raising)
for multi-provider scenarios. These tests validate the contract between CLI > env > .env
precedence and the new non-throwing key resolution method.
"""
# @mock-exempt: Must mock os.environ to test env var resolution without polluting
# the actual environment. The asyncio.run and load_dotenv mocks prevent real pipeline
# execution and file I/O during CLI tests.

from __future__ import annotations

from unittest.mock import patch

import pytest

from sat.config import ProviderConfig


class TestDotenvIntegration:
    """Test that .env files are loaded by the CLI."""

    def test_load_dotenv_called_on_analyze(self):
        """Verify load_dotenv() is called when analyze command runs."""
        from typer.testing import CliRunner
        from sat.cli import app

        runner = CliRunner()

        # Mock the entire pipeline to prevent actual execution
        with (
            patch("sat.cli.asyncio.run"),
            patch("sat.cli.load_dotenv") as mock_load_dotenv,
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
        ):
            runner.invoke(app, ["analyze", "test question"])
            # load_dotenv should be called before pipeline execution
            mock_load_dotenv.assert_called_once()


class TestTryResolveApiKey:
    """Test try_resolve_api_key() returns None instead of raising."""

    def test_returns_key_from_config(self):
        """If api_key is set in config, return it."""
        config = ProviderConfig(provider="anthropic", api_key="explicit-key")
        assert config.try_resolve_api_key() == "explicit-key"

    def test_returns_key_from_anthropic_env(self):
        """Resolve ANTHROPIC_API_KEY from environment."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}):
            config = ProviderConfig(provider="anthropic")
            assert config.try_resolve_api_key() == "env-key"

    def test_returns_key_from_openai_env(self):
        """Resolve OPENAI_API_KEY from environment."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "openai-key"}):
            config = ProviderConfig(provider="openai", model="gpt-4")
            assert config.try_resolve_api_key() == "openai-key"

    def test_returns_key_from_gemini_env(self):
        """Resolve GEMINI_API_KEY from environment."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "gemini-key"}):
            config = ProviderConfig(provider="gemini", model="gemini-2.5-pro")
            assert config.try_resolve_api_key() == "gemini-key"

    def test_returns_none_when_no_key_found(self):
        """Return None instead of raising when no key is available."""
        with patch.dict("os.environ", {}, clear=True):
            config = ProviderConfig(provider="anthropic")
            assert config.try_resolve_api_key() is None

    def test_returns_none_for_unknown_provider(self):
        """Return None for providers without env var mapping."""
        with patch.dict("os.environ", {}, clear=True):
            config = ProviderConfig(provider="custom-provider", model="custom-model")
            # Falls back to CUSTOM-PROVIDER_API_KEY which doesn't exist
            assert config.try_resolve_api_key() is None

    def test_prefers_config_over_env(self):
        """Config api_key takes precedence over environment variable."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}):
            config = ProviderConfig(provider="anthropic", api_key="config-key")
            assert config.try_resolve_api_key() == "config-key"


class TestResolveApiKeyBackwardCompat:
    """Test that resolve_api_key() still raises ValueError (backward compatibility)."""

    def test_resolve_raises_when_no_key(self):
        """resolve_api_key() should raise ValueError when no key is found."""
        with patch.dict("os.environ", {}, clear=True):
            config = ProviderConfig(provider="anthropic")
            with pytest.raises(ValueError, match="No API key found"):
                config.resolve_api_key()

    def test_resolve_returns_key_when_present(self):
        """resolve_api_key() returns key when available (unchanged behavior)."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            config = ProviderConfig(provider="anthropic")
            assert config.resolve_api_key() == "test-key"

    def test_resolve_returns_config_key(self):
        """resolve_api_key() returns explicit config key (unchanged behavior)."""
        config = ProviderConfig(provider="anthropic", api_key="explicit")
        assert config.resolve_api_key() == "explicit"
