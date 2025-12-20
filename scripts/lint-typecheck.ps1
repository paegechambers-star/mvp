Param([switch]$Strict)
$ErrorActionPreference="Stop"

$py = ".\.venv\Scripts\python.exe"; if (!(Test-Path $py)) { $py="python" }

# Tools installieren/aktualisieren (leise)
& $py -m pip install --disable-pip-version-check -q ruff black mypy bandit pip-audit cyclonedx-bom | Out-Null

$fails = @()

function RunPyMod([string]$Title, [string]$Module, [string[]]$ArgList) {
  Write-Host "== $Title =="
  & $py -m $Module @ArgList
  if ($LASTEXITCODE -ne 0) { $script:fails += $Title }
}

# Zielpfade für Lint/Format
$paths = @()
if (Test-Path .\src)   { $paths += "src" }
if (Test-Path .\tests) { $paths += "tests" }
if ($paths.Count -eq 0) { $paths = @(".") }  # Fallback

# Ruff/Black nur checkend (kein Autoformat)
RunPyMod "ruff"  "ruff"  (@("check","--quiet") + $paths)
RunPyMod "black" "black" (@("--check") + $paths)

# mypy
$mypyArgs = @()
if (-not $Strict) { $mypyArgs += "--ignore-missing-imports" }
if (Test-Path .\src)   { $mypyArgs += "src" } else { $mypyArgs += "." }
if (Test-Path .\tests) { $mypyArgs += "tests" }
RunPyMod "mypy" "mypy" $mypyArgs

# Bandit (SAST) nur auf src oder Fallback .
$src = if (Test-Path .\src) { "src" } else { "." }
RunPyMod "bandit" "bandit" @("-q","-r",$src)

# Dependency Audit
$pipAuditArgs = @("--strict")
if (Test-Path ".\requirements.txt") { $pipAuditArgs = @("--strict","-r","requirements.txt") }
RunPyMod "pip-audit" "pip_audit" $pipAuditArgs

# SBOM (best effort) – CLI "cyclonedx-bom", nicht als -m!
try {
  New-Item -ItemType Directory -Force diagnostics | Out-Null
  $venvBin = Split-Path -Parent $py   # .venv\Scripts
  $cdx = Join-Path $venvBin "cyclonedx-bom.exe"
  if (Test-Path $cdx) {
    & $cdx -o "diagnostics\sbom.json"
  } elseif (Get-Command "cyclonedx-bom" -ErrorAction SilentlyContinue) {
    cyclonedx-bom -o "diagnostics\sbom.json"
  } else {
    Write-Warning "cyclonedx-bom CLI nicht gefunden (aber installiert). Öffne neue Shell oder prüfe PATH."
  }
  if (Test-Path "diagnostics\sbom.json") { Write-Host "SBOM geschrieben: diagnostics\sbom.json" }
} catch { Write-Warning "SBOM Erzeugung übersprungen: $_" }

# Report
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$rep = [ordered]@{ ts=(Get-Date).ToString("s"); ok=($fails.Count -eq 0); fails=$fails }
New-Item -ItemType Directory -Force diagnostics | Out-Null
($rep | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 ("diagnostics\quality_{0}.json" -f $ts)
if ($fails.Count -gt 0) { throw ("Quality FAIL: " + ($fails -join ", ")) }
