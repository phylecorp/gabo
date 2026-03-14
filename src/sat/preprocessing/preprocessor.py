"""Evidence preprocessor orchestrator: detect -> measure -> reduce -> format.

@decision DEC-PREPROC-006: Preprocessing orchestrator with passthrough optimization.
@title Evidence preprocessor orchestrator
@status accepted
@rationale The preprocessor runs between provider creation and Phase 0 (research).
Plain text under budget is a no-op passthrough (zero overhead). Structured formats
(CSV, JSON, logs) get format conversion even when under budget. Oversized data
gets map-reduce. The result is written as an artifact for provenance tracking.
"""

from __future__ import annotations

import logging
import re

from sat.config import PreprocessingConfig
from sat.models.preprocessing import EvidenceFormat, PreprocessingResult
from sat.preprocessing.detector import detect_format
from sat.preprocessing.measurer import estimate_tokens, needs_reduction
from sat.preprocessing.reducer import reduce_format_conversion, reduce_map_reduce
from sat.providers.base import LLMProvider

logger = logging.getLogger(__name__)

# Formats that benefit from conversion even when under budget
_STRUCTURED_FORMATS = {
    EvidenceFormat.CSV,
    EvidenceFormat.JSON,
    EvidenceFormat.JSONL,
    EvidenceFormat.LOG_FILE,
}

_SOURCE_MARKER = re.compile(r"--- Source: (.+?) ---")


def _extract_sources(text: str) -> list[str]:
    """Extract source file names from multi-file evidence markers."""
    return _SOURCE_MARKER.findall(text)


def _add_provenance_header(
    text: str,
    fmt: EvidenceFormat,
    reduction: str,
    sources: list[str],
) -> str:
    """Add metadata header noting original format and reduction applied."""
    parts = [f"[Evidence preprocessed: format={fmt.value}, reduction={reduction}]"]
    if sources:
        parts.append(f"[Sources: {', '.join(sources)}]")
    parts.append("")
    parts.append(text)
    return "\n".join(parts)


async def preprocess_evidence(
    evidence: str,
    provider: LLMProvider,
    provider_name: str,
    config: PreprocessingConfig,
) -> PreprocessingResult:
    """Run the full preprocessing pipeline on evidence text.

    Returns PreprocessingResult with formatted_evidence for downstream techniques.
    Passthrough (no LLM calls) when evidence is plain text under budget.
    """
    # 1. Detect format
    if config.force_format:
        try:
            fmt = EvidenceFormat(config.force_format)
        except ValueError:
            logger.warning(
                "Unknown force_format %r, falling back to auto-detect", config.force_format
            )
            fmt = detect_format(evidence)
    else:
        fmt = detect_format(evidence)

    original_tokens = estimate_tokens(evidence)
    sources = _extract_sources(evidence) if fmt == EvidenceFormat.MULTI_FILE else []
    over_budget = needs_reduction(evidence, provider_name, config.budget_fraction)

    logger.info(
        "Evidence preprocessing: format=%s, tokens=%d, over_budget=%s",
        fmt.value,
        original_tokens,
        over_budget,
    )

    # 2. Decide what to do
    warnings: list[str] = []

    if not over_budget and fmt not in _STRUCTURED_FORMATS:
        # Plain text under budget -- passthrough (no LLM calls)
        formatted = evidence
        reduction = "none"
    elif not over_budget and fmt in _STRUCTURED_FORMATS:
        # Structured format under budget -- convert to narrative
        formatted = await reduce_format_conversion(evidence, fmt, provider)
        reduction = "format_conversion"
    else:
        # Over budget -- map-reduce
        formatted, mr_warnings = await reduce_map_reduce(
            text=evidence,
            fmt=fmt,
            provider=provider,
            provider_name=provider_name,
            budget_fraction=config.budget_fraction,
            max_chunk_tokens=config.max_chunk_tokens,
        )
        warnings.extend(mr_warnings)
        reduction = "map_reduce"

    # 3. Add provenance header
    formatted = _add_provenance_header(formatted, fmt, reduction, sources)

    output_tokens = estimate_tokens(formatted)

    return PreprocessingResult(
        technique_id="preprocessing",
        technique_name="Evidence Preprocessing",
        summary=f"Preprocessed {fmt.value} evidence ({original_tokens} -> {output_tokens} est. tokens, {reduction})",
        original_format=fmt,
        original_estimated_tokens=original_tokens,
        reduction_applied=reduction,
        output_estimated_tokens=output_tokens,
        formatted_evidence=formatted,
        sources_preserved=sources,
        warnings=warnings,
    )
