"""FraPP-Chat-Werkzeuge: lesen sofort, schreiben nur nach Bestätigung."""

from datetime import date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from frapp import chat_tools as ct
from frapp.models import Event
from frapp.planner.models import Task
from frapp.planner.timesource import BERLIN, Timestamp
from scriptor.audit import AuditLog
from scriptor.chat import ChatError, ChatStore, decide, stream_reply
from scriptor.llm import AgentTurn, FakeLLM

NOW = datetime(2026, 10, 25, 9, 30, tzinfo=BERLIN)  # Sonntag


@pytest.fixture(autouse=True)
def db(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ct, "_engine", lambda: engine)
    monkeypatch.setattr(ct, "now_cached", lambda: Timestamp(NOW, "MEZ", "PTB-basiert (Test)", True))
    return engine


def _event(engine, title, start, end):
    with Session(engine) as s:
        e = Event(title=title, starts_at=start, ends_at=end)
        s.add(e)
        s.commit()
        s.refresh(e)
        return e.id


def _tk():
    return ct.calendar_toolkit()


def _tool(name):
    return next(t for t in _tk().tools if t.name == name)


def test_time_context_names_weekdays():
    ctx = ct.time_context()
    assert "JETZT: Sonntag, 25.10.2026 09:30" in ctx
    assert "Montag = 2026-10-26" in ctx and "PTB-basiert" in ctx


def test_list_events_with_sources(db):
    eid = _event(
        db,
        "Zahnarzt",
        datetime(2026, 10, 27, 14, tzinfo=BERLIN),
        datetime(2026, 10, 27, 15, tzinfo=BERLIN),
    )
    out = ct.list_events({"from_date": "2026-10-26", "to_date": "2026-10-31"})
    assert f"Termin #{eid}: Di 27.10.2026 14:00–15:00 · Zahnarzt" in out and "VERIFIED" in out
    assert "EMPTY-BUT-VERIFIED" in ct.list_events(
        {"from_date": "2026-12-01", "to_date": "2026-12-02"}
    )
    with pytest.raises(ValueError, match="höchstens"):
        ct.list_events({"from_date": "2026-01-01", "to_date": "2026-12-31"})


def test_create_event_proposal_is_deterministic_and_writes_nothing(db):
    _event(
        db,
        "Meeting",
        datetime(2026, 10, 26, 14, 30, tzinfo=BERLIN),
        datetime(2026, 10, 26, 16, tzinfo=BERLIN),
    )
    p = ct.prepare_create_event(
        {"title": "Zahnarzt", "start": "2026-10-26T14:00", "location": "Hauptstraße"}
    )
    assert p.summary == "Termin anlegen: Mo 26.10.2026 14:00–15:00 · Zahnarzt · Hauptstraße"
    assert any("überschneidet sich" in w for w in p.warnings)
    with Session(db) as s:
        assert len(s.exec(select(Event)).all()) == 1  # nichts geschrieben
    result = ct.apply_create_event(p.payload)
    assert "gespeichert" in result
    with Session(db) as s:
        e = s.exec(select(Event).where(Event.title == "Zahnarzt")).one()
        assert e.owner == "frapp-chat"


def test_create_event_validation():
    with pytest.raises(ValueError, match="Titel"):
        ct.prepare_create_event({"start": "2026-10-26T14:00"})
    with pytest.raises(ValueError, match="ISO"):
        ct.prepare_create_event({"title": "x", "start": "morgen 14 Uhr"})
    with pytest.raises(ValueError, match="nach dem Beginn"):
        ct.prepare_create_event(
            {"title": "x", "start": "2026-10-26T14:00", "end": "2026-10-26T13:00"}
        )
    past = ct.prepare_create_event({"title": "x", "start": "2026-10-01T10:00"})
    assert "liegt in der Vergangenheit" in past.warnings
    allday = ct.prepare_create_event({"title": "Urlaub", "start": "2026-10-30", "all_day": True})
    assert allday.summary == "Termin anlegen: Fr 30.10.2026 ganztägig · Urlaub"


def test_dst_switch_keeps_local_time():
    # 29.03.2026 Sommerzeit: 10:00 lokal muss 10:00 bleiben (+02:00)
    p = ct.prepare_create_event({"title": "x", "start": "2026-03-29T10:00"})
    assert p.payload["starts_at"] == "2026-03-29T10:00:00+02:00"


def test_update_moves_and_keeps_duration(db):
    eid = _event(
        db,
        "Call",
        datetime(2026, 10, 26, 9, tzinfo=BERLIN),
        datetime(2026, 10, 26, 9, 45, tzinfo=BERLIN),
    )
    p = ct.prepare_update_event({"event_id": eid, "start": "2026-10-27T11:00"})
    assert "Mo 26.10.2026 09:00–09:45 · Call → Di 27.10.2026 11:00–11:45 · Call" in p.summary
    assert "geändert" in ct.apply_update_event(p.payload)
    with pytest.raises(ValueError, match="Keine Änderung"):
        ct.prepare_update_event({"event_id": eid})
    with pytest.raises(ValueError, match="existiert nicht"):
        ct.prepare_update_event({"event_id": 999, "title": "y"})


