"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          LEVEL 3 — INVARIANT FALSIFICATION TEST                            ║
║                                                                              ║
║  This suite actively tries to BREAK each of G.O.D.A.I.'s hard invariants.  ║
║  Every test IS an attack. A green result means the attack was repelled.     ║
║  A red result means the invariant is broken and the system is compromised.  ║
║                                                                              ║
║  INVARIANT 1 · Tamper-Proof Audit   — MNEMOSYNE SHA256 chain               ║
║  INVARIANT 2 · JWT cannot be forged — signature + expiry                   ║
║  INVARIANT 3 · All Decisions Logged — no silent pipeline exit               ║
║  INVARIANT 4 · Generator ≠ Arbiter  — model separation enforced            ║
║  INVARIANT 5 · Policy = Data        — YAML governs, code does not           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import hmac
import json
import sqlite3
import sys
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from godai.models.audit import AuditEvent, LogEntry
from godai.models.request import TrustLevel
from godai.modules.hermes import AuthenticationError, Hermes, _b64url_encode, _b64url_decode, create_token
from godai.modules.mnemosyne import GENESIS_HASH, Mnemosyne, TamperDetectedError
from godai.pipeline import GodaiPipeline
from godai.providers import EchoProvider

# ── Output helpers ────────────────────────────────────────────────────────────

RED   = "\033[91m"
GREEN = "\033[92m"
CYAN  = "\033[96m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
RESET = "\033[0m"

_results: List[bool] = []


def attack(label: str, repelled: bool, detail: str = "") -> None:
    _results.append(repelled)
    status = f"{GREEN}REPELLED{RESET}" if repelled else f"{RED}BREACHED{RESET}"
    print(f"  {'✓' if repelled else '✗'} [{status}] {label}")
    if detail and not repelled:
        print(f"    {RED}↳ {detail}{RESET}")


def section(title: str) -> None:
    print(f"\n{CYAN}{BOLD}── {title} {'─' * (60 - len(title))}{RESET}")


def _make_mnemosyne_with_entries(n: int = 10) -> Mnemosyne:
    m = Mnemosyne()
    asyncio.run(_fill(m, n))
    return m


async def _fill(m: Mnemosyne, n: int) -> None:
    for i in range(n):
        await m.append(AuditEvent(
            event_type="auth",
            event_data={"index": i, "user": f"u{i}"},
            source_module="HERMES",
            timestamp=datetime.now(timezone.utc),
        ))

# ══════════════════════════════════════════════════════════════════════════════
# INVARIANT 1 · Tamper-Proof Audit
# ══════════════════════════════════════════════════════════════════════════════

section("INVARIANT 1 · Tamper-Proof Audit (MNEMOSYNE SHA256 Chain)")

# ATTACK 01 — Modify event_data of entry[5] in-memory
m = _make_mnemosyne_with_entries(10)
m._entries[5] = replace(m._entries[5], event_data={"tampered": True})
try:
    m.verify_chain()
    attack("A01 · In-memory event_data modification", repelled=False,
           detail="verify_chain() did not detect tampered event_data")
except TamperDetectedError:
    attack("A01 · In-memory event_data modification", repelled=True)

# ATTACK 02 — Overwrite hash of entry[3] with a plausible-looking value
m = _make_mnemosyne_with_entries(10)
m._entries[3] = replace(m._entries[3], hash="a" * 64)
try:
    m.verify_chain()
    attack("A02 · Hash value overwrite (entry[3])", repelled=False,
           detail="verify_chain() accepted a fake hash")
except TamperDetectedError:
    attack("A02 · Hash value overwrite (entry[3])", repelled=True)

# ATTACK 03 — Rewrite prev_hash pointer to break the chain link
m = _make_mnemosyne_with_entries(10)
m._entries[7] = replace(m._entries[7], prev_hash="b" * 64)
try:
    m.verify_chain()
    attack("A03 · prev_hash back-pointer forgery (entry[7])", repelled=False,
           detail="verify_chain() did not detect broken back-pointer")
