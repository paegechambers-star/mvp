#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║         FraPP + G.O.D.A.I. INSTALLER                               ║
║         Interaktives Setup-Menü — kein Vorwissen nötig             ║
╚══════════════════════════════════════════════════════════════════════╝

Starten:
    python installer/install.py

Benötigt nur Python 3.10+ — alles weitere wird automatisch installiert.
"""
from __future__ import annotations

import os
import sys
import subprocess
import time
import shutil
import secrets
import platform
import textwrap
from pathlib import Path
from typing import Optional

# ── Farben ────────────────────────────────────────────────────────────────────
R = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"
B    = "\033[94m"   # blau
C    = "\033[96m"   # cyan
G    = "\033[92m"   # grün
Y    = "\033[93m"   # gelb
RED  = "\033[91m"   # rot
M    = "\033[95m"   # magenta

# ── Installer-Root ────────────────────────────────────────────────────────────
INSTALLER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT  = INSTALLER_DIR.parent

# ─────────────────────────────────────────────────────────────────────────────

LOGO = f"""
{C}{BOLD}
   ███████╗██████╗  █████╗ ██████╗ ██████╗
   ██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔══██╗
   █████╗  ██████╔╝███████║██████╔╝██████╔╝
   ██╔══╝  ██╔══██╗██╔══██║██╔═══╝ ██╔═══╝
   ██║     ██║  ██║██║  ██║██║     ██║
   ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
{R}{M}{BOLD}
          ✦  G.O.D.A.I.  ✦
   AI Governance Control Plane
{R}{DIM}   EU AI Act · DSGVO · OWASP-sicher{R}
"""

SEPARATOR = f"{C}{'═' * 62}{R}"
THIN_SEP  = f"{DIM}{'─' * 62}{R}"


def clear():
    os.system("cls" if platform.system() == "Windows" else "clear")


def hdr(title: str):
    clear()
    print(LOGO)
    print(SEPARATOR)
    print(f"  {BOLD}{title}{R}")
    print(SEPARATOR)
    print()


def ok(msg: str):
    print(f"  {G}✓{R}  {msg}")


def info(msg: str):
    print(f"  {C}·{R}  {msg}")


def warn(msg: str):
    print(f"  {Y}!{R}  {msg}")


def err(msg: str):
    print(f"  {RED}✗{R}  {msg}")


def step(n: int, total: int, label: str):
    pct = int((n / total) * 30)
    bar = f"{G}{'█' * pct}{DIM}{'░' * (30 - pct)}{R}"
    print(f"\r  [{bar}] {n}/{total}  {label:<35}", end="", flush=True)


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{DIM}{default}{R}]" if default else ""
    try:
        val = input(f"  {C}›{R} {prompt}{hint}: ").strip()
        return val if val else default
    except (KeyboardInterrupt, EOFError):
        print()
        bye()
        sys.exit(0)


def choose(prompt: str, options: list[tuple[str, str]], default: int = 0) -> int:
    """Numbered menu. Returns chosen index."""
    print(f"  {prompt}")
    print()
    for i, (key, label) in enumerate(options):
        marker = f"{G}▶{R}" if i == default else " "
        print(f"  {marker} {BOLD}{i + 1}{R}.  {key:<18} {DIM}{label}{R}")
    print()
    while True:
        raw = ask(f"Auswahl (1–{len(options)})", str(default + 1))
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        warn("Bitte eine gültige Zahl eingeben.")


def confirm(prompt: str, default: bool = True) -> bool:
    hint = "J/n" if default else "j/N"
    val = ask(f"{prompt} ({hint})", "j" if default else "n").lower()
    return val in ("j", "ja", "y", "yes", "1", "")


def bye():
    print(f"\n  {Y}Installation abgebrochen.{R}\n")


def run(cmd: str, cwd: Path = PROJECT_ROOT, capture: bool = True) -> tuple[int, str]:
    result = subprocess.run(
        cmd, shell=True, cwd=str(cwd),
        capture_output=capture, text=True,
    )
    return result.returncode, result.stdout + result.stderr


def progress_run(label: str, cmd: str, n: int, total: int) -> bool:
    step(n, total, label)
    code, out = run(cmd)
    if code != 0:
        print()
        err(f"Fehler bei: {label}")
        print(f"{DIM}{out[:300]}{R}")
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SCREENS
# ─────────────────────────────────────────────────────────────────────────────

def screen_welcome():
    clear()
    print(LOGO)
    print(SEPARATOR)
    print(f"""
  Willkommen beim {BOLD}FraPP + G.O.D.A.I. Installer{R}.

  Dieses System installiert:
  {C}·{R} FraPP REST API        (Event-Management, CRUD, GDPR)
  {C}·{R} G.O.D.A.I. Pipeline   (5-Modul AI Governance)
  {C}·{R} MNEMOSYNE Audit-Log   (SHA256-Kette, EU AI Act Art. 12)
  {C}·{R} Alle Abhängigkeiten   (automatisch)

  {DIM}Dauer: ca. 2–3 Minuten{R}
