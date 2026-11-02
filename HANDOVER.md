# HANDOVER: FounderOS

> **Every session reads this file first.** Update it as you work, not just at the end.
> Spec: `docs/PRD.md` · Session protocol: `docs/GOAL_PROMPT.md` · Repo rules: `CLAUDE.md`

## Quick status
- **Development branch:** `claude/bold-keller-b7aput` (push only here; the founder merges to `main`)
- **Next milestone:** **M0: Scaffold & foundations**
- **Last updated:** 2026-11-02 (planning session, no code yet)

## Milestones
| # | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Scaffold & foundations | NOT STARTED | |
| M1 | Financial spine (DuckDB) | NOT STARTED | |
| M2 | Vault & hybrid RAG | NOT STARTED | |
| M3 | LLM layer & agents (text) | NOT STARTED | |
| M4 | Canvas UI (first demoable build) | NOT STARTED | |
| M5 | Voice pipeline | NOT STARTED | |
| M6 | Windows packaging, polish & demo | NOT STARTED | |

## Current session
- Started (UTC): n/a
- Target: n/a
- Plan: n/a

## Current state
Only planning documents exist: PRD v2, the `/goal` prompt, CLAUDE.md and this file. The original blueprint is kept in
`docs/reference/original_blueprint.md` for reference only. Where it differs from `docs/PRD.md`, the PRD wins.

## Next steps (for the M0 session)
1. Create the repo layout from PRD §10. Backend: `pyproject.toml` (or requirements + requirements-dev), `app/main.py`, `config.py` (pydantic-settings, reads `.env`), `/api/health` reporting dependency status (Ollama, Qdrant, Gemini/Claude configured?, GPU?).
2. Write `.env.example` with these keys: `WORKSPACE_ID`, `DATA_DIR`, `VAULT_PATH`, `OLLAMA_BASE_URL`, `OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `QDRANT_HOST`, `QDRANT_PORT`, `DEEP_PROVIDER`, `CLOUD_ALLOWED`, `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `CURRENCY`.
3. Add `docker-compose.yml` with Qdrant only.
4. Write `scripts/generate_demo_data.py`: seeded "Northwind Analytics" B2B SaaS covering 24 months of P&L, bank balance, customers/subscriptions, pipeline, marketing spend by channel and headcount. Output to `sample_data/` as CSV plus one XLSX.
5. Set up the frontend: Vite + React + TS + Tailwind + shadcn/ui shell with a dark theme, a placeholder layout (conversation left, canvas right) and a health badge that calls `/api/health` through the Vite proxy (port 3000 → 8000).
6. Draft `setup.bat`/`run.bat` and `setup.sh`/`run.sh`.
7. Add GitHub Actions CI with jobs for pytest, ruff, frontend lint/tsc/build, and one `windows-latest` backend test job.
8. Write a minimal README (it is expanded fully in M6).

## Windows verification checklist (for the founder)
_None yet. Each milestone adds one here._

## Founder feedback
_Write results from your Windows checks, bugs and change requests here. The next session acts on them first._

## Open questions for founder
_None._

## Decisions made
See PRD §12 (Decision log). Summary of the planning session on 2026-11-02:
- New repo, text-first build order (voice last), milestone-based sessions of about 2 hours.
- Ollama is the default LLM. Deep-work agents (risk, memo, scout) can use Claude via the **Claude Agent SDK on the founder's subscription** (`CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`), Anthropic API or Gemini, with automatic fallback to Ollama.
- Single user now, sell later.
- Runs natively on Windows; Docker only for Qdrant.
- Stack: LangGraph, Kokoro, Qdrant, shadcn/ui + Recharts. Synthetic demo data. Tests use mocks; the founder verifies on the PC.

## Progress log
- 2026-11-02: Planning session. Agreed scope with the founder and wrote PRD v2, GOAL_PROMPT, CLAUDE.md and HANDOVER.md.
