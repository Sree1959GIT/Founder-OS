#!/usr/bin/env bash
# FounderOS one-time setup for Linux/macOS (draft; finalised in M6). Mirrors setup.bat.
set -euo pipefail
cd "$(dirname "$0")"

echo "== FounderOS setup =="

PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  # Prefer 3.12, then 3.11. 3.13+ works today, but later ML/voice packages may lack wheels for it.
  for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
fi
if [[ -z "$PY" ]] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "[ERROR] Python 3.11+ is required." >&2
  exit 1
fi
command -v node >/dev/null 2>&1 || { echo "[ERROR] Node.js 22 LTS (or 20.19+) is required." >&2; exit 1; }

[[ -f .env ]] || { cp .env.example .env; echo "Created .env from .env.example"; }

echo "Using $("$PY" --version) via $PY"
[[ -x .venv/bin/python ]] || "$PY" -m venv .venv
if ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info < (3, 13) else 1)'; then
  echo "[WARN] .venv uses Python 3.13 or newer. Later ML/voice packages may lack wheels for it." >&2
  echo "       Recommended: install Python 3.12, delete .venv and run ./setup.sh again." >&2
fi
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -e "backend[dev]"

(cd frontend && npm ci)

[[ -f sample_data/pnl.csv ]] || .venv/bin/python scripts/generate_demo_data.py

if command -v docker >/dev/null 2>&1; then
  docker compose up -d qdrant || echo "[WARN] Could not start Qdrant. Is Docker running?"
else
  echo "[WARN] Docker not found. Search will run in BM25-only mode."
fi

env_value() {  # env_value KEY DEFAULT: read KEY from .env, else DEFAULT
  local value
  value="$(grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- || true)"
  echo "${value:-$2}"
}
OLLAMA_URL="$(env_value OLLAMA_BASE_URL http://localhost:11434)"
CHAT_MODEL="$(env_value OLLAMA_CHAT_MODEL qwen3:8b)"
EMBED_MODEL="$(env_value OLLAMA_EMBED_MODEL nomic-embed-text)"
# Ollama is an external service (native app or Docker container): detect it over HTTP, not by the CLI.
if curl -fsS -m 5 "$OLLAMA_URL/api/version" >/dev/null 2>&1; then
  echo "Ollama is running at $OLLAMA_URL"
  TAGS="$(curl -fsS -m 10 "$OLLAMA_URL/api/tags" 2>/dev/null || true)"
  for model in "$CHAT_MODEL" "$EMBED_MODEL"; do
    case "$model" in *:*) wanted="\"name\":\"$model\"" ;; *) wanted="\"name\":\"$model:latest\"" ;; esac
    if printf '%s' "$TAGS" | grep -qF "$wanted"; then
      echo "Ollama model $model is pulled"
    elif command -v ollama >/dev/null 2>&1; then
      OLLAMA_HOST="$OLLAMA_URL" ollama pull "$model" || echo "[WARN] Could not pull $model"
    else
      echo "[WARN] Ollama model $model is not pulled and the ollama command is missing. Run:"
      echo "       docker exec ollama ollama pull $model"
    fi
  done
else
  echo "[WARN] Ollama is not answering at $OLLAMA_URL. Start it (app or Docker), then pull $CHAT_MODEL and $EMBED_MODEL"
fi

echo "Setup complete. Start FounderOS with ./run.sh"
