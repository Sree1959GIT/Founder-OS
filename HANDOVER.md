# HANDOVER: FounderOS

> **Every session reads this file first.** Update it as you work, not just at the end.
> Spec: `docs/PRD.md` · Session protocol: `docs/GOAL_PROMPT.md` · Repo rules: `CLAUDE.md`

## Quick status
- **Branching:** `main` is stable. Each session works on its own assigned branch, created from `main`, and ends by opening a PR into `main`. The founder reviews and merges that PR before starting the next session.
- **Next milestone:** **M2: Vault & hybrid RAG**, but only after the founder writes `ACCEPTED` for M1 in the Gate log (Major gate)
- **Review:** every PR must pass the 4 gates in "Review gates" below
- **Last updated:** 2026-11-03 (M1 bug-fix session: projected-runway feedback fixed in PR #3, awaiting the founder's **re-test**)

## Milestones
| # | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Scaffold & foundations | DONE (merged, PR #2) | Backend `/api/health`, Northwind data, frontend shell, scripts, CI |
| M1 | Financial spine (DuckDB) | DONE (founder feedback fixed; awaiting Major-gate re-test) | Branch `claude/m1-financial-spine` |
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
| M0 Scaffold | [Sree1959GIT/Founder-OS#2](https://github.com/Sree1959GIT/Founder-OS/pull/2) | Light | ACCEPTED (merged) |
| M1 Financial spine | [Sree1959GIT/Founder-OS#3](https://github.com/Sree1959GIT/Founder-OS/pull/3) | **Major** | AWAITING FOUNDER (re-test). ISSUES FOUND 2026-11-03 (projection growth assumption) were fixed in the same PR: run checklist steps R1–R8 |

## Current session
- Started (UTC): 2026-11-03 05:48 (local Windows 11 session, founder's PC)
- Target: **M1: Financial spine (DuckDB)** (gate tier: **Major**)
- Plan:
  - [x] Founder notes: answers to the M0 questions recorded (HANDOVER + PRD §12); `frontend/.vite/` in `.gitignore`
  - [x] `engine/lineage.py`, `engine/schema.py` (canonical tables + header synonyms), `engine/ingest.py` (CSV/XLSX, `mappings.json`)
  - [x] `engine/duckdb_engine.py` (workspace DB, locking) + `engine/sql_guard.py` (read-only, single SELECT, allow-list, limits)
  - [x] `engine/metrics.py`: every §F1 routine with Lineage + golden tests (expected values computed independently with `Decimal`)
  - [x] `engine/scenario.py` (<200 ms) + sensitivity, `engine/montecarlo.py` (1,000 runs <1 s, seeded)
  - [x] `engine/decision_science.py` (MCDA, EV, decision trees, kill criteria), `engine/calibration.py` (Brier)
  - [x] REST: `/api/data/*`, `/api/metrics/*`, `/api/scenario*` + API tests
  - [x] Wrap-up: checks, self-review, HANDOVER (Windows checklist with Excel spot-checks), PR, CI

## Current state
**M1 is complete** (PR awaiting the founder's Major gate). M0 behaviour is unchanged. What works:
- **Ingestion** (`app/engine/ingest.py`, `schema.py`): CSV (UTF-8, falls back to Windows-1252) and XLSX (every sheet).
  Each sheet maps onto one of 7 canonical tables (`pnl`, `bank_balance`, `customers`, `subscriptions`, `pipeline`,
  `marketing_spend`, `headcount`): explicit choice > saved mapping > file or sheet name > best header match. Headers
  map through synonyms (e.g. `Period` → `month`, `Line Item` → `account`, `Cost of Sales` → `COGS`). Values are parsed
  strictly (`$1,234.50`, `(500)`, `Oct 2026`, Excel dates, `25%`). One bad cell rejects the whole file with row-level
  errors, and the previous data stays. `bank_balance` must have one row per month. Loading replaces the table.
  Mappings are saved to `data/<ws>/mappings.json`.
  Every row keeps `_source_file`, `_source_sheet` and `_source_row` (= CSV record / Excel row number, header = 1).
- **DuckDB** (`duckdb_engine.py`): `data/<ws>/founder.duckdb`. Short-lived connections behind a lock, and **external
  file access is disabled on every connection**.
- **SQL guard** (`sql_guard.py`): exactly one SELECT; tables are read from the parsed AST (CTE-aware) and must be
  canonical tables; no table functions (`read_csv`, `glob`…), file paths, system catalogs or `_internal` tables. It
  runs DuckDB's canonical re-serialisation of the validated AST (so comments and `;` cannot change it) on a
  read-only connection with a row limit (+ truncation flag) and a time limit (`interrupt()`).
- **Metrics** (`metrics.py`): 18 routines, each returning `MetricResult {value, unit, as_of, detail, lineage}`.
  Lineage = the exact SQL executed, the source files and row ranges, the formula, the named inputs and the period. Definitions
  and default windows are in the module docstring. Defaults: burn and runway use the **trailing 3 months**, gross
  margin is the as-of month, MRR is point-in-time, and NRR uses a 12-month lookback.
- **Scenario** (`scenario.py`): drivers are measured from DuckDB over the trailing 3 months (with lineage) and cached per
  DB version, then a NumPy recurrence (documented in `RECURRENCE`) is applied. Inputs: price %, churn points, CAC %,
  acquisition %, marketing %, hires (+ optional cost), other spend, start month, horizon (≤ 36). The response time is about
  3–10 ms warm and about 150 ms cold. Sensitivity: a 2-variable grid (≤ 11 × 11) of cash at the horizon or runway.
- **Monte Carlo** (`montecarlo.py`): normal/uniform/triangular distributions on any adjustment; seeded; P10/P50/P90
  cash fan, runway P10/P50/P90 and P(cash < 0) within the horizon and 12 months. 1,000 runs take about 5 ms warm.
- **Decision science** (`decision_science.py`): weighted scoring with 2×2 quadrants (Quick win / Big bet / Fill-in /
  Deprioritise), expected value, decision trees with rollback and policy (e.g. "pilot first"), and kill criteria
  evaluated on live metrics. **Calibration** (`calibration.py`): a JSON store of predictions, outcomes and Brier per owner.
- **REST**: `/api/data/{tables,mappings,load-sample,upload,query}`, `/api/metrics` (index), `/api/metrics/summary`
  (`{metrics, unavailable}`: one metric that cannot be computed does not fail the rest),
  `/api/metrics/{name}`, `/api/metrics/cash-projection`, `/api/metrics/kill-criteria`, `/api/scenario`,
  `/api/scenario/sensitivity`, `/api/scenario/montecarlo`. Engine errors map to 409 (no data), 422 (bad input or
  file), 400 (SQL rejected), 413 (upload too big) and 415 (wrong type). Uploads are kept in `data/<ws>/uploads/`.
- **Startup**: an empty workspace is loaded with `sample_data/` (`AUTO_LOAD_SAMPLE_DATA=true`; failures only log).

Northwind headline numbers (as of 2026-10): MRR $255,344.27 (142 customers), ARR $3,064,131.24, gross burn
$428,612.47/month, net burn $172,280.47/month (3-month average), cash $1,835,125.06, **runway 10.65 months (zero cash
2027-09)**, gross margin 72.13 %, blended CAC $26,261.27, LTV:CAC 2.92, CAC payback 20.4 months, NRR 99.2 %.

Stubbed or faked: nothing. Not exposed over REST yet: the decision-science and calibration routines (they are engine
functions that M3's agents call; only kill criteria have an endpoint). There is no frontend change in M1 (the canvas is M4).

Two runways (fixed after founder feedback; names are in every API response under `labels`, ready for M4):
- **Runway (actual burn)** = the `runway` metric: closing cash / trailing 3-month net burn from the bank sheet = **10.65**.
- **Projected runway (with growth assumptions)** = `base_runway_months` / `scenario_runway_months` from the projection.
  `growth_mode` picks the growth assumption (on `/api/scenario`, `/api/scenario/sensitivity` `base`,
  `/api/scenario/montecarlo` `adjustments`, and `GET /api/metrics/cash-projection?growth_mode=`):
  `trend` (default; keeps acquiring 5.33 customers/month) **11.23**; `none` (no new customers, churn continues,
  marketing still spent; same as `acquisition_change_pct=-100`) **9.69**; `flat` (today's run-rate: no new customers,
  no churn) **10.71**.
- Every projection response carries `assumptions` (12 drivers: value, label, unit, window, `used`, and per-driver
  lineage with SQL and source rows); `/api/scenario` and `/cash-projection` also carry `reconciliation`: actual-burn
  runway 10.65 → run-rate 10.71 (+0.06: bank cash vs P&L burn differ by 971.45/month, 0.6 %, within the 5 % tolerance
  of 0.53 months) → projected 11.23 (+0.52 from growth), with a plain-English `explanation`.

Known issues / notes:
- CAC uses P&L operating-expense accounts whose names contain "sales", "marketing" or "commission". Real charts of
  accounts may need a mapping UI (M4).
- If another program (e.g. the DuckDB CLI) holds `founder.duckdb` open, the backend cannot open it and requests fail.
- The first Monte Carlo call after start-up takes about 1–3 s on Windows (NumPy lazy imports / Defender scan); later calls
  take about 5 ms.
- `pytest` shows a Starlette deprecation warning about `httpx` in `TestClient`. It is harmless.
- `engine/` coverage was not measured (pytest-cov is not a dev dependency); every module has dedicated tests.

## Next steps (for the M2 session)
0. **Gate check:** M1 is a **Major** gate. Do not start M2 until the Gate log row for M1 says `ACCEPTED`. If the
   founder reported issues, fix them first (a bug-fix PR).
1. Read founder feedback below; fix any M1 issues found on Windows (wrong numbers take priority over everything).
2. M2 (PRD §F2): `app/vault/manager.py` (frontmatter, wikilinks + aliases, backlinks `.index/links.json`, rename-safe
   updates), `watcher.py` (watchfiles), parsers (PDF via pypdf, CSV/XLSX summary rows, MD/TXT).
3. `engine/chunking.py` (parent ≈1000 / child ≈250 tokens, tiktoken `cl100k_base`), embeddings behind an interface
   (Ollama `nomic-embed-text` + fake), Qdrant store + in-memory fallback, BM25 (`rank-bm25`), RRF (k=60).
4. `/api/vault/*`, `/api/search`; tests with fake embeddings and an in-memory vector store.
5. Later (M3a): expose decision-science and calibration as Financial Analyst tools; add REST for them if the UI needs it.

## Windows verification checklist (for the founder)
**M1 (Major tier, about 30 min).** Check out the PR branch (`git fetch origin` then `git checkout claude/m1-financial-spine`),
run `setup.bat` once (it installs the new `numpy` and `python-multipart` packages), then `run.bat`. When done, write
`ACCEPTED` (or the issues) in the Gate log row for M1.

*Start-up and data*
1. The backend window logs `Loaded sample data from ...\sample_data (7 tables)` on the first start (empty workspace).
   `data\default\founder.duckdb` now exists.
2. Open http://127.0.0.1:8000/docs: the new sections are **data**, **metrics** and **scenario**. In **GET /api/data/tables**, click
   "Try it out" → "Execute": 7 loaded tables (pnl 360 rows, bank_balance 24, customers 198, subscriptions 2535,
   pipeline 396, marketing_spend 72, headcount 29).

*Numbers: spot-check these against Excel* (open `sample_data\northwind_financials.xlsx`)
3. http://127.0.0.1:8000/api/metrics/summary (shown as JSON in the browser) lists under `metrics`: `mrr` 255344.27, `net_burn`
   172280.47, `gross_burn` 428612.47, `runway` 10.65, `gross_margin` 0.7213; `unavailable` is `{}`.
4. **Burn** (sheet `bank_balance`, rows **23–25** = 2026-08, 2026-09, 2026-10; column F = `cash_out`, C = `customer_receipts`):
   - Gross burn = `=AVERAGE(F23:F25)` → **428,612.47**
   - Net burn = `=AVERAGE(F23:F25)-AVERAGE(C23:C25)` → **172,280.47** (same as `=-AVERAGE(G23:G25)`, since there is no
     financing in those months)
   - http://127.0.0.1:8000/api/metrics/net_burn shows `lineage.source_rows[0].rows` = `"23-25"`: the same rows.
5. **Runway** = `=H25/(AVERAGE(F23:F25)-AVERAGE(C23:C25))` (H25 = closing balance **1,835,125.06**) → **10.65 months**.
   http://127.0.0.1:8000/api/metrics/runway shows `value` 10.65 and `detail.zero_cash_month` **2027-09** (cash runs out
   during the 11th month after Oct 2026).
6. **Gross margin, Oct 2026** (sheet `pnl`, rows **347–361** are 2026-10; columns A month, C category, D amount):
   - Revenue `=SUMIFS(D:D,A:A,"2026-10",C:C,"Revenue")` → **257,844.27** (rows 347–348)
   - COGS `=SUMIFS(D:D,A:A,"2026-10",C:C,"COGS")` → **71,850.06** (rows 349–351)
   - Gross margin = (257,844.27 − 71,850.06) / 257,844.27 → **72.13 %**. http://127.0.0.1:8000/api/metrics/gross_margin
     shows `value` 0.7213 and the lineage rows `347-351`.
7. Optional, **MRR**: sheet `subscriptions` `=SUMIFS(C:C,A:A,"2026-10")` → **255,344.27** (rows 2395–2536, 142
   customers). It equals `pnl` row 347 "Subscription revenue".

*Scenario and Monte Carlo* (on /docs, use "Try it out")
8. **POST /api/scenario** with body `{"price_change_pct": 10, "churn_change_pts": 2}` → `points` has 12 months from
   2026-11; `base_runway_months` 11.23 and `scenario_runway_months` 10.99; `elapsed_ms` well under 200.
9. **POST /api/scenario/sensitivity** with body `{}` → a 5×5 `table` of runway months (price −20…+20 % × churn
   −1…+3 points); `table[2][1]` (3rd row = price 0, 2nd column = churn 0) equals `base_value` 11.23.
10. **POST /api/scenario/montecarlo** with body `{}` → `runs` 1000, `points` with p10 ≤ p50 ≤ p90, `runway_p50` about
    11.3, `probability_cash_out_within_12_months` about 0.8. Run it twice: the results are identical (seeded).

*Safety and uploads*
11. **POST /api/data/query** with `{"sql": "DROP TABLE pnl"}` → 400 "Only SELECT queries are allowed". With
    `{"sql": "SELECT * FROM read_csv('C:/Windows/win.ini')"}` → 400 "Table functions ... are not allowed".
    With `{"sql": "SELECT category, sum(amount) FROM pnl GROUP BY 1"}` → 200 with three rows.
12. **POST /api/data/upload** with `sample_data\northwind_financials.xlsx` → 200 with 7 tables (sheets mapped by
    name); the metrics in step 3 are unchanged. A `.txt` file gives 415.
13. Optional: Excel export with your own headers: save a sheet with columns `Period, Line Item, Type, Value` as CSV and
    upload it. It maps to `pnl` (see `GET /api/data/mappings`). Then **POST /api/data/load-sample** to restore the demo data.
14. Regression: the M0 page at http://127.0.0.1:3000 still loads, and the health strip works as before.

*Re-test after the projected-runway fix (2026-11-03).* `git pull` on `claude/m1-financial-spine`, restart `run.bat`
(no new packages), then run these in a **PowerShell** window (they work in Windows PowerShell 5.1 and PowerShell 7):
- R1. Two runways, named apart:
  `Invoke-RestMethod http://127.0.0.1:8000/api/metrics/runway | Select-Object label, value` → `Runway (actual burn)`, **10.65**.
  `$p = Invoke-RestMethod http://127.0.0.1:8000/api/metrics/cash-projection; $p | Select-Object growth_mode, base_runway_months, base_zero_cash_month`
  → `trend`, **11.23**, `2027-10`. `$p.labels` shows the four runway labels for the UI.
- R2. The assumptions behind the projection: `$p.assumptions | Format-Table name, value, unit, used, window, label -AutoSize`
  → 12 rows, all `used = True`; e.g. `new_customers` **5.33** (`2026-08..2026-10`), `churn` **0.0167**, `marketing`
  **47910**, `cash` **1835125.06** (`2026-10`). Row lineage:
  `($p.assumptions | Where-Object name -eq 'new_customers').lineage.source_rows` → table `customers`, rows `184-199`.
- R3. **Excel** check of two assumptions (`northwind_financials.xlsx`): sheet `customers` (column G = `signup_month`)
  `=COUNTIF(G:G,"2026-08")+COUNTIF(G:G,"2026-09")+COUNTIF(G:G,"2026-10")` → **16** (rows 184–199), /3 = **5.33**
  new customers per month. Sheet `marketing_spend` `=SUM(C65:C73)/3` → **47,910.00** per month.
- R4. Reconciliation: `$p.reconciliation | Format-List` → `runway_actual_burn_months` 10.65, `actual_net_burn`
  172280.47, `run_rate_runway_months` 10.71, `run_rate_net_burn` 171309.02, `basis_gap_net_burn` 971.45,
  `basis_gap_months` 0.06, `tolerance_months` 0.53, `within_tolerance` True, `growth_gap_months` 0.52, and an
  `explanation` sentence that walks 10.65 → 10.71 → 11.23.
- R5. No new customers:
  `Invoke-RestMethod "http://127.0.0.1:8000/api/metrics/cash-projection?growth_mode=none" | Select-Object growth_mode, base_runway_months, base_zero_cash_month`
  → `none`, **9.69**, `2027-08` (shorter than 10.65: churn keeps eroding MRR while marketing is still spent).
  With `growth_mode=flat` → **10.71**, `2027-09` (today's run-rate, reconciles with 10.65). With `growth_mode=rocket` →
  an error (HTTP 422).
- R6. Scenario with a growth mode:
  `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/scenario -ContentType 'application/json' -Body '{"growth_mode": "none", "price_change_pct": 10}' | Select-Object growth_mode, base_runway_months, scenario_runway_months, scenario_zero_cash_month`
  → `none`, **9.69**, **10.68**, `2027-09`.
- R7. Monte Carlo with a growth mode:
  `$mc = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/scenario/montecarlo -ContentType 'application/json' -Body '{"adjustments": {"growth_mode": "flat"}}'; $mc | Select-Object growth_mode, runway_label, runway_p10, runway_p50, runway_p90`
  → `flat`, `Projected runway (with growth assumptions)`, **10.14**, **10.59**, **10.96**; `$mc.assumptions.Count` → 12.
- R8. Regression: steps 3–10 above give the same numbers as before (the default `growth_mode` is `trend`).

## Founder feedback
_Write results from your Windows checks, bugs and change requests here. The next session acts on them first._
### [M1] Projected runway (11.23) differs from runway metric (10.65); growth assumption is hidden
- Did: ran the M1 Windows checklist. Items 1–12 and 14 all pass; every number matches Excel
- Expected: when the runway card and the scenario chart show different runways, the reason is visible and I can change it
- Got: /api/metrics/runway = 10.65 months (actual 3-month net burn), but /api/scenario base_runway_months = 11.23 because the projection assumes new customers keep arriving. Meanwhile revenue_growth = -0.63% last month, so the assumption isn't obvious from the data
- Fix wanted:
  1. ScenarioResult and MonteCarloResult return an `assumptions` list: each projection driver (new customers/month, ARPA, churn, fixed costs, cost per hire, etc.) with value, plain-English label, the window it was derived from, and lineage (table + rows)
  2. A documented, tested way to run the projection with "no new customers" (e.g. acquisition_change_pct = -100 or a `growth_mode: "none" | "trend"` input), returned by /api/metrics/cash-projection too
  3. A reconciliation test: with no growth, projection runway agrees with the runway metric (10.65) within a stated tolerance, or the remaining gap is explained in the response
  4. Clear naming in API responses and docs: "runway (actual burn)" vs "projected runway (with growth assumptions)", ready for M4 labels
- Priority: high (blocks M1 acceptance)
- **Resolved (2026-11-03, same PR #3; re-test: checklist steps R1–R8):**
  1. `ScenarioResult` and `MonteCarloResult` return `assumptions`: all 12 drivers (starting cash, MRR, churn, new
     customers/month, MRR per new customer, acquisition cost, marketing, other revenue, variable COGS ratio,
     commission ratio, fixed costs, cost per hire) with value, label, unit, window, `used`/`note` and their own lineage
     (SQL + table + rows).
  2. `growth_mode`: `"trend"` (default) | `"none"` (no new customers; same as `acquisition_change_pct=-100`) |
     `"flat"` (today's run-rate). Accepted by `/api/scenario`, sensitivity (`base`), Monte Carlo (`adjustments`) and
     `GET /api/metrics/cash-projection?growth_mode=`. Tested.
  3. Reconciliation: the run-rate projection (`flat`) gives 10.71 vs the metric's 10.65. The gap is explained in
     `reconciliation`: the bank burn is cash-basis and the projection is P&L-basis, a difference of 971.45/month (0.6 %).
     The stated tolerance is 5 % of the metric runway (0.53 months). Tests also check Dec 2025, where receipts lag
     the Nov price uplift (gap 0.86, tolerance 1.11). The `trend` and `none` modes add a growth gap: +0.52 and −1.02
     months. The `explanation` says why, in plain English.
  4. Naming: the metric is labelled "Runway (actual burn)". Projected runways are "Projected runway (with growth
     assumptions)" (field descriptions plus a `labels` map in responses). Docs: README, HANDOVER, the docstrings in
     `metrics.py` and `scenario.py`.
  Note: no number in the original checklist changed (default `growth_mode` = `trend`).
### [M0] setup.bat picks Python 3.14 when 3.11 is not installed
- Did: ran setup.bat on Windows 11 with Python 3.12 and 3.14 installed (no 3.11); `python` on PATH is 3.14.5
- Expected: setup.bat chooses a supported version (3.12 or 3.11)
- Got: it only tries `py -3.11`, then falls back to `python` (3.14). Worked around by running `py -3.12 -m venv .venv` before setup.bat
- Fix wanted: try `py -3.12`, then `py -3.11`, then `python`; warn if the chosen version is 3.13 or newer (later ML/voice wheels may be missing). Update run.bat/README to match
- Priority: low
- M0 checklist: items 1–8 passed on RTX 4080 Laptop (Node v24.13.1, Python 3.12 venv); Ollama not installed yet
- **Resolved (2026-11-03, same PR):** `setup.bat` now tries `py -3.12`, then `py -3.11`, then `python`, and prints
  the version it chose. `setup.bat`, `run.bat` and `setup.sh` warn when `.venv` is Python 3.13+. The README recommends 3.12.
  Re-test: checklist step 11.

## Open questions for founder
_None open._

Answered (2026-11-03, founder note at the start of the M1 session):
1. ~~Demo currency~~: **keep USD** for the shipped `sample_data/` (INR stays available with `--currency INR`).
2. ~~Demo runway~~: **keep runway at about 10 months** at the end of the data window.

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
- 2026-11-03 (M1 session, 05:48 UTC onwards, local on the founder's PC): engine core (lineage, schema + column
  mapping, ingest, DuckDB with external access disabled, SQL guard, 18 metric routines); scenario + sensitivity,
  Monte Carlo, decision science, calibration; REST endpoints; backend tests including golden tests against an
  independent Decimal re-computation. Push needed the GitHub noreply email (repo-local `user.email`; see Decisions).
- 2026-11-03 (M1 self-review, `/code-review high`): 10 findings, all fixed with regression tests: money parsing
  ("Rs. 1,000" read as 0.10; "$(1,000)" lost its sign), duplicate bank months, a CTE-scope bypass in the SQL guard,
  trailing comments breaking guarded SQL, the summary failing on one metric, a sensitivity 500, interpolated Monte Carlo
  runway percentiles, undecodable CSV / DECIMAL overflow giving 500s, and a dead registry class. 250 backend tests.
- 2026-11-03 (M1 bug-fix session, local): acted on the founder's Major-gate feedback "[M1] Projected runway". Added
  growth modes (trend/none/flat), per-driver `assumptions` with lineage, the runway `reconciliation` and the
  actual-burn vs projected naming. 264 backend tests (14 new). No M2 work.
- 2026-11-02: Planning session. Agreed scope with the founder and wrote PRD v2, GOAL_PROMPT, CLAUDE.md and HANDOVER.md.
- 2026-11-02: Added the agent design (F3, F4b), decision models (F7) and decision-science routines to the PRD; split M3; started the UI mock-ups in Claude Design.
- 2026-11-02 (M0 session, 15:47 to ~16:15 UTC): backend scaffold with config and the `/api/health` probes; Northwind
  generator and `sample_data/`; frontend shell with design tokens and the live health badge; setup/run scripts; CI;
  README. Self-review found 9 issues, all fixed with regression tests. The first CI run caught a Windows-only bug
  (`meta.json` written with CRLF); it was fixed by forcing LF, with a test. 55 backend tests and 5 frontend tests pass, and CI is
  green on ubuntu and windows-latest.

- 2026-11-03: Acted on founder feedback (setup.bat chose Python 3.14). Python is now picked 3.12 → 3.11 → `python`, with a
  3.13+ warning in setup and run scripts; README updated.

## Decisions made (M1 session)
- Months are stored as `YYYY-MM` text, money as `DECIMAL(18,2)`; money sums run in DuckDB, ratios in Python `Decimal`
  (money rounded to cents and ratios to 4 dp, half-up). The API returns plain JSON numbers.
- Burn is **operating** burn: net burn = cash_out − customer_receipts (financing excluded), averaged over the trailing
  3 months. Runway = closing cash ÷ net burn; zero-cash month = as-of month + ceil(runway).
- Loading a file **replaces** its table. Ingestion is all-or-nothing per file (strict parsing, row-level errors).
- Every DuckDB connection runs with `enable_external_access=false`; agent SQL goes through the AST-based guard on a
  read-only connection.
- Scenario drivers come from DuckDB (with lineage) and the projection is a deterministic NumPy recurrence shared by the
  scenario, sensitivity and Monte Carlo code; drivers are cached per DB version.
- Empty workspaces auto-load the Northwind data at startup (`AUTO_LOAD_SAMPLE_DATA`, default true).
- New backend dependencies: `numpy` (Monte Carlo, named in the PRD) and `python-multipart` (FastAPI uploads).
- Git: the founder's GitHub account blocks pushes that expose the private email, so this repo has a **repo-local**
  `user.email` = the GitHub noreply address (`134863931+Sree1959GIT@users.noreply.github.com`). The global config is unchanged.

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
