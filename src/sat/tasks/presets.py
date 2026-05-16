"""Built-in task type definitions for SAT's 5 preset templates.

@decision DEC-TASK-002
@title 5 preset templates cover the core intelligence product types
@status accepted
@rationale The 5 presets cover the most common structured deliverables in
intelligence work: Threat Assessment (actor/capability analysis), Quick Brief
(fast-turnaround BLUF-first product), Battle Damage Assessment (CJCSI 3162.02
three-phase combat assessment), Annex B Intelligence (OPORD intelligence annex
per FM 34-10), and Annex L Collection Plan (ISR collection annex per FM 3-55).
technique_affinity values are hints to the planner — never hard constraints.
The planner may add or remove techniques based on the specific question and
available evidence. Preset IDs are kept short ('threat', 'brief', etc.) for
ergonomic CLI use: `sat task threat "What is X's capability?"`.

References:
- CJCSI 3162.02A: Methodology for Combat Assessment (BDA structure)
- FM 34-10 / FM 2-01.3: OPORD intelligence annex (Annex B structure)
- FM 3-55: Information Collection (Annex L structure)
"""

from __future__ import annotations

from sat.tasks.models import TaskSection, TaskType


# ---------------------------------------------------------------------------
# Preset 1: Threat Assessment
# ---------------------------------------------------------------------------
_THREAT = TaskType(
    id="threat",
    name="Threat Assessment",
    description=(
        "Comprehensive threat evaluation for a specific actor, capability, or scenario. "
        "Use when the question requires structured analysis of threat actor capabilities, "
        "intent, and associated risks."
    ),
    sections=[
        TaskSection(
            id="threat_overview",
            name="Threat Overview",
            description=(
                "Actor identification, background, and context. "
                "Establishes who or what the threat is and provides essential background."
            ),
            required_analysis=["evidence_assessment", "background_research"],
            technique_affinity=["quality"],
            requires_research=True,
            evidence_requirements="Open-source reporting, order of battle data, background on the actor.",
        ),
        TaskSection(
            id="capability_assessment",
            name="Capability Assessment",
            description=(
                "What the threat actor can do — resources, weapons, skills, reach. "
                "Evaluates the actor's demonstrated and assessed capabilities."
            ),
            required_analysis=["hypothesis_evaluation", "evidence_assessment", "indicator_tracking"],
            technique_affinity=["ach", "indicators"],
            requires_research=True,
            evidence_requirements="Technical intelligence, order of battle, capability demonstrations.",
        ),
        TaskSection(
            id="intent_analysis",
            name="Intent Analysis",
            description=(
                "What the threat actor wants to do — goals, motivations, doctrine. "
                "Analyzes stated and inferred intent, including historical patterns."
            ),
            required_analysis=["adversary_perspective", "assumption_check"],
            technique_affinity=["red_team", "assumptions"],
            requires_research=False,
            evidence_requirements="Doctrine, public statements, historical actions, intelligence reporting.",
        ),
        TaskSection(
            id="vulnerability_mapping",
            name="Vulnerability Mapping",
            description=(
                "What we are exposed to — attack surfaces, gaps in defense. "
                "Identifies exploitable vulnerabilities relevant to the threat."
            ),
            required_analysis=["outside_context", "high_impact_scenarios"],
            technique_affinity=["outside_in", "high_impact"],
            requires_research=False,
            evidence_requirements="Defensive posture assessments, known gaps, OPSEC assessments.",
        ),
        TaskSection(
            id="risk_matrix",
            name="Risk Matrix",
            description=(
                "Likelihood × impact assessment with prioritized risks. "
                "Synthesizes capability and intent into actionable risk rankings."
            ),
            required_analysis=["hypothesis_evaluation", "futures_analysis"],
            technique_affinity=["ach", "alt_futures"],
            requires_research=False,
            evidence_requirements="Probability estimates, consequence assessments.",
        ),
        TaskSection(
            id="dissenting_views",
            name="Dissenting Views",
            description=(
                "Challenges to the assessment and alternative interpretations. "
                "Surfaces minority views and contrarian analysis to reduce bias."
            ),
            required_analysis=["contrarian_analysis", "competing_hypotheses"],
            technique_affinity=["devils_advocacy", "team_ab"],
            requires_research=False,
            evidence_requirements="Alternative intelligence reports, dissenting analyst views.",
        ),
    ],
    default_techniques=["quality", "assumptions", "ach", "red_team", "indicators"],
)


