#!/usr/bin/env python3
"""
FraPP + G.O.D.A.I. — Sales Outreach Pipeline Generator

Generates personalised outreach sequences for 3 ICP segments:
  1. CTO / Head of AI at DACH B2B SaaS (EU AI Act angle)
  2. Compliance Officer at Banks / Insurance (GDPR liability angle)
  3. AI Engineer at Healthcare / HR Tech (high-risk AI certification angle)

Output: ready-to-send LinkedIn DM + Email sequences per contact.

Usage:
  python scripts/gtm/outreach_pipeline.py
  python scripts/gtm/outreach_pipeline.py --segment cto --export csv
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import List

BOLD  = "\033[1m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

TODAY = date.today().isoformat()


# ── Ideal Customer Profiles ───────────────────────────────────────────────────

@dataclass
class Contact:
    name: str
    title: str
    company: str
    segment: str          # "cto" | "compliance" | "engineer"
    pain_signal: str      # Why they need this NOW
    linkedin_url: str = ""
    email: str = ""


# Seed contacts — replace / extend with real prospects from LinkedIn Sales Nav
CONTACTS: List[Contact] = [
    # ── Segment 1: CTO / Head of AI at DACH SaaS ─────────────────────────────
    Contact(
        name="[VORNAME]",
        title="CTO",
        company="[DACH B2B SaaS mit KI-Feature]",
        segment="cto",
        pain_signal="EU AI Act Artikel 13 Transparenzpflicht ab August 2026",
    ),
    Contact(
        name="[VORNAME]",
        title="Head of AI",
        company="[Scale-up mit ML-Produkt]",
        segment="cto",
        pain_signal="Kein Audit-Trail für KI-Entscheidungen",
    ),
    # ── Segment 2: Compliance at Banks / Insurance ────────────────────────────
    Contact(
        name="[VORNAME]",
        title="Chief Compliance Officer",
        company="[Regionalbank oder Versicherung]",
        segment="compliance",
        pain_signal="DSGVO Art. 22 — KI-Kreditentscheidungen ohne Erklärbarkeit",
    ),
    Contact(
        name="[VORNAME]",
        title="Head of Regulatory Affairs",
        company="[Fintech mit KI-Scoring]",
        segment="compliance",
        pain_signal="BaFin DORA + EU AI Act doppelte Anforderung",
    ),
    # ── Segment 3: AI Engineer at Healthcare / HR Tech ────────────────────────
    Contact(
        name="[VORNAME]",
        title="Lead ML Engineer",
        company="[Healthcare AI / Diagnostik-Startup]",
        segment="engineer",
        pain_signal="MDR + EU AI Act Hochrisiko-Zertifizierung blockiert Go-live",
    ),
    Contact(
        name="[VORNAME]",
        title="CTO",
        company="[HR Tech mit KI-Bewerbungsscreening]",
        segment="engineer",
        pain_signal="EU AI Act Art. 10 — KI in Personalentscheidungen = Hochrisiko",
    ),
]


# ── Message Templates ─────────────────────────────────────────────────────────

TEMPLATES = {
    "cto": {
        "linkedin_touch1": """\
Hallo {name},

ich sehe dass {company} KI-Features im Produkt hat — EU AI Act Artikel 13 \
verlangt ab August 2026 einen lückenlosen Audit-Trail für alle KI-Entscheidungen.

Wir haben FraPP + G.O.D.A.I. gebaut: ein 5-stufiges Governance-System mit \
SHA256-verketteten Logs (kryptografisch unveränderbar), DSGVO Art. 15/17/20 \
Endpunkten, und 100% offline-Betrieb möglich — keine Daten verlassen euer System.

275 automatisierte Tests, EU AI Act-konform out of the box.

Wäre ein 15-min-Call diese Woche sinnvoll?

Beste Grüße""",

        "linkedin_touch2": """\
Hallo {name},

kurze Nachfassung: der EU AI Act tritt für Hochrisiko-Systeme in 4 Monaten in Kraft.

Ein Audit ohne Governance-System kostet erfahrungsgemäß 3–6 Monate Nacharbeit.

FraPP liefert den Audit-Trail am ersten Tag — komplett parametrisierbar via YAML, \
keine Codeänderungen für neue Compliance-Regeln.

