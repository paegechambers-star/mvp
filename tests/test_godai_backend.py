"""G.O.D.A.I.-Backendwahl: Echo / Claude / Ollama, SSOT = SCRIPTOR-Einstellung."""

import pytest

from frapp import godai_router as gr
from frapp.settings import settings


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    monkeypatch.setenv("SCRIPTOR_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("SCRIPTOR_PROVIDER", raising=False)
    monkeypatch.setattr(settings, "llm_provider", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(gr, "_pipeline", None)
    monkeypatch.setattr(gr, "_pipeline_key", None)


def _provider_type() -> str:
    return type(gr._get_pipeline()._llm_provider).__name__


def test_default_is_echo_without_key():
    assert _provider_type() == "EchoProvider"
    assert gr._provider_label(gr._backend()) == "EchoProvider"


def test_anthropic_with_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    assert _provider_type() == "AnthropicProvider"


def test_follows_scriptor_setting_and_rebuilds_on_switch():
    from scriptor.settings import Settings

    first = gr._get_pipeline()
    s = Settings(provider="ollama", ollama_model="qwen3:4b")
    s.save()
    pipeline = gr._get_pipeline()
    assert pipeline is not first
    assert type(pipeline._llm_provider).__name__ == "OllamaProvider"
    assert pipeline._llm_provider.model == "qwen3:4b"
    assert gr._provider_label(gr._backend()) == "OllamaProvider (qwen3:4b)"
    assert gr._get_pipeline() is pipeline  # unverändert -> kein Neuaufbau


def test_env_override_wins(monkeypatch):
    from scriptor.settings import Settings

    Settings(provider="ollama").save()
    monkeypatch.setattr(settings, "llm_provider", "echo")
    assert _provider_type() == "EchoProvider"
