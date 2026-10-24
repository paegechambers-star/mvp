import shutil
from pathlib import Path

import pytest

from scriptor.agent import Agent
from scriptor.docks import Dock, DockRegistry, discover
from scriptor.genres import list_genre_ids, load_genre
from scriptor.llm import AgentTurn

from .conftest import make_llm

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "scriptor_plugins"


def _plugin_dir(tmp_path):
    d = tmp_path / "plugins"
    shutil.copytree(EXAMPLES, d)
    return d


def test_builtin_docks_load():
    reg = discover(include_entry_points=False)
    names = {i.name: i for i in reg.infos}
    assert names["lesbarkeit"].loaded
    assert "readability" in reg.tools
    assert "lesbarkeit" in reg.cli and reg.routers


def test_folder_plugin_requires_explicit_enable(tmp_path):
    d = _plugin_dir(tmp_path)
    reg = discover(plugin_dir=d, enabled_plugins=[], include_entry_points=False)
    info = next(i for i in reg.infos if i.name == "kurzgeschichte")
    assert not info.loaded and "nicht freigegeben" in info.error
    assert "word_repetitions" not in reg.tools
    assert "kurzgeschichte" not in list_genre_ids()


def test_folder_plugin_contributes_tool_genre_material(tmp_path, workspace):
    d = _plugin_dir(tmp_path)
    reg = discover(plugin_dir=d, enabled_plugins=["kurzgeschichte"], include_entry_points=False)
    assert "word_repetitions" in reg.tools
    assert load_genre("kurzgeschichte").unit_label == "Szene"
    assert reg.materials["pitch_tweet"]

    llm = make_llm()
    call = {"id": "t2", "name": "word_repetitions", "input": {"slug": "k", "nr": 1}}
    llm._script = [
        AgentTurn([], "tool_use", "", [{"id": "t1", "name": "create_book",
                                         "input": {"title": "K", "genre": "kurzgeschichte", "idea": "x"}}]),
        AgentTurn([], "tool_use", "", [call]),
    ]
    agent = Agent(llm, workspace, docks=reg)
    assert any(t["name"] == "word_repetitions" for t in agent.tools)
    agent.run("x")
    from scriptor.project import BookProject

    p = BookProject.load(workspace, "k")
    p.commit_ssot("outline", {"chapters": [{"nr": 1, "title": "A", "words_target": 500}]}, "t", "SUPERSEDE")
    p.write_chapter(1, "Der Nebel kroch. Der Nebel stieg. Der Nebel fiel. " * 3, "t")
    out, err = agent._execute("word_repetitions", {"slug": "k", "nr": 1})
    assert not err and "nebel" in out


class _Broken(Dock):
    name = "kaputt"

    def load(self, registry: DockRegistry) -> bool:
        registry.add_material("halb", "registriert, dann Absturz")
        raise RuntimeError("boom")


class _Clash(Dock):
    name = "clash"

    def load(self, registry: DockRegistry) -> bool:
        registry.add_tool("list_books", "überschreibt eingebautes Werkzeug", {"type": "object"},
                          lambda agent: "x")
        return True


class _Crashy(Dock):
    name = "crashy"

    def load(self, registry: DockRegistry) -> bool:
        def tool(agent):
            raise ZeroDivisionError("plugin bug")

        registry.add_tool("crash", "stürzt ab", {"type": "object", "properties": {}}, tool)
        return True


def test_broken_dock_is_isolated_and_rolled_back():
    reg = DockRegistry()
    info = reg.load_dock(_Broken(), "test")
    assert not info.loaded and "boom" in info.error
    assert "halb" not in reg.materials  # Teilregistrierung zurückgerollt


def test_dock_cannot_shadow_builtin_tool(workspace):
    reg = DockRegistry()
    reg.load_dock(_Clash(), "test")
    with pytest.raises(ValueError, match="überschreiben"):
        Agent(make_llm(), workspace, docks=reg)


def test_plugin_crash_returns_tool_error(workspace):
    reg = DockRegistry()
    reg.load_dock(_Crashy(), "test")
    out, err = Agent(make_llm(), workspace, docks=reg)._execute("crash", {})
    assert err and "crashy" in out


def test_entry_point_and_disable(monkeypatch):
    class _EP:
        name = "ep"

        def load(self):
            return _Crashy

    monkeypatch.setattr("scriptor.docks.metadata.entry_points", lambda group: [_EP()])
    reg = discover()
    assert "crash" in reg.tools
    reg = discover(disabled=["crashy", "lesbarkeit"])
    assert "crash" not in reg.tools and "readability" not in reg.tools


def test_invalid_tool_name_rejected():
    reg = DockRegistry()
    with pytest.raises(ValueError):
        reg.add_tool("not valid", "x", {}, lambda a: "")


def test_readability_tool(project):
    from scriptor.docks.builtin import interpret, readability

    r = readability("Der Hund läuft. Die Katze schläft. Alles ist gut.")
    assert r["flesch_amstad"] > 65 and interpret(r["flesch_amstad"]).startswith(("sehr", "leicht"))
