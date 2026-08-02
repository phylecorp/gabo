"""Tests for provider registry."""

import pytest

from sat.config import ProviderConfig
from sat.providers.anthropic import AnthropicProvider
from sat.providers.gemini import GeminiProvider
from sat.providers.lmstudio import LMStudioProvider
from sat.providers.ollama import OllamaProvider
from sat.providers.openai import OpenAIProvider
from sat.providers.registry import create_provider


@pytest.mark.parametrize(
    "provider_name,expected_class",
    [
        ("anthropic", AnthropicProvider),
        ("openai", OpenAIProvider),
        ("gemini", GeminiProvider),
        ("ollama", OllamaProvider),
        ("lmstudio", LMStudioProvider),
    ],
)
def test_create_provider_returns_correct_type(provider_name, expected_class):
    """Test that create_provider returns the correct provider type for each name."""
    config = ProviderConfig(provider=provider_name, api_key="test-key", model="m")
    provider = create_provider(config)
    assert isinstance(provider, expected_class)


def test_create_unknown_provider_raises():
    """Test that create_provider raises ValueError for unknown provider."""
    config = ProviderConfig(provider="unknown", api_key="test-key")
    with pytest.raises(ValueError) as exc_info:
        create_provider(config)
    assert "Unknown provider: 'unknown'" in str(exc_info.value)
    assert "ollama" in str(exc_info.value)
    assert "lmstudio" in str(exc_info.value)
