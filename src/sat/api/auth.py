"""Shared-secret authentication for the SAT FastAPI backend.

@decision DEC-AUTH-001
@title Startup-token auth: random 32-byte hex token checked on every protected route
@status accepted
@rationale SAT is a localhost-only desktop app where Electron spawns the Python
sidecar. There is no multi-user session management — a single shared secret is
sufficient and avoids session cookie complexity. The token is generated once at
module import time (process lifetime), printed to stdout as SAT_AUTH_TOKEN=<token>
so the Electron sidecar manager can capture it, then validated on every HTTP request
via an Authorization: Bearer <token> header and on WebSocket connections via a
?token=<token> query parameter.

SAT_DISABLE_AUTH=1 env var bypasses all checks for the test suite and for dev mode
where the API is run standalone without Electron.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status

# ---------------------------------------------------------------------------
# Token: generated once at module import (process lifetime)
# ---------------------------------------------------------------------------

AUTH_TOKEN: str = secrets.token_hex(32)
"""32-byte (64 hex char) cryptographically random token.

Generated once when the module is first imported and lives for the duration
of the process. Printed to stdout in main.py so Electron can capture it.
"""


def get_auth_token() -> str:
    """Return the current process's auth token.

    Provided as a function (rather than direct module access) so tests can
    monkey-patch it if needed — though in practice the module-level AUTH_TOKEN
    is used directly.
    """
    return AUTH_TOKEN


def _auth_disabled() -> bool:
    """Return True when SAT_DISABLE_AUTH=1 is set in the environment.

    Used by the test suite and standalone dev runs to bypass token checks.
    Reads os.environ at call time so tests can set/unset it with monkeypatch.
    """
    return os.environ.get("SAT_DISABLE_AUTH", "").strip() == "1"


# ---------------------------------------------------------------------------
# HTTP dependency: inject via Depends(verify_token)
# ---------------------------------------------------------------------------


async def verify_token(
    authorization: str | None = Header(default=None),
) -> None:
    """FastAPI dependency that validates the Authorization: Bearer <token> header.

    Raises HTTP 401 Unauthorized if:
    - The header is absent
    - The header does not start with "Bearer "
    - The token after "Bearer " does not match AUTH_TOKEN

    Returns None (no value) on success — callers use this purely for its
    side-effect (raising 401 on auth failure).

    SAT_DISABLE_AUTH=1 bypasses all checks.
    """
    if _auth_disabled():
        return

    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[len("Bearer "):]
    if not secrets.compare_digest(token, AUTH_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# WebSocket helper: call directly (no Depends support for WS query params)
# ---------------------------------------------------------------------------


def verify_ws_token(token: str) -> bool:
    """Validate a token passed as a WebSocket query parameter.

    Returns True if the token is valid (or auth is disabled), False otherwise.
    Callers must close the WebSocket with code 4001 when this returns False.

    Uses secrets.compare_digest to prevent timing attacks.
    SAT_DISABLE_AUTH=1 always returns True.
    """
    if _auth_disabled():
        return True

    if not token:
        return False

    return secrets.compare_digest(token, AUTH_TOKEN)


# ---------------------------------------------------------------------------
# Sentinel exception (unused in production, available for testing)
# ---------------------------------------------------------------------------


class AuthDisabledError(Exception):
    """Raised internally when auth is expected to be enabled but SAT_DISABLE_AUTH is set.

    Not used in production. Available for tests that need to assert
    about disabled-auth vs enabled-auth code paths.
    """
