# FounderOS

A local-first decision copilot for business owners. It combines a Socratic voice advisor, a deterministic
DuckDB financial engine, an Obsidian-style Markdown brain with hybrid RAG, and a live visual canvas.

**Status:** M0 to M5 are done (financial engine, vault and search, agents, canvas UI, voice). M6 (Windows packaging,
polish and the demo) is in progress; see [`HANDOVER.md`](HANDOVER.md).

- Product spec: [`docs/PRD.md`](docs/PRD.md) · 10-minute demo: [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)
- How to run a dev session with Claude Code: [`docs/GOAL_PROMPT.md`](docs/GOAL_PROMPT.md)

## Fresh install on Windows 11

### 1. Install these first
| What | Version | Needed for | Without it |
|---|---|---|---|
| [Python](https://www.python.org/downloads/) | **3.12** (or 3.11) | the backend | setup stops and says so |
| [Node.js](https://nodejs.org/) | **22 LTS** (or 20.19+) | the web app | setup stops and says so |
| [Git](https://git-scm.com/download/win) | any | cloning the repo | |
| [Ollama](https://ollama.com/download) | 0.3 or newer | the local LLM (`qwen3:8b`) and embeddings | agents answer from rules only |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | any | Qdrant (vector search) | search runs in memory |
| An NVIDIA GPU with a recent driver | 8 GB VRAM or more (12 GB tested) | fast LLM and speech recognition | slower, CPU speech recognition |

Ollama can be the native app or a Docker container (for example one shared with an n8n stack). FounderOS talks to it
over HTTP at `OLLAMA_BASE_URL` (default `http://localhost:11434`), so the `ollama` command does not need to be on PATH.

`setup.bat` picks `py -3.12`, then `py -3.11`, then `python`. Python 3.13+ starts, but setup warns because some
ML/voice packages may not ship wheels for it.

### 2. Clone and run
```powershell
git clone https://github.com/Sree1959GIT/Founder-OS.git
cd Founder-OS
.\run.bat
```
On a fresh clone `run.bat` runs `setup.bat` first (10 to 30 minutes, once; most of it is the model download). Then it
starts Qdrant, the backend on http://127.0.0.1:8000 and the web app on http://127.0.0.1:3000, and opens the browser.
Close the two server windows ("FounderOS backend", "FounderOS frontend") to stop it.

What `setup.bat` does (safe to run again; it skips what is done):
1. Checks Python and Node, copies `.env.example` to `.env` (once), creates `.venv` and installs the backend
   (`backend[dev,gpu,voice]`) and the frontend (`npm ci`).
2. Starts the Qdrant container (`docker compose up -d qdrant`) when Docker Desktop is running.
3. Downloads the models with `scripts\download_models.py`: `qwen3:8b` (about 5.2 GB) and `nomic-embed-text` (0.3 GB)
   through Ollama's HTTP API, Whisper `small.en` and `base.en`, and Kokoro-82M with its voices (about 0.9 GB) into
   `data\models`.
4. Prints a preflight: one line per service, OK or MISSING with what to do.

What `run.bat` checks every time:
- **Ports 8000 and 3000.** If one is taken it stops and names the process (PID, name and command line), says when it
  is an old FounderOS backend, and prints `Stop-Process -Id <PID>`. An old backend would otherwise answer with old code.
- **Docker** installed and running; the Qdrant container.
- **Preflight:** Ollama answering at `OLLAMA_BASE_URL` and its models pulled, Qdrant, the voice models. Missing pieces
  are named with the command that fixes them; FounderOS starts anyway.
- It waits for `/api/health` (up to 90 s) before opening the browser.

### 3. Models
```powershell
.venv\Scripts\python.exe scripts\download_models.py            # everything that is missing
.venv\Scripts\python.exe scripts\download_models.py --check    # only report
.venv\Scripts\python.exe scripts\download_models.py --no-voice # Ollama models only
```
The model names come from `.env` (`OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `FAST_LANE_MODEL`, `VOICE_STT_MODEL`,
`VOICE_TTS_MODEL`). With Ollama in Docker you can also pull by hand: `docker exec ollama ollama pull qwen3:8b`.

### 4. Reset to the clean demo
```powershell
.\reset_demo.bat          # asks first; --yes to skip the question, --settings to reset Settings too
```
With FounderOS closed, it moves `vault\default\` and `data\default\` to `data\backups\reset-<time>-default\` (nothing
is deleted: test memos, uploads, the DuckDB file and the logs all go there), and restores the shipped Northwind notes
from `sample_data\vault\`. The next start reloads the Northwind financials. Your Settings are kept.

### Troubleshooting
| Problem | Fix |
|---|---|
| "Port 8000 is already in use by an old FounderOS backend" | Close that window or run the `Stop-Process -Id <PID>` it prints, then `.\run.bat` |
| "Ollama is not answering at http://localhost:11434" | Start the Ollama app, or `docker start ollama`; if it runs elsewhere set `OLLAMA_BASE_URL` in `.env` |
| "Ollama models not pulled" | `.venv\Scripts\python.exe scripts\download_models.py --no-voice` |
| "Docker Desktop is not running" | Start it and run `.\run.bat` again (search works in memory meanwhile) |
| Voice stays off | `scripts\download_models.py --no-ollama`; allow the microphone in the browser |
| Speech recognition is slow | No CUDA: it falls back to `base.en` on the CPU. Update the NVIDIA driver |
| The first answer takes 30 s or more | The model was cold (loaded on first use). Later answers are fast |
| `npm ci` fails | Node is older than 20.19: install Node 22 LTS, delete `frontend\node_modules`, run `setup.bat` |
| Python 3.13+ warning | Install Python 3.12, delete `.venv`, run `setup.bat` |

### VRAM and latency (measured on the founder's RTX 4080 Laptop, 12 GB)
- `qwen3:8b` about 5.9 GB, Whisper `small.en` +0.5 to 0.7 GB, `nomic-embed-text` 0.3 GB; total about 7.4 GB of 12 GB.
  Kokoro runs on the CPU. Avoid a second chat model on the GPU: a reload of qwen3:8b takes minutes.
- First spoken words p50 about 0.9 s; a spoken metric answer p50 about 1.7 s; barge-in pauses speech in about 70 ms
  and stops it after about 1 s of the founder's speech (`VOICE_BARGE_IN_MS`). Measure on your PC with
  `scripts\voice_bench.py`.

## Linux / macOS (development)
```bash
./setup.sh
./run.sh
```

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

## Agents and chat API (M3a)
Ask a question in plain English. The **Planner** reads the intent (by rules, or with the decision model when the
message is ambiguous) and proposes a team. The **Financial Analyst** (metric routines, scenarios, Monte Carlo, guarded
SQL) and the **Librarian** (vault search with citations) run in parallel through LangGraph, at most 2 local agents
at a time. The **Verifier** checks every number against the tool results and every cited path against the search
results. It sends a failing answer back once, then flags it. The **Advisor** answers in at most 3 sentences and
ends with a probing question.

| Endpoint | What it does |
|---|---|
| `POST /api/chat` `{"message": "...", "stream": true}` | Server-Sent Events: agent events, then `delta` (Advisor text), then `done` (the full result) |
| `POST /api/chat` `{"message": "...", "stream": false}` | One JSON result: `answer`, `metrics` (each with full `lineage`), `citations` (only the sources the answers name), `past_decisions` (decisions already on record for this topic), `decision_impact` (for a hire or spending change: cost per hire, added monthly cost and runway change, computed in code), `verified`, `issues`, `timings_ms` |
| `GET /api/events?run_id=&since=` | Live agent events (SSE) for the Agent Activity panel: `team.proposed`, `agent.status`, `agent.step`, ... |
| `GET /api/runs/{id}` · `POST /api/runs/{id}/approve` · `/cancel` | A run's result and events; approve or reject a proposed team; cancel |
| `POST /api/runs/{id}/agents/{agent_id}/cancel` · `/rerun` `{"brief": "..."}` | Cancel one agent (the team goes on), or re-run it with an edited brief: restarted in place while running, a new run once the run has finished |
| `POST /api/conversation/turn` `{"session_id": null, "text": "..."}` | One founder turn. Idle: starts a run. During a run: classified as backchannel, status, amendment, new question or stop, without disturbing the run |
| `GET /api/conversation/{session}` · `POST .../quiet` · `.../amendments/{id}` · `.../queue/{id}` | The lane's state; quiet mode; accept or decline an amendment; accept or drop the offered queued question |
| `GET /api/agents` | Agent types, tools, privacy class, the provider each one uses now, this month's calls, cost and latency per type, and the monthly cloud spend and cap |

Models: chat `OLLAMA_CHAT_MODEL` (default `qwen3:8b`, thinking off) on the local Ollama. With `CLOUD_ALLOWED=true` and
a key in `.env`, deep-work agents can use Anthropic (API key), Google Gemini (AI Studio or Vertex key), OpenAI or an
OpenAI-compatible endpoint (OpenRouter, DeepSeek and so on), chosen per agent type with `AGENT_MODELS`. A Claude Free,
Pro or Max subscription cannot be used: Anthropic allows those credentials only in its own apps. Every cloud payload
goes through a privacy filter (no raw financial rows). Calls past `CLOUD_MONTHLY_CAP_USD` (default 25), or to a model
with no known price, run locally. Cloud failures fall back to Ollama, and teams with a cloud agent wait for approval
(`TEAM_APPROVAL=cloud_only`). Small typed choices (intent routing) go through the decision
model and are logged to `data/<workspace>/decision_log.jsonl`. Without Ollama, agents answer from rules (the metric
routine or vault search), and say so.

## Development

```bash
cd backend && pytest -q && ruff check .. && ruff format --check ..
cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build
```

CI runs the same checks on every pull request (the backend on both Linux and Windows).

### Dev-only setting: `FOUNDEROS_STAGE_DELAY_S`
A pause, in seconds, before each stage of an agent team (default `0`, maximum `120`). It is for live tests only: with
the team's stages slowed down you can say something while a chosen stage runs (the Advisor panel shows
"Step N of M: <agent> working…", then "Verifying…", then "Done"). It is not a secret and is not in `.env.example`;
set it for one PowerShell session before `.\run.bat`:

```powershell
$env:FOUNDEROS_STAGE_DELAY_S = "8"; .\run.bat
```

Close that window (or `Remove-Item Env:FOUNDEROS_STAGE_DELAY_S`) to go back to normal speed.
`scripts/voice_scenarios.py` sets it to 2 for its own backend.

