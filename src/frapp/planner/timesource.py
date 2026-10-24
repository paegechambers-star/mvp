"""
Zeitstempel nach Atomzeit-Regel.

Methode 1 (bevorzugt): NTP-Abfrage bei der Physikalisch-Technischen Bundesanstalt
(ptbtime1/2/3.ptb.de) — gesetzliche Zeit Deutschlands. Methode 2 (Fallback):
Systemuhr, ausdrücklich als nicht PTB-verifiziert gekennzeichnet.
"""

from __future__ import annotations

import socket
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
PTB_SERVERS = ("ptbtime1.ptb.de", "ptbtime2.ptb.de", "ptbtime3.ptb.de")
_NTP_EPOCH_OFFSET = 2208988800  # 1900-01-01 → 1970-01-01


@dataclass(frozen=True)
class Timestamp:
    berlin: datetime
    zone: str        # "MEZ" oder "MESZ"
    method: str      # lesbare Methodik inkl. Quelle
    verified: bool   # True nur bei erfolgreicher PTB-Abfrage

    def to_dict(self) -> dict:
        return {
            "berlin": self.berlin.isoformat(timespec="seconds"),
            "zone": self.zone,
            "method": self.method,
            "verified": self.verified,
        }


def _zone_label(dt: datetime) -> str:
    return "MESZ" if dt.dst() and dt.dst().total_seconds() else "MEZ"


def query_ntp(server: str, timeout: float = 1.5) -> float:
    """Unix-Zeit vom NTP-Server (Sekunden, float). Wirft OSError bei Fehler."""
    packet = b"\x1b" + 47 * b"\0"  # LI=0, VN=3, Mode=3 (Client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, (server, 123))
        data, _ = sock.recvfrom(48)
    if len(data) < 48:
        raise OSError("NTP-Antwort zu kurz")
    seconds, fraction = struct.unpack("!II", data[40:48])  # Transmit Timestamp
    if seconds == 0:
        raise OSError("NTP-Antwort ohne Zeitstempel")
    return seconds - _NTP_EPOCH_OFFSET + fraction / 2**32


def now(ntp: Optional[Callable[[str], float]] = None, use_network: bool = True) -> Timestamp:
    """Aktueller Zeitstempel Berlin mit gekennzeichneter Methodik."""
    if use_network:
        ask = ntp or query_ntp
        for server in PTB_SERVERS:
            try:
                sent = time.time()
                unix = ask(server)
                offset_ms = (unix - (sent + time.time()) / 2) * 1000
            except OSError:
                continue
            dt = datetime.fromtimestamp(unix, tz=timezone.utc).astimezone(BERLIN)
            return Timestamp(
                dt, _zone_label(dt),
                f"PTB-basiert ({server}, NTP; Abweichung Systemuhr {offset_ms:+.0f} ms)", True,
            )
    dt = datetime.now(timezone.utc).astimezone(BERLIN)
    return Timestamp(
        dt, _zone_label(dt),
        "Fallback: Systemuhr (PTB-Zeitserver nicht erreichbar — nicht atomzeit-verifiziert)", False,
    )


# ── Cache: PTB-Abweichung 10 min wiederverwenden (sonst bis 4,5 s je Abfrage) ──
_cache: dict = {}


def now_cached(max_age_s: float = 600, ntp: Optional[Callable[[str], float]] = None) -> Timestamp:
    """Wie :func:`now`, aber mit zwischengespeicherter PTB-Abweichung."""
    hit = _cache.get("ptb")
    if hit and time.monotonic() - hit["at"] < max_age_s:
        unix = time.time() + hit["offset"]
        dt = datetime.fromtimestamp(unix, tz=timezone.utc).astimezone(BERLIN)
        age = int((time.monotonic() - hit["at"]) // 60)
        return Timestamp(dt, _zone_label(dt),
                         f"PTB-basiert ({hit['server']}, NTP; synchronisiert vor {age} min)", True)
    stamp = now(ntp=ntp)
    if stamp.verified:
        server = stamp.method.split("(")[1].split(",")[0]
        _cache["ptb"] = {"at": time.monotonic(), "offset": stamp.berlin.timestamp() - time.time(),
                         "server": server}
    return stamp
