# Installiert FraPP (mit SCRIPTOR-Dock, G.O.D.A.I. und ContextOS) für den aktuellen
# Windows-Benutzer, ohne Adminrechte.
#   PowerShell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\install.ps1
# Legt an: %LOCALAPPDATA%\FraPP\venv, Desktop- und Startmenü-Verknüpfung "FraPP".
# Eine ältere Einzel-Installation von SCRIPTOR wird entfernt (Bücher/Einstellungen bleiben).
Param(
  [switch]$NoShortcut,
  # Optional: Pfad zu einer bestimmten python.exe (sonst automatische Wahl 3.12 > 3.13 > 3.11 > 3.10)
  [string]$Python = ""
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."

# Unterstützte Versionen: für diese gibt es fertige Pakete (Wheels) aller Abhängigkeiten.
# Neuere Versionen (z. B. 3.14/3.15) würden einen C++-Compiler verlangen.
$supported = @("3.12", "3.13", "3.11", "3.10")

function Get-PyVersion([string[]]$cmd) {
  try {
    $exe = $cmd[0]
    $rest = @()
    if ($cmd.Length -gt 1) { $rest = $cmd[1..($cmd.Length - 1)] }
    $out = & $exe @rest -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) { return ($out | Select-Object -First 1).Trim() }
  } catch { }
  return $null
}

# 1) Passende Python-Version finden
$pycmd = $null
$pyver = $null
if ($Python) {
  $pyver = Get-PyVersion @($Python)
  if (-not $pyver) { throw "Python unter '$Python' nicht ausführbar." }
  $pycmd = @($Python)
} else {
  foreach ($v in $supported) {
    $found = Get-PyVersion @("py", "-$v")
    if ($found -eq $v) { $pycmd = @("py", "-$v"); $pyver = $v; break }
  }
}
if (-not $pycmd) {
  $installed = "keine (py-Launcher fehlt)"
  try { $installed = (& py --list 2>$null) -join "; " } catch { }
  throw ("Keine passende Python-Version gefunden (benötigt: 3.10 bis 3.13, empfohlen 3.12). " +
    "Installiert: $installed`n" +
    "Lösung: 'py install 3.12' ausführen (neuer Python-Installationsmanager) " +
    "oder Python 3.12 von https://www.python.org/downloads/windows/ installieren, dann dieses Skript erneut starten.")
}
if ($supported -notcontains $pyver) {
  Write-Warning "Python $pyver ist nicht offiziell unterstützt (getestet: 3.12). Installation wird versucht."
}
Write-Host "Verwende Python $pyver."

# 2) Alte SCRIPTOR-Einzelinstallation aufräumen (Code-Umgebung + Verknüpfungen; Daten bleiben)
$oldVenv = Join-Path $env:LOCALAPPDATA "Scriptor\venv"
if (Test-Path $oldVenv) { Write-Host "Entferne alte SCRIPTOR-Umgebung ..."; Remove-Item -Recurse -Force $oldVenv }
foreach ($folder in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
  $oldLnk = Join-Path $folder "SCRIPTOR.lnk"
  if (Test-Path $oldLnk) { Remove-Item -Force $oldLnk }
}

# 3) venv (bei falscher Python-Version neu anlegen) + Pakete
$base = Join-Path $env:LOCALAPPDATA "FraPP"
$venv = Join-Path $base "venv"
$py = Join-Path $venv "Scripts\python.exe"
if (Test-Path $venv) {
  $venvver = Get-PyVersion @($py)
  if ($venvver -ne $pyver) {
    Write-Host "Vorhandene Umgebung nutzt Python $venvver - wird mit $pyver neu angelegt."
    Remove-Item -Recurse -Force $venv
  }
}
if (!(Test-Path $venv)) {
  $exe = $pycmd[0]
  $rest = @()
  if ($pycmd.Length -gt 1) { $rest = $pycmd[1..($pycmd.Length - 1)] }
  & $exe @rest -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "venv konnte nicht angelegt werden" }
}
& $py -m pip install --disable-pip-version-check -q --upgrade pip
# --prefer-binary: fertige Pakete bevorzugen (mit 3.10-3.13 ist kein C++-Compiler nötig)
& $py -m pip install --disable-pip-version-check -q --prefer-binary -e "$root[windows]"
if ($LASTEXITCODE -ne 0) {
  throw ("pip install fehlgeschlagen. Häufigste Ursache: Python-Version ohne fertige Pakete. " +
    "Mit Python 3.12 erneut versuchen: 'py install 3.12' bzw. python.org.")
}

# 4) Rauchtest: alle Schichten importierbar, SCRIPTOR als FraPP-Dock erreichbar
& $py -c "import frapp.api, godai.pipeline, contextos, scriptor.governance" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Rauchtest fehlgeschlagen: FraPP/G.O.D.A.I./ContextOS/SCRIPTOR nicht importierbar" }
& $py -m frapp.cli scriptor genres | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Rauchtest fehlgeschlagen: 'frapp scriptor genres'" }

# 5) Verknüpfungen (pythonw = ohne Konsolenfenster)
if (-not $NoShortcut) {
  $pyw = Join-Path $venv "Scripts\pythonw.exe"
  $shell = New-Object -ComObject WScript.Shell
  $targets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "FraPP.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "FraPP.lnk")
  )
  foreach ($lnk in $targets) {
    $s = $shell.CreateShortcut($lnk)
    $s.TargetPath = $pyw
    $s.Arguments = "-m frapp.cli app"
    $s.WorkingDirectory = $base
    $s.Description = "FraPP - Tagesplan, Kalender, SCRIPTOR, G.O.D.A.I., ContextOS"
    $s.Save()
  }
  Write-Host "Verknüpfungen angelegt (Desktop + Startmenü)."
}

Write-Host ""
Write-Host "Fertig. Start: Desktop-Verknüpfung 'FraPP' (Tabs: Tagesplan, Kalender, Scriptor, G.O.D.A.I., ContextOS)."
Write-Host "Daten: $env:APPDATA\FraPP (Termine, Aufgaben, ContextOS)  |  Bücher: Dokumente\Scriptor"
Write-Host "CLI:  $venv\Scripts\frapp.exe --help   |   $venv\Scripts\frapp.exe scriptor --help"
Write-Host "API-Key: in der App unter Einstellungen, oder: $venv\Scripts\frapp.exe scriptor config --set-api-key sk-ant-..."
