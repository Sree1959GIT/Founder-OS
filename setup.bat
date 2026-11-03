@echo off
rem FounderOS one-time setup for Windows 11 (draft; finalised in M6).
rem Creates .venv, installs backend and frontend dependencies, starts Qdrant and pulls Ollama models.
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
".venv\Scripts\python.exe" -m pip install -e "backend[dev,gpu]" || exit /b 1

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
  echo [WARN] Docker not found. Search will run in BM25-only mode until Docker Desktop is installed.
) else (
  docker compose up -d qdrant || echo [WARN] Could not start Qdrant. Is Docker Desktop running?
)

rem --- Ollama models (optional) -------------------------------------------------
set "OLLAMA_CHAT_MODEL=qwen2.5:7b-instruct-q4_K_M"
set "OLLAMA_EMBED_MODEL=nomic-embed-text"
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
  if /i "%%A"=="OLLAMA_CHAT_MODEL" if not "%%B"=="" set "OLLAMA_CHAT_MODEL=%%B"
  if /i "%%A"=="OLLAMA_EMBED_MODEL" if not "%%B"=="" set "OLLAMA_EMBED_MODEL=%%B"
)
where ollama >nul 2>nul
if errorlevel 1 (
  echo [WARN] Ollama not found. Install it from https://ollama.com/download, then run:
  echo        ollama pull !OLLAMA_CHAT_MODEL!  and  ollama pull !OLLAMA_EMBED_MODEL!
) else (
  ollama pull "!OLLAMA_CHAT_MODEL!" || echo [WARN] Could not pull !OLLAMA_CHAT_MODEL!
  ollama pull "!OLLAMA_EMBED_MODEL!" || echo [WARN] Could not pull !OLLAMA_EMBED_MODEL!
)

echo.
echo Setup complete. Start FounderOS with run.bat
endlocal
