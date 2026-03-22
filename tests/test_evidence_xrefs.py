"""Tests for S4 — Evidence-to-Finding Cross-References.

@decision DEC-TEST-S4-001: Test-first coverage for evidence registry injection and model fields.
Tests verify:
1. format_evidence_section injects an Evidence Registry when TechniqueEvidence has items.
2. format_evidence_section falls back to plain text when no items present (backward compat).
3. ACHEvidence.source_evidence_ids field defaults to empty list.
4. AssumptionRow.evidence_references field defaults to empty list.
5. TechniqueFinding.evidence_references field defaults to empty list.
6. ACH prompt instructs source_evidence_ids usage.
7. Assumptions prompt instructs evidence_references usage.
8. Synthesis prompt instructs evidence_references usage.

Production sequence exercised: TechniqueEvidence with structured items flows through
format_evidence_section, which is called by build_user_message, which feeds all technique
prompts. The registry injection is the key enabler for cross-references.
"""

from __future__ import annotations

import sat.techniques  # noqa: F401 — triggers full technique registration before prompt imports

from sat.models.ach import ACHEvidence
from sat.models.assumptions import AssumptionRow
from sat.models.evidence import EvidenceItem, EvidencePool, TechniqueEvidence
from sat.models.synthesis import TechniqueFinding
from sat.prompts.base import build_user_message, format_evidence_section


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evidence_item(
    item_id: str = "D-F1",
    claim: str = "The sky is blue.",
    confidence: str = "High",
    category: str = "fact",
    verified: bool = False,
) -> EvidenceItem:
    return EvidenceItem(
        item_id=item_id,
        claim=claim,
        source="decomposition",
        confidence=confidence,
        category=category,
        verified=verified,
    )


def _make_technique_evidence_with_items() -> TechniqueEvidence:
    items = [
        _make_evidence_item("D-F1", "Satellite imagery shows new construction.", confidence="High", verified=True),
        _make_evidence_item("R-C1", "Centrifuge components were purchased.", confidence="Medium", category="analysis"),
        _make_evidence_item("U-1", "Subject denied allegations in press.", confidence="Low"),
    ]
    text = "\n".join(f"- [{i.item_id}] {i.claim}" for i in items)
    return TechniqueEvidence(text=text, items=items)


# ---------------------------------------------------------------------------
# format_evidence_section: Evidence Registry injection
# ---------------------------------------------------------------------------


class TestFormatEvidenceSectionRegistry:
    """format_evidence_section must include an Evidence Registry when items are present."""

    def test_registry_header_appears_with_items(self):
        """'Evidence Registry' heading appears when TechniqueEvidence has items."""
        evidence = _make_technique_evidence_with_items()
        output = format_evidence_section(evidence)
        assert "Evidence Registry" in output

    def test_registry_contains_all_item_ids(self):
        """Every item ID appears in the registry section."""
        evidence = _make_technique_evidence_with_items()
        output = format_evidence_section(evidence)
        assert "[D-F1]" in output
        assert "[R-C1]" in output
        assert "[U-1]" in output

    def test_registry_contains_item_claims(self):
        """Each item's claim text appears in the registry."""
        evidence = _make_technique_evidence_with_items()
        output = format_evidence_section(evidence)
        assert "Satellite imagery shows new construction." in output
        assert "Centrifuge components were purchased." in output

    def test_registry_shows_confidence_and_category(self):
        """Confidence and category appear in registry entries."""
        evidence = _make_technique_evidence_with_items()
        output = format_evidence_section(evidence)
        assert "High/fact" in output
        assert "Medium/analysis" in output

    def test_verified_item_tagged(self):
        """Verified items get a verification tag in the registry."""
        evidence = _make_technique_evidence_with_items()
        output = format_evidence_section(evidence)
        assert "verified" in output.lower()

    def test_registry_includes_instruction(self):
        """Registry section includes instruction to use IDs in analysis."""
        evidence = _make_technique_evidence_with_items()
        output = format_evidence_section(evidence)
        assert "Use the IDs below" in output or "IDs" in output

    def test_original_evidence_text_still_present(self):
        """The original evidence text still appears alongside the registry."""
        evidence = _make_technique_evidence_with_items()
        output = format_evidence_section(evidence)
        assert "Evidence / Context" in output
        # The text channel is included
        assert "D-F1" in output  # Both in text and registry

    def test_no_registry_when_items_empty(self):
        """No Evidence Registry section when TechniqueEvidence.items is empty."""
        evidence = TechniqueEvidence(text="Some context text.", items=[])
        output = format_evidence_section(evidence)
        assert "Evidence Registry" not in output
        assert "Some context text." in output

    def test_no_registry_for_plain_string_evidence(self):
        """Plain string evidence produces no registry — backward-compatible."""
        output = format_evidence_section("Plain text evidence.")
        assert "Evidence Registry" not in output
        assert "Plain text evidence." in output

    def test_none_evidence_returns_empty_string(self):
        """None input still returns empty string."""
        assert format_evidence_section(None) == ""

    def test_empty_string_evidence_returns_empty_string(self):
        """Empty string input returns empty string (falsy guard)."""
        assert format_evidence_section("") == ""


