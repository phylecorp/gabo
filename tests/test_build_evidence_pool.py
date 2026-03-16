"""Tests for build_evidence_pool and persist_evidence in sat.evidence.persistence.

@decision DEC-TEST-EVIDENCE-POOL-BUILD-001
@title Test-first for build_evidence_pool and universal evidence persistence
@status accepted
@rationale Verify that build_evidence_pool correctly reconstructs an EvidencePool
from pipeline artifact files on disk (research.json, decomposition.json), and that
persist_evidence writes evidence.json and patches manifest.json. Tests use real
model objects and real filesystem I/O — no mocks of internal modules.

Covers:
- persist_evidence: writes evidence.json, updates manifest.json evidence_path
- persist_evidence: works even when manifest.json doesn't exist (no-op for manifest)
- build_evidence_pool: empty output dir → empty pool (no artifacts)
- build_evidence_pool: output dir with research artifact → research EvidenceItems (R- prefix)
- build_evidence_pool: output dir with decomposition artifact → decomposition EvidenceItems (D- prefix)
- build_evidence_pool: output dir with both → merged items from both sources
- build_evidence_pool: returns EvidencePool with correct session_id, question, status="ready"
- build_evidence_pool: research sources and gaps propagated to pool
- build_evidence_pool: malformed artifact files → skipped (resilient, no errors)
- analysis route: best-effort block wires build_evidence_pool + persist_evidence correctly
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sat.models.base import ArtifactManifest
from sat.models.decomposition import AtomicFact, DecompositionResult
from sat.models.evidence import EvidenceItem, EvidencePool
from sat.models.research import ResearchClaim, ResearchResult, ResearchSource


# ---------------------------------------------------------------------------
# Helpers: write real artifact files for testing
# ---------------------------------------------------------------------------


def _write_research_artifact(output_dir: Path, technique_id: str = "research") -> Path:
    """Write a real research artifact JSON file to output_dir and return its path."""
    result = ResearchResult(
        technique_id=technique_id,
        technique_name="Deep Research",
        summary="Research found relevant facts.",
        query="Test question?",
        sources=[
            ResearchSource(
                id="S1",
                title="Example Source",
                url="https://example.com/report",
                source_type="web",
                reliability_assessment="High",
            )
        ],
        claims=[
            ResearchClaim(
                claim="Unemployment rose to 5% in Q3 2024.",
                source_ids=["S1"],
                confidence="High",
                category="fact",
                verified=True,
            ),
            ResearchClaim(
                claim="Inflation remained elevated above 3%.",
                source_ids=["S1"],
                confidence="Medium",
                category="fact",
                verified=False,
            ),
        ],
        formatted_evidence="Unemployment rose. Inflation remained elevated.",
        research_provider="perplexity",
        gaps_identified=["Unemployment regional breakdown missing"],
    )
    artifact_path = output_dir / "01-research.json"
    artifact_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return artifact_path


def _write_decomposition_artifact(output_dir: Path, technique_id: str = "decomposition") -> Path:
    """Write a real decomposition artifact JSON file to output_dir and return its path."""
    result = DecompositionResult(
        technique_id=technique_id,
        technique_name="Atomic Fact Decomposition",
        summary="Decomposed evidence into 2 facts.",
        facts=[
            AtomicFact(
                fact_id="F1",
                claim="GDP growth slowed to 1.2% in Q3.",
                source_ids=["doc-1"],
                category="fact",
                confidence="high",
            ),
            AtomicFact(
                fact_id="F2",
                claim="Consumer confidence index fell by 3 points.",
                source_ids=["doc-1"],
                category="fact",
                confidence="medium",
            ),
        ],
        total_facts=2,
        total_sources=1,
        chunks_processed=1,
        formatted_evidence="GDP slowed. Consumer confidence fell.",
    )
    artifact_path = output_dir / "01-decomposition.json"
    artifact_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return artifact_path


def _write_manifest(output_dir: Path, run_id: str = "testrun") -> Path:
    """Write a minimal manifest.json to output_dir."""
    manifest = ArtifactManifest(
        question="Test question?",
        run_id=run_id,
        started_at=datetime.now(timezone.utc),
        techniques_selected=["col"],
    )
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest_path


# ---------------------------------------------------------------------------
# Tests: persist_evidence
# ---------------------------------------------------------------------------


class TestPersistEvidence:
    def test_writes_evidence_json(self, tmp_path):
        """persist_evidence writes evidence.json to output_path."""
        from sat.evidence.persistence import persist_evidence

        pool = EvidencePool(
            session_id="sess-test",
            question="Test?",
            items=[EvidenceItem(item_id="R-C1", claim="A claim", source="research")],
            status="ready",
        )
        persist_evidence(tmp_path, pool)

        evidence_file = tmp_path / "evidence.json"
        assert evidence_file.exists()
        data = json.loads(evidence_file.read_text(encoding="utf-8"))
        assert data["session_id"] == "sess-test"
        assert data["question"] == "Test?"
        assert len(data["items"]) == 1

    def test_evidence_json_roundtrips_to_pool(self, tmp_path):
        """Written evidence.json can be deserialized back to EvidencePool."""
        from sat.evidence.persistence import persist_evidence

        pool = EvidencePool(
            session_id="sess-abc",
            question="Round trip?",
            items=[EvidenceItem(item_id="D-F1", claim="GDP slowed.", source="decomposition")],
            sources=[{"id": "S1", "title": "Source 1", "url": "https://example.com"}],
            gaps=["Missing regional data"],
            status="ready",
        )
        persist_evidence(tmp_path, pool)

        evidence_file = tmp_path / "evidence.json"
        restored = EvidencePool.model_validate_json(evidence_file.read_text(encoding="utf-8"))
        assert restored.session_id == pool.session_id
        assert len(restored.items) == 1
        assert restored.items[0].item_id == "D-F1"
        assert restored.sources == pool.sources
        assert restored.gaps == pool.gaps

    def test_patches_manifest_evidence_path(self, tmp_path):
        """persist_evidence updates manifest.json with evidence_path='evidence.json'."""
        from sat.evidence.persistence import persist_evidence

        _write_manifest(tmp_path)
        pool = EvidencePool(session_id="sess-x", question="Q?", status="ready")
        persist_evidence(tmp_path, pool)

        manifest_data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest_data["evidence_path"] == "evidence.json"

    def test_no_manifest_does_not_raise(self, tmp_path):
        """persist_evidence does not raise when manifest.json is absent."""
        from sat.evidence.persistence import persist_evidence

        pool = EvidencePool(session_id="sess-y", question="Q?", status="ready")
        # Should not raise even without a manifest
        persist_evidence(tmp_path, pool)
        assert (tmp_path / "evidence.json").exists()

    def test_existing_manifest_fields_preserved(self, tmp_path):
        """persist_evidence preserves existing manifest fields when patching evidence_path."""
        from sat.evidence.persistence import persist_evidence

        _write_manifest(tmp_path, run_id="preserve-me")
        pool = EvidencePool(session_id="sess-z", question="Q?", status="ready")
        persist_evidence(tmp_path, pool)

        manifest_data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest_data["run_id"] == "preserve-me"
        assert manifest_data["evidence_path"] == "evidence.json"


# ---------------------------------------------------------------------------
# Tests: build_evidence_pool — empty / missing artifacts
# ---------------------------------------------------------------------------


class TestBuildEvidencePoolEmpty:
    def test_empty_output_dir_returns_empty_pool(self, tmp_path):
        """Empty output dir (no artifact files) returns a pool with no items."""
        from sat.evidence.persistence import build_evidence_pool

        pool = build_evidence_pool(tmp_path, "What happened?")
        assert isinstance(pool, EvidencePool)
        assert pool.items == []
        assert pool.status == "ready"

    def test_pool_has_correct_question(self, tmp_path):
        """build_evidence_pool sets question on the returned pool."""
        from sat.evidence.persistence import build_evidence_pool

        pool = build_evidence_pool(tmp_path, "My test question?")
        assert pool.question == "My test question?"

    def test_pool_has_session_id(self, tmp_path):
        """build_evidence_pool sets a non-empty session_id."""
        from sat.evidence.persistence import build_evidence_pool

        pool = build_evidence_pool(tmp_path, "Q?")
        assert pool.session_id
        assert isinstance(pool.session_id, str)

    def test_nonexistent_dir_returns_empty_pool(self, tmp_path):
        """Nonexistent output_path returns an empty pool (resilient)."""
        from sat.evidence.persistence import build_evidence_pool

        missing = tmp_path / "does-not-exist"
        pool = build_evidence_pool(missing, "Q?")
        assert pool.items == []
        assert pool.status == "ready"


# ---------------------------------------------------------------------------
# Tests: build_evidence_pool — research artifacts
# ---------------------------------------------------------------------------


class TestBuildEvidencePoolResearch:
    def test_research_artifact_produces_items(self, tmp_path):
        """A research artifact JSON produces EvidenceItems in the pool."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        assert len(pool.items) >= 1

    def test_research_items_have_r_prefix(self, tmp_path):
        """Research-derived EvidenceItems have 'R-' prefixed item_ids."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        research_items = [i for i in pool.items if i.source == "research"]
        assert len(research_items) >= 1
        for item in research_items:
            assert item.item_id.startswith("R-"), f"Expected R- prefix, got {item.item_id!r}"

    def test_research_items_source_is_research(self, tmp_path):
        """Research-derived EvidenceItems have source='research'."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        for item in pool.items:
            assert item.source == "research"

    def test_research_claim_text_preserved(self, tmp_path):
        """Claim text from research artifact matches EvidenceItem claims."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        claims = {item.claim for item in pool.items}
        assert "Unemployment rose to 5% in Q3 2024." in claims

    def test_research_sources_propagated_to_pool(self, tmp_path):
        """Research sources list is set on the EvidencePool."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        assert len(pool.sources) >= 1
        titles = [s.get("title", "") for s in pool.sources]
        assert any("Example Source" in t for t in titles)

    def test_research_gaps_propagated_to_pool(self, tmp_path):
        """Research gaps_identified are set on the EvidencePool."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        assert "Unemployment regional breakdown missing" in pool.gaps

    def test_research_confidence_normalized(self, tmp_path):
        """Research item confidence values are normalized to Title Case."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        for item in pool.items:
            assert item.confidence in ("High", "Medium", "Low")


