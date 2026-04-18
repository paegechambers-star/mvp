"""FastAPI router exposing G.O.D.A.I. pipeline over HTTP (B4)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from godai.pipeline import GodaiPipeline
from godai.providers import EchoProvider

_logger = logging.getLogger("frapp.godai_router")

router = APIRouter(prefix="/v1/godai", tags=["G.O.D.A.I."])

# Singleton pipeline — created once at first request
_pipeline: Optional[GodaiPipeline] = None


def _get_pipeline() -> GodaiPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = GodaiPipeline.create(llm_provider=EchoProvider())
        _logger.info("G.O.D.A.I. pipeline initialised (EchoProvider)")
    return _pipeline


# ── Schemas ───────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    token: Optional[str] = None
    user_id: str
    protocol: str = "http"
    query: str
    context: Optional[Dict[str, Any]] = None


class QueryResponse(BaseModel):
    success: bool
    output: Optional[str]
    error: Optional[str]
    model_id: Optional[str]
    timestamp: datetime


class AuditEntry(BaseModel):
    chain_index: int
    event_type: str
    source_module: str
    timestamp: datetime
    event_data: Dict[str, Any]


class AuditResponse(BaseModel):
    entries: List[AuditEntry]
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


@router.get("/status", summary="Pipeline health and audit chain status")
def godai_status():
    pipeline = _get_pipeline()
    try:
        chain_valid = pipeline.mnemosyne.verify_chain()
    except Exception:
        chain_valid = False
    return {
        "status": "ok",
        "audit_entries": len(pipeline.mnemosyne),
        "chain_valid": chain_valid,
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
