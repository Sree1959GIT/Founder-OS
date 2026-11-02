# FounderOS

A local-first decision copilot for business owners. It combines a Socratic voice advisor, a deterministic
DuckDB financial engine, an Obsidian-style Markdown brain with hybrid RAG, and a live visual canvas.

**Status:** milestone M0 (scaffold and foundations). The app starts, reports the health of its dependencies and
ships a synthetic demo company. Features arrive milestone by milestone; see [`HANDOVER.md`](HANDOVER.md).

- Product spec: [`docs/PRD.md`](docs/PRD.md)
- How to run a dev session with Claude Code: [`docs/GOAL_PROMPT.md`](docs/GOAL_PROMPT.md)
- Current state and next steps: [`HANDOVER.md`](HANDOVER.md)

## Requirements
- Python 3.11+
- Node.js 22 LTS (or 20.19+)
- Optional: [Ollama](https://ollama.com/download) (local LLM) and Docker Desktop (Qdrant vector search).
  Without them the app still starts and the health badge says what is missing.

## Quick start

Windows 11:

```bat
setup.bat
run.bat
```

Linux / macOS:

```bash
./setup.sh
./run.sh
```

Then open http://127.0.0.1:3000. The backend API is on http://127.0.0.1:8000 (`/api/health`, docs at `/docs`).

`setup` creates `.venv`, installs backend and frontend dependencies, copies `.env.example` to `.env`, starts Qdrant
with Docker (if available) and pulls the Ollama models named in `.env`.

## Configuration
All settings live in `.env` (git-ignored). See [`.env.example`](.env.example) for every key. By default everything
runs locally and nothing is sent to a cloud model (`CLOUD_ALLOWED=false`).

## Demo data
`sample_data/` holds "Northwind Analytics", a fictional B2B SaaS company (24 months of P&L, bank balance, customers,
subscriptions, pipeline, marketing spend and headcount). Regenerate it with:

```bash
python scripts/generate_demo_data.py              # USD
python scripts/generate_demo_data.py --currency INR --out sample_data_inr
```

## Development

```bash
cd backend && pytest -q && ruff check .. && ruff format --check ..
cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build
```

CI runs the same checks on every pull request (the backend on both Linux and Windows).

Full Windows setup, troubleshooting and the stakeholder demo script are added in milestone M6.
