"""LLM-based research fallback when no dedicated research provider is available.

@decision DEC-RESEARCH-005: LLM knowledge as fallback research.
@title LLM fallback for zero-config research
@status accepted
@rationale Uses the configured LLM provider to generate research from its training
data. No external API calls — works with any provider. Lower quality than dedicated
research backends but always available as a fallback.
"""

from __future__ import annotations

import logging

from sat.providers.base import LLMMessage, LLMProvider
from sat.research.base import ResearchResponse

logger = logging.getLogger(__name__)

RESEARCH_SYSTEM_PROMPT = """You are a research analyst providing comprehensive background \
information on a topic.

Your task is to provide the most relevant, factual information you know about the given \
question or topic. Include:

1. Key facts and data points
2. Important context and background
3. Different perspectives or viewpoints
4. Recent developments (to the best of your knowledge)
5. Areas of uncertainty or debate

Be specific and cite well-known sources where possible. Distinguish between established \
facts and analysis/opinion. Focus on information that would be useful for an intelligence \
analyst evaluating this question."""


class LLMResearchProvider:
    """Research provider that uses an LLM's knowledge as a fallback."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def research(
        self,
        query: str,
        context: str | None = None,
        max_sources: int = 10,
    ) -> ResearchResponse:
        """Execute research using LLM knowledge."""
        user_msg = f"Research question: {query}"
        if context:
            user_msg = f"Context: {context}\n\n{user_msg}"
        user_msg += (
            f"\n\nProvide comprehensive research findings. "
            f"Aim for at least {max_sources} distinct factual points."
        )

        result = await self._provider.generate(
            system_prompt=RESEARCH_SYSTEM_PROMPT,
            messages=[LLMMessage(role="user", content=user_msg)],
            max_tokens=4096,
            temperature=0.2,
        )

        return ResearchResponse(content=result.text, citations=[])
