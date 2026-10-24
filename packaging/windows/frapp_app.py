"""
Einstiegspunkt der Windows-App FraPP (PyInstaller): FraPP + SCRIPTOR + G.O.D.A.I.

Ohne Argumente: Desktop-App starten. Mit Argumenten: FraPP-CLI
(z. B. ``FraPP.exe scriptor genres``, ``FraPP.exe version``).
"""

import os
import sys

# CLI-Modus unter Windows: an die aufrufende Konsole (cmd/PowerShell) anhängen,
# damit Ausgaben der Fenster-EXE sichtbar sind.
if len(sys.argv) > 1 and sys.platform == "win32" and sys.stdout is None:
    import ctypes

    if ctypes.windll.kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
        sys.stdout = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115
        sys.stderr = sys.stdout

# Fensteranwendung (console=False) hat sonst keine Standardausgabe — umlenken,
# damit Logging/print nicht abstürzt.
if sys.stdout is None or sys.stderr is None:
    _null = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    sys.stdout = sys.stdout or _null
    sys.stderr = sys.stderr or _null

os.environ.setdefault("PYTHONUTF8", "1")


def main() -> None:
    from frapp.cli import main as cli_main

    if len(sys.argv) == 1:
        sys.argv.append("app")  # Doppelklick → Desktop-App
    cli_main()


if __name__ == "__main__":
    main()
