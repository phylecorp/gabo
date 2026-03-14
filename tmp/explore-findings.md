# SAT Project Configuration & Environment Variables — Complete Exploration

## 1. Existing Documentation

**README.md** (comprehensive):
- Purpose: CIA Tradecraft Primer-based structured analytic techniques automation
- Quick start, installation, usage, techniques reference, adversarial critique, MCP server, providers, and development info
- Python 3.11+ required
- Installation: `pip install -e .` (Anthropic), `pip install -e ".[all]"` (all providers), `pip install -e ".[dev]"` (development)

**Key docs location**: `/Users/ianroos/Documents/phyle/sat/README.md`

---

## 2. Environment Configuration Files

### .env.example
**Location**: `/Users/ianroos/Documents/phyle/sat/.env.example`

**Contents**:
```
# API Keys
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=

# Default models (override per provider)
ANTHROPIC_MODEL=claude-opus-4-6
OPENAI_MODEL=o3
GEMINI_MODEL=gemini-2.5-pro
```

**Note**: `.env` file is NOT tracked (uses `python-dotenv` for automatic loading)

---

## 3. Complete Environment Variables List

### LLM Provider API Keys & Models

| Variable | Purpose | Used By | Default |
|----------|---------|---------|---------|
| `ANTHROPIC_API_KEY` | Anthropic Claude API authentication | Primary/challenger/investigator provider | Required if using Anthropic |
| `ANTHROPIC_MODEL` | Override Anthropic model | CLI/config | `claude-opus-4-6` |
| `OPENAI_API_KEY` | OpenAI API authentication | Primary/challenger/investigator provider | Required if using OpenAI |
| `OPENAI_MODEL` | Override OpenAI model | CLI/config | `o3` |
| `OPENAI_DEEP_RESEARCH_FALLBACK` | Fallback model for OpenAI deep research | `openai_deep` research provider | `o4-mini-deep-research-2025-06-26` |
| `GEMINI_API_KEY` | Google Gemini API authentication | Primary/challenger/investigator provider | Required if using Gemini |
| `GEMINI_MODEL` | Override Gemini model | CLI/config | `gemini-2.5-pro` |

### Research Provider API Keys

| Variable | Purpose | Provider | Notes |
|----------|---------|----------|-------|
| `PERPLEXITY_API_KEY` | Perplexity sonar-deep-research API key | Perplexity research backend | Auto-selected if available (priority 1) |
| `BRAVE_API_KEY` | Brave Search API key | Brave search backend | Auto-selected if Perplexity unavailable (priority 2) |

### MCP Server Configuration

| Variable | Purpose | Usage | Default |
|----------|---------|-------|---------|
| `SAT_OUTPUT_DIR` | Directory for artifact output | MCP server | `.` (current directory) |
| `SAT_PRIMARY_PROVIDER` | Primary LLM provider for MCP | MCP server initialization | `anthropic` |
| `SAT_PRIMARY_MODEL` | Override primary model | MCP server | Provider default (resolved per provider) |
| `SAT_PRIMARY_API_KEY` | Primary API key override | MCP server (falls back to provider env var) | — |
| `SAT_ADVERSARIAL_ENABLED` | Enable adversarial analysis in MCP | MCP server | Disabled (values: true, 1, yes) |
| `SAT_CHALLENGER_PROVIDER` | Challenger provider for MCP | MCP server | `anthropic` (if adversarial enabled) |
| `SAT_CHALLENGER_MODEL` | Override challenger model | MCP server | Provider default |
| `SAT_CHALLENGER_API_KEY` | Challenger API key override | MCP server (falls back to provider env var) | — |

### Special Notes on Environment Variable Resolution

**API Key Precedence** (for all providers):
1. CLI flag (`--api-key`, `--research-api-key`, etc.)
2. Config file value
3. Environment variable (provider-specific name)
4. Raises error if not found

**Model Resolution Precedence**:
1. CLI flag (`--model`, `--challenger-model`, etc.)
2. Environment variable (provider-specific name: `ANTHROPIC_MODEL`, `OPENAI_MODEL`, `GEMINI_MODEL`)
3. Built-in default per provider

