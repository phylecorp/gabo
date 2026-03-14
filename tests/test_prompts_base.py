"""Tests for prompt building utilities in sat.prompts.base.

@decision DEC-TEST-PROMPTS-BASE-001: Separate test module for base prompt utilities.
build_user_message and format_prior_results_section are shared by every technique
prompt, so their correctness is tested independently here rather than relying on
technique-level tests to catch regressions. Covers: date injection (Bug 1),
adversarial artifact rendering in prior_results (Bug 2 verification).

Covers:
  - Date injection (Bug 1 fix): build_user_message must include today's ISO date.
  - format_prior_results_section: adversarial artifacts (adjudication, investigator,
    convergence) keyed under compound IDs like "<tid>-adjudication" must appear in
    the formatted output (Bug 2 fix verification).
  - format_research_evidence: deterministic markdown rendering from ResearchResult
    structured data — every claim, source, and gap appears; handles empty collections.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sat.models.base import ArtifactResult
from sat.models.research import ResearchClaim, ResearchResult, ResearchSource
from sat.prompts.base import (
    build_user_message,
    format_prior_results_section,
    format_research_evidence,
)


class TestBuildUserMessageDateInjection:
    """build_user_message must include today's ISO date as temporal grounding."""

    def test_contains_today_iso_date(self):
        """The very first substantive content is today's ISO date."""
        today = date.today().isoformat()
        msg = build_user_message("Will X happen?")
        assert today in msg, f"Expected {today!r} in message but got:\n{msg}"

    def test_date_appears_before_question(self):
        """The date line must appear before the analytic question."""
        today = date.today().isoformat()
        msg = build_user_message("Test question?")
        date_pos = msg.index(today)
        question_pos = msg.index("Test question?")
        assert date_pos < question_pos, "Date must precede the analytic question"

    def test_question_still_present(self):
        """The question itself must still appear in the output."""
        msg = build_user_message("My analytic question?")
        assert "My analytic question?" in msg

    def test_evidence_still_included(self):
        """Evidence section is preserved alongside the date."""
        msg = build_user_message("Q?", evidence="Some evidence text.")
        assert "Some evidence text." in msg
        assert date.today().isoformat() in msg


class TestFormatPriorResultsAdversarialArtifacts:
    """format_prior_results_section must include adversarial artifact entries.

    Bug 2 fix: adjudication, investigator, and convergence results are stored
    under compound keys like "<tid>-adjudication". Synthesis calls
    format_prior_results_section with those keys in prior_results — it must
    render them.
    """

    def _make_result(self, tid: str, name: str, summary: str) -> ArtifactResult:
        return ArtifactResult(
            technique_id=tid,
            technique_name=name,
            summary=summary,
        )

    def test_adjudication_key_included(self):
        """Keys like '<tid>-adjudication' are rendered in output."""
        prior = {
            "ach": self._make_result("ach", "ACH", "Original ACH summary."),
            "ach-adjudication": self._make_result(
                "ach-adjudication", "ACH Adjudication", "Adjudication resolved disagreements."
            ),
        }
        output = format_prior_results_section(prior)
        assert "Adjudication resolved disagreements." in output

    def test_investigator_key_included(self):
        """Keys like '<tid>-investigator' are rendered in output."""
        prior = {
            "ach-investigator": self._make_result(
                "ach-investigator", "ACH Investigator", "Investigator factual findings."
            ),
        }
        output = format_prior_results_section(prior)
        assert "Investigator factual findings." in output

    def test_convergence_key_included(self):
        """Keys like '<tid>-convergence' are rendered in output."""
        prior = {
            "ach-convergence": self._make_result(
                "ach-convergence", "ACH Convergence", "Convergence summary reached."
            ),
        }
        output = format_prior_results_section(prior)
        assert "Convergence summary reached." in output

    def test_all_adversarial_artifacts_included(self):
        """When adjudication, investigator, and convergence are all present, all appear."""
        prior = {
            "ach": self._make_result("ach", "ACH", "Base ACH."),
            "ach-adjudication": self._make_result("ach-adjudication", "Adjudication", "Adj."),
            "ach-investigator": self._make_result("ach-investigator", "Investigator", "Inv."),
            "ach-convergence": self._make_result("ach-convergence", "Convergence", "Conv."),
        }
        output = format_prior_results_section(prior)
        assert "Adj." in output
        assert "Inv." in output
        assert "Conv." in output
        assert "Base ACH." in output


# ---------------------------------------------------------------------------
# Helpers for TestFormatResearchEvidence
# ---------------------------------------------------------------------------


def _make_source(
    id: str,
    title: str,
    url: str | None = "https://example.com",
    source_type: str = "web",
    reliability: str = "Medium",
) -> ResearchSource:
    return ResearchSource(
        id=id,
        title=title,
        url=url,
        source_type=source_type,
        reliability_assessment=reliability,
        retrieved_at=datetime.now(timezone.utc),
    )


