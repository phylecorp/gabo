"""Evidence persistence: write EvidencePool artifacts and reconstruct them from pipeline output.

@decision DEC-EVIDENCE-003
@title Universal evidence persistence — build_evidence_pool reconstructs EvidencePool from artifacts
@status accepted
@rationale The quick-run path (POST /api/analysis) never persisted evidence.  Research results,
user text, and decomposition facts accumulated in config.evidence as a flat string but were never
saved as a structured EvidencePool.  Only the curated flow (POST /api/evidence/{session_id}/analyze)
persisted evidence via _persist_evidence().

This module provides two functions:

  persist_evidence(output_path, pool)
    — Extracted from evidence.py; writes evidence.json and patches manifest.json.
    — Caller should catch exceptions (best-effort).

  build_evidence_pool(output_path, question)
    — Reads pipeline artifact JSON files from output_path to reconstruct a structured EvidencePool.
    — Looks for ``*-research.json`` and ``*-decomposition.json`` artifacts written by ArtifactWriter.
    — Returns EvidencePool(status="ready") with whatever items were found.
    — Resilient: missing artifacts, malformed JSON, and missing directories all yield an empty pool
      rather than raising.

@decision DEC-EVIDENCE-004
@title artifact filename convention: {nn}-{technique_id}.json drives discovery
@status accepted
@rationale ArtifactWriter names files "{counter:02d}-{technique_id}.json". build_evidence_pool
uses glob("*-research.json") and glob("*-decomposition.json") to discover the relevant artifacts
without coupling to the counter prefix. This is forward-compatible: if a run has multiple research
passes (e.g. multi_runner producing separate files) they will all be picked up.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from sat.models.evidence import EvidenceItem, EvidencePool

logger = logging.getLogger(__name__)


def persist_evidence(output_path: Path, pool: EvidencePool) -> None:
    """Write the EvidencePool to evidence.json and update manifest.json.

    Writes ``evidence.json`` to *output_path* and then patches ``manifest.json``
    in the same directory to set ``evidence_path = "evidence.json"``.

    Called after run_analysis() completes with a known output_path. Errors
    from this function are best-effort — the caller logs and suppresses them so
    a persistence failure does not mask the real pipeline result.

    Args:
        output_path: Directory containing pipeline artifacts.
        pool: EvidencePool to persist.
    """
    evidence_file = output_path / "evidence.json"
    evidence_file.write_text(pool.model_dump_json(), encoding="utf-8")

    manifest_file = output_path / "manifest.json"
    if manifest_file.exists():
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        data["evidence_path"] = "evidence.json"
        manifest_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _normalize_confidence(raw: str) -> str:
    """Normalize confidence strings to Title Case (High/Medium/Low)."""
    mapping = {
        "high": "High",
        "medium": "Medium",
        "med": "Medium",
        "low": "Low",
    }
    return mapping.get(raw.lower(), raw.capitalize() if raw else "Medium")


def build_evidence_pool(output_path: Path, question: str) -> EvidencePool:
    """Reconstruct a structured EvidencePool from pipeline artifact files.

    Reads artifact JSON files written by ArtifactWriter from *output_path* and
    converts them into EvidenceItems. Looks for:

    - ``*-research.json``      → ResearchResult → EvidenceItems with source="research" (R- prefix)
    - ``*-decomposition.json`` → DecompositionResult → EvidenceItems with source="decomposition"
                                  (D- prefix)

    All artifact parsing is best-effort: malformed files, unexpected schemas, and
    I/O errors are logged and skipped so a partial or missing artifact set yields
    fewer items rather than raising.

    Args:
        output_path: Directory containing pipeline artifacts (the sat-{run_id} dir).
        question: The analytic question (stored on the returned pool).

    Returns:
        EvidencePool with all discovered items, sources, gaps, and status="ready".
        Returns an empty pool if output_path does not exist or no recognizable artifacts
        are found.
    """
    session_id = uuid.uuid4().hex[:12]
    items: list[EvidenceItem] = []
    sources: list[dict] = []
    gaps: list[str] = []

    if not output_path.exists():
        return EvidencePool(
            session_id=session_id,
            question=question,
            items=[],
            sources=[],
            gaps=[],
            status="ready",
        )

    # Discover research artifacts: *-research.json
    research_files = sorted(output_path.glob("*-research.json"))
    for artifact_file in research_files:
        try:
            research_items, research_sources, research_gaps = _load_research_artifact(
                artifact_file
            )
            items.extend(research_items)
            sources.extend(research_sources)
            gaps.extend(research_gaps)
        except Exception:
            logger.warning(
                "Failed to load research artifact %s — skipping", artifact_file, exc_info=True
            )

    # Discover decomposition artifacts: *-decomposition.json
    decomp_files = sorted(output_path.glob("*-decomposition.json"))
    for artifact_file in decomp_files:
        try:
            decomp_items = _load_decomposition_artifact(artifact_file)
            items.extend(decomp_items)
        except Exception:
            logger.warning(
                "Failed to load decomposition artifact %s — skipping", artifact_file, exc_info=True
            )

    return EvidencePool(
        session_id=session_id,
        question=question,
        items=items,
        sources=sources,
        gaps=gaps,
        status="ready",
    )


def _load_research_artifact(
    artifact_file: Path,
) -> tuple[list[EvidenceItem], list[dict], list[str]]:
    """Parse a research artifact JSON file into EvidenceItems, sources, and gaps.

    Args:
        artifact_file: Path to a ``*-research.json`` artifact file.

    Returns:
        Tuple of (items, sources_dicts, gaps).

    Raises:
        Exception: Any I/O or parse error — caller catches and skips.
    """
    from sat.models.research import ResearchResult

    raw = json.loads(artifact_file.read_text(encoding="utf-8"))

    # Validate this is actually a research artifact
    if raw.get("technique_id") != "research":
        return [], [], []

    result = ResearchResult.model_validate(raw)

    items: list[EvidenceItem] = []
    for n, claim in enumerate(result.claims, start=1):
        item = EvidenceItem(
            item_id=f"R-C{n}",
            claim=claim.claim,
            source="research",
            source_ids=list(claim.source_ids),
            category=claim.category,
            confidence=_normalize_confidence(claim.confidence),
            entities=[],
            verified=claim.verified,
            selected=True,
            provider_name=result.research_provider,
        )
        items.append(item)

    # Convert sources to plain dicts (matching gatherer.py format)
    sources_dicts = [
        {
            "id": s.id,
            "title": s.title,
            "url": s.url,
            "source_type": s.source_type,
            "reliability_assessment": s.reliability_assessment,
        }
        for s in result.sources
    ]

    return items, sources_dicts, list(result.gaps_identified)


def _load_decomposition_artifact(artifact_file: Path) -> list[EvidenceItem]:
    """Parse a decomposition artifact JSON file into EvidenceItems.

    Args:
        artifact_file: Path to a ``*-decomposition.json`` artifact file.

    Returns:
        List of EvidenceItems with source="decomposition" and D- item_id prefix.

    Raises:
        Exception: Any I/O or parse error — caller catches and skips.
    """
    from sat.models.decomposition import DecompositionResult

    raw = json.loads(artifact_file.read_text(encoding="utf-8"))

    # Validate this is actually a decomposition artifact
    if raw.get("technique_id") != "decomposition":
        return []

    result = DecompositionResult.model_validate(raw)

    items: list[EvidenceItem] = []
    for fact in result.facts:
        item = EvidenceItem(
            item_id=f"D-{fact.fact_id}",
            claim=fact.claim,
            source="decomposition",
            source_ids=list(fact.source_ids),
            category=fact.category,
            confidence=_normalize_confidence(fact.confidence),
            entities=list(fact.entities),
            verified=False,
            selected=True,
        )
        items.append(item)

    return items
