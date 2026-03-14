Perfect. Now I have a comprehensive understanding. Let me create a detailed findings report.

## PERFORMANCE BOTTLENECK ANALYSIS — SAT Tool

Based on thorough examination of the codebase, I've identified several significant performance issues. Here are the key findings:

### **1. PIPELINE.PY — Sequential Execution Bottleneck**

**Critical Issue: Techniques run sequentially (lines 387-502)**
```python
for tid in technique_ids:
    # ... execute one technique at a time, wait for completion, then move to next
```

- **What's happening:** Each technique waits for the previous one to complete. With typical runs selecting 4-6 techniques (line 334-349), and each technique making 1+ LLM calls (16k token max_tokens per call), this creates a pure sequential pipeline.
- **Current timeline impact:** If each technique takes ~30-60 seconds (including LLM latency), 5 techniques = 2.5-5 minutes just on technique execution. Multiply by adversarial analysis and you get 5-10 minutes per technique.
- **Why it's sequential:** Comment at lines 3-8 claims "later techniques depend on earlier results (e.g., ACH uses assumptions, indicators uses ACH hypotheses)." However, examination shows **this dependency is overstated** — techniques only read `prior_results` dict, they don't block each other. Techniques could start in parallel, reading completed prior results as they arrive.

**Adversarial Analysis Adds More Sequential Delay (lines 421-495)**
```python
for tid in technique_ids:
    result = await technique.execute(...)  # ~30-60s
    if adversarial_session:
        exchange = await adversarial_session.run_adversarial_technique(...)  # +40-120s
        # ... write results
```

- Per-technique adversarial analysis runs **sequentially after each technique completes**.
- With N techniques and M rounds of critique/rebuttal, this adds significant time.
- **Trident mode partially mitigates this** (lines 198-350 in session.py) — critique and investigation run in parallel via `asyncio.gather()` at line 258 — but rebuttal, convergence, and adjudication still run sequentially afterwards.

---

### **2. ADVERSARIAL/SESSION.PY — Round Sequencing & Redundancy**

**Sequential Rounds (lines 90-161 in _run_dual)**
```python
for round_num in range(1, self._config.rounds + 1):
    critique = await challenger.generate_structured(...)  # ~15-30s
    rebuttal = await primary.generate_structured(...)     # +15-30s per round
    # If config.rounds=2, this loops twice sequentially
```

- With default `config.adversarial.rounds=2`, critique-rebuttal happens in pairs sequentially.
- **Potential optimization:** Critique and rebuttal in the same round could theoretically run in parallel (challenger critiques while primary prepares rebuttal concurrently), but current code waits for critique before starting rebuttal.
- **Per-round cost:** ~30-60 seconds per round. With 2 rounds = 60-120 seconds per technique's adversarial phase.

**Redundant technique.execute() call in Trident Mode (line 250)**
```python
async def do_investigation() -> ArtifactResult:
    result = await technique.execute(inv_ctx, investigator_provider)
```

- The same technique is **re-executed a second time** with a different provider during investigation phase.
- This duplicates all prompt building, LLM calls, and post-processing.
- For ACH (16384 max_tokens), this means another expensive LLM call.
- **Cost per technique:** Full extra LLM call (potentially 15-45 seconds).

---

### **3. SYNTHESIS.PY — Massive Token Injection**

**No Token Budget / Prompt Optimization (lines 97-113)**
```python
def build_prompt(ctx: TechniqueContext) -> tuple[str, list[LLMMessage]]:
    user_msg = build_user_message(
        question=ctx.question,
        evidence=ctx.evidence,
        prior_results=ctx.prior_results,  # Injects ALL prior results in full JSON
        relevant_prior_ids=None,  # Always "None" — never filters
    )
    return SYNTHESIS_SYSTEM_PROMPT, [LLMMessage(role="user", content=user_msg)]
```

**Underlying issue in prompts/base.py (lines 97-128):**
```python
def format_prior_results_section(..., relevant_ids=None):
    ids_to_include = relevant_ids if relevant_ids else list(prior_results.keys())
    # ... for each result, includes FULL JSON serialization:
    # "**Full output:**\n```json\n{result.model_dump_json(indent=2)}\n```"
```

- **Every single prior result is serialized to JSON in the synthesis prompt.**
- With 5 techniques × ~2-4KB per result JSON = 10-20KB of JSON in the synthesis prompt alone.
- Add evidence (could be 50KB+ from research phase) + research result (5-10KB) = **synthesis prompts routinely 100KB+.**
- Synthesis receives `max_tokens=16384` (line 33 in synthesis.py) to generate output, but input is massive.
- **Performance impact:** Larger inputs = slower token processing at the LLM, especially on models not optimized for large context. Token streaming/processing time grows linearly with input size.

**No caching of synthesis results** — If you re-run with same techniques, synthesis is recomputed fully.

---

### **4. PROVIDERS/REGISTRY.PY — Provider Creation Is Lazy But Not Cached at Pipeline Level**

