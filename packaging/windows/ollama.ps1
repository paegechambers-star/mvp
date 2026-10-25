# Richtet Ollama als lokalen KI-Anbieter für FraPP ein (SCRIPTOR + G.O.D.A.I.), ohne Adminrechte.
#   PowerShell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\ollama.ps1 [-Model qwen3:8b]
# Schritte: Ollama installieren (winget, sonst offizieller Installer) -> Server starten ->
# Modell herunterladen -> FraPP auf "ollama" umstellen. Mehrfach ausführbar.
Param(
  # Empfehlung: qwen3:8b (ca. 5 GB, 16 GB RAM). Schwächerer PC: qwen3:4b
  [string]$Model = "qwen3:8b",
  [string]$Url = "http://localhost:11434",
  # Nur installieren/Modell laden, FraPP-Einstellung nicht ändern
  [switch]$NoSwitch
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Find-Ollama {
  $cmd = Get-Command ollama -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  foreach ($p in @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe")) {
    if (Test-Path $p) { return $p }
  }
  return $null
}

function Test-Server {
  try { Invoke-RestMethod -UseBasicParsing "$Url/api/version" -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}

# 1) Installieren
$ollama = Find-Ollama
if (-not $ollama) {
  Write-Host "Ollama fehlt - wird installiert ..."
  $viaWinget = $false
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
    $viaWinget = ($LASTEXITCODE -eq 0)
  }
  $ollama = Find-Ollama
  if (-not $ollama) {
    Write-Host "Lade offiziellen Installer von ollama.com ..."
    $setup = Join-Path $env:TEMP "OllamaSetup.exe"
    Invoke-WebRequest -UseBasicParsing "https://ollama.com/download/OllamaSetup.exe" -OutFile $setup
    Start-Process $setup -Wait
    $ollama = Find-Ollama
  }
  if (-not $ollama) { throw "Ollama-Installation nicht gefunden. Bitte von https://ollama.com/download installieren und erneut starten." }
}
Write-Host "Ollama: $ollama"

# 2) Server starten (die Ollama-App startet ihn normalerweise automatisch)
if (-not (Test-Server)) {
  Write-Host "Starte Ollama-Server ..."
  Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
  $ok = $false
  for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Seconds 1; if (Test-Server) { $ok = $true; break } }
  if (-not $ok) { throw "Ollama-Server antwortet nicht unter $Url." }
}
Write-Host "Ollama-Server laeuft: $Url"

# 3) Modell herunterladen (bei vorhandenem Modell nur Abgleich)
Write-Host "Lade Modell $Model (beim ersten Mal mehrere GB) ..."
& $ollama pull $Model
if ($LASTEXITCODE -ne 0) { throw "ollama pull $Model fehlgeschlagen." }

# 4) FraPP umstellen
if (-not $NoSwitch) {
  $frapp = Join-Path $env:LOCALAPPDATA "FraPP\venv\Scripts\frapp.exe"
  if (-not (Test-Path $frapp)) { throw "FraPP ist nicht installiert ($frapp). Erst install.ps1 ausfuehren." }
  & $frapp scriptor config --provider ollama --ollama-model $Model --ollama-url $Url
  if ($LASTEXITCODE -ne 0) { throw "FraPP-Einstellung konnte nicht gesetzt werden." }
}
Write-Host ""
Write-Host "Fertig. FraPP nutzt jetzt lokal $Model (Scriptor + G.O.D.A.I.). Umschalten: Scriptor -> Einstellungen -> KI-Anbieter."
