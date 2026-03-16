"""FastAPI application factory for the SAT API.

@decision DEC-API-006
@title Single app factory with RunManager as shared singleton
@status accepted
@rationale All routes that need to interact with in-flight runs (analysis POST,
runs GET, WebSocket) need access to the same RunManager instance. Passing it
through the factory function (rather than a global module-level singleton) makes
the app testable — tests can create a fresh RunManager per test without cross-
contamination. The factory pattern also makes it trivial to run multiple servers
on different ports if needed (each gets its own RunManager).

@decision DEC-SEC-002
@title CORS restricted to localhost and 127.0.0.1 origins via allow_origin_regex
@status accepted
@rationale SAT is a localhost-only desktop app. Using allow_origins=["*"] would
allow any web page visited by the user to make cross-origin requests to the API,
which could exfiltrate analysis results or trigger expensive LLM calls. The regex
restricts allowed origins to http(s)://localhost and http(s)://127.0.0.1 with any
port. allow_origins=["*"] with allow_credentials=True is also rejected by browsers
(CORS spec), so wildcard was already broken for credentialed requests. The Electron
renderer uses file:// which does not send an Origin header at all and passes
without CORS checks. FastAPI CORSMiddleware does not support port wildcards in
allow_origins, so allow_origin_regex is the correct approach.

@decision DEC-AUTH-002
@title Router-level auth dependency - health endpoint excluded via separate route
@status accepted
@rationale Applying verify_token as a router-level dependency on each sub-router
(rather than app-level middleware) gives fine-grained control. The /api/health
endpoint is registered directly on the app (not on any sub-router) so it remains
accessible to the Electron sidecar's health-poll loop even before the token is
captured from stdout. WebSocket routes handle auth via verify_ws_token() at
connection time (query param), since WebSocket upgrade requests cannot carry
custom headers in browsers.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sat.api.auth import verify_token
from sat.api.evidence_manager import EvidenceSessionManager
from sat.api.models import HealthResponse
from sat.api.run_manager import RunManager
from sat.api.routes.analysis import create_analysis_router
from sat.api.routes.config import router as config_router
from sat.api.routes.evidence import create_evidence_router
from sat.api.routes.models import router as models_router
from sat.api.routes.runs import create_runs_router
from sat.api.routes.techniques import router as techniques_router
from sat.api.ws import create_ws_router
from sat.providers.rate_limiter import ProviderRateLimiter

# Regex matching localhost and 127.0.0.1 on any port, http or https.
# Electron renderer uses file:// which sends no Origin header and bypasses CORS
# entirely - no special case needed.
_LOCALHOST_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def create_app(port: int = 8742) -> FastAPI:
    """Create and return a configured FastAPI application.

    Args:
        port: The port the server will listen on. Used to construct ws_url
              values returned in AnalysisResponse.

    A shared ProviderRateLimiter is created and passed to all routes that
    create LLM calls. This ensures a global cap on concurrent LLM API calls
    across all concurrent analysis runs.

    All routes except /api/health require Authorization: Bearer <token> header.
    WebSocket routes require ?token=<token> query parameter.
    Set SAT_DISABLE_AUTH=1 to bypass auth for tests and standalone dev runs.
    """
    app = FastAPI(title="Gabo API", version="0.1.0")

    # CORS: restrict to localhost origins only (DEC-SEC-002).
    # SAT is a desktop-only app - no external origins should be able to make
    # cross-origin requests. The Electron renderer uses file:// which sends no
    # Origin header, so it is unaffected by this restriction.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=_LOCALHOST_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    manager = RunManager(max_concurrent=2)
    evidence_manager = EvidenceSessionManager()
    rate_limiter = ProviderRateLimiter(max_concurrent_per_provider=4)

    # Store managers on app.state so tests and diagnostic tooling can inspect them
    app.state.run_manager = manager
    app.state.evidence_manager = evidence_manager

    # All API routers require auth (DEC-AUTH-002). The dependency is applied at
    # include_router time so every route on every sub-router is protected without
    # modifying each route function individually.
    auth_dep = [Depends(verify_token)]

    app.include_router(create_analysis_router(manager, port, rate_limiter), dependencies=auth_dep)
    app.include_router(create_runs_router(manager), dependencies=auth_dep)
    app.include_router(techniques_router, dependencies=auth_dep)
    app.include_router(config_router, dependencies=auth_dep)
    app.include_router(models_router, dependencies=auth_dep)
    app.include_router(
        create_evidence_router(evidence_manager, manager, port, rate_limiter),
        dependencies=auth_dep,
    )
    # WebSocket router: auth handled at connection time via verify_ws_token()
    # (query param), not via the HTTP dependency (DEC-AUTH-002).
    app.include_router(create_ws_router(manager, evidence_manager))

    # Health check: intentionally unauthenticated so the Electron sidecar's
    # health-poll loop works before the auth token is captured from stdout.
    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Health check endpoint - no auth required."""
        return HealthResponse()

    return app
