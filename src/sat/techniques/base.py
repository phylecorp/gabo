"""Technique base class defining the interface all techniques implement.

@decision DEC-TECH-001: Thin technique classes with deterministic post-processing.
Each technique composes a prompt, calls generate_structured(), and optionally
post-processes. LLM handles analysis content; Python handles computation
(e.g., ACH inconsistency scores). build_prompt() is separate from execute()
so prompts can be tested independently.

@decision DEC-TECH-003: Per-technique max_tokens override via property.
Provider default of 4096 tokens is too low for token-heavy techniques like ACH,
which need 6000-8000+ tokens for a complete hypothesis matrix. A max_tokens
property on Technique (default None = use provider default) lets individual
techniques declare their needs without coupling the base class to any specific
limit. execute() passes it through to generate_structured() only when set,
leaving the default unchanged for techniques that don't override.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


from sat.models.base import ArtifactResult
from sat.providers.base import LLMMessage, LLMProvider


@dataclass
class TechniqueContext:
    """Input context for a technique execution."""

    question: str
    evidence: str | None = None
    prior_results: dict[str, ArtifactResult] = field(default_factory=dict)


@dataclass
class TechniqueMetadata:
    """Descriptive metadata for a technique."""

    id: str
    name: str
    category: str  # "diagnostic", "contrarian", "imaginative"
    description: str
    order: int  # execution priority within category (lower = earlier)
    dependencies: list[str] = field(default_factory=list)  # technique IDs this depends on


class Technique(ABC):
    """Base class for all structured analytic techniques."""

    @property
    @abstractmethod
    def metadata(self) -> TechniqueMetadata:
        """Return metadata describing this technique."""
        ...

    @property
    @abstractmethod
    def output_schema(self) -> type[ArtifactResult]:
        """Return the Pydantic model class for this technique's output."""
        ...

    @property
    def max_tokens(self) -> int | None:
        """Return the token budget for this technique's generate_structured call.

        Returns None to use the provider's default. Override in subclasses that
        need a larger context window (e.g. ACH with its large hypothesis matrix).
        """
        return None

    def build_prompt(self, ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
        """Build the system prompt and user messages for this technique.

        Returns (system_prompt, messages). Subclasses should override
        to incorporate technique-specific instructions and prior results.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement build_prompt()")

    def post_process(self, result: ArtifactResult) -> ArtifactResult:
        """Optional post-processing after LLM generation.

        Override for deterministic computations like ACH scoring.
        Default: return result unchanged.
        """
        return result

    async def execute(
        self,
        ctx: TechniqueContext,
        provider: LLMProvider,
    ) -> ArtifactResult:
        """Run this technique: build prompt, call LLM, post-process.

        This is the main entry point. Subclasses typically don't need
        to override this — override build_prompt() and post_process() instead.

        The framework enforces technique identity after LLM generation so that
        filenames and registry lookups always use the canonical registry ID
        (e.g. "assumptions") rather than whatever the LLM may have generated
        (e.g. "KAC-001"). See @decision DEC-TECH-002.
        """
        system_prompt, messages = self.build_prompt(ctx)
        kwargs: dict = {
            "system_prompt": system_prompt,
            "messages": messages,
            "output_schema": self.output_schema,
        }
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        result = await provider.generate_structured(**kwargs)
        result = self.post_process(result)
        # Framework controls identity — not the LLM.
        # @decision DEC-TECH-002: Override LLM-generated technique_id/name.
        # The LLM may produce arbitrary strings (e.g. "KAC-001") for these
        # fields. We overwrite them with authoritative metadata values so that
        # downstream code (artifact filenames, registry lookups, manifest) is
        # always consistent and predictable.
        result = result.model_copy(
            update={
                "technique_id": self.metadata.id,
                "technique_name": self.metadata.name,
            }
        )
        return result
