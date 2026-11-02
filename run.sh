#!/usr/bin/env bash
# Start FounderOS on Linux/macOS: Qdrant (if Docker is available), backend :8000 and frontend :3000.
# Ctrl+C stops both servers.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

[[ -x .venv/bin/python ]] || { echo "[ERROR] .venv not found. Run ./setup.sh first." >&2; exit 1; }
[[ -d frontend/node_modules ]] || { echo "[ERROR] Frontend dependencies missing. Run ./setup.sh first." >&2; exit 1; }

if command -v docker >/dev/null 2>&1; then
  docker compose up -d qdrant >/dev/null 2>&1 || echo "[WARN] Qdrant did not start (BM25-only search)."
fi

(cd backend && exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!
(cd frontend && exec npm run dev) &
FRONTEND_PID=$!
trap 'kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true' EXIT INT TERM

echo "FounderOS: http://127.0.0.1:3000 (Ctrl+C to stop)"
wait
