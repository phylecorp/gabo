"""Token estimation and budget calculation for evidence preprocessing.

@decision DEC-PREPROC-003: Character-based token estimation with provider context windows.
@title Conservative token budgeting
@status accepted
@rationale Exact tokenization requires provider-specific tokenizers. Character/4 is a
conservative estimate (real tokens are ~3.5 chars). Budget fraction of 0.4 leaves room
for system prompt, output schema, technique prompts, and prior results.
"""

from __future__ import annotations


PROVIDER_CONTEXT_WINDOWS = {
    "anthropic": 200_000,
    "openai": 200_000,
    "gemini": 1_000_000,
}

DEFAULT_CONTEXT_WINDOW = 200_000


def estimate_tokens(text: str) -> int:
    """Estimate token count from text using character/4 heuristic."""
    return len(text) // 4


def get_context_window(provider_name: str) -> int:
    """Get context window size for a provider."""
    return PROVIDER_CONTEXT_WINDOWS.get(provider_name, DEFAULT_CONTEXT_WINDOW)


def calculate_budget(provider_name: str, budget_fraction: float = 0.4) -> int:
    """Calculate the token budget for evidence based on provider context window.

    Returns the max estimated tokens allowed for evidence.
    """
    window = get_context_window(provider_name)
    return int(window * budget_fraction)


def needs_reduction(text: str, provider_name: str, budget_fraction: float = 0.4) -> bool:
    """Check if evidence exceeds the token budget and needs reduction."""
    tokens = estimate_tokens(text)
    budget = calculate_budget(provider_name, budget_fraction)
    return tokens > budget
