"""
Mobile-to-Desktop dispatch API endpoints.

Provides:
  POST /mobile/dispatch              Mobile/chat sends a command (requires auth token)
  GET  /mobile/pending               Desktop polls for pending commands
  POST /mobile/result/{command_id}   Desktop posts the result of a command
  GET  /mobile/result/{command_id}   Mobile polls for the result (410 on expiry)
  WS   /ws/desktop                   Desktop Claude listens in real-time

Auth: all endpoints require a bearer token in the Authorization header.
      Token controls trust level (L1/L2/L3) via HERMES.
      Tokens are never forwarded to audit logs in cleartext.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from godai.modules.dispatch_bridge import CommandExpiredError, DispatchBridge
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
# Helpers
# ------------------------------------------------------------------

def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _source_from_request(request: Request) -> str:
    """Build a source identifier from the HTTP request (no tokens, no sensitive data)."""
    client = request.client
    ip = client.host if client else "unknown"
    ua = (request.headers.get("user-agent") or "")[:40]
    return f"{ip} ({ua})" if ua else ip


# ------------------------------------------------------------------
# Endpoint factory
# ------------------------------------------------------------------

def build_router(bridge: DispatchBridge, hermes: Hermes) -> APIRouter:
    """Return a fully-wired mobile-dispatch router."""

    @router.post("/dispatch", status_code=202)
    async def dispatch_command(
        body: DispatchRequest,
        request: Request,
        authorization: Optional[str] = Header(default=None),
    ):
        """
        Mobile/chat client submits a command for desktop Claude to execute.

        The DispatchBridge classifies the command as READ or WRITE.
        WRITE commands are flagged requires_confirmation=True in the response —
        the desktop agent MUST ask for confirmation before executing them.
        """
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
            source=_source_from_request(request),
        )
        resp = {"command_id": str(cmd.command_id), "status": "queued"}
        if cmd.requires_confirmation:
            resp["requires_confirmation"] = True
            resp["notice"] = (
                "This command modifies files or executes code. "
                "It will not run until the desktop operator confirms it."
            )
        return resp

    @router.get("/pending")
    async def get_pending(
        authorization: Optional[str] = Header(default=None),
    ):
        """Desktop agent polls for pending commands it should execute."""
        token = _extract_token(authorization)
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
            raise HTTPException(
                status_code=410,
                detail=f"Command {command_id} has expired or was not found.",
            )
        return {"command_id": str(command_id), "status": "completed"}

    @router.get("/result/{command_id}")
    async def get_result(
        command_id: UUID,
        authorization: Optional[str] = Header(default=None),
    ):
        """
        Mobile client polls for the result of a previously dispatched command.

        HTTP status codes:
          200  command found (check .completed for result)
          404  command_id was never seen
          410  command existed but its TTL has elapsed
        """
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

        try:
            cmd = bridge.get_result(command_id)
        except CommandExpiredError as exc:
            raise HTTPException(
                status_code=410,
                detail=f"Command {command_id} has expired (TTL elapsed). Re-send to try again.",
            ) from exc
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Command {command_id} not found.")

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
          Client → Server: {"type": "result",  "command_id": "...", "result": "..."}
          Server → Client: {"type": "ack",      "command_id": "..."}
          Server → Client: {"type": "ping"}

        IMPORTANT: the client must check data.requires_confirmation before
        executing WRITE commands — they require a visible desktop confirmation first.
        """
        await websocket.accept()
        _logger.info("Desktop WebSocket connected from %s", websocket.client)

        try:
            while True:
                commands = await bridge.wait_for_command(timeout=25.0)
                if not commands:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                    continue

                for cmd in commands:
                    await websocket.send_text(
                        json.dumps({"type": "command", "data": cmd.to_dict()})
                    )

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
