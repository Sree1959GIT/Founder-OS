#!/usr/bin/env bash
# FounderOS one-time setup for Linux/macOS (draft; finalised in M6). Mirrors setup.bat.
set -euo pipefail
cd "$(dirname "$0")"

echo "== FounderOS setup =="

PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  for candidate in python3.11 python3.12 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
  done
fi
if [[ -z "$PY" ]] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "[ERROR] Python 3.11+ is required." >&2
  exit 1
fi
command -v node >/dev/null 2>&1 || { echo "[ERROR] Node.js 22 LTS (or 20.19+) is required." >&2; exit 1; }

[[ -f .env ]] || { cp .env.example .env; echo "Created .env from .env.example"; }

[[ -x .venv/bin/python ]] || "$PY" -m venv .venv
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
CHAT_MODEL="$(env_value OLLAMA_CHAT_MODEL qwen2.5:7b-instruct-q4_K_M)"
EMBED_MODEL="$(env_value OLLAMA_EMBED_MODEL nomic-embed-text)"
if command -v ollama >/dev/null 2>&1; then
  ollama pull "$CHAT_MODEL" || echo "[WARN] Could not pull $CHAT_MODEL"
  ollama pull "$EMBED_MODEL" || echo "[WARN] Could not pull $EMBED_MODEL"
else
  echo "[WARN] Ollama not found. Install it, then: ollama pull $CHAT_MODEL && ollama pull $EMBED_MODEL"
fi

echo "Setup complete. Start FounderOS with ./run.sh"
