# SCRIPTOR — KI-Ghostwriter & Arbeitsagent

Schreibt Bücher aller Arten im Namen der Autorin/des Autors — von der Idee bis zum
exportierten Manuskript inkl. Exposé, Klappentext und Agentur-Anschreiben. Läuft über
die Claude-API (Default: `claude-opus-5-5`).

## Setup

```bash
pip install -e .                 # installiert auch das anthropic-SDK
export ANTHROPIC_API_KEY=sk-ant-…  # oder: ant auth login
export SCRIPTOR_HOME=~/scriptor-workspace   # optional, sonst ./scriptor-workspace
```

## Workflow (Buch)

```bash
scriptor genres                                         # 12 Bucharten
scriptor new "Die Stimmen der Stadt" -g young_adult -i "Berlin spricht nachts zu Mila" -a "Chambi"
scriptor voice  die-stimmen-der-stadt probe1.txt probe2.txt   # optional: deine Stimme lernen
scriptor source die-stimmen-der-stadt interview.md            # Pflicht bei Memoir/Sachbuch
scriptor bible   die-stimmen-der-stadt --notes "Band 1 einer Trilogie"
scriptor outline die-stimmen-der-stadt
scriptor write-book die-stimmen-der-stadt --start 1 --end 3   # erst testen, dann alles
scriptor status  die-stimmen-der-stadt
scriptor review  die-stimmen-der-stadt 2
scriptor revise  die-stimmen-der-stadt 2 -i "Mehr Humor, Dialog straffen"
scriptor material die-stimmen-der-stadt expose
scriptor export  die-stimmen-der-stadt
```

## Agent (freie Aufträge)

```bash
scriptor agent "Leg ein Bilderbuch über einen ängstlichen Leuchtturm an und entwickle die Bible"
scriptor agent --web "Recherchiere Vergleichstitel für die-stimmen-der-stadt und schreib ein Exposé"
scriptor chat
```

Teure Werkzeuge (Bible, Outline, Entwurf, Revision, Komplettlauf) fragen vorher nach;
`--yes` schaltet das ab.

## Architektur

| Baustein | Datei | Regel |
|---|---|---|
| Bucharten | `genres/*.yaml` | Policy = Data: Struktur, Umfang, Stil, Lektorats-Checkliste. Neue Buchart = neue YAML. |
| Qualitäts-Gate | `config.yaml` | Score-Schwelle, Revisionslimit, Wort-/Voice-Toleranz, Effort je Schritt |
| Projekt | `project.py` | SSOT (Bible, Outline, Voice, Quellen) nur per `commit_ssot` (CREATE/PATCH/SUPERSEDE + Begründung). Kapitel versioniert, nie überschrieben. Alles im `register.jsonl` mit ID. |
| Ghostwriter | `ghostwriter.py` | **Generator ≠ Arbiter**: Lektorat ist eine separate Rolle; PASS/REVISE entscheidet `gate()` im Code, nicht das LLM. |
| Voice | `voice.py` | Deterministische Stilometrie → Zielwerte im Prompt + Abweichungsmessung im Gate |
| Agent | `agent.py` | Tool-Loop; Dateizugriff nur im Workspace; SSOT nicht per `write_file` änderbar |
| Audit | `audit.py` | SHA256-Kette, Prompts nur als Hash (Manuskripte bleiben vertraulich) |

Ablage je Buch: `books/<slug>/{ssot,work,export}/`, `register.jsonl`, `audit.jsonl`.

## Grenzen (ehrlich)

- **Kein „macht alles“-Agent.** Er arbeitet nur mit Text/Dateien im Workspace. Kein E-Mail-Versand,
  kein Kalender, keine Shell. Erweiterung = neues Werkzeug in `agent.py` (bewusst, mit Rechteprüfung).
- **Qualität ≠ druckreif ohne dich.** Das Gate fängt Strukturfehler, Bible-Widersprüche und
  Stil-Drift ab; literarische Endabnahme bleibt menschlich.
- **Non-Fiction:** Fakten nur aus `ssot/sources/`. Fehlendes wird mit `[UNVERIFIED]`,
  `[QUELLE BENÖTIGT]`, `[FRAGE AN AUTOR: …]` markiert — vor Veröffentlichung abarbeiten.
- **Kosten:** Ein Roman mit 30 Kapiteln und bis zu 2 Revisionen = ca. 90–150 API-Aufrufe mit
  langen Ausgaben. Erst `--end 3` testen.
- **Rechtliches:** Ghostwriting-Rechte/Vertrag, Persönlichkeitsrechte Dritter (Memoir) und
  Kennzeichnungspflichten für KI-Texte beim Verlag klären.

## Tests

```bash
python -m pytest tests/scriptor_tests   # offline, FakeLLM, keine API-Kosten
```
