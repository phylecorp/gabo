"""Research provider protocol.

@decision DEC-RESEARCH-002: Protocol-based research providers for pluggability.
@title Structural typing for research backends
@status accepted
@rationale Same pattern as LLMProvider — structural subtyping via Protocol so
backends don't need to inherit. Each backend implements research() returning
ResearchResponse with synthesized content and citations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class SearchResult:
    """A single search result with URL and snippet."""

    title: str
    url: str
    snippet: str


@dataclass
class ResearchResponse:
    """Raw response from a research provider."""

    content: str  # Synthesized research text
    citations: list[SearchResult] = field(default_factory=list)


@runtime_checkable
class ResearchProvider(Protocol):
    """Interface for research backends."""

    async def research(
        self,
        query: str,
        context: str | None = None,
        max_sources: int = 10,
    ) -> ResearchResponse:
        """Execute research and return raw findings with citations."""
        ...
