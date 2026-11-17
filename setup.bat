@echo off
rem FounderOS one-time setup for Windows 11. Safe to run again: it skips what is already done.
rem Creates .venv, installs backend and frontend dependencies, starts Qdrant, pulls the Ollama models over HTTP
rem (native app or Docker container at OLLAMA_BASE_URL) and downloads the voice models.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo == FounderOS setup ==

rem --- Python: prefer 3.12, then 3.11, then whatever "python" is ------------------
rem 3.13+ works today, but later ML/voice packages may not ship wheels for it yet.
set "PY="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 --version >nul 2>nul && set "PY=py -3.12"
  if not defined PY py -3.11 --version >nul 2>nul && set "PY=py -3.11"
)
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.12 from https://www.python.org/downloads/ and re-run.
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.11 or newer is required; found an older one via "%PY%". Install Python 3.12.
  exit /b 1
)
for /f "delims=" %%V in ('%PY% --version') do echo Using %%V via "%PY%"

rem --- Node 20+ ----------------------------------------------------------------
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js 22 LTS ^(or 20.19+^) not found. Install it from https://nodejs.org/ and re-run.
  exit /b 1
)
node -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit(a>20||(a===20&&b>=19)?0:1)"
if errorlevel 1 (
  for /f "delims=" %%V in ('node --version') do echo [ERROR] Node.js %%V is too old: Vite needs 20.19+ ^(22 LTS recommended^). https://nodejs.org/
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm not found. Reinstall Node.js 22 LTS from https://nodejs.org/ ^(npm comes with it^).
  exit /b 1
)

rem --- .env ----------------------------------------------------------------------
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo Created .env from .env.example
)

rem --- Backend -------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment in .venv ...
  %PY% -m venv .venv || exit /b 1
)
echo Installing backend dependencies ...
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info < (3, 13) else 1)"
if errorlevel 1 (
  echo [WARN] .venv uses Python 3.13 or newer. Later ML/voice packages may lack wheels for it.
  echo        Recommended: install Python 3.12, delete the .venv folder and run setup.bat again.
)
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul || exit /b 1
".venv\Scripts\python.exe" -m pip install -e "backend[dev,gpu,voice]" || exit /b 1

rem --- Frontend ------------------------------------------------------------------
echo Installing frontend dependencies ...
pushd frontend
call npm ci || (popd & exit /b 1)
popd

rem --- Demo data -----------------------------------------------------------------
if not exist "sample_data\pnl.csv" (
  ".venv\Scripts\python.exe" scripts\generate_demo_data.py || exit /b 1
)

rem --- Qdrant (Docker, optional) ------------------------------------------------
where docker >nul 2>nul
if errorlevel 1 (
  echo [WARN] Docker not found. Search runs in memory until Docker Desktop is installed ^(optional^).
  goto :models
)
docker info >nul 2>nul
if errorlevel 1 (
  echo [WARN] Docker Desktop is installed but not running. Start it, then run setup.bat again for Qdrant ^(optional^).
  goto :models
)
docker compose up -d qdrant
if errorlevel 1 echo [WARN] Could not start the Qdrant container. Search runs in memory until it starts.

:models
rem --- Models (once): qwen3:8b and nomic-embed-text through Ollama's HTTP API, Whisper small.en/base.en and Kokoro --
rem A failure never stops setup: FounderOS starts without them and says what is missing.
echo Downloading models ^(qwen3:8b about 5.2 GB, nomic-embed-text 0.3 GB, voice about 0.9 GB; skipped when present^) ...
".venv\Scripts\python.exe" scripts\download_models.py
if errorlevel 1 (
  echo [WARN] Some models are missing. Fix what is named above, then run:
  echo        .venv\Scripts\python.exe scripts\download_models.py
)

echo.
".venv\Scripts\python.exe" scripts\preflight.py
echo.
echo Setup complete. Start FounderOS with run.bat
endlocal
exit /b 0
