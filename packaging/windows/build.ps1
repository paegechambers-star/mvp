# Baut dist\Scriptor\Scriptor.exe (+ ZIP). Aufruf aus dem Repo-Root:
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

& $py -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller packaging\windows\scriptor.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen" }

# Rauchtest: CLI-Modus der EXE muss laufen
$smoke = Start-Process -FilePath .\dist\Scriptor\Scriptor.exe -ArgumentList "genres" -Wait -PassThru -NoNewWindow
if ($smoke.ExitCode -ne 0) { throw "Rauchtest fehlgeschlagen (Exit $($smoke.ExitCode))" }

Compress-Archive -Path dist\Scriptor -DestinationPath dist\Scriptor-windows.zip -Force
Write-Host "Fertig: dist\Scriptor\Scriptor.exe und dist\Scriptor-windows.zip"
