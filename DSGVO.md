# DSGVO — Verzeichnis von Verarbeitungstätigkeiten (VVT)

**Art. 30 DS-GVO | Verantwortlicher:** Lucas William Chambers ("Chambi")
**Projekt:** ForReal / ForRealAI (FraPP + G.O.D.A.I.)
**Stand:** 2026-04-14
**Status:** Entwurf — vor Produktivbetrieb durch Datenschutzbeauftragten zu prüfen.

---

## Allgemeine Angaben (Art. 30 Abs. 1 DS-GVO)

| Feld | Inhalt |
|------|--------|
| **Name und Kontaktdaten des Verantwortlichen** | Lucas William Chambers, [Adresse einzutragen], [E-Mail einzutragen] |
| **Datenschutzbeauftragter** | Nicht verpflichtend (kein Unternehmen mit > 20 MA, keine systematische Verarbeitung sensibler Daten im laufenden Betrieb) |
| **Zweck der Verarbeitung** | Betrieb einer KI-Governance-Plattform (G.O.D.A.I.) und einer Kalender-Webanwendung (FraPP) |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. b DS-GVO (Vertragserfüllung) / Art. 6 Abs. 1 lit. f DS-GVO (berechtigte Interessen) — je nach Einsatzszenario anzupassen |

---

## 1. Verarbeitungstätigkeit: FraPP Kalender-API

### 1.1 Beschreibung

Die FraPP-API verarbeitet Kalenderereignisse (Titel, Start-/Endzeit, Ort). Die Daten werden vom Nutzer selbst eingegeben und dienen ausschließlich der eigenen Terminverwaltung.

### 1.2 Betroffene Personen

- Nutzer der FraPP-Anwendung (ggf. auch genannte Dritte in Termintiteln)

### 1.3 Verarbeitete Datenkategorien

| Datenkategorie | Felder | Sensitivität |
|---------------|--------|-------------|
| Termindaten | `title`, `starts_at`, `ends_at`, `location`, `all_day` | Niedrig – keine besonderen Kategorien nach Art. 9 DS-GVO |

### 1.4 Zweck und Rechtsgrundlage

- **Zweck:** Verwaltung eigener Kalendereinträge durch den Nutzer
- **Rechtsgrundlage:** Art. 6 Abs. 1 lit. b DS-GVO (Vertragserfüllung)

### 1.5 Empfänger

- Keine Weitergabe an Dritte (Stand: Entwicklungsphase)

### 1.6 Speicherdauer

- Bis zur Löschung durch den Nutzer oder bis zur Deinstallation der Anwendung

### 1.7 Technische und organisatorische Maßnahmen (TOM)

| Maßnahme | Umsetzung |
|---------|----------|
| Datenspeicherung | SQLite-Datenbank, lokal auf dem Server (`frapp.db`) |
| Zugriffskontrolle | API-Key-Authentifizierung (konfigurierbar via `.env`) |
| Verschlüsselung | TLS auf Transport-Ebene (in Produktivumgebung verpflichtend) |
| Datenminimierung | Nur notwendige Felder werden erfasst |

---

## 2. Verarbeitungstätigkeit: G.O.D.A.I. Audit-Log (MNEMOSYNE)

### 2.1 Beschreibung

MNEMOSYNE führt ein unveränderliches, SHA256-verkettetes Protokoll aller Routing-, Richtlinien- und Validierungsentscheidungen. Dieses Log enthält User-IDs und Request-IDs.

### 2.2 Betroffene Personen

- Nutzer, die Anfragen über die G.O.D.A.I.-Pipeline stellen (`user_id`)

### 2.3 Verarbeitete Datenkategorien

| Datenkategorie | Felder | Sensitivität |
|---------------|--------|-------------|
| Kennung | `user_id`, `request_id` | Niedrig (Pseudonym) |
| Anfragedaten | `query` (Anfragetexte), `data_class`, `trust_level` | Variabel — abhängig vom Inhalt der Anfrage |
| Entscheidungsdaten | Routing-Entscheidungen, Policy-Ergebnisse, Validierungsergebnisse | Intern |
| Zeitstempel | `timestamp` | Niedrig |

**Hinweis:** Anfragetexte (`query`) können personenbezogene Daten enthalten, wenn Nutzer solche eingeben. Der Verantwortliche muss sicherstellen, dass Nutzer über diese Möglichkeit informiert werden.

### 2.4 Zweck und Rechtsgrundlage

- **Zweck:** Nachvollziehbarkeit und Prüfbarkeit von KI-Entscheidungen (EU AI Act Art. 12); interne Sicherheits- und Qualitätssicherung
- **Rechtsgrundlage:** Art. 6 Abs. 1 lit. c DS-GVO (rechtliche Verpflichtung — EU AI Act) i.V.m. Art. 6 Abs. 1 lit. f DS-GVO (berechtigtes Interesse an Systemsicherheit)

