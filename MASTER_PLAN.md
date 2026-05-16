# MASTER_PLAN: SAT — Structured Analytic Techniques

## Identity

**Type:** CLI + Desktop App (Electron)
**Languages:** Python (70%), TypeScript (25%), CSS (5%)
**Root:** /Users/joel/dev/src/sat
**Created:** 2025-02-13
**Last updated:** 2026-04-14

SAT is a 12-technique CIA Tradecraft Primer analysis pipeline with multi-model adversarial critique, deep research, evidence preprocessing, and executive report generation. It exposes a CLI, a FastAPI REST+WebSocket API, and an Electron desktop frontend. The pipeline leverages model diversity across Anthropic, OpenAI, and Gemini for higher-quality intelligence assessments.

## Architecture

```
src/sat/              — Python backend: pipeline, config, models, providers, techniques
src/sat/api/          — FastAPI routes (analysis, config, evidence, runs, websocket)
src/sat/providers/    — LLM provider implementations (anthropic, openai, gemini)
src/sat/research/     — Deep research backends (perplexity, brave, openai_deep, gemini_deep, multi_runner)
src/sat/adversarial/  — Multi-model critique/rebuttal/adjudication (config, pool, session)
src/sat/techniques/   — 12 CIA tradecraft technique implementations
src/sat/models/       — Pydantic v2 models for all artifacts, config, events
src/sat/preprocessing/ — Evidence format detection, measurement, reduction
src/sat/report/       — Executive report builder with technique-specific renderers
desktop/              — Electron + React + TypeScript frontend
desktop/src/renderer/ — React pages, components, hooks, API client
tests/                — Unit and integration tests (pytest)
```

## Original Intent

> The SAT tool is a complete 12-technique CIA Tradecraft Primer analysis pipeline with multi-model adversarial critique and deep research. The goal is a self-sufficient analytical tool that leverages model diversity and automated research for higher-quality intelligence assessments.

## Principles

1. **Pydantic is Truth** — All data structures use Pydantic v2 BaseModel. Schema, validation, serialization, and structured LLM output flow from one source of truth.
2. **Provider Agnostic** — The pipeline works with any LLM provider. Protocol-based structural typing (LLMProvider, ResearchProvider) over inheritance. New providers add without modifying existing code.
3. **Evidence Preservation** — Every artifact, research finding, and adversarial exchange is persisted to disk with provenance. Analysis is reproducible and auditable.
4. **Graceful Degradation** — Missing providers, failed research, transient API errors: the pipeline continues with what it has rather than failing entirely.
5. **CLI Parity** — Every feature available in the desktop UI is available via CLI. Configuration resolution order (CLI flag > config file > env var > default) applies everywhere.

---

## Decision Log

Append-only record of significant decisions across all initiatives. Each entry references
the initiative and decision ID. This log persists across initiative boundaries — it is the
project's institutional memory.

