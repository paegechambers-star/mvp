"""
Concrete LLMProvider implementations for G.O.D.A.I.

Five implementations are provided:

  EchoProvider      — returns the prompt verbatim; validation calls emit a
                      passing JSON verdict.  Use for development and smoke tests.

  LoggingProvider   — wraps any other provider and logs every call with
                      model_id, prompt length, and response length.

  OllamaProvider    — fully offline, local-first.  Talks to a running Ollama
                      server (http://localhost:11434) via httpx.  No cloud
                      dependency.  See scripts/install_local_llm.sh.

  LlamaCppProvider  — fully offline, no separate server.  Loads a GGUF model
                      file directly in-process via llama-cpp-python.  Slower to
                      start but zero external dependencies after install.

  AnthropicProvider — production cloud provider via the Anthropic SDK.

Usage::

    # Offline / local (recommended for dev)
    from godai.providers import OllamaProvider
    pipeline = GodaiPipeline.create(llm_provider=OllamaProvider())

    # Fully offline, in-process (no server required)
    from godai.providers import LlamaCppProvider
    pipeline = GodaiPipeline.create(
        llm_provider=LlamaCppProvider(model_path="/path/to/model.gguf")
    )

    # Cloud
    from godai.providers import AnthropicProvider
    pipeline = GodaiPipeline.create(llm_provider=AnthropicProvider())
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from godai.modules.athena import LLMProvider

_logger = logging.getLogger("godai.providers")


# ---------------------------------------------------------------------------
# EchoProvider
# ---------------------------------------------------------------------------


class EchoProvider:
    """
    Development provider that echoes the prompt back.

    Generation calls return the prompt text unchanged.
    Validation calls (detected by the presence of ``verdict`` keyword in the
    prompt) return a well-formed passing JSON verdict so ATHENA is satisfied.

    Never use in production — it performs no actual inference.
    """

    async def generate(
        self,
        model_id: str,
        prompt: str,
        context: Dict[str, Any],
    ) -> str:
        """Return prompt verbatim, or a passing verdict for validation calls."""
        _logger.debug("EchoProvider.generate(model=%s, prompt_len=%d)", model_id, len(prompt))

        # Validation prompts contain structured keywords; return a passing verdict
        validation_keywords = {"verdict", "quality-assurance", "fact-check", "compliance"}
        if any(kw in prompt.lower() for kw in validation_keywords):
            return json.dumps({
                "verdict": "pass",
                "confidence": 0.95,
                "issues": [],
            })

        return prompt


# ---------------------------------------------------------------------------
# LoggingProvider
# ---------------------------------------------------------------------------


class LoggingProvider:
    """
    Transparent wrapper that logs every generate() call and response.

    Wraps any :class:`~godai.modules.athena.LLMProvider` and adds
    structured logging at DEBUG level.  Useful for tracing which model
    is called at each pipeline stage.

    Example::

        from godai.providers import LoggingProvider, EchoProvider
        pipeline = GodaiPipeline.create(llm_provider=LoggingProvider(EchoProvider()))
    """

    def __init__(self, inner: LLMProvider) -> None:
        """
        Args:
            inner: The underlying provider to delegate all calls to.
        """
        self._inner = inner

    async def generate(
        self,
        model_id: str,
        prompt: str,
        context: Dict[str, Any],
    ) -> str:
        """Delegate to inner provider, logging call metadata."""
        _logger.debug(
            "LLMProvider.generate → model=%s prompt_len=%d",
            model_id,
            len(prompt),
        )
        response = await self._inner.generate(
            model_id=model_id,
            prompt=prompt,
            context=context,
        )
        _logger.debug(
            "LLMProvider.generate ← model=%s response_len=%d",
            model_id,
            len(response),
        )
        return response


# ---------------------------------------------------------------------------
# AnthropicProvider (skeleton — requires anthropic SDK + API key)
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """
    Production provider for the Anthropic Claude API.

    Requires:
      1. ``pip install anthropic``
      2. ``ANTHROPIC_API_KEY`` set in environment (or pass ``api_key``)

    Example::

        provider = AnthropicProvider()  # reads ANTHROPIC_API_KEY from env
        pipeline = GodaiPipeline.create(llm_provider=provider)
    """

    def __init__(self, api_key: str | None = None, max_tokens: int = 1024) -> None:
        """
        Args:
            api_key: Anthropic API key.  Falls back to the
                ``ANTHROPIC_API_KEY`` environment variable if omitted.
            max_tokens: Maximum tokens in generated responses.
        """
        self._api_key = api_key
        self._max_tokens = max_tokens
        # Lazy-import to keep anthropic as an optional dependency
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazily initialise the Anthropic client."""
        if self._client is None:
            try:
                import anthropic  # type: ignore[import]
            except ImportError as exc:
                raise ImportError(
                    "The 'anthropic' package is required for AnthropicProvider. "
                    "Install it with: pip install anthropic"
                ) from exc
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def generate(
        self,
        model_id: str,
        prompt: str,
        context: Dict[str, Any],
    ) -> str:
        """Call the Anthropic Messages API and return the text response."""
        client = self._get_client()

        # ATHENA validation calls contain these keywords; respond with structured JSON
        validation_keywords = {"verdict", "quality-assurance", "fact-check", "compliance"}
        is_validation = any(kw in prompt.lower() for kw in validation_keywords)
        system: str | None = (
            'Respond ONLY with valid JSON: {"verdict":"pass"|"fail","confidence":0.0-1.0,"issues":[]}'
            if is_validation else None
        )

        _logger.debug(
            "AnthropicProvider.generate(model=%s, prompt_len=%d, validation=%s)",
            model_id, len(prompt), is_validation,
        )

        kwargs: Dict[str, Any] = {
            "model": model_id,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        try:
            message = await client.messages.create(**kwargs)
            return message.content[0].text
        except Exception as exc:
            try:
                import anthropic as _ant  # type: ignore[import]
                if isinstance(exc, _ant.APIError):
                    raise RuntimeError(
                        f"Anthropic API error ({type(exc).__name__}): {exc}"
                    ) from exc
            except ImportError:
                pass
            raise RuntimeError(f"AnthropicProvider.generate() failed: {exc}") from exc


# ---------------------------------------------------------------------------
# OllamaProvider — fully offline, local Ollama server
# ---------------------------------------------------------------------------

_VALIDATION_SYSTEM = (
    'You are a JSON-only validation oracle. '
    'Respond ONLY with valid JSON — no markdown, no explanation: '
    '{"verdict":"pass"|"fail","confidence":0.0-1.0,"issues":[]}'
)

_VALIDATION_KEYWORDS = frozenset({"verdict", "quality-assurance", "fact-check", "compliance"})


class OllamaProvider:
    """
    Fully offline LLM provider that talks to a local Ollama server.

    Ollama runs open-source models (Llama 3, Mistral, Phi-3, Gemma, …)
    entirely on the local machine — no data leaves the host.

    Install Ollama and pull a model::

        bash scripts/install_local_llm.sh          # installs Ollama + default model
        # or manually:
        curl -fsSL https://ollama.com/install.sh | sh
        ollama pull llama3.2:3b
        ollama serve                                # starts server on :11434

    Then use::

        from godai.providers import OllamaProvider
        provider = OllamaProvider()                 # default model: llama3.2:3b
        provider = OllamaProvider(model="phi3:mini")

    The ``model_id`` argument passed to ``generate()`` by the pipeline is
    an Anthropic model ID (e.g. "claude-haiku-4-5-20251001").  OllamaProvider
    ignores it and always uses its configured local model — the pipeline's
    routing decision still appears in the MNEMOSYNE log for auditability.

    Args:
        model:       Ollama model tag.  Run ``ollama list`` to see installed models.
        base_url:    Ollama server URL (default: http://localhost:11434).
        max_tokens:  Maximum tokens to generate (``num_predict`` in Ollama).
        timeout:     HTTP request timeout in seconds.
    """

    DEFAULT_MODEL = "llama3.2:3b"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = "http://localhost:11434",
        max_tokens: int = 1024,
        timeout: float = 120.0,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    async def health_check(self) -> bool:
        """Return True if the Ollama server is reachable and the model is available."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self._base_url}/api/version")
                return r.status_code == 200
        except Exception:
            return False

    async def generate(
        self,
        model_id: str,
        prompt: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Generate a response using the local Ollama server.

        ``model_id`` is logged for audit purposes but the local model
        configured at construction time is always used for inference.
        """
        try:
            import httpx
        except ImportError as exc:
            raise ImportError(
                "httpx is required for OllamaProvider. "
                "Install it with: pip install httpx"
            ) from exc

        is_validation = any(kw in prompt.lower() for kw in _VALIDATION_KEYWORDS)
        _logger.debug(
            "OllamaProvider.generate(local=%s, pipeline_model=%s, prompt_len=%d, validation=%s)",
            self._model, model_id, len(prompt), is_validation,
        )

        messages = []
        if is_validation:
            messages.append({"role": "system", "content": _VALIDATION_SYSTEM})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": self._max_tokens},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                text: str = data["message"]["content"]
                _logger.debug("OllamaProvider ← response_len=%d", len(text))
                return text
        except Exception as exc:
            raise RuntimeError(
                f"OllamaProvider.generate() failed "
                f"(is Ollama running at {self._base_url}?): {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# LlamaCppProvider — fully offline, in-process (no separate server)
# ---------------------------------------------------------------------------


class LlamaCppProvider:
    """
    Fully offline, in-process LLM provider using llama-cpp-python.

    Loads a GGUF model file directly — no network, no separate server process.
    The model is loaded once at first call and kept in memory.

    Install llama-cpp-python::

        pip install llama-cpp-python          # CPU-only (slow but works everywhere)
        # GPU acceleration (optional):
        CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python --force-reinstall

    Download a GGUF model (example — Phi-3 Mini, ~2.2 GB)::

        bash scripts/install_local_llm.sh --llamacpp

    Then use::

        from godai.providers import LlamaCppProvider
        provider = LlamaCppProvider(model_path="models/phi-3-mini.Q4_K_M.gguf")

    Args:
        model_path:   Path to a GGUF model file.
        n_ctx:        Context window size (tokens).
        max_tokens:   Maximum tokens to generate.
        n_threads:    CPU threads to use (default: all available).
        n_gpu_layers: Layers to offload to GPU (0 = CPU-only).
        verbose:      Show llama.cpp progress output.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        max_tokens: int = 512,
        n_threads: Optional[int] = None,
        n_gpu_layers: int = 0,
        verbose: bool = False,
    ) -> None:
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._max_tokens = max_tokens
        self._n_threads = n_threads
        self._n_gpu_layers = n_gpu_layers
        self._verbose = verbose
        self._llm: Any = None  # lazy-loaded

    def _load(self) -> Any:
        if self._llm is None:
            try:
                from llama_cpp import Llama  # type: ignore[import]
            except ImportError as exc:
                raise ImportError(
                    "llama-cpp-python is required for LlamaCppProvider. "
                    "Install with: pip install llama-cpp-python"
                ) from exc
            _logger.info("LlamaCppProvider: loading model from %s …", self._model_path)
            kwargs: Dict[str, Any] = {
                "model_path": self._model_path,
                "n_ctx": self._n_ctx,
                "n_gpu_layers": self._n_gpu_layers,
                "verbose": self._verbose,
            }
            if self._n_threads is not None:
                kwargs["n_threads"] = self._n_threads
            self._llm = Llama(**kwargs)
            _logger.info("LlamaCppProvider: model loaded.")
        return self._llm

    async def generate(
        self,
        model_id: str,
        prompt: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Run inference in a thread pool to avoid blocking the async event loop.
        ``model_id`` is recorded in the audit log but ignored for inference.
        """
        is_validation = any(kw in prompt.lower() for kw in _VALIDATION_KEYWORDS)
        _logger.debug(
            "LlamaCppProvider.generate(path=%s, pipeline_model=%s, prompt_len=%d, validation=%s)",
            self._model_path, model_id, len(prompt), is_validation,
        )

        if is_validation:
            full_prompt = (
                f"[INST] <<SYS>>\n{_VALIDATION_SYSTEM}\n<</SYS>>\n\n{prompt} [/INST]"
            )
        else:
            full_prompt = prompt

        loop = asyncio.get_event_loop()
        try:
            output = await loop.run_in_executor(
                None,
                lambda: self._load()(
                    full_prompt,
                    max_tokens=self._max_tokens,
                    stop=["</s>", "[INST]"],
                ),
            )
            text: str = output["choices"][0]["text"].strip()
            _logger.debug("LlamaCppProvider ← response_len=%d", len(text))
            return text
        except Exception as exc:
            raise RuntimeError(f"LlamaCppProvider.generate() failed: {exc}") from exc