# ---------------------------------------------------------------------------
# build_user_message: registry flows through to user message
# ---------------------------------------------------------------------------


class TestBuildUserMessageWithRegistry:
    """build_user_message with TechniqueEvidence items must include the registry."""

    def test_registry_in_full_user_message(self):
        """Full user message includes the Evidence Registry when items present."""
        evidence = _make_technique_evidence_with_items()
        msg = build_user_message("Will X happen?", evidence=evidence)
        assert "Evidence Registry" in msg
        assert "[D-F1]" in msg
        assert "[R-C1]" in msg

    def test_registry_absent_for_text_only_evidence(self):
        """Plain string evidence flows through without triggering registry."""
        msg = build_user_message("Q?", evidence="Simple text.")
        assert "Evidence Registry" not in msg
        assert "Simple text." in msg

    def test_question_still_present_with_registry(self):
        """Analytic question is not displaced by the registry."""
        evidence = _make_technique_evidence_with_items()
        msg = build_user_message("Will X happen?", evidence=evidence)
        assert "Will X happen?" in msg


# ---------------------------------------------------------------------------
# ACHEvidence model: source_evidence_ids field
# ---------------------------------------------------------------------------


class TestACHEvidenceSourceIds:
    """ACHEvidence.source_evidence_ids defaults to empty list and is assignable."""

    def test_source_evidence_ids_default_empty(self):
        """Default value for source_evidence_ids is an empty list."""
        e = ACHEvidence(
            id="E1",
            description="Some evidence.",
            credibility="High",
            relevance="Medium",
        )
        assert e.source_evidence_ids == []

    def test_source_evidence_ids_can_be_set(self):
        """source_evidence_ids accepts a list of string IDs."""
        e = ACHEvidence(
            id="E1",
            description="Some evidence.",
            credibility="High",
            relevance="Medium",
            source_evidence_ids=["D-F1", "R-C3"],
        )
        assert e.source_evidence_ids == ["D-F1", "R-C3"]

    def test_source_evidence_ids_survives_serialization(self):
        """source_evidence_ids round-trips through model_dump."""
        e = ACHEvidence(
            id="E1",
            description="Evidence.",
            credibility="Low",
            relevance="Low",
            source_evidence_ids=["U-1"],
        )
        data = e.model_dump()
        assert data["source_evidence_ids"] == ["U-1"]
        reconstructed = ACHEvidence(**data)
        assert reconstructed.source_evidence_ids == ["U-1"]


# ---------------------------------------------------------------------------
# AssumptionRow model: evidence_references field
# ---------------------------------------------------------------------------


class TestAssumptionRowEvidenceReferences:
    """AssumptionRow.evidence_references defaults to empty list and is assignable."""

    def test_evidence_references_default_empty(self):
        """Default value for evidence_references is an empty list."""
        row = AssumptionRow(
            assumption="The regime is stable.",
            confidence="High",
            basis_for_confidence="No major dissent visible.",
            what_undermines="Sudden leadership change.",
            impact_if_wrong="Analysis invalid.",
        )
        assert row.evidence_references == []

    def test_evidence_references_can_be_set(self):
        """evidence_references accepts a list of string IDs."""
        row = AssumptionRow(
            assumption="The regime is stable.",
            confidence="Medium",
            basis_for_confidence="Historical trend.",
            what_undermines="Economic collapse.",
            impact_if_wrong="Dramatically wrong.",
            evidence_references=["D-F2", "R-C1"],
        )
        assert row.evidence_references == ["D-F2", "R-C1"]

    def test_evidence_references_survives_serialization(self):
        """evidence_references round-trips through model_dump."""
        row = AssumptionRow(
            assumption="Some assumption.",
            confidence="Low",
            basis_for_confidence="Speculation.",
            what_undermines="Any new data.",
            impact_if_wrong="Analysis fails.",
            evidence_references=["R-C5"],
        )
        data = row.model_dump()
        assert data["evidence_references"] == ["R-C5"]
        reconstructed = AssumptionRow(**data)
        assert reconstructed.evidence_references == ["R-C5"]


# ---------------------------------------------------------------------------
# TechniqueFinding model: evidence_references field
# ---------------------------------------------------------------------------


