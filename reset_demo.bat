@echo off
rem Reset FounderOS to the clean Northwind demo (close FounderOS first). Your old vault and data are moved to
rem data\backups\, never deleted. Options: --yes (no question), --settings (also reset Settings), --workspace ID.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run setup.bat first.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\reset_demo.py %*
exit /b %errorlevel%
