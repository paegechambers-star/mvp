# SCRIPTOR-Plugins (Docks)

SCRIPTOR übernimmt das Dock-Konzept von FraPP: Ein Plugin ist eine Klasse mit `name`
und `load()`. In `load()` meldet das Dock seine Beiträge bei der Registry an.

## Was ein Dock beitragen kann

| Methode | Wirkung | Sichtbar in |
|---|---|---|
| `registry.add_tool(name, beschreibung, json_schema, handler, confirm=False)` | Neues Agent-Werkzeug. `handler(agent, **input) -> str` | Agent (App + CLI) |
| `registry.add_genre_dir(pfad)` | Ordner mit Buchart-YAMLs (Format wie `scriptor/genres/*.yaml`) | Buchart-Auswahl, Ghostwriter |
| `registry.add_material(art, auftrag)` | Neue Art von Begleitmaterial | Material & Export, Agent |
| `registry.add_router(fastapi.APIRouter())` | Eigene API-Endpunkte (Pfad mit `/api/` beginnen → Token-geschützt) | App-Server |
| `registry.add_cli(name, typer.Typer())` | Eigene CLI-Befehlsgruppe: `scriptor <name> …` | CLI |

`load()` gibt `True` zurück, wenn das Dock aktiv sein soll. Mit `False` (z. B. bei einer
fehlenden Abhängigkeit) oder einer Exception wird alles zurückgerollt, was das Dock bis
dahin registriert hat. Ein kaputtes Plugin legt die App nicht lahm.

## Drei Wege, ein Plugin zu installieren

### 1. Ordner-Plugin (schnell, für eigene Erweiterungen)

1. Eine `.py`-Datei mit einer Variable `DOCK` (Klasse oder Instanz) anlegen.
2. In den Plugin-Ordner kopieren:
   - Windows: `%APPDATA%\Scriptor\plugins`
   - sonst: `~/.config/scriptor/plugins`
   - Der genaue Pfad steht in der App unter **Plugins** und bei `scriptor docks`.
3. Freigeben: App → Plugins → Haken setzen → speichern, oder
   `scriptor config --enable-plugin <dateiname-ohne-.py>`.
4. SCRIPTOR neu starten.

> **Sicherheit:** Ein Ordner-Plugin ist beliebiger Python-Code und läuft mit deinen
> Benutzerrechten. Deshalb wird es erst nach expliziter Freigabe geladen. Gib nur eigene
> oder vollständig gelesene Plugins frei.

Vollständiges Beispiel: `examples/scriptor_plugins/kurzgeschichte.py`. Es liefert eine
Buchart „Kurzgeschichte“, das Werkzeug `word_repetitions` und die Materialart
`pitch_tweet`.

### 2. pip-Paket (zum Weitergeben, versionierbar)

```toml
# pyproject.toml deines Plugin-Pakets
[project]
name = "scriptor-mein-plugin"
version = "1.0.0"
dependencies = ["frapp"]          # bringt scriptor mit

[project.entry-points."scriptor.docks"]
mein_plugin = "scriptor_mein_plugin:MeinDock"
```

`pip install scriptor-mein-plugin` in dieselbe Umgebung (Windows: `%LOCALAPPDATA%\Scriptor\venv`).
Entry-Point-Plugins sind standardmäßig aktiv und lassen sich unter **Plugins** abschalten.

### 3. Eingebaut

Neues Dock in `scriptor/docks/builtin.py` anlegen und in `BUILTIN_DOCKS` eintragen.
Referenzen: `LesbarkeitDock` (Werkzeug + CLI + API) und `DocxExportDock` (optionale Abhängigkeit).

## Minimalbeispiel

```python
from scriptor.docks import Dock, DockRegistry


class ZeichenDock(Dock):
    name = "zeichen"
    version = "1.0.0"
    description = "Zählt Zeichen inkl. Leerzeichen je Kapitel (Normseiten-Abschätzung)"

    def load(self, registry: DockRegistry) -> bool:
        def tool(agent, slug: str) -> str:
            p = agent._book(slug)
            rows = []
            for ch in p.outline:
                latest = p.latest_chapter(int(ch["nr"]))
                if latest:
                    chars = len(latest[1])
                    rows.append(f"Kap. {ch['nr']}: {chars} Zeichen ≈ {chars / 1800:.1f} Normseiten")
            return "\n".join(rows) or "Noch kein Text."

        registry.add_tool(
            "char_count",
            "Zeichen und Normseiten je Kapitel.",
            {"type": "object", "properties": {"slug": {"type": "string"}},
             "required": ["slug"], "additionalProperties": False},
            tool,
        )
        return True


DOCK = ZeichenDock
```

## Regeln für Werkzeuge

- Der Name muss ein Python-Bezeichner sein und darf kein eingebautes Werkzeug überdecken
  (z. B. `list_books`). Der Agent bricht in dem Fall mit einer klaren Fehlermeldung ab.
- `confirm=True` für alles, was Geld kostet (LLM-Aufrufe) oder schwer rückgängig zu machen ist.
- SSOT-Dateien (Bible, Outline, Voice) nur über `project.commit_ssot(…)` ändern, nie direkt.
- Werkzeuge geben einen String zurück. Eine Exception wird dem Modell als Werkzeugfehler
  gemeldet, der Agent läuft weiter.
- Dateizugriff nur über `agent.workspace` bzw. `agent._safe(pfad)`, das verhindert Pfad-Ausbrüche.
