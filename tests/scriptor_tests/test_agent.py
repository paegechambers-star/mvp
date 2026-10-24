from scriptor.agent import Agent
from scriptor.llm import AgentTurn

from .conftest import make_llm


def _call(i, name, **inp):
    return {"id": f"t{i}", "name": name, "input": inp}


def _turn(*calls, text=""):
    content = [{"type": "tool_use", **c} for c in calls]
    return AgentTurn(content=content, stop_reason="tool_use", text=text, tool_calls=list(calls))


def _results(llm):
    out = []
    for m in llm.calls[-1]["messages"]:
        if m["role"] == "user" and isinstance(m["content"], list):
            out.extend(m["content"])
    return out


def test_agent_runs_book_tools(workspace):
    llm = make_llm(n_chapters=2)
    llm._script = [
        _turn(_call(1, "create_book", title="Test Buch", genre="kinderroman", idea="Drache")),
        _turn(_call(2, "develop_bible", slug="test-buch"), _call(3, "list_books")),
        _turn(_call(4, "book_material", slug="test-buch", kind="klappentext")),
        AgentTurn(content=[{"type": "text", "text": "Erledigt."}], stop_reason="end_turn", text="Erledigt."),
    ]
    agent = Agent(llm, workspace)
    assert agent.run("Leg ein Buch an") == "Erledigt."
    results = _results(llm)
    assert not any(r["is_error"] for r in results), results
    assert len([r for r in results if r["tool_use_id"] in ("t2", "t3")]) == 2  # parallel in 1 Message
    assert (workspace / "books/test-buch/export/klappentext.md").exists()


def test_agent_blocks_path_escape_and_ssot_writes(workspace):
    llm = make_llm()
    llm._script = [
        _turn(_call(1, "read_file", path="../../etc/passwd")),
        _turn(_call(2, "create_book", title="B", genre="roman", idea="x")),
        _turn(_call(3, "write_file", path="books/b/ssot/bible.yaml", content="hack")),
        _turn(_call(4, "write_file", path="notes/a.md", content="eins"),
              _call(5, "write_file", path="notes/a.md", content="zwei")),
    ]
    agent = Agent(llm, workspace)
    agent.run("x")
    res = {r["tool_use_id"]: r for r in _results(llm)}
    assert res["t1"]["is_error"] and "außerhalb" in res["t1"]["content"]
    assert res["t3"]["is_error"]
    assert (workspace / "notes/a.md").read_text() == "eins"
    assert (workspace / "notes/a.v2.md").read_text() == "zwei"


def test_agent_respects_denied_approval(workspace):
    llm = make_llm()
    llm._script = [
        _turn(_call(1, "create_book", title="C", genre="roman", idea="x")),
        _turn(_call(2, "develop_bible", slug="c")),
    ]
    agent = Agent(llm, workspace, approve=lambda name, args: False)
    agent.run("x")
    res = {r["tool_use_id"]: r for r in _results(llm)}
    assert not res["t1"]["is_error"]
    assert res["t2"]["is_error"] and "abgelehnt" in res["t2"]["content"]
    assert not any(c["role"] == "bible" for c in llm.calls)


def test_update_bible_and_unknown_tool(workspace):
    llm = make_llm()
    llm._script = [
        _turn(_call(1, "create_book", title="D", genre="roman", idea="x")),
        _turn(_call(2, "update_bible", slug="d", patch_yaml="tone: düster", reason="Autorwunsch"),
              _call(3, "update_bible", slug="d", patch_yaml="meta: {}", reason="x"),
              _call(4, "rm_rf")),
    ]
    agent = Agent(llm, workspace)
    agent.run("x")
    res = {r["tool_use_id"]: r for r in _results(llm)}
    assert not res["t2"]["is_error"]
    assert res["t3"]["is_error"] and res["t4"]["is_error"]


def test_web_search_tool_optional(workspace):
    assert all(t["name"] != "web_search" for t in Agent(make_llm(), workspace).tools)
    assert Agent(make_llm(), workspace, web_search=True).tools[-1]["type"] == "web_search_20260209"
