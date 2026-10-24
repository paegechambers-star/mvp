@echo off
rem Startet SCRIPTOR aus dem installierten venv (oder aus dem Repo, falls nicht installiert).
setlocal
set PYTHONUTF8=1
set VENV=%LOCALAPPDATA%\Scriptor\venv
if exist "%VENV%\Scripts\pythonw.exe" (
  start "" "%VENV%\Scripts\pythonw.exe" -m scriptor app %*
) else (
  py -3 -m scriptor app %*
)
