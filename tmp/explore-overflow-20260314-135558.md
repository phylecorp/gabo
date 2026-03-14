Excellent! I now have a comprehensive understanding of the codebase. Let me provide a detailed report.

## Codebase Exploration Report: SAT

### 1. Project Identity and Purpose

**SAT** stands for **Structured Analytic Techniques**. It's a comprehensive intelligence analysis tool that implements the 12 techniques from the CIA's *Tradecraft Primer* — a declassified methodology designed to reduce cognitive bias and improve analytical rigor. The tool is designed to run selected techniques sequentially, with each building on prior results, then synthesize findings into a bottom-line assessment with supporting analysis.

### 2. Overall Architecture

SAT is a **hybrid multi-platform tool** consisting of:

- **Python Backend**: Core CLI tool + research & analysis engine (3 entry points)
- **Electron Desktop App**: GUI for interactive analysis and settings management
- **REST + WebSocket API**: Real-time analysis pipeline for programmatic access
- **MCP Server**: Model Context Protocol integration for agent workflows

The architecture follows a **pipeline model** with these phases:

1. **Phase 0 (Research)**: Optionally gathers evidence via multiple research backends (Perplexity, Brave, OpenAI deep research, Gemini deep research, LLM-based fallback)
2. **Preprocessing**: Format detection, token budgeting, and evidence reduction for diverse inputs
3. **Technique Selection**: Auto-selects or uses user-specified techniques from 12 available
4. **Sequential Execution**: Runs techniques with prior results threading
5. **Adversarial Critique**: Optional multi-model debate (dual-mode or trident-mode with investigator)
6. **Synthesis**: Cross-technique integration with confidence levels
7. **Output**: Artifacts written to `sat-{run_id}/` directory

### 3. Main Entry Points

**CLI:**
- `sat analyze` — Primary command for structured analysis
- `sat list-techniques` — Discover available techniques

**Python Library:**
- Direct import of `sat.pipeline.run_analysis()` for programmatic use

**MCP Server:**
- `sat-mcp` — Stdio protocol server exposing 6 analysis tools for LLM agents

**REST API:**
- `sat-api --port 8742` — FastAPI + WebSocket server for web/desktop clients

**Desktop GUI:**
- Electron app with React + TypeScript, connects to the Python API via HTTP/WebSocket

### 4. Languages and Frameworks

**Backend (Python 3.11+):**
- **Async runtime**: asyncio throughout
- **CLI**: Typer (type-hint-based auto-completion)
- **LLM abstraction**: Protocol-based (structural typing, no inheritance)
- **Data models**: Pydantic v2 (BaseModel with JSON Schema validation)
- **API server**: FastAPI + uvicorn + WebSocket
- **HTTP client**: httpx (async)
- **Markdown**: Jinja2 templates + python-markdown

**Frontend (Node.js/TypeScript):**
- **Framework**: Electron + React 19
- **Routing**: React Router 7
- **Build**: electron-vite with Tailwind CSS
- **State**: TanStack React Query
- **UI**: Tailwind CSS

**Infrastructure:**
- **Build**: Hatchling (Python packages)
- **Testing**: pytest + pytest-asyncio (Python)
- **Linting**: ruff (Python)
- **MCP**: mcp[cli] package

### 5. Directory Structure (High Level)

