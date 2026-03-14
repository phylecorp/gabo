"""Tests for technique-specific renderers.

@decision DEC-TEST-REPORT-002
@title Individual renderer unit tests for all 12 techniques
@status accepted
@rationale Verify each technique-specific renderer produces proper markdown
with tables, badges, and structure. Uses minimal valid Pydantic model instances.
"""

from __future__ import annotations


from sat.report.renderers import render_technique, render_generic


class TestACHRenderer:
    """ACH renderer should produce diagnosticity matrix tables."""

    def _make_result(self):
        from sat.models.ach import ACHEvidence, ACHHypothesis, ACHRating, ACHResult

        return ACHResult(
            technique_id="ach",
            technique_name="Analysis of Competing Hypotheses",
            summary="H2 is most consistent.",
            hypotheses=[
                ACHHypothesis(id="H1", description="Hypothesis A"),
                ACHHypothesis(id="H2", description="Hypothesis B"),
            ],
            evidence=[
                ACHEvidence(
                    id="E1", description="Evidence 1", credibility="High", relevance="High"
                ),
            ],
            matrix=[
                ACHRating(evidence_id="E1", hypothesis_id="H1", rating="I", explanation="x"),
                ACHRating(evidence_id="E1", hypothesis_id="H2", rating="C", explanation="y"),
            ],
            inconsistency_scores={"H1": 1.0, "H2": 0.0},
            most_likely="H2",
            rejected=["H1"],
            diagnosticity_notes="E1 discriminates.",
            missing_evidence=["Network logs"],
        )

    def test_renders_hypotheses_table(self):
        md = render_technique("ach", self._make_result())
        assert "| ID | Hypothesis |" in md
        assert "| H1 |" in md

    def test_renders_diagnosticity_matrix(self):
        md = render_technique("ach", self._make_result())
        assert "Diagnostic Value" in md
        assert "HIGH" in md

    def test_renders_inconsistency_scores(self):
        md = render_technique("ach", self._make_result())
        assert "Inconsistency Scores" in md
        assert "1.00" in md

    def test_renders_most_likely(self):
        md = render_technique("ach", self._make_result())
        assert "Most Likely" in md
        assert "H2" in md

    def test_renders_rejected(self):
        md = render_technique("ach", self._make_result())
        assert "Rejected" in md
        assert "H1" in md

    def test_evidence_renders_as_cards(self):
        """Evidence items use card layout with ID heading and credibility/relevance inline."""
        md = render_technique("ach", self._make_result())
        assert "#### E1: Evidence 1" in md
        assert "**Credibility**: High | **Relevance**: High" in md

    def test_matrix_uses_evidence_id_only(self):
        """Matrix rows reference evidence by ID only, not full description."""
        md = render_technique("ach", self._make_result())
        # Matrix row starts with the evidence ID, not a description
        assert "| E1 |" in md

    def test_inconsistency_scores_hidden_when_all_zero(self):
        """Inconsistency scores section is suppressed when every score is 0.0."""
        from sat.models.ach import ACHResult

        result = ACHResult(
            technique_id="ach",
            technique_name="ACH",
            summary="Zero scores.",
            inconsistency_scores={"H1": 0.0, "H2": 0.0},
        )
        md = render_technique("ach", result)
        assert "Inconsistency Scores" not in md

    def test_inconsistency_scores_hidden_when_all_identical(self):
        """Inconsistency scores section is suppressed when all scores are equal."""
        from sat.models.ach import ACHResult

        result = ACHResult(
            technique_id="ach",
            technique_name="ACH",
            summary="Identical scores.",
            inconsistency_scores={"H1": 0.5, "H2": 0.5},
        )
        md = render_technique("ach", result)
        assert "Inconsistency Scores" not in md

    def test_most_likely_hidden_when_empty_string(self):
        """most_likely is omitted when it is an empty string."""
        from sat.models.ach import ACHResult

        result = ACHResult(
            technique_id="ach",
            technique_name="ACH",
            summary="No conclusion.",
            most_likely="",
        )
        md = render_technique("ach", result)
        assert "Most Likely" not in md

    def test_rejected_hidden_when_empty_list(self):
        """rejected section is omitted when the list is empty."""
        from sat.models.ach import ACHResult

        result = ACHResult(
            technique_id="ach",
            technique_name="ACH",
            summary="No rejections.",
            rejected=[],
        )
        md = render_technique("ach", result)
        assert "Rejected" not in md

    def test_empty_ach_does_not_crash(self):
        from sat.models.ach import ACHResult

        result = ACHResult(
            technique_id="ach",
            technique_name="ACH",
            summary="Empty.",
        )
        md = render_technique("ach", result)
        assert "Empty." in md


