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
  boundaries clean (one `workspace_id` threaded through storage paths and DB files), and Claude is reached with an
  **API key** only (see §12, 2026-11-04).

---

## 2. Target environment

| Item | Value |
|---|---|
| OS | Windows 11 (native Python + Node), Docker Desktop for **Qdrant only** |
| CPU / RAM / GPU | Core i9 · 64 GB · 12 GB VRAM (RTX 3060/4070 class) |
| Local LLM | **Ollama as an external service** at `OLLAMA_BASE_URL` (on the founder's PC: the `ollama` Docker container with GPU, shared with an n8n stack; the native app works too) — chat `qwen3:8b` (thinking off), embeddings `nomic-embed-text` |
| Python | 3.11+ (venv in `.venv`) |
| Node | 20 LTS+ |

**VRAM budget (12 GB, shared with other apps' Ollama models, so `/api/health` shows VRAM in use per model):** Qwen3 8B Q4 at 8k context ~5.8 GB · faster-whisper small.en FP16 + Silero VAD ~1.5 GB ·
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
        │                    llm/ providers: Ollama | Claude API | Gemini | OpenAI(-compat.)│
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
| `AnthropicAPIProvider` | deep-work agents, web search | `ANTHROPIC_API_KEY`. A subscription token (`CLAUDE_CODE_OAUTH_TOKEN`) is not allowed outside Anthropic's own apps. |
| `GeminiProvider` | deep-work agents, web search | `GEMINI_API_KEY` (AI Studio) or `VERTEX_API_KEY` (Vertex express) |
| `OpenAICompatibleProvider` | deep-work agents | `OPENAI_API_KEY`, or `OPENAI_COMPATIBLE_API_KEY` + `OPENAI_COMPATIBLE_BASE_URL` (OpenRouter, DeepSeek and so on) |
| `FakeProvider` | tests | scripted responses |

- Each agent type has a privacy class in its registry entry. `cloud_allowed` and `cloud` types use the type's choice in
  `AGENT_MODELS` (`{"market_scout": "gemini:gemini-3.8-flash"}`), else `DEEP_PROVIDER` (`anthropic` | `gemini` | `openai` |
  `openai_compatible` | `ollama`), with automatic fallback to Ollama. Cloud is off by default.
- Every cloud payload goes through a deterministic privacy filter (no raw financial rows). Each call's cost and latency is
  recorded, a monthly cap sends further calls to Ollama, and `/api/agents` shows both.
- Cloud calls are multi-second; never used in the real-time voice path. Results arrive on the canvas
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
- LLM reply streamed token-wise; **sentence-chunked** into Kokoro-82M ONNX TTS; 24 kHz PCM chunks back to browser. *(Changed 2026-11-13, §12 "how the Advisor speaks": the voice says a short code-built summary with rounded numbers and offers more; it does not read the answer aloud. Round 2, same day: one opening turn, then silence while the team works, then findings, outcome and an offer.)*
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
  - `JevProvider`: TypeSafe AI's Jev, a paid cloud model. Optional, and off unless `CLOUD_ALLOWED=true`. Receives only non-sensitive routing state (an allow-list, privacy-filtered, numbers masked), never financial rows.
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
├── scripts/ generate_demo_data.py  download_models.py  eval_decision_models.py  finetune_laya.py  eval_labelled.py  tune_prompts.py  bakeoff_providers.py  bakeoff_embeddings.py
├── sample_data/            # generated Northwind CSV/XLSX
├── backend/
│   ├── pyproject.toml (or requirements.txt + requirements-dev.txt)
│   ├── app/ main.py  config.py  deps.py  events.py (SSE bus)
│   │   ├── api/   health.py data.py metrics.py scenario.py chat.py vault.py voice_ws.py
│   │   ├── llm/   base.py ollama.py cloud.py costs.py privacy.py fake.py router.py
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
| Cloud costs run away, or raw data reaches a provider | Monthly cap with fallback to Ollama; privacy filter on every payload; team approval for cloud agents |
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
| 2026-11-03 | M1: burn = operating burn (financing excluded), 3-month trailing default for burn/runway; loading a file replaces its table (all-or-nothing); DuckDB external access disabled on every connection; scenario = DuckDB-measured drivers + deterministic NumPy recurrence shared with sensitivity and Monte Carlo; empty workspaces auto-load the demo data. |
| 2026-11-03 | M1 founder feedback: two named runways, **"Runway (actual burn)"** (metric) and **"Projected runway (with growth assumptions)"** (projection). The projection takes `growth_mode` trend (default) / none / flat. It returns every driver as an assumption with lineage, plus a reconciliation with the metric (tolerance: 5 % of the metric runway). |
| 2026-11-03 | M2: vault code in `app/vault/` (manager, links, parsers, watcher), retrieval in `app/engine/` (chunking, embeddings, vector_store, hybrid_rag). Qdrant via REST/httpx, one collection per workspace and embedding model, in-memory fallback. BM25 uses the Lucene IDF (always positive) so small vaults rank correctly. tiktoken with an offline approximate fallback. Child chunks never cross a heading (section-precise citations). Sample notes in `sample_data/vault/` seed an empty vault. |
| 2026-11-03 | Founder decision (M3a): **Ollama is an external service** at `OLLAMA_BASE_URL`. On the founder's PC it is the `ollama` Docker container (port 11434, GPU), shared with the n8n stack, replacing "native Ollama app" in §2. `setup.bat`/`setup.sh` detect it over HTTP (`/api/version`, `/api/tags`), pull with the `ollama` CLI when present, and otherwise print `docker exec ollama ollama pull <model>`. The GPU is shared, so health shows VRAM per loaded model. |
| 2026-11-03 | Founder decision (M3a): the chat model changes from `qwen2.5:7b-instruct-q4_K_M` (manifests fail to pull with EOF) to **`qwen3:8b`**, with Qwen3 thinking **off** (`think: false`, `OLLAMA_THINK`) for fast replies and clean JSON/tool calls. Tool calling was verified live. The EmbeddingGemma vs `nomic-embed-text` comparison is deferred to M3c. |
| 2026-11-03 | M3a: providers in `app/llm/` (`base`, `ollama`, `cloud` = Anthropic API + Gemini over REST/httpx + Claude Agent SDK imported lazily, `fake`, `router`); no `anthropic`/`google-genai` packages needed. Agents in `app/agents/` (registry, prompts, tools, runtime, verifier, graph, events). The Verifier is deterministic code: numbers must match what the model was shown from tools (1 % rounding), and Librarian paths must be returned citations. Intent routing tries rules first, then the decision model. Every agent falls back to rules when the LLM is down (R3). The chat model is preloaded at startup. |
| 2026-11-04 | M3a founder review: past decisions are surfaced by code. Notes under `decisions/` have a `DecisionRecord` (status, dates, prediction, kill criteria), and frontmatter is indexed. The Librarian gets a code-run decision lookup and whole-vault search before the model's first turn, and any fact the answer omits is added by code. `citations` lists only sources the answer names (`retrieved` keeps the rest). BM25 gains a light stemmer. Eval: `scripts/eval_vault.py` (offline in CI, `--live` on Windows). |
| 2026-11-04 | M3a founder review: a figure must keep its meaning. Tool numbers are `Fact`s (label, unit, quantity, flow or balance); the deterministic Verifier also checks the claim around each figure. A failing sentence is sent back once, then replaced by a code-written one and left unverified; the Advisor's reply is checked per sentence, so it streams per sentence. Counted hires get a code-run scenario and a code-computed `decision_impact` in `/api/chat`. The cost per hire is the company's average, labelled as such. |
| 2026-11-04 | **Correction, founder decision (M3b): no Claude subscription path.** Anthropic does not allow Claude Free, Pro or Max OAuth tokens outside Claude Code and Claude.ai, including in Agent SDK apps (re-checked 2026-11-04: code.claude.com/docs/en/agent-sdk/overview and /legal-and-compliance). Replaces the 2026-11-02 row. Claude is reached with an API key. New provider-agnostic cloud layer: per-agent-type choice among Anthropic, Gemini (AI Studio or Vertex), OpenAI and an OpenAI-compatible endpoint; keys only in `.env`, never logged. Kept: cloud off by default, privacy filter on every payload, team approval, automatic fallback to Ollama. Added: per-call cost and latency, a monthly cost cap (default $25), both in `/api/agents`. **Google ADK is not adopted**; LangGraph stays. The M3c bake-off compares providers on accuracy, latency and cost per answer. |
| 2026-11-04 | **Founder decision (M3b): two lanes (F3/F5).** A fast conversation lane (small local model; narrates real agent events, asks an assumption question, recaps; never states an unverified number; quiet mode) beside the inference lane (agents + Verifier + one repair turn). Mid-run turns are classified as backchannel, answerable now, amendment, new question or stop: amendments offer cancel-and-re-run with the edited request, new questions queue first in, first out and are offered after delivery. Three contexts: global (workspace), run (snapshot frozen at start), local (session window). M3b builds the backend; M4 the text UI; M5 the voice, and M5 must test GPU sharing (Ollama parallelism, or CPU/Laya for the fast lane). |
| 2026-11-04 | M3b: a team runs in **stages** fixed in the registry (data, then specialists, then Devil's Advocate, then Memo Writer), not model-written `depends_on`: a small planning model does not get dependencies right, and a fixed order is testable. Each stage sees earlier findings, and the Verifier accepts earlier stages' numbers. The founder's words add specialists by rule on top of the Planner's choice. The Memo Writer's prose goes through the Verifier; code writes the file, metrics with lineage, review date (+30 days) and predictions. A memo is `proposed`: the founder decides. A figure with no lineage is removed from a memo, not just flagged. |
| 2026-11-05 | M3b founder review: every decision gets a **decision frame in code, before the agents**: type (`hire`, `new_office`, `pricing`, `spend`, `fundraise`, `new_product`, `other`; `new_product` added beyond the founder's list), a one-off plus recurring cost model at low/base/high through `run_scenario` (new `one_off_cost`), costed options, and a goal check against `profile/company.md`. Inputs not in the data are founder-editable placeholders, labelled "assumption, confirm", not market data, and a memo resting on them is never `verified`. Memo structure is enforced in code: one proposed option, outcome predictions, measurable stop rules, "Open numbers to confirm" in place of removed figures. |
| 2026-11-05 | M3c: a sentence may never contradict the frame's goal statuses (`guards.goal_contradiction`, checked against the option chosen); a cheaper option not proposed always states a reason (`OptionCost.trade_off`). Customer, person and company names are pseudonymised before any cloud use and restored on the PC; the call stays local if the name list cannot be built. `DECISION_PROVIDER` gains `laya` and `jev`, with the LLM as fallback; Jev also needs `CLOUD_ALLOWED=true`. Prompt versions live in `prompts/versions/`, tuned offline only. No default changed in M3c. |
| 2026-11-06 | M3c fix (founder's C4 finding): `agents/sources.py` removes, in code, any sentence naming a source that is not a real vault file or a page a search returned, and any figure not backed by a routine, the passages of the file it is cited to, or the founder's message, including inside a question. Later stages, the answer and the memo never see it. `Open numbers to confirm` now lists what to confirm with no figure in it, which replaces the M3b rule that moved the figure there. A forecast's or stop rule's own target stays, as a target. With cloud off, the Market Scout keeps only sentences citing a retrieved passage and lists what to find. Spans of days or weeks are not financial figures. |
| 2026-11-06 | **M4:** a single-metric question takes a code-written fast path (optional one short LLM question, 4 s timeout), verified as usual. UI settings are saved in `<data>/<workspace>/ui_settings.json` and win over `.env`; keys stay in `.env`. Matrix data lives in the vault (`notes/priorities.md`). `issues` and `agent.step` are audit trail: the UI shows counts and sanitised steps only. Ollama models moved to a Docker named volume at the founder's request. |
| 2026-11-08 | **M5 voice:** faster-whisper `small.en` `int8_float16` on CUDA (0.52 GB measured on the founder's RTX 4080 Laptop next to qwen3:8b at 5.86 GiB), `base.en` int8 on CPU as the fallback; Silero VAD v6 ONNX as bundled in faster-whisper (no torch), 512-sample frames; Kokoro-82M ONNX on CPU with clause streaming; rules-first barge-in/backchannel with the decision model for unclear words; the conversation lane never speaks a figure; quiet silences all speech; a run's text is broadcast to the canvas and the voice. Measured: first word p50 0.93 s, metric answer p50 3.8 s, barge-in pause 65 ms. |
| 2026-11-08 | **Licence points for "sell later" (voice, checked 2026-11-08 on PyPI and the model cards; not legal advice):** faster-whisper 1.2.1 **MIT**; CTranslate2 4.8 **MIT**; Whisper weights (Systran conversions of OpenAI Whisper) **MIT**; Silero VAD **MIT** (the `silero-vad` package README badge says CC BY-NC 4.0, but its licence file and classifier are MIT; we use the copy bundled in MIT faster-whisper); onnxruntime 1.31 **MIT**; PyAV **BSD-3-Clause** (it ships FFmpeg libraries, LGPL); Kokoro-82M weights **Apache-2.0**; kokoro-onnx 0.6.1 **MIT**; the `fastrtc/kokoro-onnx` mirror **MIT**. **But kokoro-onnx depends on `phonemizer` (GPL-3.0-or-later) and `espeakng-loader`, which ships espeak-ng (GPL-3.0).** Selling a product that bundles them means GPL duties (source for the whole combined work, or keeping them as a separate, user-installed component), or swapping the phonemizer for a permissive G2P (for example misaki's English lexicon) before selling. NVIDIA CUDA wheels (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) are under NVIDIA's own licence: redistribution follows the CUDA EULA. Decide before M6 packaging if an installer is to bundle them. |
| 2026-11-08 | **Founder notes 60–63, 55, 7 (M5 first task):** a held-back team never runs and is never narrated as done; "vs." never ends a sentence; "as you asked" only for a real amendment; a one-metric lookup needs no team approval; Devil's Advocate prompt v3 (live tuner); a code-written Monte Carlo cash-out warning at `CASH_RISK_WARN_AT` (0.5). |
| 2026-11-13 | **Founder design decision (M5 review): how the Advisor speaks.** Replaces "LLM reply … sentence-chunked into TTS" in F5: the on-screen answer is never read aloud. **A.** A team run starts with one or two sentences on who is on the team and each one's focus; no running commentary of every step. **B.** One short line a stage on what its agents produced, then the outcome. Spoken numbers are rounded and colloquial, made **by code from the verified figure, never by the model** ("around 10 thousand dollars", "about 1.8 million dollars", "about ten and a half months", "about four in five"); exact figures and lineage stay on screen. The normaliser covers money, percent, months and dates, and says INR in lakh and crore. **C.** Not a non-stop speaker: the outcome and the one thing that matters, two or three sentences, then a pause and an offer of more ("Want me to go through the risks?"). **D.** Follow-ups use the conversation: the open decision, earlier questions and the first sentences of earlier answers go to the Advisor with the next run; "and what about churn?" is answered as that metric and "why that option?" from the open decision's own frame. **E.** An agent can be re-run by voice or text ("re-run the analyst, assume three hires", "redo the Devil's Advocate") through the existing re-run and amendment paths; the Advisor then carries on as before. Code: `app/voice/spoken.py`, `app/voice/session.py`, `app/conversation/manager.py`. |
| 2026-11-13 | **M5 fix (founder's V7 finding): the founder has the floor.** Nothing new is played while the founder is speaking or while their words are being understood; a pause made for older speech is never resumed over newer speech; speech with no words made out is answered with "Sorry, I didn't catch that." instead of silence. **Echo gate (`VOICE_ECHO_GATE`, default 0.3):** while FounderOS plays audio, sound below that share of the founder's own speech level is its own echo, not speech. Measured with the real engines and a simulated echo at 8 % of the playback level: 20 self-made pauses and several invented turns without the gate, none with it. |
| 2026-11-13 | **Founder decisions for M6 (no code yet):** **F.** Expandable left and right panels, and a collapsible left panel. **G.** A movable pop-up agent window with a graphical view of each agent's work, replacing trips to the Activity tab (time-boxed). **Kokoro licence point:** `phonemizer` and espeak-ng are GPL-3.0 (row of 2026-11-08); to be decided before selling. **TTS latency:** the metric answer is 3.8 s against a target of about 3 s, with Kokoro on the CPU; to be worked on in M6. |
| 2026-11-13 | **Founder decisions for after v1 (v1.1, no code yet):** **H.** A geopolitical analyst agent (it needs web or cloud to be useful). **I.** Dynamic agent selection or creation from context. **J.** A draft planner and risk analyser that feeds risks back to the team, with the Devil's Advocate at each stage. |
| 2026-11-13 | **Founder design decision (M5 re-test, round 2): voice during a team run. This replaces A and B's "one short line a stage" in the row above.** **R4.** The voice speaks ONE opening turn ("I've put together a team of six: the Librarian, Market Scout, Financial Analyst, People and Ops, Regulatory and Tax and a Devil's Advocate. They're looking at the Dubai office from different angles so the decision holds up."), after a short "On it.". Then it is silent while the team works: no line per agent or stage, no Verifier line, no figure, no assumption question; all of that stays on screen. At most one "Still working on it." if the run passes about 30 s (`VOICE_STILL_WORKING_S`). When the run is done: the team's two or three key findings (the full model's cost and runway effect, a goal it moves away from, the cash warning, what is unverified or assumed; all built by code, numbers rounded by code), then the outcome (the proposal and its main trade-off). **R5.** The spoken summary always ends with an offer ("Want me to go through the risks?") and then stops; a listening noise that cut the summary short brings the offer back. Spoken risks are statements only, never a question. |
| 2026-11-13 | **M5 re-test, round 2: what stops a team, and what is confirmed first.** **R1.** A listening noise or one stray word ("Ugh!", "mm", "hmm", "right", "okay") while a team runs is a backchannel, decided by rules; a decision model's guess can no longer stop a team. Stop takes an explicit word (stop, cancel, halt, hold it, abort, never mind, forget it) **and a yes**: "Stop the team? Say yes to stop.", typed or spoken. `VOICE_BARGE_IN_MS` default is now 1000 (was 600), so a noise of up to about a second can resume the voice; the pause itself is still immediate. **R3.** A number whose unit is in doubt in a change to a decision ("2%" where the decision counts people and has no percentage, or "two" with no unit) is asked about before it is applied ("Did you mean two people?"); yes applies it at once. **R8.** "Yes" (or "restart") answers "Restart with your change?", typed or spoken, and the canvas follows the restarted run. Re-running one agent after the answer runs only that agent; the rest of the team's findings are kept and the Advisor writes the answer again. The exception: a re-run that changes the decision's inputs ("assume three hires") is an amendment, so the whole team runs again, and the reply says so. |
| 2026-11-13 | **M5 re-test, round 2: transcription (R6).** faster-whisper is given a FounderOS vocabulary (`initial_prompt` and `hotwords`: agent names, metric names, Dubai, hires, runway, churn; `VOICE_STT_VOCABULARY`). Code repairs a command's opening where the mishearing is not a sentence ("should be open" to "should we open", "Freerun the" to "Re-run the"). A turn Whisper is less sure of than `VOICE_CONFIRM_BELOW` (0.45) is read back before it is acted on ("Did you say: ...?"). **No LLM correction pass** (not needed for these, and it would add a model call to every turn). **Measured on the founder's PC with qwen3:8b loaded** (`scripts/stt_bakeoff.py`, 48 synthetic clips): `large-v3-turbo` fits (+1.07 GB of VRAM against +0.52 GB for `small.en`; about 7.5 of 12 GB in use) and is no slower (p50 about 190 ms against 211 ms). On synthetic speech the two are equally accurate, so the test does not show which is better on a real microphone. **`small.en` stays the default; `large-v3-turbo` is offered as a setting for the founder to try (open question).** |
| 2026-11-13 | **M5 re-test, round 2: a proposed memo on record gets one question (R7).** With a proposed memo on record, the only question in the answer is code's: "what has changed since you drafted it?". The Advisor is told to add none, and code removes any other question (about a target, a forecast or a kill criterion) and any second mention of the memo. |
| 2026-11-14 | **Founder decisions (M5 re-test, round 3), answering the open questions of round 2.** `small.en` stays the default STT model and `large-v3-turbo` stays an option (`VOICE_STT_MODEL`). Barge-in stays at 1 s (`VOICE_BARGE_IN_MS=1000`). **A typed "stop" stops the team at once, with no confirmation; a spoken "stop" is still confirmed ("Stop the team? Say yes to stop."); the Cancel button stays immediate.** This replaces "typed or spoken" in R1 of the row of 2026-11-13. "On it." is still said before the opening turn. The read-back threshold stays at 0.45 (`VOICE_CONFIRM_BELOW`). Headphones or a headset give the best voice results. |
| 2026-11-14 | **M5 re-test, round 3: what the voice never does.** **S1.** A run the founder stopped is never summarised or spoken: stopping clears the lines waiting to be said, nothing of that run's answer is said later, and a run whose stop landed too late to interrupt its last step is still ended as cancelled, with no answer on screen. **S2.** Each offer ("Want me to go through the risks?") is said once; only an offer that a barge-in dropped before it was said may be said afterwards. **S3.** After an offer the voice waits for the founder. Silence never continues it; nor do its own words heard back through the microphone (words it said in the last 20 s, heard while it plays or within 1 s after), nor an "okay" the recogniser was less sure of than `VOICE_CONFIRM_BELOW`. The echo gate stays on for 0.3 s after the last audio. **S4.** A change said while the team works is offered in the same words as after the answer ("That changes the decision. Restart with your change?"), on screen and aloud. If it is still unanswered when the answer is ready, the offer stays open and is asked again ("You asked for a change while the team worked, and this answer does not have it. Restart with it?") in place of the offer of more. A change, a question or a stop that the lane's rules recognise is never left to a model's guess, and three words or more are never dropped as a listening noise. |
| 2026-11-14 | **M5 re-test, round 3: one telling per topic, and a memo's own date (S5).** The last pass over an answer drops a second sentence about the same goal even when its figures differ (the exception: the first only named the goal and the second is the first to say which way the decision moves it). With a proposed memo on record, a sentence that tells the memo again without the word "memo" ("You already proposed …", "your earlier proposal") is dropped like any second mention. A sentence about a memo or decision on record never states a date the record does not have: not as the date it was written (only the record's own date, by year or in full), and no other full date (such as a review date) that the record does not state. |

### Proposals from the M3c bake-offs (decided by the founder on 2026-11-06)
**Approved 2026-11-06:** P1, P2, P3, P4, P6 and P7 as written, with no default changed. P5 is approved and applied (`people_ops` v2 is live). Laya fine-tuning (checklist C8) and Jev (C9) are deferred until after M5. The `embeddinggemma` model may be removed from the founder's Ollama container (`docker exec ollama ollama rm embeddinggemma`); that is left to the founder.

Measured on the founder's PC on 2026-11-05: one run, Ollama in Docker, sample data. Figures are in `HANDOVER.md`; re-run them with the Windows checklist.

| # | Proposal | Evidence | Your decision |
|---|---|---|---|
| P1 | **Decision provider: keep `llm` (`qwen3:8b`) behind the rules.** Do not move to Laya or Jev yet. | Rules first, then the model, on the held-out split: intent 94.3 %, team 100 %, turn 85.7 %, and 0 ms whenever the rules answer. Laya and Jev were **not measured**: the install was refused in the session, and there is no Jev key. Stock Laya is documented as near chance until fine-tuned. Run checklist C8 and C9, then decide. | Approved 2026-11-06 |
| P2 | **Turn classifier: keep rules first, and treat the model's answer as weak.** Do not widen what the model decides here. | Alone, all three local models scored 52–57 % on turn kinds, and `qwen3:8b` is overconfident there (ECE 0.429). The rules are 100 % right on the 76 % of turns they answer, which lifts the real path to 85.7 %. This is the best case for fine-tuning Laya. | Approved 2026-11-06 |
| P3 | **Agent models: keep `qwen3:8b` for every agent type.** | It passed or tied on every type. `phi4-mini` tied on the Financial Analyst (3/3, 4.6 s against 7.8 s) on only 3 questions, and a second model on a shared 12 GB GPU risks a reload of about 3.5 minutes. It failed the Devil's Advocate 0/3. `mistral` was slower and needed more repairs. Local cost is $0. No cloud row: no cloud call was made. | Approved 2026-11-06 |
| P4 | **Conversation lane: `FAST_LANE_MODEL=qwen3:8b`, or stay on templates.** Not `phi4-mini`. | `qwen3:8b` 5/5 good replies, 5/5 within 4 s, p50 2.92 s, and it is already loaded. `mistral` 5/5, p50 3.20 s, but needs its own GPU memory. `phi4-mini`, the small candidate, gave 4/5 (one reply stated a figure) and only 2/5 in time. Measured with a free GPU: under agent load it still queues (M5 must test this). A truly fast lane needs the Ollama overhead fixed first (Open question 1). | Approved 2026-11-06 |
| P5 | **Prompts: apply `people_ops` v2** (`python scripts/tune_prompts.py --agents people_ops --apply`). Keep the live `devils_advocate`, `regulatory_tax` and `librarian`. | People & Ops v1 passed 0/5 and v2 5/5. The other agents' live versions already pass every case, and a challenger must beat them by a whole case. | Approved and applied 2026-11-06 |
| P6 | **Embeddings: keep `nomic-embed-text`.** | Hybrid search, which the app uses: MRR 0.940 for both models, recall@3 100 % for both. Dense only: EmbeddingGemma 0.938 against 0.887. VRAM 0.30 GB against 0.63 GB, and it is already the indexed model. | Approved 2026-11-06 |
| P7 | **Licence point for "sell later":** `nomic-embed-text` is Apache-2.0. EmbeddingGemma is under the **Gemma Terms of Use**, not an open-source licence: you must pass its use restrictions on in your agreements, give recipients a copy of the terms, ship the notice file ("Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms"), mark modified files, and follow the prohibited use policy. Google may restrict use it believes breaches the terms, and ending the licence means deleting your copies. It claims no rights in outputs. Bundling it adds these duties to any product you sell; `nomic-embed-text` does not. Not legal advice. | ai.google.dev/gemma/terms, read 2026-11-05. | Approved 2026-11-06 |