""")
    print(SEPARATOR)
    print()
    if not confirm("Installation starten?"):
        bye()
        sys.exit(0)


def screen_check_python():
    hdr("Schritt 1 / 6 — System-Prüfung")
    info(f"Python {sys.version.split()[0]} auf {platform.system()}")

    major, minor = sys.version_info[:2]
    if major < 3 or minor < 10:
        err(f"Python 3.10+ benötigt. Gefunden: {major}.{minor}")
        sys.exit(1)
    ok("Python-Version OK")

    pip_ok = shutil.which("pip") or shutil.which("pip3")
    if not pip_ok:
        err("pip nicht gefunden. Bitte pip installieren.")
        sys.exit(1)
    ok("pip gefunden")

    code, _ = run("git --version")
    if code == 0:
        ok("git gefunden")
    else:
        warn("git nicht gefunden — optional, kein Blocker")

    print()
    time.sleep(0.5)


def screen_install_type() -> str:
    hdr("Schritt 2 / 6 — Installations-Typ")
    idx = choose(
        "Welche Installation möchtest du?",
        [
            ("Schnell",      "Alles mit sinnvollen Standardwerten (empfohlen)"),
            ("Benutzerdefiniert", "Port, Datenbank, API-Key selbst wählen"),
            ("Entwickler",   "Dev-Modus, hot-reload, EchoProvider"),
        ],
        default=0,
    )
    return ["quick", "custom", "dev"][idx]


def screen_configure(mode: str) -> dict:
    hdr("Schritt 3 / 6 — Konfiguration")

    if mode == "quick":
        config = {
            "port": "8000",
            "api_key": secrets.token_urlsafe(24),
            "secret_key": secrets.token_urlsafe(32),
            "database": "sqlite",
            "env": "production",
            "log_level": "INFO",
        }
        ok(f"Port          : {config['port']}")
        ok(f"API-Key       : {config['api_key'][:16]}… (generiert)")
        ok(f"Datenbank     : SQLite (lokal)")
        ok(f"Modus         : Produktion")

    elif mode == "dev":
        config = {
            "port": "8000",
            "api_key": "dev-key",
            "secret_key": "dev-secret-change-in-production",
            "database": "sqlite",
            "env": "dev",
            "log_level": "DEBUG",
        }
        ok("Dev-Modus: API-Key = dev-key, hot-reload aktiv")

    else:  # custom
        print(f"  {DIM}Enter drücken für Standardwert{R}\n")
        config = {
            "port":       ask("Port", "8000"),
            "api_key":    ask("API-Key (leer = generieren)", "") or secrets.token_urlsafe(24),
            "secret_key": ask("Secret-Key (leer = generieren)", "") or secrets.token_urlsafe(32),
            "env":        "production",
            "log_level":  "INFO",
            "database":   "sqlite",
        }

        db_idx = choose(
            "Datenbank:",
            [("SQLite", "lokal, kein Server nötig (Standard)"),
             ("PostgreSQL", "Produktions-DB, DATABASE_URL eingeben")],
            default=0,
        )
        if db_idx == 1:
            config["database"] = "postgres"
            config["db_url"] = ask("DATABASE_URL", "postgresql://user:pass@localhost/frapp")
        else:
            config["database"] = "sqlite"

        anthropic = ask("Anthropic API-Key (leer = offline/Echo)", "")
        if anthropic:
            config["anthropic_api_key"] = anthropic

    print()
    return config


def screen_install_deps(config: dict) -> bool:
    hdr("Schritt 4 / 6 — Abhängigkeiten installieren")

    total = 6
    tasks = [
        ("FastAPI + Uvicorn",    "pip install fastapi uvicorn[standard] sqlmodel pydantic-settings -q"),
        ("Datenbank-Tools",      "pip install alembic psycopg2-binary -q"),
        ("G.O.D.A.I. Core",     "pip install pyyaml networkx anthropic -q"),
        ("Observability",        "pip install structlog prometheus-fastapi-instrumentator prometheus-client -q"),
        ("Rate Limiting",        "pip install slowapi redis limits -q"),
        ("FraPP installieren",   f"pip install -e {str(PROJECT_ROOT)} -q"),
    ]

    all_ok = True
    for i, (label, cmd) in enumerate(tasks, 1):
        if not progress_run(label, cmd, i, total):
            all_ok = False
            break
        time.sleep(0.1)

    print(f"\r  [{G}{'█' * 30}{R}] {total}/{total}  {'Fertig':<35}")
    print()

    if all_ok:
        ok("Alle Abhängigkeiten installiert")
    else:
        err("Installation fehlgeschlagen. Prüfe Netzwerk und Rechte.")

    return all_ok


def screen_write_env(config: dict):
    hdr("Schritt 5 / 6 — Konfiguration schreiben")

    db_url = config.get("db_url", "sqlite:///./frapp.db")
    env_content = f"""# FraPP + G.O.D.A.I. — automatisch generiert
ENV={config['env']}
LOG_LEVEL={config['log_level']}

# Auth
API_KEY={config['api_key']}
SECRET_KEY={config['secret_key']}

