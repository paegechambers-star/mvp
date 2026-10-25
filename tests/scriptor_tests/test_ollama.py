"""OllamaLLM gegen einen simulierten Ollama-Server (httpx.MockTransport, kein Netz)."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from scriptor.agent import Agent
from scriptor.app.jobs import JobManager
from scriptor.app.server import create_app
from scriptor.audit import AuditLog
from scriptor.llm import LLMError, OllamaLLM, ollama_status
from scriptor.runtime import Runtime, default_factory
from scriptor.settings import Settings


def _client(handler):
    return httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(handler))


def _reply(content="", tool_calls=None, done_reason="stop"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return httpx.Response(
        200,
        json={"message": msg, "done_reason": done_reason, "prompt_eval_count": 7, "eval_count": 3},
    )


def test_complete_sends_system_ctx_and_strips_thinking():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return _reply("<think>intern</think>\nKapiteltext.")

    audit = AuditLog()
    llm = OllamaLLM(audit, model="qwen3:8b", num_ctx=8192, client=_client(handler))
    assert llm.complete("draft", "SYS", "Schreib!", max_tokens=64000) == "Kapiteltext."
    assert seen["model"] == "qwen3:8b" and seen["stream"] is False
    assert seen["messages"][0] == {"role": "system", "content": "SYS"}
    assert seen["options"] == {"num_ctx": 8192, "num_predict": 8192}
    entry = audit.entries[-1]["data"]
    assert entry["model"] == "ollama:qwen3:8b" and entry["input_tokens"] == 7


def test_complete_json_uses_schema_format_and_recovers_wrapped_json():
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return _reply('Hier: {"ok": true} fertig')

    llm = OllamaLLM(AuditLog(), client=_client(handler))
    assert llm.complete_json("review", "S", "P", schema) == {"ok": True}
    assert seen["format"] == schema


def test_errors_are_actionable():
    llm = OllamaLLM(AuditLog(), model="fehlt:1b", client=_client(lambda r: httpx.Response(404)))
    with pytest.raises(LLMError, match="ollama pull fehlt:1b"):
        llm.complete("draft", "S", "P")

    def down(req):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError, match="nicht erreichbar"):
        OllamaLLM(AuditLog(), client=_client(down)).complete("draft", "S", "P")

    cut = OllamaLLM(AuditLog(), client=_client(lambda r: _reply("abc", done_reason="length")))
    with pytest.raises(LLMError, match="abgeschnitten"):
        cut.complete("draft", "S", "P")


def test_agent_turn_translates_tools_and_history(tmp_path):
    requests = []
    answers = [
        _reply(
            "Ich lege an.",
            tool_calls=[{"function": {"name": "list_books", "arguments": {}}}],
        ),
        _reply("Keine Bücher vorhanden."),
    ]

    def handler(req):
        requests.append(json.loads(req.content))
        return answers.pop(0)

    llm = OllamaLLM(AuditLog(), client=_client(handler))
    agent = Agent(llm, tmp_path / "ws", web_search=True)
    assert agent.run("Welche Bücher gibt es?") == "Keine Bücher vorhanden."

    first, second = requests
    names = {t["function"]["name"] for t in first["tools"]}
    assert "list_books" in names and "web_search" not in names  # serverseitig: lokal nicht
    assert all(t["type"] == "function" for t in first["tools"])
    roles = [m["role"] for m in second["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert second["messages"][2]["tool_calls"][0]["function"]["name"] == "list_books"
    assert second["messages"][3]["tool_name"] == "list_books"


def test_agent_turn_parses_string_arguments():
    call = {"function": {"name": "read_book", "arguments": '{"slug": "x"}'}}
    llm = OllamaLLM(AuditLog(), client=_client(lambda r: _reply("", tool_calls=[call])))
    turn = llm.agent_turn("S", [{"role": "user", "content": "lies"}], [])
    assert turn.stop_reason == "tool_use"
    assert turn.tool_calls[0]["input"] == {"slug": "x"}


def test_ollama_status():
    def handler(req):
        if req.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.12.0"})
        return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}, {"name": "a:1b"}]})

    st = ollama_status("http://ollama.test", client=_client(handler))
    assert st == {
        "reachable": True,
        "url": "http://ollama.test",
        "version": "0.12.0",
        "models": ["a:1b", "qwen3:8b"],
    }

    def down(req):
        raise httpx.ConnectError("refused")

    assert ollama_status("http://x", client=_client(down))["reachable"] is False


def test_runtime_switches_provider_without_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    s = Settings(workspace=str(tmp_path / "ws"), governance=False)
    rt = Runtime.create(s, include_entry_points=False)
    assert rt.llm_factory is default_factory
    assert type(rt.llm()).__name__ == "AnthropicLLM"
    s.provider, s.ollama_model = "ollama", "qwen3:4b"
    llm = rt.llm()
    assert isinstance(llm, OllamaLLM) and llm.model == "ollama:qwen3:4b"
    assert s.active_model() == "ollama:qwen3:4b"


def test_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("SCRIPTOR_PROVIDER", "ollama")
    monkeypatch.setenv("SCRIPTOR_OLLAMA_MODEL", "llama3.1:8b")
    s = Settings.load()
    assert s.provider == "ollama" and s.ollama_model == "llama3.1:8b"


def test_server_settings_and_ollama_endpoint(tmp_path, monkeypatch):
    import scriptor.llm as llm_mod

    monkeypatch.setattr(
        llm_mod, "ollama_status", lambda url: {"reachable": False, "url": url, "error": "x"}
    )
    rt = Runtime.create(
        Settings(workspace=str(tmp_path / "ws")),
        llm_factory=lambda rt: None,
        include_entry_points=False,
    )
    client = TestClient(create_app(rt, "t", JobManager()))
    h = {"X-Scriptor-Token": "t"}
    r = client.put(
        "/api/settings", json={"provider": "ollama", "ollama_model": "qwen3:4b"}, headers=h
    )
    assert r.status_code == 200
    info = client.get("/api/info", headers=h).json()
    assert info["provider"] == "ollama" and info["model"] == "ollama:qwen3:4b"
    assert Settings.load().provider == "ollama"  # gespeichert
    assert client.put("/api/settings", json={"provider": "gpt"}, headers=h).status_code == 422
    o = client.get("/api/ollama", headers=h).json()
    assert o["reachable"] is False and o["model"] == "qwen3:4b"
    bad = client.post("/api/ollama/pull", json={"model": "x; rm -rf /"}, headers=h)
    assert bad.status_code == 422