| Date | DEC-ID | Initiative | Decision | Rationale |
|------|--------|-----------|----------|-----------|
| 2025-02-13 | DEC-PLAN-001 | core | Optional deps for new providers | Users only install providers they need |
| 2025-02-13 | DEC-PLAN-002 | core | Research as Phase 0 before technique selection | Evidence stays `str \| None`; techniques never know evidence came from research |
| 2025-02-13 | DEC-PLAN-003 | core | Adversarial as pipeline wrapper | Existing techniques untouched; critique layer wraps around them |
| 2025-02-13 | DEC-PLAN-004 | core | Pluggable research backends with auto-selection | Priority: Perplexity > Brave > LLM based on available API keys |
| 2025-02-13 | DEC-SCHEMA-001 | core | Pydantic v2 BaseModel for all artifacts | Single source of truth for schema, validation, serialization |
| 2025-02-13 | DEC-CFG-001 | core | Pydantic models for config with env var fallback | CLI > env > file precedence |
| 2025-02-13 | DEC-LLM-001 | core | Abstract LLMProvider protocol | Structural typing for pluggability |
| 2025-02-13 | DEC-PIPE-001 | core | Sequential execution with prior-results threading | Techniques build on each other |
| 2025-02-13 | DEC-RESEARCH-006 | core | Auto-selection registry for research backends | Priority-based fallback |
| 2025-02-13 | DEC-RESEARCH-009 | core | OpenAI deep research via Responses API | Async polling for deep research |
| 2025-02-13 | DEC-RESEARCH-010 | core | Gemini deep research via Interactions API | Async polling for Gemini deep research |
| 2025-02-13 | DEC-RESEARCH-011 | core | Parallel multi-provider deep research | Multiple providers run concurrently, best result wins |
| 2025-02-13 | DEC-RESEARCH-012 | core | Research API keys resolved from config file before env var | Settings UI keys now picked up by research |
| 2025-02-13 | DEC-CFG-002 | core | resolve_investigator_provider finds the third provider | Trident mode investigator resolution |
| 2025-02-13 | DEC-CFG-003 | core | Config file loaded in resolve_api_key | Settings UI keys applied without restart |
| 2025-02-13 | DEC-REPORT-001 | core | ReportBuilder reads manifest.json and assembles Jinja2-rendered reports | Disk-based artifact loading |
| 2025-02-13 | DEC-REPORT-002 | core | Technique-specific renderer registry with generic fallback | Proper table/structure per technique |
| 2025-02-13 | DEC-REPORT-003 | core | Single-file HTML with embedded CSS/JS | No external dependencies at runtime |
| 2025-02-13 | DEC-PIPE-RESIL-001 | core | Retry guard wraps model_validate in provider _retry_structured | RuntimeError with context is actionable |
| 2025-02-13 | DEC-PIPE-RESIL-002 | core | _short_error helper for console status | Error class + summary in spinner |
| 2025-02-13 | DEC-PIPE-RESIL-003 | core | _is_transient classifier for single technique-level retry | One retry covers most transient API hiccups |
| 2026-03-15 | DEC-MODELS-001 | model-selection | Hybrid model listing: API for OpenAI/Gemini, curated for Anthropic/Perplexity | API listing gives real-time accuracy; curated lists for providers without listing APIs |
| 2026-03-15 | DEC-MODELS-002 | model-selection | `research_model` field in config.json alongside `default_model` | Research providers need separate model configuration |
| 2026-03-15 | DEC-MODELS-003 | model-selection | Research providers accept model override from config | Instance-level model with config-file fallback replaces module-level constants |
| 2026-03-15 | DEC-MODELS-004 | model-selection | Settings dropdowns populated from models endpoint with free-text fallback | Dropdowns for usability, fallback for resilience |
| 2026-03-30 | DEC-BUILD-001 | distribution | PyInstaller spec file over CLI arguments | Spec file allows conditional logic, data files, hidden imports in one auditable place |
| 2026-03-30 | DEC-BUILD-002 | distribution | `--onedir` mode instead of `--onefile` for sidecar | Faster startup, easier debugging, compatible with electron-builder extraResources |
| 2026-03-30 | DEC-BUILD-003 | distribution | Platform-conditional sidecar path resolution via `process.resourcesPath` | Dev: python -m; production: binary from app resources directory |
| 2026-03-30 | DEC-BUILD-004 | distribution | Separate `dist:mac` and `dist:win` scripts, no cross-compilation | PyInstaller cannot cross-compile; CI matrix builds each platform natively |
| 2026-03-30 | DEC-BUILD-005 | distribution | `sys._MEIPASS`-aware resource path helper | Resolves paths relative to _MEIPASS when frozen, source tree otherwise |
| 2026-03-30 | DEC-BUILD-006 | distribution | GitHub Actions release workflow with matrix build | macos-latest + windows-latest runners, tag-triggered with artifact upload |

---

## Active Initiatives

### Initiative: Template-Driven Analysis (Task Mode)
**Status:** active
**Started:** 2026-04-14
**Goal:** Invert the pipeline — start from a deliverable template (threat assessment, BDA, Annex B, etc.), work backwards to determine required techniques, research, and evidence, then render results into the template format.

> Real intelligence work often starts from a deliverable, not a question. An analyst has a template to fill — an Annex B, a collection plan, a threat assessment — and needs to figure out what analysis to run. Task mode wraps the existing pipeline with a planning layer that maps template sections to techniques, identifies evidence gaps, and renders results into the deliverable's structure.

**Dominant Constraint:** analytical quality (section-to-technique mappings must produce useful content)

#### Phases

##### Phase 1 — Preset Task Types + Planner (foundation)
**Status:** in-progress
**Effort:** ~1 week

New package `src/sat/tasks/` with:
- `models.py` — TaskType, TaskSection, TaskPlan, SectionMapping (Pydantic v2)
- `presets.py` — 5 built-in task types: Threat Assessment, Quick Brief, BDA, Annex B, Annex L
- `planner.py` — LLM-powered section-to-technique mapper (reuses TECHNIQUE_DESCRIPTIONS from `src/sat/prompts/selector.py`)
- CLI: `sat task <type> <question> [--evidence ...] [--list-types]`
- API: `POST /api/task` endpoint

**Integration:** Planner outputs an `AnalysisConfig` passed to existing `run_analysis()`. Techniques field set explicitly; research queries feed into `ResearchConfig`. Existing pipeline unchanged.