# ---------------------------------------------------------------------------
# Preset 2: Quick Brief
# ---------------------------------------------------------------------------
_BRIEF = TaskType(
    id="brief",
    name="Quick Brief",
    description=(
        "Fast-turnaround intelligence product with BLUF-first structure. "
        "Use for time-sensitive reporting where the bottom line must lead."
    ),
    sections=[
        TaskSection(
            id="bluf",
            name="BLUF",
            description=(
                "Bottom Line Up Front — single-paragraph key judgment. "
                "States the analyst's main conclusion with confidence level."
            ),
            required_analysis=["key_judgment_synthesis"],
            technique_affinity=None,  # Planner decides based on question
            requires_research=False,
            evidence_requirements="Sufficient evidence to support a key judgment.",
        ),
        TaskSection(
            id="supporting_analysis",
            name="Supporting Analysis",
            description=(
                "Evidence and reasoning behind the BLUF. "
                "Documents the analytical basis for the key judgment."
            ),
            required_analysis=["evidence_assessment", "assumption_check", "hypothesis_evaluation"],
            technique_affinity=["quality", "assumptions", "ach"],
            requires_research=False,
            evidence_requirements="All evidence relevant to the key judgment.",
        ),
        TaskSection(
            id="dissenting_views",
            name="Dissenting Views",
            description=(
                "Challenges, alternative explanations, and low-confidence caveats. "
                "Ensures the brief acknowledges uncertainty and minority views."
            ),
            required_analysis=["contrarian_analysis"],
            technique_affinity=["devils_advocacy"],
            requires_research=False,
            evidence_requirements="Any evidence that cuts against the BLUF.",
        ),
        TaskSection(
            id="recommendations",
            name="Recommendations",
            description=(
                "Actionable next steps and collection priorities. "
                "Translates the analysis into concrete actions or collection gaps."
            ),
            required_analysis=["indicator_tracking", "gap_identification"],
            technique_affinity=["indicators"],
            requires_research=True,
            evidence_requirements="Collection gaps, known unknowns.",
        ),
    ],
    default_techniques=["quality", "assumptions", "devils_advocacy"],
)


# ---------------------------------------------------------------------------
# Preset 3: Battle Damage Assessment (BDA)
# ---------------------------------------------------------------------------
_BDA = TaskType(
    id="bda",
    name="Battle Damage Assessment (BDA)",
    description=(
        "Three-phase combat assessment per CJCSI 3162.02. "
        "Evaluates physical damage, functional impact, and target system effects. "
        "Use following kinetic strikes or targeting operations."
    ),
    sections=[
        TaskSection(
            id="target_identification",
            name="Target Identification",
            description=(
                "Target designation, coordinates, and target system membership. "
                "Establishes what was struck and its role in the adversary target system."
            ),
            required_analysis=["evidence_assessment", "background_research"],
            technique_affinity=None,
            requires_research=True,
            evidence_requirements="Strike package data, target coordinates, pre-strike imagery.",
        ),
        TaskSection(
            id="phase1_physical",
            name="Phase 1: Physical Damage Assessment",
            description=(
                "Observed and interpreted physical damage from imagery, mission reports, "
                "and weapon video. Assesses what was physically destroyed or degraded."
            ),
            required_analysis=["evidence_assessment", "indicator_tracking"],
            technique_affinity=["quality", "indicators"],
            requires_research=False,
            evidence_requirements="Post-strike imagery, BDA sensors, mission reports, weapon video.",
        ),
        TaskSection(
            id="phase2_functional",
            name="Phase 2: Functional Damage Assessment",
            description=(
                "Remaining operational capability and recuperation/replacement timeline. "
                "Assesses whether the target can still perform its intended function."
            ),
            required_analysis=["hypothesis_evaluation", "what_if_analysis"],
            technique_affinity=["ach", "what_if"],
            requires_research=False,
            evidence_requirements="Functional indicators, restoration activity, logistics reporting.",
        ),
        TaskSection(
            id="phase3_system",
            name="Phase 3: Target System Assessment",
            description=(
                "Aggregate impact on adversary target system capabilities. "
                "Evaluates how the strike affects the broader target system and campaign."
            ),
            required_analysis=["outside_context", "futures_analysis"],
            technique_affinity=["outside_in", "alt_futures"],
            requires_research=False,
            evidence_requirements="Target system analysis, aggregate effect reporting.",
        ),
        TaskSection(
            id="restrike_recommendation",
            name="Restrike Recommendation",
            description=(
                "Whether reattack is needed, priority, and rationale. "
                "Provides actionable recommendation for follow-on targeting."
            ),
            required_analysis=["hypothesis_evaluation", "high_impact_scenarios"],
            technique_affinity=["high_impact", "ach"],
            requires_research=False,
            evidence_requirements="Damage assessment results, target system requirements.",
        ),
        TaskSection(
            id="collateral_assessment",
            name="Collateral Assessment",
            description=(
                "Unintended effects outside the target boundary. "
                "Documents civilian and non-targeted infrastructure effects."
            ),
            required_analysis=["assumption_check", "contrarian_analysis"],
            technique_affinity=["assumptions", "devils_advocacy"],
            requires_research=False,
            evidence_requirements="Collateral damage assessment, civilian presence reporting.",
        ),
    ],
    default_techniques=["quality", "ach", "indicators", "what_if"],
)


