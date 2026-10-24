"""
MCP Streamable HTTP server — exposes `dispatch_to_desktop` as an MCP tool.

Implements MCP spec 2024-11-05 (JSON-RPC 2.0 over HTTP + optional SSE keep-alive)
without any external mcp package dependency.

Connect from Claude chat / Claude for Mac:
  Transport : Streamable HTTP  (or "HTTP with SSE")
  Endpoint  : http://<server>/mcp

Security rules enforced unconditionally:
  - Only trust_level="basic" (L1) is accepted from this endpoint.
    elevated / internal levels require manual desktop authorisation.
  - Auth token submitted here is NEVER forwarded to logs.
  - WRITE commands (file edits, code execution, etc.) require explicit
    confirmation at the desktop before the agent executes them.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from godai.modules.dispatch_bridge import CommandExpiredError, DispatchBridge
from godai.modules.hermes import AuthenticationError, Hermes, RateLimitError

_logger = logging.getLogger("frapp.mcp_dispatch")

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_INFO = {"name": "dispatch-bridge", "version": "1.0.0"}

_TOOL_DEF = {
    "name": "dispatch_to_desktop",
    "description": (
        "Send a task to Claude Code running on the desktop machine. "
        "Read-only tasks (show file, explain code, check status) execute automatically. "
        "Tasks that write files, run code, or call external services require explicit "
        "confirmation from the desktop operator before they run. "
        "Returns the result once the desktop agent has finished, or a clear timeout/expiry "
        "message if it does not respond in time."
    ),
    "inputSchema": {
        "type": "object",
        "required": ["command"],
        "properties": {
            "command": {
                "type": "string",
                "description": "The task or question to send to the desktop Claude agent.",
            },
            "trust_level": {
                "type": "string",
                "enum": ["basic"],
                "default": "basic",
                "description": (
                    "Trust level. Only 'basic' (L1) is accepted from chat context. "
                    "Higher levels (elevated, internal) require manual desktop authorisation."
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "default": 120,
                "minimum": 10,
                "maximum": 300,
                "description": "Seconds to wait for the desktop to respond (default 120, max 300).",
            },
        },
    },
}


# ------------------------------------------------------------------
# JSON-RPC helpers
# ------------------------------------------------------------------

def _ok(req_id: Any, result: Any) -> Dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> Dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ------------------------------------------------------------------
# Router factory
# ------------------------------------------------------------------

def build_mcp_router(bridge: DispatchBridge, hermes: Hermes) -> APIRouter:
    """Return a FastAPI router that mounts the MCP endpoint at /mcp."""

    router = APIRouter(prefix="/mcp", tags=["mcp"])

    async def _dispatch_tool(req_id: Any, args: Dict) -> Dict:
        """Handle a tools/call for dispatch_to_desktop."""
        command = (args.get("command") or "").strip()
        if not command:
            return _rpc_error(req_id, -32602, "'command' is required and must not be empty.")

        # Hard ceiling: basic trust only from MCP/chat context
        trust_level = args.get("trust_level", "basic")
        if trust_level != "basic":
            return _rpc_error(
                req_id, -32602,
                "Only trust_level='basic' is permitted from chat context. "
                "elevated/internal require manual desktop authorisation.",
            )

        timeout = min(int(args.get("timeout_seconds", 120)), 300)

        # Enqueue — classifier runs inside enqueue(), sets requires_confirmation
        cmd = await bridge.enqueue(
            user_id="mcp-chat",
            payload=command,
            context={"trust_level": "basic"},
            ttl_seconds=timeout,
            source="mcp-chat",
        )

        if cmd.requires_confirmation:
            _logger.info(
                "WRITE command %s queued from mcp-chat — desktop confirmation required",
                cmd.command_id,
            )

        # Poll for completion
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(2)
            try:
                stored = bridge.get_result(cmd.command_id)
            except CommandExpiredError:
                return _ok(req_id, {
                    "content": [{
                        "type": "text",
                        "text": (
                            f"⚠ Command `{cmd.command_id}` expired before the desktop responded. "
                            f"The desktop agent may be offline. Re-send when it reconnects."
                        ),
                    }],
                    "isError": True,
                })
            except KeyError:
                # Should not happen — was just enqueued
                continue

            if stored.completed:
                result_text = stored.result or "(desktop returned no output)"
                if stored.requires_confirmation:
                    result_text = f"✓ Confirmed and executed by desktop operator.\n\n{result_text}"
                return _ok(req_id, {
                    "content": [{"type": "text", "text": result_text}],
                })

        return _ok(req_id, {
            "content": [{
                "type": "text",
                "text": (
                    f"⏰ Timeout ({timeout}s): desktop did not respond. "
                    f"Command ID: `{cmd.command_id}` — it remains queued until it expires."
                ),
            }],
            "isError": True,
        })

    async def _handle_rpc(msg: Dict, request: Request) -> Optional[Dict]:
        """Dispatch one JSON-RPC message and return the response (or None for notifications)."""
        method = msg.get("method", "")
        req_id = msg.get("id")        # None for notifications
        params = msg.get("params") or {}

        if method == "initialize":
            return _ok(req_id, {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": _SERVER_INFO,
            })

        if method in ("initialized", "notifications/initialized"):
            return None  # notification — no response

        if method == "ping":
            return _ok(req_id, {})

        if method == "tools/list":
            return _ok(req_id, {"tools": [_TOOL_DEF]})

        if method == "tools/call":
            name = params.get("name")
            if name != "dispatch_to_desktop":
                return _rpc_error(req_id, -32601, f"Unknown tool: {name!r}")
            return await _dispatch_tool(req_id, params.get("arguments") or {})

        if req_id is None:
            return None  # unknown notification — ignore silently
        return _rpc_error(req_id, -32601, f"Method not found: {method!r}")

    # ------------------------------------------------------------------
    # POST /mcp — primary JSON-RPC endpoint
    # ------------------------------------------------------------------

    @router.post("")
    async def mcp_post(request: Request) -> JSONResponse:
        """
        Receive a JSON-RPC 2.0 message (or batch) and return the response.

        Tool calls block here until the desktop agent completes the command
        or the timeout elapses — this is correct MCP behaviour for long-running tools.
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                _rpc_error(None, -32700, "Parse error — body must be valid JSON"),
                status_code=400,
            )

        if isinstance(body, list):
            responses = [r for msg in body if (r := await _handle_rpc(msg, request)) is not None]
            return JSONResponse(responses if responses else None, status_code=200 if responses else 202)

        resp = await _handle_rpc(body, request)
        if resp is None:
            return JSONResponse(None, status_code=202)
        return JSONResponse(resp)

    # ------------------------------------------------------------------
    # GET /mcp — SSE keep-alive (required by MCP 2024-11-05 spec)
    # ------------------------------------------------------------------

    @router.get("")
    async def mcp_sse(request: Request) -> StreamingResponse:
        """
        SSE endpoint required by the MCP transport spec.
        Sends a session endpoint event and then a keepalive ping every 15 s.
        """
        async def _stream():
            base = str(request.base_url).rstrip("/")
            yield f"event: endpoint\ndata: {json.dumps({'uri': base + '/mcp'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                await asyncio.sleep(15)
                yield ": keepalive\n\n"

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return router
