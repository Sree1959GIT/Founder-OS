# FounderOS

A local-first decision copilot for business owners. It combines a Socratic voice advisor, a deterministic
DuckDB financial engine, an Obsidian-style Markdown brain with hybrid RAG, and a live visual canvas.

**Status:** milestone M2 (vault and hybrid search). The backend loads CSV/XLSX financials into DuckDB and serves
deterministic metrics (every number with its lineage), what-if scenarios, sensitivity tables and Monte Carlo
runs over a REST API. It also keeps an Obsidian-compatible Markdown vault with wikilinks and backlinks, and
searches it (plus PDFs and spreadsheets) with hybrid keyword + semantic retrieval and citations. Features arrive
milestone by milestone; see [`HANDOVER.md`](HANDOVER.md).

- Product spec: [`docs/PRD.md`](docs/PRD.md)
- How to run a dev session with Claude Code: [`docs/GOAL_PROMPT.md`](docs/GOAL_PROMPT.md)
- Current state and next steps: [`HANDOVER.md`](HANDOVER.md)

## Requirements
- Python 3.12 (recommended) or 3.11. Newer versions (3.13+) start, but setup warns because later ML/voice
  packages (milestones M2–M5) may not ship wheels for them yet. `setup.bat` picks `py -3.12`, then `py -3.11`, then
  `python`.
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

## Financial engine API (M1)
On first start an empty workspace is loaded with the Northwind demo data (`AUTO_LOAD_SAMPLE_DATA=true`). Browse and
try every endpoint at http://127.0.0.1:8000/docs.

| Endpoint | What it does |
|---|---|
| `GET /api/data/tables` | Loaded tables (source file, rows, column mapping) and the canonical schema |
| `POST /api/data/upload` | Upload a CSV/XLSX; columns are mapped by header synonyms (optional `table` form field) |
| `POST /api/data/load-sample` | Reload the Northwind demo data |
| `GET /api/data/mappings` | Saved column mappings (`data/<workspace>/mappings.json`, editable) |
| `POST /api/data/query` | One read-only `SELECT` over the loaded tables (SQL guard) |
| `GET /api/metrics` · `/api/metrics/summary` · `/api/metrics/{name}` | Metric routines (`?month=YYYY-MM&window=N`) |
| `GET /api/metrics/cash-projection` | Base-case 12-month cash projection (`?growth_mode=trend\|none\|flat`) |
| `POST /api/metrics/kill-criteria` | Evaluate kill criteria against live metrics |
| `POST /api/scenario` · `/sensitivity` · `/montecarlo` | What-if projection, 2-variable grid, seeded Monte Carlo |

Every number comes back with a `lineage` object: the SQL that ran, the source file and row numbers (which match the
Excel rows), the formula and the intermediate inputs. Metric definitions are documented at the top of
`backend/app/engine/metrics.py`.

There are two runways, and the API labels them differently:
- **Runway (actual burn)** (`/api/metrics/runway`) is closing cash divided by the trailing 3-month net burn from the
  bank sheet. It makes no growth assumptions.
- **Projected runway (with growth assumptions)** (`base_runway_months` / `scenario_runway_months`) comes from the
  projection. `growth_mode` sets the growth assumption:
  - `trend` (default): new customers keep arriving at the measured acquisition cost.
  - `none`: no new customers.
  - `flat`: today's run-rate.

  Projection responses list every driver under `assumptions`, each with its own lineage. They also include a
  `reconciliation`, which explains the step from the actual-burn runway to the projected one.

## Vault and search API (M2)
The vault is a folder of Markdown notes, `vault/<workspace>/` (`profile/`, `notes/`, `decisions/`, `journal/`,
`sources/`). You can open it as an Obsidian vault or edit the files in any editor: a file watcher re-indexes changes
within about a second. On first start an empty vault gets the Northwind sample notes (`AUTO_LOAD_SAMPLE_VAULT=true`).

| Endpoint | What it does |
|---|---|
| `GET /api/search?q=...&k=5&mode=hybrid\|bm25\|dense&folder=` (or `POST` with JSON) | Hybrid search; returns passages with citations `{path, heading, chunk_id}` |
| `GET /api/vault/status` | Index size, embedder and vector store in use, files that failed to parse |
| `GET /api/vault/notes` · `GET\|PUT\|DELETE /api/vault/notes/{path}` | List, read (frontmatter, links, backlinks), write `.md`/`.txt`, delete |
| `POST /api/vault/rename` | Move a file and rewrite every `[[link]]` to it |
| `POST /api/vault/upload` | Add a PDF, CSV, XLSX, MD or TXT (default folder `sources/`) |
| `GET /api/vault/links` · `POST /api/vault/reindex` | Link graph (also in `.index/links.json`); manual rescan |

How search works: files are split into ~1000-token passages and ~250-token pieces. Pieces are scored by keyword
search (BM25) and by meaning (Ollama `nomic-embed-text` vectors in Qdrant, or in memory without Docker). The two
rankings are merged with Reciprocal Rank Fusion. Without Ollama, search falls back to keywords and says so in
`warnings`.

## Development

```bash
cd backend && pytest -q && ruff check .. && ruff format --check ..
cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build
```

CI runs the same checks on every pull request (the backend on both Linux and Windows).

Full Windows setup, troubleshooting and the stakeholder demo script are added in milestone M6.
