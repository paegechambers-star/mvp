"""
Concrete LLMProvider implementations for G.O.D.A.I.

Three implementations are provided:

  EchoProvider      — returns the prompt verbatim; validation calls emit a
                      passing JSON verdict.  Use for development and smoke tests.

  LoggingProvider   — wraps any other provider and logs every call with
                      model_id, prompt length, and response length.

  AnthropicProvider — skeleton wired for the Anthropic SDK.  Import the
                      ``anthropic`` package, set an API key, then implement
                      ``generate()`` using the real client.  Raises
                      ``NotImplementedError`` until you fill it in.

Usage::

    from godai.providers import EchoProvider
    from godai.pipeline import GodaiPipeline

    pipeline = GodaiPipeline.create(llm_provider=EchoProvider())
    result = await pipeline.process(...)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

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
    Skeleton provider for the Anthropic Claude API.

    To activate:
      1. ``pip install anthropic``
      2. Set ``ANTHROPIC_API_KEY`` in your environment (or pass ``api_key``)
      3. Fill in the ``generate()`` body below

    Per project policy, no external API calls are made without explicit
    approval.  This class intentionally raises ``NotImplementedError``
    until the ``generate()`` body is implemented.

    Example (after implementing)::

        provider = AnthropicProvider(api_key="sk-ant-...")
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
        """
        Generate a response using the Anthropic Messages API.

        Implement this method with the real SDK call, e.g.:

            client = self._get_client()
            message = await client.messages.create(
                model=model_id,
                max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text

        Raises:
            NotImplementedError: Until the generate() body is implemented.
        """
        raise NotImplementedError(
            "AnthropicProvider.generate() is not yet implemented. "
            "Fill in the SDK call in godai/providers.py and ensure "
            "ANTHROPIC_API_KEY is set."
        )
