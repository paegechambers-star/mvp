# FRAPP Repo Template

Ein minimaler Python-Repo-Start mit Qualitäts-Gate (Ruff, Black, Mypy, Bandit, pip-audit) und SBOM-Erzeugung.

## Quickstart

```powershell
# optional: venv
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Quality-Gate
PowerShell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lint-typecheck.ps1
```

## Ordnerstruktur

- `src/` – Python-Paket (`frapp`) mit Beispieldateien
- `tests/` – einfacher Test
- `scripts/lint-typecheck.ps1` – führt Ruff, Black, Mypy, Bandit, pip-audit und optional SBOM aus
- `.github/workflows/ci.yml` – GitHub Actions Pipeline
- `.pre-commit-config.yaml` – lokale Qualitäts-Hooks (optional)

## Hinweise

- `pip-audit` wird (wenn vorhanden) gegen `requirements.txt` ausgeführt. Die Vorlage enthält eine leere `requirements.txt`, damit der Schritt stabil läuft.
- Für die SBOM wird `cyclonedx-bom` verwendet (CLI). Falls nicht im PATH, zeigt das Skript nur einen Hinweis.
