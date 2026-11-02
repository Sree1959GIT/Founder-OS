# HANDOVER: FounderOS

> **Every session reads this file first.** Update it as you work, not just at the end.
> Spec: `docs/PRD.md` · Session protocol: `docs/GOAL_PROMPT.md` · Repo rules: `CLAUDE.md`

## Quick status
- **Branching:** `main` is stable. Each session works on its own assigned branch, created from `main`, and ends by opening a PR into `main`. The founder reviews and merges that PR before starting the next session.
- **Next milestone:** **M0: Scaffold & foundations**
- **Review:** every PR must pass the 4 gates in "Review gates" below
- **Last updated:** 2026-11-02 (planning session, no code yet)

## Milestones
| # | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Scaffold & foundations | NOT STARTED | |
| M1 | Financial spine (DuckDB) | NOT STARTED | |
| M2 | Vault & hybrid RAG | NOT STARTED | |
| M3a | LLM layer, agent framework & core agents | NOT STARTED | |
| M3b | Specialist agents | NOT STARTED | |
| M3c | Decision models (Laya / Jev) | NOT STARTED | |
| M4 | Canvas UI (first demoable build) | NOT STARTED | |
| M5 | Voice pipeline | NOT STARTED | |
| M6 | Windows packaging, polish & demo | NOT STARTED | |

## Review gates (every PR passes all four)
| # | Gate | Who | Pass condition |
|---|---|---|---|
| 1 | **CI** | GitHub Actions (from M0) | Backend tests, ruff, frontend lint/tsc/build, and the Windows backend job are all green |
| 2 | **Self-review** | The session | Own diff reviewed; no open high-severity findings; scope = this milestone only |
| 3 | **PR checklist** | The session, checked by the founder | Every section of the PR template is filled: DoD items, tests added, HANDOVER updated, no secrets |
| 4 | **Founder review** | Founder | Depends on the tier below. Merge the PR to pass |

**Tiers for gate 4:**
- **Light** (about 5 min): read the summary, run the short Windows checklist, merge.
- **Medium** (about 15 min): run the checklist and try the new feature by hand.
- **Major** (about 30 min): a full checklist and acceptance test on the Windows PC. Then write `ACCEPTED` (or the issues found) in the Gate log. **The next milestone cannot start until a Major gate is ACCEPTED.**

| Milestone | Tier |
|---|---|
| M0 Scaffold | Light |
| M1 Financial engine | **Major** (are the numbers right?) |
| M2 Vault & search | Light |
| M3a Agent framework | Medium (first run with real Ollama) |
| M3b Specialist agents | Medium |
| M3c Laya / Jev | Light |
| M4 Canvas UI | **Major** (first full demo) |
| M5 Voice | **Major** (latency and barge-in on the GPU) |
| M6 Packaging | **Major** (fresh install with `run.bat`) |
| Partial-milestone PRs and bug-fix PRs | Light |

### Gate log
| Milestone | PR | Tier | Status |
|---|---|---|---|
| Planning | (committed directly before the branch rename) | n/a | ACCEPTED |

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
5. Set up the frontend: Vite + React + TS + Tailwind + shadcn/ui shell. Take the **design tokens (colours, type, spacing, radius) and the overall layout from the Claude Design mock-ups** linked in `docs/design/README.md`, and put them in Tailwind config and CSS variables. Include a health badge that calls `/api/health` through the Vite proxy (port 3000 → 8000).
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

Second planning round (2026-11-02):
- Agents: fixed types (5 core and 8 specialist) with instances spawned dynamically by the Planner, in parallel. The founder approves teams that include cloud agents. Custom agent types come after v1.
- Agent Activity panel on the dashboard.
- Decision-model layer: LLM, then Laya (local, fine-tuned), with Jev as an optional paid add-on. Monte Carlo, weighted scoring, EV and calibration were added to the engine.
- M3 is split into M3a/M3b/M3c.
- The UI is being designed in Claude Design first (see `docs/design/README.md`).

## Progress log
- 2026-11-02: Planning session. Agreed scope with the founder and wrote PRD v2, GOAL_PROMPT, CLAUDE.md and HANDOVER.md.
- 2026-11-02: Added the agent design (F3, F4b), decision models (F7) and decision-science routines to the PRD; split M3; started the UI mock-ups in Claude Design.