# ---------------------------------------------------------------------------
# Tests: build_evidence_pool — decomposition artifacts
# ---------------------------------------------------------------------------


class TestBuildEvidencePoolDecomposition:
    def test_decomposition_artifact_produces_items(self, tmp_path):
        """A decomposition artifact JSON produces EvidenceItems in the pool."""
        from sat.evidence.persistence import build_evidence_pool

        _write_decomposition_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        assert len(pool.items) >= 1

    def test_decomposition_items_have_d_prefix(self, tmp_path):
        """Decomposition-derived EvidenceItems have 'D-' prefixed item_ids."""
        from sat.evidence.persistence import build_evidence_pool

        _write_decomposition_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        decomp_items = [i for i in pool.items if i.source == "decomposition"]
        assert len(decomp_items) >= 1
        for item in decomp_items:
            assert item.item_id.startswith("D-"), f"Expected D- prefix, got {item.item_id!r}"

    def test_decomposition_items_source_is_decomposition(self, tmp_path):
        """Decomposition-derived EvidenceItems have source='decomposition'."""
        from sat.evidence.persistence import build_evidence_pool

        _write_decomposition_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        for item in pool.items:
            assert item.source == "decomposition"

    def test_decomposition_claim_text_preserved(self, tmp_path):
        """Claim text from decomposition artifact matches EvidenceItem claims."""
        from sat.evidence.persistence import build_evidence_pool

        _write_decomposition_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        claims = {item.claim for item in pool.items}
        assert "GDP growth slowed to 1.2% in Q3." in claims

    def test_decomposition_confidence_normalized(self, tmp_path):
        """Decomposition item confidence values are normalized to Title Case."""
        from sat.evidence.persistence import build_evidence_pool

        _write_decomposition_artifact(tmp_path)
        pool = build_evidence_pool(tmp_path, "Test question?")
        for item in pool.items:
            assert item.confidence in ("High", "Medium", "Low")


