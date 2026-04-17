# G.O.D.A.I.

**Governance-Orchestrating Deterministic Artificial Intelligence**

A deterministic control plane for multi-model AI orchestration.
G.O.D.A.I. is **not** an AI model — it is a governance layer that sits between users and LLMs.

---

## Three Invariants (never violated)

| # | Invariant | Enforcement |
|---|-----------|-------------|
| 1 | **Generator ≠ Arbiter** | LLMs generate. The pipeline decides. No LLM has a direct path to authorization or routing decisions. |
| 2 | **Policy = Data, not Code** | All rules live in YAML files. Python only executes them. No rule is ever hardcoded in Python. |
| 3 | **All Decisions Logged** | Every routing, policy, validation, and pipeline outcome is appended to MNEMOSYNE before it is acted on. No exceptions. |

---

## Five Modules

| Module | Mythological Role | Function |
|--------|------------------|---------|
| **HERMES** | Messenger / boundary | Auth, trust-level assignment, rate-limiting, protocol normalization |
| **THEMIS** | Justice / law | YAML-driven policy evaluation — binding; no override |
| **APOLLON** | Sun / clarity | Deterministic model routing — same input always → same model |
| **ATHENA** | Wisdom / independent judgment | Cross-validation by a second model; validator ≠ generator enforced |
| **MNEMOSYNE** | Memory / record | Append-only SHA256-chained audit log; tamper-evident |

---

## Request Lifecycle

```
User Request
  → HERMES.normalize()           # Auth + trust level + data class
  → MNEMOSYNE ← auth event      # (inside HERMES)
  → THEMIS.evaluate()            # Policy check against YAML rules
  → MNEMOSYNE ← policy event    # (inside THEMIS)
  → if denied → return 403
  → APOLLON.route()              # Deterministic model selection
  → MNEMOSYNE ← routing event   # (inside APOLLON)
  → LLM.generate()               # Injected provider, selected model
  → ATHENA.validate()            # Independent model cross-checks output
  → MNEMOSYNE ← validation event # (inside ATHENA)
  → if invalid → return error
  → MNEMOSYNE ← pipeline_success # (pipeline itself)
  → Return validated output
```

---

## Quick Start

```python
import asyncio
from godai.pipeline import GodaiPipeline
from godai.providers import EchoProvider   # swap for AnthropicProvider in production

async def main():
    pipeline = GodaiPipeline.create(llm_provider=EchoProvider())

    result = await pipeline.process(
        token="elevated-mytoken999",
        user_id="user-42",
        protocol="http",
        query="Summarise this document",
        context={"data_class": "INTERNAL"},
    )

    if result.success:
        print(result.output)
    else:
        print(f"Denied: {result.error}")

    # Verify audit log integrity at any time
    pipeline.mnemosyne.verify_chain()

asyncio.run(main())
```

---

## Providers

### EchoProvider (development / testing)

Returns the prompt verbatim. Validation calls receive a passing JSON verdict.
No network calls. Zero configuration.

```python
from godai.providers import EchoProvider
pipeline = GodaiPipeline.create(llm_provider=EchoProvider())
```

### LoggingProvider (observability wrapper)

Wraps any provider and logs every call at DEBUG level.

```python
from godai.providers import EchoProvider, LoggingProvider
pipeline = GodaiPipeline.create(llm_provider=LoggingProvider(EchoProvider()))
```

### AnthropicProvider (production skeleton)

Skeleton wired for the Anthropic SDK. Raises `NotImplementedError` until you
implement the `generate()` body.

```python
from godai.providers import AnthropicProvider
provider = AnthropicProvider(api_key="sk-ant-...")
pipeline = GodaiPipeline.create(llm_provider=provider)
```

### Custom Provider

Implement the `LLMProvider` protocol from `godai.modules.athena`:

