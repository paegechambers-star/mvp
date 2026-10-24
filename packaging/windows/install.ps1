# Installiert SCRIPTOR für den aktuellen Windows-Benutzer (ohne Adminrechte).
#   PowerShell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\install.ps1
# Legt an: %LOCALAPPDATA%\Scriptor\venv, Desktop- und Startmenü-Verknüpfung "SCRIPTOR".
Param([switch]$NoShortcut)
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."

# 1) Python prüfen (3.10+)
$pyver = & py -3 -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
if (-not $pyver) { throw "Python 3.10+ nicht gefunden. Installieren: https://www.python.org/downloads/windows/ (Haken bei 'py launcher')." }
if ([version]$pyver -lt [version]"3.10") { throw "Python $pyver ist zu alt, benötigt 3.10+." }
Write-Host "Python $pyver gefunden."

# 2) venv + Pakete
$base = Join-Path $env:LOCALAPPDATA "Scriptor"
$venv = Join-Path $base "venv"
if (!(Test-Path $venv)) { py -3 -m venv $venv }
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --disable-pip-version-check -q --upgrade pip
& $py -m pip install --disable-pip-version-check -q -e "$root[windows]"
if ($LASTEXITCODE -ne 0) { throw "pip install fehlgeschlagen" }

# 3) Rauchtest
& $py -m scriptor genres | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Rauchtest fehlgeschlagen" }

# 4) Verknüpfungen (pythonw = ohne Konsolenfenster)
if (-not $NoShortcut) {
  $pyw = Join-Path $venv "Scripts\pythonw.exe"
  $shell = New-Object -ComObject WScript.Shell
  $targets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "SCRIPTOR.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "SCRIPTOR.lnk")
  )
  foreach ($lnk in $targets) {
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = $pyw
    $s.Arguments = "-m scriptor app"
    $s.WorkingDirectory = $base
    $s.Description = "SCRIPTOR - KI-Ghostwriter"
    $s.Save()
  }
  Write-Host "Verknüpfungen angelegt (Desktop + Startmenü)."
}

# 5) CLI im Benutzer-PATH verfügbar machen (optional, nur Hinweis)
Write-Host ""
Write-Host "Fertig. Start: Desktop-Verknüpfung 'SCRIPTOR'."
Write-Host "CLI: $venv\Scripts\scriptor.exe --help"
Write-Host "API-Key: in der App unter Einstellungen, oder: $venv\Scripts\scriptor.exe config --set-api-key sk-ant-..."
