# SAT — Structured Analytic Techniques

Apply CIA Tradecraft Primer intelligence analysis methods to any question, powered by LLMs.

## What Is This?

SAT automates the 12 structured analytic techniques from the CIA's *Tradecraft Primer* — a declassified methodology used by intelligence analysts to reduce cognitive bias and improve analytical rigor. These techniques were designed to force analysts to challenge assumptions, consider alternatives, and weigh evidence systematically.

Given a question (and optionally evidence), SAT runs selected techniques sequentially — each building on prior results — then synthesizes findings into a bottom-line assessment with supporting analysis. The result is a structured, defensible analysis rather than a single model's first-pass opinion.

Techniques are grouped into three categories: **Diagnostic** (test hypotheses against evidence), **Contrarian** (challenge consensus thinking), and **Imaginative** (explore alternatives and futures). SAT includes optional adversarial multi-model critique where a challenger model reviews and rebuts each technique's output, and it can gather its own evidence via deep research before analysis begins. It works as a CLI tool, Python library, or MCP server for agent workflows.

## Getting Started

### 1. Create a virtual environment

SAT requires Python 3.11+. Use a virtual environment to keep dependencies isolated:

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
```

### 2. Install

```bash
pip install -e ".[all]"   # all LLM providers (recommended)
```

See [Installation](#installation) below for other variants.

### 3. Configure API keys

```bash
cp .env.example .env
```

Edit `.env` and add your API keys. At minimum, set one provider key (e.g., `ANTHROPIC_API_KEY`). SAT loads `.env` automatically on startup — no need to `export` anything.

For cross-model adversarial critique (where a different LLM challenges each analysis), set keys for two or more providers. If only one key is configured, SAT falls back to self-critique using the same model.

For deep research (`--research`), add a `PERPLEXITY_API_KEY` or `BRAVE_API_KEY`. Without these, research falls back to the primary LLM.

### 4. Run your first analysis

```bash
sat analyze "Will the ceasefire hold?"
```

SAT will auto-select techniques, run adversarial critique, and write results to a `sat-<run-id>/` directory.

### 5. Verify provider detection (optional)

```bash
sat analyze "Test question" --verbose 2>&1 | head -30
```

Check the log output to confirm which providers are active for primary, challenger, and research roles.

## Installation

Requires Python 3.11+.

```bash
# Anthropic only (includes MCP server)
pip install -e .

# All providers (adds OpenAI, Google Gemini)
pip install -e ".[all]"

# Development (adds pytest, ruff, mypy)
pip install -e ".[dev]"
```

Or use the Makefile:

```bash
make install   # creates venv and installs
```

## Usage

### Basic analysis

```bash
sat analyze "Will the ceasefire hold?"
```

When no `-t` flag is given, SAT auto-selects techniques based on the question.

### Choosing techniques

```bash
sat analyze "Will the ceasefire hold?" -t assumptions,ach,devils_advocacy
```

### Evidence from text or file

```bash
# Inline evidence
sat analyze "Will the ceasefire hold?" -e "Reports indicate both sides withdrew heavy weapons..."

# From a file or directory
sat analyze "Will the ceasefire hold?" -f ./reports/
```

### Deep research (gather evidence automatically)

```bash
sat analyze "Will the ceasefire hold?" --research
```

### Cross-model adversarial critique

```bash
# Default: auto-selects a different provider as challenger if available,
# otherwise falls back to self-critique (same model challenges its own output)
sat analyze "Will the ceasefire hold?" -e "Evidence..."

# Explicit cross-model: force a specific challenger provider
sat analyze "Will the ceasefire hold?" -e "Evidence..." --challenger-provider openai

# More critique-rebuttal rounds (default: 2)
sat analyze "Will the ceasefire hold?" -e "Evidence..." --rounds 4

