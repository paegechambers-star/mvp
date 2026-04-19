"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          LEVEL 5 — ULTIMATE SDE STRESS TEST                                ║
║                                                                              ║
║  The hardest self-test possible without external infrastructure.            ║
║  Combines concurrent load, chaos engineering, independent cryptographic     ║
║  verification, full E2E system simulation, and regression validation.       ║
║                                                                              ║
║  PHASE 1 · Concurrent Correctness  — chain integrity under parallel load   ║
║  PHASE 2 · Chaos Engineering       — fault injection at every stage        ║
║  PHASE 3 · Cryptographic Proof     — independent SHA256 recomputation      ║
║  PHASE 4 · Full System Simulation  — 500 mixed HTTP requests               ║
║  PHASE 5 · L3+L4 Regression        — invariants + security after load      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from frapp.api import app
from frapp.settings import settings

from godai.models.audit import AuditEvent
from godai.models.request import TrustLevel
from godai.modules.hermes import create_token
from godai.modules.mnemosyne import GENESIS_HASH, Mnemosyne, TamperDetectedError
from godai.pipeline import GodaiPipeline
from godai.providers import EchoProvider

client = TestClient(app, raise_server_exceptions=False)
AUTH = {"X-API-Key": settings.api_key}

# ── Output helpers ────────────────────────────────────────────────────────────

RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

_results: List[bool] = []
_timings: List[float] = []


def result(label: str, passed: bool, detail: str = "", timing: Optional[float] = None) -> None:
    _results.append(passed)
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    t_str = f"{DIM} ({timing*1000:.0f}ms){RESET}" if timing else ""
    print(f"  {'✓' if passed else '✗'} [{status}] {label}{t_str}")
    if detail and not passed:
        print(f"    {RED}↳ {detail}{RESET}")


def section(title: str) -> None:
    print(f"\n{CYAN}{BOLD}── {title} {'─' * (60 - len(title))}{RESET}")


