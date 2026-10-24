# FraPP Desktop

Ein Fenster, fünf Bereiche. Start: Desktop-Verknüpfung **FraPP** oder `frapp app`.

| Tab | Inhalt | API |
|---|---|---|
| **Tagesplan** | Zeitstempel Berlin (PTB/NTP, sonst markierter Fallback) → Truth-Gate → 4D-Matrix (Time / Constraint / Domain / Source + Certainty); Aufgaben anlegen/erledigen | `/v1/planner/day`, `/v1/tasks` |
| **Kalender** | Wochenansicht, Termine anlegen/bearbeiten/löschen (Europe/Berlin) | `/v1/events` |
| **Scriptor** | KI-Ghostwriter (Dock), jeder Claude-Aufruf über G.O.D.A.I. | `/scriptor/` |
| **G.O.D.A.I.** | Anfrage durch HERMES → THEMIS → APOLLON → Modell → ATHENA → MNEMOSYNE, Audit-Ansicht | `/v1/godai/*` |
| **ContextOS** | Register (SSOT/WORK), Log-Kette, NKID/MKID-Prüfung | `/v1/contextos/*` |

Zusätzlich aktiv (aus dem Dispatch-Branch): `/mobile/*`, `/mcp`, `/chat`.

## Tagesplaner-Regeln
- Termine aus dem FraPP-Kalender: **HARD, VERIFIED**, Quelle = Termin-ID.
- HARD-Aufgaben brauchen eine feste Uhrzeit. SOFT, dann FLOAT werden in freie Lücken gelegt —
  diese Uhrzeiten sind **Vorschläge (ASSUMPTION)**.
- Leerer Kalender = **EMPTY-BUT-VERIFIED** (geprüft leer). Nicht angebundene Quellen
  (z. B. Google Calendar) = **UNVERIFIED** — keine Aussage, nicht „leer“.
- Was nicht passt, steht unter „Nicht eingeplant“ mit Grund. Überschneidungen fester Blöcke
  werden als Konflikt gemeldet.

## Sicherheit / Daten
- Server nur auf `127.0.0.1`; pro Start ein zufälliger Schlüssel für alle Bereiche
  (der Entwicklungsschlüssel `dev-key` gilt im Desktop-Modus nicht).
- Daten: `%APPDATA%\FraPP` (SQLite + ContextOS), Bücher: `Dokumente\Scriptor`.
- API-Key: Windows-Anmeldeinformationsverwaltung (Einstellungen im Scriptor-Tab); wird auch
  für den G.O.D.A.I.-Chat genutzt. Ohne Key antwortet G.O.D.A.I. nur als Echo (wird angezeigt).

## Bekannte Grenzen
- MNEMOSYNE der Dispatch-Bridge und der Scriptor-Governance laufen im Speicher; die G.O.D.A.I.-Pipeline
  (`/v1/godai`) ist ein eigener Prozessteil mit eigener Kette.
- APOLLON-Routing (`godai/config/routing/rules.yaml`) nennt ältere Modell-IDs (4.x) — unverändert
  übernommen, da Teil deines G.O.D.A.I.-Regelwerks.
