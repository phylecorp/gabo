"""Evidence lineage tracking: records transformations through the pipeline.

@decision DEC-EVIDENCE-005
@title Evidence lineage chain with content hashes and transformation metadata
@status accepted
@rationale Evidence undergoes up to 5 transformations (ingestion, decomposition,
preprocessing, research merge). Without lineage tracking, there's no record of what
each stage produced. The lineage chain records content hashes, character counts, and
stage-specific metadata at each step, persisted as evidence-lineage.json for
post-hoc debugging and auditability.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class LineageEntry(BaseModel):
    """A single evidence transformation step."""

    stage: str = Field(
        description="Transformation stage: initial, ingestion, decomposition, preprocessing, research_merge"
    )
    content_hash: str = Field(description="SHA-256 hash of the evidence text after this stage (first 16 hex chars)")
    char_count: int = Field(description="Character count of evidence after this stage")
    timestamp: str = Field(description="ISO timestamp when this transformation occurred")
    metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        description="Stage-specific metadata (e.g., facts_extracted, tokens_reduced, sources_merged)",
    )


class EvidenceLineage(BaseModel):
    """Complete evidence transformation history for a pipeline run.

    Usage:
        lineage = EvidenceLineage(run_id=run_id)
        lineage.record("initial", config.evidence)
        # ... after each pipeline transformation ...
        lineage.record("ingestion", config.evidence, documents=3)
        lineage.write(output_dir)
    """

    run_id: str = Field(description="Pipeline run ID")
    entries: list[LineageEntry] = Field(default_factory=list)

    def record(
        self,
        stage: str,
        evidence: str | None,
        **metadata: str | int | float | bool,
    ) -> None:
        """Record an evidence transformation step.

        Args:
            stage: Name of the transformation stage (e.g. "initial", "ingestion").
            evidence: The evidence text after this transformation. None is treated as empty.
            **metadata: Stage-specific key-value pairs (str, int, float, or bool only).
        """
        text = evidence or ""
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        self.entries.append(
            LineageEntry(
                stage=stage,
                content_hash=content_hash,
                char_count=len(text),
                timestamp=datetime.now(timezone.utc).isoformat(),
                metadata=dict(metadata),
            )
        )

    def write(self, output_dir: Path) -> Path:
        """Persist lineage to evidence-lineage.json in the output directory.

        Creates the directory if it does not exist. Always writes even when
        the lineage has no entries (e.g. when evidence is None throughout).

        Args:
            output_dir: Directory to write the JSON file into.

        Returns:
            Path to the written evidence-lineage.json file.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "evidence-lineage.json"
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return path