##### Phase 2 — Task-Aware Rendering (output)
**Status:** planned, blocked by Phase 1
**Effort:** ~1 week

- `renderer.py` — TaskRenderer: maps technique artifacts to template sections with per-section LLM synthesis
- Task-specific Jinja2 templates in `src/sat/tasks/templates/`
- Reuses existing technique renderers and `write_llm()` pattern

##### Phase 3 — Arbitrary Template Upload + Evidence Gap Analysis (generalization)
**Status:** planned, blocked by Phase 2
**Effort:** ~1-2 weeks

- `analyzer.py` — LLM-powered: upload PDF/DOCX to auto-generate TaskType definition
- Evidence gap analysis as pre-analysis step
- Human-in-the-loop review of auto-generated TaskType before execution

##### Critical Files
- `src/sat/tasks/` (new package — models, presets, planner, renderer)
- `src/sat/tasks/templates/` (new — 5 Jinja2 templates)
- `src/sat/cli.py` (modified — `task` subcommand)
- `src/sat/api/routes/analysis.py` (modified — task endpoint)
- `src/sat/prompts/selector.py` (reused — TECHNIQUE_DESCRIPTIONS)
- `src/sat/report/renderers.py` (reused — per-technique renderers)

### Initiative: Distributable Desktop Application — Remaining
**Status:** active (nearly complete)
**Goal:** Complete the CI/CD release workflow — the only remaining item from the Distribution initiative.

**W3-1: GitHub Actions release workflow (#25)** — Weight: L, Gate: approve
- Create `.github/workflows/release.yml` with matrix strategy: `[macos-latest, windows-latest]`
- Tag-triggered + manual `workflow_dispatch`
- All prerequisite waves (W1 + W2) are implemented and merged

---

## Completed Initiatives

| Initiative | Period | Phases | Key Decisions | Archived |
|-----------|--------|--------|---------------|----------|
| Core Pipeline (Phases 1-8) | 2025-02-13 to 2026-03-14 | 8 phases, all P0s delivered | DEC-SCHEMA-001, DEC-CFG-001, DEC-LLM-001, DEC-PIPE-001, DEC-RESEARCH-006, DEC-RESEARCH-011, DEC-ADV-001, DEC-REPORT-001, DEC-PIPE-RESIL-001 | N/A |
| Dynamic Model Selection | 2026-03-15 to 2026-03-16 | 2 waves (W1: 4 parallel, W2: 1), all completed | DEC-MODELS-001, DEC-MODELS-002, DEC-MODELS-003, DEC-MODELS-004 | N/A |
| UX Polish & Analytical Quality | 2026-03-30 to 2026-04-14 | 1 wave (3 parallel), all completed | DEC-TEMPLATE-003, DEC-SYNDICATION-002 | N/A |
| Distributable Desktop App (W1+W2) | 2026-03-30 to 2026-04-14 | 2 waves (W1: 2 parallel, W2: 2 parallel), all completed | DEC-BUILD-001 through DEC-BUILD-006 | N/A |

**Core Pipeline Summary:** Built the complete SAT analysis pipeline from scratch: 12 CIA tradecraft techniques, 3 LLM providers (Anthropic, OpenAI, Gemini), deep research with Perplexity/Brave/OpenAI/Gemini, adversarial critique in dual and trident modes, evidence preprocessing, executive report generation, desktop Electron frontend with real-time WebSocket progress, and pipeline resilience with transient error retry. 8 phases, all completed and merged to main.

**Dynamic Model Selection Summary:** Added model listing endpoint with hybrid API/curated approach, research model config storage, research provider model wiring from config, model passthrough fix with integration tests, and Settings UI dropdowns with free-text fallback.

**UX Polish Summary:** Welcome dashboard with onboarding when no runs exist, report template upload/management with custom template support in Settings, source syndication detection with domain clustering and wire service awareness injected into technique prompts.

**Distribution Summary (W1+W2):** PyInstaller spec with hidden imports and data file bundling, MEIPASS-aware resource path helper, platform-aware Electron sidecar with health polling and graceful shutdown, electron-builder config for macOS DMG and Windows NSIS, sidecar build validation and integration smoke tests.

---

## Parked Issues

Issues not belonging to any active initiative. Tracked for future consideration.

| Issue | Description | Reason Parked |
|-------|-------------|---------------|
| #6 | Change temp on creatives | Needs scoping — which techniques need temperature adjustment |
| #7 | Handling API Keys | Partially addressed by Settings UI; remaining UX issues deferred |
| #8 | Research with Brave should be iterative | Architecture decision needed — separate initiative |