**Research Provider Auto-Selection** (with `--research` flag):
1. Check for `PERPLEXITY_API_KEY` → use Perplexity sonar-deep-research
2. Check for `BRAVE_API_KEY` → use Brave Search
3. Fall back to LLM-only research (no external API needed)
4. Raise error if none available

---

## 4. Python Dependencies & Virtual Environment Setup

### pyproject.toml

**Build system**: `hatchling`

**Core dependencies**:
- typer>=0.15.0 (CLI framework)
- rich>=13.0 (terminal formatting)
- pydantic>=2.11 (config validation)
- anthropic>=0.45 (Anthropic SDK)
- jinja2>=3.1 (prompt templating)
- python-dotenv>=1.0 (environment loading)
- httpx>=0.27 (async HTTP)
- mcp[cli]>=1.0 (Model Context Protocol)

**Optional dependencies**:
```toml
[project.optional-dependencies]
openai = ["openai>=1.60"]              # For OpenAI provider
gemini = ["google-genai>=1.0"]         # For Gemini provider
all = ["openai>=1.60", "google-genai>=1.0"]  # Both OpenAI and Gemini
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25",
    "pytest-cov>=6.0",
    "ruff>=0.9",
    "mypy>=1.14",
]
```

**Installation commands**:
```bash
# Anthropic only (default, includes MCP)
pip install -e .

# All LLM providers (adds OpenAI, Google Gemini)
pip install -e ".[all]"

# Development (adds pytest, ruff, mypy)
pip install -e ".[dev]"

# Or use Makefile
make install   # creates venv and installs
```

**Entry points**:
- `sat` → `sat.cli:app` (main CLI)
- `sat-mcp` → `sat.mcp_server:main` (MCP server)

---

## 5. CLI Entry Points & Subcommands

### Main Command: `sat`

```bash
sat analyze "Question" [options]
sat list-techniques [options]
sat report <output-dir> [options]
```

#### `sat analyze` — Full Analysis Pipeline

**Positional argument**:
- `question` (required): The analytic question to investigate

**Evidence options**:
- `-e, --evidence TEXT` — Inline evidence text
- `-f, --evidence-file PATH` — File or directory of evidence files
- Stdin support if no flags provided and terminal not interactive

**Technique selection**:
- `-t, --techniques TEXT` — Comma-separated technique IDs (auto-selects all if omitted)
  - Valid IDs: `quality`, `assumptions`, `ach`, `indicators`, `devils_advocacy`, `team_ab`, `high_impact`, `what_if`, `brainstorming`, `outside_in`, `red_team`, `alt_futures`

**Output**:
- `-o, --output-dir PATH` — Artifact output directory (default: `.`)

**Primary LLM provider**:
- `-p, --provider TEXT` — Provider name (default: `anthropic`)
- `-m, --model TEXT` — Model identifier (overrides env var or default)
- `--api-key TEXT` — API key (overrides env var)

**Deep research**:
- `-r, --research / --no-research` — Enable/disable evidence gathering (default: off)
- `--research-provider TEXT` — Research backend: `perplexity`, `brave`, `openai_deep`, `gemini_deep`, `llm`, `auto` (default: `auto`)
- `--research-api-key TEXT` — API key for research provider
- `--research-mode TEXT` — `single` or `multi` (default: `multi`)

**Evidence preprocessing**:
- `--preprocess / --no-preprocess` — Enable/disable evidence preprocessing (default: on)
- `--evidence-budget FLOAT` — Fraction of context window for evidence (0.0–1.0)

**Adversarial analysis** (multi-model critique):
- `--adversarial / --no-adversarial` — Enable/disable adversarial (default: on)
- `--challenger-provider TEXT` — Challenger LLM provider (auto-detected if omitted)
- `--challenger-model TEXT` — Challenger model identifier
- `--rounds INT` — Critique-rebuttal rounds (default: 2)
- `--adversarial-mode TEXT` — `dual` (default) or `trident` (3-provider)
- `--investigator-provider TEXT` — Investigator provider for trident mode (auto-detected)
- `--investigator-model TEXT` — Investigator model identifier

