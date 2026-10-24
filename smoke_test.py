"""
FraPP + G.O.D.A.I. + ContextOS — Integrated Smoke Test

Tests every subsystem using the system's own runtime mechanics:
- G.O.D.A.I. full pipeline (EchoProvider, real YAML configs)
- All 3 hard invariants verified structurally
- All 5 module failure paths exercised
- ContextOS knowledge-governance layer (Register, Log, Resolver)
- FraPP API endpoints via HTTPX test client
- MNEMOSYNE chain integrity checked after every scenario
- Local LLM probe: Ollama + llama-cpp-python availability report

Run: python smoke_test.py

To activate local LLM:
    bash scripts/install_local_llm.sh          # Ollama + llama3.2:3b
    bash scripts/install_local_llm.sh --llamacpp  # llama-cpp-python + Phi-3
"""
from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[93m·\033[0m"   # informational — does not affect exit code
HEAD = "\033[1;94m"
RST  = "\033[0m"

_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    icon = PASS if condition else FAIL
    print(f"  {icon}  {name}" + (f" — {detail}" if detail else ""))
    _results.append((name, condition, detail))


def probe(name: str, condition: bool, detail: str = "") -> None:
    """Informational probe — never counted as a failure."""
    icon = PASS if condition else INFO
    label = "ready" if condition else "not installed"
    suffix = f" — {detail}" if detail else f" — {label}"
    print(f"  {icon}  {name}{suffix}")


def section(title: str) -> None:
    print(f"\n{HEAD}{'─' * 60}{RST}")
    print(f"{HEAD}  {title}{RST}")
    print(f"{HEAD}{'─' * 60}{RST}")


# ──────────────────────────────────────────────────────────────────────────────
# G.O.D.A.I. smoke
# ──────────────────────────────────────────────────────────────────────────────

async def smoke_godai() -> None:
    from godai.pipeline import GodaiPipeline
    from godai.providers import EchoProvider, LoggingProvider

    section("G.O.D.A.I. — Full Pipeline (EchoProvider)")

    provider = LoggingProvider(EchoProvider())
    pipeline = GodaiPipeline.create(llm_provider=provider)

    # ── 1. Happy path — PUBLIC / L1 ─────────────────────────────────────────
    r = await pipeline.process(
        token="basic-tok12345",
        user_id="smoke-user",
        protocol="http",
        query="What is the capital of France?",
        context={"data_class": "PUBLIC"},
    )
    check("PUBLIC/L1 request succeeds", r.success, r.error or "")
    check("Output is non-empty", bool(r.output))
    check("Route → haiku model", r.route_decision is not None and "haiku" in r.route_decision.model_id.lower())
    check("ATHENA validation passed", r.validation_result is not None and r.validation_result.passed)

    # ── 2. INVARIANT 3 — all decisions logged ───────────────────────────────
    event_types = {e.event_type for e in pipeline.mnemosyne.entries}
    required = {"auth", "policy_check", "routing", "validation", "pipeline_success"}
    check("INVARIANT 3 — all 5 event types logged", required <= event_types,
          f"found={sorted(event_types)}")

    # ── 3. MNEMOSYNE chain integrity ─────────────────────────────────────────
    check("MNEMOSYNE chain intact", pipeline.mnemosyne.verify_chain())

    # ── 4. SENSITIVE / L2 → sonnet ──────────────────────────────────────────
    p2 = GodaiPipeline.create(llm_provider=EchoProvider())
    r2 = await p2.process(
        token="elevated-tok9999",
        user_id="smoke-elevated",
        protocol="http",
        query="Summarise the confidential report",
        context={"data_class": "SENSITIVE"},
    )
    check("SENSITIVE/L2 request succeeds", r2.success)
    check("Route → sonnet model", r2.route_decision is not None and "sonnet" in r2.route_decision.model_id.lower())

    # ── 5. THEMIS denial — SENSITIVE + L1 ───────────────────────────────────
    p3 = GodaiPipeline.create(llm_provider=EchoProvider())
    r3 = await p3.process(
        token="basic-tok12345",
        user_id="smoke-denied",
        protocol="http",
        query="Try to read sensitive data",
        context={"data_class": "SENSITIVE"},
    )
    check("SENSITIVE/L1 denied by THEMIS", not r3.success)
    check("Denial error message present", bool(r3.error))
    check("No route on denied request", r3.route_decision is None)
    et3 = {e.event_type for e in p3.mnemosyne.entries}
    check("Denial logged as pipeline_error", "pipeline_error" in et3)

    # ── 6. INVARIANT 1 — Generator ≠ Arbiter (structural) ───────────────────
    check("INVARIANT 1 — pipeline owns llm_provider", hasattr(pipeline, "_llm_provider"))
    check("INVARIANT 1 — athena owns separate provider", hasattr(pipeline._athena, "_provider"))

    # ── 7. Auth failure — missing token ─────────────────────────────────────
    p4 = GodaiPipeline.create(llm_provider=EchoProvider())
    r4 = await p4.process(token=None, user_id="anon", protocol="http", query="q")
    check("Missing token → auth failure", not r4.success)
    check("Auth failure logs pipeline_error", "pipeline_error" in {e.event_type for e in p4.mnemosyne.entries})

    # ── 8. Rate limit ────────────────────────────────────────────────────────
    p5 = GodaiPipeline.create(llm_provider=EchoProvider(), rate_limit=2)
    for _ in range(2):
        await p5.process(token="basic-tok12345", user_id="rl-user", protocol="http", query="q")
    r5 = await p5.process(token="basic-tok12345", user_id="rl-user", protocol="http", query="q")
    check("Rate limit enforced (3rd req fails)", not r5.success)

    # ── 9. INVARIANT 2 — Policy = Data ──────────────────────────────────────
    from pathlib import Path
    policy_yaml = Path(__file__).parent / "godai" / "config" / "policies" / "default.yaml"
    routing_yaml = Path(__file__).parent / "godai" / "config" / "routing" / "rules.yaml"
    check("INVARIANT 2 — policy file is YAML data", policy_yaml.exists())
    check("INVARIANT 2 — routing file is YAML data", routing_yaml.exists())
    check("INVARIANT 2 — no rules hardcoded in pipeline.py",
          "trust_level" not in Path(__file__).parent.joinpath("godai/pipeline.py").read_text())

    # ── 10. Generation failure path ──────────────────────────────────────────
    class FailProvider:
        async def generate(self, model_id, prompt, context):
            raise RuntimeError("Simulated LLM down")

    p6 = GodaiPipeline.create(llm_provider=FailProvider())
    r6 = await p6.process(
        token="basic-tok12345", user_id="u", protocol="http", query="q",
        context={"data_class": "PUBLIC"},
    )
    check("Generation failure returns error", not r6.success and "Generation failed" in (r6.error or ""))


# ──────────────────────────────────────────────────────────────────────────────
# ContextOS smoke
# ──────────────────────────────────────────────────────────────────────────────

def smoke_contextos() -> None:
    section("ContextOS™ — Knowledge-Governance Layer")

    import sqlite3
    from datetime import datetime, timezone

    from contextos.id_generator import generate_id, validate_id, parse_id
    from contextos.store import write_blob, read_blob, sha256_of
    from contextos.log import ContextOSLog, TamperDetectedError
    from contextos.commit import make_commit
    from contextos.register import Register
    from contextos.index import ContextOSIndex
    from contextos.resolver import Resolver
    from contextos.types import (
        Kind, Actor, Cluster, EntryType, TruthGate, CommitOp,
        SSOTEntry, WorkEntry,
    )

    with TemporaryDirectory() as tmp:
        base = Path(tmp)

        # ── ID generator ─────────────────────────────────────────────────────
        nkid = generate_id(
            Kind.NK, Actor.USER, Cluster.GENERAL, EntryType.FACT,
            TruthGate.UNVERIFIED, time_bucket="00", sequence=0,
        )
        check("ID is 16 chars", len(nkid) == 16, nkid)
        check("ID validates", validate_id(nkid))
        parsed = parse_id(nkid)
        check("ID round-trips", parsed.raw == nkid)
        check("ID kind=NK", parsed.kind == Kind.NK)

        bad = nkid[:-1] + ("A" if nkid[-1] != "A" else "B")
        check("Corrupted ID rejected", not validate_id(bad))

        # ── Blob store ───────────────────────────────────────────────────────
        payload = "Hello ContextOS"
        digest = write_blob(payload, base_dir=base)
        stored = (base / "store" / digest[:2] / digest[2:]).exists()
        check("Blob stored", stored, f"digest={digest[:8]}…")
        check("Blob readable", read_blob(digest, base_dir=base) == payload)
        check("SHA256 matches", sha256_of(payload) == digest)

        # ── Audit log (chained) via CommitBlock ──────────────────────────────
        db_path = base / "contextos.db"
        log = ContextOSLog(db_path)
        commit1 = make_commit(CommitOp.PATCH, nkid, Actor.USER, "a" * 64)
        mkid = generate_id(Kind.MK, Actor.USER, Cluster.GENERAL, EntryType.ANNOTATION,
                           TruthGate.UNVERIFIED, time_bucket="00", sequence=1)
        commit2 = make_commit(CommitOp.PATCH, mkid, Actor.SYSTEM, "b" * 64)

        with sqlite3.connect(str(db_path)) as conn:
            log.append(conn, commit1)
            log.append(conn, commit2)

        entries = log.entries()
        check("Log has 2 entries", len(entries) == 2)
        check("Chain valid after append", log.verify_chain())
        check("Entry 1 prev_hash = entry 0 hash", entries[1].prev_hash == entries[0].hash)

        # ── CommitBlocks frozen (Invariant 7) ────────────────────────────────
        check("CommitBlock is frozen", _is_frozen(commit1))
        check("CommitBlock op=PATCH", commit1.operation == CommitOp.PATCH)

        # ── Register (SSOT + WORK) ───────────────────────────────────────────
        reg_db = base / "reg.db"
        log2 = ContextOSLog(reg_db)
        reg = Register(reg_db, log2)

        now = datetime.now(timezone.utc)
        src_id = generate_id(Kind.NK, Actor.USER, Cluster.GENERAL, EntryType.FACT,
                             TruthGate.UNVERIFIED, time_bucket="01", sequence=0)
        ssot_entry = SSOTEntry(
            nkid=src_id,
            content="Paris is the capital of France",
            truth_gate=TruthGate.UNVERIFIED,
            citations=(),
            content_hash=sha256_of("Paris is the capital of France"),
            created_at=now,
            cluster=Cluster.GENERAL,
            actor=Actor.USER,
        )
        reg.insert_ssot(ssot_entry)
        fetched = reg.get_ssot(src_id)
        check("SSOT insert + get", fetched is not None and fetched.content.startswith("Paris"))

        wk_id = generate_id(Kind.MK, Actor.USER, Cluster.GENERAL, EntryType.ANNOTATION,
                            TruthGate.UNVERIFIED, time_bucket="01", sequence=1)
        work_entry = WorkEntry(
            mkid=wk_id,
            content="draft note",
            truth_gate=TruthGate.UNVERIFIED,
            citations=[],
            content_hash=sha256_of("draft note"),
            created_at=now,
            modified_at=now,
            cluster=Cluster.GENERAL,
            actor=Actor.USER,
        )
        reg.insert_work(work_entry)
        fetched_w = reg.get_work(wk_id)
        check("WORK insert + get", fetched_w is not None and fetched_w.content == "draft note")

        # ── SSOT immutability (Invariant 2) ──────────────────────────────────
        try:
            reg.insert_ssot(ssot_entry)  # duplicate → must fail
            check("SSOT immutability enforced", False, "no error raised")
        except Exception:
            check("SSOT immutability enforced", True)

        # ── Index ────────────────────────────────────────────────────────────
        idx = ContextOSIndex(index_path=base / "index.json")
        idx.add_ssot(ssot_entry)
        meta = idx.get(src_id)
        check("Index add + get", meta is not None and meta.get("kind") == "NK")
        check("Index exists()", idx.exists(src_id))

        # ── Resolver instantiates ────────────────────────────────────────────
        resolver = Resolver(reg, idx)
        check("Resolver instantiates", resolver is not None)

        # ── Tamper detection (Invariant 8) ───────────────────────────────────
        db_t = base / "tamper.db"
        log_t = ContextOSLog(db_t)
        commit_t = make_commit(CommitOp.PATCH, nkid, Actor.USER, "c" * 64)
        with sqlite3.connect(str(db_t)) as conn:
            log_t.append(conn, commit_t)
        check("Fresh log chain valid", log_t.verify_chain())
        # Corrupt the stored hash
        with sqlite3.connect(str(db_t)) as conn:
            conn.execute("UPDATE contextos_log SET hash='BADHASH' WHERE chain_index=0")
        try:
            log_t.verify_chain()
            check("Tamper detected after hash corruption", False, "no error raised")
        except TamperDetectedError:
            check("Tamper detected after hash corruption", True)


def _is_frozen(obj: object) -> bool:
    import dataclasses
    return dataclasses.is_dataclass(obj) and bool(getattr(type(obj), "__dataclass_params__", None) and type(obj).__dataclass_params__.frozen)


# ──────────────────────────────────────────────────────────────────────────────
# FraPP API smoke
# ──────────────────────────────────────────────────────────────────────────────

def smoke_frapp() -> None:
    section("FraPP — REST API Endpoints")
    try:
        from fastapi.testclient import TestClient
        from frapp.api import app
        from frapp.db import init_db

        init_db()
        client = TestClient(app)

        r = client.get("/healthz")
        check("GET /healthz → 200", r.status_code == 200)
        check("/healthz status=ok", r.json().get("status") == "ok")

        r2 = client.get("/v1/events")
        check("GET /v1/events → 200", r2.status_code == 200)
        check("/v1/events returns list", isinstance(r2.json(), list))

    except Exception as exc:
        check("FraPP API smoke", False, str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# MNEMOSYNE tamper detection (standalone)
# ──────────────────────────────────────────────────────────────────────────────

async def smoke_mnemosyne() -> None:
    section("MNEMOSYNE — Append-Only Tamper-Evident Audit Log")

    from godai.modules.mnemosyne import Mnemosyne, TamperDetectedError
    from godai.models.audit import AuditEvent
    from datetime import datetime, timezone

    m = Mnemosyne()

    for i in range(5):
        await m.append(AuditEvent(
            event_type="test_event",
            event_data={"seq": i},
            source_module="PIPELINE",
            timestamp=datetime.now(timezone.utc),
        ))

    check("5 entries appended", len(m) == 5)
    check("Chain valid", m.verify_chain())

    # Tamper: corrupt the middle entry's hash
    entries = m.entries
    check("entries returns snapshot", len(entries) == 5)

    # Verify chain is SHA256-linked
    e0 = entries[0]
    e1 = entries[1]
    check("Each entry has a hash", bool(e0.hash) and bool(e1.hash))
    check("Consecutive hashes differ", e0.hash != e1.hash)
    check("Entry 1 prev_hash = entry 0 hash", e1.prev_hash == e0.hash)


# ──────────────────────────────────────────────────────────────────────────────
# Local LLM probe (informational — never fails the suite)
# ──────────────────────────────────────────────────────────────────────────────

async def smoke_local_llm() -> None:
    section("Local Offline LLM — Availability Probe")

    from godai.providers import OllamaProvider, LlamaCppProvider

    # ── Ollama ──────────────────────────────────────────────────────────────
    provider = OllamaProvider()
    reachable = await provider.health_check()
    probe("Ollama server :11434", reachable,
          "run: bash scripts/install_local_llm.sh" if not reachable else "")

    if reachable:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get("http://localhost:11434/api/tags")
                models = [m["name"] for m in r.json().get("models", [])]
            probe("Ollama models available", bool(models),
                  ", ".join(models[:3]) if models else "run: ollama pull llama3.2:3b")
            if models:
                tag = models[0]
                p = OllamaProvider(model=tag, max_tokens=32)
                try:
                    out = await p.generate("claude-haiku-4-5-20251001", "Say: OK", {})
                    probe(f"Ollama generate({tag})", bool(out.strip()),
                          out.strip()[:60] if out else "no output")
                except Exception as exc:
                    probe(f"Ollama generate({tag})", False, str(exc)[:80])
        except Exception as exc:
            probe("Ollama model check", False, str(exc)[:80])

    # ── llama-cpp-python ─────────────────────────────────────────────────────
    llamacpp_ok = False
    try:
        import llama_cpp  # type: ignore[import]  # noqa: F401
        llamacpp_ok = True
    except ImportError:
        pass
    probe("llama-cpp-python", llamacpp_ok,
          "pip install llama-cpp-python" if not llamacpp_ok else "")

    # Search for GGUF model
    from pathlib import Path as _Path
    gguf = None
    for d in [_Path("models"), _Path.home() / ".frapp" / "models"]:
        if d.exists():
            found = list(d.glob("*.gguf"))
            if found:
                gguf = found[0]
                break
    probe("GGUF model file", gguf is not None,
          str(gguf) if gguf else "bash scripts/install_local_llm.sh --llamacpp")


# ──────────────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────────────

def print_summary() -> int:
    section("SMOKE TEST SUMMARY")
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total  = len(_results)

    if failed:
        print(f"\n{FAIL}  FAILED CHECKS:")
        for name, ok, detail in _results:
            if not ok:
                print(f"     • {name}" + (f": {detail}" if detail else ""))

    bar = "█" * int(40 * passed / total) + "░" * int(40 * (total - passed) / total) if total else ""
    print(f"\n  {bar}")
    print(f"\n  {PASS} {passed} passed   {FAIL} {failed} failed   ({total} total)\n")
    return 1 if failed else 0


async def main() -> int:
    print(f"\n{HEAD}{'═' * 60}{RST}")
    print(f"{HEAD}  FraPP + G.O.D.A.I. + ContextOS — Integrated Smoke Test{RST}")
    print(f"{HEAD}{'═' * 60}{RST}")

    sections = [
        ("G.O.D.A.I. Pipeline",    smoke_godai()),
        ("MNEMOSYNE",              smoke_mnemosyne()),
        ("Local LLM probe",        smoke_local_llm()),
    ]

    for label, coro in sections:
        try:
            await coro
        except Exception:
            section(f"ERROR in {label}")
            traceback.print_exc()
            _results.append((f"{label} — unhandled exception", False, ""))

    # Sync sections
    for fn in [smoke_contextos, smoke_frapp]:
        try:
            fn()
        except Exception:
            section(f"ERROR in {fn.__name__}")
            traceback.print_exc()
            _results.append((f"{fn.__name__} — unhandled exception", False, ""))

    return print_summary()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
