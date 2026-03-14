"""LLM provider protocol defining the interface all providers must implement.

@decision DEC-LLM-001: Abstract LLMProvider protocol instead of concrete base class.
Uses Python Protocol (structural subtyping) so providers don't need to inherit.
Two methods: generate() for free text, generate_structured() for schema-validated output.
Async throughout for future parallelism and streaming support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass
class LLMMessage:
    """A message in the conversation."""

    role: str  # "user" or "assistant"
    content: str


@dataclass
class LLMUsage:
    """Token usage from an LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LLMResult:
    """Result from an LLM text generation call."""

    text: str
    usage: LLMUsage = field(default_factory=LLMUsage)


@runtime_checkable
class LLMProvider(Protocol):
    """Abstract interface for LLM providers.

    Providers must implement both generate() for free-form text
    and generate_structured() for schema-validated structured output.
    """

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> LLMResult:
        """Generate a text completion."""
        ...

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[BaseModel],
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ) -> BaseModel:
        """Generate a structured (schema-validated) output.

        The provider is responsible for ensuring the output conforms
        to the given Pydantic model's schema.
        """
        ...