**Configuration & reporting**:
- `-c, --config PATH` — TOML config file for multi-model setup
- `--report / --no-report` — Generate executive report (default: on)
- `--report-format TEXT` — `markdown`, `html`, or `both` (default: `both`)

**Source verification**:
- `--verify / --no-verify` — Verify cited sources against claims (default: on)
- `--verify-model TEXT` — Model for source verification (defaults to fast model)

**Debugging**:
- `-v, --verbose` — Verbose logging (DEBUG level)

#### `sat list-techniques`

**Options**:
- `-c, --category TEXT` — Filter by category: `diagnostic`, `contrarian`, `imaginative`

**Output**: Formatted table of all techniques with ID, name, category, and description

#### `sat report`

**Positional argument**:
- `output-dir` (required): Path to SAT output directory containing `manifest.json`

**Options**:
- `-f, --format TEXT` — Report format: `markdown`, `html`, `both` (default: `both`)

**Purpose**: Regenerate executive report from existing analysis output

---

## 6. Provider Configuration Details

### LLM Providers (in `src/sat/config.py`)

**ProviderConfig class**:
```python
class ProviderConfig(BaseModel):
    provider: str              # "anthropic", "openai", "gemini"
    model: str | None          # Model ID (resolved from env or default)
    api_key: str | None        # Optional explicit key
    max_tokens: int            # Default: 16384
    temperature: float         # Default: 0.3
    base_url: str | None       # Custom API endpoint
```

**Provider defaults**:
| Provider | Default Model | API Key Env |
|----------|---|---|
| anthropic | claude-opus-4-6 | ANTHROPIC_API_KEY |
| openai | o3 | OPENAI_API_KEY |
| gemini | gemini-2.5-pro | GEMINI_API_KEY |

**Adversarial auto-selection**:
- Primary provider chosen by CLI `--provider` flag (default: anthropic)
- Challenger provider auto-detected from available API keys
- Preference order per primary:
  - Primary=anthropic → prefer openai, fallback gemini, fallback self-critique
  - Primary=openai → prefer anthropic, fallback gemini, fallback self-critique
  - Primary=gemini → prefer anthropic, fallback openai, fallback self-critique
- Investigator (trident mode) is remaining provider with API key

### Research Providers (in `src/sat/research/registry.py`)

**Available backends**:

1. **Perplexity** (`openai_deep` client)
   - Model: `sonar-deep-research` (default)
   - API: OpenAI-compatible
   - API Key: `PERPLEXITY_API_KEY`
   - Features: Multi-step research with inline citations
   - Priority: 1 (auto-selected if available)

2. **Brave Search**
   - Endpoint: `https://api.search.brave.com/res/v1/web/search`
   - API Key: `BRAVE_API_KEY`
   - Features: Web search with snippets and URLs
   - Priority: 2 (auto-selected if Perplexity unavailable)

3. **OpenAI Deep Research** (`openai_deep`)
   - Model: `o3-deep-research-2025-06-26` (default), fallback `o4-mini-deep-research-2025-06-26`
   - API Key: `OPENAI_API_KEY` (same as LLM provider)
   - Features: OpenAI's native deep research capability

4. **Gemini Deep Research** (`gemini_deep`)
   - Model: `deep-research-pro-preview-12-2025` (default)
   - API Key: `GEMINI_API_KEY` (same as LLM provider)
   - Features: Google's native deep research capability

5. **LLM Fallback** (`llm`)
   - No external API needed
   - Uses primary LLM provider only
   - Auto-selected if no research provider has API key set

6. **Auto** (default `--research-provider auto`)
   - Tries Perplexity → Brave → LLM in order
   - Checks env vars to find available backends
   - Multi-mode (default): runs all available providers in parallel

---

## 7. Configuration File Support

### TOML Config Files (for `--config PATH`)

