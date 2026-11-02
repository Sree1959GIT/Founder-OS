# HANDOVER: FounderOS

> **Every session reads this file first.** Update it as you work, not just at the end.
> Spec: `docs/PRD.md` · Session protocol: `docs/GOAL_PROMPT.md` · Repo rules: `CLAUDE.md`

## Quick status
- **Branching:** `main` is stable. Each session works on its own assigned branch, created from `main`, and ends by opening a PR into `main`. The founder reviews and merges that PR before starting the next session.
- **Next milestone:** **M1: Financial spine (DuckDB)**, after the founder merges the M0 PR
- **Review:** every PR must pass the 4 gates in "Review gates" below
- **Last updated:** 2026-11-02 (M0 session: scaffold done, PR awaiting founder)

## Milestones
| # | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Scaffold & foundations | DONE (awaiting merge) | Backend `/api/health`, Northwind data, frontend shell, scripts, CI |
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
| M0 Scaffold | PR pending | Light | AWAITING FOUNDER |

## Current session
- Started (UTC): 2026-11-02 15:47
- Target: **M0: Scaffold & foundations** (gate tier: Light)
- Plan:
  - [x] Backend package (`pyproject.toml`, `app/main.py`, `config.py`, `deps.py`, `/api/health` with dependency probes + tests)
  - [x] `.env.example`, `docker-compose.yml` (Qdrant only)
  - [x] `scripts/generate_demo_data.py` (Northwind, seeded) + `sample_data/` + tests
  - [x] Frontend shell (Vite + React + TS + Tailwind + shadcn/ui, design tokens, health badge via proxy)
  - [x] `setup.bat`/`run.bat` + `setup.sh`/`run.sh`
  - [x] GitHub Actions CI (pytest, ruff, frontend lint/tsc/build, windows-latest backend)
  - [x] Minimal README; wrap-up, self-review, PR

## Current state
**M0 is complete.** What works:
- **Backend** (`backend/`, Python 3.11, FastAPI). Started with `uvicorn --factory app.main:create_app` (no module-level
  app, so importing never reads `.env`). `GET /api/health` always answers 200 and reports `ok` or `degraded`, with one
  entry each for `ollama` (reachable, models pulled), `qdrant` (optional), `cloud` (from config only, never shows secrets),
  `gpu` (NVML through the optional `gpu` extra) and `storage` (workspace folders writable). Probes run concurrently
  with timeouts and never raise.
- **Config** (`app/config.py`, pydantic-settings) reads `<repo>/.env`. Relative paths resolve against the repo root,
  workspace ids are validated (no path tricks), and `effective_deep_provider()` falls back to Ollama unless
  `CLOUD_ALLOWED=true` and credentials exist.
- Empty packages with docstrings for `llm/`, `agents/` (+ `prompts/`), `decision/`, `engine/`, `vault/` and `voice/`
  (PRD §10 layout).
- **Demo data**: `scripts/generate_demo_data.py` writes Northwind Analytics (seed 42, USD, 2024-11..2026-10) to
  `sample_data/`: 7 CSVs, one XLSX (a sheet per table), `meta.json` and a data dictionary in `sample_data/README.md`.
  Money is computed in integer cents, so the cash identities reconcile exactly. At the end: 142 active customers, MRR
  about $255k, 27 staff, net burn about $176k/month, cash about $1.84M (runway roughly 10 months). `--currency INR`
  scales by a fixed 84.
- **Frontend** (`frontend/`, Vite 7, React 18, strict TypeScript, Tailwind 3, shadcn/ui primitives `Button`, `Badge`
  and `Card`). Design tokens ("Graphite & Signal") are CSS variables in `src/index.css`, mapped in `tailwind.config.ts`.
  Fonts are bundled locally (`@fontsource`), so the app works offline. The layout follows `Main.dc.html`: top bar
  (workspace, data status, privacy badge, live service health), Advisor panel, canvas and agent rail, with honest
  empty states that name the milestone each feature arrives in. The health badge polls `/api/health` every 15 s
  through the Vite proxy (3000 → 8000) and labels every status in text.
- **Scripts**: `setup.bat`/`run.bat` and `setup.sh`/`run.sh` (drafts; finalised in M6). Tested `.sh` in the
  container; the `.bat` files are untested (no Windows here).
- **CI** (`.github/workflows/ci.yml`): the backend runs ruff and pytest on ubuntu and windows-latest, plus a
  reproducibility check that the CSV/JSON demo data matches the generator. The frontend runs lint, tsc, vitest and build.

Stubbed or faked: nothing in delivered features. Advisor input, mic and Settings are visibly disabled until M3a, M5
and M4. Tests use fakes (httpx `MockTransport`, a fake NVML, fake probes).

Known issues:
- `npm audit` reports 12 moderate advisories, all inside eslint/typescript-eslint (a minimatch ReDoS); they are
  lint-time only. The critical and high Vite/Vitest advisories were fixed by moving to Vite 7 and Vitest 4.