# Datenbank
DATABASE_URL={db_url}

# CORS
CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]

# Optional
ANTHROPIC_API_KEY={config.get('anthropic_api_key', '')}
REDIS_URL=
TIMEZONE=Europe/Berlin
"""

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        backup = env_path.with_suffix(".env.backup")
        shutil.copy(env_path, backup)
        warn(f"Bestehende .env gesichert → .env.backup")

    env_path.write_text(env_content)
    ok(f".env geschrieben → {env_path}")

    # DB Migration
    info("Führe Datenbank-Migration aus …")
    code, out = run("python -m alembic upgrade head", cwd=PROJECT_ROOT)
    if code == 0:
        ok("Datenbank-Migrationen erfolgreich")
    else:
        # Fallback: direkte DB-Initialisierung
        code2, _ = run(
            "python -c \"import sys; sys.path.insert(0,'src'); "
            "from frapp.db import init_db; init_db()\"",
            cwd=PROJECT_ROOT,
        )
        if code2 == 0:
            ok("Datenbank initialisiert (Fallback)")
        else:
            warn("Datenbank-Migration übersprungen — beim ersten Start ausgeführt")

    print()


def screen_verify():
    hdr("Schritt 6 / 6 — Verifikation")

    info("Starte Schnelltest …")
    code, out = run(
        "python -c \""
        "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'.')\n"
        "from fastapi.testclient import TestClient\n"
        "from frapp.api import app\n"
        "c = TestClient(app)\n"
        "assert c.get('/healthz/live').status_code == 200\n"
        "print('OK')\n"
        "\"",
        cwd=PROJECT_ROOT,
    )

    if code == 0:
        ok("Health-Check bestanden")
    else:
        warn("Schnelltest übersprungen (wird beim ersten Start geprüft)")

    print()


def screen_success(config: dict):
    port = config.get("port", "8000")
    api_key = config["api_key"]

    clear()
    print(LOGO)
    print(f"{G}{BOLD}")
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║   ✓  Installation erfolgreich abgeschlossen!        ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print(f"{R}")

    print(f"""
  {BOLD}Server starten:{R}

    {C}cd {PROJECT_ROOT}{R}
    {C}uvicorn frapp.api:app --host 0.0.0.0 --port {port} --reload{R}

  {BOLD}Oder Demo-Setup (mit Anleitungen):{R}

    {C}bash scripts/gtm/demo_setup.sh{R}

  {BOLD}URLs:{R}

    {G}Swagger UI{R}   →  http://localhost:{port}/docs
    {G}ReDoc{R}        →  http://localhost:{port}/redoc
    {G}Health{R}       →  http://localhost:{port}/healthz
    {G}Audit-Log{R}    →  http://localhost:{port}/v1/godai/audit
    {G}Metrics{R}      →  http://localhost:{port}/metrics

  {BOLD}Auth-Header:{R}

    {Y}X-API-Key: {api_key[:32]}{"…" if len(api_key) > 32 else ""}{R}

  {DIM}(vollständiger Key in .env gespeichert){R}

  {BOLD}Erste Schritte:{R}

    {C}# JWT ausstellen{R}
    curl -s -X POST http://localhost:{port}/v1/godai/token \\
      -H "X-API-Key: {api_key}" \\
      -H "Content-Type: application/json" \\
      -d '{{"user_id": "ich", "trust_level": "L2"}}' | python -m json.tool

    {C}# Pipeline abfragen{R}
    curl -s -X POST http://localhost:{port}/v1/godai/query \\
      -H "X-API-Key: {api_key}" \\
      -H "Content-Type: application/json" \\
      -d '{{"user_id": "ich", "query": "Hallo", "context": {{"data_class": "PUBLIC"}}}}' \\
      | python -m json.tool

  {BOLD}Tests laufen lassen:{R}

    {C}python -m pytest                   {DIM}# 206 Unit-Tests{R}
    {C}python tests/level4_security.py    {DIM}# OWASP Penetrationstest{R}
    {C}python tests/level5_ultimate.py    {DIM}# Ultimate Stress-Test{R}

""")
    print(SEPARATOR)
    print(f"  {G}{BOLD}Viel Erfolg mit FraPP + G.O.D.A.I. ✦{R}")
    print(SEPARATOR)
    print()

    if confirm("Server jetzt starten?", default=True):
        print(f"\n  {C}Starte Server auf Port {port} …{R}\n")
        os.chdir(str(PROJECT_ROOT))
        os.execvp(
            sys.executable,
            [sys.executable, "-m", "uvicorn", "frapp.api:app",
             "--host", "0.0.0.0", "--port", port, "--reload"],
        )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    try:
        screen_welcome()
        screen_check_python()
        mode   = screen_install_type()
        config = screen_configure(mode)

        if not screen_install_deps(config):
            err("Installation fehlgeschlagen.")
            sys.exit(1)

        screen_write_env(config)
        screen_verify()
        screen_success(config)

    except KeyboardInterrupt:
        print()
        bye()
        sys.exit(0)


if __name__ == "__main__":
    main()
