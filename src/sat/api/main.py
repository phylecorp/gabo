"""SAT API server entry point.

Run with:
    python -m sat.api.main --port 8742
    sat-api --port 8742
"""

from __future__ import annotations

import argparse

import uvicorn
from dotenv import load_dotenv

from sat.api.app import create_app


def main() -> None:
    """Parse CLI args, load .env, then start the uvicorn server."""
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

    app = create_app(port=args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