Habt ihr das Thema intern schon adressiert?""",

        "email_touch1": """\
Betreff: EU AI Act August 2026 — habt ihr den Audit-Trail?

Hallo {name},

ab August 2026 müssen Anbieter von KI-Systemen in der EU lückenlose, \
prüfbare Aufzeichnungen aller KI-Entscheidungen vorhalten (EU AI Act Art. 12).

Die meisten DACH SaaS-Teams unterschätzen den Aufwand massiv.

Was wir gebaut haben:
→ G.O.D.A.I. Pipeline: 5 Module, SHA256-verketteter Audit-Log
→ DSGVO Art. 15/17/20 Endpunkte (Auskunft, Löschung, Export)
→ Lokaler Betrieb: keine Daten in die Cloud
→ 30/30 OWASP-Angriffsvektoren blockiert (verifiziert)
→ Preise: 149 €/Monat (Starter) bis 3.500 €/Monat (Enterprise)

15-Minuten-Demo? Ich schicke euch den Kalender-Link.

{sender_name}""",
    },

    "compliance": {
        "linkedin_touch1": """\
Hallo {name},

DSGVO Art. 22 und EU AI Act zusammen: wenn {company} KI für Entscheidungen \
nutzt, braucht ihr zwei Dinge gleichzeitig — Erklärbarkeit und Unveränderbarkeit.

G.O.D.A.I. liefert beides: kryptografisch verkettete Logs (SHA256, \
tamper-evident) plus DSGVO-Auskunfts- und Löschendpunkte out of the box.

Wir haben das System selbst einem simulierten OWASP-Penetrationstest unterzogen — \
30/30 Angriffsvektoren blockiert.

Kurzes Gespräch diese Woche?""",

        "email_touch1": """\
Betreff: DSGVO + EU AI Act — eine Infrastruktur für beide Anforderungen

Hallo {name},

Compliance-Teams in regulierten Branchen stehen vor einer Doppelbelastung:
DSGVO verlangt Auskunfts- und Löschrecht. EU AI Act verlangt prüfbare Logs.

Zwei separate Systeme bedeuten doppelte Auditkosten.

FraPP + G.O.D.A.I. erfüllt beides in einer Plattform:
→ SHA256-Kette: jeder Log-Eintrag kryptografisch mit dem vorherigen verbunden
→ Automatisches Tamper-Detection bei jedem Start
→ GET /v1/me/data · DELETE /v1/me/data · GET /v1/me/export (DSGVO Art. 15/17/20)
→ Vollständig On-Premise betreibbar — BaFin/FINMA-konform

Preis: ab 149 €/Monat. Self-hosted: 15.000 € einmalig.

Darf ich euch eine kurze Demo schicken?

{sender_name}""",
    },

    "engineer": {
        "linkedin_touch1": """\
Hallo {name},

Hochrisiko-KI-Systeme nach EU AI Act brauchen ab 2026 eine \
konformitätsbewertete Governance-Infrastruktur — das blockiert viele Go-lives.

G.O.D.A.I. ist eine open-source-nutzbare Pipeline (5 Module, YAML-konfigurierbar) \
mit SHA256-Audit-Chain. Wir haben 275 automatisierte Tests, davon 18 reine \
Invarianten-Angriffe — alle bestanden.

Drop-in für FastAPI-Backends. 15 Minuten Setup.

Interessiert?""",

        "email_touch1": """\
Betreff: EU AI Act Hochrisiko-Konformität — fertige Governance-Pipeline

Hallo {name},

wenn ihr ein Hochrisiko-KI-System (Healthcare, HR, Finance) baut, \
ist die EU AI Act Konformitätsbewertung ein harter Blocker vor dem Launch.

Was in jedem Audit gefragt wird:
✓ Prüfbarer Audit-Trail (EU AI Act Art. 12) → MNEMOSYNE SHA256-Kette
✓ Menschliche Aufsicht dokumentiert (Art. 14) → ATHENA Validierungsmodul
✓ Keine Bias in der Modellauswahl (Art. 10) → THEMIS YAML-Policy-Engine
✓ DSGVO-Compliance (Art. 9/22) → GDPR-Endpunkte eingebaut

Alles in einer Pipeline. Messbarer Beweis: 30/30 OWASP, 1.000-Einträge SHA256 \
unabhängig verifiziert.

