@echo off
rem Start FounderOS on Windows: Qdrant (if Docker is running), backend :8000 and frontend :3000, then the browser.
rem From a fresh clone it runs setup.bat first. Close the two server windows to stop FounderOS.
setlocal EnableExtensions
cd /d "%~dp0"

echo == FounderOS ==

rem --- First run: set up ------------------------------------------------------------------------------------------
set "NEED_SETUP="
if not exist ".venv\Scripts\python.exe" set "NEED_SETUP=1"
if not exist "frontend\node_modules" set "NEED_SETUP=1"
if defined NEED_SETUP (
  echo First run: FounderOS is not set up yet, so setup.bat runs now ^(10 to 30 minutes, once^).
  call "%~dp0setup.bat"
  if errorlevel 1 (
    echo [ERROR] Setup did not finish. Fix the error above, then run run.bat again.
    exit /b 1
  )
)
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info < (3, 13) else 1)"
if errorlevel 1 (
  echo [WARN] .venv uses Python 3.13 or newer; Python 3.12 is recommended. See README.
)

rem --- Ports: an old FounderOS still running would answer with old code --------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check_ports.ps1" 8000 3000
if errorlevel 1 exit /b 1

rem --- Qdrant (Docker, optional) ----------------------------------------------------------------------------------
rem Founder Y3: a Qdrant that already answers on port 6333 (another clone's container) is used as it is.
curl.exe -s -f -m 3 http://localhost:6333/readyz >nul 2>nul
if not errorlevel 1 (
  echo [OK] Qdrant already running on port 6333.
  goto :preflight
)
where docker >nul 2>nul
if errorlevel 1 (
  echo [WARN] Docker is not installed: search runs in memory ^(fine for the demo^). Docker Desktop adds Qdrant.
  goto :preflight
)
docker info >nul 2>nul
if errorlevel 1 (
  echo [WARN] Docker Desktop is not running: search runs in memory. Start Docker Desktop to use Qdrant.
  goto :preflight
)
docker compose up -d qdrant >nul 2>nul
if errorlevel 1 echo [WARN] The Qdrant container did not start ^(docker compose up -d qdrant^). Search runs in memory.

:preflight
rem --- M7a: the server secret for saved API keys (made once in .env when missing, never printed) ----------------------
rem Founder F1: at :preflight, so every path (Qdrant running, started, or no Docker) runs it once on every start.
".venv\Scripts\python.exe" scripts\ensure_secret.py
rem --- What is there: Ollama at OLLAMA_BASE_URL, Qdrant, voice models (never stops the start) -----------------------
".venv\Scripts\python.exe" scripts\preflight.py

rem --- Start ------------------------------------------------------------------------------------------------------
rem Founder F8c: PowerShell's $env: variables set before .\run.bat reach the backend window (start inherits them, and
rem an environment variable beats .env). Shown here so a test run can see them; the backend logs the limit it uses.
if defined CLOUD_SLOW_AFTER_S echo Slow-agent offer from this window: CLOUD_SLOW_AFTER_S=%CLOUD_SLOW_AFTER_S% CLOUD_SLOW_MIN_S=%CLOUD_SLOW_MIN_S%
start "FounderOS backend" /d "%~dp0backend" cmd /k ""%~dp0.venv\Scripts\python.exe" -m uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000"
start "FounderOS frontend" /d "%~dp0frontend" cmd /k "npm run dev"

echo Waiting for the backend ^(up to 90 s^) ...
powershell -NoProfile -Command "for ($i = 0; $i -lt 90; $i++) { try { Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1"
if errorlevel 1 (
  echo [WARN] The backend did not answer within 90 s. Look at the "FounderOS backend" window for the error.
) else (
  echo Backend is up: http://127.0.0.1:8000/api/health
)
start "" "http://127.0.0.1:3000"
echo FounderOS is running at http://127.0.0.1:3000 . Close the two server windows to stop it.
endlocal
exit /b 0