- Vite 7 needs Node 20.19+ or 22.12+ (Node 22 LTS recommended).
- pytest shows a Starlette deprecation warning about `httpx` in `TestClient`. It is harmless.

## Next steps (for the M1 session)
1. Read founder feedback below first, and fix any M0 issues found on Windows.
2. `app/engine/lineage.py`: the `Lineage` model `{metric, sql, source_files, source_rows/range, formula, computed_at}`.
3. `app/engine/ingest.py` + column mapping (header synonyms, `data/<ws>/mappings.json`). Load the `sample_data/`
   tables into `data/<ws>/founder.duckdb`. Use `sample_data/README.md` for the schema and built-in identities.
4. `app/engine/sql_guard.py` (read-only connection, a single SELECT, a table allow-list, row and time limits).
5. `app/engine/metrics.py`: every PRD §F1 routine returns value + Lineage. Golden tests come from `sample_data`
   (compute the expected numbers independently in the tests with `Decimal`, as `tests/test_demo_data.py` does).
6. `scenario.py` (<200 ms), sensitivity, `montecarlo.py` (1,000 runs <1 s, seeded), `decision_science.py`
   (MCDA, EV and decision trees, kill criteria) and `calibration.py` (Brier).
7. REST: `/api/data/*`, `/api/metrics/*`, `/api/scenario`. M1 is a **Major** gate: write a thorough Windows checklist
   with expected numbers.

## Windows verification checklist (for the founder)
**M0 (Light tier).** Run in a terminal (cmd or PowerShell) from the repo folder after checking out the PR branch.
1. `node --version` should print v22.x (or v20.19 or newer). `py -3.11 --version` should print Python 3.11.x or newer.
2. `setup.bat`: it should finish with "Setup complete". Warnings about Docker or Ollama are fine if they are not
   installed. It creates `.env`, `.venv` and `frontend\node_modules`.
3. `run.bat`: two windows open (backend, frontend) and the browser opens http://127.0.0.1:3000.
4. The page shows the dark FounderOS layout: Advisor panel on the left, "No decision open yet" in the centre,
   "Local only" badge top right.
5. The service-health strip shows Ollama, Qdrant, Cloud, GPU and Storage. With Ollama running and models pulled,
   Ollama has a green dot and no "(down)". With Docker Desktop running, Qdrant is green. With the NVIDIA driver,
   the GPU shows `GPU x.x/12.0 GB`. Storage is green.
6. Open http://127.0.0.1:8000/api/health: JSON with `"status": "ok"` when Ollama, Qdrant and GPU are all up
   (otherwise `"degraded"` with a reason per dependency).
7. Stop Ollama (quit it from the tray) and wait 15 s: the badge shows `Ollama (down)` and the page keeps working.
8. Close the backend window: within 15 s the strip shows "Backend offline" and the privacy badge says
   "Privacy status unknown".
9. Optional: `.venv\Scripts\python scripts\generate_demo_data.py`, then `git status sample_data` shows
   no CSV/JSON changes (the demo data is reproducible on Windows).
10. Optional: open `sample_data\northwind_financials.xlsx` in Excel: 7 sheets, with figures that look plausible.

## Founder feedback
_Write results from your Windows checks, bugs and change requests here. The next session acts on them first._

## Open questions for founder
1. Demo currency: USD is the default; INR is available with `--currency INR` (fixed rate 84). Should the shipped
   `sample_data/` be INR instead?
2. Runway in the demo data is about 10 months at the end of the window. Is that the right level of tension for the
   demo (for example, so the Dubai scenario pushes it into the amber "under 3 months" band)?

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
- 2026-11-02 (M0 session, 15:47 to ~16:15 UTC): backend scaffold with config and the `/api/health` probes; Northwind
  generator and `sample_data/`; frontend shell with design tokens and the live health badge; setup/run scripts; CI;
  README. Self-review found 9 issues, all fixed with regression tests. 54 backend tests and 5 frontend tests pass.

## Decisions made (M0 session)
- Python venv at the repo root (`.venv`); backend installed editable from `backend/pyproject.toml` (extras: `dev`, `gpu`).
- Uvicorn runs the app factory (`--factory app.main:create_app`); there is no module-level app.
- `/api/health` returns 200 even when dependencies are down. "Required" covers Ollama and storage; Qdrant, cloud
  and GPU are optional. `not_configured` on an optional dependency still counts as OK overall.
- The shared ruff config is in the root `ruff.toml` (line length 120) and covers `backend/` and `scripts/`.
- Frontend: Tailwind 3 (not 4) for shadcn/ui compatibility; Vite 7 and Vitest 4 for security fixes. Node 22 LTS recommended.
- Fonts are bundled with `@fontsource` (no Google Fonts CDN) so the app works offline (acceptance demo step 7).
- Demo money is computed in integer cents; the XLSX is written with fixed timestamps so regeneration is byte-stable.
- `.gitattributes` keeps CSV/JSON as LF (Windows checkouts stay byte-identical) and `.bat` as CRLF.