```
/Users/ianroos/Documents/phyle/sat/
├── src/sat/                           # Main Python package (129 .py files, ~14.8k LOC)
│   ├── cli.py                         # CLI entry point (Typer)
│   ├── pipeline.py                    # Core orchestrator
│   ├── config.py                      # Configuration model
│   ├── artifacts.py                   # Output writing
│   ├── errors.py                      # Custom exceptions
│   ├── events.py                      # Event bus for progress
│   ├── mcp_server.py                  # MCP protocol server
│   ├── mcp_session.py                 # MCP session management
│   │
│   ├── models/                        # Pydantic models for all artifacts
│   │   ├── base.py                    # ArtifactResult base class
│   │   ├── {technique}.py             # Per-technique models (12 techniques)
│   │   ├── adversarial.py             # Critique/rebuttal/convergence models
│   │   ├── research.py                # ResearchResult, ResearchClaim models
│   │   ├── preprocessing.py           # Preprocessing metadata
│   │   ├── synthesis.py               # Synthesis output model
│   │   └── ...
│   │
│   ├── prompts/                       # LLM prompts as Python templates
│   │   ├── base.py                    # Utilities (date injection)
│   │   ├── {technique}.py             # Per-technique prompts
│   │   ├── adversarial.py             # Critique/rebuttal prompts
│   │   ├── research.py                # Research query generation
│   │   ├── preprocessing.py           # Evidence conversion prompts
│   │   └── ...
│   │
│   ├── providers/                     # LLM provider implementations
│   │   ├── base.py                    # LLMProvider protocol
│   │   ├── anthropic.py               # Claude API (default)
│   │   ├── openai.py                  # OpenAI (o1/o3 reasoning models)
│   │   ├── gemini.py                  # Google Gemini
│   │   ├── registry.py                # Auto-selection and creation
│   │   └── ...
│   │
│   ├── techniques/                    # Technique implementations
│   │   ├── base.py                    # Technique protocol & context
│   │   ├── registry.py                # Technique lookup & iteration
│   │   ├── selector.py                # LLM-based technique selection
│   │   ├── synthesis.py               # Cross-technique synthesis
│   │   ├── diagnostic/                # Quality, Assumptions, ACH, Indicators (4)
│   │   ├── contrarian/                # Devils Advocacy, Team A/B, High Impact, What-if (4)
│   │   ├── imaginative/               # Brainstorming, Outside-In, Red Team, Alt Futures (4)
│   │   └── ...
│   │
│   ├── research/                      # Evidence gathering backends
│   │   ├── base.py                    # ResearchProvider protocol
│   │   ├── perplexity.py              # Sonar deep research API
│   │   ├── brave.py                   # Web search API
│   │   ├── llm_search.py              # LLM-only fallback
│   │   ├── openai_deep.py             # OpenAI o1 deep research
│   │   ├── gemini_deep.py             # Gemini deep research (async polling)
│   │   ├── runner.py                  # Single-provider orchestrator
│   │   ├── multi_runner.py            # Parallel multi-provider runner
│   │   ├── structurer.py              # Raw research → structured claims
│   │   ├── registry.py                # Auto-selection with priority
│   │   ├── verification/              # Source verification (URL fetching, extraction, assessment)
│   │   └── ...
│   │
│   ├── adversarial/                   # Multi-model debate
│   │   ├── config.py                  # Adversarial configuration
│   │   ├── pool.py                    # Provider pool with role assignment
│   │   ├── session.py                 # Critique-rebuttal-convergence orchestrator
│   │   └── ...
│   │
│   ├── preprocessing/                 # Evidence preprocessing pipeline
│   │   ├── detector.py                # Format detection (JSON, CSV, XML, HTML, code, logs, markdown)
│   │   ├── measurer.py                # Token counting and budgeting
│   │   ├── preprocessor.py            # Orchestrator
│   │   └── ...
│   │
│   ├── ingestion/                     # Document parsing & fetching
│   │   ├── parser.py                  # Docling-based PDF/document extraction
│   │   ├── fetcher.py                 # URL fetching with httpx
│   │   ├── orchestrator.py            # Combine parsing & fetching
│   │   └── ...
│   │
│   ├── evidence/                      # Interactive evidence curation (Waves 3+4)
│   │   ├── formatter.py               # Evidence formatting
│   │   ├── gatherer.py                # Evidence aggregation
│   │   └── ...
│   │
│   ├── decomposition/                 # Question decomposition (Phase 8+)
│   │   ├── extractor.py               # Extract sub-questions
│   │   ├── deduplicator.py            # Remove duplicates
│   │   ├── prompts.py                 # Decomposition prompts
│   │   └── ...
│   │
│   ├── report/                        # Executive report generation
│   │   ├── renderers.py               # Technique-specific Markdown renderers
│   │   ├── descriptions.py            # Metadata descriptions
│   │   └── ...
│   │
│   └── api/                           # REST + WebSocket server (FastAPI)
│       ├── app.py                     # App factory
│       ├── main.py                    # Entry point (sat-api)
│       ├── run_manager.py             # In-process run registry
│       ├── evidence_manager.py        # Evidence session management
│       ├── models.py                  # API request/response models
│       ├── ws.py                      # WebSocket event subscription
│       └── routes/                    # API endpoints
│
├── desktop/                           # Electron + React GUI
│   ├── src/                           # React components & logic
│   ├── package.json                   # Node dependencies (React 19, React Router 7, TanStack Query)
│   ├── electron.vite.config.ts        # Electron build config
│   └── dev.sh                         # Dev server startup
│
├── tests/                             # Test suite (~43 test files)
│   ├── conftest.py                    # Fixtures & global setup
│   ├── test_adversarial/              # Adversarial debate tests
│   ├── test_preprocessing/            # Preprocessing pipeline tests
│   ├── test_integration.py            # End-to-end tests
│   ├── integration/                   # Tests marked with @pytest.mark.integration (skipped by default)
│   │   ├── test_openai_live.py        # Real OpenAI API tests
│   │   ├── test_gemini_live.py        # Real Gemini API tests
│   │   └── ...
│   └── ...
│
├── MASTER_PLAN.md                     # Project roadmap (8 phases, comprehensive decision log)
├── DECISIONS.md                       # Auto-generated decision registry from @decision annotations
├── README.md                          # 314 lines covering all features, usage, providers
├── pyproject.toml                     # Python package config + optional dependencies
├── Makefile                           # Test, lint, format, install targets
└── .env.example                       # Configuration template
```

