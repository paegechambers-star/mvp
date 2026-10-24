# SCRIPTOR — KI-Ghostwriter & Arbeitsagent

Schreibt Bücher aller Arten im Namen der Autorin/des Autors — von der Idee bis zum
exportierten Manuskript inkl. Exposé, Klappentext und Agentur-Anschreiben. Läuft über
die Claude-API (Default: `claude-opus-5-5`).

## Windows-App

**Variante A: Installer-Skript** (empfohlen, ohne Adminrechte, Python 3.10+ nötig)

```powershell
git clone https://github.com/paegechambers-star/mvp.git
cd mvp
PowerShell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\install.ps1
```

Das Skript legt `%LOCALAPPDATA%\Scriptor\venv` und eine Verknüpfung **SCRIPTOR** auf dem
Desktop und im Startmenü an. Die App öffnet sich in einem eigenen Fenster (Edge WebView2,
ab Windows 10/11 vorinstalliert).

**Variante B: fertige EXE** (ohne Python)
GitHub → Actions → „SCRIPTOR Windows“ → letzter grüner Lauf → Artefakt `Scriptor-windows`.
ZIP entpacken und `Scriptor\Scriptor.exe` starten. Selbst bauen:
`.\packaging\windows\build.ps1` (erzeugt `dist\Scriptor-windows.zip`).

**Erster Start:** Einstellungen → API-Key eintragen. Er wird in der Windows-Anmeldeinformations­verwaltung
gespeichert, nie in einer Datei.

| Was | Wo (Windows) |
|---|---|
| Bücher, Exporte | `Dokumente\Scriptor` (änderbar in den Einstellungen) |
| Einstellungen | `%APPDATA%\Scriptor\settings.json` |
| Plugins | `%APPDATA%\Scriptor\plugins` |

### App-Funktionen

- **Bücher:** anlegen, Bible → Outline → Schreiben per Klick. Lange Läufe arbeiten im Hintergrund,
  der Fortschritt steht unten rechts. Pro Buch läuft höchstens ein Job gleichzeitig.
- **Kapitel-Editor:** Versionen durchblättern, selbst schreiben und als neue Version speichern,
  Lektorat mit Befunden und Zitaten, Überarbeitung mit eigener Anweisung.
- **Bible-Editor:** YAML bearbeiten, Commit nur mit Begründung (PATCH/SUPERSEDE, Register).
- **Quellen & Stimme:** Interviewnotizen hochladen, eigene Texte für das Voice-Profil.
- **Material & Export:** Exposé, Klappentext, Anschreiben … sowie Markdown- und Word-Export (.docx).
- **Agent:** Chat mit Werkzeugen. Teure Schritte laufen nur mit Haken „teure Werkzeuge erlauben“.
- **Plugins:** alle Docks mit Status und Beiträgen, Freigabe von Ordner-Plugins.
- **Register:** alle SSOT-Commits und Outputs mit ID.

Sicherheit: Der Server lauscht nur auf `127.0.0.1`. Jede API-Anfrage braucht einen pro Start
erzeugten Token. Fremde Host-Header werden abgewiesen (Schutz vor DNS-Rebinding).

## CLI-Setup (alle Systeme)

```bash
pip install -e ".[app]"           # SDK + Fenster + Tresor + Word-Export
scriptor config --set-api-key sk-ant-…   # oder ANTHROPIC_API_KEY setzen
scriptor app                      # Desktop-App
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

## Plugins (Docks)

Erweiterbar wie FraPP über Docks: Agent-Werkzeuge, Bucharten, Materialarten, API-Routen,
CLI-Befehle. Eingebaut: `lesbarkeit` (Flesch-Amstad, Wiener Sachtextformel) und `docx_export`.
Ordner-Plugins laufen nur nach Freigabe. Anleitung: [`docs/scriptor-plugins.md`](../docs/scriptor-plugins.md),
Beispiel: `examples/scriptor_plugins/kurzgeschichte.py`.

```bash
scriptor docks                         # geladene Docks + Beiträge
scriptor config --enable-plugin kurzgeschichte
scriptor lesbarkeit buch <slug>        # CLI-Befehl aus einem Dock
```

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
| Docks | `docks/` | Plugin-Registry; Fehler isoliert und zurückgerollt; Ordner-Plugins nur mit Freigabe |
| Laufzeit | `runtime.py`, `settings.py` | Einstellungen (Plattform-Pfade), API-Key im OS-Tresor, LLM-Fabrik |
| App | `app/` | FastAPI-Server (Token, nur localhost), Hintergrund-Jobs, Oberfläche, Launcher |
| Windows | `packaging/windows/` | `install.ps1`, `build.ps1` (PyInstaller), `Scriptor.bat` |

Ablage je Buch: `books/<slug>/{ssot,work,export}/`, `register.jsonl`, `audit.jsonl`.

## Grenzen (ehrlich)

- **Kein „macht alles“-Agent.** Er arbeitet nur mit Text/Dateien im Workspace. Kein E-Mail-Versand,
  kein Kalender, keine Shell. Erweiterung = Dock-Plugin (bewusst, mit Freigabe).
- **Windows-EXE ist nicht signiert.** SmartScreen warnt beim ersten Start („Weitere Informationen → Trotzdem
  ausführen“). Für Weitergabe an Dritte: Code-Signing-Zertifikat nötig.
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
python -m pytest tests/scriptor_tests   # offline, FakeLLM, keine API-Kosten (auch in CI auf Windows)
```