# ---------------------------------------------------------------------------
# Preset 4: Annex B — Intelligence (OPORD)
# ---------------------------------------------------------------------------
_ANNEX_B = TaskType(
    id="annex_b",
    name="Annex B — Intelligence",
    description=(
        "Intelligence annex to an operations order (OPORD). "
        "Provides enemy situation, ISR tasks, and CI guidance per FM 34-10. "
        "Use when drafting or supporting an OPORD intelligence annex."
    ),
    sections=[
        TaskSection(
            id="enemy_forces",
            name="1. Situation — Enemy Forces",
            description=(
                "Composition, disposition, strength, recent activity, capabilities, "
                "and enemy courses of action (COAs). Core enemy situation paragraph."
            ),
            required_analysis=["adversary_perspective", "hypothesis_evaluation", "background_research"],
            technique_affinity=["red_team", "ach"],
            requires_research=True,
            evidence_requirements=(
                "Order of battle, recent SIGINT/HUMINT/GEOINT, enemy doctrine, "
                "PIR responses, intelligence summaries."
            ),
        ),
        TaskSection(
            id="terrain_weather",
            name="1. Situation — Terrain & Weather",
            description=(
                "Militarily significant terrain and weather effects on operations. "
                "OAKOC analysis (Observation, Avenues, Key terrain, Obstacles, Cover)."
            ),
            required_analysis=["outside_context", "background_research"],
            technique_affinity=["outside_in"],
            requires_research=True,
            evidence_requirements="Terrain analysis, weather forecasts, OAKOC assessments.",
        ),
        TaskSection(
            id="mission",
            name="2. Mission",
            description=(
                "Intelligence mission in support of the OPORD. "
                "States the intelligence task and purpose derived from the commander's PIR."
            ),
            required_analysis=["mission_derivation"],
            technique_affinity=None,
            requires_research=False,
            evidence_requirements="Commander's PIR, OPORD mission statement.",
        ),
        TaskSection(
            id="scheme_of_support",
            name="3a. Scheme of Intelligence Support",
            description=(
                "ISR concept, collection priorities, and intelligence architecture. "
                "Describes how intelligence support is organized and sequenced."
            ),
            required_analysis=["indicator_tracking", "assumption_check"],
            technique_affinity=["indicators", "assumptions"],
            requires_research=False,
            evidence_requirements="Collection asset inventory, PIR, ISR task organization.",
        ),
        TaskSection(
            id="subordinate_tasks",
            name="3b. Tasks to Subordinate Units",
            description=(
                "Unit-specific intelligence acquisition tasks. "
                "Translates collection requirements into unit taskings."
            ),
            required_analysis=["indicator_tracking"],
            technique_affinity=["indicators"],
            requires_research=False,
            evidence_requirements="Collection requirements, unit capabilities.",
        ),
        TaskSection(
            id="counterintelligence",
            name="3c. Counterintelligence",
            description=(
                "CI guidance, OPSEC measures, and threat to friendly force. "
                "Addresses adversary collection threats and protective measures."
            ),
            required_analysis=["adversary_perspective", "assumption_check"],
            technique_affinity=["red_team", "assumptions"],
            requires_research=False,
            evidence_requirements="CI assessments, OPSEC reviews, adversary collection reporting.",
        ),
        TaskSection(
            id="coordinating_instructions",
            name="3d. Coordinating Instructions",
            description=(
                "PIR, LTIOV, reporting procedures, and document/material handling. "
                "Administrative and procedural guidance for intelligence activities."
            ),
            required_analysis=["indicator_tracking"],
            technique_affinity=["indicators"],
            requires_research=False,
            evidence_requirements="PIR list, reporting timelines, handling procedures.",
        ),
        TaskSection(
            id="intelligence_estimate",
            name="Appendix 1: Intelligence Estimate",
            description=(
                "Formal estimate: enemy COAs, relative probability, and vulnerabilities. "
                "The analytical heart of the Annex B — structured enemy COA analysis."
            ),
            required_analysis=["hypothesis_evaluation", "competing_hypotheses", "futures_analysis"],
            technique_affinity=["ach", "team_ab", "alt_futures"],
            requires_research=False,
            evidence_requirements="All enemy situation reporting, COA analysis, vulnerability assessments.",
        ),
    ],
    default_techniques=["quality", "assumptions", "ach", "red_team", "indicators"],
)


