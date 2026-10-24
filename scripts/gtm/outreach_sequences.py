#!/usr/bin/env python3
"""
FraPP + G.O.D.A.I. — Complete Outreach Sequences
3 Segmente × 3 Touches × 2 Kanäle = 18 fertige Nachrichten

Touch 1: erster Kontakt (Problem benennen)
Touch 2: +3 Tage (sozialer Beweis + Dringlichkeit)
Touch 3: +7 Tage (letzter Versuch, niedrige Einstiegshürde)

Usage:
  python scripts/gtm/outreach_sequences.py             # alle Segmente
  python scripts/gtm/outreach_sequences.py --segment cto
  python scripts/gtm/outreach_sequences.py --export
"""
from __future__ import annotations
import sys

BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"

# ─────────────────────────────────────────────────────────────────────────────
# SEGMENT 1 · CTO / Head of AI bei DACH SaaS
# Schmerz: EU AI Act August 2026, kein Audit-Trail
# ─────────────────────────────────────────────────────────────────────────────

SEG1 = {
    "label": "CTO / Head of AI — DACH SaaS",
    "pain":  "EU AI Act August 2026 — kein prüfbarer Audit-Trail",
    "where": "LinkedIn: 'CTO' + 'AI' + 'Germany' + '50-500 MA' | AngelList DACH",

    "li_t1": """\
Hallo {name},

{company} baut KI-Features — habt ihr schon eine Antwort auf EU AI Act Art. 12?

Ab August 2026: lückenloser, prüfbarer Audit-Trail für jede KI-Entscheidung. \
Pflicht, keine Option. Fehlt er beim Audit: bis zu 30 Mio. € oder 6% Jahresumsatz.

Wir haben genau dafür gebaut: G.O.D.A.I. — 5-stufige Governance-Pipeline, \
SHA256-Kette, DSGVO out of the box. 275 automatisierte Tests. 100% offline möglich.

Wäre ein 15-Minuten-Call sinnvoll?

Grüße""",

    "li_t2": """\
Hallo {name},

kurze Nachfassung zu meiner letzten Nachricht.

Ein konkreter Datenpunkt: Teams die heute ohne Governance-Infrastruktur arbeiten, \
brauchen erfahrungsgemäß 3–6 Monate Nacharbeit für eine EU AI Act Konformitätsprüfung.

Was wir liefern: Drop-in für FastAPI, 15 Minuten Setup, Audit-Artefakt sofort. \
Starter ab 149 €/Monat.

Habt ihr das intern schon adressiert — oder sucht ihr noch eine Lösung?""",

    "li_t3": """\
Hallo {name},

letzte Nachricht von mir — ich will eure Zeit nicht verschwenden.

Falls EU AI Act aktuell kein Thema ist: kein Problem, vielleicht später.

Falls doch: ich schicke euch gerne das Demo-Repo + Swagger-Docs, \
ihr könnt es in 15 Minuten selbst testen. Kein Call, kein Pitch — nur Code.

Einfach antworten mit "Demo" und ich schicke den Link.""",

    "mail_t1": """\
Betreff: EU AI Act August 2026 — habt ihr den Audit-Trail?

Hallo {name},

ihr baut KI-Features bei {company}. Ab August 2026 ist ein lückenloser, \
kryptografisch prüfbarer Audit-Trail für KI-Entscheidungen EU-Pflicht (Art. 12).

Was wir gebaut haben — G.O.D.A.I.:
→ 5-Modul-Pipeline: Auth → Policy → Routing → Validierung → Audit-Log
→ SHA256-Kette: jeder Eintrag mit dem vorherigen verbunden, Manipulation sofort erkannt
→ DSGVO Art. 15/17/20 Endpunkte eingebaut
→ 100% offline betreibbar (keine Daten verlassen eure Infrastruktur)
→ 30/30 OWASP-Angriffsvektoren blockiert (verifiziert, Protokoll vorhanden)

Preis: 149 €/Monat Starter · 799 €/Monat Pro · 3.500 €/Monat Enterprise
Self-Hosted (Quellcode): 15.000 € einmalig

15-Minuten-Demo diese Woche?

{sender}""",

    "mail_t2": """\
Betreff: Re: EU AI Act — Demo-Link für {company}

Hallo {name},

ich folge kurz nach. Hier direkt der Link zum laufenden System:
→ Swagger /docs: zeigt alle Endpunkte live
→ GET /v1/godai/audit: die kryptografische Kette in Echtzeit
→ GET /v1/godai/status: Chain-Integrität, Anzahl Einträge

Ein Beispiel was der Audit-Trail bei einem regulatorischen Check beweist:
jede KI-Anfrage wird mit User-ID, Trust-Level, Policy-Entscheidung, \
verwendetem Modell und Validierungs-Verdict protokolliert — unveränderbar.

Habt ihr 15 Minuten für eine kurze Demo?

{sender}""",

    "mail_t3": """\
Betreff: Letzte Nachricht — Demo-Repo für {company}

Hallo {name},

letzte E-Mail von mir.

Falls EU AI Act gerade kein Prioritätsthema ist: völlig verständlich. \
Ich hinterlasse trotzdem das Demo-Repo — ihr könnt es jederzeit selbst ausprobieren:

  git clone [REPO_URL]
  pip install -r requirements.txt
  uvicorn frapp.api:app --reload
  # → http://localhost:8000/docs

Wenn sich das ändert oder ihr Fragen habt: einfach melden.

{sender}""",
}

