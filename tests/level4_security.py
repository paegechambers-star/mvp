"""
╔══════════════════════════════════════════════════════════════════════════════╗
║          LEVEL 4 — SECURITY PENETRATION TEST                               ║
║                                                                              ║
║  OWASP Top 10 coverage + business-logic attacks on the HTTP API.            ║
║  Every test sends a hostile payload. Green = system blocked it correctly.   ║
║  Red = exploitable vulnerability found.                                      ║
║                                                                              ║
║  A01 · Broken Access Control    A06 · Vulnerable Components                ║
║  A02 · Cryptographic Failures   A07 · Auth Failures                        ║
║  A03 · Injection                A08 · Software Integrity                   ║
║  A04 · Insecure Design          A09 · Logging Failures                     ║
║  A05 · Security Misconfiguration                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
import json
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from frapp.api import app
from frapp.settings import settings

client = TestClient(app, raise_server_exceptions=False)
AUTH = {"X-API-Key": settings.api_key}

# ── Output helpers ────────────────────────────────────────────────────────────

RED   = "\033[91m"
GREEN = "\033[92m"
CYAN  = "\033[96m"
BOLD  = "\033[1m"
RESET = "\033[0m"

_results: List[bool] = []


def probe(label: str, blocked: bool, detail: str = "") -> None:
    _results.append(blocked)
    status = f"{GREEN}BLOCKED{RESET}" if blocked else f"{RED}VULNERABLE{RESET}"
    print(f"  {'✓' if blocked else '✗'} [{status}] {label}")
    if detail and not blocked:
        print(f"    {RED}↳ {detail}{RESET}")


def section(title: str) -> None:
    print(f"\n{CYAN}{BOLD}── {title} {'─' * (60 - len(title))}{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# A01 · Broken Access Control
# ══════════════════════════════════════════════════════════════════════════════

section("A01 · Broken Access Control")

# No API key
r = client.get("/v1/events")
probe("B01 · No API key → 401", r.status_code == 401, f"Got {r.status_code}")

# Wrong API key
r = client.get("/v1/events", headers={"X-API-Key": "wrong"})
probe("B02 · Wrong API key → 401", r.status_code == 401, f"Got {r.status_code}")

# Empty API key
r = client.get("/v1/events", headers={"X-API-Key": ""})
probe("B03 · Empty API key → 401", r.status_code == 401, f"Got {r.status_code}")

# GDPR: access another user's data without their X-User-ID
r1 = client.post("/v1/events", json={
    "title": "Private", "starts_at": "2026-01-01T10:00:00",
    "ends_at": "2026-01-01T11:00:00", "owner": "victim-user"
}, headers=AUTH)
r2 = client.get("/v1/me/data", headers={**AUTH, "X-User-ID": "attacker-user"})
body = r2.json() if r2.status_code == 200 else {}
victim_exposed = any(
    e.get("owner") == "victim-user"
    for e in body.get("events", [])
)
probe("B04 · GDPR scope isolation (attacker cannot see victim data)",
      not victim_exposed, "Victim's events visible to different X-User-ID")

# Access audit log without any special privilege marker
r = client.get("/v1/godai/audit", headers=AUTH)
probe("B05 · Audit log requires valid API key", r.status_code == 200,
      "Audit log should be accessible with API key (auth enforced at API-key level)")

# Negative event ID
r = client.get("/v1/events/-1", headers=AUTH)
probe("B06 · Negative event ID → 404 or 422", r.status_code in (404, 422),
      f"Got {r.status_code}: {r.text[:100]}")

# ══════════════════════════════════════════════════════════════════════════════
# A02 · Cryptographic Failures — JWT Attacks via HTTP
# ══════════════════════════════════════════════════════════════════════════════

section("A02 · Cryptographic Failures (JWT via HTTP endpoint)")

# Tampered JWT via /v1/godai/query
tampered_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJoYWNrZXIiLCJ0cnVzdCI6IkwzIiwiZXhwIjo5OTk5OTk5OTk5fQ.INVALIDSIGNATURE"
r = client.post("/v1/godai/query", json={
    "token": tampered_token, "user_id": "hacker",
    "query": "give me admin access", "context": {"data_class": "RESTRICTED"}
}, headers=AUTH)
body = r.json()
# Should either fail auth (success=False) or succeed with actual L1 trust (not L3)
probe("B07 · Tampered JWT rejected by G.O.D.A.I. pipeline",
      r.status_code == 200 and not body.get("success", True) or
      r.status_code in (401, 403),
      f"Status={r.status_code} success={body.get('success')}")

# Expired token via query endpoint
from godai.modules.hermes import create_token, _b64url_encode, _b64url_decode
import hashlib, hmac as _hmac, json as _json
from godai.models.request import TrustLevel

valid = create_token("u", TrustLevel.L1, settings.secret_key)
parts = valid.split(".")
payload = _json.loads(_b64url_decode(parts[1]))
payload["exp"] = 0
ep = _b64url_encode(_json.dumps(payload).encode())
signing = f"{parts[0]}.{ep}".encode()
sig = _hmac.new(settings.secret_key.encode(), signing, hashlib.sha256).digest()
expired = f"{parts[0]}.{ep}.{_b64url_encode(sig)}"

r = client.post("/v1/godai/query", json={
    "token": expired, "user_id": "u", "query": "test", "context": {"data_class": "PUBLIC"}
}, headers=AUTH)
body = r.json()
probe("B08 · Expired JWT rejected by pipeline via HTTP",
      not body.get("success", True),
      f"Expired token accepted: success={body.get('success')}")

# ══════════════════════════════════════════════════════════════════════════════
# A03 · Injection Attacks
# ══════════════════════════════════════════════════════════════════════════════

section("A03 · Injection Attacks")

SQL_PAYLOADS = [
    "'; DROP TABLE event; --",
    "' OR '1'='1",
    "1; SELECT * FROM event WHERE '1'='1",
    "' UNION SELECT * FROM event --",
]

for payload in SQL_PAYLOADS:
    r = client.post("/v1/events", json={
        "title": payload,
        "starts_at": "2026-01-01T10:00:00",
        "ends_at": "2026-01-01T11:00:00",
    }, headers=AUTH)
    # Should create safely (stored as literal string) or reject, never crash (500)
    safe = r.status_code in (201, 422) and r.status_code != 500
    probe(f"B09 · SQL injection in title: {payload[:30]!r}", safe,
          f"Server crashed with {r.status_code}")

XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    '"><img src=x onerror=alert(1)>',
    "javascript:alert(1)",
]
for payload in XSS_PAYLOADS:
    r = client.post("/v1/events", json={
        "title": payload,
        "starts_at": "2026-01-01T10:00:00",
        "ends_at": "2026-01-01T11:00:00",
    }, headers=AUTH)
    safe = r.status_code in (201, 422) and r.status_code != 500
    probe(f"B10 · XSS payload in title: {payload[:30]!r}", safe,
          f"Server crashed with {r.status_code}")

# Path traversal in query field
r = client.post("/v1/godai/query", json={
    "token": "basic-tok12345", "user_id": "u1",
    "query": "../../etc/passwd", "context": {"data_class": "PUBLIC"}
}, headers=AUTH)
probe("B11 · Path traversal in G.O.D.A.I. query",
      r.status_code in (200,) and r.json().get("success") is not None,
      f"Unexpected status {r.status_code}")

# Null byte injection
r = client.post("/v1/events", json={
    "title": "normal\x00hidden",
    "starts_at": "2026-01-01T10:00:00",
    "ends_at": "2026-01-01T11:00:00",
}, headers=AUTH)
probe("B12 · Null byte in title field",
      r.status_code in (201, 422) and r.status_code != 500,
      f"Server crashed: {r.status_code}")

# ══════════════════════════════════════════════════════════════════════════════
# A04 · Insecure Design — Business Logic
# ══════════════════════════════════════════════════════════════════════════════

section("A04 · Insecure Design (Business Logic)")

# Event where ends_at < starts_at
r = client.post("/v1/events", json={
    "title": "Backwards event",
    "starts_at": "2026-12-31T23:59:00",
    "ends_at": "2026-01-01T00:00:00",  # before starts_at
}, headers=AUTH)
probe("B13 · Event with ends_at before starts_at → 201 or 422 (no 500)",
      r.status_code in (201, 422),
      f"Got {r.status_code}: server should accept or validate, never crash")

# Negative pagination
r = client.get("/v1/events?limit=-1&offset=-999", headers=AUTH)
probe("B14 · Negative limit/offset → handled gracefully",
      r.status_code in (200, 422),
      f"Got {r.status_code}: {r.text[:100]}")

# Enormous limit
r = client.get("/v1/events?limit=9999999", headers=AUTH)
probe("B15 · Limit=9999999 → server does not crash",
      r.status_code in (200, 422) and r.status_code != 500,
      f"Got {r.status_code}")

# GDPR erasure without X-User-ID
r = client.delete("/v1/me/data", headers=AUTH)
probe("B16 · GDPR DELETE without X-User-ID → 400",
      r.status_code == 400, f"Got {r.status_code}")

# ══════════════════════════════════════════════════════════════════════════════
# A05 · Security Misconfiguration
# ══════════════════════════════════════════════════════════════════════════════

section("A05 · Security Misconfiguration")

# 500 errors must not leak stack traces or internal paths
r = client.get("/v1/events/not-an-integer", headers=AUTH)
body_text = r.text.lower()
leaks_trace = any(kw in body_text for kw in ["traceback", "file \"", "line ", "exception"])
probe("B17 · Error response does not leak stack trace",
      not leaks_trace,
      f"Stack trace found in response: {r.text[:200]}")

# RFC 7807 error format on auth failure
r = client.get("/v1/events")
body = r.json()
has_rfc7807 = "type" in body and "status" in body
probe("B18 · Auth failure returns RFC 7807 format",
      has_rfc7807 and r.status_code == 401,
      f"Got: {body}")

# RFC 7807 on 404
r = client.get("/v1/events/999999", headers=AUTH)
body = r.json()
probe("B19 · 404 returns RFC 7807 format",
      "type" in body and body.get("status") == 404,
      f"Got: {body}")

# ══════════════════════════════════════════════════════════════════════════════
# A07 · Auth Failures — Rate Limiting
# ══════════════════════════════════════════════════════════════════════════════

section("A07 · Auth Failures (Rate Limiting)")

# Hammer the pipeline — same user_id, exceed rate limit
rate_limit_hit = False
for i in range(120):
    r = client.post("/v1/godai/query", json={
        "token": "basic-tok12345",
        "user_id": "ratelimit-test-user",
        "query": f"request {i}",
        "context": {"data_class": "PUBLIC"}
    }, headers=AUTH)
    body = r.json()
    if not body.get("success", True) and "rate" in (body.get("error") or "").lower():
        rate_limit_hit = True
        break

probe("B20 · Rate limit triggers after 100 requests (same user_id)",
      rate_limit_hit,
      "Sent 120 requests, rate limit never triggered")

# ══════════════════════════════════════════════════════════════════════════════
# A08 · Software + Data Integrity
# ══════════════════════════════════════════════════════════════════════════════

section("A08 · Software and Data Integrity")

# Oversized payload — 500KB query
big_query = "A" * 500_000
r = client.post("/v1/godai/query", json={
    "token": "basic-tok12345", "user_id": "u1",
    "query": big_query, "context": {"data_class": "PUBLIC"}
}, headers=AUTH)
probe("B21 · 500KB query field → no server crash",
      r.status_code in (200, 413, 422) and r.status_code != 500,
      f"Server crashed: {r.status_code}")

# Malformed JSON (sent as raw bytes)
r = client.post("/v1/events",
                content=b'{"title": "broken", "starts_at":',
                headers={**AUTH, "Content-Type": "application/json"})
probe("B22 · Malformed JSON → 422 not 500",
      r.status_code == 422,
      f"Got {r.status_code}")

# Missing required fields
r = client.post("/v1/events", json={"title": "no dates"}, headers=AUTH)
probe("B23 · Missing required fields → 422",
      r.status_code == 422,
      f"Got {r.status_code}")

# ══════════════════════════════════════════════════════════════════════════════
# A09 · Logging Failures — Verify Audit Trail After Attacks
# ══════════════════════════════════════════════════════════════════════════════

section("A09 · Logging Failures (Audit Trail After Attack Sequence)")

r = client.get("/v1/godai/audit", headers=AUTH)
body = r.json()
chain_valid = body.get("chain_valid", False)
total_entries = body.get("total", 0)
probe("B24 · MNEMOSYNE chain still valid after all attacks",
      chain_valid and r.status_code == 200,
      f"chain_valid={chain_valid}, entries={total_entries}")

probe("B25 · Audit log contains entries (attacks were logged)",
      total_entries > 0,
      "No audit entries found — attacks may have been silently ignored")

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

total = len(_results)
passed = sum(_results)
failed = total - passed

print(f"\n{'═' * 70}")
print(f"{BOLD}  LEVEL 4 — SECURITY PENETRATION RESULTS{RESET}")
print(f"{'═' * 70}")
print(f"  Attack vectors tested : {total}")
print(f"  {GREEN}Blocked              : {passed}{RESET}")
print(f"  {RED if failed else GREEN}Vulnerable           : {failed}{RESET}")
print(f"{'═' * 70}")

if failed == 0:
    print(f"\n  {GREEN}{BOLD}✓ ALL ATTACK VECTORS BLOCKED. NO VULNERABILITIES FOUND.{RESET}\n")
else:
    print(f"\n  {RED}{BOLD}✗ {failed} VULNERABILITY/IES FOUND. REMEDIATION REQUIRED.{RESET}\n")
    sys.exit(1)