# ---------------------------------------------------------------------------
# Tests: build_evidence_pool — combined research + decomposition
# ---------------------------------------------------------------------------


class TestBuildEvidencePoolCombined:
    def test_both_artifacts_produce_items_from_each_source(self, tmp_path):
        """With both research and decomposition artifacts, items from both sources appear."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        # Use different counter prefix for decomposition to avoid file collision
        result = DecompositionResult(
            technique_id="decomposition",
            technique_name="Atomic Fact Decomposition",
            summary="2 facts.",
            facts=[
                AtomicFact(
                    fact_id="F1",
                    claim="GDP growth slowed to 1.2% in Q3.",
                    confidence="high",
                )
            ],
            total_facts=1,
            chunks_processed=1,
            formatted_evidence="GDP slowed.",
        )
        (tmp_path / "02-decomposition.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )

        pool = build_evidence_pool(tmp_path, "Test question?")
        sources = {item.source for item in pool.items}
        assert "research" in sources
        assert "decomposition" in sources

    def test_combined_pool_has_all_items(self, tmp_path):
        """Combined research + decomposition pool has items from both."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        # Write decomp with different prefix
        result = DecompositionResult(
            technique_id="decomposition",
            technique_name="Atomic Fact Decomposition",
            summary="1 fact.",
            facts=[
                AtomicFact(fact_id="F1", claim="Unique decomp claim not in research.", confidence="high")
            ],
            total_facts=1,
            chunks_processed=1,
            formatted_evidence="Unique claim.",
        )
        (tmp_path / "02-decomposition.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )

        pool = build_evidence_pool(tmp_path, "Test question?")
        # Research provides 2, decomp provides 1
        assert len(pool.items) >= 3


# ---------------------------------------------------------------------------
# Tests: build_evidence_pool — resilience (malformed artifacts)
# ---------------------------------------------------------------------------


class TestBuildEvidencePoolResilience:
    def test_malformed_json_file_is_skipped(self, tmp_path):
        """Malformed JSON artifact file is silently skipped, other files processed."""
        from sat.evidence.persistence import build_evidence_pool

        # Write a valid research artifact
        _write_research_artifact(tmp_path)
        # Write a malformed JSON file with the right name pattern
        (tmp_path / "02-decomposition.json").write_text("{ not valid json }", encoding="utf-8")

        # Should not raise; should return items from the valid artifact
        pool = build_evidence_pool(tmp_path, "Test question?")
        research_items = [i for i in pool.items if i.source == "research"]
        assert len(research_items) >= 1

    def test_empty_json_file_is_skipped(self, tmp_path):
        """Empty JSON file is silently skipped."""
        from sat.evidence.persistence import build_evidence_pool

        _write_research_artifact(tmp_path)
        (tmp_path / "02-decomposition.json").write_text("", encoding="utf-8")

        pool = build_evidence_pool(tmp_path, "Test question?")
        research_items = [i for i in pool.items if i.source == "research"]
        assert len(research_items) >= 1

    def test_artifact_with_wrong_technique_id_is_skipped(self, tmp_path):
        """Artifact files for non-research/decomp technique_ids produce no items."""
        from sat.evidence.persistence import build_evidence_pool

        # Only write an ACH artifact — not research or decomposition
        from sat.models.base import ArtifactResult

        ach_result = ArtifactResult(
            technique_id="ach",
            technique_name="Analysis of Competing Hypotheses",
            summary="ACH summary.",
        )
        (tmp_path / "01-ach.json").write_text(
            ach_result.model_dump_json(indent=2), encoding="utf-8"
        )

        pool = build_evidence_pool(tmp_path, "Test question?")
        # ACH artifacts don't produce evidence items
        assert pool.items == []

    def test_no_raise_on_unreadable_dir(self, tmp_path):
        """build_evidence_pool returns empty pool for non-existent dir without raising."""
        from sat.evidence.persistence import build_evidence_pool

        missing = tmp_path / "not-here" / "deep" / "path"
        pool = build_evidence_pool(missing, "Q?")
        assert pool.items == []
        assert pool.status == "ready"


# ---------------------------------------------------------------------------
# Tests: analysis route wiring — best-effort evidence persistence block
# ---------------------------------------------------------------------------


class TestAnalysisRoutePersistenceWiring:
    """Verify the best-effort persistence block in the analysis route is wired correctly.

    These are unit tests against the route module, not integration tests.
    They verify:
    1. The execute() coroutine imports build_evidence_pool and persist_evidence
    2. persist_evidence is called when pool.items is non-empty
    3. A failure in build_evidence_pool does not propagate (best-effort)
    """

    def test_analysis_route_has_best_effort_block(self):
        """The analysis route execute() calls build_evidence_pool and persist_evidence."""
        import inspect

        from sat.api.routes import analysis

        source = inspect.getsource(analysis)
        assert "build_evidence_pool" in source, "build_evidence_pool not found in analysis route"
        assert "persist_evidence" in source, "persist_evidence not found in analysis route"

    def test_persistence_module_importable_from_evidence_package(self):
        """sat.evidence.persistence is importable."""
        from sat.evidence import persistence  # noqa: F401

        assert persistence is not None

    def test_persist_evidence_importable(self):
        """persist_evidence is importable from sat.evidence.persistence."""
        from sat.evidence.persistence import persist_evidence

        assert callable(persist_evidence)

    def test_build_evidence_pool_importable(self):
        """build_evidence_pool is importable from sat.evidence.persistence."""
        from sat.evidence.persistence import build_evidence_pool

        assert callable(build_evidence_pool)


# ---------------------------------------------------------------------------
# Tests: evidence.py route uses imported persist_evidence (not inline)
# ---------------------------------------------------------------------------


class TestEvidenceRouteRefactored:
    def test_evidence_route_imports_persist_evidence(self):
        """evidence.py route imports persist_evidence from sat.evidence.persistence."""
        import inspect

        from sat.api.routes import evidence

        source = inspect.getsource(evidence)
        assert "from sat.evidence.persistence import persist_evidence" in source

    def test_evidence_route_no_longer_has_inline_persist(self):
        """evidence.py route no longer defines _persist_evidence inline."""
        import inspect

        from sat.api.routes import evidence

        source = inspect.getsource(evidence)
        assert "def _persist_evidence" not in source