```python
from typing import Any, Dict

class MyProvider:
    async def generate(self, model_id: str, prompt: str, context: Dict[str, Any]) -> str:
        # Call your LLM backend here
        return "response"
```

---

## Configuration

### Policy Rules — `config/policies/default.yaml`

```yaml
version: "1.0"
rules:
  - id: "PII_REQUIRES_L2"
    condition: "data_class == SENSITIVE"
    requirement: "trust_level >= L2"
    action: "deny"
    message: "Sensitive data requires L2+ trust level"
```

**Condition DSL:**

| Token | Values | Notes |
|-------|--------|-------|
| `data_class` | `PUBLIC` `INTERNAL` `SENSITIVE` `RESTRICTED` | string equality |
| `trust_level` | `L0` `L1` `L2` `L3` | integer `>=` / `<=` comparison |
| `action` | any string | from `request.context["action"]` |
| `explicit_consent` | `true` / `false` | from `request.context["explicit_consent"]` |
| `and` / `or` | — | compound expressions |

### Routing Rules — `config/routing/rules.yaml`

```yaml
version: "1.0"
routes:
  - condition: "data_class == SENSITIVE and trust_level >= L2"
    model: "claude-sonnet-4-6"
    reason: "Sensitive data → trusted model"
  - condition: "data_class == PUBLIC"
    model: "claude-haiku-4-5-20251001"
    reason: "Public data → efficient model"
  - default:
      model: "claude-sonnet-4-6"
      reason: "Default fallback"
```

A `default` entry is mandatory — APOLLON raises `RoutingConfigError` if it is absent.

---

## Trust Levels (HERMES)

Token prefix → TrustLevel mapping:

| Token prefix | Level | Value |
|-------------|-------|-------|
| `internal-` | L3 | 3 |
| `elevated-` | L2 | 2 |
| `basic-` | L1 | 1 |
| (any other valid token) | L1 | 1 |

---

## Audit Log (MNEMOSYNE)

Every decision produces an `AuditEvent` logged before the decision is returned.
Events are SHA256-chained: `hash = SHA256(json(event_data) + prev_hash)`.

**Event sources (`source_module`):**

| Source | Events emitted |
|--------|---------------|
| `HERMES` | `auth` (accepted or rejected) |
| `THEMIS` | `policy_check` (allowed or denied) |
| `APOLLON` | `routing` |
| `ATHENA` | `validation` |
| `PIPELINE` | `pipeline_success`, `pipeline_error` |

**Tamper detection:**

```python
pipeline.mnemosyne.verify_chain()   # raises TamperDetectedError if broken
entries = pipeline.mnemosyne.entries  # read-only snapshot
```

---

## Running Tests

```bash
pytest godai/tests/ -v
```

All tests are async (`pytest-asyncio`) and require no network access.
`EchoProvider` is used as the LLM backend in all integration tests.

---

## Project Structure

```
godai/
├── __init__.py
├── _condition_eval.py   # Shared YAML condition expression evaluator
├── pipeline.py          # Full request lifecycle orchestration
├── providers.py         # Concrete LLMProvider implementations
├── models/
│   ├── audit.py         # AuditEvent, LogEntry
│   ├── policy.py        # PolicyDecision, PolicyRule
│   ├── request.py       # InternalRequest, TrustLevel, DataClass
│   ├── routing.py       # RouteDecision
│   └── validation.py    # ValidationResult
├── modules/
│   ├── hermes.py        # API Gateway
│   ├── themis.py        # Policy Engine
│   ├── apollon.py       # Deterministic Router
│   ├── athena.py        # Cross-Validator + LLMProvider Protocol
│   └── mnemosyne.py     # Audit Log
├── config/
│   ├── policies/default.yaml
│   └── routing/rules.yaml
└── tests/
    ├── conftest.py
    ├── test_hermes.py
    ├── test_themis.py
    ├── test_apollon.py
    ├── test_athena.py
    ├── test_mnemosyne.py
    └── test_pipeline.py
```
