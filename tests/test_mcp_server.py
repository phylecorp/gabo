"""Tests for MCP server tools and session lifecycle.

@decision DEC-TEST-MCP-001
@title MCP server tool integration tests with direct function calls
@status accepted
@rationale Tests call MCP tool functions directly (bypassing MCP transport) to verify
tool logic: technique listing, session lifecycle, prompt generation, result validation,
post-processing, state accumulation, synthesis gating, and research. Mock is acceptable
for research (external API boundary) and adversarial (external LLM calls).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

import sat.techniques  # noqa: F401 — trigger registration
from sat.mcp_server import (
    sat_get_synthesis_prompt,
    sat_list_techniques,
    sat_new_session,
    sat_next_prompt,
    sat_research,
    sat_submit_result,
    sat_submit_synthesis,
)
from sat.mcp_session import clear_sessions
from sat.models.ach import ACHEvidence, ACHHypothesis, ACHRating, ACHResult
from sat.models.assumptions import AssumptionRow, KeyAssumptionsResult
from sat.models.synthesis import SynthesisResult, TechniqueFinding


@pytest.fixture(autouse=True)
def _clean_sessions():
    """Clear session state before and after each test."""
    clear_sessions()
    yield
    clear_sessions()


def _minimal_assumptions_result() -> dict:
    """Build a minimal valid KeyAssumptionsResult as a dict."""
    return KeyAssumptionsResult(
        technique_id="assumptions",
        technique_name="Key Assumptions Check",
        summary="Two key assumptions identified.",
        analytic_line="Country X is pursuing nuclear weapons.",
        assumptions=[
            AssumptionRow(
                assumption="Country X has technical capability",
                confidence="Medium",
                basis_for_confidence="Limited intelligence",
                what_undermines="Leadership change",
                impact_if_wrong="Fundamental reassessment needed",
            ),
        ],
        most_vulnerable=["Country X has technical capability"],
        recommended_monitoring=["Track procurement patterns"],
    ).model_dump()


def _minimal_ach_result() -> dict:
    """Build a minimal valid ACHResult as a dict."""
    return ACHResult(
        technique_id="ach",
        technique_name="Analysis of Competing Hypotheses",
        summary="H1 most consistent with evidence.",
        hypotheses=[
            ACHHypothesis(id="H1", description="Pursuing weapons"),
            ACHHypothesis(id="H2", description="Peaceful program"),
        ],
        evidence=[
            ACHEvidence(
                id="E1",
                description="Enrichment beyond civilian needs",
                credibility="High",
                relevance="High",
            ),
        ],
        matrix=[
            ACHRating(hypothesis_id="H1", evidence_id="E1", rating="C", explanation="Consistent"),
            ACHRating(hypothesis_id="H2", evidence_id="E1", rating="I", explanation="Inconsistent"),
        ],
        inconsistency_scores={},
        most_likely="H1",
        rejected=["H2"],
        diagnosticity_notes="E1 is diagnostic — strongly favors H1 over H2.",
    ).model_dump()


def _minimal_synthesis_result() -> dict:
    """Build a minimal valid SynthesisResult as a dict."""
    return SynthesisResult(
        technique_id="synthesis",
        technique_name="Synthesis Report",
        summary="Converging evidence supports the primary assessment.",
        question="Is Country X pursuing nuclear weapons?",
        techniques_applied=["assumptions", "ach"],
        key_findings=[
            TechniqueFinding(
                technique_id="assumptions",
                technique_name="Key Assumptions Check",
                summary="Key assumptions identified.",
                key_finding="Technical capability assumption is vulnerable.",
                confidence="Medium",
            ),
        ],
        convergent_judgments=["Both techniques point to active pursuit."],
        divergent_signals=[],
        highest_confidence_assessments=["Active enrichment program."],
        remaining_uncertainties=["Leadership intent unclear."],
        intelligence_gaps=["Need HUMINT on leadership decisions."],
        recommended_next_steps=["Prioritize HUMINT collection."],
        bottom_line_assessment="Country X is likely pursuing nuclear weapons.",
    ).model_dump()


class TestListTechniques:
    """sat_list_techniques should return all 12 techniques with correct fields."""

    async def test_returns_all_twelve(self):
        result = await sat_list_techniques()
        assert len(result) == 12

    async def test_each_has_required_fields(self):
        result = await sat_list_techniques()
        for tech in result:
            assert "id" in tech
            assert "name" in tech
            assert "category" in tech
            assert "description" in tech
            assert "order" in tech

    async def test_categories_present(self):
        result = await sat_list_techniques()
        categories = {t["category"] for t in result}
        assert categories == {"diagnostic", "contrarian", "imaginative"}

    async def test_sorted_by_category_order(self):
        result = await sat_list_techniques()
        categories = [t["category"] for t in result]
        # Diagnostic should come before contrarian, contrarian before imaginative
        diag_end = max(i for i, c in enumerate(categories) if c == "diagnostic")
        cont_start = min(i for i, c in enumerate(categories) if c == "contrarian")
        assert diag_end < cont_start


class TestNewSession:
    """sat_new_session creates a session with correct state."""

    async def test_default_all_techniques(self):
        result = await sat_new_session(question="Test question?")
        assert result["status"] == "created"
        assert result["session_id"]
        assert result["total_techniques"] == 12
        assert len(result["techniques"]) == 12

    async def test_explicit_technique_list(self):
        result = await sat_new_session(
            question="Test?",
            techniques=["assumptions", "ach"],
        )
        assert result["techniques"] == ["assumptions", "ach"]
        assert result["total_techniques"] == 2

    async def test_invalid_technique_raises(self):
        with pytest.raises(ValueError, match="Unknown technique"):
            await sat_new_session(
                question="Test?",
                techniques=["nonexistent_technique"],
            )

    async def test_with_evidence(self):
        result = await sat_new_session(
            question="Test?",
            evidence="Some background evidence.",
        )
        assert result["status"] == "created"


class TestNextPrompt:
    """sat_next_prompt returns valid prompts with schema."""

    async def test_returns_first_technique_prompt(self):
        session = await sat_new_session(
            question="Is X pursuing Y?",
            evidence="E1 detected.",
            techniques=["assumptions"],
        )
        result = await sat_next_prompt(session["session_id"])

        assert result["status"] == "ready"
        assert result["technique_id"] == "assumptions"
        assert result["technique_name"] == "Key Assumptions Check"
        assert result["progress"] == "1/1"
        assert "system_prompt" in result
        assert len(result["system_prompt"]) > 0
        assert "messages" in result
        assert len(result["messages"]) > 0
        assert result["messages"][0]["role"] == "user"
        assert "output_json_schema" in result
        assert "properties" in result["output_json_schema"]

    async def test_prompt_contains_question(self):
        session = await sat_new_session(
            question="Is Country X pursuing nuclear weapons?",
            techniques=["assumptions"],
        )
        result = await sat_next_prompt(session["session_id"])
        # The question should appear in the user message
        user_content = result["messages"][0]["content"]
        assert "Country X" in user_content

    async def test_returns_complete_when_done(self):
        session = await sat_new_session(
            question="Test?",
            techniques=["assumptions"],
        )
        sid = session["session_id"]

        # Submit a result to advance past the single technique
        await sat_next_prompt(sid)
        await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))

        result = await sat_next_prompt(sid)
        assert result["status"] == "all_techniques_complete"


class TestSubmitResult:
    """sat_submit_result validates, post-processes, and stores results."""

    async def test_accepts_valid_result(self):
        session = await sat_new_session(
            question="Test?",
            techniques=["assumptions"],
        )
        sid = session["session_id"]
        await sat_next_prompt(sid)

        result = await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))
        assert result["status"] == "accepted"
        assert result["technique_id"] == "assumptions"
        assert result["has_more_techniques"] is False

    async def test_rejects_invalid_json(self):
        session = await sat_new_session(question="Test?", techniques=["assumptions"])
        sid = session["session_id"]
        await sat_next_prompt(sid)

        result = await sat_submit_result(sid, "not valid json{{{")
        assert "error" in result
        assert "Invalid JSON" in result["error"]

    async def test_rejects_schema_mismatch(self):
        session = await sat_new_session(question="Test?", techniques=["assumptions"])
        sid = session["session_id"]
        await sat_next_prompt(sid)

        # Submit a valid JSON but wrong schema (missing required fields)
        result = await sat_submit_result(sid, json.dumps({"technique_id": "assumptions"}))
        assert "error" in result
        assert "validation" in result["error"].lower()

    async def test_ach_post_process_computes_scores(self):
        """ACH post_process should compute inconsistency scores."""
        session = await sat_new_session(question="Test?", techniques=["ach"])
        sid = session["session_id"]
        await sat_next_prompt(sid)

        ach_data = _minimal_ach_result()
        result = await sat_submit_result(sid, json.dumps(ach_data))
        assert result["status"] == "accepted"
        assert result["post_processed"] is True

        # Verify the stored result has computed scores
        from sat.mcp_session import get_session

        stored = get_session(sid)
        ach_result = stored.prior_results["ach"]
        # H2 had one "I" rating with High credibility -> score 1.0
        assert hasattr(ach_result, "inconsistency_scores")
        assert ach_result.inconsistency_scores.get("H2", 0) > 0

    async def test_advances_to_next_technique(self):
        session = await sat_new_session(
            question="Test?",
            techniques=["assumptions", "ach"],
        )
        sid = session["session_id"]
        await sat_next_prompt(sid)

        result = await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))
        assert result["has_more_techniques"] is True
        assert result["next_technique_id"] == "ach"

    async def test_error_when_all_complete(self):
        session = await sat_new_session(question="Test?", techniques=["assumptions"])
        sid = session["session_id"]
        await sat_next_prompt(sid)
        await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))

        result = await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))
        assert "error" in result


class TestPriorResultsAccumulate:
    """Prior results should accumulate and be available to later techniques."""

    async def test_second_technique_sees_first_result(self):
        session = await sat_new_session(
            question="Test?",
            evidence="Background info.",
            techniques=["assumptions", "ach"],
        )
        sid = session["session_id"]

        # Complete first technique
        await sat_next_prompt(sid)
        await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))

        # Second technique's prompt should include prior results
        prompt2 = await sat_next_prompt(sid)
        assert prompt2["technique_id"] == "ach"
        # The user message should reference prior analysis
        user_content = prompt2["messages"][0]["content"]
        assert "Key Assumptions Check" in user_content or "assumptions" in user_content.lower()


class TestSynthesisPrompt:
    """sat_get_synthesis_prompt gating and content."""

    async def test_errors_when_techniques_incomplete(self):
        session = await sat_new_session(
            question="Test?",
            techniques=["assumptions", "ach"],
        )
        sid = session["session_id"]

        result = await sat_get_synthesis_prompt(sid)
        assert "error" in result
        assert "remaining_techniques" in result

    async def test_returns_prompt_when_complete(self):
        session = await sat_new_session(
            question="Is X pursuing Y?",
            techniques=["assumptions"],
        )
        sid = session["session_id"]

        # Complete the technique
        await sat_next_prompt(sid)
        await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))

        result = await sat_get_synthesis_prompt(sid)
        assert result["status"] == "ready"
        assert "system_prompt" in result
        assert "messages" in result
        assert "output_json_schema" in result
        assert result["techniques_completed"] == ["assumptions"]


class TestSubmitSynthesis:
    """sat_submit_synthesis validates and writes artifacts."""

    async def test_writes_artifacts(self, tmp_path):
        import os

        os.environ["SAT_OUTPUT_DIR"] = str(tmp_path)
        try:
            session = await sat_new_session(
                question="Is X pursuing Y?",
                techniques=["assumptions"],
            )
            sid = session["session_id"]

            await sat_next_prompt(sid)
            await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))
            await sat_get_synthesis_prompt(sid)

            result = await sat_submit_synthesis(sid, json.dumps(_minimal_synthesis_result()))
            assert result["status"] == "complete"
            assert "output_dir" in result
            assert "manifest_path" in result
            assert result["artifacts_written"] == 2  # 1 technique + 1 synthesis

            # Verify files exist on disk
            from pathlib import Path

            output_dir = Path(result["output_dir"])
            assert output_dir.exists()
            manifest = Path(result["manifest_path"])
            assert manifest.exists()

            # Check manifest content
            manifest_data = json.loads(manifest.read_text())
            assert manifest_data["question"] == "Is X pursuing Y?"
            assert "assumptions" in manifest_data["techniques_completed"]
        finally:
            os.environ.pop("SAT_OUTPUT_DIR", None)

    async def test_rejects_invalid_synthesis_json(self):
        session = await sat_new_session(question="Test?", techniques=["assumptions"])
        sid = session["session_id"]
        await sat_next_prompt(sid)
        await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))

        result = await sat_submit_synthesis(sid, "invalid json!!!")
        assert "error" in result


class TestFullSessionLifecycle:
    """End-to-end test: new_session -> next_prompt -> submit -> synthesis."""

    async def test_two_technique_lifecycle(self, tmp_path):
        import os

        os.environ["SAT_OUTPUT_DIR"] = str(tmp_path)
        try:
            # Step 1: Create session
            session = await sat_new_session(
                question="Is Country X pursuing nuclear weapons?",
                evidence="Enrichment detected beyond civilian needs.",
                techniques=["assumptions", "ach"],
            )
            sid = session["session_id"]
            assert session["total_techniques"] == 2

            # Step 2: First technique prompt
            p1 = await sat_next_prompt(sid)
            assert p1["technique_id"] == "assumptions"
            assert p1["progress"] == "1/2"

            # Step 3: Submit first result
            r1 = await sat_submit_result(sid, json.dumps(_minimal_assumptions_result()))
            assert r1["status"] == "accepted"
            assert r1["has_more_techniques"] is True

            # Step 4: Second technique prompt
            p2 = await sat_next_prompt(sid)
            assert p2["technique_id"] == "ach"
            assert p2["progress"] == "2/2"

            # Step 5: Submit second result
            r2 = await sat_submit_result(sid, json.dumps(_minimal_ach_result()))
            assert r2["status"] == "accepted"
            assert r2["has_more_techniques"] is False

            # Step 6: All techniques done
            p3 = await sat_next_prompt(sid)
            assert p3["status"] == "all_techniques_complete"

            # Step 7: Synthesis prompt
            sp = await sat_get_synthesis_prompt(sid)
            assert sp["status"] == "ready"

            # Step 8: Submit synthesis
            synth = await sat_submit_synthesis(sid, json.dumps(_minimal_synthesis_result()))
            assert synth["status"] == "complete"
            assert synth["artifacts_written"] == 3  # 2 techniques + 1 synthesis
        finally:
            os.environ.pop("SAT_OUTPUT_DIR", None)


class TestResearch:
    """sat_research tool — mock the research provider since it's an external boundary.

    # @mock-exempt: Research requires external API calls (Perplexity, Brave, OpenAI deep
    # research) and an LLM provider for evidence structuring. These are external service
    # boundaries appropriate for mocking.
    """

    async def test_research_callable(self):
        """Verify sat_research can be called and returns expected structure."""
        from sat.models.research import ResearchClaim, ResearchResult, ResearchSource

        mock_result = ResearchResult(
            technique_id="research",
            technique_name="Deep Research",
            summary="Research completed.",
            query="nuclear weapons Country X",
            sources=[
                ResearchSource(
                    id="S1",
                    title="IAEA Report 2024",
                    url="https://example.com/iaea",
                    source_type="government",
                    reliability_assessment="High",
                ),
            ],
            claims=[
                ResearchClaim(
                    claim="Enrichment levels exceed civilian needs",
                    source_ids=["S1"],
                    confidence="High",
                    category="fact",
                ),
            ],
            formatted_evidence="Enrichment detected at 60% — well above civilian 5%.",
            research_provider="multi(perplexity)",
            gaps_identified=["No HUMINT available"],
        )

        with (
            patch("sat.mcp_server.create_provider"),
            patch("sat.mcp_server.run_multi_research", new_callable=AsyncMock) as mock_research,
        ):
            mock_research.return_value = mock_result

            result = await sat_research(question="Is Country X pursuing nuclear weapons?")

            assert result["status"] == "complete"
            assert "formatted_evidence" in result
            assert result["sources_count"] == 1
            assert result["claims_count"] == 1
