"""Evidence format detection via heuristics.

@decision DEC-PREPROC-002: Heuristic format detection without LLM calls.
@title Fast format detection
@status accepted
@rationale Format detection runs on every evidence input and must be fast/free.
Heuristics are ordered by specificity: multi-file markers first (most specific),
then JSON (starts with { or [), JSONL, CSV/TSV (delimiter counting), log files
(timestamp patterns), plain text (fallback). No false positives are preferred
over no false negatives — misdetection as plain text is safe (passthrough).
"""

from __future__ import annotations

import re

from sat.models.preprocessing import EvidenceFormat

# Patterns
_LOG_TIMESTAMP = re.compile(
    r"^\[?\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}"  # ISO-ish timestamps
    r"|^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"  # syslog format: Jan  1 00:00:00
)
_LOG_LEVEL = re.compile(r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b", re.IGNORECASE)
_MULTI_FILE_MARKER = re.compile(r"^--- Source: .+ ---$", re.MULTILINE)
_DECOMPOSED_MARKER = re.compile(r"^\[Decomposed Evidence:", re.MULTILINE)


def detect_format(text: str) -> EvidenceFormat:
    """Detect the format of evidence text using heuristics.

    Returns EvidenceFormat enum. Defaults to PLAIN_TEXT if no specific format detected.
    """
    if not text or not text.strip():
        return EvidenceFormat.PLAIN_TEXT

    # Decomposed: check for [Decomposed Evidence: marker (most specific — passthrough)
    if _DECOMPOSED_MARKER.search(text):
        return EvidenceFormat.DECOMPOSED

    # Multi-file: check for --- Source: markers
    if _MULTI_FILE_MARKER.search(text):
        return EvidenceFormat.MULTI_FILE

    stripped = text.strip()

    # JSON: starts with { or [
    if stripped[0] in "{[":
        # Check if it's JSONL (multiple JSON objects, one per line)
        lines = [line for line in stripped.splitlines() if line.strip()]
        if len(lines) >= 3 and all(line.strip().startswith("{") for line in lines[:10]):
            return EvidenceFormat.JSONL
        return EvidenceFormat.JSON

    # CSV/TSV: consistent delimiter count across first 5 non-empty lines
    lines = [line for line in stripped.splitlines() if line.strip()]
    if len(lines) >= 2:
        for delimiter in (",", "\t"):
            counts = [line.count(delimiter) for line in lines[:5]]
            if counts[0] >= 2 and len(set(counts)) == 1:
                return EvidenceFormat.CSV

    # Log file: timestamp or log level patterns in first 10 lines
    if len(lines) >= 3:
        log_score = 0
        for line in lines[:10]:
            if _LOG_TIMESTAMP.search(line):
                log_score += 1
            elif _LOG_LEVEL.search(line):
                log_score += 1
        if log_score >= 3:
            return EvidenceFormat.LOG_FILE

    return EvidenceFormat.PLAIN_TEXT