def test_delete_and_stale_apply(db):
    eid = _event(
        db,
        "Alt",
        datetime(2026, 10, 26, 9, tzinfo=BERLIN),
        datetime(2026, 10, 26, 10, tzinfo=BERLIN),
    )
    p = ct.prepare_delete_event({"event_id": eid})
    assert p.summary.endswith("LÖSCHEN")
    assert "gelöscht" in ct.apply_delete_event(p.payload)
    with pytest.raises(ValueError, match="existiert nicht mehr"):
        ct.apply_delete_event(p.payload)


def test_create_task(db):
    p = ct.prepare_create_task({"title": "Exposé", "duration_min": 90, "constraint": "hard"})
    assert "HARD ohne feste Uhrzeit" in p.warnings[0]
    p = ct.prepare_create_task(
        {
            "title": "Exposé",
            "duration_min": 90,
            "day": "2026-10-26",
            "domain": "Scriptor",
            "priority": 1,
        }
    )
    assert (
        p.summary
        == "Aufgabe anlegen: Exposé · 90 min · SOFT · Scriptor · Prio 1 · für Mo 26.10.2026"
    )
    assert "gespeichert" in ct.apply_create_task(p.payload)
    with Session(db) as s:
        t = s.exec(select(Task)).one()
        assert t.day == date(2026, 10, 26) and t.certainty.value == "VERIFIED"
    assert "Exposé" in ct.list_tasks({})
    with pytest.raises(ValueError):
        ct.prepare_create_task({"title": "x", "constraint": "MAYBE"})


def test_day_plan_tool(db):
    _event(
        db,
        "Zahnarzt",
        datetime(2026, 10, 25, 14, tzinfo=BERLIN),
        datetime(2026, 10, 25, 15, tzinfo=BERLIN),
    )
    out = ct.day_plan({})
    assert "Tagesplan So 25.10.2026" in out and "Zahnarzt · HARD" in out and "VERIFIED" in out


def test_chat_end_to_end_proposal_flow(tmp_path, db):
    """Modell schlägt vor → Karte → nichts gespeichert → Übernehmen → Termin in DB."""
    turns = [
        AgentTurn(
            content=[{"type": "tool_use", "id": "c1", "name": "create_event", "input": {}}],
            stop_reason="tool_use",
            text="",
            tool_calls=[
                {
                    "id": "c1",
                    "name": "create_event",
                    "input": {"title": "Zahnarzt", "start": "2026-10-26T14:00"},
                }
            ],
        ),
        AgentTurn(content=[], stop_reason="end_turn", text="Bitte bestätigen."),
    ]
    llm = FakeLLM(agent_script=turns, audit=AuditLog())
    store = ChatStore(tmp_path)
    chat = store.create()
    events = list(stream_reply(store, chat["id"], "Morgen 14 Uhr Zahnarzt", llm, "m", [_tk()]))
    kinds = [next(iter(e)) for e in events]
    assert kinds == ["tool", "proposal", "delta", "done"]
    prop = events[1]["proposal"]
    assert (
        prop["summary"].startswith("Termin anlegen: Mo 26.10.2026 14:00–15:00")
        and "payload" not in prop
    )
    # Systemprompt enthält Zeitbasis + Regeln
    system = llm.calls[0]["system"]
    assert "JETZT: Sonntag" in system and "VORSCHLAG" in system
    with Session(db) as s:
        assert s.exec(select(Event)).all() == []
    res = decide(store, chat["id"], prop["id"], True, [_tk()])
    assert res["status"] == "accepted" and "gespeichert" in res["result"]
    with Session(db) as s:
        assert s.exec(select(Event)).one().title == "Zahnarzt"
    with pytest.raises(ChatError, match="bereits accepted"):
        decide(store, chat["id"], prop["id"], True, [_tk()])
    saved = store.get(chat["id"])
    assert (
        saved["messages"][-1]["kind"] == "note" and "übernommen" in saved["messages"][-1]["content"]
    )


def test_tool_errors_go_back_to_model(tmp_path):
    turns = [
        AgentTurn(
            content=[],
            stop_reason="tool_use",
            text="",
            tool_calls=[
                {"id": "c1", "name": "create_event", "input": {"title": "x", "start": "Freitag"}}
            ],
        ),
        AgentTurn(content=[], stop_reason="end_turn", text="Welches Datum genau?"),
    ]
    llm = FakeLLM(agent_script=turns)
    store = ChatStore(tmp_path)
    chat = store.create()
    events = list(stream_reply(store, chat["id"], "Freitag Termin", llm, "m", [_tk()]))
    assert not any("proposal" in e for e in events)
    tool_result = llm.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] and "ISO" in tool_result["content"]
    assert events[-2] == {"delta": "Welches Datum genau?"}


def test_chat_without_tools_streams(tmp_path):
    llm = FakeLLM({"chat": lambda s, p: "Hallo"})
    store = ChatStore(tmp_path)
    chat = store.create(tools=False)
    events = list(stream_reply(store, chat["id"], "Hi", llm, "m", [_tk()]))
    assert events[0] == {"delta": "Hallo "} and llm.calls[0]["role"] == "chat"
