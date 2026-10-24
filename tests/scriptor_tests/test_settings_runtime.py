import sys
import types

from scriptor import settings as st
from scriptor.runtime import Runtime


def test_settings_roundtrip_and_workspace_precedence(tmp_path, monkeypatch):
    s = st.Settings.load()
    assert s.model == "claude-opus-5-5"
    s.workspace = str(tmp_path / "ws")
    s.enabled_plugins = ["a"]
    s.save()
    assert st.Settings.path().parent == tmp_path / "config"
    s2 = st.Settings.load()
    assert s2.workspace_path() == (tmp_path / "ws").resolve() and s2.enabled_plugins == ["a"]
    monkeypatch.setenv("SCRIPTOR_HOME", str(tmp_path / "env"))
    assert st.Settings.load().workspace_path() == (tmp_path / "env").resolve()


def test_api_key_never_in_settings_file(tmp_path, monkeypatch):
    store = {}
    fake = types.SimpleNamespace(
        get_password=lambda s, u: store.get((s, u)),
        set_password=lambda s, u, p: store.__setitem__((s, u), p),
        delete_password=lambda s, u: store.pop((s, u), None),
    )
    monkeypatch.setitem(sys.modules, "keyring", fake)
    assert st.api_key_status() == "missing"
    assert st.set_api_key("sk-ant-test")
    assert st.get_api_key() == "sk-ant-test" and st.api_key_status() == "keyring"
    st.Settings.load().save()
    assert "sk-ant" not in st.Settings.path().read_text()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert st.get_api_key() == "sk-env" and st.api_key_status() == "env"


def test_no_keyring_reports_false(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)
    assert st.set_api_key("x") is False and st.get_api_key() is None


def test_runtime_uses_settings(tmp_path):
    s = st.Settings(workspace=str(tmp_path / "w"))
    rt = Runtime.create(s, llm_factory=lambda rt: "LLM", include_entry_points=False)
    assert rt.workspace.exists() and rt.llm().inner == "LLM"  # von G.O.D.A.I. umhüllt
    s.governance = False
    raw = Runtime.create(s, llm_factory=lambda rt: "LLM", include_entry_points=False)
    assert raw.governance is None and raw.llm() == "LLM"
    assert any(i.name == "lesbarkeit" for i in rt.docks.infos)