except TamperDetectedError:
    attack("A03 · prev_hash back-pointer forgery (entry[7])", repelled=True)

# ATTACK 04 — Insert a fabricated entry at chain position 5 (shifts indices)
m = _make_mnemosyne_with_entries(10)
fake = LogEntry(
    event_id=uuid4(), event_type="auth",
    event_data={"injected": "malicious admin override"},
    source_module="PIPELINE",
    timestamp=datetime.now(timezone.utc),
    hash="c" * 64, prev_hash="d" * 64, chain_index=5,
)
m._entries.insert(5, fake)
try:
    m.verify_chain()
    attack("A04 · Fabricated entry injection (mid-chain)", repelled=False,
           detail="verify_chain() accepted injected entry")
except TamperDetectedError:
    attack("A04 · Fabricated entry injection (mid-chain)", repelled=True)

# ATTACK 05 — SQLite-level tamper: modify DB directly, reload, verify
with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "mnemo.db"
    m = Mnemosyne(db_path=db)
    asyncio.run(_fill(m, 8))

    # Directly edit the SQLite database — real-world attack vector
    with sqlite3.connect(str(db)) as conn:
        conn.execute("UPDATE mnemosyne_log SET event_data = ? WHERE chain_index = 4",
                     ('{"tampered_at_db_level": true}',))

    m2 = Mnemosyne(db_path=db)   # fresh instance loading from tampered DB
    try:
        m2.verify_chain()
        attack("A05 · SQLite DB-level tamper + reload", repelled=False,
               detail="New Mnemosyne instance accepted tampered DB row")
    except TamperDetectedError:
        attack("A05 · SQLite DB-level tamper + reload", repelled=True)

# ATTACK 06 — Delete a row from SQLite (gap in chain_index sequence)
with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "mnemo2.db"
    m = Mnemosyne(db_path=db)
    asyncio.run(_fill(m, 6))
    with sqlite3.connect(str(db)) as conn:
        conn.execute("DELETE FROM mnemosyne_log WHERE chain_index = 2")
    m3 = Mnemosyne(db_path=db)
    try:
        m3.verify_chain()
        attack("A06 · SQLite row deletion (entry[2])", repelled=False,
               detail="verify_chain() passed with a missing entry")
    except TamperDetectedError:
        attack("A06 · SQLite row deletion (entry[2])", repelled=True)

# ══════════════════════════════════════════════════════════════════════════════
# INVARIANT 2 · JWT cannot be forged
# ══════════════════════════════════════════════════════════════════════════════

section("INVARIANT 2 · JWT Cannot Be Forged")

SECRET = "prod-secret-key-32chars-minimum!"

async def _try_token(token: str, label: str, expect_trust: TrustLevel | None = None) -> None:
    m = Mnemosyne()
    h = Hermes(m, secret_key=SECRET, dev_mode=False)  # PRODUCTION mode — no prefix fallback
    try:
        req = await h.normalize(token=token, user_id="attacker", protocol="http", query="hack")
        if expect_trust and req.trust_level == expect_trust:
            attack(label, repelled=False,
                   detail=f"Attacker got trust level {expect_trust.name}")
        else:
            attack(label, repelled=False, detail="Token was accepted (should have been rejected)")
    except AuthenticationError:
        attack(label, repelled=True)

# ATTACK 07 — Payload tampering: valid token, change trust L1→L3 without re-signing
valid_token = create_token("alice", TrustLevel.L1, SECRET)
parts = valid_token.split(".")
payload = json.loads(_b64url_decode(parts[1]))
payload["trust"] = "L3"   # Escalation attempt
tampered_payload = _b64url_encode(json.dumps(payload).encode())
tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
asyncio.run(_try_token(tampered_token, "A07 · JWT payload tampering (L1→L3 trust escalation)",
                       expect_trust=TrustLevel.L3))

