"""Tagesplaner: Truth-Gate, 4D-Matrix, PTB-Zeit, API."""

from __future__ import annotations

import struct
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from frapp.planner import timesource
from frapp.planner.engine import build_day_plan
from frapp.planner.timesource import BERLIN, Timestamp

DAY = date(2026, 10, 26)  # Montag, MEZ (nach Zeitumstellung)


def stamp(hour=6, verified=True, day=DAY):
    dt = datetime.combine(day, time(hour, 0), BERLIN)
    return Timestamp(dt, "MEZ", "PTB-basiert (Test)" if verified else "Fallback: Systemuhr", verified)


def ev(i, h1, h2, title="Termin", all_day=False, day=DAY):
    return NS(id=i, title=title, location=None, all_day=all_day,
              starts_at=datetime.combine(day, time(h1), BERLIN).astimezone(timezone.utc),
              ends_at=datetime.combine(day, time(h2), BERLIN).astimezone(timezone.utc))


def task(i, minutes=60, constraint="SOFT", prio=2, fixed=None, certainty="VERIFIED", done=False):
    return NS(id=i, title=f"Aufgabe {i}", duration_min=minutes, constraint=constraint, domain="Arbeit",
              fixed_start=fixed, due=None, priority=prio, source="Nutzereingabe",
              certainty=certainty, done=done)


def test_empty_day_is_empty_but_verified_not_invented():
    plan = build_day_plan(DAY, [], [], stamp())
    gate = {g["source"]: g["status"] for g in plan.truth_gate}
    assert gate["FraPP-Kalender"] == "EMPTY-BUT-VERIFIED"
    assert gate["FraPP-Aufgaben"] == "EMPTY-BUT-VERIFIED"
    assert gate["Zeitbasis"] == "VERIFIED"
    assert plan.rows == [] and plan.free_minutes == 15 * 60  # 07–22 Uhr


def test_events_are_hard_verified_with_source():
    plan = build_day_plan(DAY, [ev(7, 9, 10, "Zahnarzt")], [], stamp())
    [row] = plan.rows
    assert (row.constraint, row.certainty, row.time_basis) == ("HARD", "VERIFIED", "Quelle")
    assert "Termin #7" in row.source and row.start.startswith("2026-10-26T09:00")
    assert {g["source"]: g["status"] for g in plan.truth_gate}["FraPP-Kalender"] == "VERIFIED"


def test_soft_tasks_fill_gaps_by_priority_and_are_marked_assumption():
    events = [ev(1, 7, 9), ev(2, 10, 12)]
    tasks = [task(1, 60, prio=3), task(2, 60, prio=1), task(3, 90, constraint="FLOAT", prio=1)]
    plan = build_day_plan(DAY, events, tasks, stamp())
    by_ref = {r.ref: r for r in plan.rows}
    assert by_ref["task:2"].start.startswith("2026-10-26T09:00")  # Prio 1 zuerst in Lücke 9–10
    assert by_ref["task:1"].start.startswith("2026-10-26T12:00")
    assert by_ref["task:3"].start.startswith("2026-10-26T13:00")  # FLOAT nach SOFT
    assert all(by_ref[f"task:{i}"].time_basis == "Vorschlag (ASSUMPTION)" for i in (1, 2, 3))
    assert [r.start for r in plan.rows] == sorted(r.start for r in plan.rows)


def test_hard_task_fixed_time_and_conflict_detected():
    fixed = datetime.combine(DAY, time(9, 30), BERLIN)
    plan = build_day_plan(DAY, [ev(1, 9, 10)], [task(5, 60, "HARD", fixed=fixed)], stamp())
    assert {r.ref for r in plan.rows} == {"event:1", "task:5"}
    assert plan.conflicts == [{"a": "event:1", "b": "task:5", "overlap_min": 30}]


def test_unplaced_with_reason_and_done_ignored():
    tasks = [task(1, 700), task(2, done=True)]
    plan = build_day_plan(DAY, [], tasks, stamp(), day_start=time(8), day_end=time(18))
    assert plan.rows == []
    assert plan.unplaced[0]["ref"] == "task:1" and "Lücke" in plan.unplaced[0]["reason"]


def test_today_starts_after_now_and_all_day_event():
    plan = build_day_plan(DAY, [ev(9, 0, 23, "Urlaub", all_day=True)], [task(1, 30)], stamp(hour=14))
    allday = next(r for r in plan.rows if r.ref == "event:9")
    assert allday.start is None and allday.time_basis == "ganztägig"
    t = next(r for r in plan.rows if r.ref == "task:1")
    assert t.start.startswith("2026-10-26T14:00")  # nicht vor jetzt


