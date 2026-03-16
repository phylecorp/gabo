"""SAT API server entry point.

@decision DEC-AUTH-004
@title Print SAT_AUTH_TOKEN to stdout before uvicorn starts
@status accepted
@rationale The Electron sidecar manager captures the auth token by parsing
stdout from the Python process. Printing before uvicorn.run() ensures the
token line appears before any uvicorn startup logs, making it easy to parse
with a simple startswith("SAT_AUTH_TOKEN=") check. sys.stdout.flush() is
redundant when print(flush=True) is used but harmless. The token is already
generated at module import (auth.py), so printing it here adds no latency.

Run with:
    python -m sat.api.main --port 8742
    sat-api --port 8742
"""

from __future__ import annotations

import argparse

import uvicorn
from dotenv import load_dotenv

from sat.api.app import create_app
from sat.api.auth import AUTH_TOKEN


def main() -> None:
    """Parse CLI args, load .env, print auth token, then start the uvicorn server."""
    parser = argparse.ArgumentParser(
        description="SAT API server — REST + WebSocket interface for the SAT pipeline"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8742,
        help="Port to listen on (default: 8742)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    # Load .env before creating the app so API keys are available when
    # routes inspect os.environ (e.g., /api/config/providers)
    load_dotenv()

    # Print the auth token before server startup so the Electron sidecar manager
    # can parse it from stdout. The structured format SAT_AUTH_TOKEN=<token> is
    # parsed by sidecar.ts. flush=True ensures the line is delivered even if
    # stdout is buffered (e.g., when piped).
    print(f"SAT_AUTH_TOKEN={AUTH_TOKEN}", flush=True)

    app = create_app(port=args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
