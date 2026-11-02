# CLAUDE.md: rules for every Claude Code session in this repo

## Start of every session (mandatory)
1. Read **`HANDOVER.md` first**: it holds the current state, the next steps and founder feedback.
2. Then read `docs/PRD.md` (the agreed spec) and, if you are running a milestone, `docs/GOAL_PROMPT.md` (the session protocol).
3. `main` is the stable branch, which the founder merges into. Work on the branch this session was assigned, created from the latest `main`. At wrap-up, open a pull request into `main`. Never push to `main` directly.

## Session limits
- One milestone per session, or about 2 hours, whichever comes first. Then wrap up and **stop**. The founder is managing credits.
- Keep `HANDOVER.md` current as you go, not just at the end. A session can die at any moment.

## Engineering rules
- Python 3.11, FastAPI, asyncio, Pydantic v2, pydantic-settings, DuckDB, LangGraph, loguru. Lint with ruff; test with pytest (+ pytest-asyncio).
- Frontend: Vite, React 18, TypeScript (strict), Tailwind, shadcn/ui, Recharts.
- **No LLM arithmetic on financial data.** Numbers come from DuckDB routines and carry a `Lineage`.
- Every external service sits behind an interface with a fake, and tests never need GPU, Ollama, Docker, the network or Windows.
- Use `pathlib` for paths and UTF-8 for I/O. Nothing may be Linux-only, because the target is native Windows 11.
- Secrets live only in `.env` (git-ignored). Keep `.env.example` up to date.
- Model IDs come from config and are never hard-coded in agent logic. Agent prompts live in `backend/app/agents/prompts/*.md`.
- Thread a `workspace_id` (default `"default"`) through storage paths so multi-tenant support stays possible later.

## Commands (update as the project grows)
- Backend tests: `cd backend && pytest -q`
- Backend lint: `cd backend && ruff check .`
- Frontend checks: `cd frontend && npm run lint && npx tsc --noEmit && npm run build`
- Demo data: `python scripts/generate_demo_data.py`
