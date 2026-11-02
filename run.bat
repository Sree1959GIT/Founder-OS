@echo off
rem Start FounderOS on Windows: Qdrant (if Docker is available), backend :8000 and frontend :3000.
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found. Run setup.bat first.
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo [ERROR] Frontend dependencies missing. Run setup.bat first.
  exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 (
  echo [WARN] Docker not found; running without Qdrant ^(BM25-only search^).
) else (
  docker compose up -d qdrant >nul 2>nul || echo [WARN] Qdrant did not start. Is Docker Desktop running?
)

start "FounderOS backend" /d "%~dp0backend" cmd /k ""%~dp0.venv\Scripts\python.exe" -m uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000"
start "FounderOS frontend" /d "%~dp0frontend" cmd /k "npm run dev"

rem Give the dev servers a few seconds, then open the browser.
timeout /t 6 /nobreak >nul
start "" "http://127.0.0.1:3000"
echo FounderOS is starting. Close the two server windows to stop it.
endlocal
