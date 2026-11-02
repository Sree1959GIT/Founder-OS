# FounderOS: Multi-Agent Decision Intelligence System

## Product Requirements Document (PRD) \& Claude Code Implementation Blueprint

\---

## 1\. Executive Summary \& Vision

**FounderOS** is a local-first, privacy-preserving conversational decision copilot built for business owners, founders, and managing directors. It pairs an interruptible, full-duplex voice executive advisor with an autonomous multi-agent swarm, an Obsidian-style bi-directional knowledge brain, and a deterministic financial analytics engine.

### Core Problems Solved

1. **Unstructured Brainstorming vs. Financial Reality:** Founders generate ideas faster than their teams can evaluate trade-offs. FounderOS tests ideas against real operational numbers without requiring manual modeling.
2. **Hallucination in Business Math:** Traditional LLMs hallucinate calculations. FounderOS enforces a strict deterministic layer (DuckDB/SQL) for all accounting metrics, unit economics, and runway projections.
3. **Data Sovereignty \& Privacy:** Sensitive P\&L statements, payroll, customer churn, and personal founder journals remain on-premise on the user's workstation.
4. **Cognitive Overload:** Instead of outputting walls of text, the voice advisor delivers crisp, 2–3 sentence executive summaries and directs visual attention to an interactive canvas.

\---

## 2\. Target Hardware \& Deployment Environment

* **Host System:** Windows 11 with WSL2 \& Docker Desktop
* **Hardware Profile:** Intel Core i9, 64 GB RAM, 12 GB VRAM (RTX 3060 / 4070 class)
* **VRAM Allocation Budget (12 GB Total):**

  * Local LLM Orchestrator: `qwen2.5:7b-instruct-q4\_K\_M` via Ollama (\~5.5 GB VRAM)
  * Voice STT: `faster-whisper` (`small.en`, FP16) + Silero VAD (\~1.5 GB VRAM)
  * Voice TTS: Piper / Kokoro ONNX streaming (\~1.0 GB VRAM)
  * Headroom: \~4.0 GB free VRAM (prevents OS display paging and driver instability)
* **System RAM Allocation Budget (64 GB Total):**

  * Docker Services (Qdrant, DuckDB, Ollama daemon): 16 GB max limit
  * Hybrid In-Memory Vector \& BM25 Indexes: 4 GB
  * System Free Headroom: \~44 GB

\---

## 3\. Product Requirements \& Feature Specifications

### 3.1 Full-Duplex Socratic Voice Agent ("Executive Advisor")

* **Sub-500ms Turn Latency:** End-to-end voice-to-voice response cycle under 500ms over local WebSockets.
* **Natural Barge-In (Interruption Handling):** Silero VAD detects user speech frames (<30ms). If the user interrupts while the system is speaking, ongoing TTS audio streaming is immediately aborted and buffers are cleared.
* **Anti-Monologue UX:** The voice persona delivers short executive insights (maximum 2–3 sentences) and verbally references the visual UI (e.g., *"Take a look at the orange band on your runway chart"*).
* **Socratic Elicitation \& Pre-Mortems:** The agent questions assumptions rather than agreeing passively (e.g., *"Assume this expansion fails 6 months from now—what caused it?"*).

### 3.2 The Deterministic Financial Spine

* **Zero-Hallucination Math:** The LLM is strictly prohibited from doing mental arithmetic on accounting data.
* **DuckDB Analytical Engine:** Ingests CSV/Excel sheets (P\&L, balance sheets, pipeline metrics) into an embedded DuckDB instance.
* **Automated Audit Lineage:** Every visual metric rendered on the canvas includes an exact SQL trace citation referencing the source file, row, and formula.

### 3.3 Obsidian-Style Bi-Directional Brain \& WeKnora Hybrid RAG

* **Markdown Vault (`/vault`):** All founder notes, business profiles, and recorded decisions are stored as human-editable `.md` files with YAML frontmatter and `\[\[wikilinks]]`.
* **Hybrid Retrieval (Dense + Sparse):**

  * Parent-child hierarchical chunking (Parent: 1000 tokens, Child: 250 tokens).
  * Dense vector search using `nomic-embed-text` indexed in a local Qdrant container.
  * Sparse keyword search using Rank-BM25.
  * Reciprocal Rank Fusion (RRF) to merge keyword and semantic results before feeding agents.

### 3.4 Multi-Agent Roles

1. **Conversational Orchestrator (Ollama / Local):** Manages dialog flow, interrupts, and dispatches sub-tasks.
2. **Context \& Ingestion Agent:** Manages local `/vault` files, founder memory, and past decision logs.
3. **Deterministic Financial Agent:** Executes SQL queries against DuckDB for financial evaluations.
4. **Risk \& Devil's Advocate Agent:** Identifies operational bottlenecks, key-person dependencies, and downside risks.
5. **Multimodal Visual Synthesis Agent (Gemini API):** Handles heavy multimodal rendering, web intelligence, and structured UI chart generation.