# ---------------------------------------------------------------------------
# Preset 5: Annex L — Information Collection / Collection Plan
# ---------------------------------------------------------------------------
_ANNEX_L = TaskType(
    id="annex_l",
    name="Annex L — Information Collection",
    description=(
        "Intelligence collection plan annex to an OPORD. "
        "Translates PIRs into collection requirements per FM 3-55. "
        "Use when building or reviewing a collection plan."
    ),
    sections=[
        TaskSection(
            id="priority_intelligence_requirements",
            name="Priority Intelligence Requirements",
            description=(
                "Commander's PIRs derived from the question/scenario. "
                "The foundation of the collection plan — what the commander must know."
            ),
            required_analysis=["assumption_check", "hypothesis_evaluation"],
            technique_affinity=["assumptions", "ach"],
            requires_research=False,
            evidence_requirements="Commander's critical information requirements, mission analysis.",
        ),
        TaskSection(
            id="specific_information_requirements",
            name="Specific Information Requirements",
            description=(
                "Indicators and SIRs that answer each PIR. "
                "Decomposes PIRs into observable, collectable information requirements."
            ),
            required_analysis=["indicator_tracking"],
            technique_affinity=["indicators"],
            requires_research=False,
            evidence_requirements="PIR list, intelligence gaps, existing collection.",
        ),
        TaskSection(
            id="collection_asset_assessment",
            name="Collection Asset Assessment",
            description=(
                "Available collection means, capabilities, and limitations. "
                "Matches collection requirements to available assets."
            ),
            required_analysis=["evidence_assessment", "background_research"],
            technique_affinity=["quality"],
            requires_research=True,
            evidence_requirements="Collection asset inventory, capability assessments, availability.",
        ),
        TaskSection(
            id="collection_matrix",
            name="Collection Matrix",
            description=(
                "PIR × Agency tasking matrix with priorities and NAIs. "
                "The operational product — who collects what, where, and when."
            ),
            required_analysis=["indicator_tracking", "hypothesis_evaluation"],
            technique_affinity=["indicators", "ach"],
            requires_research=False,
            evidence_requirements="PIR, SIR, available collectors, NAI list.",
        ),
        TaskSection(
            id="indicator_worksheet",
            name="Indicator Worksheet",
            description=(
                "Observable indicators, supported PIR/IR, and priority weighting. "
                "Detailed indicator list for collection tasking and reporting."
            ),
            required_analysis=["indicator_tracking", "assumption_check"],
            technique_affinity=["indicators", "assumptions"],
            requires_research=False,
            evidence_requirements="Intelligence gaps, expected enemy actions, PIR.",
        ),
        TaskSection(
            id="dissemination_plan",
            name="Dissemination Plan",
            description=(
                "Who gets what intelligence, when, and in what format. "
                "Ensures collected intelligence reaches the right consumers."
            ),
            required_analysis=["structural"],
            technique_affinity=None,  # Structural — no technique affinity
            requires_research=False,
            evidence_requirements="Intelligence consumer list, reporting timelines, formats.",
        ),
        TaskSection(
            id="synchronization",
            name="Synchronization",
            description=(
                "Timing alignment with operational phases and LTIOV. "
                "Ensures collection is timed to support decision points."
            ),
            required_analysis=["what_if_analysis", "futures_analysis"],
            technique_affinity=["what_if", "alt_futures"],
            requires_research=False,
            evidence_requirements="Operational timeline, decision points, LTIOV.",
        ),
    ],
    default_techniques=["assumptions", "indicators", "ach"],
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PRESETS: dict[str, TaskType] = {
    "threat": _THREAT,
    "brief": _BRIEF,
    "bda": _BDA,
    "annex_b": _ANNEX_B,
    "annex_l": _ANNEX_L,
}


def get_preset(task_type_id: str) -> TaskType:
    """Return a preset TaskType by ID.

    Raises ValueError for unknown IDs with a helpful message listing available types.
    """
    if task_type_id not in PRESETS:
        available = ", ".join(sorted(PRESETS.keys()))
        raise ValueError(
            f"Unknown task type: {task_type_id!r}. Available: {available}"
        )
    return PRESETS[task_type_id]


def list_presets() -> list[TaskType]:
    """Return all preset TaskTypes in a stable order."""
    return [PRESETS[k] for k in ("threat", "brief", "bda", "annex_b", "annex_l")]
