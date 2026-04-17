# Dependency License Audit

**Project:** FraPP + G.O.D.A.I.
**Owner:** Lucas William Chambers
**Date:** 2026-04-14
**Status:** Based on requirements.txt as of audit date. Re-run on every dependency update.

---

## Summary

All listed dependencies use permissive or copyleft-with-exception licenses compatible
with the planned Apache 2.0 release of this project.

| License | Count | Compatible with Apache 2.0 |
|---------|-------|--------------------------|
| MIT | 12 | Yes |
| BSD-3-Clause | 4 | Yes |
| Apache 2.0 | 3 | Yes |
| PSF (Python) | 1 | Yes |

No GPL, AGPL, or SSPL dependencies are present.

---

## Production Dependencies

### FastAPI

| Field | Value |
|-------|-------|
| Package | `fastapi` |
| Version | ≥ 0.100.0 |
| License | MIT |
| Author | Sebastián Ramírez |
| URL | https://fastapi.tiangolo.com |
| Usage | HTTP API framework for FraPP |

### SQLModel

| Field | Value |
|-------|-------|
| Package | `sqlmodel` |
| Version | ≥ 0.0.14 |
| License | MIT |
| Author | Sebastián Ramírez |
| URL | https://sqlmodel.tiangolo.com |
| Usage | ORM for FraPP database models |

### SQLAlchemy

| Field | Value |
|-------|-------|
| Package | `sqlalchemy` |
| Version | ≥ 2.0 (transitive via sqlmodel) |
| License | MIT |
| Author | Mike Bayer |
| URL | https://www.sqlalchemy.org |
| Usage | Database engine (transitive) |

### Pydantic

| Field | Value |
|-------|-------|
| Package | `pydantic` |
| Version | ≥ 2.0 (transitive via fastapi/sqlmodel) |
| License | MIT |
| Author | Samuel Colvin |
| URL | https://docs.pydantic.dev |
| Usage | Data validation (transitive) |

### pydantic-settings

| Field | Value |
|-------|-------|
| Package | `pydantic-settings` |
| Version | ≥ 2.0 |
| License | MIT |
| Author | Samuel Colvin |
| URL | https://docs.pydantic.dev/latest/concepts/pydantic_settings/ |
| Usage | Configuration management from `.env` files |

### Uvicorn

| Field | Value |
|-------|-------|
| Package | `uvicorn[standard]` |
| Version | ≥ 0.23 |
| License | BSD-3-Clause |
| Author | Encode OSS |
| URL | https://www.uvicorn.org |
| Usage | ASGI server for FraPP API |

### Typer

| Field | Value |
|-------|-------|
| Package | `typer` |
| Version | ≥ 0.9 |
| License | MIT |
| Author | Sebastián Ramírez |
| URL | https://typer.tiangolo.com |
| Usage | CLI framework for `frapp.cli` |

### PyYAML

| Field | Value |
|-------|-------|
| Package | `pyyaml` |
| Version | ≥ 6.0 |
| License | MIT |
| Author | Kirill Simonov |
| URL | https://pyyaml.org |
| Usage | YAML policy/routing config loading in G.O.D.A.I. |

### Starlette

| Field | Value |
|-------|-------|
| Package | `starlette` |
| Version | ≥ 0.27 (transitive via fastapi) |
| License | BSD-3-Clause |
| Author | Encode OSS |
| URL | https://www.starlette.io |
| Usage | ASGI framework (transitive) |

### AnyIO

| Field | Value |
|-------|-------|
| Package | `anyio` |
| Version | ≥ 3.0 (transitive) |
| License | MIT |
| Author | Alex Grönholm |
| Usage | Async I/O abstraction (transitive) |

---

## Development / Test Dependencies

### pytest

| Field | Value |
|-------|-------|
| Package | `pytest` |
| Version | ≥ 7.0 |
| License | MIT |
| URL | https://pytest.org |
| Usage | Test runner |

### pytest-asyncio

| Field | Value |
|-------|-------|
| Package | `pytest-asyncio` |
| Version | ≥ 0.21 |
| License | Apache 2.0 |
| URL | https://github.com/pytest-dev/pytest-asyncio |
| Usage | Async test support for G.O.D.A.I. tests |

### httpx

| Field | Value |
|-------|-------|
| Package | `httpx` |
| Version | ≥ 0.24 |
| License | BSD-3-Clause |
| URL | https://www.python-httpx.org |
| Usage | FastAPI test client |

### Ruff

| Field | Value |
|-------|-------|
| Package | `ruff` |
| Version | ≥ 0.1 |
| License | MIT |
| URL | https://docs.astral.sh/ruff |
| Usage | Linter / formatter |

### Black

| Field | Value |
|-------|-------|
| Package | `black` |
| Version | ≥ 23.0 |
| License | MIT |
| URL | https://black.readthedocs.io |
| Usage | Code formatter |

### Mypy

| Field | Value |
|-------|-------|
| Package | `mypy` |
| Version | ≥ 1.0 |
| License | MIT |
| URL | https://mypy.readthedocs.io |
| Usage | Static type checker |

---

## ContextOS Dependencies

### NetworkX

| Field | Value |
|-------|-------|
| Package | `networkx` |
| Version | ≥ 3.0 |
| License | BSD-3-Clause |
| Author | NetworkX Developers |
| URL | https://networkx.org |
| Usage | Citation graph construction and cycle detection in ContextOS resolver |

---

## Standard Library Modules Used

The following Python standard library modules are used — they carry the
Python Software Foundation (PSF) license:

| Module | Usage |
|--------|-------|
| `asyncio` | Async event loop, locks in MNEMOSYNE |
| `dataclasses` | Dataclass definitions in models |
| `datetime` | Timestamps in all models |
| `enum` | TrustLevel, DataClass enumerations |
| `hashlib` | SHA256 hash chaining in MNEMOSYNE |
| `json` | Canonical serialisation for hash computation |
| `logging` | Module-level logging throughout G.O.D.A.I. |
| `pathlib` | File path handling in config loaders |
| `re` | Regex-based condition expression preprocessing |
| `typing` | Type annotations |
| `uuid` | Request IDs and log entry IDs |

---

## Audit Notes

1. **PyYAML** — `yaml.safe_load()` is used exclusively (never `yaml.load()`), mitigating arbitrary code execution risk.
2. **eval() usage** — G.O.D.A.I. uses `eval()` with `{"__builtins__": {}}` to evaluate policy conditions. All builtins are stripped. Policy files are administrator-controlled trusted input.
3. **SQLite** — Development only. For production, replace with PostgreSQL. SQLite is public domain.
4. **No LLM SDK** — No Anthropic or OpenAI SDK is bundled. LLM integration is via injected `LLMProvider` interface (no external API calls without explicit approval).

---

*Re-run `pip-audit -r requirements.txt` and `pip licenses` after any dependency update.*
