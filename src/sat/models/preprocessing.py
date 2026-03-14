"""Evidence preprocessing models.

@decision DEC-PREPROC-001: Evidence preprocessing with format detection and token budgeting.
@title Evidence preprocessor models
@status accepted
@rationale Evidence comes in diverse formats (CSV, JSON, logs, multi-file). The preprocessor
detects format, measures token cost, and reduces oversized input via LLM-driven summarization.
Models capture the preprocessing pipeline's inputs and outputs for artifact tracking.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from sat.models.base import ArtifactResult


class EvidenceFormat(str, Enum):
    """Detected format of evidence input."""

    PLAIN_TEXT = "plain_text"
    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"
    LOG_FILE = "log_file"
    MULTI_FILE = "multi_file"
    DECOMPOSED = "decomposed"


class PreprocessingResult(ArtifactResult):
    """Result of evidence preprocessing pipeline."""

    original_format: EvidenceFormat = Field(description="Detected format of the raw evidence")
    original_estimated_tokens: int = Field(description="Estimated tokens in the raw evidence")
    reduction_applied: str = Field(
        description="Type of reduction: none, format_conversion, map_reduce"
    )
    output_estimated_tokens: int = Field(description="Estimated tokens in the processed evidence")
    formatted_evidence: str = Field(
        description="The processed evidence text for downstream techniques"
    )
    sources_preserved: list[str] = Field(
        default_factory=list,
        description="Source file names preserved from multi-file input",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Any warnings generated during preprocessing",
    )