# Disable adversarial entirely
sat analyze "Will the ceasefire hold?" -e "Evidence..." --no-adversarial
```

### List available techniques

```bash
sat list-techniques
```

### All CLI flags

| Flag | Short | Description |
|------|-------|-------------|
| `--evidence` | `-e` | Evidence text |
| `--evidence-file` | `-f` | File or directory of evidence |
| `--techniques` | `-t` | Comma-separated technique IDs |
| `--output-dir` | `-o` | Output directory |
| `--provider` | `-p` | LLM provider (default: anthropic) |
| `--model` | `-m` | Model identifier |
| `--api-key` | | API key (or set env var) |
| `--research` / `--no-research` | `-r` | Deep research to gather evidence |
| `--research-provider` | | `perplexity`, `brave`, `openai_deep`, `gemini_deep`, `llm`, `auto` |
| `--research-api-key` | | API key for research provider |
| `--research-mode` | | `single` or `multi` (default: multi) |
| `--preprocess` / `--no-preprocess` | | Evidence preprocessing (default: on) |
| `--evidence-budget` | | Fraction of context window (0.0–1.0) |
| `--adversarial` / `--no-adversarial` | | Adversarial critique (default: on) |
| `--challenger-provider` | | Challenger LLM provider |
| `--challenger-model` | | Challenger model |
| `--rounds` | | Critique-rebuttal rounds (default: 2) |
| `--config` | `-c` | TOML config file |
| `--verbose` | `-v` | Verbose output |

## Techniques

### Diagnostic — test hypotheses against evidence

| ID | Name | Description |
|----|------|-------------|
| `quality` | Quality of Information Check | Evaluate the accuracy, completeness, and reliability of information sources |
| `assumptions` | Key Assumptions Check | Identify and challenge key working assumptions underlying the analytic line |
| `ach` | Analysis of Competing Hypotheses | Array evidence against multiple hypotheses to find the best explanation |
| `indicators` | Indicators/Signposts of Change | Track observable events or trends to monitor which future is emerging |

### Contrarian — challenge consensus thinking

| ID | Name | Description |
|----|------|-------------|
| `devils_advocacy` | Devil's Advocacy | Challenge a dominant view by building the best case against it |
| `team_ab` | Team A/Team B | Develop two competing cases for rival hypotheses and assess which is stronger |
| `high_impact` | High-Impact/Low-Probability Analysis | Explore unlikely but consequential events by developing plausible pathways |
| `what_if` | 'What If?' Analysis | Assume an event has occurred and work backward to explain how it came about |

### Imaginative — explore alternatives and futures

| ID | Name | Description |
|----|------|-------------|
| `brainstorming` | Brainstorming | Generate a wide range of ideas and hypotheses through divergent thinking |
| `outside_in` | Outside-In Thinking | Identify external STEEP forces that could shape the issue |
| `red_team` | Red Team Analysis | Think like the adversary to understand their likely actions |
| `alt_futures` | Alternative Futures Analysis | Develop multiple plausible futures using a 2x2 scenario matrix |

## How It Works

1. **Evidence preprocessing** — Incoming evidence is format-detected and token-budgeted to fit the model's context window
2. **Deep research** (optional, when no evidence provided) — SAT queries research providers to gather evidence before analysis
3. **Technique selection** — Specified techniques run in order; if none specified, SAT auto-selects based on the question
4. **Sequential execution** — Each technique runs in turn, receiving the question, evidence, and prior technique outputs as context
5. **Adversarial critique** — A challenger model reviews each output, raises objections, and the primary model rebuts; this repeats for N rounds
6. **Synthesis** — All technique results are synthesized into a bottom-line assessment with key judgments and confidence levels
7. **Artifacts** — Markdown and JSON artifacts are written to the output directory

## Output

Each run writes numbered artifacts to `sat-{run_id}/` inside the output directory:

```
sat-a1b2c3d4/
├── 01-quality.md
├── 01-quality.json
├── 02-quality-critique.md
├── 02-quality-critique.json
├── 03-quality-rebuttal.md
├── 03-quality-rebuttal.json
├── 04-assumptions.md
├── 04-assumptions.json
├── ...
├── NN-synthesis.md
├── NN-synthesis.json
└── manifest.json
```

`.md` files are human-readable reports. `.json` files round-trip through Pydantic models and are suitable for programmatic consumption. `manifest.json` records the full run configuration (question, techniques selected, providers used, timestamps) for reproducibility.

## Adversarial Critique

After each technique executes, a challenger model acts as a peer reviewer: it reads the output, identifies weaknesses, logical gaps, or unsupported claims, and returns structured objections. The primary model then rebuts each objection. This cycle repeats for the configured number of rounds (default: 2).

The purpose is to reduce confirmation bias and force the analysis to survive challenge before it reaches synthesis. A single model's output often has blind spots that become visible only when a skeptical reviewer is applied — adversarial critique operationalizes this within a single run.

By default, adversarial critique is enabled. SAT auto-selects a different provider as the challenger if multiple API keys are configured (preference order: Anthropic, OpenAI, Gemini); if only one provider is available, it falls back to self-critique. Use `--challenger-provider` to explicitly choose a challenger, `--no-adversarial` to skip entirely for speed, or `--rounds N` to control depth.

## MCP Server

SAT ships an MCP server (`sat-mcp`) that exposes its pipeline as tools for LLM agents and Claude Desktop. This enables an AI assistant to conduct structured analysis as part of a larger workflow — for example, gathering evidence with research tools, then handing off to SAT for systematic technique execution.

### Running the server

```bash
sat-mcp
```

Configure via environment variables (see below). The server speaks the MCP stdio protocol and is compatible with Claude Desktop and any MCP-compliant client.

### Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SAT_OUTPUT_DIR` | Artifact output directory | `"."` |
| `SAT_PRIMARY_PROVIDER` | Primary LLM provider | `"anthropic"` |
| `SAT_PRIMARY_MODEL` | Primary model override | provider default |
| `SAT_PRIMARY_API_KEY` | Primary API key (falls back to provider env var) | — |
| `SAT_ADVERSARIAL_ENABLED` | Enable adversarial (`true`/`1`/`yes`) | disabled |
| `SAT_CHALLENGER_PROVIDER` | Challenger provider | `"anthropic"` |
| `SAT_CHALLENGER_MODEL` | Challenger model override | provider default |
| `SAT_CHALLENGER_API_KEY` | Challenger API key (falls back to provider env var) | — |