# ─────────────────────────────────────────────────────────────────────────────
# SEGMENT 2 · Compliance / CCO bei Bank, Versicherung, Fintech
# Schmerz: DSGVO Art. 22 + EU AI Act = doppelter Audit
# ─────────────────────────────────────────────────────────────────────────────

SEG2 = {
    "label": "CCO / Compliance bei Bank / Versicherung / Fintech",
    "pain":  "DSGVO + EU AI Act — zwei Audits, ein System gesucht",
    "where": "LinkedIn: 'Compliance' + 'KI' + 'DACH' | BaFin-regulierte Unternehmen",

    "li_t1": """\
Hallo {name},

DSGVO Art. 22 und EU AI Act sind zwei verschiedene Prüfpflichten — \
die meisten Compliance-Teams bereiten sie getrennt vor. Das verdoppelt den Aufwand.

G.O.D.A.I. erfüllt beide in einer Infrastruktur: \
kryptografisch verkettete Logs (EU AI Act Art. 12) + \
Auskunfts-/Lösch-/Export-Endpunkte (DSGVO Art. 15/17/20). \
Vollständig On-Premise — BaFin/FINMA-konform.

Wäre ein kurzes Gespräch sinnvoll?""",

    "li_t2": """\
Hallo {name},

ein konkreter Mehrwert für euren nächsten Audit:

Unser System erzeugt bei jedem KI-Aufruf automatisch:
- Wer hat angefragt (User-ID, Trust-Level)
- Welche Policy hat entschieden (ja/nein, Begründung)
- Welches Modell wurde verwendet
- Hat die Validierung bestätigt (Vier-Augen-Prinzip)
- SHA256-Hash des Eintrags + vorheriger Hash (Kette unmanipulierbar)

Das ist exakt das was ein BaFin-Prüfer sehen will.

Habt ihr so etwas gerade in eurer Infrastruktur?""",

    "li_t3": """\
Hallo {name},

letzter Versuch — falls Compliance-Infrastruktur für KI gerade kein Thema ist, \
kein Problem.

Für den Fall dass doch: Self-Hosted Lizenz für 15.000 € einmalig, \
Quellcode, keine laufenden Gebühren, keine Cloud-Abhängigkeit. \
Für manche Häuser die einzige akzeptable Option.

Einfach antworten falls Interesse.""",

    "mail_t1": """\
Betreff: DSGVO + EU AI Act — eine Infrastruktur für beide Anforderungen

Hallo {name},

Compliance-Teams in regulierten Branchen stehen vor einer Doppelbelastung: \
DSGVO verlangt Auskunfts- und Löschrecht. \
EU AI Act verlangt prüfbare, unveränderliche Logs für KI-Entscheidungen.

Zwei separate Systeme = doppelte Audit-Kosten.

FraPP + G.O.D.A.I. löst beides:
→ SHA256-Kette: Manipulation wird beim nächsten Start sofort erkannt
→ GET /v1/me/data · DELETE /v1/me/data · GET /v1/me/export
→ Jede KI-Entscheidung: User-ID, Policy, Modell, Validierung — protokolliert
→ On-Premise: keine Daten verlassen euer Rechenzentrum
→ BaFin / FINMA / SNB kompatibel (keine US-Cloud-Abhängigkeit)

Preis: 149 €/Monat · Self-Hosted: 15.000 € einmalig (Quellcode-Lizenz)

Darf ich eine kurze Demo schicken?

{sender}""",

    "mail_t2": """\
Betreff: Re: DSGVO + EU AI Act — Audit-Protokoll als Anhang

Hallo {name},

zur Veranschaulichung: so sieht ein G.O.D.A.I. Audit-Eintrag aus (JSON):

  {{
    "chain_index": 42,
    "event_type": "policy_decision",
    "source_module": "THEMIS",
    "timestamp": "2026-04-19T10:23:11Z",
    "event_data": {{
      "user_id": "user-123",
      "trust_level": "L2",
      "allowed": true,
      "reason": "policy:allow_internal_data_class_L2"
    }},
    "hash": "a3f2...e91b",
    "prev_hash": "8d4c...f02a"
  }}

Jeder Eintrag ist kryptografisch mit dem vorherigen verbunden. \
Ein Prüfer kann die gesamte Kette in Sekunden verifizieren.

15-Minuten-Call um das live zu zeigen?

{sender}""",

    "mail_t3": """\
Betreff: Letzte E-Mail — On-Premise Demo für {company}

Hallo {name},

letzte Nachricht von mir.

Falls KI-Governance-Infrastruktur gerade kein akutes Thema ist: vollkommen verständlich.

Für später: wir bieten eine Self-Hosted-Option (15.000 € einmalig, Quellcode, \
keine laufenden Kosten, keine Cloud). Für regulierte Häuser oft die einzige Option.

Demo-Repo steht jederzeit zur Verfügung. Einfach melden.

{sender}""",
}

