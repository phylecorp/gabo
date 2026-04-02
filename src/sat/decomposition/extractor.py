"""Atomic fact extraction from evidence text.

@decision DEC-DECOMP-004: Iterative chunked extraction with sequential fact numbering.
@title Evidence decomposition into atomic claims
@status accepted
@rationale Large evidence is chunked and processed iteratively. Each chunk sees prior
facts to avoid re-extraction. Facts get sequential IDs (F1, F2, ...). Output is
formatted as structured text that replaces config.evidence for downstream techniques.

@decision DEC-DECOMP-005: Parallel batch extraction replaces sequential chunk processing.
@title Batched asyncio.gather for chunk parallelism
@status accepted
@rationale Sequential extraction was the bottleneck for large evidence — each chunk
waited for the previous LLM call to complete. Chunks are now processed in parallel
batches of _DECOMP_BATCH_SIZE=4. Prior-facts context is dropped per chunk (was 20
recent facts) because the deduplication pass (line ~155) already handles overlapping
claims across chunks. This trades minor duplication increase for a 4x throughput
improvement on multi-chunk evidence. Failures in individual chunks are swallowed
per the existing graceful-degradation contract.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict

from pydantic import BaseModel, Field

from sat.config import DecompositionConfig
from sat.decomposition.deduplicator import deduplicate_facts
from sat.decomposition.prompts import build_decomposition_prompt
from sat.ingestion.parser import _generate_source_id
from sat.models.decomposition import AtomicFact, DecompositionResult
from sat.preprocessing.reducer import chunk_text

logger = logging.getLogger(__name__)

# Number of chunks to process concurrently. Higher values reduce wall-clock time
# but increase concurrent LLM API load. 4 is a conservative default that avoids
# rate-limit pressure while still delivering meaningful parallelism.
_DECOMP_BATCH_SIZE = 4

_SOURCE_MARKER = re.compile(r"^--- Source: (.+) ---$", re.MULTILINE)


class ChunkExtractionResult(BaseModel):
    """LLM structured output for a single chunk's fact extraction."""

    facts: list[AtomicFact] = Field(default_factory=list)


def _build_source_index(evidence: str) -> tuple[str, dict[str, str]]:
    """Parse source markers from evidence and build an index string.

    Returns:
        (source_index_str, name_to_id_map)
    """
    matches = _SOURCE_MARKER.findall(evidence)
    if not matches:
        # No markers — treat entire evidence as a single unnamed source
        return "- [inline]: inline evidence", {"inline": "inline"}

    name_to_id: dict[str, str] = {}
    lines: list[str] = []
    for name in matches:
        name = name.strip()
        if name not in name_to_id:
            sid = _generate_source_id(name)
            name_to_id[name] = sid
            lines.append(f"- [{sid}]: {name}")

    return "\n".join(lines), name_to_id


def _format_facts(facts: list[AtomicFact], source_index: str) -> str:
    """Render facts as a structured text block suitable for downstream prompts."""
    n = len(facts)
    # Count unique sources
    source_ids_seen: set[str] = set()
    for f in facts:
        source_ids_seen.update(f.source_ids)
    m = len(source_ids_seen)

    lines: list[str] = [
        f"[Decomposed Evidence: {n} atomic facts from {m} sources]",
        "",
        "## Facts",
        "",
    ]
    for fact in facts:
        src_str = ", ".join(fact.source_ids) if fact.source_ids else "unknown"
        lines.append(
            f"[{fact.fact_id}] {fact.claim} "
            f"(Source: {src_str}, Confidence: {fact.confidence}, Category: {fact.category})"
        )

    lines += [
        "",
        "## Source Index",
        "",
        source_index,
    ]

    # Build entity index
    entity_facts: dict[str, list[str]] = defaultdict(list)
    for fact in facts:
        for entity in fact.entities:
            entity_facts[entity].append(fact.fact_id)

    if entity_facts:
        lines += ["", "## Entity Index", ""]
        for entity in sorted(entity_facts):
            lines.append(f"{entity}: {', '.join(entity_facts[entity])}")

    return "\n".join(lines)


async def _extract_chunk(
    chunk: str,
    source_index_str: str,
    provider: object,
) -> list[AtomicFact]:
    """Extract facts from a single chunk, returning an empty list on failure.

    Prior-facts context is intentionally omitted — parallel batches cannot share
    sequential state. The deduplication pass in decompose_evidence cleans up any
    overlapping claims across chunks.
    """
    system_prompt, messages = build_decomposition_prompt(chunk, [], source_index_str)
    try:
        result: ChunkExtractionResult = await provider.generate_structured(  # type: ignore[union-attr]
            system_prompt=system_prompt,
            messages=messages,
            output_schema=ChunkExtractionResult,
        )
        return list(result.facts)
    except Exception as exc:
        logger.warning("Fact extraction failed for chunk: %s", exc)
        return []


async def decompose_evidence(
    evidence: str,
    provider: object,
    config: DecompositionConfig | None = None,
) -> DecompositionResult:
    """Decompose evidence text into atomic facts.

    Chunks large evidence, extracts facts from each chunk in parallel batches of
    _DECOMP_BATCH_SIZE, optionally deduplicates, and formats the result as
    structured text. Prior-facts context is dropped per chunk — the dedup pass
    handles overlapping claims across concurrent extractions.

    Args:
        evidence: The evidence text to decompose.
        provider: LLM provider implementing generate_structured().
        config: Decomposition configuration; defaults to DecompositionConfig(enabled=True).

    Returns:
        DecompositionResult with facts list, formatted evidence, and metadata.
    """
    if config is None:
        config = DecompositionConfig(enabled=True)

    source_index_str, _name_to_id = _build_source_index(evidence)
    chunks = chunk_text(evidence, config.chunk_tokens)

    all_facts: list[AtomicFact] = []
    fact_counter = 1

    # Process chunks in parallel batches; stop early if max_facts reached.
    for batch_start in range(0, len(chunks), _DECOMP_BATCH_SIZE):
        batch = chunks[batch_start : batch_start + _DECOMP_BATCH_SIZE]
        batch_results = await asyncio.gather(
            *[_extract_chunk(chunk, source_index_str, provider) for chunk in batch]
        )
        for facts in batch_results:
            for fact in facts:
                fact.fact_id = f"F{fact_counter}"
                fact_counter += 1
                all_facts.append(fact)

        if len(all_facts) >= config.max_facts:
            break

    all_facts = all_facts[: config.max_facts]

    duplicates_removed = 0
    if config.deduplicate and len(all_facts) >= 5:
        all_facts, duplicates_removed = await deduplicate_facts(all_facts, provider)

    source_ids_seen: set[str] = set()
    for f in all_facts:
        source_ids_seen.update(f.source_ids)

    formatted = _format_facts(all_facts, source_index_str)

    return DecompositionResult(
        facts=all_facts,
        total_facts=len(all_facts),
        total_sources=len(source_ids_seen),
        chunks_processed=len(chunks),
        duplicates_removed=duplicates_removed,
        formatted_evidence=formatted,
        summary=f"Extracted {len(all_facts)} atomic facts from {len(chunks)} chunk(s)",
        warnings=[],
    )