class TestTechniqueFindingEvidenceReferences:
    """TechniqueFinding.evidence_references defaults to empty list and is assignable."""

    def test_evidence_references_default_empty(self):
        """Default value for evidence_references is an empty list."""
        finding = TechniqueFinding(
            technique_id="brainstorming",
            technique_name="Brainstorming",
            key_finding="Multiple scenarios identified.",
            confidence="Medium",
            summary="Summary.",
        )
        assert finding.evidence_references == []

    def test_evidence_references_can_be_set(self):
        """evidence_references accepts a list of string IDs."""
        finding = TechniqueFinding(
            technique_id="ach",
            technique_name="ACH",
            key_finding="H2 is most likely.",
            confidence="High",
            summary="ACH summary.",
            evidence_references=["D-F1", "D-F3", "R-C2"],
        )
        assert finding.evidence_references == ["D-F1", "D-F3", "R-C2"]

    def test_evidence_references_survives_serialization(self):
        """evidence_references round-trips through model_dump."""
        finding = TechniqueFinding(
            technique_id="red_team",
            technique_name="Red Team",
            key_finding="Critical vulnerability found.",
            confidence="Low",
            summary="Red team summary.",
            evidence_references=["U-2"],
        )
        data = finding.model_dump()
        assert data["evidence_references"] == ["U-2"]
        reconstructed = TechniqueFinding(**data)
        assert reconstructed.evidence_references == ["U-2"]


# ---------------------------------------------------------------------------
# Prompt content: ACH, Assumptions, Synthesis prompts mention evidence IDs
# ---------------------------------------------------------------------------


class TestACHPromptEvidenceIdGuidance:
    """ACH system prompt must include guidance for source_evidence_ids."""

    def test_ach_prompt_mentions_source_evidence_ids(self):
        """ACH_SYSTEM_PROMPT references source_evidence_ids field."""
        from sat.prompts.ach import ACH_SYSTEM_PROMPT
        assert "source_evidence_ids" in ACH_SYSTEM_PROMPT

    def test_ach_prompt_explains_evidence_registry_mapping(self):
        """ACH prompt explains how to map ACH evidence back to the registry."""
        from sat.prompts.ach import ACH_SYSTEM_PROMPT
        # Should mention mapping back to original evidence or Evidence Registry
        assert "Evidence Registry" in ACH_SYSTEM_PROMPT or "registry" in ACH_SYSTEM_PROMPT.lower()


class TestAssumptionsPromptEvidenceIdGuidance:
    """Assumptions system prompt must include guidance for evidence_references."""

    def test_assumptions_prompt_mentions_evidence_references(self):
        """ASSUMPTIONS_SYSTEM_PROMPT references evidence_references field."""
        from sat.prompts.assumptions import ASSUMPTIONS_SYSTEM_PROMPT
        assert "evidence_references" in ASSUMPTIONS_SYSTEM_PROMPT

    def test_assumptions_prompt_mentions_evidence_registry(self):
        """Assumptions prompt mentions Evidence Registry for context."""
        from sat.prompts.assumptions import ASSUMPTIONS_SYSTEM_PROMPT
        assert "Evidence Registry" in ASSUMPTIONS_SYSTEM_PROMPT or "evidence_references" in ASSUMPTIONS_SYSTEM_PROMPT


class TestSynthesisPromptEvidenceIdGuidance:
    """Synthesis system prompt must include guidance for evidence_references."""

    def test_synthesis_prompt_mentions_evidence_references(self):
        """SYNTHESIS_SYSTEM_PROMPT references evidence_references field."""
        from sat.prompts.synthesis import SYNTHESIS_SYSTEM_PROMPT
        assert "evidence_references" in SYNTHESIS_SYSTEM_PROMPT

    def test_synthesis_prompt_mentions_evidence_ids(self):
        """Synthesis prompt instructs citing evidence IDs in findings."""
        from sat.prompts.synthesis import SYNTHESIS_SYSTEM_PROMPT
        # Should mention tracing back to evidence
        assert "evidence" in SYNTHESIS_SYSTEM_PROMPT.lower()
        assert "evidence_references" in SYNTHESIS_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# EvidencePool.from_pool: only selected items flow into TechniqueEvidence
# ---------------------------------------------------------------------------


class TestTechniqueEvidenceFromPool:
    """TechniqueEvidence.from_pool only includes selected items."""

    def test_unselected_items_excluded(self):
        """Items with selected=False are excluded from TechniqueEvidence.items."""
        pool = EvidencePool(
            session_id="test-session",
            question="Q?",
            items=[
                _make_evidence_item("D-F1"),
                EvidenceItem(
                    item_id="D-F2",
                    claim="Unselected claim.",
                    source="decomposition",
                    selected=False,
                ),
            ],
        )
        te = TechniqueEvidence.from_pool(pool, text="Evidence text.")
        ids = [item.item_id for item in te.items]
        assert "D-F1" in ids
        assert "D-F2" not in ids

    def test_all_selected_items_included(self):
        """All selected items flow into TechniqueEvidence."""
        pool = EvidencePool(
            session_id="test-session",
            question="Q?",
            items=[
                _make_evidence_item("D-F1"),
                _make_evidence_item("R-C1", claim="Research claim."),
            ],
        )
        te = TechniqueEvidence.from_pool(pool, text="text")
        assert len(te.items) == 2