def _make_claim(
    claim: str,
    source_ids: list[str],
    confidence: str = "Medium",
    category: str = "fact",
    verified: bool = False,
    verification_verdict: str | None = None,
) -> ResearchClaim:
    return ResearchClaim(
        claim=claim,
        source_ids=source_ids,
        confidence=confidence,
        category=category,
        verified=verified,
        verification_verdict=verification_verdict,
    )


def _make_research_result(
    claims: list[ResearchClaim] | None = None,
    sources: list[ResearchSource] | None = None,
    gaps: list[str] | None = None,
    verification_status: str | None = None,
    verification_summary: str | None = None,
) -> ResearchResult:
    return ResearchResult(
        technique_id="research",
        technique_name="Deep Research",
        summary="Test summary",
        query="test query",
        sources=sources or [],
        claims=claims or [],
        formatted_evidence="placeholder",
        research_provider="mock",
        gaps_identified=gaps or [],
        verification_status=verification_status,
        verification_summary=verification_summary,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFormatResearchEvidence:
    """format_research_evidence renders ResearchResult into deterministic markdown.

    All claims, sources, and gaps must appear. Empty collections are handled
    gracefully. Verification summary appears only when verification_status is set.
    """

    def test_all_claims_rendered_with_confidence_and_category(self):
        """Every claim appears with its confidence and category in the output."""
        claims = [
            _make_claim("AI is advancing", ["S1"], confidence="High", category="fact"),
            _make_claim("Risks are understudied", ["S2"], confidence="Low", category="analysis"),
        ]
        result = _make_research_result(claims=claims)
        output = format_research_evidence(result)

        assert "AI is advancing" in output
        assert "High/fact" in output
        assert "Risks are understudied" in output
        assert "Low/analysis" in output

    def test_sources_rendered_with_reliability_and_url(self):
        """Every source appears with reliability and URL in the output."""
        sources = [
            _make_source("S1", "OpenAI Blog", url="https://openai.com", reliability="High"),
            _make_source("S2", "Unknown Site", url=None, reliability="Unknown"),
        ]
        result = _make_research_result(sources=sources)
        output = format_research_evidence(result)

        assert "OpenAI Blog" in output
        assert "High" in output
        assert "https://openai.com" in output
        assert "Unknown Site" in output
        assert "Unknown" in output

    def test_gaps_section_appears(self):
        """Information gaps are rendered as a bullet list."""
        gaps = ["No primary sources", "Missing 2024 data"]
        result = _make_research_result(gaps=gaps)
        output = format_research_evidence(result)

        assert "Information Gaps" in output
        assert "No primary sources" in output
        assert "Missing 2024 data" in output

    def test_verification_verdicts_shown_when_present(self):
        """Verification verdicts appear inline with the claim when verified=True."""
        claims = [
            _make_claim(
                "Claim with verdict",
                ["S1"],
                verified=True,
                verification_verdict="SUPPORTED by multiple sources",
            ),
        ]
        result = _make_research_result(claims=claims)
        output = format_research_evidence(result)

        assert "SUPPORTED by multiple sources" in output

    def test_empty_claims_handled_gracefully(self):
        """No crash on empty claims list; section notes none identified."""
        result = _make_research_result(claims=[])
        output = format_research_evidence(result)

        assert "Key Claims" in output
        assert "None identified" in output

    def test_empty_sources_handled_gracefully(self):
        """No crash on empty sources list; section notes none identified."""
        result = _make_research_result(sources=[])
        output = format_research_evidence(result)

        assert "Source Registry" in output
        assert "None identified" in output

    def test_empty_gaps_omits_section(self):
        """When gaps_identified is empty, the Information Gaps section is omitted."""
        result = _make_research_result(gaps=[])
        output = format_research_evidence(result)

        assert "Information Gaps" not in output

    def test_verification_summary_section_appears_when_status_set(self):
        """Verification Summary section appears when verification_status is set."""
        result = _make_research_result(
            verification_status="partial",
            verification_summary="Three of five claims confirmed by independent sources.",
        )
        output = format_research_evidence(result)

        assert "Verification Summary" in output
        assert "partial" in output
        assert "Three of five claims confirmed" in output

    def test_verification_section_absent_when_no_status(self):
        """Verification Summary section is absent when verification_status is None."""
        result = _make_research_result(verification_status=None)
        output = format_research_evidence(result)

        assert "Verification Summary" not in output

    def test_source_ids_appear_in_claim_line(self):
        """Source IDs referenced by a claim appear in its rendered line."""
        claims = [_make_claim("Some finding", ["S1", "S3"])]
        result = _make_research_result(claims=claims)
        output = format_research_evidence(result)

        assert "S1" in output
        assert "S3" in output

    def test_claim_with_no_source_ids_shows_no_sources(self):
        """Claims with empty source_ids render 'no sources' rather than crashing."""
        claims = [_make_claim("Unsourced claim", source_ids=[])]
        result = _make_research_result(claims=claims)
        output = format_research_evidence(result)

        assert "Unsourced claim" in output
        assert "no sources" in output