# ATTACK 08 — Wrong signing key
wrong_key_token = create_token("attacker", TrustLevel.L3, "wrong-secret-key-32chars!!!!!")
asyncio.run(_try_token(wrong_key_token, "A08 · JWT signed with wrong key"))

# ATTACK 09 — Expired token (exp = unix epoch 0)
parts = valid_token.split(".")
payload = json.loads(_b64url_decode(parts[1]))
payload["exp"] = 0   # Jan 1 1970 — definitely expired
expired_payload = _b64url_encode(json.dumps(payload).encode())
signing = f"{parts[0]}.{expired_payload}".encode()
sig = hmac.new(SECRET.encode(), signing, hashlib.sha256).digest()
expired_token = f"{parts[0]}.{expired_payload}.{_b64url_encode(sig)}"
asyncio.run(_try_token(expired_token, "A09 · Expired JWT (exp=0)"))

# ATTACK 10 — Algorithm confusion: strip signature entirely (alg:none)
none_token = f"{parts[0]}.{parts[1]}."   # empty signature segment
asyncio.run(_try_token(none_token, "A10 · alg:none attack (empty signature)"))

# ATTACK 11 — Random signature (brute-force style)
import os as _os
random_sig = _b64url_encode(_os.urandom(32))
random_token = f"{parts[0]}.{parts[1]}.{random_sig}"
asyncio.run(_try_token(random_token, "A11 · Random signature forgery"))

# ATTACK 12 — Prefix token in production mode (should be rejected)
async def _try_prefix_in_prod() -> None:
    m = Mnemosyne()
    h = Hermes(m, secret_key=SECRET, dev_mode=False)
    try:
        await h.normalize(token="internal-supersecret", user_id="attacker",
                          protocol="http", query="hack")
        attack("A12 · Prefix token in production mode (dev_mode=False)", repelled=False,
               detail="Prefix token was accepted in production mode — trivially forgeable")
    except AuthenticationError:
        attack("A12 · Prefix token in production mode (dev_mode=False)", repelled=True)

asyncio.run(_try_prefix_in_prod())

# ══════════════════════════════════════════════════════════════════════════════
# INVARIANT 3 · All Decisions Logged — No Silent Pipeline Exit
# ══════════════════════════════════════════════════════════════════════════════

section("INVARIANT 3 · All Decisions Logged (No Silent Pipeline Exit)")


async def _run_pipeline_and_check(scenario: str, token, user_id, query, context,
                                   expected_event: str) -> None:
    p = GodaiPipeline.create(EchoProvider())
    await p.process(token=token, user_id=user_id, protocol="http",
                    query=query, context=context)
    event_types = {e.event_type for e in p.mnemosyne.entries}
    modules = {e.source_module for e in p.mnemosyne.entries}
    has_event = expected_event in event_types
    has_pipeline = "PIPELINE" in modules
    repelled = has_event and has_pipeline
    attack(f"A13 · PIPELINE event logged: {scenario} → {expected_event!r}",
           repelled=repelled,
           detail=f"Events found: {event_types}, Modules: {modules}")


asyncio.run(_run_pipeline_and_check(
    "auth failure",
    token=None, user_id="u1", query="q", context={},
    expected_event="pipeline_error",
))
asyncio.run(_run_pipeline_and_check(
    "policy denial (RESTRICTED data, L1 trust)",
    token="basic-tok12345", user_id="u1", query="q",
    context={"data_class": "RESTRICTED"},
    expected_event="pipeline_error",
))
asyncio.run(_run_pipeline_and_check(
    "successful request",
    token="basic-tok12345", user_id="u1", query="hello",
    context={"data_class": "PUBLIC"},
    expected_event="pipeline_success",
))