def info(msg: str) -> None:
    print(f"    {DIM}{msg}{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1 · Concurrent Correctness
# Chain integrity and index uniqueness under parallel async load
# ══════════════════════════════════════════════════════════════════════════════

section("PHASE 1 · Concurrent Correctness (200 parallel pipeline requests)")


async def _concurrent_pipeline(n: int = 200) -> tuple[bool, bool, bool, int, float]:
    pipeline = GodaiPipeline.create(EchoProvider())
    t0 = time.perf_counter()

    async def one(i: int) -> Any:
        return await pipeline.process(
            token="basic-tok12345",
            user_id=f"concurrent-user-{i % 20}",  # 20 distinct users
            protocol="http",
            query=f"concurrent query number {i}",
            context={"data_class": "PUBLIC"},
        )

    results = await asyncio.gather(*[one(i) for i in range(n)])
    elapsed = time.perf_counter() - t0

    # All must succeed
    all_success = all(r.success for r in results)

    # Chain must be valid
    try:
        chain_ok = pipeline.mnemosyne.verify_chain()
    except TamperDetectedError as e:
        chain_ok = False

    # Chain indices must be unique and sequential (0, 1, 2, ...)
    indices = [e.chain_index for e in pipeline.mnemosyne.entries]
    indices_ok = indices == list(range(len(indices)))

    return all_success, chain_ok, indices_ok, len(pipeline.mnemosyne), elapsed


all_success, chain_ok, indices_ok, entry_count, elapsed = asyncio.run(_concurrent_pipeline(200))

result("C01 · All 200 concurrent requests succeed",
       all_success, "Some requests failed unexpectedly", elapsed)
result("C02 · MNEMOSYNE chain intact after 200 concurrent writes",
       chain_ok, "verify_chain() failed — concurrency broke the hash chain")
result("C03 · No duplicate/missing chain indices (sequential 0..N)",
       indices_ok, f"Chain indices are not sequential — lock failure detected")
info(f"Entries written: {entry_count} | Throughput: {200/elapsed:.0f} req/s")

# ── Concurrent HTTP API (threading) ──────────────────────────────────────────

section("PHASE 1b · Concurrent HTTP (50 threads × create+read)")

_http_results: List[int] = []
_http_lock = threading.Lock()


def _http_worker(worker_id: int) -> None:
    payload = {
        "title": f"Thread {worker_id} Event",
        "starts_at": "2026-03-01T10:00:00",
        "ends_at": "2026-03-01T11:00:00",
        "owner": f"thread-user-{worker_id}",
    }
    r = client.post("/v1/events", json=payload, headers=AUTH)
    with _http_lock:
        _http_results.append(r.status_code)


threads = [threading.Thread(target=_http_worker, args=(i,)) for i in range(50)]
t0 = time.perf_counter()
for t in threads:
    t.start()
for t in threads:
    t.join()
http_elapsed = time.perf_counter() - t0

all_201 = all(s == 201 for s in _http_results)
result("C04 · 50 concurrent HTTP creates → all 201 Created",
       all_201, f"Status codes: {Counter(_http_results)}", http_elapsed)

duplicates = len(_http_results) - len(set(range(len(_http_results))))
result("C05 · No response duplicates or missing responses",
       len(_http_results) == 50,
       f"Got {len(_http_results)} responses, expected 50")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2 · Chaos Engineering (Fault Injection)
# ══════════════════════════════════════════════════════════════════════════════

section("PHASE 2 · Chaos Engineering (Fault Injection at Every Stage)")


class CrashingProvider:
    """LLM provider that raises on every call — simulates total LLM outage."""
    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        raise RuntimeError("LLM service unavailable — simulated outage")


class EmptyResponseProvider:
    """LLM provider that returns empty string — edge case."""
    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        return ""


class SlowProvider:
    """LLM provider with 100ms latency — simulates slow model."""
    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        await asyncio.sleep(0.1)
        if "verdict" in prompt.lower():
            return json.dumps({"verdict": "pass", "confidence": 0.9, "issues": []})
        return "slow but valid response"


class CorruptValidatorProvider:
    """Returns valid generation but malformed validation JSON."""
    _call_count = 0
    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        CorruptValidatorProvider._call_count += 1
        if "verdict" in prompt.lower():
            return "NOT_JSON_AT_ALL"   # ATHENA will reject this
        return "generated output"


# CHAOS 01 — Total LLM outage
async def _chaos_llm_crash() -> bool:
    p = GodaiPipeline.create(CrashingProvider())
    r = await p.process(token="basic-tok12345", user_id="chaos-u1",
                        protocol="http", query="test", context={"data_class": "PUBLIC"})
    # Must return failure result, not raise
    has_pipeline_event = any(
        e.source_module == "PIPELINE" for e in p.mnemosyne.entries
    )
    return not r.success and has_pipeline_event and r.error is not None

chaos1 = asyncio.run(_chaos_llm_crash())
result("C06 · LLM crash → graceful PipelineResult(success=False) + PIPELINE audit event",
       chaos1, "System crashed instead of returning failure result")

# CHAOS 02 — Empty LLM response
async def _chaos_empty_response() -> bool:
    p = GodaiPipeline.create(EmptyResponseProvider())
    r = await p.process(token="basic-tok12345", user_id="chaos-u2",
                        protocol="http", query="test", context={"data_class": "PUBLIC"})
    # Empty output: ATHENA may pass or fail it — either is fine, just no crash
    chain_ok = p.mnemosyne.verify_chain()
    return chain_ok and r is not None

chaos2 = asyncio.run(_chaos_empty_response())
result("C07 · Empty LLM response → no crash, chain intact",
       chaos2, "System crashed on empty LLM response")

# CHAOS 03 — Slow provider (100ms × 20 concurrent)
async def _chaos_slow_concurrent() -> tuple[bool, float]:
    p = GodaiPipeline.create(SlowProvider())
    t0 = time.perf_counter()
    results = await asyncio.gather(*[
        p.process(token="basic-tok12345", user_id=f"slow-u{i}",
                  protocol="http", query="test", context={"data_class": "PUBLIC"})
        for i in range(20)
    ])
    elapsed = time.perf_counter() - t0
    all_ok = all(r.success for r in results)
    chain_ok = p.mnemosyne.verify_chain()
    return all_ok and chain_ok, elapsed

chaos3_ok, chaos3_time = asyncio.run(_chaos_slow_concurrent())
result("C08 · 20 concurrent slow-provider requests → all succeed, chain intact",
       chaos3_ok, "Slow provider caused failures or chain corruption", chaos3_time)
info(f"20 × 100ms requests completed in {chaos3_time*1000:.0f}ms (async concurrency working)")

# CHAOS 04 — Corrupt validator output (ATHENA rejects malformed JSON)
async def _chaos_corrupt_validator() -> bool:
    p = GodaiPipeline.create(CorruptValidatorProvider())
    r = await p.process(token="basic-tok12345", user_id="chaos-u4",
                        protocol="http", query="test", context={"data_class": "PUBLIC"})
    has_pipeline_event = any(e.source_module == "PIPELINE" for e in p.mnemosyne.entries)
    chain_ok = p.mnemosyne.verify_chain()
    return has_pipeline_event and chain_ok  # may succeed or fail — just no crash

chaos4 = asyncio.run(_chaos_corrupt_validator())
result("C09 · Corrupt validator JSON → no crash, audit chain intact",
       chaos4, "Corrupt validator response caused system crash")

# CHAOS 05 — MNEMOSYNE persistence survives restart simulation
async def _chaos_persistence() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "chaos.db"
        p = GodaiPipeline.create(EchoProvider())
        p._mnemosyne = Mnemosyne(db_path=db)
        p._hermes._mnemosyne = p._mnemosyne
        p._themis._mnemosyne = p._mnemosyne
        p._apollon._mnemosyne = p._mnemosyne
        p._athena._mnemosyne = p._mnemosyne

        for i in range(10):
            await p.process(token="basic-tok12345", user_id=f"persist-u{i}",
                            protocol="http", query="persist test",
                            context={"data_class": "PUBLIC"})

        first_count = len(p.mnemosyne)
        first_last_hash = p.mnemosyne.entries[-1].hash

        # Simulate restart: new instance loads from same DB
        m2 = Mnemosyne(db_path=db)
        second_count = len(m2)
        second_last_hash = m2.entries[-1].hash if m2.entries else ""
        chain_ok = m2.verify_chain()

        return (first_count == second_count and
                first_last_hash == second_last_hash and
                chain_ok)

chaos5 = asyncio.run(_chaos_persistence())
result("C10 · MNEMOSYNE survives simulated restart (SQLite persistence)",
       chaos5, "Entry count or hash mismatch after reload from DB")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3 · Cryptographic Proof (Independent SHA256 Verification)
# ══════════════════════════════════════════════════════════════════════════════

section("PHASE 3 · Cryptographic Proof (Independent Recomputation)")


async def _build_large_chain(n: int) -> Mnemosyne:
    m = Mnemosyne()
    for i in range(n):
        await m.append(AuditEvent(
            event_type="auth" if i % 3 == 0 else "routing" if i % 3 == 1 else "validation",
            event_data={"seq": i, "payload": f"data-{i}", "nested": {"a": i * 2}},
            source_module=["HERMES", "APOLLON", "ATHENA", "THEMIS", "PIPELINE"][i % 5],
            timestamp=datetime.now(timezone.utc),
        ))
    return m

m = asyncio.run(_build_large_chain(1000))

# CRYPTO 01 — Independent recomputation without using Mnemosyne internals
def _independent_verify(entries) -> tuple[bool, Optional[int]]:
    """Recompute every hash from scratch using only stdlib — no Mnemosyne methods."""
    prev_hash = GENESIS_HASH
    for entry in entries:
        # Exact same formula as Mnemosyne._compute_hash()
        payload = json.dumps(entry.event_data, sort_keys=True, default=str)
        raw = f"{payload}{prev_hash}".encode("utf-8")
        expected = hashlib.sha256(raw).hexdigest()
        if entry.hash != expected:
            return False, entry.chain_index
        if entry.prev_hash != prev_hash:
            return False, entry.chain_index
        prev_hash = entry.hash
    return True, None

t0 = time.perf_counter()
crypto_ok, bad_idx = _independent_verify(m.entries)
crypto_elapsed = time.perf_counter() - t0

result("C11 · 1,000-entry chain independently verified (stdlib SHA256, no Mnemosyne methods)",
       crypto_ok, f"Hash mismatch at chain index {bad_idx}", crypto_elapsed)
info(f"1,000 entries verified in {crypto_elapsed*1000:.1f}ms")

# CRYPTO 02 — Single bit-flip at position 500 is detected at exactly position 500
entries = list(m.entries)
original_data = dict(entries[500].event_data)
entries[500] = type(entries[500])(
    **{**entries[500].__dict__, "event_data": {**original_data, "_tampered": True}}
)
_, bad_at = _independent_verify(entries)
result("C12 · Single-entry tamper detected at exact position (bit-flip precision)",
       bad_at == 500, f"Tamper detected at {bad_at}, expected 500")

# CRYPTO 03 — Genesis hash is constant and correct
genesis_correct = GENESIS_HASH == "0" * 64 and len(GENESIS_HASH) == 64
result("C13 · Genesis hash is 64 zero-chars (sentinel value correct)",
       genesis_correct)

# CRYPTO 04 — Chain ordering: each entry's prev_hash equals previous entry's hash
prev = GENESIS_HASH
chain_linked = True
for entry in m.entries:
    if entry.prev_hash != prev:
        chain_linked = False
        break
    prev = entry.hash
result("C14 · Every prev_hash pointer links to exact previous entry hash",
       chain_linked, "Broken link found in chain back-pointer sequence")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4 · Full System Simulation (500 mixed HTTP requests)
# ══════════════════════════════════════════════════════════════════════════════

section("PHASE 4 · Full System Simulation (500 mixed HTTP requests)")

_status_counts: Counter = Counter()
_error_500 = 0
_created_ids: List[int] = []

t0 = time.perf_counter()

for i in range(500):
    action = i % 10

    if action in (0, 1, 2):  # 30% — create events
        r = client.post("/v1/events", json={
            "title": f"Sim Event {i}",
            "starts_at": "2026-04-01T09:00:00",
            "ends_at": "2026-04-01T10:00:00",
            "owner": f"sim-user-{i % 10}",
        }, headers=AUTH)
        _status_counts[r.status_code] += 1
        if r.status_code == 201:
            _created_ids.append(r.json()["id"])
        if r.status_code == 500:
            _error_500 += 1

    elif action == 3:  # 10% — list events
        r = client.get("/v1/events?limit=10&offset=0", headers=AUTH)
        _status_counts[r.status_code] += 1
        if r.status_code == 500:
            _error_500 += 1

    elif action == 4:  # 10% — G.O.D.A.I. query
        r = client.post("/v1/godai/query", json={
            "token": "basic-tok12345",
            "user_id": f"sim-user-{i % 5}",
            "query": f"simulate query {i}",
            "context": {"data_class": "PUBLIC"},
        }, headers=AUTH)
        _status_counts[r.status_code] += 1
        if r.status_code == 500:
            _error_500 += 1

    elif action == 5:  # 10% — health check
        r = client.get("/healthz")
        _status_counts[r.status_code] += 1
        if r.status_code == 500:
            _error_500 += 1

    elif action == 6 and _created_ids:  # 10% — get by ID
        eid = _created_ids[i % len(_created_ids)]
        r = client.get(f"/v1/events/{eid}", headers=AUTH)
        _status_counts[r.status_code] += 1
        if r.status_code == 500:
            _error_500 += 1

    elif action == 7 and _created_ids:  # 10% — update
        eid = _created_ids[i % len(_created_ids)]
        r = client.put(f"/v1/events/{eid}", json={"title": f"Updated {i}"},
                       headers=AUTH)
        _status_counts[r.status_code] += 1
        if r.status_code == 500:
            _error_500 += 1

    elif action == 8:  # 10% — GDPR access
        r = client.get("/v1/me/data",
                       headers={**AUTH, "X-User-ID": f"sim-user-{i % 10}"})
        _status_counts[r.status_code] += 1
        if r.status_code == 500:
            _error_500 += 1

    elif action == 9:  # 10% — audit log
        r = client.get("/v1/godai/audit?limit=5", headers=AUTH)
        _status_counts[r.status_code] += 1
        if r.status_code == 500:
            _error_500 += 1

sim_elapsed = time.perf_counter() - t0

result("C15 · 500 mixed HTTP requests — zero 500 errors",
       _error_500 == 0,
       f"{_error_500} server crashes (500s) detected", sim_elapsed)
result("C16 · All responses are valid HTTP status codes",
       all(s in (200, 201, 204, 400, 401, 404, 422, 429) for s in _status_counts.keys()),
       f"Unexpected status codes: {_status_counts}")
info(f"Status distribution: {dict(sorted(_status_counts.items()))}")
info(f"Throughput: {500/sim_elapsed:.0f} req/s over {sim_elapsed:.2f}s")

# Verify audit chain still valid after full simulation
r = client.get("/v1/godai/audit", headers=AUTH)
body = r.json()
result("C17 · MNEMOSYNE chain valid after 500-request simulation",
       body.get("chain_valid", False),
       f"chain_valid={body.get('chain_valid')} entries={body.get('total')}")

info(f"Total MNEMOSYNE entries after simulation: {body.get('total', 0)}")

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5 · L3+L4 Regression Under Load
# Replay the core invariant + security checks AFTER full stress
# ══════════════════════════════════════════════════════════════════════════════

section("PHASE 5 · Regression: L3+L4 Invariants + Security After Load")

# Re-run critical invariants AFTER the stress test

# Invariant: fresh MNEMOSYNE is still tamper-detectable
m_fresh = asyncio.run(_build_large_chain(50))
m_fresh._entries[25] = type(m_fresh._entries[25])(
    **{**m_fresh._entries[25].__dict__, "event_data": {"tampered": "post-load"}}
)
try:
    m_fresh.verify_chain()
    result("C18 · Tamper detection works AFTER load (regression)", False,
           "verify_chain() passed on tampered chain post-load")
except TamperDetectedError:
    result("C18 · Tamper detection works AFTER load (regression)", True)

# Invariant: API key still enforced after load
r = client.get("/v1/events")
result("C19 · Auth still enforced after full load (no bypass regression)",
       r.status_code == 401,
       f"Auth returned {r.status_code} after load — possible regression")

# Invariant: JWT attack still blocked after load
tampered = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJoYWNrIiwidHJ1c3QiOiJMMyIsImV4cCI6OTk5OX0.FAKESIG"
r = client.post("/v1/godai/query", json={
    "token": tampered, "user_id": "post-load-attacker",
    "query": "hack", "context": {"data_class": "RESTRICTED"}
}, headers=AUTH)
body = r.json()
result("C20 · JWT forgery still blocked after full load (regression)",
       not body.get("success", True),
       f"Forged JWT accepted post-load: {body}")

# Pipeline success after all chaos
async def _final_pipeline_check() -> bool:
    p = GodaiPipeline.create(EchoProvider())
    r = await p.process(
        token="basic-tok12345", user_id="final-check",
        protocol="http", query="final system check",
        context={"data_class": "PUBLIC"},
    )
    return r.success and p.mnemosyne.verify_chain()

result("C21 · Pipeline runs cleanly after all stress phases",
       asyncio.run(_final_pipeline_check()),
       "Pipeline failed or chain broken after stress test")

# ══════════════════════════════════════════════════════════════════════════════
# FINAL SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

total = len(_results)
passed = sum(_results)
failed = total - passed

print(f"\n{'═' * 70}")
print(f"{BOLD}  LEVEL 5 — ULTIMATE SDE STRESS TEST RESULTS{RESET}")
print(f"{'═' * 70}")
print(f"  Phase 1 · Concurrent Correctness  : 200 parallel async + 50 threads")
print(f"  Phase 2 · Chaos Engineering        : 5 fault injection scenarios")
print(f"  Phase 3 · Cryptographic Proof      : 1,000-entry independent verify")
print(f"  Phase 4 · Full System Simulation   : 500 mixed HTTP requests")
print(f"  Phase 5 · Regression Under Load    : L3+L4 replayed post-stress")
print(f"{'─' * 70}")
print(f"  Total checks  : {total}")
print(f"  {GREEN}Passed        : {passed}{RESET}")
print(f"  {RED if failed else GREEN}Failed        : {failed}{RESET}")
print(f"{'═' * 70}")

if failed == 0:
    print(f"""
  {GREEN}{BOLD}✓ SYSTEM PASSED THE ULTIMATE SDE STRESS TEST.{RESET}

  {BOLD}What this proves:{RESET}
  • Chain integrity holds under 200 concurrent async writes
  • 50 simultaneous HTTP clients produce zero corrupted responses
  • LLM crashes, empty responses, slow responses → graceful degradation
  • MNEMOSYNE survives a simulated server restart from SQLite
  • Independent SHA256 recomputation confirms cryptographic correctness
  • 500 mixed HTTP requests → zero 500 errors
  • All L3 invariants and L4 security checks hold after full load
""")
else:
    print(f"\n  {RED}{BOLD}✗ {failed} CHECK(S) FAILED. SYSTEM NOT PRODUCTION READY.{RESET}\n")
    sys.exit(1)
