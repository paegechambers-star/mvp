"""
Deterministischer Tagesplaner (kein LLM): gleiche Eingabe → gleicher Plan.

Regeln:
  - Termine aus dem FraPP-Kalender sind HARD und VERIFIED (Quelle: FraPP-DB, Event-ID).
  - HARD-Aufgaben mit fester Uhrzeit werden wie Termine behandelt.
  - SOFT-Aufgaben werden in freie Lücken gelegt (Priorität, dann Fälligkeit, dann ID),
    danach FLOAT-Aufgaben. Diese Uhrzeiten sind Vorschläge → ASSUMPTION.
  - Was nicht passt, landet unter „nicht eingeplant“ mit Grund. Nichts wird erfunden.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .timesource import BERLIN, Timestamp

_ROUND_MIN = 5


@dataclass
class PlanRow:
    start: Optional[str]          # ISO Berlin, None = ganztägig / ohne Uhrzeit
    end: Optional[str]
    title: str
    constraint: str               # HARD | SOFT | FLOAT
    domain: str
    source: str                   # Quellenangabe (No-Citation = No-Assertion)
    certainty: str                # VERIFIED | UNVERIFIED | ASSUMPTION (Inhalt)
    time_basis: str               # "Quelle" | "Vorschlag (ASSUMPTION)" | "ganztägig"
    ref: str                      # event:<id> | task:<id>


@dataclass
class DayPlan:
    day: str
    timestamp: Dict[str, Any]
    truth_gate: List[Dict[str, str]]
    rows: List[PlanRow] = field(default_factory=list)
    unplaced: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    free_minutes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def _berlin(dt: datetime) -> datetime:
    if dt.tzinfo is None:  # SQLite liefert ggf. naiv → gespeichert wird UTC
        from datetime import timezone

        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BERLIN)


def _round_up(dt: datetime) -> datetime:
    extra = (-dt.minute) % _ROUND_MIN
    return (dt + timedelta(minutes=extra)).replace(second=0, microsecond=0)


def _free_slots(
    window: Tuple[datetime, datetime], busy: Iterable[Tuple[datetime, datetime]]
) -> List[Tuple[datetime, datetime]]:
    start, end = window
    slots: List[Tuple[datetime, datetime]] = []
    cursor = start
    for b_start, b_end in sorted(busy):
        if b_end <= cursor:
            continue
        if b_start > cursor:
            slots.append((cursor, min(b_start, end)))
        cursor = max(cursor, b_end)
        if cursor >= end:
            break
    if cursor < end:
        slots.append((cursor, end))
    return [(a, b) for a, b in slots if b > a]


def build_day_plan(
    day: date,
    events: Sequence[Any],
    tasks: Sequence[Any],
    stamp: Timestamp,
    day_start: time = time(7, 0),
    day_end: time = time(22, 0),
    external: Optional[Dict[str, str]] = None,
) -> DayPlan:
    """
    ``events``: Objekte mit id, title, starts_at, ends_at, all_day, location.
    ``tasks``:  Objekte mit id, title, duration_min, constraint, domain, fixed_start,
                due, priority, source, certainty, done.
    ``external``: Name → Status externer Quellen (z. B. {"Google Calendar": "nicht verbunden"}).
    """
    window_start = datetime.combine(day, day_start, BERLIN)
    window_end = datetime.combine(day, day_end, BERLIN)
    day_begin = datetime.combine(day, time(0, 0), BERLIN)
    day_finish = day_begin + timedelta(days=1)
    if stamp.berlin.date() == day:
        window_start = max(window_start, _round_up(stamp.berlin))

    rows: List[PlanRow] = []
    busy: List[Tuple[datetime, datetime, str]] = []

    # ── Termine (FraPP-Kalender) ─────────────────────────────────────────
    day_events = []
    for ev in events:
        s, e = _berlin(ev.starts_at), _berlin(ev.ends_at)
        if e <= day_begin or s >= day_finish:
            continue
        day_events.append(ev)
        src = f"FraPP-Kalender, Termin #{ev.id}" + (f" ({ev.location})" if ev.location else "")
        if ev.all_day:
            rows.append(PlanRow(None, None, ev.title, "HARD", "Termin", src, "VERIFIED",
                                "ganztägig", f"event:{ev.id}"))
            continue
        rows.append(PlanRow(s.isoformat(timespec="minutes"), e.isoformat(timespec="minutes"),
                            ev.title, "HARD", "Termin", src, "VERIFIED", "Quelle", f"event:{ev.id}"))
        busy.append((s, e, f"event:{ev.id}"))

    # ── Aufgaben ─────────────────────────────────────────────────────────
    open_tasks = [t for t in tasks if not t.done]
    flexible = []
    for t in open_tasks:
        c = getattr(t.constraint, "value", t.constraint)
        src = f"FraPP-Aufgabe #{t.id} ({t.source})"
        cert = getattr(t.certainty, "value", t.certainty)
        if c == "HARD" and t.fixed_start is not None:
            s = _berlin(t.fixed_start)
            if s.date() != day:
                continue
            e = s + timedelta(minutes=t.duration_min)
            rows.append(PlanRow(s.isoformat(timespec="minutes"), e.isoformat(timespec="minutes"),
                                t.title, "HARD", t.domain, src, cert, "Quelle", f"task:{t.id}"))
            busy.append((s, e, f"task:{t.id}"))
        else:
            flexible.append(t)

    # ── Konflikte zwischen festen Blöcken ────────────────────────────────
    conflicts = []
    ordered = sorted(busy)
    for (s1, e1, r1), (s2, e2, r2) in zip(ordered, ordered[1:]):
        if s2 < e1:
            conflicts.append({"a": r1, "b": r2, "overlap_min": int((min(e1, e2) - s2).total_seconds() // 60)})

    # ── Flexible Aufgaben in Lücken legen ────────────────────────────────
    def key(t: Any) -> Tuple[int, int, date, int]:
        c = getattr(t.constraint, "value", t.constraint)
        return (0 if c != "FLOAT" else 1, t.priority, t.due or date.max, t.id or 0)

    slots = _free_slots((window_start, window_end), [(s, e) for s, e, _ in busy])
    unplaced = []
    for t in sorted(flexible, key=key):
        need = timedelta(minutes=t.duration_min)
        c = getattr(t.constraint, "value", t.constraint)
        placed = False
        for i, (a, b) in enumerate(slots):
            if b - a >= need:
                rows.append(PlanRow(
                    a.isoformat(timespec="minutes"), (a + need).isoformat(timespec="minutes"),
                    t.title, c if c != "HARD" else "SOFT", t.domain,
                    f"FraPP-Aufgabe #{t.id} ({t.source})",
                    getattr(t.certainty, "value", t.certainty), "Vorschlag (ASSUMPTION)", f"task:{t.id}",
                ))
                slots[i] = (a + need, b)
                placed = True
                break
        if not placed:
            reason = "keine ausreichend große Lücke im Tagesfenster"
            if c == "HARD":
                reason = "HARD ohne feste Uhrzeit — bitte Uhrzeit setzen"
            unplaced.append({"ref": f"task:{t.id}", "title": t.title, "duration_min": t.duration_min,
                             "constraint": c, "reason": reason})

    rows.sort(key=lambda r: (r.start is not None, r.start or ""))

    # ── Truth-Gate ───────────────────────────────────────────────────────
    gate = [
        {"source": "Zeitbasis", "status": "VERIFIED" if stamp.verified else "UNVERIFIED",
         "detail": stamp.method},
        {"source": "FraPP-Kalender", "status": "VERIFIED" if day_events else "EMPTY-BUT-VERIFIED",
         "detail": f"{len(day_events)} Termin(e) am {day.isoformat()} in der FraPP-Datenbank"},
        {"source": "FraPP-Aufgaben", "status": "VERIFIED" if open_tasks else "EMPTY-BUT-VERIFIED",
         "detail": f"{len(open_tasks)} offene Aufgabe(n) für diesen Tag"},
    ]
    for name, status in (external or {}).items():
        gate.append({"source": name, "status": "UNVERIFIED",
                     "detail": f"{status} — keine Aussage über Termine aus dieser Quelle"})

    free = sum(int((b - a).total_seconds() // 60) for a, b in slots)
    return DayPlan(day.isoformat(), stamp.to_dict(), gate, rows, unplaced, conflicts, free)