# ─────────────────────────────────────────────────────────────────────────────
# SEGMENT 3 · AI Engineer / CTO bei Healthcare / HR Tech (Hochrisiko)
# Schmerz: EU AI Act Hochrisiko-Zertifizierung blockiert Go-live
# ─────────────────────────────────────────────────────────────────────────────

SEG3 = {
    "label": "AI Engineer / CTO bei Healthcare / HR Tech (Hochrisiko-KI)",
    "pain":  "EU AI Act Hochrisiko-Zertifizierung blockiert Go-live",
    "where": "LinkedIn: 'ML Engineer' + 'Healthcare AI' / 'HR Tech' | HIMSS | RecFest",

    "li_t1": """\
Hallo {name},

Hochrisiko-KI unter EU AI Act (Medizin, HR, Kredit) braucht ab 2026 \
eine konformitätsbewertete Governance-Infrastruktur — das blockiert viele Go-lives.

G.O.D.A.I. ist ein Drop-in für FastAPI-Backends: \
5 Module, YAML-konfigurierbar, 15 Minuten Setup. \
275 automatisierte Tests, SHA256-Audit-Chain, \
ATHENA-Modul dokumentiert die menschliche Aufsicht (EU AI Act Art. 14).

Interessiert? Ich schicke das Demo-Repo.""",

    "li_t2": """\
Hallo {name},

kurze Nachfassung. Was euren Audit konkret vereinfacht:

EU AI Act Checkliste für Hochrisiko-Systeme:
✓ Art. 12 Audit-Trail → MNEMOSYNE SHA256-Kette (automatisch)
✓ Art. 13 Transparenz → jede Entscheidung protokolliert (User, Policy, Modell)
✓ Art. 14 Menschliche Aufsicht → ATHENA Validierungsmodul
✓ Art. 10 Datensätze → THEMIS Policy-Engine (konfigurierbar ohne Code)

Das sind die vier Punkte die ein Notified Body als erstes prüft.

Habt ihr die alle abgedeckt?""",

    "li_t3": """\
Hallo {name},

letzter Versuch — kein Call notwendig.

Ich schicke euch einfach:
1. Das Demo-Repo (15 Minuten setup, läuft lokal)
2. Den L4 Security Test Report (30/30 OWASP blockiert)
3. Eine EU AI Act Mapping-Tabelle: welches Modul welchen Artikel abdeckt

Einfach "Ja" antworten und ich schicke alles.""",

    "mail_t1": """\
Betreff: EU AI Act Hochrisiko — Governance-Infrastruktur die den Go-live entsperrt

Hallo {name},

wenn ihr ein Hochrisiko-KI-System baut (Healthcare, HR, Finance), \
ist die EU AI Act Konformitätsbewertung ein harter Launch-Blocker.

Was ein Notified Body als erstes prüft — und wie G.O.D.A.I. es abdeckt:

EU AI Act Art.  | Anforderung              | G.O.D.A.I. Modul
─────────────────────────────────────────────────────────────
Art. 12         | Prüfbarer Audit-Trail    | MNEMOSYNE SHA256-Kette
Art. 13         | Transparenz              | Vollprotokoll jeder Entscheidung
Art. 14         | Menschliche Aufsicht     | ATHENA (Generator ≠ Prüfer)
Art. 10         | Datensatz-Governance     | THEMIS YAML-Policy-Engine

Alles in einem System. Drop-in für FastAPI. 15 Minuten Setup.

Preis: 149 €/Monat · Self-Hosted: 15.000 € einmalig

Demo-Repo + Swagger-Docs schicke ich sofort. Interesse?

{sender}""",

    "mail_t2": """\
Betreff: Re: EU AI Act Hochrisiko — konkretes Mapping für {company}

Hallo {name},

ich folge kurz nach mit etwas Konkretem:

Unser System hat 275 automatisierte Tests — davon 18 reine Invarianten-Angriffe \
("kann die Pipeline ihren eigenen Audit-Trail manipulieren?" → Nein, beweisbar).

Das Ergebnis ist ein maschinenlesbares Protokoll das direkt als \
Konformitätsnachweis eingereicht werden kann.

Ich kann euch schicken:
→ Das vollständige Test-Protokoll (JSON + Human-readable)
→ Den EU AI Act Mapping-Report
→ Das Demo-Repo zum selbst testen

Einfach antworten — kein Call notwendig wenn ihr das lieber asynchron prüft.

{sender}""",

    "mail_t3": """\
Betreff: Letzte Nachricht — EU AI Act Mapping-Tabelle für euch

Hallo {name},

letzte E-Mail.

Ich lasse euch die EU AI Act Mapping-Tabelle hier — auch wenn ihr \
aktuell kein Interesse habt, vielleicht ist sie für interne Diskussionen nützlich:

Art. 9  Risikomanagement     → THEMIS Policy-Engine (YAML, auditierbar)
Art. 10 Datensätze           → GDPR-Endpunkte + Tenant-Isolation
Art. 12 Aufzeichnungspflicht → MNEMOSYNE (SHA256, SQLite, persistent)
Art. 13 Transparenz          → Vollprotokoll + /v1/godai/audit Endpunkt
Art. 14 Menschl. Aufsicht    → ATHENA (separate Validierungs-KI, kein Self-Check)
Art. 17 Dokumentation        → OpenAPI /docs + Audit-Chain-Export

Repo: [REPO_URL] | Docs: [DOCS_URL]

Viel Erfolg mit dem Projekt.

{sender}""",
}