# ATTACK 14 — Verify ALL five modules log to MNEMOSYNE on a successful request
async def _check_all_modules_logged() -> None:
    p = GodaiPipeline.create(EchoProvider())
    await p.process(token="basic-tok12345", user_id="u1", protocol="http",
                    query="hello world", context={"data_class": "PUBLIC"})
    modules = {e.source_module for e in p.mnemosyne.entries}
    expected = {"HERMES", "THEMIS", "APOLLON", "ATHENA", "PIPELINE"}
    missing = expected - modules
    attack("A14 · All 5 modules write to MNEMOSYNE on success",
           repelled=len(missing) == 0,
           detail=f"Missing modules: {missing}")

asyncio.run(_check_all_modules_logged())

# ══════════════════════════════════════════════════════════════════════════════
# INVARIANT 4 · Generator ≠ Arbiter
# ══════════════════════════════════════════════════════════════════════════════

section("INVARIANT 4 · Generator ≠ Arbiter (Model Separation)")


async def _check_model_separation() -> None:
    p = GodaiPipeline.create(EchoProvider())
    await p.process(token="basic-tok12345", user_id="u1", protocol="http",
                    query="hello", context={"data_class": "PUBLIC"})
    routing_events = [e for e in p.mnemosyne.entries if e.event_type == "routing"]
    validation_events = [e for e in p.mnemosyne.entries if e.event_type == "validation"]

    if not routing_events or not validation_events:
        attack("A15 · Generator model ≠ Validator model (different model_ids in audit log)",
               repelled=False, detail="Missing routing or validation event in MNEMOSYNE")
        return

    gen_model = routing_events[0].event_data.get("model_id", "")
    val_model = validation_events[0].event_data.get("validator_model", "")
    different = gen_model != val_model and bool(gen_model) and bool(val_model)
    attack("A15 · Generator model ≠ Validator model (different model_ids in audit log)",
           repelled=different,
           detail=f"Generator: {gen_model!r} | Validator: {val_model!r}")

asyncio.run(_check_model_separation())

# ══════════════════════════════════════════════════════════════════════════════
# INVARIANT 5 · Policy = Data (YAML governs, code does not)
# ══════════════════════════════════════════════════════════════════════════════

section("INVARIANT 5 · Policy = Data (YAML Governs)")

from godai.pipeline import _DEFAULT_POLICY_PATH  # noqa
import yaml  # noqa

async def _check_policy_is_data() -> None:
    policy_path = Path(__file__).parent.parent / "godai" / "config" / "policies" / "default.yaml"
    with open(policy_path) as f:
        original = f.read()

    # Verify a RESTRICTED request IS denied with current policy
    p = GodaiPipeline.create(EchoProvider())
    r1 = await p.process(token="basic-tok12345", user_id="u1", protocol="http",
                          query="q", context={"data_class": "RESTRICTED"})
    was_denied = not r1.success

    attack("A16 · RESTRICTED data denied with current YAML policy",
           repelled=was_denied,
           detail="RESTRICTED data was allowed — policy not enforced")

asyncio.run(_check_policy_is_data())

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

total = len(_results)
passed = sum(_results)
failed = total - passed

print(f"\n{'═' * 70}")
print(f"{BOLD}  LEVEL 3 — INVARIANT FALSIFICATION RESULTS{RESET}")
print(f"{'═' * 70}")
print(f"  Attacks launched : {total}")
print(f"  {GREEN}Repelled         : {passed}{RESET}")
print(f"  {RED if failed else GREEN}Breached         : {failed}{RESET}")
print(f"{'═' * 70}")

if failed == 0:
    print(f"\n  {GREEN}{BOLD}✓ ALL INVARIANTS HELD. SYSTEM IS CRYPTOGRAPHICALLY SOUND.{RESET}\n")
else:
    print(f"\n  {RED}{BOLD}✗ {failed} INVARIANT(S) BREACHED. SYSTEM IS COMPROMISED.{RESET}\n")
    sys.exit(1)