### 2.5 Empfänger

- Keine Weitergabe an Dritte

### 2.6 Speicherdauer

- Aktuell: In-Memory (verloren bei Neustart) — **für Produktivbetrieb: persistente Speicherung erforderlich**
- Empfohlene Aufbewahrungsfrist: 90 Tage (ggf. kürzere Fristen nach Abwägung)
- Löschkonzept: Nach Ablauf der Aufbewahrungsfrist sicheres Löschen

### 2.7 Technische und organisatorische Maßnahmen (TOM)

| Maßnahme | Umsetzung |
|---------|----------|
| Unveränderlichkeit | Append-only-Struktur; keine Update-/Delete-Methoden |
| Integritätssicherung | SHA256-Hashverkettung (Tamper-Detection via `verify_chain()`) |
| Zugriffsbeschränkung | Nur interne Module; kein öffentlicher Endpunkt für das Audit-Log |
| Pseudonymisierung | `user_id` als Pseudonym (kein Klarname im Log) |

---

## 3. Verarbeitungstätigkeit: G.O.D.A.I. Authentifizierung (HERMES)

### 3.1 Beschreibung

HERMES prüft Bearer-Tokens und weist Vertrauensstufen zu. Bei Ablehnung wird ein Protokolleintrag in MNEMOSYNE erzeugt.

### 3.2 Betroffene Personen

- Alle Nutzer, die Anfragen stellen

### 3.3 Verarbeitete Datenkategorien

| Datenkategorie | Felder |
|---------------|--------|
| Authentifizierungsdaten | Bearer-Token (nur Präfix wird ausgewertet, vollständiger Token wird nicht gespeichert) |
| Kennung | `user_id` |

### 3.4 Zweck und Rechtsgrundlage

- **Zweck:** Zugangskontrolle und Betrugsprävention
- **Rechtsgrundlage:** Art. 6 Abs. 1 lit. b DS-GVO (Vertragserfüllung)

### 3.5 Speicherdauer

- Rate-Limit-Zähler: In-Memory, Laufzeit der Anwendung
- Abgelehnte Auth-Ereignisse: Über MNEMOSYNE (s. Abschnitt 2)

---

## 4. Betroffenenrechte (Art. 15–22 DS-GVO)

| Recht | Umsetzungshinweis |
|-------|------------------|
| Auskunft (Art. 15) | Abfrage aller Logeinträge mit `user_id` aus MNEMOSYNE; Datenbankabfrage in `frapp.db` |
| Berichtigung (Art. 16) | Termindaten in `frapp.db` berichtigbar; MNEMOSYNE-Einträge sind unveränderlich (technische Notwendigkeit) |
| Löschung (Art. 17) | Termindaten löschbar; MNEMOSYNE-Einträge: Aufbewahrung aus rechtlicher Pflicht (AI Act) kann Löschung einschränken |
| Datenübertragbarkeit (Art. 20) | JSON-Export der Termindaten aus `frapp.db` zu implementieren |
| Widerspruch (Art. 21) | Nicht anwendbar (keine Direktwerbung; Verarbeitung auf Rechtsgrundlage b/c) |

---

## 5. Drittlandübermittlungen (Art. 44 ff. DS-GVO)

**Aktueller Stand (Entwicklungsphase):** Keine Drittlandübermittlungen.

**Hinweis für Produktivbetrieb:** Bei Nutzung von Cloud-LLM-APIs (z.B. Anthropic Claude, OpenAI) werden Anfrageinhalte an US-amerikanische Server übermittelt. In diesem Fall:
- Standardvertragsklauseln (SCCs) mit dem Anbieter vereinbaren
- Datenschutz-Folgenabschätzung (DSFA) nach Art. 35 DS-GVO prüfen, wenn besondere Datenkategorien verarbeitet werden
- Einwilligung der Nutzer einholen oder Verarbeitung auf berechtigtes Interesse stützen und dokumentieren

---

## 6. Technische und organisatorische Gesamtmaßnahmen

| Kategorie | Maßnahme |
|-----------|---------|
| Verschlüsselung | TLS für alle Netzwerkverbindungen (Produktivbetrieb) |
| Zugriffskontrolle | Rollenbasierte Vertrauensstufen (L0–L3) in G.O.D.A.I. |
| Protokollierung | MNEMOSYNE — SHA256-verkettetes Audit-Log |
| Datenminimierung | Nur notwendige Felder in Datenmodellen |
| Pseudonymisierung | `user_id` als Pseudonym (kein Klarname im System) |
| Backups | Für Produktivbetrieb zu implementieren |
| Incident Response | Verfahren für Datenpannen (Art. 33/34 DS-GVO) zu definieren |

---

*Dieses Dokument ist ein lebendes Dokument und bei jeder wesentlichen Änderung der Datenverarbeitung zu aktualisieren.*