def test_external_sources_are_unverified_and_fallback_time_flagged():
    plan = build_day_plan(DAY, [], [], stamp(verified=False), external={"Google Calendar": "nicht verbunden"})
    gate = {g["source"]: g for g in plan.truth_gate}
    assert gate["Google Calendar"]["status"] == "UNVERIFIED"
    assert gate["Zeitbasis"]["status"] == "UNVERIFIED" and "Fallback" in gate["Zeitbasis"]["detail"]


def test_dst_change_day_is_handled():
    """29.03.2026: Umstellung auf MESZ — Lücken dürfen nicht verrutschen."""
    d = date(2026, 3, 29)
    plan = build_day_plan(d, [ev(1, 7, 8, day=d)], [task(1, 60)], stamp(hour=6, day=d))
    t = next(r for r in plan.rows if r.ref == "task:1")
    assert t.start == "2026-03-29T08:00+02:00"


# ── Zeitquelle ──────────────────────────────────────────────────────────────

def test_ptb_time_used_when_reachable(monkeypatch):
    fixed_unix = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc).timestamp()
    ts = timesource.now(ntp=lambda server: fixed_unix)
    assert ts.verified and ts.zone == "MESZ" and "ptbtime1.ptb.de" in ts.method
    assert ts.berlin.hour == 12  # 10 UTC = 12 MESZ


def test_fallback_when_ptb_unreachable():
    def fail(server):
        raise OSError("timeout")

    ts = timesource.now(ntp=fail)
    assert not ts.verified and ts.method.startswith("Fallback")
    assert ts.zone in ("MEZ", "MESZ")


def test_ntp_packet_parsing(monkeypatch):
    unix = 1_800_000_000.5
    secs = int(unix) + 2208988800
    reply = b"\x1c" + b"\0" * 39 + struct.pack("!II", secs, int(0.5 * 2**32))

    class FakeSock:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, t): pass
        def sendto(self, data, addr): assert addr == ("ptbtime1.ptb.de", 123)
        def recvfrom(self, n): return reply, None

    monkeypatch.setattr(timesource.socket, "socket", FakeSock)
    assert timesource.query_ntp("ptbtime1.ptb.de") == pytest.approx(unix)


# ── API ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import frapp.api as api
    from frapp.planner import api as papi

    monkeypatch.setattr(papi, "now_cached", lambda: stamp(hour=6, day=date.today()))
    with TestClient(api.app) as c:
        yield c


H = {"X-API-Key": "dev-key"}


def test_api_task_crud_and_day_plan(client):
    today = date.today().isoformat()
    assert client.get("/v1/tasks").status_code == 401
    r = client.post("/v1/tasks", headers=H, json={"title": "Exposé schreiben", "duration_min": 90,
                                                   "domain": "Scriptor", "day": today, "priority": 1})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    bad = client.post("/v1/tasks", headers=H, json={"title": "Arzt", "constraint": "HARD"})
    assert bad.status_code == 422
    hard = client.post("/v1/tasks", headers=H, json={"title": "Arzt", "constraint": "HARD",
                                                     "fixed_start": f"{today}T15:00:00", "duration_min": 30})
    assert hard.status_code == 201 and hard.json()["day"] == today

    plan = client.get(f"/v1/planner/day?day={today}", headers=H).json()
    titles = {r["title"]: r for r in plan["rows"]}
    assert titles["Arzt"]["start"].startswith(f"{today}T15:00") and titles["Arzt"]["constraint"] == "HARD"
    assert titles["Exposé schreiben"]["time_basis"] == "Vorschlag (ASSUMPTION)"
    assert plan["timestamp"]["verified"] is True
    assert any(g["source"] == "Google Calendar" and g["status"] == "UNVERIFIED" for g in plan["truth_gate"])

    assert client.patch(f"/v1/tasks/{tid}", headers=H, json={"done": True}).json()["done"] is True
    plan2 = client.get(f"/v1/planner/day?day={today}", headers=H).json()
    assert "Exposé schreiben" not in {r["title"] for r in plan2["rows"]}
    assert client.delete(f"/v1/tasks/{tid}", headers=H).status_code == 204
    assert client.get(f"/v1/planner/day?start=18:00&end=08:00", headers=H).status_code == 422


def test_api_naive_event_is_berlin_time_in_plan(client):
    today = date.today().isoformat()
    r = client.post("/v1/events", headers=H, json={"title": "Lesung", "starts_at": f"{today}T19:00:00",
                                                    "ends_at": f"{today}T20:00:00"})
    assert r.status_code == 201, r.text
    plan = client.get(f"/v1/planner/day?day={today}", headers=H).json()
    row = next(x for x in plan["rows"] if x["title"] == "Lesung")
    assert row["start"].startswith(f"{today}T19:00")  # 19 Uhr Berlin bleibt 19 Uhr