class TestIndicatorsRenderer:
    def test_renders_indicator_table(self):
        from sat.models.indicators import Indicator, IndicatorsResult

        result = IndicatorsResult(
            technique_id="indicators",
            technique_name="Indicators",
            summary="Monitoring active.",
            hypothesis_or_scenario="Scenario X",
            indicators=[
                Indicator(
                    topic="Military",
                    indicator="Troop movements",
                    current_status="Serious Concern",
                    trend="Worsening",
                    notes="Increased activity",
                ),
            ],
            trigger_mechanisms=["Threshold breach"],
            overall_trajectory="Deteriorating",
        )
        md = render_technique("indicators", result)
        assert "| Topic |" in md
        assert "Troop movements" in md
        assert "\u2197" in md  # Worsening arrow


class TestAltFuturesRenderer:
    def test_renders_scenarios(self):
        from sat.models.alt_futures import AltFuturesResult, FuturesAxis, ScenarioQuadrant

        result = AltFuturesResult(
            technique_id="alt_futures",
            technique_name="Alternative Futures",
            summary="Four scenarios identified.",
            x_axis=FuturesAxis(name="Growth", low_label="Low", high_label="High"),
            y_axis=FuturesAxis(name="Stability", low_label="Low", high_label="High"),
            scenarios=[
                ScenarioQuadrant(
                    quadrant_label="High Growth / High Stability",
                    scenario_name="Golden Age",
                    narrative="Prosperity reigns.",
                    indicators=["GDP growth"],
                    policy_implications="Invest broadly.",
                ),
            ],
        )
        md = render_technique("alt_futures", result)
        assert "Golden Age" in md
        assert "X Axis" in md
        assert "\u2194" in md  # axis arrow


class TestAssumptionsRenderer:
    def test_renders_assumptions_cards(self):
        from sat.models.assumptions import AssumptionRow, KeyAssumptionsResult

        result = KeyAssumptionsResult(
            technique_id="assumptions",
            technique_name="Key Assumptions Check",
            summary="Two assumptions.",
            analytic_line="Main judgment",
            assumptions=[
                AssumptionRow(
                    assumption="Assumption 1",
                    confidence="High",
                    basis_for_confidence="Evidence",
                    what_undermines="Counter-evidence",
                    impact_if_wrong="Major",
                ),
            ],
            most_vulnerable=["Assumption 1"],
        )
        md = render_technique("assumptions", result)
        # Card layout: numbered heading, inline confidence/impact, basis, what undermines
        assert "#### 1. Assumption 1" in md
        assert "**Confidence**: High" in md
        assert "**Impact if Wrong**: Major" in md
        assert "**Basis**: Evidence" in md
        assert "**What Could Undermine**: Counter-evidence" in md
        assert "Most Vulnerable" in md


