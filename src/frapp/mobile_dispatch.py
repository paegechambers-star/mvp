"""
Mobile-to-Desktop dispatch API endpoints.

Provides:
  POST /mobile/dispatch              Mobile sends a command (requires auth token)
  GET  /mobile/pending               Desktop polls for pending commands
  POST /mobile/result/{command_id}   Desktop posts the result of a command
  GET  /mobile/result/{command_id}   Mobile polls for the result
  WS   /ws/desktop                   Desktop Claude listens in real-time

Auth: all endpoints require a bearer token in the Authorization header.
The token is forwarded through HERMES for trust-level assignment exactly
as regular pipeline requests are.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from godai.modules.dispatch_bridge import DispatchBridge
from godai.modules.hermes import AuthenticationError, Hermes, RateLimitError

_logger = logging.getLogger("frapp.mobile_dispatch")

router = APIRouter(prefix="/mobile", tags=["mobile-dispatch"])


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------


class DispatchRequest(BaseModel):
    user_id: str
    payload: str
    context: Optional[Dict[str, Any]] = None
    ttl_seconds: int = 300


class ResultPost(BaseModel):
    result: str
    agent_id: str


# ------------------------------------------------------------------
# Dependency: extract & validate bearer token
# ------------------------------------------------------------------


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


# ------------------------------------------------------------------
# Endpoint factory
#
# The router itself is stateless; the DispatchBridge and Hermes instances
# are injected at registration time via the factory below so that the
# FastAPI app can share the same singletons across all routes.
# ------------------------------------------------------------------


def build_router(bridge: DispatchBridge, hermes: Hermes) -> APIRouter:
    """Return a fully-wired mobile-dispatch router."""

    @router.post("/dispatch", status_code=202)
    async def dispatch_command(
        body: DispatchRequest,
        authorization: Optional[str] = Header(default=None),
    ):
        """Mobile client submits a command for desktop Claude to execute."""
        token = _extract_token(authorization)
        try:
            await hermes.normalize(
                token=token,
                user_id=body.user_id,
                protocol="http",
                query=body.payload,
                context=body.context or {},
            )
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        cmd = await bridge.enqueue(
            user_id=body.user_id,
            payload=body.payload,
            context=body.context,
            ttl_seconds=body.ttl_seconds,
        )
        return {"command_id": str(cmd.command_id), "status": "queued"}

    @router.get("/pending")
    async def get_pending(
        authorization: Optional[str] = Header(default=None),
    ):
        """Desktop agent polls for pending commands it should execute."""
        token = _extract_token(authorization)
        # Any valid token grants read access to the queue (L1+)
        try:
            await hermes.normalize(
                token=token,
                user_id="desktop-agent",
                protocol="http",
                query="poll-pending",
            )
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        return {"commands": [c.to_dict() for c in bridge.pending()]}

    @router.post("/result/{command_id}", status_code=200)
    async def post_result(
        command_id: UUID,
        body: ResultPost,
        authorization: Optional[str] = Header(default=None),
    ):
        """Desktop agent posts the result of an executed command."""
        token = _extract_token(authorization)
        try:
            await hermes.normalize(
                token=token,
                user_id=body.agent_id,
                protocol="http",
                query="post-result",
            )
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        ok = await bridge.complete(command_id, result=body.result, user_id=body.agent_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Command not found or expired")
        return {"command_id": str(command_id), "status": "completed"}

    @router.get("/result/{command_id}")
    async def get_result(
        command_id: UUID,
        authorization: Optional[str] = Header(default=None),
    ):
        """Mobile client polls for the result of a previously dispatched command."""
        token = _extract_token(authorization)
        try:
            await hermes.normalize(
                token=token,
                user_id="mobile-poll",
                protocol="http",
                query="poll-result",
            )
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        cmd = bridge.get_result(command_id)
        if cmd is None:
            raise HTTPException(status_code=404, detail="Command not found or expired")
        return cmd.to_dict()

    # ------------------------------------------------------------------
    # WebSocket — real-time desktop listener
    # ------------------------------------------------------------------

    @router.websocket("/ws/desktop")
    async def desktop_websocket(websocket: WebSocket):
        """
        Desktop Claude connects here to receive commands in real time.

        Protocol (JSON frames):
          Server → Client: {"type": "command", "data": <DispatchCommand.to_dict()>}
          Client → Server: {"type": "result", "command_id": "...", "result": "..."}
          Server → Client: {"type": "ack",     "command_id": "..."}
          Server → Client: {"type": "ping"}
        """
        await websocket.accept()
        _logger.info("Desktop WebSocket connected from %s", websocket.client)

        try:
            while True:
                # Long-poll for new commands (up to 25 s, then send a keepalive ping)
                commands = await bridge.wait_for_command(timeout=25.0)
                if not commands:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                    continue

                for cmd in commands:
                    await websocket.send_text(
                        json.dumps({"type": "command", "data": cmd.to_dict()})
                    )

                # Receive results from the desktop agent
                try:
                    raw = await websocket.receive_text()
                    msg = json.loads(raw)
                    if msg.get("type") == "result":
                        cid = UUID(msg["command_id"])
                        await bridge.complete(
                            command_id=cid,
                            result=msg.get("result", ""),
                            user_id="desktop-ws-agent",
                        )
                        await websocket.send_text(
                            json.dumps({"type": "ack", "command_id": str(cid)})
                        )
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    _logger.warning("Invalid message from desktop agent: %s", exc)

        except WebSocketDisconnect:
            _logger.info("Desktop WebSocket disconnected")

    return router
