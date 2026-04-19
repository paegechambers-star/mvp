# Demo-Script — 15-Minuten Call

**Ziel:** Vom "interessant" zum "schick mir den Vertrag" in 15 Minuten.
**Werkzeug:** Terminal + Browser (localhost:8000/docs). Kein Pitch-Deck.

---

## Minute 0–2 · Schmerz bestätigen

> "Bevor ich euch was zeige — wie weit seid ihr aktuell mit EU AI Act Vorbereitung?
> Habt ihr einen Audit-Trail für KI-Entscheidungen?"

**Wenn JA:** "Perfekt — dann kann ich euch zeigen wie wir das einfacher machen."
**Wenn NEIN:** "Dann ist der Zeitpunkt gut. August 2026 ist in X Monaten."

*Ziel: Sie reden zuerst. Du hörst zu.*

---

## Minute 2–5 · Live: Swagger aufmachen

```
http://localhost:8000/docs
```

> "Das ist die komplette API. Kein Pitch-Deck — das ist echter Code, der läuft.
> Ich zeige euch drei Dinge in 10 Minuten."

**Zeigen:**
1. `POST /v1/godai/token` — JWT ausstellen, Trust Level erklären (L1/L2/L3)
2. `POST /v1/godai/query` — Anfrage durch die Pipeline schicken, live
3. **Pause.** Auf Reaktion warten.

---

## Minute 5–8 · Die Kette zeigen (der "Wow"-Moment)

```
GET /v1/godai/audit
```

> "Seht ihr das? Jeder Eintrag hat einen Hash — und der nächste Eintrag enthält
> den Hash des vorherigen. Das ist eine kryptografische Kette.
> Wenn jemand nachträglich einen Eintrag ändert — auch nur ein Zeichen —
> erkennt das System es beim nächsten Start automatisch."

**Dann im Terminal:**
```bash
python tests/level4_security.py 2>&1 | grep -E "BLOCKED|VULNERABLE"
```

> "Das war ein automatisierter OWASP Penetrationstest. 30 von 30 Angriffen blockiert.
> Das ist das Protokoll das ihr eurem Auditor zeigen könnt."

---

## Minute 8–10 · DSGVO live demonstrieren

```
POST /v1/events          (mit X-User-ID: demo-user)
GET  /v1/me/data         (mit X-User-ID: demo-user)
DELETE /v1/me/data       (mit X-User-ID: demo-user)
```

> "Drei Endpunkte. DSGVO Art. 15, 17, 20. Auskunft, Löschung, Export.
> Out of the box. Kein Custom-Code."

---

## Minute 10–12 · Offline-Option erwähnen (für regulierte Branchen)

> "Falls ihr in einer regulierten Branche seid oder BaFin-Anforderungen habt:
> das System läuft 100% lokal. Kein Datentransfer in die Cloud.
> Wir haben Ollama-Integration — open-source LLM, läuft auf eurem Server."

---

## Minute 12–14 · Preis (direkt, ohne Umwege)

> "Starter: 149 Euro im Monat, 50.000 Anfragen. Die meisten Teams starten da.
> Professional: 799 Euro, 500.000 Anfragen.
> Wenn ihr On-Premise wollt: 15.000 Euro einmalig, Quellcode-Lizenz, keine laufenden Kosten."

**Frage:** "Welches Modell passt zu euch?"

*Nicht: "Was ist euer Budget?" Direkt fragen welches Modell passt.*

---

## Minute 14–15 · Nächster Schritt festlegen

> "Was braucht ihr um intern eine Entscheidung zu treffen?
> Soll ich den Quellcode schicken, damit eure Entwickler reinschauen können?"

**Ziele für den Abschluss:**
- Demo-Repo-Zugang zusagen
- Technischen Kontakt (Entwickler) für nächsten Call identifizieren
- Oder: direkt Starter-Vertrag anbieten

---

## Häufige Reaktionen

**"Wir haben das intern gebaut"**
> "Wie lange hat das gedauert? Und habt ihr den Penetrationstest-Bericht?"
> *(Die meisten sagen 6+ Monate und nein)*

**"Zu teuer"**
> "Wie lange würde es intern dauern? Ein Entwickler-Monat kostet mehr als ein Jahr Starter."

**"Wir brauchen das nicht"**
> "EU AI Act tritt in X Monaten in Kraft. Was ist euer Plan?"

**"Schick uns erst Unterlagen"**
> "Ich schicke das Demo-Repo — ihr könnt in 15 Minuten selbst testen. Besser als jeder Prospekt."