class TestQualityRenderer:
    def test_renders_source_cards(self):
        from sat.models.quality import QualityOfInfoResult, SourceQualityRow

        result = QualityOfInfoResult(
            technique_id="quality",
            technique_name="Quality of Information",
            summary="Sources assessed.",
            sources=[
                SourceQualityRow(
                    source_id="S1",
                    description="OSINT report",
                    source_type="OSINT",
                    reliability="High",
                    access_quality="Direct",
                    corroboration="Multiple sources",
                    gaps="Limited scope",
                ),
            ],
            key_gaps=["Classified intel"],
        )
        md = render_technique("quality", result)
        # Card layout: heading from description, inline type/reliability, access, corroboration, gaps
        assert "#### OSINT report" in md
        assert "**Type**: OSINT" in md
        assert "**Reliability**: High" in md
        assert "**Access**: Direct" in md
        assert "**Corroboration**: Multiple sources" in md
        assert "**Gaps**: Limited scope" in md


class TestRedTeamRenderer:
    def test_renders_memo_as_blockquote(self):
        from sat.models.red_team import RedTeamResult

        result = RedTeamResult(
            technique_id="red_team",
            technique_name="Red Team",
            summary="Adversary perspective.",
            adversary_identity="State actor",
            first_person_memo="We must act now.\nTime is running out.",
            predicted_actions=["Escalate"],
        )
        md = render_technique("red_team", result)
        assert "> We must act now." in md
        assert "Predicted Actions" in md


class TestTeamABRenderer:
    def test_renders_both_teams(self):
        from sat.models.team_ab import TeamABResult, TeamPosition

        result = TeamABResult(
            technique_id="team_ab",
            technique_name="Team A/B",
            summary="Debate complete.",
            team_a=TeamPosition(
                team="A",
                hypothesis="H1 is correct",
                argument="Strong evidence supports H1.",
            ),
            team_b=TeamPosition(
                team="B",
                hypothesis="H2 is correct",
                argument="H2 better explains the data.",
            ),
            stronger_case="A",
        )
        md = render_technique("team_ab", result)
        assert "Team A" in md
        assert "Team B" in md
        assert "Stronger Case" in md


class TestDevilsAdvocacyRenderer:
    def test_renders_verdict_badge(self):
        from sat.models.devils_advocacy import DevilsAdvocacyResult

        result = DevilsAdvocacyResult(
            technique_id="devils_advocacy",
            technique_name="Devil's Advocacy",
            summary="Challenge complete.",
            mainline_judgment="The mainline holds.",
            conclusion="Mainline Weakened",
        )
        md = render_technique("devils_advocacy", result)
        assert "\u26a0" in md  # warning symbol
        assert "Verdict" in md

    def test_challenged_assumptions_render_as_cards(self):
        """Challenged assumptions use card layout, not a table."""
        from sat.models.devils_advocacy import ChallengedAssumption, DevilsAdvocacyResult

        result = DevilsAdvocacyResult(
            technique_id="devils_advocacy",
            technique_name="Devil's Advocacy",
            summary="Cards test.",
            challenged_assumptions=[
                ChallengedAssumption(
                    assumption="The treaty will hold throughout 2026.",
                    challenge="Historical precedent shows defections after elections.",
                    evidence_against="Three prior treaties collapsed within 18 months.",
                    vulnerability="High",
                ),
            ],
        )
        md = render_technique("devils_advocacy", result)
        # Card layout: heading from first sentence, then labelled fields
        assert "#### The treaty will hold throughout 2026." in md
        assert "**Vulnerability**: High" in md
        assert "**Challenge**:" in md
        assert "**Evidence Against**:" in md
        # Must NOT use table format
        assert "| Assumption |" not in md


class TestHighImpactRenderer:
    def test_renders_pathways(self):
        from sat.models.high_impact import HighImpactResult, Pathway

        result = HighImpactResult(
            technique_id="high_impact",
            technique_name="High Impact",
            summary="Event analyzed.",
            event_definition="Major disruption",
            pathways=[
                Pathway(
                    name="Supply chain",
                    description="Cascade failure.",
                    triggers=["Initial event"],
                    indicators=["Warning sign"],
                    plausibility="Plausible",
                ),
            ],
        )
        md = render_technique("high_impact", result)
        assert "Supply chain" in md
        assert "Plausible" in md