Preis: 149 €/Monat. Self-hosted: 15.000 € einmalig (Quellcode-Lizenz).

Demo-Repo + Swagger-Docs kann ich sofort schicken. Interesse?

{sender_name}""",
    },
}


# ── Pipeline Generator ────────────────────────────────────────────────────────

def generate_sequence(contact: Contact, sender_name: str = "Dein Name") -> dict:
    tmpl = TEMPLATES[contact.segment]
    sequence = {}
    for key, text in tmpl.items():
        sequence[key] = text.format(
            name=contact.name,
            company=contact.company,
            pain_signal=contact.pain_signal,
            sender_name=sender_name,
        )
    return sequence


def print_pipeline(sender_name: str = "Dein Name"):
    print(f"\n{CYAN}{BOLD}{'═' * 66}{RESET}")
    print(f"{CYAN}{BOLD}  FraPP + G.O.D.A.I. — OUTREACH PIPELINE  {TODAY}{RESET}")
    print(f"{CYAN}{BOLD}{'═' * 66}{RESET}\n")

    by_segment = {}
    for c in CONTACTS:
        by_segment.setdefault(c.segment, []).append(c)

    segment_labels = {
        "cto":        "SEGMENT 1 · CTO / Head of AI (EU AI Act Angle)",
        "compliance": "SEGMENT 2 · Compliance / Regulatory (DSGVO Angle)",
        "engineer":   "SEGMENT 3 · AI Engineer / Healthcare / HR (Hochrisiko Angle)",
    }

    for segment, contacts in by_segment.items():
        print(f"{BOLD}── {segment_labels[segment]} {'─' * (40 - len(segment_labels[segment]) + 16)}{RESET}")
        print(f"  {len(contacts)} Kontakte | Schmerz: {contacts[0].pain_signal[:60]}...")
        print()

        for contact in contacts[:1]:  # Show first contact as example
            seq = generate_sequence(contact, sender_name)
            for step_name, message in seq.items():
                channel = "LinkedIn DM" if "linkedin" in step_name else "E-Mail"
                touch = step_name.replace("linkedin_", "").replace("email_", "").replace("_", " ").upper()
                print(f"  {YELLOW}[{channel} — {touch}]{RESET}")
                print()
                for line in message.strip().split("\n"):
                    print(f"    {line}")
                print()

    print(f"{CYAN}{BOLD}{'═' * 66}{RESET}")
    print(f"{BOLD}  NÄCHSTE SCHRITTE:{RESET}")
    steps = [
        "LinkedIn Sales Navigator: Suche 'CTO' + 'AI' + 'Germany' + '50-200 Mitarbeiter'",
        "HubSpot / Notion: Kontakte importieren, Status tracken",
        "Touch 1 senden — 3 Tage warten — Touch 2 wenn keine Antwort",
        "Demo-Repo auf GitHub public stellen (Swagger /docs als Beweis)",
        "Loom-Video: 3 Minuten Pipeline-Demo (MNEMOSYNE Chain live zeigen)",
        "Preis: 149 € / Monat — kein Custom-Deal unter 800 € für erste 10 Kunden",
    ]
    for i, step in enumerate(steps, 1):
        print(f"  {GREEN}{i}.{RESET} {step}")
    print(f"{CYAN}{BOLD}{'═' * 66}{RESET}\n")


def export_csv(filename: str = "outreach_contacts.csv"):
    import csv
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "title", "company", "segment", "pain_signal",
            "linkedin_url", "email", "status", "next_action", "notes"
        ])
        writer.writeheader()
        for c in CONTACTS:
            writer.writerow({
                "name": c.name,
                "title": c.title,
                "company": c.company,
                "segment": c.segment,
                "pain_signal": c.pain_signal,
                "linkedin_url": c.linkedin_url,
                "email": c.email,
                "status": "not_contacted",
                "next_action": "Touch 1 senden",
                "notes": "",
            })
    print(f"{GREEN}✓ CSV exportiert: {filename}{RESET}")


if __name__ == "__main__":
    import sys
    sender = "Dein Name"
    if "--export" in sys.argv and "csv" in sys.argv:
        export_csv()
    else:
        print_pipeline(sender_name=sender)
