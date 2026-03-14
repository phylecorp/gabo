"""Evidence reducer: converts and/or compresses evidence to fit token budget.

@decision DEC-PREPROC-005: Two-tier reduction: format conversion and map-reduce.
@title LLM-driven evidence reduction
@status accepted
@rationale Small structured data (CSV, JSON, logs) benefits from format conversion
to narrative even when under budget. Oversized data requires map-reduce: split into
chunks, summarize each in parallel, merge. Capped at 2 reduction rounds to prevent
infinite loops — truncate with warning if still over budget.
"""

from __future__ import annotations

import asyncio
import logging

from sat.models.preprocessing import EvidenceFormat
from sat.preprocessing.measurer import calculate_budget, estimate_tokens
from sat.prompts.preprocessing import MERGE_SYSTEM_PROMPT, get_system_prompt
from sat.providers.base import LLMMessage, LLMProvider

logger = logging.getLogger(__name__)


def chunk_text(text: str, max_chunk_tokens: int = 50_000, overlap_chars: int = 500) -> list[str]:
    """Split text into chunks of approximately max_chunk_tokens.

    Uses paragraph boundaries when possible. Adds overlap between chunks
    to preserve context at boundaries.
    """
    max_chars = max_chunk_tokens * 4  # Convert token estimate to chars

    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + max_chars

        if end >= len(text):
            chunks.append(text[start:])
            break

        # Try to break at paragraph boundary
        boundary = text.rfind("\n\n", start + max_chars // 2, end)
        if boundary == -1:
            # Fall back to line boundary
            boundary = text.rfind("\n", start + max_chars // 2, end)
        if boundary == -1:
            # Fall back to hard cut
            boundary = end

        chunks.append(text[start:boundary])
        # Overlap: back up a bit for context continuity
        start = max(boundary - overlap_chars, start + 1)

    return chunks


async def reduce_format_conversion(
    text: str,
    fmt: EvidenceFormat,
    provider: LLMProvider,
) -> str:
    """Convert structured evidence to narrative via a single LLM call."""
    system_prompt = get_system_prompt(fmt)
    result = await provider.generate(
        system_prompt=system_prompt,
        messages=[LLMMessage(role="user", content=text)],
        max_tokens=8192,
    )
    return result.text


async def reduce_map_reduce(
    text: str,
    fmt: EvidenceFormat,
    provider: LLMProvider,
    provider_name: str,
    budget_fraction: float = 0.4,
    max_chunk_tokens: int = 50_000,
) -> tuple[str, list[str]]:
    """Reduce oversized evidence via map-reduce.

    Returns (reduced_text, warnings).
    """
    warnings: list[str] = []
    budget = calculate_budget(provider_name, budget_fraction)
    system_prompt = get_system_prompt(fmt)

    current_text = text

    for round_num in range(2):  # Cap at 2 rounds
        chunks = chunk_text(current_text, max_chunk_tokens)
        logger.info(
            "Map-reduce round %d: %d chunks, ~%d tokens",
            round_num + 1,
            len(chunks),
            estimate_tokens(current_text),
        )

        if len(chunks) == 1:
            # Single chunk — just summarize directly
            result = await provider.generate(
                system_prompt=system_prompt,
                messages=[LLMMessage(role="user", content=chunks[0])],
                max_tokens=8192,
            )
            current_text = result.text
        else:
            # Map: summarize each chunk in parallel
            tasks = [
                provider.generate(
                    system_prompt=system_prompt,
                    messages=[
                        LLMMessage(
                            role="user",
                            content=f"[Section {i + 1} of {len(chunks)}]\n\n{chunk}",
                        )
                    ],
                    max_tokens=8192,
                )
                for i, chunk in enumerate(chunks)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect successful summaries
            summaries = []
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    logger.warning("Chunk %d summarization failed: %s", i + 1, r)
                    warnings.append(f"Chunk {i + 1} summarization failed: {r}")
                else:
                    summaries.append(f"## Section {i + 1}\n\n{r.text}")

            if not summaries:
                warnings.append("All chunk summarizations failed, using truncated original")
                current_text = text[: budget * 4]  # Truncate to budget
                break

            merged_sections = "\n\n---\n\n".join(summaries)

            # Reduce: merge summaries
            merge_result = await provider.generate(
                system_prompt=MERGE_SYSTEM_PROMPT,
                messages=[LLMMessage(role="user", content=merged_sections)],
                max_tokens=8192,
            )
            current_text = merge_result.text

        # Check if we're under budget now
        if estimate_tokens(current_text) <= budget:
            break
    else:
        # Still over budget after 2 rounds — truncate with warning
        if estimate_tokens(current_text) > budget:
            truncate_chars = budget * 4
            current_text = current_text[:truncate_chars]
            warnings.append(
                f"Evidence still over budget after 2 reduction rounds. "
                f"Truncated to ~{budget} tokens."
            )

    return current_text, warnings
