import subprocess
import sys


def test_cli_version():
    p = subprocess.run(
        [sys.executable, "-m", "frapp.cli", "version"], capture_output=True, text=True
    )
    assert p.returncode == 0
    assert p.stdout.strip()
