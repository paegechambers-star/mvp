import pytest

from scriptor.ghostwriter import Ghostwriter
from scriptor.governance import GodaiGovernance, GovernedLLM, PolicyDenied
from scriptor.project import BookProject

from .conftest import make_llm


def test_allowed_call_is_audited_in_mnemosyne(project):
    gov = GodaiGovernance()
    llm = GovernedLLM(make_llm(), gov)
    Ghostwriter(llm).develop_bible(project)
    st = gov.status()
    assert st["decisions"] == {"allowed": 1, "denied": 0}
    assert st["chain_ok"] and st["entries"] >= 3  # HERMES auth + THEMIS policy + Ergebnis
    modules = {e["module"] for e in st["recent"]}
    assert {"HERMES", "THEMIS", "PIPELINE"} <= modules
    assert llm.data_class == "INTERNAL" and llm.book == project.slug


def test_memoir_is_sensitive_and_denied_below_l2(workspace):
    p = BookProject.create(workspace, "Leben", "memoir", "x")
    inner = make_llm()
    low = GovernedLLM(inner, GodaiGovernance(token="basic-low"))  # L1 < L2
    with pytest.raises(PolicyDenied, match="THEMIS"):
        Ghostwriter(low).develop_bible(p)
    assert low.data_class == "SENSITIVE"
    assert not any(c["role"] == "bible" for c in inner.calls)  # Modell nie aufgerufen
    ok = GovernedLLM(make_llm(), GodaiGovernance())  # elevated- → L2
    Ghostwriter(ok).develop_bible(p)


def test_rate_limit_and_failures_recorded(project):
    gov = GodaiGovernance(rate_limit=1)
    llm = GovernedLLM(make_llm(), gov)
    llm.complete("x", "s", "p")
    with pytest.raises(PolicyDenied, match="HERMES"):
        llm.complete("x", "s", "p")

    class Boom:
        model = "boom"

        def complete(self, *a, **k):
            raise RuntimeError("API down")

    gov2 = GodaiGovernance()
    with pytest.raises(RuntimeError):
        GovernedLLM(Boom(), gov2).complete("draft", "s", "p")
    assert any(e["type"] == "pipeline_error" for e in gov2.status()["recent"])


def test_parallel_threads_share_one_chain(project):
    import threading

    gov = GodaiGovernance()
    llm = GovernedLLM(make_llm(), gov)
    threads = [threading.Thread(target=lambda: [llm.complete("x", "s", "p") for _ in range(10)])
               for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    st = gov.status()
    assert st["decisions"]["allowed"] == 40 and st["chain_ok"]
