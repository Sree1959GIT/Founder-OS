# FounderOS — Product Requirements Document (v2.0)

> Status: **Agreed baseline** (2026-11-02). Supersedes `docs/reference/original_blueprint.md`.
> Any change to scope or stack must be recorded in §12 (Decision Log) and in `HANDOVER.md`.

---

## 1. Vision

FounderOS is a **local-first decision copilot for business owners**. A founder talks (or types) to an
"Executive Advisor" that challenges their thinking Socratically, tests ideas against the company's **real
numbers** (computed deterministically, never by an LLM), remembers everything in an Obsidian-style
Markdown vault, and shows its reasoning on a live visual canvas.

### Problems solved
1. **Ideas vs. financial reality** — test an idea against real P&L/cash/pipeline data without building a model by hand.
2. **LLM math hallucination** — every number comes from DuckDB SQL with a visible audit trail.
3. **Data sovereignty** — P&L, payroll, customers and journals stay on the founder's PC by default.
4. **Cognitive overload** — the advisor speaks in 2–3 sentences and points at the canvas.

### Who it is for
- **Now:** a single founder (the owner of this repo), on one Windows 11 workstation, no login.
- **Later (design for, don't build):** sold to other business owners. Code must keep tenant/workspace
  boundaries clean (one `workspace_id` threaded through storage paths and DB files), and the Claude adapter must
  support an **API key** as well as a personal subscription token.

---

## 2. Target environment

| Item | Value |
|---|---|
| OS | Windows 11 (native Python + Node), Docker Desktop for **Qdrant only** |
| CPU / RAM / GPU | Core i9 · 64 GB · 12 GB VRAM (RTX 3060/4070 class) |
| Local LLM | **Ollama native Windows app** (GPU direct) — `qwen2.5:7b-instruct-q4_K_M`, embeddings `nomic-embed-text` |
| Python | 3.11+ (venv in `.venv`) |
| Node | 20 LTS+ |

**VRAM budget (12 GB):** Qwen 7B Q4 ~5.5 GB · faster-whisper small.en FP16 + Silero VAD ~1.5 GB ·
Kokoro-82M ONNX ~1 GB · headroom ~4 GB. All models must also run on CPU (slower) so the app never hard-fails.

**Development reality:** the build runs in a cloud Linux container **without GPU, Ollama, Docker or Windows**.
Therefore every external dependency (LLM, embeddings, Qdrant, STT, TTS) sits behind an interface with a
**fake/in-memory implementation** used by tests. Real-hardware verification is done by the founder on the PC
using the per-milestone checklist in `HANDOVER.md`.

---

## 3. Architecture

```
            Browser (React + Vite + Tailwind + shadcn/ui + Recharts)
              │  WebSocket /ws/voice (PCM audio, barge-in)   ▲ SSE /api/events (canvas artifacts)
              ▼  REST /api/* (chat, upload, scenario, vault)  │
        ┌──────────────────── FastAPI gateway (Python 3.11, asyncio) ────────────────────┐
        │  voice/            agents/ (LangGraph)                engine/                  │
        │  VAD·STT·TTS       orchestrator · financial · risk    duckdb_engine (+lineage) │
        │  barge-in          memory · scout                     scenario · hybrid_rag    │
        │                    llm/ providers: Ollama | Gemini | Claude(Agent SDK / API)   │
        └───────────────┬──────────────────────────────┬────────────────────────────────┘
                        ▼                              ▼
              ./data/<workspace>/founder.duckdb    ./vault/<workspace>/*.md  +  Qdrant :6333  +  BM25 (in-proc)
```

### Key rules
- **R1 Deterministic math.** LLMs never produce a financial number. They pick a pre-built metric routine
  (tool call) or, as a fallback, emit SQL that is validated (read-only, single SELECT, table allow-list,
  row/time limits) and run by DuckDB. Every number shown or spoken carries a `Lineage` object
  `{metric, sql, source_files, source_rows/range, formula, computed_at}`.
- **R2 Privacy routing.** Financial rows and vault content are sent to a cloud model **only** for agents
  marked "deep work" *and* only when cloud is enabled in Settings. Default = local only.
- **R3 Never crash on missing services.** No Gemini/Claude credentials → Ollama. No Ollama → clear UI error +
  rule-based fallbacks where possible. No Qdrant → BM25-only retrieval with a warning. No GPU → CPU.
- **R4 Voice never blocks canvas.** Canvas updates stream over SSE independently of the audio WebSocket.

---

## 4. LLM provider layer (`backend/llm/`)

One interface: `async complete(messages, tools=None, json_schema=None, stream=False)` + `embed(texts)`.

| Provider | Use | Auth |
|---|---|---|
| `OllamaProvider` (default) | orchestrator, voice turns, SQL generation, embeddings | none (localhost:11434) |
| `ClaudeAgentSDKProvider` | deep-work agents | **Claude subscription** via `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) using the `claude-agent-sdk` Python package (requires Claude Code CLI installed). Personal use only. |
| `AnthropicAPIProvider` | same as above, for the future commercial product | `ANTHROPIC_API_KEY` |
| `GeminiProvider` | deep-work agents, web/market intelligence, multimodal (PDF/image) | `GEMINI_API_KEY` (`google-genai` SDK) |
| `FakeProvider` | tests | scripted responses |

- Routing table in `config.py`: `AGENT_PROVIDERS = {orchestrator: ollama, financial: ollama, risk: deep, memo: deep, scout: deep}`;
  `deep` resolves to `DEEP_PROVIDER` env (`claude_sdk` | `anthropic` | `gemini` | `ollama`) with automatic fallback to Ollama.
- Claude Agent SDK calls are multi-second; never used in the real-time voice path. Results arrive on the canvas
  and the advisor says e.g. *"The risk review just landed on the right."*
- Model IDs come from `.env`, never hard-coded in agent code (defaults: latest Claude Sonnet/Opus, `gemini-2.5-flash`).

---

## 5. Features

### F1 Deterministic financial spine (`backend/engine/duckdb_engine.py`, `scenario.py`)
- Ingest CSV/XLSX: P&L, cash/bank balance, customers/subscriptions, sales pipeline, marketing spend, headcount.
- Canonical schema + **column-mapping** layer (auto-detect by header synonyms; mapping saved per file in
  `data/<ws>/mappings.json`) so real files can be added later.
- Pre-built routines (each returns value + Lineage): monthly burn (gross/net), runway (months + zero-cash date),
  MRR/ARR, revenue growth, gross margin, CAC (blended & by channel), LTV, LTV:CAC, payback, logo & revenue churn,
  NRR, headcount cost, 12-month cash-flow projection.
- **Scenario engine:** inputs (price Δ%, churn Δ, CAC Δ, new hires, spend change, start month) → recomputed
  12-month projection via DuckDB in **< 200 ms** for slider use. Base vs scenario series + delta.
- Sensitivity table (2 variables × 5 steps) for the financial agent.
- **Monte Carlo** (`engine/montecarlo.py`, NumPy, seeded): distributions on the scenario drivers (e.g. churn, price, CAC,
  win-rate) → P10/P50/P90 cash path, runway range and probability that cash hits zero within 12 months. Must complete
  1,000 runs in under 1 s.
- **Decision-science routines** (deterministic code; the LLM only elicits the inputs): weighted scoring / MCDA
  (founder-set weights → priority matrix), expected value and simple decision trees (including "pilot first"
  staged options), kill criteria, and **calibration tracking** (memos store probabilistic predictions; the 30-day
  review records outcomes; a Brier score is tracked per founder and per agent).
- **Synthetic demo company** generator (`scripts/generate_demo_data.py`, seeded, deterministic): fictional
  B2B SaaS "Northwind Analytics", 24 months, ~₹/$ selectable currency, ~150 customers, pipeline, 3 channels,
  ~25 staff. Ships in `sample_data/` and is the basis of golden-number tests.

### F2 Knowledge brain (`backend/vault_manager.py`, `engine/hybrid_rag.py`)
- `./vault/<ws>/` Markdown with YAML frontmatter; folders `profile/`, `notes/`, `decisions/`, `journal/`, `sources/`.
- `[[wikilink]]` + `[[link|alias]]` parsing, backlink index (`.index/links.json`), rename-safe updates,
  file-watcher re-index (watchfiles). Human edits in Obsidian must be picked up.
- Ingestion of PDF (pypdf), CSV/XLSX (summary rows), MD/TXT.
- Parent–child chunking (parent ≈1000 tokens, child ≈250, tiktoken `cl100k_base` approximation), children embedded.
- Dense: Qdrant collection per workspace, `nomic-embed-text` (768-d). Sparse: `rank-bm25`. **RRF (k=60)** fusion,
  return parent chunks with citations `{path, heading, chunk_id}`.

### F3 Agent swarm (`backend/app/agents/`, LangGraph): fixed types, dynamic instances

**Design principle.** Agent **types** are fixed in code. Each type has a vetted prompt, an allow-list of tools, a
privacy class (local-only or cloud-allowed) and a cost class. For each decision, the **Planner** dynamically
decides which types to run, how many **instances** of each, and the **brief** for each instance. Instances run in
parallel through the LangGraph `Send` fan-out, limited by concurrency caps (default: 2 local and 6 cloud at once, set in
Settings; any extra instances queue). Nothing is spawned that isn't a registered type, which keeps math
deterministic, privacy routing enforceable and the system testable.

**Core agents (always on):**
| Agent | Job | Runs on |
|---|---|---|
| **Advisor** (voice/text persona) | Socratic dialogue in replies of 3 sentences or fewer. Never blindly agrees. Narrates what the swarm is doing ("Three analysts are on it; the runway chart is updating") | Local |
| **Planner** | Classifies the decision (type, reversibility: one-way vs two-way door) and decomposes it into a task graph. Proposes the team: which agent types, how many instances, the briefs and dependencies | Local |
| **Financial Analyst** | The **only** agent that can call metric routines, scenarios, Monte Carlo and guarded SQL. Its outputs carry `Lineage` | Local |
| **Librarian** | Hybrid RAG over the vault and past decisions; supplies context packs to other agents | Local |
| **Verifier** | Rejects any artifact containing a number without lineage or a claim without a citation, and sends it back to the agent once before flagging it | Local |

**Specialist agents (spawned on demand, multiple instances allowed):**
| Agent | Job | Runs on |
|---|---|---|
| **Devil's Advocate** | Pre-mortem ("it failed after 6 months; why?"), red-team, downside scenarios | Cloud allowed |
| **Market Scout** | Market size, competitors, local conditions; one instance per market or competitor. Uses web search grounding when cloud is allowed | Cloud |
| **Revenue & Customer** | Pricing, churn, pipeline, segment value (requests numbers from the Financial Analyst) | Local |
| **People & Ops** | Hiring, capacity, key-person dependency, execution plan | Cloud allowed |
| **Regulatory & Tax** | Flags compliance and tax considerations to verify. Not legal advice | Cloud |
| **Prioritiser** | Runs the weighted-scoring routine (F1) for the 2×2 matrix. Weights are elicited from the founder | Local |
| **Memo Writer** | Writes decision memos to `vault/<ws>/decisions/YYYY-MM-DD-<slug>.md`: context, options, rejected alternatives, assumptions, metrics (with lineage), predictions (for calibration), kill criteria, review date (+30d) | Cloud allowed |
| **Perspective lens** (template) | One-off viewpoints the Planner can instantiate, e.g. "Investor", "Largest customer", "Competitor CEO". Prompt-only: **no data tools, no web access** | Cloud allowed |

"Cloud allowed" agents run locally when cloud is disabled in Settings or no cloud provider is configured. Data
sent to cloud agents is filtered by the privacy classifier (F7): raw financial rows are never sent, only
summarised metrics with lineage IDs.

**Team approval:** the Planner's proposed team is shown in the Agent Activity panel. If any instance would use a
cloud provider, the founder must approve (approve / edit briefs / add / remove). Local-only teams start
immediately. This is configurable in Settings: `always` / `cloud_only` (default) / `never`.

**Agent event protocol** (SSE, typed Pydantic): `team.proposed`, `team.approved`, `agent.spawned`,
`agent.status` (`queued | thinking | querying_data | searching_vault | searching_web | waiting_cloud | verifying | done | failed | cancelled`),
`agent.step` (human-readable current action, e.g. "running runway_projection()"), `agent.tool_call`,
`agent.artifact`, `agent.done` (elapsed ms, provider, tokens, est. cost). The dashboard can also send
`agent.cancel` and `agent.rerun` (optionally with an edited brief).

- Artifacts are typed (Pydantic) and streamed over SSE: `metric_card | scenario | monte_carlo | priority_matrix | risk_register | decision_memo | chart | table | citation | insight`.
- Prompts live in `backend/app/agents/prompts/*.md` (editable without code changes). The agent registry lives in `agents/registry.py`.
- **After v1:** user-defined permanent agent types (e.g. "My CA's view") created from a Settings screen, also limited to prompt-only plus approved tools.

### F4 Canvas UI (`frontend/`)
- Layout: left = conversation (text input + voice controller + transcript); right = canvas grid of artifact cards; top = workspace/data status, Local/Cloud badge.
- **Scenario Simulator:** sliders (price, churn, CAC, hires, spend) → `/api/scenario` → Recharts base vs scenario cash line with zero-cash marker and a coloured "danger band"; debounced ≤150 ms.
- **Prioritisation Matrix:** 2×2 bubble chart (Bottom-line Value × Execution Feasibility, bubble = cost); drag to adjust scores; initiatives persisted in vault.
- **Decision Memo:** rendered Markdown, edit-in-place, export `.md` and `.pdf` (browser print-to-PDF stylesheet; no server PDF dependency).
- **Lineage popover** on every number: SQL, source file, rows, formula.
- Data panel: upload files, see ingested tables and mappings; Vault browser with backlinks.
- Settings: deep provider, cloud allowed (on/off), voice mode (push-to-talk / full-duplex), voice choice.
- Dark "executive" theme, keyboard accessible, works at 1280px+ (desktop app first).

### F4b Agent Activity panel (dashboard)
- One live card per agent instance, showing: type icon, instance name and brief, status chip, current step, elapsed
  time, a local or cloud badge with provider, tokens/cost, and links to the artifacts it produced. Actions: cancel, re-run, and edit the brief.
- Team proposal view with approve/edit controls, as set by the approval policy.
- Timeline (Gantt-style) view of the run showing parallelism and dependencies.
- Concurrency caps and the approval policy are set in Settings.

### F5 Voice advisor (`backend/voice/`) — built **last**
- Browser captures 16 kHz mono PCM (AudioWorklet) → `/ws/voice`.
- Silero VAD (ONNX), 30 ms frames; end-of-utterance after 400 ms silence (configurable).
- faster-whisper `small.en` (cuda/float16, fallback cpu/int8).
- LLM reply streamed token-wise; **sentence-chunked** into Kokoro-82M ONNX TTS; 24 kHz PCM chunks back to browser.
- **Barge-in:** speech detected while TTS playing → server sends `interrupt`, cancels LLM+TTS tasks, client flushes audio buffer within 100 ms.
- Modes: push-to-talk and full-duplex. Waveform visualiser + "listening / thinking / speaking / interrupted" states.
- **Latency targets (honest):** first audio byte after end-of-speech p50 **≤ 900 ms**, stretch goal 500 ms. Metrics logged per turn and shown in a debug overlay.

### F7 Decision-model layer ("System 1": fast typed choices) (`backend/app/decision/`)
Many micro-decisions per turn are too slow for a 7B LLM (1–2 s each). These use a **decision model** that picks one
of the given options and returns a probability, never free text.

- Interface: `choose(state, question, options) -> Decision(choice, probability, provider, latency_ms)`, plus `score(...)` and `yes_no(...)`.
- Implementations:
  - `LLMDecisionProvider` (Ollama JSON-schema output): the **initial default**.
  - `LayaProvider`: local, open-source Laya (~421M parameters, ~1 GB, Apache-2.0), on GPU or CPU. It becomes the default once it is fine-tuned on our logged examples and beats the LLM in the bake-off.
  - `JevProvider`: TypeSafe AI's Jev, a paid cloud model. Optional. Receives only non-sensitive routing state, never financial rows.
  - `FakeDecisionProvider`: for tests.
- Uses: intent routing; Planner agent-type selection; metric-routine selection; barge-in vs backchannel
  ("uh-huh") detection in voice; privacy classification (may this text go to the cloud?); decision reversibility
  (one-way vs two-way door); Verifier yes/no checks.
- **Not used for:** numbers, open-ended reasoning, memos, or 1–5 ordinal scoring.
- **Confidence fallback:** if the probability is below `DECISION_MIN_CONFIDENCE` (default 0.75), escalate to the LLM, or ask the founder.
- **Data flywheel:** every decision is logged (`data/<ws>/decision_log.jsonl`: state, options, choice, probability, and the eventual correction), which builds the fine-tuning set for Laya.
- **Bake-off harness** (`scripts/eval_decision_models.py`): about 200 labelled routing examples from the Northwind demo, reporting accuracy, calibration and latency per provider. The results pick the default provider.
- Status note: Jev and Laya were both released in autumn 2026, and their published performance figures are vendor-reported. The base Laya model performs near random zero-shot and **requires fine-tuning**. Re-verify APIs and licences when implementing.

### F6 Packaging & demo
- `docker-compose.yml`: Qdrant only (6333/6334, volume `./data/qdrant`).
- `run.bat` (+ `setup.bat`): check Docker/Python/Node/Ollama → create venv → pip install → npm install → `docker compose up -d` → `ollama pull` models → download VAD/Kokoro models → start backend :8000 and frontend :3000 → open browser.
- `README.md` with Windows setup, troubleshooting (GPU, ports, Ollama), and a **10-minute stakeholder demo script** using the Northwind data.

---

## 6. Non-functional requirements
- **Quality:** ruff + mypy (lenient) for Python, ESLint + `tsc --noEmit` for TS. pytest coverage on `engine/` ≥ 85 %.
- **Golden tests:** every financial routine has a test against hand-checked numbers from the seeded demo data.
- **Security:** SQL guard (read-only DuckDB connection for agent SQL), no shell exec, upload size/type limits, CORS restricted to localhost, secrets only in `.env` (git-ignored).
- **Observability:** structured logs (loguru), `/api/health` reports each dependency status, per-turn timing.
- **Portability:** paths via `pathlib`; no Linux-only calls; `.bat` + `.sh` scripts for both OSes.

---

## 7. Out of scope (v1)
Multi-user auth, cloud sync, mobile, accounting-system connectors (Tally/QuickBooks/Xero), Electron/Tauri packaging,
non-English voice. (Logged as "later" in §12.)

---

## 8. Milestones

Each milestone ends with: all tests green, lint clean, commit + push, `HANDOVER.md` updated, Windows checklist written, session **stops**.

| # | Milestone | Definition of Done |
|---|---|---|
| **M0** | Scaffold & foundations | Repo tree, `pyproject`/requirements, FastAPI app with `/api/health`, config via pydantic-settings, Vite+React+TS+Tailwind+shadcn shell, docker-compose (Qdrant), `.env.example`, `setup.bat`/`run.bat` draft + `.sh` equivalents, GitHub Actions CI (pytest, ruff, tsc, build), synthetic data generator + `sample_data/`. |
| **M1** | Financial spine | Ingestion + column mapping, all §F1 routines with Lineage, scenario engine (<200 ms), sensitivity, Monte Carlo, weighted scoring / EV / decision-tree routines, calibration store, SQL guard, REST endpoints (`/api/data/*`, `/api/metrics/*`, `/api/scenario`), golden tests. |
| **M2** | Vault & hybrid RAG | Vault manager (frontmatter, wikilinks, backlinks, watcher), parsers, parent-child chunking, Qdrant + in-memory fallback, BM25, RRF, `/api/vault/*`, `/api/search`, tests with fake embeddings. |
| **M3a** | LLM layer, agent framework & core agents | LLM provider interface (Ollama/Gemini/ClaudeAgentSDK/Anthropic/Fake), routing and fallback; decision-model interface with LLM and Fake providers plus decision logging; agent registry; LangGraph graph with Planner → `Send` fan-out → Verifier; concurrency caps; team-approval policy; agent event protocol over SSE; `/api/chat` (streaming); core agents Advisor, Planner, Financial Analyst, Librarian, Verifier; tests with fakes. |
| **M3b** | Specialist agents | Devil's Advocate, Market Scout, Revenue & Customer, People & Ops, Regulatory & Tax, Prioritiser, Memo Writer (writes memos with predictions and review date), Perspective-lens template; cancel and re-run with edited brief; privacy filter on cloud payloads; tests. |
| **M3c** | Decision models (Laya / Jev) | `LayaProvider`, `JevProvider`, bake-off harness and labelled set; Laya fine-tuning script (runs on founder's PC GPU); provider choice is driven by config and the bake-off results. |
| **M4** | Canvas UI | Implements the **Claude Design mock-ups** (`docs/design/`): conversation panel, canvas artifact cards, **Agent Activity panel** (live cards, team approval, timeline), Scenario Simulator plus Monte Carlo fan chart, Prioritisation Matrix, Decision Memo (MD/PDF export), lineage popovers, data and vault panels, Settings; Playwright smoke test against the backend with fakes. **First demoable build.** |
| **M5** | Voice | WS audio pipeline, VAD, STT, Kokoro streaming TTS, barge-in plus decision-model backchannel detection, PTT/full-duplex, latency metrics; tests with WAV fixtures and fake STT/TTS; CPU fallback. |
| **M6** | Windows packaging, polish & demo | Final `setup.bat`/`run.bat`, model download script, README + demo script, VRAM/latency tuning notes, bug-fix pass from founder's PC feedback. |

---

## 9. Acceptance demo (end of M6)
1. `run.bat` from a fresh clone brings the app up at `http://localhost:3000`.
2. Northwind data is loaded; "What's our runway?" → spoken 2–3 sentence answer + runway card with lineage.
3. "What if we raise prices 10 % and churn goes up 2 points?" → scenario chart updates; sliders tweak it live.
4. "I want to open a Dubai office" → Socratic questions, pre-mortem, risk register, priority matrix entry.
5. "Record the decision" → memo in `vault/default/decisions/`, exportable to PDF.
6. Interrupt the advisor mid-sentence → it stops within ~0.3 s and listens.
7. Unplug the network → everything except Scout/cloud agents still works.

---

## 10. Repository layout (target)
```
founder-os/
├── CLAUDE.md  HANDOVER.md  README.md  .env.example  docker-compose.yml
├── setup.bat run.bat setup.sh run.sh
├── docs/ PRD.md  GOAL_PROMPT.md  design/ (Claude Design link + exported mock-ups)  reference/
├── scripts/ generate_demo_data.py  download_models.py  eval_decision_models.py  finetune_laya.py
├── sample_data/            # generated Northwind CSV/XLSX
├── backend/
│   ├── pyproject.toml (or requirements.txt + requirements-dev.txt)
│   ├── app/ main.py  config.py  deps.py  events.py (SSE bus)
│   │   ├── api/   health.py data.py metrics.py scenario.py chat.py vault.py voice_ws.py
│   │   ├── llm/   base.py ollama.py gemini.py claude_sdk.py anthropic_api.py fake.py router.py
│   │   ├── agents/ registry.py graph.py planner.py advisor.py financial.py librarian.py verifier.py
│   │   │          specialists/ (devils_advocate, market_scout, revenue, people_ops, regulatory, prioritiser, memo_writer, lens) prompts/
│   │   ├── decision/ base.py llm.py laya.py jev.py fake.py log.py
│   │   ├── engine/ duckdb_engine.py metrics.py scenario.py montecarlo.py decision_science.py calibration.py sql_guard.py lineage.py ingest.py hybrid_rag.py chunking.py
│   │   ├── vault/ manager.py links.py watcher.py
│   │   └── voice/ vad.py stt.py tts.py session.py
│   └── tests/ (unit + api, fixtures)
└── frontend/ (Vite React TS, shadcn/ui, Recharts) src/{components,hooks,lib,pages}
```
(The flat layout in the original blueprint is replaced by this package layout; module responsibilities are unchanged.)

---

## 11. Risks
| Risk | Mitigation |
|---|---|
| 500 ms voice latency unrealistic on 7B + Whisper small on a 3060 | Honest 900 ms target, sentence-streaming, warm models, optional `qwen2.5:3b` for voice turns |
| VRAM contention (LLM + STT + TTS) | Kokoro on CPU option; Ollama `keep_alive`; health page shows VRAM |
| No GPU/Ollama in dev container | Fakes + founder's Windows checklist each milestone |
| Claude subscription via Agent SDK not allowed for resale | Separate `AnthropicAPIProvider`; documented in README |
| Windows path/encoding issues | pathlib, UTF-8 everywhere, CI job on `windows-latest` |
| Messy real spreadsheets | Column-mapping layer + mapping UI in M4 |

---

## 12. Decision log
| Date | Decision |
|---|---|
| 2026-11-02 | New dedicated repo `Sree1959GIT/Founder-OS`. |
| 2026-11-02 | Build order text-first, voice last (M0→M6). |
| 2026-11-02 | Pluggable LLM providers: Ollama default; Claude via **Claude Agent SDK on subscription** (+ API-key adapter for future product); Gemini. |
| 2026-11-02 | Cloud models used for "deep work" agents only (risk, memo, scout); orchestrator & SQL stay local. |
| 2026-11-02 | Audience: single user now, sell later → keep `workspace_id` boundaries; no auth in v1. |
| 2026-11-02 | Runtime: native Windows Python/Node + native Ollama; Docker only for Qdrant. |
| 2026-11-02 | Stack locked: LangGraph, Kokoro TTS, Qdrant (Docker, with in-memory fallback), shadcn/ui + Recharts. |
| 2026-11-02 | Demo data: synthetic seeded company "Northwind Analytics". |
| 2026-11-02 | Verification: mocks in cloud dev; founder runs a checklist on Windows at each milestone. |
| 2026-11-02 | Sessions stop at each milestone or ~2 h, whichever first; state lives in `HANDOVER.md`. |
| 2026-11-02 | Agent design: fixed agent **types** (5 core and 8 specialist, including the Perspective-lens template); the Planner spawns **instances** dynamically per decision and runs them in parallel with concurrency caps (2 local, 6 cloud). |
| 2026-11-02 | Team approval policy default `cloud_only`: the founder approves before any cloud agent runs. |
| 2026-11-02 | User-defined custom agent types deferred to after v1. |
| 2026-11-02 | Agent Activity panel on the dashboard showing live status of every agent instance, with cancel and re-run. |
| 2026-11-02 | Decision-model layer (F7): LLM default → **Laya** (local, after fine-tuning) → **Jev** (optional, paid). Chosen by bake-off, with a confidence fallback to the LLM. |
| 2026-11-02 | Decision-science routines added to F1: Monte Carlo, weighted scoring, EV/decision trees, kill criteria, calibration (Brier). |
| 2026-11-02 | M3 split into M3a/M3b/M3c. UI designed first with **Claude Design**; mock-ups in `docs/design/` are the reference for M0 shell and M4. |
| 2026-11-02 | M0: Node 22 LTS recommended (Vite 7 needs Node 20.19+); Tailwind 3 for shadcn/ui; fonts bundled locally (offline-safe); Python venv at repo root `.venv`; uvicorn runs the `create_app` factory. |
| 2026-11-02 | M0: `/api/health` always returns 200; Ollama and storage are "required", Qdrant, cloud and GPU optional. Demo data uses integer-cent maths and is byte-reproducible (CI checks it). |
| 2026-11-03 | Founder answers to M0 questions: shipped demo data stays in **USD**; demo runway stays at **about 10 months**. |
