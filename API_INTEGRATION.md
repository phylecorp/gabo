# SAT API Integration Guide

This document describes how an external service can drive the SAT analysis pipeline over HTTP and WebSocket. It is written for engineers integrating SAT into another product, automation, or pipeline — not for desktop users.

The API is implemented in `src/sat/api/`. Authoritative request/response shapes live in `src/sat/api/models.py`; route handlers live in `src/sat/api/routes/`. When this document and the code diverge, the code wins.

---

## 1. Deployment model and important caveats

SAT was designed as a **localhost sidecar** for the Electron desktop app. Before integrating from another service, understand what that means:

- **Single shared-secret auth.** A 32-byte hex token is generated at process start and printed to stdout as `SAT_AUTH_TOKEN=<token>`. There is no user model, no session store, no token rotation. (`src/sat/api/auth.py`, DEC-AUTH-001.)
- **Localhost-only CORS.** The CORS middleware allows only `http://localhost:*` and `http://127.0.0.1:*`. Browser clients on other origins will be blocked by the browser. Server-to-server clients are unaffected. (`src/sat/api/app.py`, DEC-SEC-002.)
- **Process-lifetime state.** Run state is held in-memory by `RunManager`; restarting the process loses queued/running runs. Completed run artifacts persist on disk under the configured runs directory.
- **No multi-tenancy.** Anyone holding the token gets full access to every run, every artifact, and the settings endpoints (which include API keys for upstream providers).

**If you plan to expose the API beyond a trusted host:** put it behind a reverse proxy that adds TLS, network-level access control, and rate limits. Treat the auth token as an internal credential.

### Starting the server for non-desktop use

```bash
sat-api --port 8742
# or
python -m sat.api.main --port 8742
```

On startup, the process prints (to stdout):

```
SAT_API_PORT=8742
SAT_AUTH_TOKEN=<64 hex chars>
```

Capture both. Every authenticated call needs the token.

For tests or trusted environments where you want to skip token checks entirely, set `SAT_DISABLE_AUTH=1`. **Do not do this in any environment reachable from outside the host.**

---

## 2. Authentication

### HTTP

Send `Authorization: Bearer <token>` on every request except `GET /api/health`.

```bash
curl -H "Authorization: Bearer $SAT_AUTH_TOKEN" \
     http://localhost:8742/api/techniques
```

A missing, malformed, or wrong token yields `401 Unauthorized`.

### WebSocket

WebSocket upgrades cannot carry custom headers from browsers, so the token is passed as a query parameter:

```
ws://localhost:8742/ws/analysis/<run_id>?token=<token>
```

An invalid token closes the socket with code `4001`. A missing run/session closes with code `4004`.

---

## 3. The two ways to drive an analysis

There are two top-level entry points. Pick one based on what you need:

| Goal | Endpoint | When to use |
|------|----------|-------------|
| Free-form analysis with optional techniques | `POST /api/analysis` | You want SAT's general-purpose pipeline against a question. |
| Template-driven deliverable (threat assessment, brief, BDA, etc.) | `POST /api/task` | You want a structured preset deliverable — the task type drives technique selection and report shape. |

Both return an `AnalysisResponse`:

```json
{
  "run_id": "01HXY...",
  "ws_url": "ws://localhost:8742/ws/analysis/01HXY...",
  "queue_position": null
}
```

`queue_position` is non-null when the run was queued behind the concurrency limit (default 2 concurrent runs). Connect to `ws_url` to watch progress.

### 3a. Free-form analysis

```http
POST /api/analysis
Content-Type: application/json
Authorization: Bearer <token>

{
  "question": "Will the ceasefire hold through Q3?",
  "evidence": "Optional inline evidence text...",
  "evidence_sources": ["./briefing.pdf", "https://example.com/report"],
  "techniques": null,
  "provider": "anthropic",
  "model": null,
  "research_enabled": true,
  "research_mode": "multi",
  "adversarial_enabled": true,
  "adversarial_mode": "dual",
  "adversarial_rounds": 1,
  "report_enabled": true,
  "report_format": "both",
  "gap_resolution_enabled": true
}
```

Field constraints (enforced by Pydantic in `api/models.py`):

- `question`: ≤ 50,000 chars
- `evidence`: ≤ 500,000 chars
- `evidence_sources`: ≤ 100 items (paths or URLs)
- `techniques`: ≤ 20 ids; call `GET /api/techniques` to discover valid ids

### 3b. Template-driven (task mode)

```bash
curl -H "Authorization: Bearer $SAT_AUTH_TOKEN" \
     http://localhost:8742/api/task/types
```

Returns the available preset deliverable types. As of writing: `threat`, `brief`, `bda`, `annex_b`, `annex_l`. Each preset declares its own `default_techniques` and section structure.

