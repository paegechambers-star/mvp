"""
Kalender- und Aufgaben-Werkzeuge für den FraPP-Chat.

Lesen (Termine, Aufgaben, Tagesplan) läuft sofort und antwortet nur mit Daten aus der
FraPP-Datenbank, jeweils mit Quelle (``Termin #ID``). Schreiben (Termin anlegen/ändern/
löschen, Aufgabe anlegen) erzeugt einen Vorschlag mit deterministischem Kartentext und
Konfliktprüfung; in die Datenbank geschrieben wird erst nach „Übernehmen“ im Chat.
Die Zeitbasis (heute, Wochentage) kommt aus der PTB-Zeit des Tagesplaners.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from .models import Event
from .planner.models import Certainty, Constraint, Task
from .planner.timesource import now_cached
from .settings import settings

_WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_WD_LONG = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MAX_RANGE_DAYS = 62
OWNER = "frapp-chat"


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def _engine() -> Any:
    from .db import engine

    return engine


def _local(dt: datetime) -> datetime:
    if dt.tzinfo is None:  # SQLite liefert ggf. naiv → gespeichert wird UTC
        from datetime import timezone

        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_tz())


def _parse_dt(value: Any, what: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} fehlt (ISO 8601, z. B. 2026-10-27T14:00)")
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"{what} '{value}' ist kein ISO-Datum (z. B. 2026-10-27T14:00)") from None
    return dt.replace(tzinfo=_tz()) if dt.tzinfo is None else dt.astimezone(_tz())


def _parse_date(value: Any, what: str) -> date:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        raise ValueError(f"{what} '{value}' ist kein Datum (YYYY-MM-DD)") from None


def _fmt_day(d: date) -> str:
    return f"{_WD[d.weekday()]} {d:%d.%m.%Y}"


def _fmt_event(e: Event) -> str:
    s, t = _local(e.starts_at), _local(e.ends_at)
    when = "ganztägig" if e.all_day else f"{s:%H:%M}–{t:%H:%M}"
    loc = f" ({e.location})" if e.location else ""
    return f"Termin #{e.id}: {_fmt_day(s.date())} {when} · {e.title}{loc}"


def _fmt_span(start: datetime, end: datetime, all_day: bool) -> str:
    if all_day:
        return f"{_fmt_day(start.date())} ganztägig"
    if start.date() == end.date():
        return f"{_fmt_day(start.date())} {start:%H:%M}–{end:%H:%M}"
    return f"{_fmt_day(start.date())} {start:%H:%M} – {_fmt_day(end.date())} {end:%H:%M}"


def _today() -> date:
    return now_cached().berlin.date()


def _conflicts(start: datetime, end: datetime, ignore_id: int | None = None) -> list[str]:
    with Session(_engine()) as s:
        events = s.exec(select(Event)).all()
    out = []
    for e in events:
        if e.id == ignore_id or e.all_day:
            continue
        if _local(e.starts_at) < end and _local(e.ends_at) > start:
            out.append(f"überschneidet sich mit {_fmt_event(e)}")
    return out


def _span(args: dict[str, Any], base: Event | None = None) -> tuple[datetime, datetime, bool]:
    all_day = bool(args.get("all_day", base.all_day if base else False))
    if args.get("start"):
        start = _parse_dt(args["start"], "Beginn")
    elif base is not None:
        start = _local(base.starts_at)
    else:
        raise ValueError("Beginn fehlt (ISO 8601, z. B. 2026-10-27T14:00)")
    if all_day:
        day = start.date()
        return (
            datetime.combine(day, time(0, 0), _tz()),
            datetime.combine(day, time(23, 59), _tz()),
            True,
        )
    if args.get("end"):
        end = _parse_dt(args["end"], "Ende")
    elif args.get("duration_min"):
        end = start + timedelta(minutes=int(args["duration_min"]))
    elif base is not None and not args.get("start"):
        end = _local(base.ends_at)
    elif base is not None:  # Beginn verschoben → Dauer beibehalten
        end = start + (_local(base.ends_at) - _local(base.starts_at))
    else:
        end = start + timedelta(hours=1)
    if end <= start:
        raise ValueError("Ende muss nach dem Beginn liegen")
    if end - start > timedelta(days=14):
        raise ValueError("Termin länger als 14 Tage — bitte prüfen")
    return start, end, False


def _warnings(start: datetime, end: datetime, ignore_id: int | None = None) -> list[str]:
    warn = _conflicts(start, end, ignore_id)
    if start.date() < _today():
        warn.append("liegt in der Vergangenheit")
    if start.year > _today().year + 2:  # Tippfehler im Jahr?
        warn.append(f"Jahr {start.year} — wirklich?")
    return warn


def _get_event(event_id: Any) -> Event:
    try:
        eid = int(event_id)
    except (TypeError, ValueError):
        raise ValueError(f"Termin-ID '{event_id}' ist keine Zahl") from None
    with Session(_engine()) as s:
        e = s.get(Event, eid)
    if e is None:
        raise ValueError(f"Termin #{eid} existiert nicht")
    return e


# ---------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------


def list_events(args: dict[str, Any]) -> str:
    start = _parse_date(args["from_date"], "from_date") if args.get("from_date") else _today()
    end = _parse_date(args["to_date"], "to_date") if args.get("to_date") else start + timedelta(7)
    if end < start:
        raise ValueError("to_date liegt vor from_date")
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValueError(f"Zeitraum höchstens {MAX_RANGE_DAYS} Tage")
    with Session(_engine()) as s:
        events = s.exec(select(Event)).all()
    hits = sorted(
        (e for e in events if start <= _local(e.starts_at).date() <= end),
        key=lambda e: _local(e.starts_at),
    )
    head = f"FraPP-Kalender {_fmt_day(start)} bis {_fmt_day(end)}"
    if not hits:
        return f"{head}: keine Termine (EMPTY-BUT-VERIFIED)."
    return head + f" ({len(hits)} Termine, VERIFIED):\n" + "\n".join(_fmt_event(e) for e in hits)


def list_tasks(args: dict[str, Any]) -> str:
    with Session(_engine()) as s:
        tasks = s.exec(select(Task).where(Task.done == False)).all()
    if not tasks:
        return "Keine offenen Aufgaben (EMPTY-BUT-VERIFIED)."
    lines = []
    for t in sorted(tasks, key=lambda t: (t.priority, t.id or 0)):
        c = getattr(t.constraint, "value", t.constraint)
        when = f" ab {_local(t.fixed_start):%d.%m. %H:%M}" if t.fixed_start else ""
        day = f" für {_fmt_day(t.day)}" if t.day else ""
        lines.append(
            f"Aufgabe #{t.id}: {t.title} · {t.duration_min} min · {c} · {t.domain} · "
            f"Prio {t.priority}{day}{when}"
        )
    return f"{len(tasks)} offene Aufgaben:\n" + "\n".join(lines)


def day_plan(args: dict[str, Any]) -> str:
    from .planner.engine import build_day_plan

    stamp = now_cached()
    target = _parse_date(args["date"], "date") if args.get("date") else stamp.berlin.date()
    today = stamp.berlin.date()
    with Session(_engine()) as s:
        events = s.exec(select(Event)).all()
        tasks = [
            t
            for t in s.exec(select(Task).where(Task.done == False)).all()
            if t.day == target or (t.day is None and target == today)
        ]
        plan = build_day_plan(target, events, tasks, stamp)
    lines = [f"Tagesplan {_fmt_day(target)} — Zeitbasis: {stamp.method}"]
    lines += [f"Truth-Gate {g['source']}: {g['status']} ({g['detail']})" for g in plan.truth_gate]
    for r in plan.rows:
        when = "ganztägig" if r.start is None else f"{r.start[11:16]}–{(r.end or '')[11:16]}"
        lines.append(
            f"{when} · {r.title} · {r.constraint} · {r.domain} · {r.certainty} · "
            f"{r.time_basis} · Quelle: {r.source}"
        )
    lines += [f"Nicht eingeplant: {u['title']} ({u['reason']})" for u in plan.unplaced]
    lines += [f"Konflikt: {c['a']} ↔ {c['b']} ({c['overlap_min']} min)" for c in plan.conflicts]
    lines.append(f"Freie Zeit: {plan.free_minutes} min")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Schreiben (nur Vorschlag; apply erst nach Bestätigung)
# ---------------------------------------------------------------------------


def _clean_title(args: dict[str, Any], required: bool = True) -> str | None:
    title = str(args.get("title") or "").strip()
    if not title:
        if required:
            raise ValueError("Titel fehlt")
        return None
    if len(title) > 200:
        raise ValueError("Titel zu lang (max. 200 Zeichen)")
    return title


def prepare_create_event(args: dict[str, Any]) -> Any:
    from scriptor.chat import Proposal

    title = _clean_title(args)
    start, end, all_day = _span(args)
    location = (str(args.get("location") or "").strip() or None) if args.get("location") else None
    loc = f" · {location}" if location else ""
    return Proposal(
        summary=f"Termin anlegen: {_fmt_span(start, end, all_day)} · {title}{loc}",
        payload={
            "title": title,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "all_day": all_day,
            "location": location,
        },
        warnings=_warnings(start, end),
    )


def apply_create_event(payload: dict[str, Any]) -> str:
    event = Event(
        title=payload["title"],
        starts_at=datetime.fromisoformat(payload["starts_at"]),
        ends_at=datetime.fromisoformat(payload["ends_at"]),
        all_day=payload["all_day"],
        location=payload.get("location"),
        owner=OWNER,
    )
    with Session(_engine()) as s:
        s.add(event)
        s.commit()
        s.refresh(event)
        return f"{_fmt_event(event)} gespeichert"


def prepare_update_event(args: dict[str, Any]) -> Any:
    from scriptor.chat import Proposal

    old = _get_event(args.get("event_id"))
    title = _clean_title(args, required=False) or old.title
    start, end, all_day = _span(args, base=old)
    location = args.get("location", old.location)
    if (
        title == old.title
        and start == _local(old.starts_at)
        and end == _local(old.ends_at)
        and location == old.location
        and all_day == old.all_day
    ):
        raise ValueError(f"Keine Änderung an Termin #{old.id} angegeben")
    loc = f" · {location}" if location else ""
    return Proposal(
        summary=(
            f"Termin #{old.id} ändern: {_fmt_event(old).split(': ', 1)[1]} → "
            f"{_fmt_span(start, end, all_day)} · {title}{loc}"
        ),
        payload={
            "event_id": old.id,
            "title": title,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "all_day": all_day,
            "location": location,
        },
        warnings=_warnings(start, end, ignore_id=old.id),
    )


def apply_update_event(payload: dict[str, Any]) -> str:
    with Session(_engine()) as s:
        e = s.get(Event, payload["event_id"])
        if e is None:
            raise ValueError(f"Termin #{payload['event_id']} existiert nicht mehr")
        e.title = payload["title"]
        e.starts_at = datetime.fromisoformat(payload["starts_at"])
        e.ends_at = datetime.fromisoformat(payload["ends_at"])
        e.all_day = payload["all_day"]
        e.location = payload.get("location")
        s.add(e)
        s.commit()
        s.refresh(e)
        return f"{_fmt_event(e)} geändert"


def prepare_delete_event(args: dict[str, Any]) -> Any:
    from scriptor.chat import Proposal

    e = _get_event(args.get("event_id"))
    return Proposal(summary=f"{_fmt_event(e)} LÖSCHEN", payload={"event_id": e.id})


def apply_delete_event(payload: dict[str, Any]) -> str:
    with Session(_engine()) as s:
        e = s.get(Event, payload["event_id"])
        if e is None:
            raise ValueError(f"Termin #{payload['event_id']} existiert nicht mehr")
        text = _fmt_event(e)
        s.delete(e)
        s.commit()
    return f"{text} gelöscht"


def prepare_create_task(args: dict[str, Any]) -> Any:
    from scriptor.chat import Proposal

    title = _clean_title(args)
    duration = int(args.get("duration_min") or 30)
    if not 5 <= duration <= 720:
        raise ValueError("Dauer muss zwischen 5 und 720 Minuten liegen")
    raw_c = str(args.get("constraint") or "SOFT").upper()
    if raw_c not in Constraint.__members__:
        raise ValueError("constraint muss HARD, SOFT oder FLOAT sein")
    priority = int(args.get("priority") or 2)
    if priority not in (1, 2, 3):
        raise ValueError("Priorität muss 1 (hoch), 2 oder 3 (niedrig) sein")
    domain = str(args.get("domain") or "Allgemein").strip()[:60]
    fixed = _parse_dt(args["fixed_start"], "fixed_start") if args.get("fixed_start") else None
    day = _parse_date(args["day"], "day") if args.get("day") else (fixed.date() if fixed else None)
    due = _parse_date(args["due"], "due") if args.get("due") else None
    warnings = []
    if raw_c == "HARD" and fixed is None:
        warnings.append("HARD ohne feste Uhrzeit wird im Tagesplan nicht eingeplant")
    if fixed is not None:
        warnings += _warnings(fixed, fixed + timedelta(minutes=duration))
    parts = [f"Aufgabe anlegen: {title}", f"{duration} min", raw_c, domain, f"Prio {priority}"]
    if fixed:
        parts.append(f"fest {_fmt_day(fixed.date())} {fixed:%H:%M}")
    elif day:
        parts.append(f"für {_fmt_day(day)}")
    if due:
        parts.append(f"fällig {_fmt_day(due)}")
    return Proposal(
        summary=" · ".join(parts),
        payload={
            "title": title,
            "duration_min": duration,
            "constraint": raw_c,
            "domain": domain,
            "priority": priority,
            "fixed_start": fixed.isoformat() if fixed else None,
            "day": day.isoformat() if day else None,
            "due": due.isoformat() if due else None,
        },
        warnings=warnings,
    )


def apply_create_task(payload: dict[str, Any]) -> str:
    task = Task(
        title=payload["title"],
        duration_min=payload["duration_min"],
        constraint=Constraint(payload["constraint"]),
        domain=payload["domain"],
        priority=payload["priority"],
        fixed_start=(
            datetime.fromisoformat(payload["fixed_start"]) if payload["fixed_start"] else None
        ),
        day=date.fromisoformat(payload["day"]) if payload["day"] else None,
        due=date.fromisoformat(payload["due"]) if payload["due"] else None,
        source="Chat (vom Nutzer bestätigt)",
        certainty=Certainty.VERIFIED,
    )
    with Session(_engine()) as s:
        s.add(task)
        s.commit()
        s.refresh(task)
        return f"Aufgabe #{task.id}: {task.title} gespeichert"


# ---------------------------------------------------------------------------
# Toolkit
# ---------------------------------------------------------------------------


def time_context() -> str:
    stamp = now_cached()
    now = stamp.berlin
    week = ", ".join(
        f"{_WD_LONG[(d := now.date() + timedelta(i)).weekday()]} = {d.isoformat()}"
        for i in range(14)
    )
    return (
        f"JETZT: {_WD_LONG[now.weekday()]}, {now:%d.%m.%Y %H:%M} ({stamp.zone}, "
        f"Europe/Berlin). Zeitbasis: {stamp.method}.\n"
        f"Die nächsten 14 Tage: {week}.\n"
        "„Morgen“ = heute + 1 Tag. Termine ohne Endzeit: 60 Minuten. Für Fragen zu "
        "Terminen immer list_events/day_plan nutzen und die Termin-ID als Quelle nennen."
    )


def _schema(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or []}


_S = {"type": "string"}
_DT = {"type": "string", "description": "ISO 8601, z. B. 2026-10-27T14:00 (Europe/Berlin)"}
_D = {"type": "string", "description": "Datum YYYY-MM-DD"}


def calendar_toolkit() -> Any:
    from scriptor.chat import ChatTool, ChatToolkit

    return ChatToolkit(
        name="kalender",
        context=time_context,
        tools=[
            ChatTool(
                "list_events",
                "Termine aus dem FraPP-Kalender in einem Zeitraum (Standard: heute + 7 Tage).",
                _schema({"from_date": _D, "to_date": _D}),
                run=list_events,
            ),
            ChatTool(
                "list_tasks",
                "Offene Aufgaben des Tagesplaners.",
                _schema({}),
                run=list_tasks,
            ),
            ChatTool(
                "day_plan",
                "Tagesplan (Truth-Gate + 4D-Matrix) für ein Datum (Standard: heute).",
                _schema({"date": _D}),
                run=day_plan,
            ),
            ChatTool(
                "create_event",
                "Termin anlegen (Vorschlag, Nutzer bestätigt). Ohne Ende: 60 Minuten.",
                _schema(
                    {
                        "title": _S,
                        "start": _DT,
                        "end": _DT,
                        "duration_min": {"type": "integer"},
                        "all_day": {"type": "boolean"},
                        "location": _S,
                    },
                    ["title", "start"],
                ),
                prepare=prepare_create_event,
                apply=apply_create_event,
            ),
            ChatTool(
                "update_event",
                "Termin ändern (Vorschlag). Nur angegebene Felder ändern sich; "
                "verschobener Beginn behält die Dauer.",
                _schema(
                    {
                        "event_id": {"type": "integer"},
                        "title": _S,
                        "start": _DT,
                        "end": _DT,
                        "duration_min": {"type": "integer"},
                        "all_day": {"type": "boolean"},
                        "location": _S,
                    },
                    ["event_id"],
                ),
                prepare=prepare_update_event,
                apply=apply_update_event,
            ),
            ChatTool(
                "delete_event",
                "Termin löschen (Vorschlag, Nutzer bestätigt).",
                _schema({"event_id": {"type": "integer"}}, ["event_id"]),
                prepare=prepare_delete_event,
                apply=apply_delete_event,
            ),
            ChatTool(
                "create_task",
                "Aufgabe für den Tagesplaner anlegen (Vorschlag). constraint: HARD (feste "
                "Uhrzeit nötig), SOFT (heute, flexibel), FLOAT (wenn Zeit bleibt).",
                _schema(
                    {
                        "title": _S,
                        "duration_min": {"type": "integer"},
                        "constraint": {"type": "string", "enum": ["HARD", "SOFT", "FLOAT"]},
                        "domain": _S,
                        "priority": {"type": "integer", "enum": [1, 2, 3]},
                        "fixed_start": _DT,
                        "day": _D,
                        "due": _D,
                    },
                    ["title"],
                ),
                prepare=prepare_create_task,
                apply=apply_create_task,
            ),
        ],
    )
