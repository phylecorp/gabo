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
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sat.api.evidence_manager import EvidenceSessionManager
from sat.api.models import HealthResponse
from sat.api.run_manager import RunManager
from sat.providers.rate_limiter import ProviderRateLimiter
from sat.api.routes.analysis import create_analysis_router
from sat.api.routes.config import router as config_router
from sat.api.routes.evidence import create_evidence_router
from sat.api.routes.runs import create_runs_router
from sat.api.routes.techniques import router as techniques_router
from sat.api.ws import create_ws_router


def create_app(port: int = 8742) -> FastAPI:
    """Create and return a configured FastAPI application.

    Args:
        port: The port the server will listen on. Used to construct ws_url
              values returned in AnalysisResponse.

    A shared ProviderRateLimiter is created and passed to all routes that
    create LLM calls. This ensures a global cap on concurrent LLM API calls
    across all concurrent analysis runs.
    """
    app = FastAPI(title="Gabo API", version="0.1.0")

    # CORS: allow all origins for the Electron desktop app, which may use
    # file:// or a localhost dev server as origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    manager = RunManager(max_concurrent=2)
    evidence_manager = EvidenceSessionManager()
    rate_limiter = ProviderRateLimiter(max_concurrent_per_provider=4)

    app.include_router(create_analysis_router(manager, port, rate_limiter))
    app.include_router(create_runs_router(manager))
    app.include_router(techniques_router)
    app.include_router(config_router)
    app.include_router(create_evidence_router(evidence_manager, manager, port, rate_limiter))
    app.include_router(create_ws_router(manager, evidence_manager))

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Health check endpoint."""
        return HealthResponse()

    return app
