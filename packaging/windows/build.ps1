# Baut dist\FraPP\FraPP.exe (+ ZIP): FraPP + SCRIPTOR + G.O.D.A.I. Aufruf aus dem Repo-Root:
#   PowerShell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\build.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root

# Python wählen: $env:SCRIPTOR_PYTHON > python im PATH > py-Launcher
$base = if ($env:SCRIPTOR_PYTHON) { $env:SCRIPTOR_PYTHON } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "py" }
if (!(Test-Path .\.venv-build)) { & $base -m venv .venv-build }
$py = ".\.venv-build\Scripts\python.exe"
& $py -m pip install --disable-pip-version-check -q --upgrade pip
& $py -m pip install --disable-pip-version-check -q -e ".[windows]" pyinstaller

& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller packaging\windows\frapp.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen" }

# Rauchtest: CLI-Modus der EXE muss laufen
$smoke = Start-Process -FilePath .\dist\FraPP\FraPP.exe -ArgumentList "scriptor","genres" -Wait -PassThru -NoNewWindow
if ($smoke.ExitCode -ne 0) { throw "Rauchtest fehlgeschlagen (Exit $($smoke.ExitCode))" }

Compress-Archive -Path dist\FraPP -DestinationPath dist\FraPP-windows.zip -Force
Write-Host "Fertig: dist\FraPP\FraPP.exe und dist\FraPP-windows.zip"
