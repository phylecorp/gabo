"""Provider registry and factory for resolving provider names to instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sat.config import ProviderConfig

if TYPE_CHECKING:
    from sat.providers.base import LLMProvider
    from sat.providers.rate_limiter import ProviderRateLimiter


def create_provider(
    config: ProviderConfig,
    rate_limiter: ProviderRateLimiter | None = None,
) -> LLMProvider:
    """Create an LLM provider instance from config.

    If *rate_limiter* is provided, the returned provider is wrapped in a
    RateLimitedProvider that enforces per-provider concurrency limits.
    The rate_limiter parameter is optional to preserve backward compatibility
    with callers that don't need rate limiting.
    """
    if config.provider == "anthropic":
        from sat.providers.anthropic import AnthropicProvider

        provider: LLMProvider = AnthropicProvider(config)
    elif config.provider == "openai":
        from sat.providers.openai import OpenAIProvider

        provider = OpenAIProvider(config)
    elif config.provider == "gemini":
        from sat.providers.gemini import GeminiProvider

        provider = GeminiProvider(config)
    elif config.provider == "copilot":
        from sat.providers.copilot import CopilotProvider
        provider = CopilotProvider(config)
    else:
        raise ValueError(
            f"Unknown provider: {config.provider!r}. Available: anthropic, openai, gemini, copilot"
        )

    if rate_limiter is not None:
        from sat.providers.rate_limiter import RateLimitedProvider

        return RateLimitedProvider(provider, rate_limiter, config.provider)

    return provider