### 6. Known Performance Considerations

The codebase does NOT document explicit performance issues, but the architecture reveals several areas that may warrant optimization in Phase 8+:

1. **Sequential Technique Execution**: Techniques run one at a time (by design) with prior results threading. This is intentional for dependency ordering but means total runtime is sum of all technique runtimes.

2. **Multi-Provider Parallelism**: Research providers (Perplexity, Brave, OpenAI deep, Gemini deep) run in parallel via `multi_runner.py` with graceful degradation — this is well-architected.

3. **Adversarial Critique Rounds**: Each technique generates output → challenger critique → rebuttal (2 rounds by default, configurable). This multiplies the number of LLM calls by ~3x per technique.

4. **Evidence Preprocessing**: Token measurement and reduction via map-reduce adds LLM calls if evidence exceeds context budget. Format conversion happens before reduction.

5. **Token Budgeting**: Evidence is allocated 40% of context window by default (`DEC-PREPROC-003`), reducing available output tokens.

6. **API Polling for Deep Research**: OpenAI and Gemini deep research use async polling with configurable intervals, adding latency vs. instant completion.

**Notable optimizations already in place:**
- **Lazy provider creation** in `ProviderPool` (DEC-ADV-003)
- **Passthrough optimization** for evidence that fits budget (skips preprocessing, DEC-PREPROC-006)
- **Cheap model for verification** in source verification (DEC-VERIFY-004)
- **Bounded concurrency** in verification fetching with `asyncio.Semaphore` (DEC-VERIFY-003)
- **Per-technique max_tokens override** for large-output techniques like ACH (16384 tokens, DEC-TECH-ACH-002)

### 7. Key Technical Decisions (Highlights)

**Architecture:**
- **Protocol-based providers** (structural typing) instead of inheritance for pluggability
- **Event bus** for real-time progress visibility (replaced spinners suppressing output)
- **Numbered artifacts** with manifest.json for reproducibility
- **Sequential + prior-results threading** for technique interdependencies

**LLM Integration:**
- **Anthropic structured output API** for validation (Claude)
- **OpenAI reasoning models** (o1/o3) with developer-role-only prompts
- **Gemini** via google-genai SDK with response_schema validation
- **Auto-selection** of challenger provider with env-var fallback

**Data Models:**
- **Pydantic v2** BaseModel everywhere (validation, serialization, schema)
- **Defaults on all fields** except base identifiers (prevents LLM output crashes)
- **Safety net validator** for double-encoded JSON strings from tool_use blocks

**Testing:**
- **Integration tests** use protocol-conforming doubles, not mocks
- **Live API tests** isolated under `tests/integration/`, skipped by default
- **Per-technique unit tests** validate end-to-end execution

### Summary

SAT is a sophisticated, well-architected intelligence analysis pipeline that automates CIA tradecraft methods via multiple LLM providers and research backends. It combines a Python backend (CLI, API, MCP server) with an Electron desktop GUI, supporting both local analysis and real-time multi-provider debate. The codebase shows careful attention to error resilience, evidence handling, and extensibility. Phase 8 introduced executive report generation; the plan extends to Phase 8+ with pipeline resilience improvements and question decomposition.
