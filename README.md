# FraPP + G.O.D.A.I.

**AI-governed event management API — privacy-first, locally-runnable, EU AI Act compliant.**

FraPP is a FastAPI backend for calendar/event management. Every AI request flows through **G.O.D.A.I.** — a five-module AI governance control plane that enforces authentication, policy, routing, validation, and tamper-proof audit logging before any LLM call is made.

---

## Features

| Feature | Details |
|---------|---------|
| **REST API** | Full CRUD for events, paginated responses, RFC 7807 errors |
| **JWT Auth** | HMAC-SHA256 signed tokens with trust levels (L1/L2/L3) |
| **G.O.D.A.I. Pipeline** | 5-module governance: HERMES → THEMIS → APOLLON → ATHENA → MNEMOSYNE |
| **Tamper-proof Audit** | SHA256-chained log persisted to SQLite (EU AI Act Art. 12) |
| **GDPR Art. 15/17/20** | Data access, erasure, and portability endpoints |
| **Local LLM** | Runs 100% offline via Ollama or llama-cpp-python |
| **Cloud LLM** | Anthropic Claude via `AnthropicProvider` |
| **Docker** | Multi-stage production image, non-root user, health checks |
| **DB Migrations** | Alembic — zero data loss schema evolution |

---

## Quick Start

### 1. Install

```bash
git clone <repo>
cd mvp
pip install -r requirements.txt
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Set API_KEY and SECRET_KEY at minimum
```

### 3. Run

```bash
uvicorn frapp.api:app --reload
# API docs: http://localhost:8000/docs
```

### 4. First request

```bash
# List events
curl -H "X-API-Key: dev-key" http://localhost:8000/v1/events

# Issue a G.O.D.A.I. JWT
curl -X POST http://localhost:8000/v1/godai/token \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "trust_level": "L2"}'

# Query the G.O.D.A.I. pipeline
curl -X POST http://localhost:8000/v1/godai/query \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"token": "<jwt>", "user_id": "alice", "query": "Summarise my schedule", "context": {"data_class": "INTERNAL"}}'
```

---

## API Reference

Full interactive docs at `/docs` (Swagger UI) or `/redoc`.

### Events

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/events?limit=50&offset=0` | List events (paginated) |
| `POST` | `/v1/events` | Create event |
| `GET` | `/v1/events/{id}` | Get event by ID |
| `PUT` | `/v1/events/{id}` | Update event |
| `DELETE` | `/v1/events/{id}` | Delete event |

### G.O.D.A.I. Pipeline

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/godai/query` | Run query through governance pipeline |
| `GET` | `/v1/godai/status` | Pipeline health + audit chain status |
| `GET` | `/v1/godai/audit` | Paginated MNEMOSYNE audit log |
| `POST` | `/v1/godai/token` | Issue signed JWT for pipeline access |

### GDPR

| Method | Path | GDPR Article |
|--------|------|-------------|
| `GET` | `/v1/me/data` | Art. 15 — Right of access |
| `DELETE` | `/v1/me/data` | Art. 17 — Right to erasure |
| `GET` | `/v1/me/export` | Art. 20 — Data portability |

All endpoints require `X-API-Key` header. GDPR endpoints additionally require `X-User-ID`.

---

## Authentication

### API Key (all endpoints)

```
X-API-Key: <your-api-key>
```

Set `API_KEY` in `.env`. Default dev value: `dev-key`.

### G.O.D.A.I. JWT (pipeline queries)

Issue a token via `POST /v1/godai/token`, then pass it as `token` in query requests.

Trust levels:
- `L1` — Basic (public data, standard rate limits)
- `L2` — Elevated (internal data, higher limits)
- `L3` — Internal (sensitive data, admin operations)

---

## G.O.D.A.I. Architecture

```
Request
  │
  ▼
HERMES      ← JWT authentication, trust-level resolution, rate limiting
  │
  ▼
THEMIS      ← Policy evaluation (YAML-driven, no hardcoded rules)
  │
  ▼ (allowed)
APOLLON     ← Deterministic model routing (YAML config)
  │
  ▼
LLM         ← Generation (Ollama / llama-cpp / Anthropic)
  │
  ▼
ATHENA      ← Cross-validation (different model verifies output)
  │
  ▼
MNEMOSYNE   ← SHA256-chained audit log (tamper-evident, persistent)
```

Three hard invariants:
1. **Generator ≠ Arbiter** — ATHENA never uses the generator model for validation
2. **Policy = Data** — all rules live in YAML, zero hardcoded logic in modules
3. **All Decisions Logged** — every module AND the pipeline emits audit events

See [`godai/README.md`](godai/README.md) for full module documentation.

---

## Local LLM (Offline Mode)

```bash
# Install Ollama + default model (llama3.2:3b)
bash scripts/install_local_llm.sh

# Or llama-cpp-python with Phi-3 Mini GGUF
bash scripts/install_local_llm.sh --llamacpp
```

```python
from godai.providers import OllamaProvider, LlamaCppProvider
from godai.pipeline import GodaiPipeline

# Fully offline — no data leaves your machine
pipeline = GodaiPipeline.create(llm_provider=OllamaProvider())
```

---

## Docker

```bash
# Development
docker-compose up

# Production (multi-stage, non-root, health check)
docker-compose -f docker-compose.prod.yml up
```

Environment variables: see `.env.example` for the full list.

---

## Running Tests

```bash
pytest                        # all 200+ tests
pytest godai/tests/ -v        # G.O.D.A.I. unit tests
pytest tests/ -v              # FraPP + ContextOS tests
python smoke_test.py          # end-to-end integration check
```

---

## Tech Stack

- **FastAPI** + **SQLModel** + **Pydantic v2**
- **Alembic** (migrations) — SQLite (dev) / PostgreSQL (prod)
- **G.O.D.A.I.** — custom AI governance pipeline
- **ContextOS™** — SHA256-chained knowledge-governance layer
- **Anthropic Claude** / **Ollama** / **llama-cpp-python**
