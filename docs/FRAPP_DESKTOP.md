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

## Chat

Tab **Chat**: freies Gespräch mit dem eingestellten Modell (Ollama lokal oder Claude),
Antworten erscheinen Wort für Wort, „Stopp“ bricht ab (bisheriger Teil bleibt gespeichert).
Verläufe liegen als JSON unter `<Workspace>\chats\` (Standard `Dokumente\Scriptor\chats`).
Jede Nachricht läuft durch G.O.D.A.I. (HERMES → THEMIS → MNEMOSYNE) mit der gewählten
Datenklasse. An das Modell gehen die letzten 40 Nachrichten.

### Termine per Chat

Mit Haken „Kalender“ (Standard) darf der Chat Termine, Aufgaben und den Tagesplan
**lesen** (Antwort mit Quelle `Termin #ID`) und Änderungen **vorschlagen**: Termin
anlegen/ändern/löschen, Aufgabe anlegen. Ein Vorschlag erscheint als Karte mit
deterministischem Text und Konfliktwarnungen; geschrieben wird erst nach „Übernehmen“.
„Morgen“/„nächsten Dienstag“ löst das Modell über die PTB-Zeit auf, die es im
Systemprompt bekommt (inkl. Wochentag→Datum der nächsten 14 Tage). Im Werkzeug-Modus
kommt die Antwort am Stück statt Wort für Wort; ohne Haken wird gestreamt.

## Lokale KI mit Ollama (ohne API-Key, offline)

FraPP kann statt Claude ein lokales Modell über [Ollama](https://ollama.com) nutzen,
für SCRIPTOR **und** G.O.D.A.I. Texte verlassen den Rechner dann nicht.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\ollama.ps1            # qwen3:8b
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\ollama.ps1 -Model qwen3:4b
```

Das Skript installiert Ollama (winget, sonst offizieller Installer), startet den Server
auf `http://localhost:11434`, lädt das Modell und stellt FraPP auf `ollama` um.
Umschalten jederzeit: Scriptor → Einstellungen → KI-Anbieter (gilt ab dem nächsten
Auftrag, ohne Neustart). Dort auch: installierte Modelle, „Modell herunterladen“,
Kontextfenster (Standard 16 384 Tokens).

CLI: `frapp scriptor config --provider ollama --ollama-model qwen3:8b` · zurück:
`--provider anthropic`. G.O.D.A.I. folgt der SCRIPTOR-Einstellung; `FRAPP_LLM_PROVIDER`
(`anthropic|ollama|echo`) überschreibt das.

Grenzen (ASSUMPTION, hängt von Modell und Hardware ab): lokale 4–8B-Modelle schreiben
deutlich schwächer als Claude und brauchen pro Kapitel Minuten statt Sekunden; der
Agent-Chat braucht ein Modell mit Tool-Calling (qwen3, llama3.1); Websuche gibt es lokal nicht.

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
