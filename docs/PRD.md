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

### F3 Agent swarm (`backend/agents/`, LangGraph)
| Agent | Job | Output |
|---|---|---|
| Orchestrator | Socratic dialogue, intent classification, dispatch, ≤3-sentence replies, pre-mortems, never blindly agrees | spoken/text reply + dispatch plan |
| Financial | maps question → metric routine / scenario / guarded SQL; builds sensitivity tables | `metric_card`, `scenario`, `table` artifacts w/ lineage |
| Risk / Devil's advocate | downside scenarios, key-person dependency, execution blockers, pre-mortem | `risk_register` artifact |
| Memory | RAG context for other agents; writes decision memos to `vault/<ws>/decisions/YYYY-MM-DD-<slug>.md` with context, options, rejected alternatives, assumptions, metrics (+lineage), review date (+30d) | `decision_memo` artifact |
| Scout | market/web synthesis (Gemini w/ search grounding when available), structured chart JSON | `chart`, `insight` artifacts |

- Artifacts are typed (Pydantic) and streamed over SSE: `metric_card | scenario | priority_matrix | risk_register | decision_memo | chart | table | citation`.
- Prompts live in `backend/agents/prompts/*.md` (editable without code changes).

### F4 Canvas UI (`frontend/`)
- Layout: left = conversation (text input + voice controller + transcript); right = canvas grid of artifact cards; top = workspace/data status, Local/Cloud badge.
- **Scenario Simulator:** sliders (price, churn, CAC, hires, spend) → `/api/scenario` → Recharts base vs scenario cash line with zero-cash marker and a coloured "danger band"; debounced ≤150 ms.
- **Prioritisation Matrix:** 2×2 bubble chart (Bottom-line Value × Execution Feasibility, bubble = cost); drag to adjust scores; initiatives persisted in vault.
- **Decision Memo:** rendered Markdown, edit-in-place, export `.md` and `.pdf` (browser print-to-PDF stylesheet; no server PDF dependency).
- **Lineage popover** on every number: SQL, source file, rows, formula.
- Data panel: upload files, see ingested tables and mappings; Vault browser with backlinks.
- Settings: deep provider, cloud allowed (on/off), voice mode (push-to-talk / full-duplex), voice choice.
- Dark "executive" theme, keyboard accessible, works at 1280px+ (desktop app first).

### F5 Voice advisor (`backend/voice/`) — built **last**
- Browser captures 16 kHz mono PCM (AudioWorklet) → `/ws/voice`.
- Silero VAD (ONNX), 30 ms frames; end-of-utterance after 400 ms silence (configurable).
- faster-whisper `small.en` (cuda/float16, fallback cpu/int8).
- LLM reply streamed token-wise; **sentence-chunked** into Kokoro-82M ONNX TTS; 24 kHz PCM chunks back to browser.
- **Barge-in:** speech detected while TTS playing → server sends `interrupt`, cancels LLM+TTS tasks, client flushes audio buffer within 100 ms.
- Modes: push-to-talk and full-duplex. Waveform visualiser + "listening / thinking / speaking / interrupted" states.
- **Latency targets (honest):** first audio byte after end-of-speech p50 **≤ 900 ms**, stretch goal 500 ms. Metrics logged per turn and shown in a debug overlay.

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
| **M1** | Financial spine | Ingestion + column mapping, all §F1 routines with Lineage, scenario engine (<200 ms), sensitivity, SQL guard, REST endpoints (`/api/data/*`, `/api/metrics/*`, `/api/scenario`), golden tests. |
| **M2** | Vault & hybrid RAG | Vault manager (frontmatter, wikilinks, backlinks, watcher), parsers, parent-child chunking, Qdrant + in-memory fallback, BM25, RRF, `/api/vault/*`, `/api/search`, tests with fake embeddings. |
| **M3** | LLM layer & agents (text) | Provider interface + Ollama/Gemini/ClaudeAgentSDK/Anthropic/Fake, routing + fallback, LangGraph graph, 5 agents, prompts, artifacts over SSE, `/api/chat` (streaming), decision memo writing, tests with FakeProvider. |
| **M4** | Canvas UI | Chat panel, artifact cards, Scenario Simulator, Prioritisation Matrix, Decision Memo (MD/PDF export), lineage popovers, data & vault panels, settings; Playwright smoke test against backend with FakeProvider. **First demoable build.** |
| **M5** | Voice | WS audio pipeline, VAD, STT, Kokoro streaming TTS, barge-in, PTT/full-duplex, latency metrics; tests with WAV fixtures and fake STT/TTS; CPU fallback. |
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
├── docs/ PRD.md  GOAL_PROMPT.md  reference/
├── scripts/ generate_demo_data.py  download_models.py
├── sample_data/            # generated Northwind CSV/XLSX
├── backend/
│   ├── pyproject.toml (or requirements.txt + requirements-dev.txt)
│   ├── app/ main.py  config.py  deps.py  events.py (SSE bus)
│   │   ├── api/   health.py data.py metrics.py scenario.py chat.py vault.py voice_ws.py
│   │   ├── llm/   base.py ollama.py gemini.py claude_sdk.py anthropic_api.py fake.py router.py
│   │   ├── agents/ graph.py orchestrator.py financial.py risk.py memory.py scout.py prompts/
│   │   ├── engine/ duckdb_engine.py metrics.py scenario.py sql_guard.py lineage.py ingest.py hybrid_rag.py chunking.py
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
