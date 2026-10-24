# FraPP + G.O.D.A.I.
## EU AI Act Compliance Infrastructure — One Pager

---

### Das Problem (ab August 2026)

EU AI Act Art. 12 ist Pflicht: **lückenloser, kryptografisch prüfbarer Audit-Trail** für jede KI-Entscheidung. Fehlt er beim Audit → bis zu **30 Mio. € oder 6% Jahresumsatz**.

Die meisten Teams unterschätzen den Aufwand: 3–6 Monate Nacharbeit ohne Infrastruktur.

---

### Die Lösung

**G.O.D.A.I.** — 5-stufige AI Governance Pipeline, Drop-in für FastAPI-Backends.

```
Anfrage → HERMES → THEMIS → APOLLON → KI → ATHENA → MNEMOSYNE → Antwort
           Auth     Policy   Routing        Prüfung   Audit-Log
```

Jede Stufe protokolliert. SHA256-Kette. Unveränderbar. Beim Start automatisch verifiziert.

---

### Was es konkret liefert

| EU AI Act / DSGVO | Anforderung | G.O.D.A.I. Modul |
|---|---|---|
| Art. 12 | Aufzeichnungspflicht | MNEMOSYNE SHA256-Kette |
| Art. 13 | Transparenz | Vollprotokoll jeder Entscheidung |
| Art. 14 | Menschliche Aufsicht | ATHENA (Generator ≠ Prüfer) |
| Art. 10 | Datensatz-Governance | THEMIS YAML-Policy-Engine |
| DSGVO 15 | Auskunftsrecht | GET /v1/me/data |
| DSGVO 17 | Löschrecht | DELETE /v1/me/data |
| DSGVO 20 | Datenportabilität | GET /v1/me/export |

---

### Messbarer Beweis (kein Marketing)

- **275 automatisierte Tests** — 0 Fehler
- **30/30 OWASP Angriffsvektoren** blockiert (Penetrationstest-Protokoll vorhanden)
- **1.000-Einträge SHA256-Kette** unabhängig verifiziert (kein Self-Attestation)
- **2.334 Anfragen/Sekunde** bei gleichzeitig 200 parallelen Requests — Kette intakt
- **Chaos Engineering bestanden**: KI-Absturz, leere Antwort, Serverneustart → kein Datenverlust

---

### 100% Offline möglich

Keine Daten verlassen eure Infrastruktur. OllamaProvider / LlamaCppProvider laufen vollständig lokal. Für BaFin, FINMA, SNB, Bundesbehörden — die einzige akzeptable Option.

---

### Preise

| Paket | Preis | Volumen | Für wen |
|---|---|---|---|
| **Starter** | 149 €/Monat | 50.000 Anfragen/Monat | Startups, interne Tools |
| **Professional** | 799 €/Monat | 500.000 Anfragen/Monat | Scale-ups, regulierte Branchen |
| **Enterprise** | 3.500 €/Monat | Unbegrenzt + SLA + Onboarding | Banken, Healthcare, EU-reguliert |
| **Self-Hosted** | 15.000 € einmalig | Unbegrenzt + Quellcode | Sovereign Cloud, Air-gapped |

---

### Setup: 15 Minuten

```bash
git clone [REPO_URL] && cd mvp
pip install -r requirements.txt
cp .env.example .env  # API_KEY und SECRET_KEY setzen
uvicorn frapp.api:app --reload
# → http://localhost:8000/docs
```

---

**Kontakt:** [NAME] · [EMAIL] · [LINKEDIN]