### Tools

| Tool | Description |
|------|-------------|
| `sat_list_techniques` | List all 12 techniques with metadata |
| `sat_new_session` | Create analysis session (question, evidence, techniques) |
| `sat_next_prompt` | Get the next technique's prompt and output schema |
| `sat_submit_result` | Submit technique result; validates, post-processes, runs adversarial critique |
| `sat_get_synthesis_prompt` | Get synthesis prompt after all techniques complete |
| `sat_submit_synthesis` | Submit synthesis; writes all artifacts to disk |
| `sat_research` | Run deep research to gather evidence |

### Workflow

```
sat_list_techniques          (optional — discover available techniques)
sat_new_session              (create session: question, evidence, technique list)
  loop until complete:
    sat_next_prompt          (get prompt + schema for next technique)
    [LLM executes prompt]
    sat_submit_result        (submit result; adversarial critique runs here)
sat_get_synthesis_prompt     (get synthesis prompt with all technique results)
[LLM executes synthesis]
sat_submit_synthesis         (submit; artifacts written to SAT_OUTPUT_DIR)
```

## Providers

### LLM providers

| Provider | API Key Variable | Default Model |
|----------|-----------------|---------------|
| `anthropic` (default) | `ANTHROPIC_API_KEY` | `claude-opus-4-6` |
| `openai` | `OPENAI_API_KEY` | `o3` |
| `gemini` | `GEMINI_API_KEY` | `gemini-2.5-pro` |

Override the model per-provider with environment variables (`ANTHROPIC_MODEL`, `OPENAI_MODEL`, `GEMINI_MODEL`) or with the `--model` / `--challenger-model` CLI flags.

### Research providers

| Provider | API Key Variable | Notes |
|----------|-----------------|-------|
| `openai_deep` | `OPENAI_API_KEY` | OpenAI deep research |
| `gemini_deep` | `GEMINI_API_KEY` | Gemini deep research |
| `perplexity` | `PERPLEXITY_API_KEY` | Multi-step research with citations |
| `brave` | `BRAVE_API_KEY` | Web search fallback |
| `llm` | — | Uses primary LLM only (no external API needed) |
| `auto` | — | Auto-selects: perplexity → brave → llm |

In `multi` mode (default), SAT discovers all available research providers and runs them in parallel to gather broader evidence before analysis.

## Development

```bash
pip install -e ".[dev]"
make test     # pytest
make lint     # ruff check
make format   # ruff format
```
