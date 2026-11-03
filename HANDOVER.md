# HANDOVER: FounderOS

> **Every session reads this file first.** Update it as you work, not just at the end.
> Spec: `docs/PRD.md` · Session protocol: `docs/GOAL_PROMPT.md` · Repo rules: `CLAUDE.md`

## Quick status
- **Branching:** `main` is stable. Each session works on its own assigned branch, created from `main`, and ends by opening a PR into `main`. The founder reviews and merges that PR before starting the next session.
- **Next milestone:** **M3a: LLM layer, agent framework & core agents**, after the founder merges the M2 PR (M2 is a Light gate: run the checklist below, then merge). M1 is ACCEPTED (Major gate passed 2026-11-03)
- **Review:** every PR must pass the 4 gates in "Review gates" below
- **Last updated:** 2026-11-03 (M2 session, 13:29 to ~14:15 UTC: M2 complete, PR open, awaiting the founder's Light gate)

## Milestones
| # | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Scaffold & foundations | DONE (merged, PR #2) | Backend `/api/health`, Northwind data, frontend shell, scripts, CI |
| M1 | Financial spine (DuckDB) | DONE (merged, PRs #3 + #4; Major gate ACCEPTED 2026-11-03) | |
| M2 | Vault & hybrid RAG | DONE (PR open, awaiting Light gate) | Branch `claude/m2-vault-search` |
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
| M1 Financial spine | [Sree1959GIT/Founder-OS#4](https://github.com/Sree1959GIT/Founder-OS/pull/4) (fix; M1 itself merged in [#3](https://github.com/Sree1959GIT/Founder-OS/pull/3)) | **Major** | ACCEPTED (SM, 2026-11-03) after re-test R1–R8 on Windows; fix in #4 |

## Current session
- Started (UTC): 2026-11-03 13:29 (local Windows 11 session, founder's PC); wrapped up ~14:15
- Target: **M2: Vault & hybrid RAG** (gate tier: **Light**)
- Plan:
  - [x] Tidy stale M1 status lines (M1 ACCEPTED)
  - [x] `vault/links.py` (wikilinks + aliases, rename rewrite), `vault/parsers.py` (MD/TXT, PDF via pypdf, CSV/XLSX summary rows)
  - [x] `vault/manager.py` (frontmatter, safe paths, CRUD, rename-safe link updates, backlinks `.index/links.json`)
  - [x] `engine/chunking.py` (parent ~1000 / child ~250 tokens; tiktoken `cl100k_base` with offline fallback)
  - [x] `engine/embeddings.py` (Ollama `nomic-embed-text` + fake), `engine/vector_store.py` (Qdrant REST + in-memory)
  - [x] `engine/hybrid_rag.py` (BM25 via rank-bm25 + dense, RRF k=60, parent chunks with citations)
  - [x] `vault/watcher.py` (watchfiles re-index), sample Northwind vault notes, startup wiring
  - [x] REST `/api/vault/*`, `/api/search` + tests (fake embeddings, in-memory store)
  - [x] Wrap-up: checks, self-review, HANDOVER (Windows checklist incl. Notepad edit), PR, CI

## Current state
**M2 is complete** (PR awaiting the founder's Light gate). M0 and M1 behaviour is unchanged (all M1 tests pass).

### Vault and search (M2)
- **Vault** (`app/vault/manager.py`): `vault/<ws>/` with `profile/ notes/ decisions/ journal/ sources/`. API paths are
  POSIX and relative (`notes/pricing-strategy.md`). `resolve()` rejects `..`, absolute or drive paths, hidden
  segments (`.index`, `.obsidian`), Windows device names (`CON`, `AUX`...) and characters Windows forbids. Writes are
  atomic (hidden temp file + `os.replace`). Only `.md`/`.txt` can be written through the API; PDF/CSV/XLSX come in by
  upload. A PUT with only `frontmatter` (or only `body`) keeps the other part of the note.
- **Links** (`links.py`): `[[Note]]`, `[[Note|alias]]`, `[[Note#Heading]]`, `[[folder/Note]]`, `[[file.pdf]]`, embeds;
  links in code are ignored. Resolution is Obsidian-like (case-insensitive name, then path, then frontmatter
  `aliases`; with duplicate names the linking note's own folder wins). The graph (outgoing, backlinks, unresolved) is
  written to `vault/<ws>/.index/links.json` and rebuilt from the files after every change.
- **Rename** (`POST /api/vault/rename`): moves the file and rewrites every link so that each link still points at
  the same file. Heading and alias parts are kept; links that still resolve (e.g. via an alias) are left alone. It
  also protects links the move would otherwise capture (a same-name note moving into the linking note's folder).
- **Parsers** (`parsers.py`): Markdown (YAML frontmatter, heading paths such as `Pricing strategy > Annual plans`),
  TXT (UTF-8, falls back to Windows-1252 for Notepad "ANSI"), PDF via pypdf (one section per page, `Page N`), and
  CSV/XLSX as summary rows: a shape line, numeric column min/max (computed in code), then `Row N: col=value; ...`
  for the first 200 rows per sheet.
- **Chunking** (`engine/chunking.py`): parents ~1000 tokens and children ~250 tokens, measured with tiktoken
  `cl100k_base`. tiktoken downloads its vocabulary on first use; offline it falls back to an approximate counter.
  Children never cross a heading, so each citation names the exact section. Parents pack small sections together.
- **Embeddings** (`engine/embeddings.py`): `OllamaEmbedder` (`POST /api/embed`, `search_document:`/`search_query:`
  prefixes for nomic) and a deterministic `FakeEmbedder` (tests, `EMBED_PROVIDER=fake`).
- **Vector store** (`engine/vector_store.py`): Qdrant over REST (httpx), using one collection per workspace *and*
  embedding model (`founderos_<ws>_<hash of model>`), so switching models never mixes vectors. Point ids are
  content-addressed (chunk id + hash), so a restart re-embeds only what changed. Without Qdrant (`VECTOR_STORE=auto`)
  vectors live in memory and are re-embedded at each start.
- **Hybrid search** (`engine/hybrid_rag.py`): BM25 over child chunks (rank-bm25 with the Lucene IDF, see Decisions)
  plus cosine similarity, fused with **RRF k=60** (`score = sum 1/(60 + rank)`). A parent scores as its best child.
  Results are parent chunks with `citation {path, heading, chunk_id}` plus `child_id`, `snippet`, `bm25_rank` and
  `dense_rank`. The `folder` filter runs inside the vector store. Modes: `hybrid` (default), `bm25`, `dense`.
- **Degradation (R3)**: with Ollama down, search is BM25 only, `mode: "bm25"`, and `warnings` says why. Chunks that
  are not embedded yet are retried at most every 30 s, triggered by searches. Qdrant down at start means the
  in-memory store is used (`store_note` in status). Qdrant going down later means BM25 with a warning. A file that
  cannot be parsed is listed in `/api/vault/status` `errors` and never stops indexing.
- **Watcher** (`watcher.py`): watchfiles (0.4 s debounce) re-indexes changed files, so edits in Obsidian or Notepad
  are searchable within about 1 s. It ignores hidden folders, Office lock files and unsupported file types, and a
  folder delete or rename triggers a rescan.
- **Startup**: the store, tokenizer and index are built in a worker thread, so the API starts at once. Keyword
  search is ready first, then embedding runs in the background. An empty vault gets the 7 Northwind sample notes
  from `sample_data/vault/` (`AUTO_LOAD_SAMPLE_VAULT=true`).
- **REST**: `GET /api/vault/status`, `GET /api/vault/notes[?folder=]`, `GET|PUT|DELETE /api/vault/notes/{path}`,
  `POST /api/vault/rename`, `POST /api/vault/upload` (multipart `file` + optional `folder`, default `sources`; size
  limit `MAX_UPLOAD_MB`; 415 for other types), `GET /api/vault/links`, `POST /api/vault/reindex[?full=true]`,
  `GET /api/search?q=&k=&mode=&folder=` and `POST /api/search` (same fields as JSON). Errors: 400 (unsafe path),
  404, 409 (exists / create_only), 413, 415, 422.
- New settings (`.env.example`): `AUTO_LOAD_SAMPLE_VAULT`, `VECTOR_STORE` (auto|qdrant|memory), `EMBED_PROVIDER`
  (ollama|fake), `TOKENIZER` (tiktoken|approx), `VAULT_WATCH`, `VAULT_WATCH_POLLING`. New dependencies: pyyaml, pypdf,
  tiktoken, rank-bm25, watchfiles (already installed by uvicorn[standard]).

Known issues / notes (M2):
- Every change rebuilds the BM25 index and the link graph over the whole vault, and stats every file. This is fine
  for hundreds of notes; a vault with tens of thousands of notes would need an incremental BM25 (later, if needed).
- Dense search always returns the nearest chunks, even for unrelated queries; there is no similarity cut-off because
  it depends on the model. BM25 only returns chunks that contain a query word.
- With the in-memory store (no Qdrant), the whole vault is re-embedded at every start (seconds for the sample vault).
- Scanned PDFs have no text layer (no OCR); they are listed under `file_warnings` in status.
- Live-checked on the founder's PC during the session with Qdrant running and Ollama not running: BM25 fallback with
  a warning, and the watcher picked up a file written from outside the app.

### Financial engine (M1)
What works:
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

## Next steps (for the M3a session)
0. **Gate check:** M2 is a **Light** gate. The founder runs the M2 checklist and merges the PR; act on any
   "Founder feedback" first.
1. M3a (PRD §4, F3, §8): `app/llm/` provider interface `complete(messages, tools, json_schema, stream)` + `embed()`
   with Ollama / Gemini / ClaudeAgentSDK / Anthropic / Fake providers, routing table and fallback to Ollama (R2/R3).
   Consider making `engine/embeddings.OllamaEmbedder` delegate to the new `OllamaProvider.embed` (keep the
   `Embedder` protocol so the vault code does not change).
2. Decision-model interface (`app/decision/`: LLM + Fake + decision log), agent registry, LangGraph graph
   (Planner → `Send` fan-out → Verifier), concurrency caps (2 local / 6 cloud), team-approval policy `cloud_only`.
3. Agent event protocol over SSE (`/api/events`) and `/api/chat` (streaming).
4. Core agents: Advisor, Planner, Financial Analyst (tools = M1 metric routines + guarded SQL + decision-science and
   calibration routines), **Librarian** (tools = `HybridIndex.search` with citations, `VaultManager.read_note`,
   writes to `decisions/` and `journal/`), Verifier (checks every number against lineage and every claim against a
   citation). Prompts go in `app/agents/prompts/*.md`; model IDs come from config.
5. Tests with fakes only (FakeProvider scripted responses, FakeEmbedder, in-memory store).

## Windows verification checklist (for the founder)
**M2 (Light tier, about 10 min).** In PowerShell, from `D:\Founder-OS`: `git fetch origin`, then
`git checkout claude/m2-vault-search`, then run `setup.bat` once (it installs the new packages pypdf, tiktoken and
rank-bm25), then `run.bat`. Every command below works in Windows PowerShell 5.1 and PowerShell 7. Optional for steps
4–5: Docker Desktop (Qdrant) and Ollama with `nomic-embed-text` (setup pulls it). Without them, search is keyword-only
and says so. When done, merge the PR, or write the issues under "Founder feedback".

1. **Start-up log.** On the first start the backend window shows `Copied 7 sample notes into ...\vault\default`,
   then `Vault indexed: 7 files, 20 chunks`, then `Watching vault ... for changes`. Expected: these 3 lines.
2. **Status.** `Invoke-RestMethod http://127.0.0.1:8000/api/vault/status | Select-Object files, parents, children, tokenizer, vector_store, embedder, watching`
   → files **7**, parents **7**, children **20**, tokenizer `tiktoken:cl100k_base`, vector_store `qdrant` (Docker
   running) or `memory`, embedder `ollama:nomic-embed-text`, watching **True**.
3. **Notes and backlinks.** `(Invoke-RestMethod http://127.0.0.1:8000/api/vault/notes).notes | Format-Table path, title, backlinks -AutoSize`
   → 7 rows. Backlinks: customer-churn **3**, pricing-strategy **3**, company **2**, hire-two-sdrs **2**,
   journal **1**, board-update **1**, competitor-pricing.csv **0**.
4. **Keyword search with citations** (works without Ollama).
   `(Invoke-RestMethod http://127.0.0.1:8000/api/search -Body @{q='annual prepayment discount'; mode='bm25'; k=3}).results | Format-Table rank, path, heading -AutoSize`
   → 1 `notes/pricing-strategy.md` `Pricing strategy > Annual plans`; 2 `sources/board-update-2026-q3.md`
   `Board update, Q3 2026 > Asks of the board`; 3 `journal/2026-10-28.md`.
   `(Invoke-RestMethod http://127.0.0.1:8000/api/search -Body @{q='Fabrikam Enterprise dedicated support'; mode='bm25'; k=1}).results[0].citation`
   → path `sources/competitor-pricing.csv`, heading `Sheet competitor-pricing`, chunk_id `sources/competitor-pricing.csv#p0`
   (the CSV is searchable).
5. **Hybrid search and fallback** (needs Ollama running).
   `$r = Invoke-RestMethod http://127.0.0.1:8000/api/search -Body @{q='why are logistics customers churning'; k=3}; $r.mode; $r.warnings; $r.results | Format-Table rank, path, heading, bm25_rank, dense_rank -AutoSize`
   → mode **hybrid**, no warnings, and `notes/customer-churn.md` in the top 3 (status `embedded` = **20**).
   Then quit Ollama (tray icon → Quit) and run the same line → mode **bm25** and a warning `semantic search
   unavailable (...); using keyword search (BM25) only`. Start Ollama again, wait 30 s, and run it twice → **hybrid**.
6. **Edit a note in Notepad: search picks it up.**
   `notepad .\vault\default\notes\pricing-strategy.md`. Add this line at the end, save (Ctrl+S), close:
   `Flamingo bundle: test pricing for the Growth tier. See [[board-update-2026-q3]].` Then (within a few seconds):
   `(Invoke-RestMethod http://127.0.0.1:8000/api/search -Body @{q='flamingo bundle'; mode='bm25'}).results[0] | Select-Object path, heading`
   → `notes/pricing-strategy.md`, `Pricing strategy > Annual plans`. The new link counts too:
   `(Invoke-RestMethod http://127.0.0.1:8000/api/vault/notes/sources/board-update-2026-q3.md).backlinks`
   → `notes/pricing-strategy.md` and `profile/company.md` (it was only company before).
7. **Create a note through the API.**
   `Invoke-RestMethod -Method Put -Uri http://127.0.0.1:8000/api/vault/notes/notes/dubai-office.md -ContentType 'application/json' -Body '{"content": "# Dubai office\nShould we open a [[Northwind]] office in Dubai?"}' | Select-Object title, @{n='link';e={$_.links[0].resolved}}`
   → title `Dubai office`, link `profile/company.md` (resolved through the alias). The file is in `vault\default\notes\`.
8. **Rename keeps links working.**
   `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/vault/rename -ContentType 'application/json' -Body '{"from_path": "notes/customer-churn.md", "to_path": "notes/churn-review.md"}'`
   → updated_files `journal/2026-10-28.md, notes/pricing-strategy.md, profile/company.md`, links_rewritten **3**.
   `Select-String -Path .\vault\default\journal\2026-10-28.md -Pattern 'churn-review'` → the line now shows
   `[[churn-review]]`. Rename it back the same way (swap the two paths) → the same 3 files.
9. **Upload a PDF.** With any text PDF on the PC (for example a page printed with "Microsoft Print to PDF"):
   `curl.exe -F "file=@C:\path\to\your.pdf" http://127.0.0.1:8000/api/vault/upload` → `{"path":"sources/your.pdf",...,"error":null}`.
   Searching a distinctive word from that PDF returns `sources/your.pdf` with heading `Page 1` (or the page it is on).
   A `.exe` gives HTTP 415.
10. **Path safety.** `try { Invoke-RestMethod "http://127.0.0.1:8000/api/vault/notes/..%2F..%2F.env" } catch { $_.Exception.Response.StatusCode.value__ }`
    → **400**. `try { Invoke-RestMethod -Method Put -Uri http://127.0.0.1:8000/api/vault/notes/CON.md -ContentType 'application/json' -Body '{"content":"x"}' } catch { $_.Exception.Response.StatusCode.value__ }`
    → **400**.
11. **Link index on disk.** `(Get-Content .\vault\default\.index\links.json -Raw | ConvertFrom-Json).unresolved`
    → empty (no broken links in the sample vault).
12. **Regression (M1).** `(Invoke-RestMethod http://127.0.0.1:8000/api/metrics/runway).value` → **10.65**; the page at
    http://127.0.0.1:3000 still loads with the health strip.

To start again with a fresh demo vault: stop `run.bat`, delete `vault\default`, and start again.

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
- **Resolved (2026-11-03, PR #4; re-test: checklist steps R1–R8):**
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
- 2026-11-03 (M2 session, 13:29 to ~14:15 UTC, local on the founder's PC): vault manager, links, parsers, chunking,
  embeddings, Qdrant/in-memory stores, hybrid RAG with RRF, watcher, `/api/vault/*` and `/api/search`, sample vault.
  Tests found an in-memory payload bug and the BM25 negative-IDF problem (both fixed). The self-review
  (`/code-review high`) found 10 issues, all fixed with regression tests: vectors were not tied to the embedding model,
  a parser exception could stop indexing, an empty snapshot could wipe stored vectors, a vector-sync race, a
  frontmatter-only PUT erased the body, rename could capture unrelated links, the folder filter ran after the vector
  top-N, `status()` was not locked, image saves triggered rescans, and startup blocked on Qdrant/tiktoken.
  327 backend tests.
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

## Decisions made (M2 session)
- Vault code lives in `app/vault/` (manager, links, parsers, watcher, service); retrieval lives in `app/engine/`
  (chunking, embeddings, vector_store, hybrid_rag), as in the PRD §10 layout.
- Qdrant is used over its REST API with httpx (no `qdrant-client` dependency); tests run against a fake Qdrant
  server (`httpx.MockTransport`). There is one collection per workspace and embedding model.
- BM25 uses the **Lucene IDF** `log(1 + (N - n + 0.5)/(n + 0.5))` instead of rank-bm25's classic IDF. The classic IDF
  goes negative for words found in more than half the notes, so in a small vault notes that plainly contain the
  query word disappeared from keyword results (found during the session; regression test added).
- tiktoken `cl100k_base` counts tokens; when its vocabulary cannot be downloaded (offline first run), an approximate
  counter is used, so the app never needs the network.
- Children never cross a heading, so citations are section-precise. Parents still pack small sections (~1000 tokens).
- Sample vault notes ship in `sample_data/vault/` and are copied into an empty vault at startup
  (`AUTO_LOAD_SAMPLE_VAULT`). They are hand-written narrative; the financial engine stays the source of every number.

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
