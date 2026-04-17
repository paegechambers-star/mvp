# FraPP + G.O.D.A.I. — Handover Documentation

**Owner:** Lucas William Chambers ("Chambi")
**Project:** ForReal / ForRealAI
**Version:** 1.0 | 2026-04-14
**IP Status:** PROPRIETARY — unpublished until deal-close.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Setup & Installation](#2-setup--installation)
3. [Running the Application](#3-running-the-application)
4. [Configuration](#4-configuration)
5. [G.O.D.A.I. Module Reference](#5-godai-module-reference)
6. [FraPP API Reference](#6-frapp-api-reference)
7. [Database](#7-database)
8. [Testing](#8-testing)
9. [Deployment Checklist](#9-deployment-checklist)
10. [Known Limitations & Future Work](#10-known-limitations--future-work)

---

## 1. Architecture Overview

The repository contains two independent but co-deployed components:

### FraPP (ForReal App)
A FastAPI-based REST backend providing:
- Calendar event management (CRUD via `/v1/events`)
- Health endpoint (`/healthz`)
- SQLite persistence via SQLModel

### G.O.D.A.I. (Governance-Orchestrating Deterministic Artificial Intelligence)
A Python control plane for multi-model AI orchestration. It is **not** an AI model — it is a governance layer that sits between users and LLMs.

```
User Request
  → HERMES   (auth + protocol normalization)
  → THEMIS   (policy check — BINDING)
  → APOLLON  (deterministic model routing)
  → LLM      (generation via injected provider)
  → ATHENA   (cross-validation by independent model)
  → MNEMOSYNE (immutable audit log — all decisions)
```

**Three Hard Invariants:**

| # | Invariant | Enforcement |
|---|-----------|-------------|
| 1 | Generator ≠ Arbiter | LLMs generate; pipeline decides. No LLM has a direct auth path. |
| 2 | Policy = Data, not Code | All rules are in `godai/config/*.yaml`. Python only executes them. |
| 3 | All Decisions Logged | Every module calls `mnemosyne.append()` before returning. |

---

## 2. Setup & Installation

### Prerequisites

- Python 3.10 or later
- `bash` (Linux/macOS) or WSL (Windows)

### One-Command Install

```bash
bash install.sh          # production
bash install.sh --dev    # + dev/test dependencies
```

The script:
1. Checks Python version
2. Creates `.venv/` virtual environment
3. Installs all dependencies from `requirements.txt`
4. Installs the `frapp` package in editable mode
5. Initialises the SQLite database
6. Runs a CLI smoke test

### Manual Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
python -c "from frapp.db import init_db; init_db()"
```

---

## 3. Running the Application

### FraPP API Server

```bash
source .venv/bin/activate
python -m frapp.cli serve                        # default: 127.0.0.1:8000
python -m frapp.cli serve --host 0.0.0.0 --port 9000 --no-reload
```

Access: http://127.0.0.1:8000/docs (Swagger UI)

### CLI Commands

```bash
python -m frapp.cli version     # Print version
python -m frapp.cli serve       # Start API server
```

### G.O.D.A.I. Pipeline (Programmatic)

```python
from godai.pipeline import GodaiPipeline

pipeline = GodaiPipeline.create(llm_provider=my_provider)
result = await pipeline.process(
    token="elevated-mytoken",
    user_id="user-123",
    protocol="http",
    query="Summarise this document",
    context={"data_class": "INTERNAL"},
)
```

---

## 4. Configuration

### Environment Variables

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `FraPP` | Application display name |
| `ENV` | `dev` | Environment (`dev`/`staging`/`prod`) |
| `VERSION` | `0.0.1` | Version string |
| `API_KEY` | `dev-key` | API key for protected endpoints |
| `TIMEZONE` | `UTC` | Application timezone |

### G.O.D.A.I. Policy File

`godai/config/policies/default.yaml` — YAML policy rules evaluated by THEMIS.

**Rule format:**

```yaml
version: "1.0"
rules:
  - id: "RULE_ID"
    condition: "data_class == SENSITIVE"
    requirement: "trust_level >= L2"
    action: "deny"
    message: "Human-readable denial message"
```

**Condition DSL:**

| Variable | Type | Values |
|----------|------|--------|
| `data_class` | string | `PUBLIC`, `INTERNAL`, `SENSITIVE`, `RESTRICTED` |
| `trust_level` | integer | `L0`=0, `L1`=1, `L2`=2, `L3`=3 |
| `action` | string | Any action string from request context |
| `explicit_consent` | bool | `true` / `false` |

### G.O.D.A.I. Routing Config

`godai/config/routing/rules.yaml` — deterministic model routing.

```yaml
version: "1.0"
routes:
  - condition: "data_class == SENSITIVE and trust_level >= L2"
    model: "claude-sonnet-4-6"
    reason: "Sensitive data → trusted model"
  - default:
      model: "claude-sonnet-4-6"
      reason: "Default fallback"
```

---

## 5. G.O.D.A.I. Module Reference

### HERMES — API Gateway (`godai/modules/hermes.py`)

- **Input:** raw token, user_id, protocol, query, context
- **Output:** `InternalRequest`
- **Raises:** `AuthenticationError` (401), `RateLimitError` (429)
- **Logs:** `auth` event to MNEMOSYNE

Token prefix → TrustLevel mapping:

| Prefix | TrustLevel |
|--------|------------|
| `internal-` | L3 |
| `elevated-` | L2 |
| `basic-` | L1 |
| (other) | L1 (default) |

### THEMIS — Policy Engine (`godai/modules/themis.py`)

- **Input:** `InternalRequest` + YAML policy
- **Output:** `PolicyDecision` (binding — no override)
- **Logs:** `policy_check` event to MNEMOSYNE
- Hot-reload: `themis.reload_policy()`

### APOLLON — Router (`godai/modules/apollon.py`)

- **Input:** `InternalRequest` + `PolicyDecision` + YAML routing config
- **Output:** `RouteDecision` (deterministic — same input = same output)
- **Logs:** `routing` event to MNEMOSYNE
- Hot-reload: `apollon.reload_config()`

### ATHENA — Validator (`godai/modules/athena.py`)

- **Input:** generator output + `InternalRequest` + generator model ID
- **Output:** `ValidationResult`
- **Invariant:** validator model ≠ generator model (enforced in code)
- **Logs:** `validation` event to MNEMOSYNE
- Strategies: `consistency_check`, `fact_verification`, `policy_compliance`

### MNEMOSYNE — Audit Log (`godai/modules/mnemosyne.py`)

- Append-only, SHA256-chained log
- `await mnemosyne.append(event)` — non-blocking
- `mnemosyne.verify_chain()` — raises `TamperDetectedError` if tampered
- `mnemosyne.entries` — read-only snapshot
- EU AI Act Article 12 compliant

---

## 6. FraPP API Reference

### Health Check

```
GET /healthz
→ {"status": "ok", "app": "FraPP", "version": "0.0.1"}
```

### Events

```
GET /v1/events
→ [...Event objects...]
```

**Event schema:**

| Field | Type | Required |
|-------|------|----------|
| `id` | integer | auto |
| `title` | string | yes |
| `starts_at` | datetime | yes |
| `ends_at` | datetime | yes |
| `location` | string | no |
| `all_day` | bool | default false |

---

## 7. Database

- **Engine:** SQLite (file: `frapp.db` in working directory)
- **ORM:** SQLModel (SQLAlchemy under the hood)
- **Init:** `from frapp.db import init_db; init_db()` (idempotent)
- **Migration:** No migration tooling yet — for schema changes, drop and recreate `frapp.db`

For production, replace the SQLite engine in `src/frapp/db.py` with PostgreSQL:

```python
engine = create_engine("postgresql://user:pass@host/dbname")
```

---

## 8. Testing

```bash
# All tests
pytest

# G.O.D.A.I. module tests only
pytest godai/tests/

# FraPP tests only
pytest tests/

# With verbose output
pytest -v

# Single module
pytest godai/tests/test_pipeline.py -v
```

**Test coverage by module:**

| Module | Tests file | Coverage |
|--------|-----------|---------|
| MNEMOSYNE | `godai/tests/test_mnemosyne.py` | hash chain, tamper detection, concurrency |
| HERMES | `godai/tests/test_hermes.py` | auth, rate limit, trust levels, protocols |
| THEMIS | `godai/tests/test_themis.py` | allow/deny, policy loading, hot-reload |
| APOLLON | `godai/tests/test_apollon.py` | routing, determinism, config loading |
| ATHENA | `godai/tests/test_athena.py` | strategies, validator != generator |
| Pipeline | `godai/tests/test_pipeline.py` | full lifecycle, invariants |
| FraPP | `tests/test_frapp.py` | API endpoints, CLI |

---

## 9. Deployment Checklist

- [ ] Copy `.env.example` → `.env`, set `ENV=prod` and a real `API_KEY`
- [ ] Replace SQLite with PostgreSQL in `src/frapp/db.py`
- [ ] Inject real `LLMProvider` implementation (Anthropic SDK / OpenAI) into `GodaiPipeline`
- [ ] Set production policy YAML paths in `GodaiPipeline.create()`
- [ ] Configure log aggregation for `godai.*` loggers (MNEMOSYNE emits DEBUG)
- [ ] Set up cron/task for `mnemosyne.verify_chain()` to alert on tampering
- [ ] Review `godai/config/policies/default.yaml` for production trust requirements
- [ ] Enable HTTPS (TLS termination at reverse proxy)

---

## 10. ContextOS™ Knowledge-Governance Layer

ContextOS is a deterministic knowledge-governance system embedded in FraPP.
It enforces 8 hard invariants and provides tamper-evident knowledge storage.

### Architecture

```
contextos/
├── types.py          # Enums + dataclasses (Kind, Actor, Cluster, …)
├── id_generator.py   # 16-char NKID/MKID generator (base36, SHA256 checksum)
├── store.py          # Content-addressable blob store (~/.frapp/contextos/store/)
├── log.py            # SHA256-chained SQLite audit log (ContextOSLog)
├── commit.py         # CommitBlock factory (PATCH/SUPERSEDE/PROMOTE/DEPRECATE)
├── register.py       # SQLite WAL register — ssot (immutable) + work (mutable)
├── index.py          # In-memory + JSON-persisted fast lookup
├── resolver.py       # Query engine with networkx citation graph
├── mkid_runner.py    # MKID execution engine (5 default MKIDs seeded)
├── godai_audit.py    # SOLE bridge to G.O.D.A.I. MNEMOSYNE (fail-closed)
├── ui.py             # PyQt5 tab with headless fallback
└── policies/
    └── contextos_default.yaml
```

### 8 Hard Invariants

| # | Invariant | Enforcement |
|---|-----------|-------------|
| 1 | Register ↔ Log mutual dependency | Same SQLite transaction writes both |
| 2 | SSOT immutable | INSERT only on `ssot` table |
| 3 | WORK mutable | INSERT + UPDATE on `work` table |
| 4 | No-Citation = No-Assertion | `_assert_citations()` before every write |
| 5 | All IDs pass `validate_id()` | Checksum verified on parse |
| 6 | MNEMOSYNE external only | Only `godai_audit.py` imports from godai |
| 7 | CommitBlocks frozen | `@dataclass(frozen=True)` |
| 8 | Chain integrity verifiable | `ContextOSLog.verify_chain()` at any time |

### ID Format (16 chars, all base36)

```
[kind 2][actor 2][cluster 2][entry_type 2][truth_gate 2][time_bucket 2][sequence 2][checksum 2]
```

- Kind: `NK` (Node Knowledge / SSOT) | `MK` (Meta Knowledge / WORK)
- Checksum: polynomial hash over first 14 chars, modulo 36²

### Quick Start

```python
from contextos import Register, ContextOSLog, generate_id
from contextos.types import Kind, Actor, Cluster, EntryType, TruthGate
from pathlib import Path

base = Path.home() / ".frapp" / "contextos"
log = ContextOSLog(base / "contextos.db")
reg = Register(base / "contextos.db", log)

nkid = generate_id(Kind.NK, Actor.USER, Cluster.GENERAL,
                    EntryType.FACT, TruthGate.UNVERIFIED,
                    time_bucket="00", sequence=0)
```

### Running ContextOS Tests

```bash
pytest tests/contextos/ -v     # 89 tests
```

---

## 11. Known Limitations & Future Work

| Item | Notes |
|------|-------|
| No real LLM integration | `GodaiPipeline` requires an injected `LLMProvider`. Anthropic SDK wrapper not included (no external API calls without approval). |
| SQLite only | Swap to PostgreSQL for multi-instance deployments. |
| MNEMOSYNE in-memory | Log entries are lost on restart. Persist to a database or append-only file for production. |
| Rate limiting in-memory | `Hermes._request_counts` is per-process. Use Redis for distributed rate limiting. |
| Policy hot-reload not thread-safe | `reload_policy()` is safe for single-threaded use; add a lock for concurrent access. |
