"""
Tests for local offline LLM providers: OllamaProvider and LlamaCppProvider.

All tests skip automatically when the required runtime is not available:
  - OllamaProvider tests skip if Ollama server is not reachable.
  - LlamaCppProvider tests skip if llama-cpp-python is not installed or
    no GGUF model file is found.

Run with Ollama active:
    ollama serve &
    pytest godai/tests/test_local_providers.py -v
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pytest

from godai.providers import LlamaCppProvider, OllamaProvider

# ──────────────────────────────────────────────────────────────────────────────
# Ollama availability detection
# ──────────────────────────────────────────────────────────────────────────────

_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", OllamaProvider.DEFAULT_MODEL)


def _ollama_available() -> bool:
    try:
        import httpx
        with httpx.Client(timeout=3.0) as c:
            r = c.get(f"{_OLLAMA_URL}/api/version")
            return r.status_code == 200
    except Exception:
        return False


def _ollama_model_available() -> bool:
    if not _ollama_available():
        return False
    try:
        import httpx
        with httpx.Client(timeout=5.0) as c:
            r = c.get(f"{_OLLAMA_URL}/api/tags")
            data = r.json()
            names = [m["name"] for m in data.get("models", [])]
            return any(_OLLAMA_MODEL.split(":")[0] in n for n in names)
    except Exception:
        return False


ollama_required = pytest.mark.skipif(
    not _ollama_model_available(),
    reason=f"Ollama not running or model '{_OLLAMA_MODEL}' not pulled. "
           f"Run: bash scripts/install_local_llm.sh",
)

# ──────────────────────────────────────────────────────────────────────────────
# llama-cpp-python availability detection
# ──────────────────────────────────────────────────────────────────────────────

_GGUF_SEARCH_PATHS = [
    Path("models"),
    Path.home() / ".frapp" / "models",
    Path("/opt/models"),
]
_ENV_GGUF = os.environ.get("LLAMACPP_MODEL_PATH", "")


def _find_gguf() -> str | None:
    if _ENV_GGUF and Path(_ENV_GGUF).exists():
        return _ENV_GGUF
    for base in _GGUF_SEARCH_PATHS:
        if base.exists():
            for p in sorted(base.glob("*.gguf")):
                return str(p)
    return None


def _llamacpp_available() -> bool:
    try:
        import llama_cpp  # type: ignore[import]  # noqa: F401
        return _find_gguf() is not None
    except ImportError:
        return False


llamacpp_required = pytest.mark.skipif(
    not _llamacpp_available(),
    reason="llama-cpp-python not installed or no .gguf model found. "
           "Run: bash scripts/install_local_llm.sh --llamacpp",
)


# ──────────────────────────────────────────────────────────────────────────────
# Shared context fixture
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def ctx() -> Dict[str, Any]:
    return {"data_class": "PUBLIC"}


# ──────────────────────────────────────────────────────────────────────────────
# OllamaProvider tests
# ──────────────────────────────────────────────────────────────────────────────


@ollama_required
@pytest.mark.asyncio
async def test_ollama_health_check() -> None:
    provider = OllamaProvider(model=_OLLAMA_MODEL, base_url=_OLLAMA_URL)
    assert await provider.health_check() is True


@ollama_required
@pytest.mark.asyncio
async def test_ollama_generate_returns_non_empty(ctx: Dict[str, Any]) -> None:
    provider = OllamaProvider(model=_OLLAMA_MODEL, base_url=_OLLAMA_URL, max_tokens=64)
    result = await provider.generate(
        model_id="claude-haiku-4-5-20251001",
        prompt="Reply with exactly one word: hello",
        context=ctx,
    )
    assert isinstance(result, str)
    assert len(result.strip()) > 0


@ollama_required
@pytest.mark.asyncio
async def test_ollama_validation_call_returns_json(ctx: Dict[str, Any]) -> None:
    provider = OllamaProvider(model=_OLLAMA_MODEL, base_url=_OLLAMA_URL, max_tokens=128)
    result = await provider.generate(
        model_id="claude-sonnet-4-6",
        prompt="You are a quality-assurance validator. Is 'Paris is in France' factually correct? Return verdict.",
        context=ctx,
    )
    import json
    data = json.loads(result)
    assert "verdict" in data
    assert data["verdict"] in ("pass", "fail")
    assert "confidence" in data


@ollama_required
@pytest.mark.asyncio
async def test_ollama_pipeline_integration(ctx: Dict[str, Any]) -> None:
    """OllamaProvider works as a drop-in replacement in the full pipeline."""
    from godai.pipeline import GodaiPipeline

    provider = OllamaProvider(model=_OLLAMA_MODEL, base_url=_OLLAMA_URL, max_tokens=128)
    pipeline = GodaiPipeline.create(llm_provider=provider)

    result = await pipeline.process(
        token="basic-tok12345",
        user_id="local-llm-test",
        protocol="http",
        query="In one sentence, what is the capital of France?",
        context={"data_class": "PUBLIC"},
    )

    assert result.success is True
    assert result.output is not None and len(result.output.strip()) > 0
    assert result.route_decision is not None

    event_types = {e.event_type for e in pipeline.mnemosyne.entries}
    assert {"auth", "policy_check", "routing", "validation", "pipeline_success"} <= event_types
    assert pipeline.mnemosyne.verify_chain() is True


@pytest.mark.asyncio
async def test_ollama_connection_refused_raises_runtime_error(ctx: Dict[str, Any]) -> None:
    """OllamaProvider raises RuntimeError (not hangs) when server is down."""
    provider = OllamaProvider(
        model="tinyllama",
        base_url="http://127.0.0.1:19999",  # nothing running here
        timeout=2.0,
    )
    with pytest.raises(RuntimeError, match="OllamaProvider"):
        await provider.generate("any-model", "hello", ctx)


# ──────────────────────────────────────────────────────────────────────────────
# LlamaCppProvider tests
# ──────────────────────────────────────────────────────────────────────────────


@llamacpp_required
@pytest.mark.asyncio
async def test_llamacpp_generate_returns_non_empty(ctx: Dict[str, Any]) -> None:
    model_path = _find_gguf()
    assert model_path is not None
    provider = LlamaCppProvider(model_path=model_path, max_tokens=64, verbose=False)
    result = await provider.generate(
        model_id="claude-haiku-4-5-20251001",
        prompt="Reply with one word: hello",
        context=ctx,
    )
    assert isinstance(result, str)
    assert len(result.strip()) > 0


@llamacpp_required
@pytest.mark.asyncio
async def test_llamacpp_pipeline_integration(ctx: Dict[str, Any]) -> None:
    """LlamaCppProvider works as a drop-in in the full pipeline."""
    from godai.pipeline import GodaiPipeline

    model_path = _find_gguf()
    assert model_path is not None
    provider = LlamaCppProvider(model_path=model_path, max_tokens=64, verbose=False)
    pipeline = GodaiPipeline.create(llm_provider=provider)

    result = await pipeline.process(
        token="basic-tok12345",
        user_id="llamacpp-test",
        protocol="http",
        query="What is 2 + 2?",
        context={"data_class": "PUBLIC"},
    )

    assert result.success is True
    assert pipeline.mnemosyne.verify_chain() is True


@pytest.mark.asyncio
async def test_llamacpp_missing_file_raises_runtime_error(ctx: Dict[str, Any]) -> None:
    """LlamaCppProvider raises RuntimeError when model file is missing."""
    provider = LlamaCppProvider(model_path="/nonexistent/path/model.gguf")
    with pytest.raises(RuntimeError, match="LlamaCppProvider"):
        await provider.generate("any-model", "hello", ctx)