SEGMENTS = {"cto": SEG1, "compliance": SEG2, "engineer": SEG3}


def print_segment(seg: dict, sender: str = "Dein Name"):
    print(f"\n{CYAN}{BOLD}{'═' * 68}{RESET}")
    print(f"{CYAN}{BOLD}  {seg['label']}{RESET}")
    print(f"{CYAN}  Schmerz : {seg['pain']}{RESET}")
    print(f"{CYAN}  Wo      : {seg['where']}{RESET}")
    print(f"{CYAN}{BOLD}{'═' * 68}{RESET}\n")

    touches = [
        ("LinkedIn", "Touch 1 — Tag 0",  seg["li_t1"]),
        ("LinkedIn", "Touch 2 — Tag 3",  seg["li_t2"]),
        ("LinkedIn", "Touch 3 — Tag 10", seg["li_t3"]),
        ("E-Mail",   "Touch 1 — Tag 0",  seg["mail_t1"]),
        ("E-Mail",   "Touch 2 — Tag 3",  seg["mail_t2"]),
        ("E-Mail",   "Touch 3 — Tag 10", seg["mail_t3"]),
    ]
    for channel, label, text in touches:
        print(f"  {YELLOW}[{channel} · {label}]{RESET}")
        for line in text.format(name="[VORNAME]", company="[UNTERNEHMEN]",
                                sender=sender).strip().split("\n"):
            print(f"    {line}")
        print()


