"""WebSocket endpoint for real-time pipeline progress streaming.

@decision DEC-API-003
@title Late-join catch-up via events_log replay before live subscription
@status accepted
@rationale The Electron frontend may open the WebSocket connection after the
pipeline has already emitted some events (e.g., between POST response and WS
open). Replaying events_log ensures no progress is lost regardless of connection
timing. The tradeoff is that slow clients receive a burst on connect, but the
log is bounded by the pipeline's event count (O(100s) at most) so this is safe.

@decision DEC-AUTH-003
@title WebSocket auth via ?token= query param, rejected before accept()
@status accepted
@rationale HTTP headers cannot be set on WebSocket upgrade requests from browsers
(the WebSocket API does not expose custom headers). The standard approach is to
pass credentials as a query parameter. The token is validated before accept() is
called so that invalid connections are rejected at the protocol level (close code
4001) rather than after the handshake completes. close() before accept() is
supported by Starlette's WebSocket implementation.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sat.api.auth import verify_ws_token
from sat.api.evidence_manager import EvidenceSessionManager
from sat.api.run_manager import RunManager


def create_ws_router(manager: RunManager, evidence_manager: EvidenceSessionManager | None = None) -> APIRouter:
    """Return the WebSocket router wired to the given RunManager (and optional EvidenceSessionManager)."""
    router = APIRouter()

    @router.websocket("/ws/analysis/{run_id}")
    async def analysis_ws(websocket: WebSocket, run_id: str, token: str = "") -> None:
        """Analysis progress WebSocket.

        Requires ?token=<auth_token> query parameter. Closes with code 4001
        if the token is invalid or absent.
        """
        if not verify_ws_token(token):
            await websocket.close(code=4001, reason="Unauthorized")
            return

        run = manager.get_run(run_id)
        if not run:
            await websocket.close(code=4004, reason="Run not found")
            return

        await websocket.accept()

        # Replay buffered events so late-joining clients get full history
        for event in list(run.events_log):
            await websocket.send_json(event)

        run.ws_clients.append(websocket)
        try:
            # Keep the connection alive; receive and silently ignore client messages
            # (the pipeline is unidirectional: server -> client)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            if websocket in run.ws_clients:
                run.ws_clients.remove(websocket)

    if evidence_manager is not None:

        @router.websocket("/ws/evidence/{session_id}")
        async def evidence_ws(websocket: WebSocket, session_id: str, token: str = "") -> None:
            """Evidence gathering WebSocket — same late-join catch-up and auth pattern as analysis WS."""
            if not verify_ws_token(token):
                await websocket.close(code=4001, reason="Unauthorized")
                return

            session = evidence_manager.get_session(session_id)
            if not session:
                await websocket.close(code=4004, reason="Evidence session not found")
                return

            await websocket.accept()

            # Replay buffered events so late-joining clients get full history
            for event in list(session.events_log):
                await websocket.send_json(event)

            session.ws_clients.append(websocket)
            try:
                # Keep connection alive; pipeline is unidirectional: server -> client
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                if websocket in session.ws_clients:
                    session.ws_clients.remove(websocket)

    return router
