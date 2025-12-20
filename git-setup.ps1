Param(
  [Parameter(Mandatory=$true)][string]$Remote
)
$ErrorActionPreference="Stop"
if (-not (Test-Path ".git")) { git init }
git branch -M main
git remote remove origin 2>$null | Out-Null
git remote add origin $Remote
git add -A
git commit -m "init: repo template" 2>$null | Out-Null
git push -u origin main
Write-Host "Fertig. Remote gesetzt: $Remote"
