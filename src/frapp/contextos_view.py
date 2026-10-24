"""ContextOS in FraPP: Register lesen (SSOT/WORK), Kette prüfen, IDs validieren."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from .paths import data_dir

router = APIRouter(prefix="/v1/contextos", tags=["ContextOS"])
_state: Dict[str, Any] = {}


def _register() -> Any:
    if "register" not in _state:
        from contextos import ContextOSLog, Register

        base = data_dir() / "contextos"
        log = ContextOSLog(base / "log.db")
        _state["log"] = log
        _state["register"] = Register(base / "register.db", log)
        _state["base"] = base
    return _state["register"]


def _plain(entry: Any) -> Dict[str, Any]:
    out = asdict(entry)
    for key, value in list(out.items()):
        if hasattr(value, "value"):
            out[key] = value.value
        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()
    out["citations"] = [str(c) for c in out.get("citations", [])]
    return out


@router.get("/status", summary="ContextOS-Status: Einträge, Log-Kette")
def status() -> Dict[str, Any]:
    reg = _register()
    try:
        chain_ok = bool(_state["log"].verify_chain())
    except Exception:  # noqa: BLE001 - TamperDetectedError
        chain_ok = False
    return {
        "ssot": len(reg.all_ssot()),
        "work": len(reg.all_work()),
        "log_entries": len(_state["log"]),
        "chain_ok": chain_ok,
        "path": str(_state["base"]),
    }


@router.get("/entries", summary="Register-Einträge (ssot | work)")
def entries(partition: str = "ssot", limit: int = 200) -> List[Dict[str, Any]]:
    reg = _register()
    if partition not in ("ssot", "work"):
        raise HTTPException(status_code=422, detail="partition muss ssot oder work sein")
    items = reg.all_ssot() if partition == "ssot" else reg.all_work()
    return [_plain(e) for e in items[:limit]]


@router.get("/validate/{context_id}", summary="NKID/MKID prüfen")
def validate(context_id: str) -> Dict[str, Optional[Any]]:
    from contextos import parse_id, validate_id

    ok = validate_id(context_id)
    parsed = None
    if ok:
        p = parse_id(context_id)
        parsed = {k: (v.value if hasattr(v, "value") else v) for k, v in asdict(p).items()} \
            if hasattr(p, "__dataclass_fields__") else str(p)
    return {"id": context_id, "valid": ok, "parsed": parsed}