```http
POST /api/task
Content-Type: application/json

{
  "task_type": "brief",
  "question": "Assess implications of the new export controls.",
  "evidence": "Optional inline text...",
  "research": true,
  "provider": "anthropic",
  "model": null
}
```

The task pipeline picks the preset's techniques and emits a deliverable shaped to that preset.

---

## 4. WebSocket events

Connect to the full `ws_url` returned by the POST response, with `?token=<token>` appended, immediately after `POST /api/analysis` (or `/api/task`). The URL is fully qualified (`ws://<host>:<port>/ws/analysis/{run_id}`) — do not prepend a base. The server **replays buffered events** before going live, so a small delay between POST and WS open does not lose events. (DEC-API-003.)

Each frame is JSON:

```json
{
  "type": "StageStarted",
  "data": { "stage": "analysis", "technique_id": "ach", "detail": "" },
  "timestamp": "2026-04-28T16:22:41.013Z"
}
```

Event `type` values come from the dataclasses in `src/sat/events.py`. The current set:

| Type | When emitted | Key fields |
|------|--------------|-----------|
| `ResearchStarted` | research phase begins | `provider_names`, `query` |
| `ProviderStarted` / `ProviderCompleted` / `ProviderFailed` | per-research-provider lifecycle | `name`, `citation_count`, `content_length`, `error`, `transient` |
| `ProviderPolling` | liveness during long polls (deep research can run 20+ min) | `name`, `attempt`, `max_attempts`, `status` |
| `ResearchCompleted` | research finished | `source_count`, `claim_count`, `provider_label` |
| `StageStarted` / `StageCompleted` | technique, adversarial step, synthesis | `stage`, `technique_id`, `detail`, `duration_secs` |
| `ArtifactWritten` | a file landed on disk | `path`, `technique_id`, `category` |
| `EvidenceGatheringStarted` | for `/ws/evidence/{session_id}` start | `session_id`, `has_evidence`, `research_enabled`, `decomposition_enabled` |
| `EvidenceGatheringCompleted` | for `/ws/evidence/{session_id}` end | `session_id`, `item_count`, `source_count`, `gap_count` |

The pipeline is **server → client only**. Anything you `send` is silently ignored; the connection is held open for streaming. Disconnects are clean — late-joiners can reconnect and receive the replay.

A run is terminal when its status (via `GET /api/runs/{run_id}`) reads `completed`, `failed`, or `cancelled`.

---

## 5. Run management

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/runs` | List all runs (summary view) |
| `GET` | `/api/runs/{id}` | Full detail including inlined synthesis JSON and per-technique summaries |
| `PATCH` | `/api/runs/{id}` | Rename a run (`{ "name": "..." }`) |
| `DELETE` | `/api/runs/{id}` | Delete a run and its artifacts |
| `POST` | `/api/runs/{id}/cancel` | Cancel an in-progress run |
| `GET` | `/api/runs/{id}/report` | Get the executive report (HTML or Markdown) |
| `POST` | `/api/runs/{id}/report/generate` | Re-run report generation (e.g., after editing the template) |
| `GET` | `/api/runs/{id}/artifact?path=<rel>` | Fetch a single artifact by relative path |
| `GET` | `/api/runs/{id}/artifact/download?path=<rel>` | Same, with `Content-Disposition: attachment` |
| `GET` | `/api/runs/{id}/evidence` | The evidence pool used by the run |
| `GET` | `/api/runs/{id}/export` | ZIP bundle of the entire run directory |
| `GET` | `/api/concurrency` | `{ running, queued, max_concurrent }` |

`RunSummary.status` is one of `queued`, `running`, `completed`, `failed`, `cancelled`. For completed runs, `RunDetail.synthesis_content` and `RunDetail.technique_summaries` are inlined so you don't need N+1 artifact fetches to render the result.

---

## 6. Evidence sessions (optional, decoupled flow)

Evidence gathering can run independently of analysis, then feed a curated subset into a run. Use this when you want a human-in-the-loop curation step.

```
POST /api/evidence/gather              → start async research → returns { session_id, ws_url }
GET  /api/evidence/{session_id}        → current EvidencePool
POST /api/evidence/{session_id}/items  → add a manual item
PATCH /api/evidence/{session_id}/items/{item_id}  → edit claim/confidence/category
POST /api/evidence/{session_id}/analyze            → kick off analysis with selected_item_ids
POST /api/evidence/pool                → build a pool synchronously from text + sources (no LLM)
POST /api/evidence/pool/import         → import an externally-built pool
```

Subscribe to `ws://.../ws/evidence/{session_id}?token=<token>` to watch gathering progress with the same event format as analysis.

If you don't need curation, skip this entirely — pass `evidence_sources`/`evidence` directly to `POST /api/analysis` with `research_enabled: true`.

---

## 7. Configuration endpoints

