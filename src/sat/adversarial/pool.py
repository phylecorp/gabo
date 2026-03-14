"""Provider pool for managing multiple LLM provider instances.

@decision DEC-ADV-003: Named provider pool with role resolution.
@title Lazy provider creation with role-based access
@status accepted
@rationale Lazily creates provider instances from ProviderRef configs. Resolves
role assignments (primary, challenger, adjudicator, investigator) to concrete
providers. Caches instances so the same named provider is not recreated per call.
"""

from __future__ import annotations

import logging

from sat.adversarial.config import AdversarialConfig
from sat.config import ProviderConfig
from sat.providers.base import LLMProvider
from sat.providers.registry import create_provider

logger = logging.getLogger(__name__)


class ProviderPool:
    """Manages named LLM provider instances for adversarial analysis."""

    def __init__(self, config: AdversarialConfig) -> None:
        self._config = config
        self._providers: dict[str, LLMProvider] = {}

    def _get_or_create(self, name: str) -> LLMProvider:
        """Get or create a provider by name."""
        if name not in self._providers:
            if name not in self._config.providers:
                raise ValueError(
                    f"Unknown provider name: {name!r}. "
                    f"Available: {list(self._config.providers.keys())}"
                )
            ref = self._config.providers[name]
            provider_config = ProviderConfig(
                provider=ref.provider,
                model=ref.model,
                api_key=ref.api_key,
            )
            self._providers[name] = create_provider(provider_config)
            logger.info("Created provider %s (%s/%s)", name, ref.provider, ref.model)
        return self._providers[name]

    def get_primary(self) -> LLMProvider:
        """Get the primary analyst provider."""
        if not self._config.roles:
            raise ValueError("No role assignments configured")
        return self._get_or_create(self._config.roles.primary)

    def get_challenger(self) -> LLMProvider:
        """Get the challenger/critic provider."""
        if not self._config.roles:
            raise ValueError("No role assignments configured")
        return self._get_or_create(self._config.roles.challenger)

    def get_adjudicator(self) -> LLMProvider | None:
        """Get the adjudicator provider, if configured."""
        if not self._config.roles or not self._config.roles.adjudicator:
            return None
        return self._get_or_create(self._config.roles.adjudicator)

    def get_investigator(self) -> LLMProvider | None:
        """Get the investigator provider for independent re-analysis, if configured."""
        if not self._config.roles or not self._config.roles.investigator:
            return None
        return self._get_or_create(self._config.roles.investigator)
