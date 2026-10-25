"""Freier Chat: Speicher, Streaming-Endpunkt, Governance, Abbruch, Ollama-Stream."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from scriptor.app.jobs import JobManager
from scriptor.app.server import create_app
from scriptor.audit import AuditLog
from scriptor.chat import ChatError, ChatNotFound, ChatStore, stream_reply
from scriptor.llm import FakeLLM, LLMError, OllamaLLM, _ThinkFilter
from scriptor.runtime import Runtime
from scriptor.settings import Settings

H = {"X-Scriptor-Token": "t"}


def _app(tmp_path, llm, governance=False):
    rt = Runtime.create(
        Settings(workspace=str(tmp_path / "ws"), governance=governance),
        llm_factory=lambda rt: llm,
        include_entry_points=False,
    )
    return TestClient(create_app(rt, "t", JobManager())), rt


def _events(resp):
    return [json.loads(line) for line in resp.text.splitlines() if line]


def test_chat_roundtrip_via_api(tmp_path):
    llm = FakeLLM({"chat": lambda system, prompt: f"Antwort auf {prompt}"})
    client, _ = _app(tmp_path, llm)
    chat = client.post("/api/chats", json={"data_class": "PUBLIC"}, headers=H).json()
    r = client.post(f"/api/chats/{chat['id']}/messages", json={"text": "Hallo"}, headers=H)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    ev = _events(r)
    assert "".join(e.get("delta", "") for e in ev).strip() == "Antwort auf Hallo"
    assert ev[-1] == {"done": True, "model": "claude-opus-5-5"}
    saved = client.get(f"/api/chats/{chat['id']}", headers=H).json()
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert saved["title"] == "Hallo"
    listing = client.get("/api/chats", headers=H).json()
    assert listing[0]["id"] == chat["id"] and listing[0]["n"] == 2
    # zweite Runde: Verlauf geht mit
    client.post(f"/api/chats/{chat['id']}/messages", json={"text": "Und?"}, headers=H)
    assert llm.calls[-1]["prompt"] == "Und?"
    assert client.delete(f"/api/chats/{chat['id']}", headers=H).status_code == 200
    assert client.get(f"/api/chats/{chat['id']}", headers=H).status_code == 404


def test_chat_validation(tmp_path):
    client, _ = _app(tmp_path, FakeLLM())
    assert client.post("/api/chats", json={"data_class": "GEHEIM"}, headers=H).status_code == 400
    assert client.get("/api/chats/../../etc", headers=H).status_code == 404
    assert client.get("/api/chats/zzzzzzzzzzzz", headers=H).status_code == 400
    assert (
        client.post("/api/chats/abcdefabcdef/messages", json={"text": "x"}, headers=H).status_code
        == 404
    )
    assert client.get("/api/chats").status_code == 401


def test_error_mid_stream_keeps_partial_reply(tmp_path):
    class Broken(FakeLLM):
        def chat_stream(self, system, messages, *, max_tokens=8000):
            yield "Teil "
            raise LLMError("[chat] Modell weg")

    store = ChatStore(tmp_path)
    chat = store.create()
    ev = list(stream_reply(store, chat["id"], "Hi", Broken(), "m"))
    assert ev[-1] == {"error": "[chat] Modell weg"}
    last = store.get(chat["id"])["messages"][-1]
    assert last["content"] == "Teil" and last["incomplete"] is True


def test_abort_saves_partial_and_closes_model_stream(tmp_path):
    closed = []

    class Slow(FakeLLM):
        def chat_stream(self, system, messages, *, max_tokens=8000):
            try:
                yield "Eins "
                yield "Zwei "
                yield "Drei"
            finally:
                closed.append(True)

    store = ChatStore(tmp_path)
    chat = store.create()
    gen = stream_reply(store, chat["id"], "Zähl", Slow(), "m")
    assert next(gen) == {"delta": "Eins "}
    gen.close()
    assert closed == [True]
    last = store.get(chat["id"])["messages"][-1]
    assert last["content"] == "Eins" and last["incomplete"] is True


def test_governance_checks_and_records_chat(tmp_path):
    pytest.importorskip("godai")
    client, rt = _app(tmp_path, FakeLLM(), governance=True)
    chat = client.post("/api/chats", json={}, headers=H).json()
    ev = _events(client.post(f"/api/chats/{chat['id']}/messages", json={"text": "Hi"}, headers=H))
    assert ev[-1].get("done") is True
    status = rt.governance.status()
    assert status["decisions"]["allowed"] >= 1 and status["chain_ok"]


def test_store_errors(tmp_path):
    store = ChatStore(tmp_path)
    with pytest.raises(ChatNotFound):
        store.get("abcdefabcdef")
    with pytest.raises(ChatError):
        stream_reply(store, store.create()["id"], "   ", FakeLLM(), "m").__next__()


def test_think_filter_across_chunks():
    f = _ThinkFilter()
    out = (
        "".join(f.feed(c) for c in ["Hal", "lo <th", "ink>geheim</th", "ink> Welt", "<"])
        + f.flush()
    )
    assert out == "Hallo  Welt<"


def test_ollama_chat_stream():
    lines = [
        {"message": {"content": "<think>x</think>"}, "done": False},
        {"message": {"content": "Hallo "}, "done": False},
        {"message": {"content": "Welt"}, "done": True, "done_reason": "stop", "eval_count": 2},
    ]
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        body = "\n".join(json.dumps(x) for x in lines) + "\n"
        return httpx.Response(200, content=body.encode())

    audit = AuditLog()
    client = httpx.Client(base_url="http://o.test", transport=httpx.MockTransport(handler))
    llm = OllamaLLM(audit, client=client)
    out = "".join(llm.chat_stream("SYS", [{"role": "user", "content": "Hi"}]))
    assert out == "Hallo Welt"
    assert seen["stream"] is True and seen["messages"][0]["role"] == "system"
    assert audit.entries[-1]["data"]["role"] == "chat"

    down = OllamaLLM(
        AuditLog(),
        client=httpx.Client(
            base_url="http://o.test",
            transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))),
        ),
    )
    with pytest.raises(LLMError, match="Verbindung zu Ollama"):
        list(down.chat_stream("S", [{"role": "user", "content": "Hi"}]))
    missing = OllamaLLM(
        AuditLog(),
        client=httpx.Client(
            base_url="http://o.test", transport=httpx.MockTransport(lambda r: httpx.Response(404))
        ),
    )
    with pytest.raises(LLMError, match="ollama pull"):
        list(missing.chat_stream("S", [{"role": "user", "content": "Hi"}]))