class TestWhatIfRenderer:
    def test_renders_chain(self):
        from sat.models.what_if import ScenarioStep, WhatIfResult

        result = WhatIfResult(
            technique_id="what_if",
            technique_name="What If",
            summary="Scenario explored.",
            assumed_event="Event X",
            chain_of_argumentation=[
                ScenarioStep(
                    step_number=1,
                    description="First this happens.",
                    enabling_factors=["Factor A"],
                ),
            ],
        )
        md = render_technique("what_if", result)
        assert "1. First this happens." in md
        assert "Factor A" in md


class TestBrainstormingRenderer:
    def test_renders_clusters(self):
        from sat.models.brainstorming import BrainstormingResult, Idea, IdeaCluster

        result = BrainstormingResult(
            technique_id="brainstorming",
            technique_name="Brainstorming",
            summary="Ideas generated.",
            clusters=[
                IdeaCluster(
                    name="Tech",
                    ideas=[
                        Idea(id="I1", text="AI disruption", source_rationale="trend"),
                    ],
                    significance="Critical area",
                ),
            ],
        )
        md = render_technique("brainstorming", result)
        assert "Tech" in md
        assert "I1" in md


class TestOutsideInRenderer:
    def test_renders_steep_table(self):
        from sat.models.outside_in import OutsideInResult, STEEPForce

        result = OutsideInResult(
            technique_id="outside_in",
            technique_name="Outside-In",
            summary="Forces analyzed.",
            forces=[
                STEEPForce(
                    category="Economic",
                    force="Inflation",
                    description="Rising prices",
                    impact_on_issue="Reduces capacity",
                    controllability="Partially Controllable",
                    evidence="CPI data",
                ),
            ],
        )
        md = render_technique("outside_in", result)
        assert "| Category |" in md
        assert "Economic" in md


class TestGenericRenderer:
    def test_renders_base_result(self):
        from sat.models.base import ArtifactResult

        result = ArtifactResult(
            technique_id="unknown",
            technique_name="Unknown",
            summary="Generic output.",
        )
        md = render_generic(result)
        assert "Generic output." in md

    def test_unknown_technique_uses_generic(self):
        from sat.models.base import ArtifactResult

        result = ArtifactResult(
            technique_id="totally_unknown",
            technique_name="Unknown",
            summary="Fallback test.",
        )
        md = render_technique("totally_unknown", result)
        assert "Fallback test." in md


class TestFirstSentenceHelper:
    """Unit tests for the _first_sentence helper function."""

    def test_short_text_returned_unchanged(self):
        from sat.report.renderers import _first_sentence

        text = "Short text."
        assert _first_sentence(text) == text

    def test_extracts_first_sentence_at_period_space(self):
        from sat.report.renderers import _first_sentence

        # Total length > max_len=50, boundary at position 14 (within max_len)
        text = "First sentence. " + "x" * 60
        result = _first_sentence(text, max_len=50)
        assert result == "First sentence."

    def test_truncates_to_max_len_when_no_boundary(self):
        from sat.report.renderers import _first_sentence

        text = "A" * 150  # no period-space boundary
        result = _first_sentence(text, max_len=100)
        assert result == "A" * 100 + "..."
        assert len(result) == 103

    def test_uses_boundary_within_max_len(self):
        from sat.report.renderers import _first_sentence

        # Boundary at position 20, max_len=100 — should use boundary
        text = "First short sentence. " + "x" * 200
        result = _first_sentence(text, max_len=100)
        assert result == "First short sentence."

    def test_truncates_when_boundary_beyond_max_len(self):
        from sat.report.renderers import _first_sentence

        # Boundary is at position 110, beyond max_len=100
        text = "x" * 110 + ". more text"
        result = _first_sentence(text, max_len=100)
        assert result.endswith("...")
        assert len(result) == 103
