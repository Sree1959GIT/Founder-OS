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
rem Ollama is an external service at OLLAMA_BASE_URL: the native app or a Docker container (e.g. "ollama" shared
rem with an n8n stack). It is detected over HTTP, so it works without the ollama command on PATH.
set "OLLAMA_BASE_URL=http://localhost:11434"
set "OLLAMA_CHAT_MODEL=qwen3:8b"
set "OLLAMA_EMBED_MODEL=nomic-embed-text"
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
  if /i "%%A"=="OLLAMA_BASE_URL" if not "%%B"=="" set "OLLAMA_BASE_URL=%%B"
  if /i "%%A"=="OLLAMA_CHAT_MODEL" if not "%%B"=="" set "OLLAMA_CHAT_MODEL=%%B"
  if /i "%%A"=="OLLAMA_EMBED_MODEL" if not "%%B"=="" set "OLLAMA_EMBED_MODEL=%%B"
)
set "OLLAMA_VERSION="
for /f "delims=" %%V in ('powershell -NoProfile -Command "try { (Invoke-RestMethod -Uri '!OLLAMA_BASE_URL!/api/version' -TimeoutSec 5).version } catch { }" 2^>nul') do set "OLLAMA_VERSION=%%V"
if not defined OLLAMA_VERSION (
  echo [WARN] Ollama is not answering at !OLLAMA_BASE_URL!/api/version.
  echo        Start the Ollama app or its Docker container ^(or set OLLAMA_BASE_URL in .env^), then pull:
  echo        !OLLAMA_CHAT_MODEL! and !OLLAMA_EMBED_MODEL!  ^(Docker: docker exec ollama ollama pull ^<model^>^)
) else (
  echo Ollama !OLLAMA_VERSION! is running at !OLLAMA_BASE_URL!
  call :ensure_model "!OLLAMA_CHAT_MODEL!"
  call :ensure_model "!OLLAMA_EMBED_MODEL!"
)

echo.
echo Setup complete. Start FounderOS with run.bat
endlocal
exit /b 0

rem --- :ensure_model <name>: report the model, pull it with the CLI, or print the docker exec command --------
:ensure_model
powershell -NoProfile -Command "try { $n = @((Invoke-RestMethod -Uri '%OLLAMA_BASE_URL%/api/tags' -TimeoutSec 10).models | ForEach-Object { $_.name }); if (($n -contains '%~1') -or ($n -contains '%~1:latest')) { exit 0 } else { exit 1 } } catch { exit 2 }" >nul 2>nul
if not errorlevel 1 (
  echo Ollama model %~1 is pulled
  exit /b 0
)
where ollama >nul 2>nul
if errorlevel 1 (
  echo [WARN] Ollama model %~1 is not pulled and the ollama command is not on PATH ^(Ollama in Docker?^). Run:
  echo        docker exec ollama ollama pull %~1
  exit /b 0
)
set "OLLAMA_HOST=%OLLAMA_BASE_URL%"
ollama pull "%~1" || echo [WARN] Could not pull %~1
exit /b 0