Used for multi-model setup. Example structure:
```toml
[adversarial]
enabled = true
rounds = 2
mode = "trident"

[adversarial.providers.primary]
provider = "anthropic"
model = "claude-opus-4-6"

[adversarial.providers.challenger]
provider = "openai"
model = "o3"

[adversarial.providers.investigator]
provider = "gemini"
model = "gemini-2.5-pro"

[adversarial.roles]
primary = "primary"
challenger = "challenger"
investigator = "investigator"
```

---

## 8. Configuration Classes (from `src/sat/config.py`)

### AnalysisConfig (main config)
- `question: str` — The analytic question
- `evidence: str | None` — Evidence text
- `techniques: list[str] | None` — Technique IDs to run
- `output_dir: Path` — Artifact output directory
- `provider: ProviderConfig` — Primary LLM config
- `research: ResearchConfig` — Deep research settings
- `preprocessing: PreprocessingConfig` — Evidence preprocessing
- `verbose: bool` — Debug logging
- `json_only: bool` — JSON-only output
- `adversarial: AdversarialConfig | None` — Adversarial settings
- `report: ReportConfig` — Report generation

### ResearchConfig
- `enabled: bool` — Enable deep research (default: False)
- `mode: str` — `single` or `multi` (default: multi)
- `provider: str` — Research backend (default: auto)
- `api_key: str | None` — Research provider API key
- `max_sources: int` — Max sources to retrieve (default: 10)
- `verification: VerificationConfig` — Source verification settings

### PreprocessingConfig
- `enabled: bool` — Enable preprocessing (default: True)
- `budget_fraction: float` — Context window fraction (default: 0.4)
- `max_chunk_tokens: int` — Max tokens per chunk (default: 50,000)
- `force_format: str | None` — Override auto-detection format

### AdversarialConfig
- `enabled: bool` — Enable adversarial (default: True)
- `rounds: int` — Critique rounds (default: 2)
- `providers: dict[str, ProviderRef]` — Named provider configs
- `roles: RoleAssignment | None` — Role-to-provider mapping
- `mode: str` — `dual` or `trident` (default: dual)

### VerificationConfig (source verification)
- `enabled: bool` — Enable verification (default: True)
- `model: str | None` — Override verification model
- `max_sources: int` — Max sources to verify (default: 20)
- `timeout: float` — Per-source fetch timeout (default: 15.0 seconds)
- `concurrency: int` — Max concurrent fetches (default: 5)

---

## 9. MCP Server Setup

### Entry point
```bash
sat-mcp  # Starts FastMCP server on stdio
```

### Configuration via environment
MCP server reads its configuration from environment variables (see "MCP Server Configuration" section above)

### MCP Tools exposed
1. `sat_list_techniques()` — List all 12 techniques
2. `sat_new_session(question, evidence, techniques)` — Create analysis session
3. `sat_next_prompt(session_id)` — Get next technique prompt
4. `sat_submit_result(session_id, result_json)` — Submit technique result
5. `sat_get_synthesis_prompt(session_id)` — Get synthesis prompt
6. `sat_submit_synthesis(session_id, synthesis_json)` — Submit final synthesis
7. `sat_research(query, provider, api_key, max_sources)` — Run deep research

### MCP Workflow
```
sat_list_techniques
sat_new_session(question, evidence, techniques)
  loop until complete:
    sat_next_prompt(session_id)
    [LLM executes prompt]
    sat_submit_result(session_id, result)
sat_get_synthesis_prompt(session_id)
[LLM executes synthesis]
sat_submit_synthesis(session_id, synthesis)
```

---

## Summary

The SAT project uses:
- **python-dotenv** for automatic `.env` loading
- **Pydantic v2** for configuration validation
- **Typer** for CLI with automatic help generation
- **FastMCP** for MCP server implementation
- **Environment variable precedence**: CLI > config file > env var > default

**All required environment variables are documented in `.env.example`**, and the application gracefully falls back to defaults or raises clear errors when required keys are missing.

The system supports 3 LLM providers (Anthropic, OpenAI, Gemini) and 6 research backends (Perplexity, Brave, OpenAI Deep Research, Gemini Deep Research, LLM fallback, auto-detection).
