@echo off
rem Startet FraPP (mit SCRIPTOR + G.O.D.A.I.) aus dem installierten venv oder aus dem Repo.
setlocal
set PYTHONUTF8=1
set VENV=%LOCALAPPDATA%\FraPP\venv
if exist "%VENV%\Scripts\pythonw.exe" (
  start "" "%VENV%\Scripts\pythonw.exe" -m frapp.cli app %*
) else (
  py -3.12 -m frapp.cli app %*
)