### 3.5 Interactive Visual Canvas

* **Dynamic Scenario Simulator:** Interactive sliders for CAC, churn rate, and pricing tiers that instantly recalculate financial runway via DuckDB.
* **Prioritization Matrix (2x2):** Evaluates initiatives across **Bottom-Line Value** vs. **Execution Feasibility**.
* **Decision Memo Generator:** Generates exportable Markdown and PDF summaries capturing context, assumptions, rejected alternatives, and 30-day review dates.

\---

## 4\. End-to-End System Architecture

```
                                  \[FOUNDER]
                               ▲            │
                         Audio │            │ Audio / Text / Sliders
                               │            ▼
                     ┌────────────────────────────────┐
                     │   Browser / Desktop UI         │
                     │   (React + Vite + TailwindCSS) │
                     └───────┬────────────────▲───────┘
            WebSocket Audio  │                │ Server-Sent Events (SSE)
            \& Interruption   │                │ Canvas Artifacts \& JSON
                             ▼                │
                     ┌────────────────────────────────┐
                     │    FastAPI Gateway             │
                     │    (Python 3.11+ / AsyncIO)    │
                     └───────┬────────────────▲───────┘
                             │                │
            ┌────────────────┴──────┐         │
            ▼                       ▼         │
┌───────────────────────┐ ┌───────────────────┴──┐ ┌───────────────────────┐
│ Voice Pipeline        │ │ Multi-Agent Router   │ │ Deterministic Engine  │
│ • Silero VAD (Local)  │ │ (LangGraph / Async)  │ │ • DuckDB / Polars     │
│ • Whisper.cpp / STT   │ │ • Ollama (Local LLM) │ │ • Strict Lineage      │
│ • Piper / Kokoro TTS  │ │ • Gemini API (Vision)│ │ • Formula Validation  │
└───────────────────────┘ └──────┬───────────────┘ └───────────────────────┘
                                 │
                     ┌───────────┴────────────┐
                     │ Context \& Storage Hub  │
                     │ • /vault (Markdown)    │
                     │ • Qdrant / Vector DB   │
                     │ • BM25 Hybrid Index    │
                     └────────────────────────┘
```

\---

## 5\. Master Prompt for Claude Code (`/goal`)

Copy and paste the exact command below into your Claude Code terminal session:

```text
/goal Build a complete, production-grade, locally executable Decision Intelligence System for Founders named "FounderOS". The system features a full-duplex interruptible voice advisor, a multi-agent analytical swarm, an Obsidian-style bi-directional knowledge brain, a deterministic DuckDB financial engine, and a live React visual canvas. The app must run on Windows 11 with 64GB RAM and 12GB VRAM using Docker Desktop and local Ollama.

### 1. SYSTEM ARCHITECTURE \& REPOSITORY STRUCTURE
Generate the following file tree and implement each file completely (no pseudocode, no placeholders, no incomplete stubs):

founder-os/
├── docker-compose.yml
├── .env.example
├── run.bat
├── backend/
│   ├── requirements.txt
│   ├── main.py
│   ├── config.py
│   ├── voice/
│   │   ├── vad.py
│   │   ├── stt.py
│   │   ├── tts.py
│   │   └── audio\_stream.py
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── financial\_agent.py
│   │   ├── risk\_agent.py
│   │   ├── memory\_agent.py
│   │   └── gemini\_scout.py
│   ├── engine/
│   │   ├── duckdb\_engine.py
│   │   └── hybrid\_rag.py
│   └── vault\_manager.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── App.tsx
        ├── components/
        │   ├── VoiceController.tsx
        │   ├── Canvas.tsx
        │   ├── ScenarioSimulator.tsx
        │   ├── PrioritizationMatrix.tsx
        │   └── DecisionMemo.tsx
        ├── hooks/
        │   ├── useAudioStream.ts
        │   └── useCanvasSync.ts
        └── styles/index.css

### 2. DETAILED MODULE REQUIREMENTS

#### A. Voice Pipeline \& Interruption Engine (backend/voice/)
- Implement a WebSocket-based streaming audio pipeline in audio\_stream.py.
- vad.py: Use Silero VAD (ONNX runtime) to detect speech vs silence in sub-30ms frames. Emit an immediate "interruption" frame if the user starts speaking while the system is streaming TTS audio, instantly aborting ongoing audio playback and clearing queues.
- stt.py: Use faster-whisper (model="small.en", device="cpu" or "cuda" with float16) to transcribe user utterances as soon as a silence threshold (400ms) is reached.
- tts.py: Implement low-latency streaming TTS using Piper or Kokoro ONNX. Return 24kHz raw PCM or WAV chunks over WebSocket directly to the browser.
- Audio UX rule: The conversational agent speaks ONLY in 2-3 sentence executive summaries and verbally references the visual UI elements.

#### B. Obsidian-Style Knowledge Brain \& WeKnora Hybrid RAG (backend/engine/ \& backend/vault\_manager.py)
- vault\_manager.py: Create a local directory ./vault storing standard Markdown files (.md) with YAML frontmatter. Implement bi-directional wikilink extraction (\[\[Link Name]]) and automated link index maintenance.
- hybrid\_rag.py: Implement WeKnora-inspired document processing:
  1. Parse PDF, CSV, Excel, and Markdown files uploaded by the user.
  2. Implement parent-child hierarchical chunking (parents 1000 tokens, children 250 tokens).
  3. Index chunks into a local Qdrant instance (vector search via Ollama nomic-embed-text or bge-m3) and a Rank-BM25 sparse index.
  4. Perform Reciprocal Rank Fusion (RRF) to merge keyword and semantic results before passing context to agents.

#### C. Deterministic Financial Engine (backend/engine/duckdb\_engine.py)
- Ensure ZERO hallucination on financial calculations. The LLM is NEVER allowed to do financial math directly.
- Ingest uploaded spreadsheets (P\&L, cash flow, unit economics) directly into an embedded DuckDB instance.
- Agents formulate SQL queries; DuckDB executes the queries; the exact numbers and SQL audit trails are returned to the agents and rendered in the frontend.
- Implement pre-built SQL routines for Runway, Burn Rate, Customer Acquisition Cost (CAC), Gross Margin, and 12-Month Cash Flow Projections.

#### D. Multi-Agent Swarm (backend/agents/)
- orchestrator.py: Socratic coordinator running on local Ollama (qwen2.5:7b-instruct or llama3.3:8b). Never agrees blindly; conducts pre-mortems.
- financial\_agent.py: Interfaces with duckdb\_engine.py to extract metrics and build sensitivity tables.
- risk\_agent.py: Formulates downside scenarios, team capability gaps, and execution blockers.
- gemini\_scout.py: Uses Google Gemini API (gemini-2.5-flash or gemini-1.5-pro) for high-level multimodal synthesis, web market intelligence, and structured JSON chart generation.
- memory\_agent.py: Persists final decision records back into ./vault/decisions/ as timestamped markdown memos with assumptions, metrics, and 30-day review dates.

#### E. Frontend Visual Canvas (frontend/)
- Build a responsive React + Vite + TailwindCSS application.
- VoiceController.tsx: Real-time audio waveform visualizer, mic toggle with push-to-talk / full-duplex toggles, and barge-in visual feedback.
- Canvas.tsx: Multi-card grid that displays real-time agent artifacts:
  - ScenarioSimulator.tsx: Interactive sliders for CAC, churn rate, and price change with live Recharts re-renders based on DuckDB logic.
  - PrioritizationMatrix.tsx: 2x2 scatter/bubble chart rendering strategic initiatives on Value vs. Execution Readiness.
  - DecisionMemo.tsx: Formatted executive decision memo with one-click export to Markdown and PDF.
- useCanvasSync.ts: Connects to FastAPI Server-Sent Events (SSE) or WebSocket to update UI components without blocking the voice audio stream.

#### F. Local Deployment \& Windows Bat Runner (docker-compose.yml, run.bat)
- docker-compose.yml: Define local services:
  - qdrant: Qdrant vector database on port 6333.
  - ollama: Host-network or bridged Ollama instance for local LLM inference on port 11434.
- run.bat: Windows batch script that:
  1. Checks for Docker, Python 3.11+, and Node.js.
  2. Creates Python virtual environment (.venv) and installs backend/requirements.txt.
  3. Runs npm install inside frontend/.
  4. Starts Qdrant and Ollama via Docker.
  5. Pulls qwen2.5:7b-instruct and nomic-embed-text into Ollama.
  6. Launches FastAPI backend on port 8000 and Vite dev server on port 3000 concurrently.
- .env.example: Template for GEMINI\_API\_KEY, OLLAMA\_BASE\_URL=http://localhost:11434, QDRANT\_HOST=localhost, and VAULT\_PATH=./vault.

### 3. IMPLEMENTATION CONSTRAINTS
- Production-ready code: All imports, dependencies, error handling, CORS headers, and asynchronous event loops must be fully implemented.
- Offline resilience: If GEMINI\_API\_KEY is not provided, the system must gracefully fall back to local Ollama models for all tasks without crashing.
- Write clear setup instructions in a generated README.md explaining how to run and demonstrate the product to stakeholders on Windows.
```

\---

