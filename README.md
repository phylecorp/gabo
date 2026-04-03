# Gabo — Structured Analysis for Any Question

> **Built at the [Nebula:Fog hackathon](https://nebulafog.ai).** Thanks to the organizers for creating the space where this tool was prototyped and first released. We're grateful. It's still in production, but we will keep working at it!

---

## What Does This Do?

Gabo helps you think through hard questions more carefully.

When you face a decision with real consequences — whether to enter a new market, how a geopolitical situation might unfold, whether a deal is sound, what an adversary is likely to do — your instinct is usually to form a view and then look for information that supports it. That's human nature, but it's also how smart people end up confidently wrong.

**Structured analytic techniques** are a set of methods originally developed for the U.S. Intelligence Community to counteract exactly this problem. They force you to slow down and do the things that feel unnatural but produce better answers: spell out the assumptions you're relying on, seriously consider the possibility that you're wrong, weigh evidence for and against competing explanations, and think through what the world looks like if something unexpected happens.

These aren't academic exercises. The CIA's *Tradecraft Primer* codified 12 of these techniques because intelligence failures kept tracing back to the same handful of cognitive traps — anchoring, confirmation bias, mirror-imaging, groupthink. The techniques are designed to make those traps visible before the assessment goes out the door.

Gabo automates all 12. You give it a question and, optionally, evidence. It selects the right techniques, runs them in sequence (each one building on what came before), optionally has a second AI model challenge every output, and then synthesizes everything into a bottom-line assessment with supporting analysis. The result is a structured, defensible analytical product — not a chatbot's first-pass opinion.

### The 12 Techniques

Gabo implements all three categories from the Tradecraft Primer:

**Diagnostic techniques** test your reasoning against the evidence. *Key Assumptions Check* surfaces the beliefs you're taking for granted. *Analysis of Competing Hypotheses* arrays evidence against multiple explanations to find the one that best survives scrutiny. *Quality of Information Check* evaluates whether your sources are actually telling you what you think they're telling you. *Indicators and Signposts* sets up a monitoring framework so you'll know which future is emerging.

**Contrarian techniques** challenge the dominant view. *Devil's Advocacy* builds the strongest possible case against the prevailing assessment. *Team A/Team B* develops two competing arguments and puts them head to head. *High-Impact/Low-Probability Analysis* takes the events everyone dismisses as unlikely and maps out how they could actually happen. *What If?* assumes an event has already occurred and works backward to explain how.

**Imaginative techniques** explore alternatives. *Brainstorming* generates a wide range of hypotheses through divergent thinking. *Outside-In Thinking* identifies external forces (social, technological, economic, environmental, political) that could reshape the issue. *Red Team Analysis* puts you in the adversary's shoes. *Alternative Futures* builds a 2×2 scenario matrix to develop multiple plausible futures.

### What Makes This Different from Just Asking an LLM?

When you ask a language model a question, you get one perspective shaped by whatever patterns the model learned. Gabo does something fundamentally different:

It runs **multiple analytical frameworks** over the same question, each designed to surface different things. Assumptions Check might reveal that your whole question rests on a premise that doesn't hold. ACH might show that a hypothesis you hadn't considered actually fits the evidence better. Red Team might expose a vulnerability you missed.

It uses **adversarial critique** — a second AI model acts as a peer reviewer, poking holes in each technique's output, and the primary model has to defend or revise its work. This catches blind spots and lazy reasoning that a single model would never flag in its own output.

And it can **gather its own evidence** through deep research before analysis begins, using multiple research backends in parallel.

### What Kinds of Questions Is This Good For?

Structured analytic techniques were designed for a specific class of problem: questions where the stakes are high, the information is incomplete or ambiguous, and reasonable people could disagree about the answer. They shine when you need to make a judgment call under uncertainty and you want that judgment to be as rigorous as possible.

**Gabo is a good fit when you're asking things like:**

- "Will this ceasefire hold?" — Geopolitical and security assessments where you need to weigh competing signals, consider adversary intentions, and track indicators over time.
- "Should we enter this market?" — Strategic business decisions where confirmation bias is a real risk and you need to stress-test your assumptions before committing resources.
- "What are the most likely ways this could go wrong?" — Risk analysis for projects, operations, or investments where you need to systematically explore failure modes rather than just hoping for the best.
- "What is this actor likely to do next?" — Competitive intelligence or adversary analysis where red-teaming and alternative perspectives are more valuable than a single prediction.
- "How should we interpret this conflicting evidence?" — Any situation where you have multiple sources telling you different things and need a disciplined framework for weighing them.

More generally, if you find yourself in a situation where the cost of being wrong is high and you suspect your own biases might be leading you toward a comfortable answer, these techniques are built for exactly that moment.

**Gabo is not the right tool when:**

- You need a factual lookup. If the answer is a known quantity — a date, a definition, a statute — just search for it. Structured analysis adds nothing to questions with clear, verifiable answers.
- You're doing routine summarization. If you need a document condensed or translated, a general-purpose LLM will do that faster and cheaper.
- The question is purely technical. "How do I configure Nginx to reverse proxy?" isn't an analytical judgment call — it's a knowledge retrieval problem.
- You need real-time monitoring. Gabo produces point-in-time assessments. It's not a dashboard or an alerting system (though its Indicators technique can help you design a monitoring framework).
- Speed matters more than rigor. A full 12-technique run with adversarial critique takes time and API calls. If you need a quick directional answer in 30 seconds, ask a chatbot. If you need a defensible assessment you can brief to a decision-maker, run Gabo.

---

## Licensing

Gabo is **free for personal use** — students, researchers, independent analysts, anyone working on their own questions.

If your company or organization wants to use Gabo commercially, we'd like you to **reach out first** so we can discuss terms and understand what you're trying to do. Contact us.

---

## The Desktop App

The primary way to use Gabo is through the desktop application. It gives you a visual workspace for configuring, running, and reviewing structured analyses without touching a terminal.

### Starting a new analysis

From the dashboard, click **New Analysis**. The form walks you through everything top to bottom:

1. **Name your analysis** (optional) — a short label for your own reference.
2. **Write your question** — the intelligence question you want analyzed. This is the only required field.
3. **Provide evidence** (optional) — paste reports, source material, or intelligence directly into the text area. You can also attach source documents (PDF, DOCX, HTML, images, URLs) and Gabo will ingest them automatically.
4. **Select techniques** — pick specific techniques from the 12 available, or leave it blank and Gabo will auto-select based on your question.
5. **Choose a provider** — select which LLM provider to use (Anthropic, OpenAI, or Gemini). Gabo shows which providers have valid API keys configured.
6. **Set advanced options** — toggle web research (automatic evidence gathering from external sources), adversarial review (a second model critiques each technique output), and report generation.

You have two ways to launch:

- **Run Analysis** sends your question straight through the full pipeline: evidence preprocessing, technique execution, adversarial critique, and synthesis.
- **Gather & Review Evidence** first collects and structures evidence from your inputs and research providers, then lets you curate what gets included before running the analysis. This is useful when you want to inspect and filter the evidence base before committing to a full run.

### Watching a run in progress

After you launch, the app navigates to a live progress view. You can watch each stage of the pipeline as it executes — evidence gathering, individual techniques, adversarial critique rounds, and synthesis. A real-time event log shows what's happening under the hood.

### Reviewing results

When the run completes, the results view shows the synthesis (bottom-line assessment with key judgments and confidence levels) alongside expandable findings from each technique. Every artifact — the markdown reports, the structured JSON, the critique-rebuttal exchanges — is available for inspection.

### Reading the report

Click through to the **Report View** for a formatted intelligence report rendered from the run's artifacts. You can print it, download the HTML, or export the full run as a ZIP archive containing every artifact and the manifest.

### Managing past runs

The dashboard shows your recent analyses with status indicators, timestamps, and provider info. You can rename runs, delete them, or click into any completed run to review its results.

---

## Getting Started

### Requirements

- Python 3.11+
- Node.js 18+ (for the desktop app)
- At least one LLM provider API key (Anthropic recommended)

 **Option A — From source (development)**

  ```bash
  cd desktop
  npm install
  bash dev.sh
  ```

  dev.sh creates a Python venv, installs dependencies, starts the API server,
  and launches Electron with hot reload. Requires Python 3.11+ and Node 18+.

**Option B — Build a distributable installer

  # 1. Build the Python sidecar (must run on the target platform)
  python3 scripts/build-sidecar.py

  # 2. Build the installer
  cd desktop
  npm install
  npm run dist:mac    # → dist/Gabo-x.x.x.dmg
  # or
  npm run dist:win    # → dist/Gabo-Setup-x.x.x.exe

  The sidecar is a PyInstaller bundle of the FastAPI backend — the Electron app
  launches it as a subprocess, so end users don't need Python installed.
  
### Install the Python backend

```bash
python3 -m venv venv
source venv/bin/activate

pip install -e ".[all]"   # all LLM providers
```

Or use the Makefile:

```bash
make install
```

### Configure API keys

You can use the "settings" button in the application to add API keys. Or, if you'd rather:

```bash
cp .env.example .env
```

Edit `.env` and add your API keys. At minimum, set one provider key (e.g., `ANTHROPIC_API_KEY`). Gabo loads `.env` automatically.

For cross-model adversarial critique, set keys for two or more providers. For deep research, add a `PERPLEXITY_API_KEY` or `BRAVE_API_KEY`.

### Run the desktop app

```bash
cd desktop
npm install
npm run dev
```

This starts the Electron app in development mode. The app launches a local API server (`sat-api`) that the frontend talks to over HTTP and WebSocket.

---

## What's Next

Recent releases shipped Trident adversarial mode (three-model debate), LLM-generated intelligence reports, universal evidence persistence, and security hardening across the stack. Coming up:

- Packaged desktop installers (macOS, Windows, Linux)
- Dynamic model selection across all pipeline stages

---

## Command Line

Everything the desktop app does is also available from the terminal via the `sat` CLI.

### Basic analysis

```bash
sat analyze "Will the ceasefire hold?"
```

Gabo auto-selects techniques, runs adversarial critique, and writes results to a `sat-<run-id>/` directory.

### Choosing specific techniques

```bash
sat analyze "Will the ceasefire hold?" -t assumptions,ach,devils_advocacy
```

### Providing evidence

```bash
# Inline
sat analyze "Will the ceasefire hold?" -e "Reports indicate both sides withdrew heavy weapons..."

# From files
sat analyze "Will the ceasefire hold?" -f ./reports/
```

### Deep research

```bash
sat analyze "Will the ceasefire hold?" --research
```

### Adversarial critique options

```bash
# Force a specific challenger provider
sat analyze "Question" --challenger-provider openai

# More rounds of critique-rebuttal (default: 2)
sat analyze "Question" --rounds 4

# Disable adversarial for speed
sat analyze "Question" --no-adversarial
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

### Output

Each run writes numbered artifacts to `sat-{run_id}/`:

```
sat-a1b2c3d4/
├── 01-quality.md
├── 01-quality.json
├── 02-quality-critique.md
├── 02-quality-critique.json
├── 03-quality-rebuttal.md
├── ...
├── NN-synthesis.md
├── NN-synthesis.json
└── manifest.json
```

`.md` files are human-readable reports. `.json` files are Pydantic-validated and suitable for programmatic use. `manifest.json` records the full run configuration for reproducibility.

---

## MCP Server

Gabo ships an MCP server that exposes its pipeline as tools for LLM agents and Claude Desktop. This lets an AI assistant conduct structured analysis as part of a larger workflow. We've run no tests of this yet...

```bash
sat-mcp
```

### Tools

| Tool | Description |
|------|-------------|
| `sat_list_techniques` | List all 12 techniques with metadata |
| `sat_new_session` | Create analysis session |
| `sat_next_prompt` | Get the next technique's prompt and output schema |
| `sat_submit_result` | Submit technique result; runs adversarial critique |
| `sat_get_synthesis_prompt` | Get synthesis prompt after all techniques complete |
| `sat_submit_synthesis` | Submit synthesis; writes artifacts to disk |
| `sat_research` | Run deep research to gather evidence |

### MCP workflow

```
sat_new_session  →  sat_next_prompt  →  [LLM runs prompt]  →  sat_submit_result
                         ↑                                           |
                         └───────────── loop until complete ─────────┘
                    sat_get_synthesis_prompt  →  [LLM runs synthesis]  →  sat_submit_synthesis
```

Environment variables for MCP configuration are documented in `.env.example`.

---

## How It Works

1. **Evidence preprocessing** — Incoming evidence is format-detected and token-budgeted to fit the model's context window.
2. **Deep research** (optional) — If enabled, Gabo queries research providers to gather evidence before analysis.
3. **Technique selection** — Specified techniques run in order; if none specified, Gabo auto-selects based on the question.
4. **Sequential execution** — Each technique runs in turn, receiving the question, evidence, and all prior technique outputs as context.
5. **Adversarial critique** — A challenger model reviews each output, raises structured objections, and the primary model rebuts. This repeats for N rounds.
6. **Synthesis** — All technique results are synthesized into a bottom-line assessment with key judgments and confidence levels.
7. **Artifacts** — Markdown and JSON artifacts are written to the output directory.

---

## Providers

### LLM providers

| Provider | API Key Variable | Default Model |
|----------|-----------------|---------------|
| `anthropic` (default) | `ANTHROPIC_API_KEY` | `claude-opus-4-6` |
| `openai` | `OPENAI_API_KEY` | `o3` |
| `gemini` | `GEMINI_API_KEY` | `gemini-2.5-pro` |
| `copilot` | (none required) | `copilot-gpt-4` |

### Research providers

| Provider | API Key Variable | Notes |
|----------|-----------------|-------|
| `perplexity` | `PERPLEXITY_API_KEY` | Multi-step research with citations |
| `brave` | `BRAVE_API_KEY` | Web search |
| `openai_deep` | `OPENAI_API_KEY` | OpenAI deep research |
| `gemini_deep` | `GEMINI_API_KEY` | Gemini deep research |
| `llm` | — | Uses primary LLM (no extra key needed) |
| `auto` | — | Auto-selects: perplexity → brave → llm |

In `multi` mode (default), all available research providers run in parallel.

---

## Development

```bash
pip install -e ".[dev]"
make test     # pytest
make lint     # ruff check
make format   # ruff format
```

---

*Built by [Phyle](https://phyle.io).*