def main():
    sender = "Dein Name"
    args = sys.argv[1:]

    if "--segment" in args:
        idx = args.index("--segment")
        key = args[idx + 1] if idx + 1 < len(args) else None
        if key in SEGMENTS:
            print_segment(SEGMENTS[key], sender)
            return
        else:
            print(f"Unbekanntes Segment '{key}'. Optionen: cto, compliance, engineer")
            sys.exit(1)

    if "--export" in args:
        _export_all(sender)
        return

    # Default: alle Segmente
    print(f"\n{BOLD}FraPP + G.O.D.A.I. — Vollständige Outreach-Sequenzen{RESET}")
    print(f"{BOLD}3 Segmente · 3 Touches · 2 Kanäle = 18 fertige Nachrichten{RESET}")
    for seg in SEGMENTS.values():
        print_segment(seg, sender)

    print(f"\n{BOLD}── Nächste Schritte ──────────────────────────────────────────────{RESET}")
    steps = [
        ("Tag 0",   "LinkedIn Sales Nav: 20 Kontakte pro Segment identifizieren"),
        ("Tag 0",   "HubSpot / Notion: CSV importieren (--export Flag)"),
        ("Tag 1",   "Loom aufnehmen: 3 Min · MNEMOSYNE live · /docs · L4-Test"),
        ("Tag 1-3", "Touch 1 (LinkedIn + E-Mail) an alle 60 Kontakte senden"),
        ("Tag 4-6", "Touch 2 an alle ohne Antwort"),
        ("Tag 11",  "Touch 3 (Break-up Message) — dann abhaken"),
        ("Laufend", "Antworten → Demo-Call buchen → 149 €/Monat Starter pitchen"),
    ]
    for tag, step in steps:
        print(f"  {GREEN}{tag:<10}{RESET} {step}")
    print()


def _export_all(sender: str):
    import csv, io
    rows = []
    for seg_key, seg in SEGMENTS.items():
        rows.append({
            "segment": seg_key,
            "label": seg["label"],
            "pain": seg["pain"],
            "where": seg["where"],
            "name": "[VORNAME]",
            "company": "[UNTERNEHMEN]",
            "li_t1": seg["li_t1"].format(name="[VORNAME]", company="[UNTERNEHMEN]", sender=sender),
            "li_t2": seg["li_t2"].format(name="[VORNAME]", company="[UNTERNEHMEN]", sender=sender),
            "li_t3": seg["li_t3"].format(name="[VORNAME]", company="[UNTERNEHMEN]", sender=sender),
            "mail_t1": seg["mail_t1"].format(name="[VORNAME]", company="[UNTERNEHMEN]", sender=sender),
            "mail_t2": seg["mail_t2"].format(name="[VORNAME]", company="[UNTERNEHMEN]", sender=sender),
            "mail_t3": seg["mail_t3"].format(name="[VORNAME]", company="[UNTERNEHMEN]", sender=sender),
            "status": "not_started",
        })
    filename = "outreach_all_sequences.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{GREEN}✓ Exportiert: {filename} ({len(rows)} Segmente){RESET}")


if __name__ == "__main__":
    main()
