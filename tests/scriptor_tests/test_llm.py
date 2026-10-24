from types import SimpleNamespace as NS

import pytest

from scriptor.audit import AuditLog
from scriptor.llm import AnthropicLLM, LLMError


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class _Client:
    def __init__(self, msg):
        self.msg = msg
        self.params = None
        self.beta = NS(messages=NS(stream=self._stream, create=self._create))

    def _stream(self, **params):
        self.params = params
        return _Stream(self.msg)

    def _create(self, **params):
        self.params = params
        return self.msg


def _msg(text, stop="end_turn"):
    usage = NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0)
    return NS(
        content=[NS(type="text", text=text)],
        stop_reason=stop,
        model="m",
        usage=usage,
        stop_details=NS(category="cyber"),
    )


def test_complete_sends_current_api_shape():
    client = _Client(_msg("Hallo"))
    audit = AuditLog()
    llm = AnthropicLLM(audit, client=client)
    assert llm.complete("draft", "sys", "prompt", effort="high") == "Hallo"
    p = client.params
    assert p["model"] == "claude-opus-5-5"
    assert p["thinking"] == {"type": "adaptive"}
    assert p["output_config"] == {"effort": "high"}
    assert p["fallbacks"] == "default" and p["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in p and "budget_tokens" not in str(p)
    assert audit.entries[-1]["data"]["role"] == "draft"


def test_complete_json_and_errors():
    llm = AnthropicLLM(AuditLog(), client=_Client(_msg('{"a": 1}')))
    assert llm.complete_json("x", "s", "p", {"type": "object"}) == {"a": 1}
    with pytest.raises(LLMError, match="abgelehnt"):
        AnthropicLLM(AuditLog(), client=_Client(_msg("", "refusal"))).complete("x", "s", "p")
    with pytest.raises(LLMError, match="max_tokens"):
        AnthropicLLM(AuditLog(), client=_Client(_msg("..", "max_tokens"))).complete("x", "s", "p")
    with pytest.raises(LLMError, match="JSON"):
        AnthropicLLM(AuditLog(), client=_Client(_msg("kein json"))).complete_json("x", "s", "p", {})


def test_agent_turn_extracts_tool_calls():
    msg = _msg("ok", "tool_use")
    msg.content.append(NS(type="tool_use", id="t1", name="list_books", input={}))
    client = _Client(msg)
    turn = AnthropicLLM(AuditLog(), client=client).agent_turn(
        "s", [{"role": "user", "content": "x"}], []
    )
    assert turn.tool_calls == [{"id": "t1", "name": "list_books", "input": {}}]
    assert "tool_choice" not in client.params