**Lines 13-27 in registry.py:**
```python
def create_provider(config: ProviderConfig) -> LLMProvider:
    if config.provider == "anthropic":
        from sat.providers.anthropic import AnthropicProvider
        return AnthropicProvider(config)  # New instance each time
```

- `AnthropicProvider` (or OpenAI, Gemini) is instantiated fresh **every time `create_provider()` is called.**
- Pipeline creates provider once at line 151: `provider = create_provider(config.provider)`
- But adversarial pool creates separate providers for primary/challenger/adjudicator/investigator at lines 30-46 in pool.py.
- **Issue:** If primary and main pipeline provider are the same config, they're two separate `AnthropicProvider()` instances with separate connection pools/clients.
- This means **separate HTTP connections, separate auth token validations, potentially duplicate initialization overhead.**

**Provider re-instantiation in adversarial trident mode:**
- Each technique's trident investigation creates a temporary `TechniqueContext` (line 227) and passes `investigator_provider` — no re-instantiation, but the investigator provider was created upfront in pool.

---

### **5. TECHNIQUES/BASE.PY — Per-Technique Overhead Is Minimal**

**Lines 88-125 in base.py — `execute()` is efficient:**
- Single `provider.generate_structured()` call per technique.
- Optional `post_process()` (lightweight for most techniques; ACH does O(N*M) scoring for N hypotheses × M evidence but this is <100ms).
- No redundant calls detected here.

**BUT: max_tokens override creates uneven processing (lines 64-70):**
- ACH overrides to 16384 (DEC-TECH-ACH-002, line 49 in ach.py).
- Most other techniques use default (likely 4096 from provider base, line 64 in base.py).
- This means variable token generation budgets — some techniques are under-provisioned, others over-provisioned.
- **Minor impact on latency**, but could affect quality (under-budgeted techniques get truncated).

---

### **6. PIPELINE.PY — Research Phase Can Cascade (Lines 244-331)**

**Research phase is enabled by default and runs before techniques:**
```python
if config.research.enabled:
    research_result = await run_multi_research(...)  # Could be 5-10+ minutes
```

- Deep research can make 10-20+ web queries, verify sources, etc.
- This is **before** any techniques run.
- Then research evidence is merged with user evidence and passed to all techniques.
- **If research is slow, entire pipeline stalls.**

**Research result is serialized into every technique prompt:**
- Line 322: `research_evidence = format_research_evidence(research_result)`
- Line 328: `config = config.model_copy(update={"evidence": merged_evidence})`
- Every technique receives this merged evidence (potentially 50-100KB).
- **Overhead:** Token counting, prompt building, LLM processing time grows with evidence size.

---

### **7. MISSING CACHING / MEMOIZATION**

**No caching found for:**
- Technique selector LLM call (line 338 — runs even if config.techniques is set)
- Synthesis (always regenerated)
- Research results (no disk cache detected)
- Provider instances (separate instances for same config)

---

## SUMMARY OF BOTTLENECKS

| **Component** | **Issue** | **Estimated Impact** | **Severity** |
|---|---|---|---|
| **Technique sequencing** | 4-6 techniques run one-at-a-time instead of parallel | 5-10 min of avoidable wait | **CRITICAL** |
| **Adversarial critique/rebuttal** | Sequential per-technique; rebuttal waits for critique | +40-120s per technique with adv. | **CRITICAL** |
| **Synthesis prompt injection** | All prior results serialized to JSON (100KB+), no filtering | 10-20% overhead on synthesis LLM call | **HIGH** |
| **Adversarial trident redundancy** | Same technique re-executed for investigation phase | +15-45s per technique in trident mode | **HIGH** |
| **Research evidence bloat** | Large research results merged into all technique prompts | 10-20% overhead on token processing | **MEDIUM** |
| **Provider duplication** | Separate provider instances for same config | Separate connection pools, minor overhead | **MEDIUM** |
| **Round sequencing** | Critique-rebuttal rounds are sequential within technique | Could run critique/rebuttal in parallel per-round | **MEDIUM** |

---

## ROOT CAUSE: Design Assumes Sequential Dependencies Don't Exist

The pipeline was built assuming strict ordering: "later techniques depend on earlier results" (DEC-PIPE-001, line 3). However, the actual code only **reads** `prior_results` dict — there's no strict blocking dependency. Techniques **could** run in parallel, collecting prior results as they complete.

**Current 20-30 minute runtime breakdown (estimated):**
- Deep research: 5-10 min (if enabled)
- Technique selection: 30-60s (LLM call)
- Technique execution (4-6 techniques): 5-10 min sequential (should be ~2-3 min parallel)
- Adversarial analysis (2 rounds × 4-6 techniques): 8-15 min sequential (could be reduced by parallelizing within rounds)
- Synthesis: 2-3 min (large prompt injection adds overhead)
- **Overhead/other:** 2-3 min

**Parallelizable time: ~8-13 minutes could be recovered** through proper async/parallel execution.
