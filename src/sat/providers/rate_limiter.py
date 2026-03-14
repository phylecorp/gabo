"""Per-provider rate limiting for concurrent LLM API calls.

@decision DEC-CONCURRENCY-001
@title Semaphore-based per-provider rate limiting wraps providers transparently
@status accepted
@rationale When multiple analyses run concurrently they all share a single API key.
Without rate limiting, N concurrent analyses launch up to N*M simultaneous LLM calls
(N runs times M techniques each). At N=2 and M=5 that's 10 simultaneous API calls —
enough to trigger rate-limit errors on free/standard tiers. A per-provider semaphore
caps in-flight calls. 4 concurrent calls per provider is the default — enough to run
2 concurrent analyses with headroom for the multi-step research phase. The
RateLimitedProvider wrapper is transparent to callers: same interface as LLMProvider.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from sat.providers.base import LLMMessage, LLMResult, LLMProvider


class ProviderRateLimiter:
    """Limits concurrent in-flight LLM API calls per provider.

    Prevents multiple concurrent analyses from overwhelming a single API key's
    rate limits. Default: 4 concurrent calls per provider.

    Thread-safety: all operations happen within the asyncio event loop; no
    additional locking is needed.
    """

    def __init__(self, max_concurrent_per_provider: int = 4) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._max = max_concurrent_per_provider

    def _get_semaphore(self, provider: str) -> asyncio.Semaphore:
        if provider not in self._semaphores:
            self._semaphores[provider] = asyncio.Semaphore(self._max)
        return self._semaphores[provider]

    @asynccontextmanager
    async def acquire(self, provider: str) -> AsyncIterator[None]:
        """Acquire a slot for *provider*, yielding when a slot is available.

        Releases the slot on exit, even if an exception is raised.
        """
        sem = self._get_semaphore(provider)
        await sem.acquire()
        try:
            yield
        finally:
            sem.release()


class RateLimitedProvider:
    """Wraps an LLMProvider to enforce per-provider rate limits.

    Transparent drop-in replacement: callers interact with this object exactly
    as they would with the underlying LLMProvider. The only difference is that
    concurrent calls are limited by the shared ProviderRateLimiter.
    """

    def __init__(
        self,
        inner: LLMProvider,
        limiter: ProviderRateLimiter,
        provider_name: str,
    ) -> None:
        self._inner = inner
        self._limiter = limiter
        self._provider_name = provider_name

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> LLMResult:
        """Generate text, acquiring a rate-limiter slot first."""
        async with self._limiter.acquire(self._provider_name):
            return await self._inner.generate(system_prompt, messages, max_tokens, temperature)

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[BaseModel],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> BaseModel:
        """Generate structured output, acquiring a rate-limiter slot first."""
        async with self._limiter.acquire(self._provider_name):
            return await self._inner.generate_structured(
                system_prompt, messages, output_schema, max_tokens, temperature
            )