These mutate process and on-disk state. The token-holder can change provider credentials and templates. **Treat as privileged.**

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/techniques` | List the ~12 registered techniques (id, name, category, default temperature) |
| `GET` | `/api/config/providers` | Per-provider availability and default model |
| `GET` | `/api/config/models/{provider}` | List models known to that provider |
| `GET` / `PUT` | `/api/config/settings` | Read / update provider keys, technique overrides, adversarial defaults |
| `POST` | `/api/config/test-provider` | Validate an API key with a tiny test call |
| `GET` / `POST` / `DELETE` | `/api/config/templates[/upload\|/{filename}]` | Manage custom Jinja2 report templates (custom templates land in `~/.sat/templates/`) |
| `GET` / `PUT` | `/api/config/style-guide` | Persistent style guide text used by report rendering |
| `GET` / `PUT` | `/api/config/exemplar` | Persistent exemplar text used by report rendering |

`PUT /api/config/settings` returns settings with masked API key previews — full keys are never returned in responses.

---

## 8. Health and discovery

- `GET /api/health` → `{ "status": "ok", "version": "..." }`. **Unauthenticated.** Suitable for liveness probes.
- Interactive OpenAPI docs at `http://<host>:<port>/docs` (Swagger UI) and `/openapi.json`. Both require auth in non-`SAT_DISABLE_AUTH` mode.

---

## 9. Errors

The API uses standard HTTP status codes:

- `400 Bad Request` — Pydantic validation failed (oversize input, bad enum, etc.)
- `401 Unauthorized` — Missing/invalid bearer token
- `404 Not Found` — Unknown `run_id` / `session_id` / artifact path
- `409 Conflict` — Run state transition not allowed (e.g., cancelling a completed run)
- `429 Too Many Requests` — Rate limited (per-provider concurrency cap, default 4)
- `500 Internal Server Error` — Unhandled exception in the pipeline

Error bodies follow FastAPI's default `{ "detail": "..." }` shape unless otherwise documented in the route.

For WebSocket failures: `4001` = unauthorized, `4004` = not found, `1000` = clean close, `1006` = abnormal close (treat as transient and reconnect; the replay buffer will catch you up).

---

## 10. Minimal end-to-end example (Python)

```python
import os, requests, json
from websockets.sync.client import connect

BASE = os.environ["SAT_API_URL"]            # e.g. http://localhost:8742
TOK  = os.environ["SAT_AUTH_TOKEN"]
H    = {"Authorization": f"Bearer {TOK}"}

# 1. Start a run
r = requests.post(f"{BASE}/api/analysis", headers=H, json={
    "question": "Will the ceasefire hold through Q3?",
    "research_enabled": True,
    "adversarial_enabled": True,
    "report_enabled": True,
}).json()
run_id = r["run_id"]

# 2. Stream events until terminal
ws_url = f"{r['ws_url']}?token={TOK}"
with connect(ws_url) as ws:
    while True:
        try:
            evt = json.loads(ws.recv(timeout=120))
        except TimeoutError:
            break
        print(evt["type"], evt["data"])
        if evt["type"] == "StageCompleted" and evt["data"].get("stage") == "synthesis":
            break

# 3. Fetch the result
detail = requests.get(f"{BASE}/api/runs/{run_id}", headers=H).json()
print(detail["status"], "->", detail.get("synthesis_content"))

# 4. Download the report (HTML)
report = requests.get(f"{BASE}/api/runs/{run_id}/report?format=html", headers=H)
open(f"{run_id}.html", "wb").write(report.content)
```

---

## 11. Operational notes

- **Concurrency.** `RunManager` defaults to `max_concurrent=2`. Above that, runs are queued and `AnalysisResponse.queue_position` is non-null. Per-provider concurrency is capped at 4 by `ProviderRateLimiter`.
- **Long runs.** Deep research can take 20+ minutes; use `ProviderPolling` events for liveness. Set generous client-side socket timeouts.
- **Artifact paths** in events and `RunDetail.artifacts` are absolute on the server. Use the `path` query parameter of the artifact endpoints to retrieve them via the API rather than reading the filesystem directly.
- **Restart loses in-flight runs.** Persist `run_id` on your side only after the run is terminal, or be ready to resubmit.
- **Do not depend on the WebSocket as the system of record.** It's a progress feed. Truth lives in `GET /api/runs/{run_id}` and the on-disk artifacts.

---

## 12. What the API does *not* expose (yet)

- **Direct deep-research as a one-shot tool.** That capability exists as the MCP tool `sat_research`; the HTTP API only surfaces research as part of an evidence-gathering session.
- **Step-by-step technique driving.** The MCP server exposes `sat_next_prompt` / `sat_submit_result` for an agent to drive techniques one at a time. The HTTP API runs the pipeline end-to-end and reports progress; it does not expose a per-step request/response loop.

If you need either of those, run the MCP server (`sat-mcp`) instead of, or alongside, the HTTP API.
