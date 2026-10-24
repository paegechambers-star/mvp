"""
Einstiegspunkt der Windows-App (PyInstaller).

Ohne Argumente: Desktop-App starten. Mit Argumenten: CLI (z. B. ``Scriptor.exe docks``).
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
    if len(sys.argv) > 1:
        from scriptor.cli import main as cli_main

        cli_main()
        return
    from scriptor.app.launcher import launch
    from scriptor.runtime import Runtime

    launch(Runtime.create())


if __name__ == "__main__":
    main()
