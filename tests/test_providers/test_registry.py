"""Tests for provider registry."""

import pytest

from sat.config import ProviderConfig
from sat.providers.anthropic import AnthropicProvider
from sat.providers.gemini import GeminiProvider
from sat.providers.openai import OpenAIProvider
from sat.providers.registry import create_provider


def test_create_anthropic_provider():
    """Test that create_provider returns AnthropicProvider for anthropic."""
    config = ProviderConfig(provider="anthropic", api_key="test-key")
    provider = create_provider(config)
    assert isinstance(provider, AnthropicProvider)


def test_create_openai_provider():
    """Test that create_provider returns OpenAIProvider for openai."""
    config = ProviderConfig(provider="openai", api_key="test-key")
    provider = create_provider(config)
    assert isinstance(provider, OpenAIProvider)


def test_create_gemini_provider():
    """Test that create_provider returns GeminiProvider for gemini."""
    config = ProviderConfig(provider="gemini", api_key="test-key")
    provider = create_provider(config)
    assert isinstance(provider, GeminiProvider)


def test_create_unknown_provider_raises():
    """Test that create_provider raises ValueError for unknown provider."""
    config = ProviderConfig(provider="unknown", api_key="test-key")
    with pytest.raises(ValueError) as exc_info:
        create_provider(config)
    assert "Unknown provider: 'unknown'" in str(exc_info.value)
    assert "Available: anthropic, openai, gemini" in str(exc_info.value)
