"""FastAPI router exposing G.O.D.A.I. pipeline over HTTP (B4 + Q4 SSE streaming)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from godai.models.request import TrustLevel
from godai.modules.hermes import create_token
from godai.pipeline import GodaiPipeline
from godai.providers import AnthropicProvider, EchoProvider, OllamaProvider

from .settings import settings

_logger = logging.getLogger("frapp.godai_router")

router = APIRouter(prefix="/v1/godai", tags=["G.O.D.A.I."])

# Pipeline — einmal pro Backend-Wahl gebaut; wechselt die Wahl (z. B. in den
# SCRIPTOR-Einstellungen auf Ollama), wird sie neu aufgebaut.
_pipeline: GodaiPipeline | None = None
_pipeline_key: tuple[str, str, str] | None = None


def _backend() -> tuple[str, str, str]:
    """(provider, ollama_url, ollama_model) — SSOT: FRAPP_LLM_PROVIDER, sonst SCRIPTOR-Einstellung."""
    provider, url, model = settings.llm_provider, settings.ollama_url, settings.ollama_model
    if not provider:
        try:
            from scriptor.settings import Settings as ScriptorSettings

            s = ScriptorSettings.load()
            if s.provider == "ollama":
                provider, url, model = "ollama", s.ollama_url, s.ollama_model
        except Exception as exc:  # SCRIPTOR nicht installiert oder Einstellungen unlesbar
            _logger.debug("SCRIPTOR-Einstellungen nicht lesbar: %s", exc)
    if provider in ("", "anthropic"):
        provider = "anthropic" if settings.anthropic_api_key else "echo"
    return provider, url, model


def _provider_label(key: tuple[str, str, str]) -> str:
    provider, _, model = key
    if provider == "ollama":
        return f"OllamaProvider ({model})"
    return "AnthropicProvider" if provider == "anthropic" else "EchoProvider"


def _get_pipeline() -> GodaiPipeline:
    global _pipeline, _pipeline_key
    key = _backend()
    if _pipeline is None or key != _pipeline_key:
        provider_name, url, model = key
        provider: Any
        if provider_name == "ollama":
            provider = OllamaProvider(model=model, base_url=url, max_tokens=2048, timeout=600.0)
        elif provider_name == "anthropic":
            provider = AnthropicProvider(api_key=settings.anthropic_api_key, max_tokens=2048)
        else:
            provider = EchoProvider()
        _logger.info("G.O.D.A.I. pipeline initialised (%s)", _provider_label(key))
        _pipeline = GodaiPipeline.create(
            llm_provider=provider,
            secret_key=settings.secret_key,
            dev_mode=(settings.env != "production"),
        )
        _pipeline_key = key
    return _pipeline


class TokenRequest(BaseModel):
    user_id: str
    trust_level: str = "L1"
    expires_hours: int = 24


class TokenResponse(BaseModel):
    token: str
    user_id: str
    trust_level: str
    expires_hours: int


class QueryRequest(BaseModel):
    token: str | None = None
    user_id: str
    protocol: str = "http"
    query: str
    context: dict[str, Any] | None = None


class QueryResponse(BaseModel):
    success: bool
    output: str | None
    error: str | None
    model_id: str | None
    timestamp: datetime


class AuditEntry(BaseModel):
    chain_index: int
    event_type: str
    source_module: str
    timestamp: datetime
    event_data: dict[str, Any]


class AuditResponse(BaseModel):
    entries: list[AuditEntry]
    total: int
    chain_valid: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Submit a query to the G.O.D.A.I. pipeline",
)
async def godai_query(req: QueryRequest):
    pipeline = _get_pipeline()
    result = await pipeline.process(
        token=req.token,
        user_id=req.user_id,
        protocol=req.protocol,
        query=req.query,
        context=req.context,
    )
    model_id = result.route_decision.model_id if result.route_decision else None
    return QueryResponse(
        success=result.success,
        output=result.output,
        error=result.error,
        model_id=model_id,
        timestamp=result.timestamp,
    )


@router.post(
    "/stream",
    summary="Submit a query and receive the response as a Server-Sent Events stream (Q4)",
    response_class=StreamingResponse,
)
async def godai_stream(req: QueryRequest):
    """
    Streams the G.O.D.A.I. pipeline response as SSE.

    Each event is a JSON object:
      data: {"chunk": "<text>"}
      data: {"done": true, "success": bool, "model_id": str|null}

    Connect with EventSource or curl:
      curl -N -X POST /v1/godai/stream \\
           -H "X-API-Key: dev-key" \\
           -H "Content-Type: application/json" \\
           -d '{"user_id": "alice", "query": "...", ...}'
    """
    pipeline = _get_pipeline()

    async def _sse() -> AsyncIterator[str]:
        result = await pipeline.process(
            token=req.token,
            user_id=req.user_id,
            protocol=req.protocol,
            query=req.query,
            context=req.context,
        )
        if result.output:
            # Chunk at word boundaries for natural streaming feel
            words = result.output.split(" ")
            for i, word in enumerate(words):
                chunk = word if i == 0 else " " + word
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        model_id = result.route_decision.model_id if result.route_decision else None
        yield f"data: {json.dumps({'done': True, 'success': result.success, 'model_id': model_id})}\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class StatusResponse(BaseModel):
    status: str
    audit_entries: int
    chain_valid: bool
    provider: str


@router.get(
    "/status", response_model=StatusResponse, summary="Pipeline health and audit chain status"
)
def godai_status():
    pipeline = _get_pipeline()
    try:
        chain_valid = pipeline.mnemosyne.verify_chain()
    except Exception:
        chain_valid = False
    provider_name = _provider_label(_pipeline_key or _backend())
    return {
        "status": "ok",
        "audit_entries": len(pipeline.mnemosyne),
        "chain_valid": chain_valid,
        "provider": provider_name,
    }


@router.get(
    "/audit",
    response_model=AuditResponse,
    summary="Paginated MNEMOSYNE audit log (admin)",
)
def godai_audit(limit: int = 50, offset: int = 0):
    pipeline = _get_pipeline()
    all_entries = pipeline.mnemosyne.entries
    page = all_entries[offset : offset + limit]
    try:
        chain_valid = pipeline.mnemosyne.verify_chain()
    except Exception:
        chain_valid = False
    return AuditResponse(
        entries=[
            AuditEntry(
                chain_index=e.chain_index,
                event_type=e.event_type,
                source_module=e.source_module,
                timestamp=e.timestamp,
                event_data=e.event_data,
            )
            for e in page
        ],
        total=len(all_entries),
        chain_valid=chain_valid,
    )


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Issue a signed JWT for G.O.D.A.I. pipeline access",
)
def issue_token(req: TokenRequest):
    try:
        trust_level = TrustLevel[req.trust_level]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trust_level '{req.trust_level}'. Must be L1, L2, or L3.",
        )
    token = create_token(
        user_id=req.user_id,
        trust_level=trust_level,
        secret_key=settings.secret_key,
        expires_hours=req.expires_hours,
    )
    return TokenResponse(
        token=token,
        user_id=req.user_id,
        trust_level=req.trust_level,
        expires_hours=req.expires_hours,
    )
