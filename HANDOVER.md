# HANDOVER: FounderOS

> **Every session reads this file first.** Update it as you work, not just at the end.
> Spec: `docs/PRD.md` · Session protocol: `docs/GOAL_PROMPT.md` · Repo rules: `CLAUDE.md`

## Quick status
- **Branching:** `main` is stable. Each session works on its own assigned branch, created from `main`, and ends by opening a PR into `main`. The founder reviews and merges that PR before starting the next session.
- **Next milestone:** **M3c: Decision models (Laya / Jev)**, in progress on branch `claude/m3c-decision-models`. M0, M1, M2, M3a and M3b are ACCEPTED and merged.
- **Review:** every PR must pass the 4 gates in "Review gates" below
- **Last updated:** 2026-11-05 (M3b fix session wrap-up)

## Milestones
| # | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Scaffold & foundations | DONE (merged, PR #2) | Backend `/api/health`, Northwind data, frontend shell, scripts, CI |
| M1 | Financial spine (DuckDB) | DONE (merged, PRs #3 + #4; Major gate ACCEPTED 2026-11-03) | |
| M2 | Vault & hybrid RAG | DONE (merged, PR #5; Light gate ACCEPTED 2026-11-03) | |
| M3a | LLM layer, agent framework & core agents | DONE (merged, PR #6; Medium gate ACCEPTED 2026-11-04) | |
| M3b | Specialist agents | DONE (merged, PR #7; Medium gate ACCEPTED 2026-11-05) | Plus the cloud layer and the conversation lane backend |
| M3c | Decision models (Laya / Jev) | IN PROGRESS | |
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
| M2 Vault & search | [Sree1959GIT/Founder-OS#5](https://github.com/Sree1959GIT/Founder-OS/pull/5) | Light | ACCEPTED (SM, 2026-11-03), Light; items 1–8, 10–12 pass on Windows (Docker Ollama, GPU) |
| M3a Agent framework | [Sree1959GIT/Founder-OS#6](https://github.com/Sree1959GIT/Founder-OS/pull/6) | Medium |    ACCEPTED (SM, 2026-11-04), Medium; steps 1–9, 11–14, RT1–RT9 and RV1–RV9 pass on Windows (Docker Ollama, qwen3:8b) |
| M3b Specialist agents | [Sree1959GIT/Founder-OS#7](https://github.com/Sree1959GIT/Founder-OS/pull/7) | Medium | ACCEPTED (SM, 2026-11-05), Medium; M1–M11 and RD3–RD9 pass on Windows (qwen3:8b, cloud off) |

## Current session
- Started (UTC): 2026-11-05 14:12 (local Windows session, time-box 2 hours), branch `claude/m3c-decision-models`, target **M3c** (gate tier: **Light**)
- Plan, in the founder's priority order (an "M3c (partial)" PR is fine if time runs out):
  - [x] Tidy the stale "Next milestone" and M3b table lines
  - [x] (1) Words never contradict the goal check; a cheaper option not proposed states a reason; off-brief wording; offline and live eval cases
  - [x] (2) Privacy filter pseudonymises customer and person names before any cloud use
  - [x] (3) 58 labelled questions; offline prompt tuning script; versioned prompts
  - [x] (4) `LayaProvider`, `JevProvider`, bake-off harness with 212 routing examples, confidence fallback, Laya fine-tune script
  - [x] (5) Provider bake-off harness
  - [x] (6) Embedding bake-off (EmbeddingGemma vs nomic-embed-text), licence point
  - [ ] Read the tuning and provider results; PRD §12 proposals; Windows checklist; self-review; PR; CI green

Previous session (2026-11-05, M3b gate fixes):
- Started (UTC): 2026-11-05 10:56 (local Windows bug-fix session for the M3b gate, time-box 2 hours), branch `claude/m3b-specialists`, PR #7
- Plan:
  - [x] Record the founder feedback first
  - [x] Decision frame: type, cost model (one-off + monthly, low/base/high via `run_scenario`), options with costs, goal check, key questions
  - [x] Goals never reported as decisions; hire framing only for hires
  - [x] Memo enforced in code: one chosen option, outcome predictions, measurable kill criteria, "Open numbers to confirm", plain Metrics
  - [x] Role discipline and second person everywhere; narration grouping and a specific question
  - [x] Offline and live eval rubric (Dubai office, price increase, new product line), tests
  - [x] Self-review, RD re-test steps, PR #7 updated, CI green

Previous session (2026-11-04, M3b):
- Started (UTC): 2026-11-04 14:23 (local Windows session), branch `claude/m3b-specialists`, target **M3b** (gate tier: **Medium**)
- Plan, in the founder's priority order (an "M3b (partial)" PR is fine if time runs out):
  - [x] Tidy the stale "Next milestone" and M3a table lines
  - [x] (1) Small items from the M3a re-test: journal eval reliable in full runs; Advisor says "you" and uses one money format; API sends `charset=utf-8`
  - [x] (2a) Cloud layer: remove the subscription path; Anthropic, Gemini (AI Studio or Vertex), OpenAI, OpenAI-compatible; per-agent-type choice; privacy filter on every cloud payload; per-call cost and latency; monthly cap; `/api/agents`
  - [x] (2b) Conversation lane backend: run queue, turn classifier, three contexts, narration events, APIs
  - [x] (3) Specialists: Devil's Advocate, Market Scout, Revenue & Customer, People & Ops, Regulatory & Tax, Prioritiser, Memo Writer, Perspective lens; cancel and re-run with an edited brief
  - [x] Offline and live evals for each new agent
  - [x] Decisions in PRD §12 and here; Windows checklist with the "Dubai office" run; self-review; PR into `main`; CI green

Previous session (2026-11-04, second M3a bug-fix):
- Started (UTC): 2026-11-04 (second local bug-fix session for the M3a gate, time-box 1 hour), branch `claude/m3a-agents`, PR #6
- Plan:
  - [x] Record the founder feedback (done first)
  - [x] Root cause: which tool returned 308,437.67, what the Analyst ran, why the Advisor reused it
  - [x] General fix: figures keep label and unit; the claim around them must agree; impacts from code-computed fields
  - [x] Unit tests, offline and live eval for the designer question
  - [x] Resolve feedback, RV steps, PR #6, CI green

Earlier session (2026-11-04, first bug-fix):
- Started (UTC): 2026-11-04 ~03:19 (local Windows session, bug-fix only for the M3a Medium gate, time-box 1 hour), branch `claude/m3a-agents`, PR #6
- Plan:
  - [x] Record the founder feedback (done first)
  - [x] Root cause: frontmatter in chunks/results, the 900-char cut, ranking of `decisions/`, Librarian prompt
  - [x] General fix + citations only for sources used + regression tests
  - [x] Offline eval (5–8 questions) and a live check for Windows
  - [x] Resolve feedback, re-test steps, PR #6 description, CI green

Previous session (M3a):
- Started (UTC): 2026-11-03 16:16 (local Windows 11 session, founder's PC), branch `claude/m3a-agents`; wrapped up ~17:45
- Target: **M3a: LLM layer, agent framework & core agents** (gate tier: **Medium**)
- Plan:
  - [x] Founder feedback: "(None)" fallback warning; Ollama in Docker (setup.bat HTTP detection, `docker exec` hints)
  - [x] Decisions: chat model `qwen3:8b` with thinking off; Ollama is an external service; EmbeddingGemma vs nomic → M3c
  - [x] `app/llm/` (base, Ollama, Anthropic API, Gemini, Claude Agent SDK, Fake, router with fallback to Ollama)
  - [x] `app/decision/` (interface, LLM + Fake providers, JSONL decision log, confidence escalation)
  - [x] `app/agents/` (registry, prompts, tools with lineage/citations, runner, Planner, Financial Analyst, Librarian,
        Verifier, Advisor, LangGraph graph with `Send` fan-out, concurrency caps, team approval)
  - [x] Event bus + `/api/events` (SSE), `/api/chat` (streaming SSE or JSON), `/api/runs/*`, `/api/agents`
  - [x] Health: Ollama loaded models + VRAM in use
  - [x] Real Ollama run ("What's our runway?" → 10.65 with lineage), wrap-up, PR

## Current state
### Decision frame (fix after the founder's M3b review, 2026-11-05)
**What you can do now**
- Ask about a decision and it is typed first: `hire`, `new_office`, `pricing`, `spend`, `fundraise`, `new_product` or `other`. An office is priced as an office (setup, rent, local hires, travel, compliance), one-off plus monthly, low/base/high, through `run_scenario`.
- Inputs not in your data are placeholders labelled "assumption, confirm", and a memo resting on them is never `verified`. Give your own figures in the lane ("rent is $9,000 a month") and it re-runs with them marked `founder`.
- The memo compares realistic options with their costs, proposes exactly one, checks your goals in `profile/company.md` and says when it moves away from one.

**How it works**
- `app/agents/decision_frame.py`: `build_frame` runs in `_plan_node`, before any agent. Costs, options, the goal check and starter outcomes are code; agents get them as findings. The placeholder values in `_TEMPLATES` are not market data.
- `app/agents/guards.py`: on words. Second person, "your adviser", one money format; a goal or proposal is never reported as decided unless a record says so; out-of-role lines go after one repair turn; FounderOS tool names never reach the founder.
- `app/agents/specialists.py`: the model drafts and code enforces: `with_required_fields` (one chosen option, not under Rejected, Decision matches), `without_unbacked_figures` (a figure with no source moves to "Open numbers to confirm"; `[figure removed` is gone), `_final_outcomes` (predictions are outcomes; stop rules are measurable, cannot fire at once, and one is always tied to spend or runway; starters follow the option proposed), `in_your_words`.
- `scenario.Adjustments.one_off_cost` is new. A proposed memo backs no figures for later runs (`tools._is_unconfirmed_memo`); once decided, it does.
- Evals: `app/evals/decision_eval.py` and `decision_questions.json` (Dubai office, price rise, new product line, spend), modes `rules`, `sloppy` (every mistake seen live) and live.

**Known limits**
- Model wording inside a role can still be weak: live, People & Ops wrote "The Financial Analyst would stop providing runway projections", and the Devil's Advocate told you to confirm the costs "with the Financial Analyst". No figures or decisions are affected. Better handled by M3c or a larger model than by more guards.
- Team findings in the memo are shortened, not rewritten, so a long list can be cut mid-point.
- Sentence filters (`_HELPS_THE_GOAL`, `_RESTATES_THE_MODEL`, `_SAYS_CHECKED`) are word patterns: they can miss a rephrased claim, or drop a true sentence. Code's own lines always remain.
- The goal check prices the full model, with the proposed option's own runway effect as its first line. It does not re-check each goal per option.
- No real cloud call was made in this session either.

### Specialist agents, cloud layer and conversation lane (M3b)
**What you can do now**
- Ask "Should we open a Dubai office? Write a decision memo." You get a team (Financial Analyst, Librarian, Market Scout, Regulatory & Tax, People & Ops, Devil's Advocate, Memo Writer), a risk register, and `decisions/YYYY-MM-DD-<slug>.md` with options, assumptions, metrics with lineage, predictions, kill criteria and a review date 30 days out. It took about 2 minutes on the local model.
- The memo's status is `proposed`: you decide. Its predictions are also stored in the calibration store.
- Cancel one agent, or re-run it with an edited brief, while the rest of the team works.
- Talk to the lane while a run works: status questions answer at once, "actually, assume..." offers a re-run, new questions wait in a queue.

**Agents (`app/agents/registry.py`, prompts in `prompts/`, code in `specialists.py`)**
- Stages: 0 Financial Analyst, Librarian, Market Scout; 1 Revenue & Customer, People & Ops, Regulatory & Tax, Prioritiser, Perspective lens; 2 Devil's Advocate; 3 Memo Writer. Each stage sees earlier findings, and the Verifier accepts earlier stages' numbers (`AgentResult.inherited`).
- Who joins: the Planner chooses, and the founder's words add specialists by rule (`team_for_message`). `calls_for_team` keeps "What is our churn?" a one-agent lookup while "What would a discount do to churn?" gets the specialist. The Memo Writer only joins when you ask for a memo or to record the decision, so ordinary questions never write to your vault. Up to 8 agents.
- Every specialist has a no-LLM rule answer with no invented figures (R3) and goes through the Verifier and its repair turn.
- What code guarantees: a risk register from the Devil's Advocate's lines; "not legal or tax advice" from Regulatory; the Market Scout's "vault only" note when cloud is off; web sources named; the Prioritiser sent back once if it ranks without the routine; the memo's path and review date in the reply.
- `request_metric` gives Revenue & Customer and People & Ops the Analyst's routines with lineage. They have no `run_sql` or scenarios.
- Memo: the model drafts JSON, the Verifier checks the prose, one repair turn, and code writes the file. (Superseded by the decision frame section above: such a figure now moves to "Open numbers to confirm".) A figure with no lineage is removed from the memo (`[figure removed: no lineage]`), including from the team findings section. A second memo on the same day gets `-2`.

**Cloud (`app/llm/`)**
- `cloud.py`: Anthropic (API key), Gemini (AI Studio or Vertex express key), OpenAI and OpenAI-compatible. The subscription path is gone; a `.env` that still says `DEEP_PROVIDER=claude_sdk` starts up local. You can delete `CLAUDE_CODE_OAUTH_TOKEN` from your `.env`.
- `router.py`: `AGENT_MODELS` per type, `DEEP_PROVIDER` as the default, fallback to Ollama. `privacy.py` filters every cloud payload. `costs.py` writes `data/<ws>/llm_calls.jsonl` (never the payload) and enforces `CLOUD_MONTHLY_CAP_USD`. `/api/agents` shows calls, cost and latency per type.
- **Tested with fakes only.** No real cloud call was made in this session: there is no key here. Prices in `costs.py` were read on 2026-11-04; override them with `LLM_PRICES`.

**Conversation lane (`app/conversation/`, `app/api/conversation.py`)**
- Backend only: M4 builds the text UI and M5 the voice. Events (`narration`, `recap`, `turn.classified`, `amendment.offered`, `queue.added`, `queue.offered`) arrive on `/api/events`.
- Rules classify clear turns in about 0.01 s. An unclear one goes to the decision model with a 4 s limit, then counts as a new question.
- Narration is templates over real events. The optional small model (`FAST_LANE_MODEL`, empty by default) only words a status reply and the assumption question, and a reply with a figure is thrown away. So the lane states no figures at all, which is stricter than "no unverified figure".

**Known limits**
- **GPU sharing is untested and matters for M5.** Live, an unclear turn timed out at 4 s while agents held the GPU and was queued: safe, but the decision model does not answer under load. M5 must test Ollama parallelism, or CPU/Laya for the fast lane.
- Findings from a `local` agent can reach a later `cloud_allowed` agent as text. The filter removes data rows and emails, not customer names in a sentence. Check this before using cloud with real customer data.
- Bedrock and Vertex for Claude are not built (Anthropic API key only). Gemini on Vertex is the express key, with no service-account login. OpenAI providers have no web search here. Web search fees per query are not in the cost estimates.
- A run's snapshot is recorded but agents do not read the session's recent turns, so "and what about Dubai?" as a new run has no earlier context. M4 should decide this with the UI.
- A specialist can still write an unsupported figure: live, Regulatory & Tax wrote a threshold from memory (375,000), the Verifier flagged it after the repair turn, and the run showed `verified False`. That is the system working, but expect it on tax questions.

### Past decisions and citations (fix after the founder's M3a review, 2026-11-04)
- **Decision records** (`app/vault/decisions.py`): every note under `decisions/` (or tagged `decision`) gets a
  `DecisionRecord`, built by code: path, title, status, decided, review date, `review_state` (upcoming | overdue,
  computed from today), what was decided, predictions, kill criteria. Kill criteria come from the frontmatter
  (`kill_criteria`, `kill_criterion`), a `Kill criteria` heading, or a sentence naming a kill criterion.
- **Frontmatter is searchable:** a note with fields beyond its name and tags gets a `Record` section, so those fields
  reach the chunks, the embeddings and the answer. Search results also return `metadata` and `decision`; `read_note`
  returns the frontmatter. Changed notes re-embed by themselves (point ids are content-addressed).
- **BM25:** a light stemmer (`SDR` = `SDRs`, `hire` = `hiring`), and question words are dropped when a topic remains.
- **`search_vault`:** the passage (1,200 characters, less when many hits share the budget) is centred on the matching
  chunk, replacing the first 900 characters. Decision hits carry their record.
- **Librarian:** before the model's first turn, code runs `past_decisions` and a whole-vault `search_vault` on the
  founder's own words. The record is put in the system prompt. `past_decisions` is not offered to the model.
- **Guarantee:** if an answer (Librarian or Advisor) leaves out a fact of a past decision, code adds it: the whole
  record if the answer states none, otherwise only what is missing. This needs no second LLM call, and it also works
  in the rules fallback. `ChatResult.past_decisions` and `AgentResult.past_decisions` return the records.
- **Citations:** `citations` lists only sources the answer names; `retrieved` keeps everything the tools returned.
- **Planner:** a decision team always has a Librarian. **Routing:** naming the notes ("what do my notes say about
  churn?") goes to the Librarian even with a finance word. **Verifier:** written dates ("15 Dec") are not figures.
- **Eval** (`app/evals/`, `scripts/eval_vault.py`): 8 questions. Offline, 2 modes each (LLM down; a careless fake LLM),
  run in pytest and CI. `--live` asks a running backend.

Known limits of this fix:
- "On the same topic" is decided by words in the note's name, tags and body. A synonym with no shared word ("BDRs"
  for "SDRs") is not guaranteed; it depends on the model's own search of `decisions/`.
- Citations are checked by path. If the model names a source it did not really use, code cannot tell.
- The Verifier checks numbers, not invented dates or wrong attributions. One live run invented a past decision; that
  was fixed in the prompt (the Advisor gets the rule only when a decision exists), so it is not a code guarantee.
- A reply with added facts can run past the Advisor's 3-sentence limit. The Planner can also spawn two Librarians,
  and both state the record.
- The final code passed the live eval 8/8 once, in PowerShell 5.1 on the founder's PC (and the code before the
  self-review fixes passed 8/8 once). Earlier runs failed and led to the fixes. Model output varies, so an occasional
  failure is possible.
- **Limits of the meaning check (rules, not understanding):**
  - It knows a fixed list of quantities. A sentence using other words, or a clause naming nothing outside a hire decision, is checked by value and unit only, so a wrong meaning can still pass there.
  - Numbers from `run_sql` are checked by value only, and a `DECIMAL` result reaches the tool as text, so it counts as a number without lineage (as before this fix).
  - A hire with no count ("Should we hire more?", "a few SDRs") gets no code-run scenario and no impact. The model chooses what to run, and the claim checks still apply.
  - A number with no lineage at all is flagged as before, not replaced.
  - In the designer answer the Advisor may mention the SDR decision as context and call the founder "the founder". It does not claim that decision covers a designer. Wording only, not changed here.

### LLM layer, agents and chat (M3a)
- **Providers** (`app/llm/`): `LLMProvider.complete(messages, tools=None, json_schema=None, stream=False)` returns
  a `Completion` (text, tool calls, usage, latency, provider, model), or with `stream=True` an async iterator of
  `StreamChunk`s. There is also `embed(texts)`. Errors are typed: `LLMUnavailable` (unreachable, not configured,
  model not pulled, 401/429/5xx) or `LLMError`.
  - `OllamaProvider` (`ollama.py`): `/api/chat` with `think: false` (Qwen3 thinking off), `keep_alive` 30m,
    `num_ctx` 8192, `format` = JSON Schema for structured output, NDJSON streaming, `/api/embed`, `/api/ps`.
    **Loading:** the chat model is preloaded at startup, and before every call the provider checks `/api/ps`
    (cached 60 s). If the model is not loaded, it loads it first with a 20-minute timeout behind a lock. Reason:
    a cold load on the founder's PC takes ~3.5 min (Docker bind mount), and a chat call with a 180 s timeout made
    Ollama abort the load every time.
  - `cloud.py`: `AnthropicAPIProvider` and `GeminiProvider` over REST with httpx (JSON output through a forced
    `respond` tool or `responseJsonSchema`), and `ClaudeAgentSDKProvider` (`claude-agent-sdk` imported lazily; no
    custom tools, so tool-using agents stay on Ollama). `fake.py`: `FakeProvider` with scripted replies.
  - `router.py`: `local` agents always use the local provider (PRD R2). `cloud_allowed`/`cloud` agents use
    `DEEP_PROVIDER` only when `CLOUD_ALLOWED=true` and credentials exist, and fall back to Ollama on any failure
    (`fallback_from` is recorded). Streaming falls back only before the first chunk.
- **Decision models** (`app/decision/base.py`): `DecisionService.choose/yes_no/score` over `LLMDecisionProvider` (JSON
  schema with an enum of the options) or `FakeDecisionProvider`. Every decision is appended to
  `data/<ws>/decision_log.jsonl` (state, options, choice, probability, provider, latency; `correct()` appends a
  correction line). An answer below `DECISION_MIN_CONFIDENCE` (0.75) is escalated to the fallback provider when one
  is set. Laya/Jev arrive in M3c.
- **Agents** (`app/agents/`): `registry.py` holds the 5 core types (Advisor, Planner, Financial Analyst, Librarian,
  Verifier), each with its prompt (`prompts/*.md`, read on every call), tool allow-list, privacy class (all
  `local`) and cost. `tools.py` wraps the M1 engine (`get_metric`, `metrics_summary`, `run_scenario` (with
  `runway_change_months` computed in code), `run_monte_carlo`, `run_sql` (guarded), `weighted_scoring`,
  `expected_value`, `calibration_scores`) and the M2 vault (`search_vault`, `read_note`, `write_note` only under
  `decisions/` or `journal/`). Tools never raise. The model gets a compact JSON summary; the canvas artifact keeps
  the full result with `Lineage`.
- **Runtime** (`runtime.py`): **Planner**: intent by rules first (decision cues, finance words, notes words,
  greetings), then the decision model for ambiguous messages. Finance → one Financial Analyst; knowledge → one
  Librarian; decision → an LLM-planned team (JSON schema; 1–4 tasks; only registered types; reversibility one/two-way)
  or a default team (Analyst + Librarian) if planning fails; chitchat → no team. **Agent loop**: up to
  `AGENT_MAX_STEPS` (4) tool rounds, then a final answer. The analyst's prompt gets the data's month range (the
  model invented `month=2023-10` before). **Rules fallback (R3)**: when the LLM is unavailable, the analyst runs
  the matching metric routine and the Librarian runs a search, and both answer from a template.
- **Verifier** (`verifier.py`, deterministic): every figure in an answer must match a number the model was shown by
  a tool (1 % relative, % vs ratio allowed). Years, YYYY-MM months and integers ≤ 12 are skipped, and numbers from
  the founder's message or the brief are allowed. Numbers quoted from returned vault passages are backed by their
  citation. A Librarian answer must cite a source, and every path it names must have been returned. A failing answer is sent back once
  with the issues, then flagged (`verified: false`, `issues`). The Advisor's reply is checked the same way at the end.
- **Graph** (`graph.py`, LangGraph): `plan` → `Send` fan-out → `agent` (×N) → `verify` (join) → `advise` → END.
  Concurrency caps are semaphores shared by all runs (`MAX_LOCAL_AGENTS` 2, `MAX_CLOUD_AGENTS` 6). Team approval
  (`TEAM_APPROVAL`): `always` | `cloud_only` (default; core agents are local, so teams start at once) | `never`;
  waiting teams time out after `TEAM_APPROVAL_TIMEOUT_S` and are rejected. Runs can be cancelled.
- **Events** (`events.py`): typed `AgentEvent {seq, type, run_id, agent_id, at, data}`. Types: `run.started`,
  `team.proposed`, `team.approved`, `team.rejected`, `agent.spawned`, `agent.status` (queued | thinking |
  querying_data | searching_vault | waiting_cloud | verifying | done | failed | cancelled), `agent.step` (e.g.
  `running get_metric(name="runway")`), `agent.tool_call`, `agent.artifact`, `agent.done` (elapsed, provider, model,
  tokens), `run.finished`. The bus keeps 2,000 events for replay (`?since=`).
- **REST**: `POST /api/chat` (`stream: true` = SSE: agent events, `delta` frames, then `done`; `stream: false` = one
  JSON `ChatResult`: `answer`, `metrics` (label, value, unit, as_of, full `lineage`), `artifacts`, `citations`,
  `agents` (text, tools, verified, attempts, provider, tokens), `verified`, `issues`, `timings_ms`, `elapsed_ms`),
  `GET /api/events?run_id=&since=` (SSE, keep-alive comment every 15 s), `GET /api/runs/{id}`,
  `POST /api/runs/{id}/approve` (`{"approved": true|false}`), `POST /api/runs/{id}/cancel`, `GET /api/agents`.
- **Health**: the Ollama probe lists the loaded models and their VRAM (`/api/ps`), e.g. `in VRAM: qwen3:8b 5.8 GB,
  nomic-embed-text:latest 0.3 GB`. The GPU probe shows total VRAM in use (`6.8/12.0 GB`). The GPU is shared with the
  n8n stack's models.
- **Setup**: `setup.bat` (and `setup.sh`) detect Ollama over HTTP (`/api/version`), report each model as pulled or
  not (`/api/tags`), pull with the `ollama` CLI when present, and otherwise print `docker exec ollama ollama pull <model>`.
- New settings (`.env.example`): `OLLAMA_CHAT_MODEL=qwen3:8b`, `OLLAMA_THINK`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_NUM_CTX`,
  `OLLAMA_WARMUP`, `LLM_PROVIDER` (ollama|fake), `LLM_TIMEOUT_S`, `TEAM_APPROVAL`, `TEAM_APPROVAL_TIMEOUT_S`,
  `MAX_LOCAL_AGENTS`, `MAX_CLOUD_AGENTS`, `AGENT_MAX_STEPS`, `DECISION_PROVIDER` (llm|fake), `DECISION_MIN_CONFIDENCE`.
  New dependency: `langgraph` (1.x).

Live results on the founder's PC (Ollama 0.32.1 in Docker, RTX 4080 Laptop, qwen3:8b loaded, 2026-11-03):
| Question | Time | Result |
|---|---|---|
| "What's our runway?" | 14.6–19.5 s | Runway (actual burn) 10.65 months with lineage; verified; 2 analyst LLM calls + 1 advisor |
| "What do my notes say about annual prepayment?" | 41 s | Librarian cites `notes/pricing-strategy.md` and 3 more; "15 % discount"; verified |
| "Should we hire two more SDRs next quarter?" | 46 s | LLM-planned team (Analyst `run_scenario` + Librarian); runway 11.23 → 9.81 (−1.42, computed in code); verified |
| Runway with the model unloaded | 222 s | the provider loaded it first (203 s), then answered with the LLM (not rules) |

Known issues / notes (M3a):
- **Ollama overhead on the founder's PC:** every Ollama request spends ~3.7 s before inference (the runner itself
  takes ~0.3 s for a short reply). `/api/tags` alone takes ~1.2 s. Cause: the model files sit on a Windows bind
  mount (`C:/Dev_Tools/LLM Models/ollama` → `/root/.ollama`), which is slow from Docker/WSL2. A cold load of
  qwen3:8b takes ~217 s. Moving the models to a Docker named volume (or the WSL filesystem) should cut both a lot.
  This is the founder's n8n stack, so it is a suggestion only (see Open questions).
- The decision model with qwen3:8b misclassified "What's our runway?" as `vault` in a raw test, which is why clear
  cases go through rules first. The M3c bake-off will measure this properly.
- Specialist agents, dependencies between tasks (one agent waiting for another), re-run with an edited brief, and
  the privacy filter on cloud payloads are M3b. All core agents are `local`, so no cloud call happens in M3a even
  with `CLOUD_ALLOWED=true`.
- The Advisor streams before its reply is verified; a failed check shows in `verified`/`issues` of the `done` frame.
- Token cost estimates for cloud agents are not computed yet (`est_cost_usd` is null for cloud).
- Agent tool loops use the guarded SQL path only through `run_sql`; the model rarely needs it.

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

## Next steps (for the M3c session)
0. **Gate check:** M3b is a **Medium** gate. The founder runs re-test steps RD1–RD10 below, tries a decision by hand and merges PR #7. Act on any "Founder feedback" first.
1. M3c (PRD §8): `LayaProvider`, `JevProvider`, the bake-off harness and labelled set, and the Laya fine-tuning script. The turn classifier (`kind="turn"` in the decision log) is new labelled data.
2. The bake-off also compares cloud providers on **accuracy, latency and cost per answer** (founder decision, PRD §12). `llm_calls.jsonl` already holds latency and cost per call; `scripts/eval_vault.py` and `scripts/eval_agents.py` supply the questions.
3. The **EmbeddingGemma vs `nomic-embed-text` comparison**, deferred from M3a: retrieval quality on the sample vault plus a labelled query set, latency and VRAM. Collection names include the embedding model, so switching re-embeds cleanly.
4. M4 builds the conversation lane's text UI on `/api/conversation/*`, approve-with-edits (`POST /api/runs/{id}/approve` takes `edit`), and agent cancel and re-run. M5 builds the voice and must test GPU sharing.
5. Smaller ideas: a smarter `LLM_PROVIDER=fake` for an offline demo; `engine/embeddings.OllamaEmbedder` delegating to `OllamaProvider.embed`.

## Windows verification checklist (for the founder)
**M3b re-test after the fixes (about 15 min). Run this one first: RD1 to RD10.** The commands ran in Windows PowerShell 5.1 here against a test backend on port 8011 with scratch data, so your vault was not touched by that run. From `D:\Founder-OS`. Each prints a summary line to compare with **Expected**. Figures are computed by code from the demo data, so they should match exactly; the model's wording varies. All the costs in these runs are **placeholders, not market data**: replacing them with real figures is what RD9 tests. Then merge, or write the issues under "Founder feedback".

- **RD1. Get the code.** `git fetch origin; git checkout claude/m3b-specialists; git pull origin claude/m3b-specialists`, close the backend window, then start `run.bat`. No new dependencies. Wait for `Ollama model qwen3:8b is loaded`.
- **RD2. Offline: no Ollama needed.**
  `.\.venv\Scripts\python.exe scripts\eval_agents.py | Select-Object -Last 1; .\.venv\Scripts\python.exe scripts\eval_vault.py | Select-Object -Last 1; Set-Location backend; ..\.venv\Scripts\python.exe -m pytest -q 2>$null | Select-Object -Last 1; Set-Location ..`
  Expected: `OFFLINE AGENT EVAL: 24/24 passed`, `OFFLINE EVAL: 18/18 passed`, `820 passed` (with a time).
- **RD3. The Dubai decision (about 2 minutes). It writes a real memo to your vault; RD5 deletes it.**
  `$b = 'http://127.0.0.1:8000'`
  `function Ask($q) { Invoke-RestMethod -Method Post -Uri "$b/api/chat" -ContentType 'application/json' -Body (@{ message = $q; stream = $false } | ConvertTo-Json) -TimeoutSec 900 }`
  `$r = Ask 'Should we open a Dubai office? Write a decision memo.'; $f = $r.decision_frame; $c = $f.cost_model.cases | Where-Object { $_.name -eq 'base' }; "RD3 type $($f.type) | up front $($c.one_off) | monthly $($c.monthly) | runway $($c.runway_change_months) | items $(@($f.cost_model.items).Count) | options $(@($f.options).Count) | assumptions $($r.assumptions_to_confirm) | status $($r.memo.status) | verified $($r.memo.verified)"`
  `"RD3 goal: $(($f.goals | Where-Object { $_.status -eq 'moves_away' })[0].goal)"`
  `"RD3 proposed: $($r.memo.chosen)"`
  `"RD3 answer: $($r.answer)"`
  Expected, four lines: `RD3 type new_office | up front 30000.0 | monthly 32347.24 | runway -2.07 | items 5 | options 5 | assumptions 5 | status proposed | verified False`, then `RD3 goal: Extend runway past 12 months without new financing`, then the proposed option (one of the five), then the reply. The reply must give the $30,000.00 and $32,347.24 as assumptions, say it moves you away from the runway goal, say the second-region goal is still open, and name the proposed option with its own cost.
- **RD4. The memo, saved to a temp file.**
  `$note = Invoke-RestMethod "$b/api/vault/notes/$($r.memo.path)"; $m = $note.content; $tmp = Join-Path $env:TEMP 'dubai-memo.md'; [IO.File]::WriteAllText($tmp, $m, (New-Object Text.UTF8Encoding($false))); $rej = ($m -split '## Rejected alternatives')[1] -split '## Assumptions' | Select-Object -First 1; "RD4 sections $((@('## Decision','## Goal check','## Cost model','## Options','## Rejected alternatives','## Assumptions','## Open numbers to confirm','## Metrics','## Predictions','## Kill criteria') | Where-Object { $m.Contains($_) }).Count) of 10 | proposed once $(([regex]::Matches($m, '\*\*\(proposed\)\*\*')).Count -eq 1) | chosen not rejected $(-not $rej.Contains("- $($r.memo.chosen):")) | figure removed $($m.Contains('[figure removed')) | the founder $($m -match '(?i)\bthe founder\b') | one hire $($m -match '(?i)\b1 hire\b') | formula dump $($m.Contains('formula:')) | payroll total $($m.Contains('308,437')) | memo saved $(Test-Path $tmp)"`
  Expected: `RD4 sections 10 of 10 | proposed once True | chosen not rejected True | figure removed False | the founder False | one hire False | formula dump False | payroll total False | memo saved True`. Read it with `notepad $tmp`: predictions and kill criteria should be outcomes with a metric, a threshold and a date; the first Goal check line gives the proposed option's own runway effect.
- **RD5. Delete the memo from the vault (the temp copy stays).**
  `Invoke-RestMethod -Method Delete "$b/api/vault/notes/$($r.memo.path)" | Out-Null; "RD5 memo still there $((Invoke-RestMethod "$b/api/vault/notes").notes.path -contains $r.memo.path) | copy at $tmp"`
  Expected: `RD5 memo still there False | copy at ...\dubai-memo.md`. Its starter predictions are never stored in the calibration store, so nothing else is left behind.
- **RD6. A price rise (about 2 minutes; deletes its own memo).**
  `$p = Ask 'Should we raise our prices by 10%? Write a decision memo.'; $pc = ($p.decision_frame.cost_model.cases | Where-Object { $_.name -eq 'base' }); "RD6 type $($p.decision_frame.type) | items $(($p.decision_frame.cost_model.items | ForEach-Object { $_.name }) -join ', ') | mrr in 3 months $($pc.mrr_in_3_months) | runway $($pc.runway_change_months) | proposed $($p.memo.chosen) | goal $(($p.decision_frame.goals | Where-Object { $_.status -eq 'moves_away' })[0].goal)"`
  `Invoke-RestMethod -Method Delete "$b/api/vault/notes/$($p.memo.path)" | Out-Null`
  Expected: `RD6 type pricing | items Price change, Extra monthly churn it causes, Customer notice and billing changes | mrr in 3 months 282096.51 | runway 1.12 | proposed` (one option) `| goal Bring logo churn under 1.5 % a month`.
- **RD7. A new product line (about 2 minutes; deletes its own memo).**
  `$n = Ask 'Should we launch a new product line? Write a decision memo.'; $nc = ($n.decision_frame.cost_model.cases | Where-Object { $_.name -eq 'base' }); "RD7 type $($n.decision_frame.type) | items $(($n.decision_frame.cost_model.items | ForEach-Object { $_.name }) -join ', ') | up front $($nc.one_off) | monthly $($nc.monthly) | runway $($nc.runway_change_months) | proposed $($n.memo.chosen)"`
  `Invoke-RestMethod -Method Delete "$b/api/vault/notes/$($n.memo.path)" | Out-Null`
  Expected: `RD7 type new_product | items Build and launch, Dedicated team, Go-to-market, Hosting and support | up front 80000.0 | monthly 27347.24 | runway -2.09 | proposed` (one option).
- **RD8. A real hire keeps the hire numbers (no memo).**
  `$h = Ask 'Should we hire two SDRs?'; "RD8 type $($h.decision_frame.type) | hires $($h.decision_frame.hires) | cost model $($null -ne $h.decision_frame.cost_model) | impact $($h.decision_impact.new_hires) | impact runway $($h.decision_impact.runway_change_months) | says decided $($h.answer -match '(?i)you have decided')"`
  Expected: `RD8 type hire | hires 2 | cost model True | impact 2 | impact runway -1.42 | says decided False`.
- **RD9. Give your own figures: the question, then the re-run (about 4 minutes; no memo).**
  `function Say($s, $text) { Invoke-RestMethod -Method Post -Uri "$b/api/conversation/turn" -ContentType 'application/json; charset=utf-8' -Body (@{ session_id = $s; text = $text } | ConvertTo-Json) }`
  `$t = Say $null 'Should we open a Dubai office?'; $s = $t.session_id; do { Start-Sleep 3; $v = Invoke-RestMethod "$b/api/conversation/$s" } while ($v.running); $q = @($v.narration | Where-Object { $_ -like 'While the team works*' })[0]; $a = Say $s 'rent is $9,000 a month and one-off setup is $40,000'; do { Start-Sleep 3; $v2 = Invoke-RestMethod "$b/api/conversation/$s" } while ($v2.running); $g = Invoke-RestMethod "$b/api/runs/$($a.run_id)"; $gc = $g.result.decision_frame.cost_model; $bc = $gc.cases | Where-Object { $_.name -eq 'base' }; "RD9 question '$q'"; "RD9 kind $($a.kind) | reply '$($a.reply)' | up front $($bc.one_off) | monthly $($bc.monthly) | rent basis $(($gc.items | Where-Object { $_.name -like 'Rent*' }).basis) | setup basis $(($gc.items | Where-Object { $_.name -like 'Setup*' }).basis)"`
  `"RD9 narration: $(@($v.narration) -join ' / ')"`
  Expected, three lines. `RD9 question 'While the team works, for a full Dubai office: tell me what setup and licences would cost, the monthly rent or desk and how many local hires. Until you do, I use assumptions you can correct.'`, then `RD9 kind amendment | reply 'Running it again with your figures.' | up front 40000.0 | monthly 36347.24 | rent basis founder | setup basis founder`, then the narration, grouped: `Librarian, Market Scout and Financial Analyst are done; three to go.` and so on, ending `The answer is ready. It rests on assumptions you should confirm.` Team order can vary.
- **RD10. Live eval (optional, about 20 minutes).** `.\.venv\Scripts\python.exe scripts\eval_agents.py --live | Select-Object -Last 1`
  Expected: `LIVE AGENT EVAL: 12/12 passed`. Model wording varies, so one miss can be noise: read its line. **The Memo Writer and decision cases write memos to your vault:** remove them afterwards from `decisions/`.

**M3b, the first round (the founder has passed M1–M11; reference only, expected values updated for the fixes).** These commands ran in Windows PowerShell 5.1 here (5.1.26100), against a test backend on another port with scratch data, so the checks below did not touch your vault. From `D:\Founder-OS`. Each step prints one summary line; compare it with **Expected**. Then merge the PR, or write the issues under "Founder feedback". Model wording varies, and so can the number of risks and predictions.

- **M1. Get the code.** `git fetch origin; git checkout claude/m3b-specialists; git pull origin claude/m3b-specialists`, close the backend window, then start `run.bat`. No new dependencies, so `setup.bat` is not needed. Wait for `Ollama model qwen3:8b is loaded`. Optional: delete `CLAUDE_CODE_OAUTH_TOKEN` from your `.env`; it is no longer used.
- **M2. Offline: no Ollama needed.**
  `.\.venv\Scripts\python.exe scripts\eval_agents.py | Select-Object -Last 1; .\.venv\Scripts\python.exe scripts\eval_vault.py | Select-Object -Last 1; Set-Location backend; ..\.venv\Scripts\python.exe -m pytest -q 2>$null | Select-Object -Last 1; Set-Location ..`
  Expected: `OFFLINE AGENT EVAL: 24/24 passed`, `OFFLINE EVAL: 18/18 passed`, `820 passed` (with a time).
- **M3. Agents, cost and cap.**
  `$b = 'http://127.0.0.1:8000'; $a = Invoke-RestMethod "$b/api/agents"; "types $($a.agents.Count) | specialists $(($a.agents | Where-Object { -not $_.core }).Count) | cloud allowed $($a.cloud.allowed) | cap $($a.cloud.cap_usd) | memo writer on $(($a.agents | Where-Object { $_.type -eq 'memo_writer' }).provider)"`
  Expected: `types 13 | specialists 8 | cloud allowed False | cap 25.0 | memo writer on ollama`.
- **M4. Charset.** `(Invoke-WebRequest -UseBasicParsing "$b/api/agents").Headers['Content-Type']`
  Expected: `application/json; charset=utf-8`.
- **M5. The Dubai office decision (about 2 minutes).** This writes a real memo to your vault; step M7 deletes it.
  `$r = Invoke-RestMethod -Method Post -Uri "$b/api/chat" -ContentType 'application/json' -Body '{"message": "Should we open a Dubai office? Write a decision memo.", "stream": false}' -TimeoutSec 900; $risks = (($r.agents | Where-Object { $_.type -eq 'devils_advocate' }).artifacts | Where-Object { $_.kind -eq 'risk_register' }).data.risks; "agents $($r.agents.Count) | scout, regulatory, devil, memo $(@('market_scout','regulatory_tax','devils_advocate','memo_writer' | Where-Object { $r.agents.type -contains $_ }).Count) | risks $(@($risks).Count) | status $($r.memo.status) | review in days $(([datetime]$r.memo.review_date - (Get-Date).Date).Days) | predictions $(@($r.memo.predictions).Count) | memo in reply $($r.answer.Contains($r.memo.path)) | vault only $(($r.agents | Where-Object { $_.type -eq 'market_scout' }).text.Contains('vault only'))"`
  Expected: `agents 6` or `7` `| scout, regulatory, devil, memo 4 | risks` 3 to 5 `| status proposed | review in days 30 | predictions` 1 to 3 `| memo in reply True | vault only True`.
  Then read it: `$r.agents.name` (the team), `$risks | Format-Table risk, likelihood, impact -Wrap` (the Devil's Advocate), `$r.memo.predictions`, `$r.answer`. The reply should give the office's modelled cost as assumptions, say what it does to your runway goal, name the memo, the proposed option and its review date, and never say you already decided.
- **M6. The memo file.**
  `$note = Invoke-RestMethod "$b/api/vault/notes/$($r.memo.path)"; "sections $((@('## Options','## Rejected alternatives','## Assumptions','## Metrics','## Predictions','## Kill criteria') | Where-Object { $note.content.Contains($_) }).Count) of 6 | lineage $($note.content.Contains('From your data'))"`
  Expected: `sections 6 of 6 | lineage True`. To read it: `$note.content`.
- **M7. Delete the test memo.**
  `Invoke-RestMethod -Method Delete "$b/api/vault/notes/$($r.memo.path)" | Out-Null; "memo still there $((Invoke-RestMethod "$b/api/vault/notes").notes.path -contains $r.memo.path)"`
  Expected: `memo still there False`. Its predictions stay in `data\default` as test rows in the calibration store. They do no harm, and there is no delete API for them yet.
- **M8. Talking during a run (about 2 minutes).**
  `function Say($s, $text) { Invoke-RestMethod -Method Post -Uri "$b/api/conversation/turn" -ContentType 'application/json; charset=utf-8' -Body (@{ session_id = $s; text = $text } | ConvertTo-Json) }; $t = Say $null 'Should we hire two SDRs? Run a pre-mortem.'; $s = $t.session_id; Start-Sleep 10; $o = Say $s 'ok thanks'; $u = Say $s 'How long will this take?'; $q = Say $s 'What is our runway?'; $m = Say $s 'Actually, assume only one SDR'; "$($o.kind) | $($u.kind) | $($q.kind) | $($m.kind) | same run $($q.run_id -eq $t.run_id) | status: $($u.reply)"`
  Expected: `backchannel | answerable_now | new_question | amendment | same run True | status: Working: ...` naming real agents, with no figures.
- **M9. Decline the change, and the queue is offered at the end.**
  `Invoke-RestMethod -Method Post -Uri "$b/api/conversation/$s/amendments/$($m.amendment_id)" -ContentType 'application/json' -Body '{"accept": false}' | Out-Null; do { Start-Sleep 3; $c = Invoke-RestMethod "$b/api/conversation/$s" } while ($c.running); Start-Sleep 1; $c = Invoke-RestMethod "$b/api/conversation/$s"; "narration $(@($c.narration).Count) | last '$($c.narration[-1])' | offered '$($c.queue[0].text)' $($c.queue[0].status)"`
  Expected: `narration` about 7 `| last 'The answer is ready.' | offered 'What is our runway?' offered`. If a specialist wrote an unverified figure, the last line says `The answer is ready, but part is unverified.` To read the narration: `$c.narration`.
- **M10. Accept the queued question.**
  `$n = Invoke-RestMethod -Method Post -Uri "$b/api/conversation/$s/queue/$($c.queue[0].id)" -ContentType 'application/json' -Body '{"accept": true}'; do { Start-Sleep 2 } while ((Invoke-RestMethod "$b/api/conversation/$s").running); $g = Invoke-RestMethod "$b/api/runs/$($n.run_id)"; "next run: $($g.result.metrics[0].metric) $($g.result.metrics[0].value)"`
  Expected: `next run: runway 10.65`.
- **M11. Cancel one agent and re-run another with an edited brief (about 2 minutes).**
  `$t = Say $null 'Should we hire two SDRs? Run a pre-mortem.'; do { Start-Sleep -Milliseconds 300; $team = ((Invoke-RestMethod "$b/api/runs/$($t.run_id)").events | Where-Object { $_.type -eq 'team.proposed' }).data.team } until ($team); $lib = ($team | Where-Object { $_.type -eq 'librarian' })[0]; $fin = ($team | Where-Object { $_.type -eq 'financial_analyst' })[0]; Start-Sleep 1; $x = Invoke-RestMethod -Method Post "$b/api/runs/$($t.run_id)/agents/$($lib.id)/cancel"; $y = Invoke-RestMethod -Method Post -Uri "$b/api/runs/$($t.run_id)/agents/$($fin.id)/rerun" -ContentType 'application/json' -Body '{"brief": "Only the payroll cost of two SDRs"}'; do { Start-Sleep 3; $g = Invoke-RestMethod "$b/api/runs/$($t.run_id)" } while ($g.status -eq 'running'); $ag = $g.result.agents; "cancelled $($x.cancelled) | restarted $($y.restarted) | librarian $(($ag | Where-Object { $_.type -eq 'librarian' }).status) | analyst $(($ag | Where-Object { $_.type -eq 'financial_analyst' }).status), brief '$(($ag | Where-Object { $_.type -eq 'financial_analyst' }).brief)' | devil $(($ag | Where-Object { $_.type -eq 'devils_advocate' }).status)"`
  Expected: `cancelled True | restarted True | librarian cancelled | analyst done, brief 'Only the payroll cost of two SDRs' | devil done`.
- **M12. Optional: the full live evals (about 10 minutes; the agent eval writes one more memo).**
  `.\.venv\Scripts\python.exe scripts\eval_vault.py --live | Select-Object -Last 1; .\.venv\Scripts\python.exe scripts\eval_agents.py --live | Select-Object -Last 1`
  Expected: `LIVE EVAL: 9/9 passed` and `LIVE AGENT EVAL: 8/8 passed` (both passed here on `qwen3:8b`). Model output varies, so a failure is a prompt to read the answer. Delete the extra memo from `vault\default\decisions` afterwards.
- **M13. Optional: a real cloud call.** None was made in this session, because there is no key here. If you want one before M3c, add an API key to `.env`, set `CLOUD_ALLOWED=true` and `DEEP_PROVIDER`, restart, and repeat M5. Expected: a team approval wait first (`POST /api/runs/{id}/approve`), the Market Scout naming web pages if you chose Anthropic or Gemini, and a non-zero `spent_usd` in `/api/agents`. Set the cap you want first with `CLOUD_MONTHLY_CAP_USD`.

**Earlier checklists, kept for reference.**
**M3a re-test after the "wrong meaning" fix (done, ACCEPTED).** Commands were
run in PowerShell 5.1 here, against a test backend on another port. From `D:\Founder-OS`. Each step prints a summary
line; compare it with **Expected**. Then merge the PR, or write the issues under "Founder feedback".

- **RV1. Get the fix.** `git pull origin claude/m3a-agents`, close the backend window, then start `run.bat`. It must be
  restarted: a backend that is already running keeps the old code. No new dependencies, so `setup.bat` is not needed.
  Wait for `Ollama model qwen3:8b is loaded` in the backend window.
- **RV2. The rules, offline (no Ollama needed).** `.\.venv\Scripts\python.exe scripts\eval_vault.py | Select-Object -Last 1; Set-Location backend; ..\.venv\Scripts\python.exe -m pytest tests\test_claim_verifier.py -q | Select-Object -Last 1; Set-Location ..`
  Expected: `OFFLINE EVAL: 18/18 passed`, then `89 passed` (with a time). These include your exact sentence, which must fail.
- **RV3. Your question.**
  `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "Should we hire a designer?", "stream": false}' -TimeoutSec 900; $i = $r.decision_impact; 'intent {0} | verified {1} | hires {2} | per hire {3} | added a month {4} | runway {5} to {6} ({7}) | payroll in answer {8}' -f $r.intent, $r.verified, $i.new_hires, $i.cost_per_hire_monthly, $i.monthly_cost_delta, $i.base_runway_months, $i.scenario_runway_months, $i.runway_change_months, ($r.answer -match '308,?437')`
  Expected: `intent decision | verified True | hires 1 | per hire 11423.62 | added a month 11423.62 | runway 11.23 to 10.47 (-0.76) | payroll in answer False`.
  `$r.answer` must give those figures and call the cost the company's average, not a quote for this role. Its other
  wording varies, and it may mention the SDR decision as context.
- **RV4. Two hires: the code multiplies.**
  `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "Should we hire two SDRs?", "stream": false}' -TimeoutSec 900; $i = $r.decision_impact; 'verified {0} | hires {1} | per hire {2} | added a month {3} | runway {4} to {5} ({6}) | past decisions {7}' -f $r.verified, $i.new_hires, $i.cost_per_hire_monthly, $i.monthly_cost_delta, $i.base_runway_months, $i.scenario_runway_months, $i.runway_change_months, @($r.past_decisions).Count`
  Expected: `verified True | hires 2 | per hire 11423.62 | added a month 22847.24 | runway 11.23 to 9.81 (-1.42) | past decisions 1`.
- **RV5. Not a hire: nothing changes.**
  `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "What''s our runway?", "stream": false}' -TimeoutSec 900; 'verified {0} | runway {1} | impact is empty {2} | tools {3}' -f $r.verified, $r.metrics[0].value, ($null -eq $r.decision_impact), ($r.agents[0].tool_calls.tool -join ',')`
  Expected: `verified True | runway 10.65 | impact is empty True | tools get_metric`.
- **RV6. A percentage still verifies.**
  `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "What is our gross margin?", "stream": false}' -TimeoutSec 900; 'verified {0} | margin {1} | says 72.13 {2}' -f $r.verified, $r.metrics[0].value, ($r.answer -match '72\.13')`
  Expected: `verified True | margin 0.7213 | says 72.13 True`.
- **RV7. A figure quoted from a note still verifies.**
  `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "What do my notes say about annual prepayment?", "stream": false}' -TimeoutSec 900; 'verified {0} | says 15 {1} | cites pricing note {2}' -f $r.verified, ($r.answer -match '15\s?%'), (@($r.citations.path) -contains 'notes/pricing-strategy.md')`
  Expected: `verified True | says 15 True | cites pricing note True`.
- **RV8. Streaming now goes sentence by sentence.**
  `Set-Content -Path $env:TEMP\ask.json -Value '{"message": "What''s our runway?"}' -Encoding ascii; $out = curl.exe -s -N -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" --data-binary "@$env:TEMP\ask.json"; ($out | Select-String '^event: (delta|done)' | ForEach-Object { $_.Line -replace 'event: ','' } | Group-Object | ForEach-Object { "$($_.Name) x$($_.Count)" }) -join ', '`
  Expected: `delta xN, done x1`, with N about 2–5 (it was 40–90, one per word). Each sentence is checked before it is sent.
- **RV9. Live eval, now 9 questions through the real model.** `.\.venv\Scripts\python.exe scripts\eval_vault.py --live`
  Expected: one `PASS [live]` line per question, ending `LIVE EVAL: 9/9 passed`, in about **2 minutes**. Model output
  varies, so if a question fails, re-run it alone with `--only <id>` and read the answer.

**Earlier M3a re-test, after the "past decision" fix (about 10 min).** RV replaces RT6 and RT8 (now 9 questions). PowerShell 5.1 or 7, from `D:\Founder-OS`. Each step
prints one summary line; compare it with **Expected**. Then merge the PR, or write the issues under "Founder feedback".

- **RT1. Get the fix.** `git pull origin claude/m3a-agents`, close the backend window, then start `run.bat`. No new
  dependencies, so `setup.bat` is not needed. Wait for `Ollama model qwen3:8b is loaded` in the backend window.
- **RT2. Offline eval (no Ollama needed).** `.\.venv\Scripts\python.exe scripts\eval_vault.py | Select-Object -Last 1`
  Expected: `OFFLINE EVAL: 16/16 passed`.
- **RT3. Your question.**
  `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "Should we hire two more SDRs next quarter?", "stream": false}' -TimeoutSec 900; $d = $r.past_decisions[0]; '{0:n0} s | verified {1} | {2} | status {3} | decided {4} | review {5} | {6}' -f ($r.elapsed_ms/1000), $r.verified, $d.path, $d.status, $d.decided, $d.review_date, $d.predictions[0]`
  Expected: about **25 s** `| verified True | decisions/2026-09-hire-two-sdrs.md | status decided | decided 2026-09-15 | review 2026-12-15 | 70% chance outbound pipeline grows by at least 30% within 90 days`.
- **RT4. The kill criterion, and the answer you read** (uses `$r` from RT3).
  `'{0} || {1}' -f $r.past_decisions[0].kill_criteria[0], $r.answer`
  Expected: `if qualified meetings per SDR stay under eight a month by December, pause the second seat ||` then an answer
  that says you already decided to hire two SDRs (September or 2026-09-15), states that kill criterion and
  2026-12-15 or 15 Dec, gives the 70 %, and asks about it. The wording varies. When the model leaves out a fact, code
  adds it at the end as `On record for "Hire two SDRs for outbound": ...`.
- **RT5. Citations list only what was used (your step 8).**
  `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "What do my notes say about annual prepayment?", "stream": false}' -TimeoutSec 900; 'intent {0} | verified {1} | past decisions {2} | cites {3} | searched {4}' -f $r.intent, $r.verified, @($r.past_decisions).Count, (($r.citations.path | Select-Object -Unique) -join ', '), (($r.agents[0].retrieved.path | Select-Object -Unique) -join ', ')`
  Expected: `intent knowledge | verified True | past decisions 0 | cites notes/pricing-strategy.md | searched` then a longer
  list. `cites` is what the answer used, and `searched` is everything the search returned. `decisions/2026-09-hire-two-sdrs.md`
  must not be under `cites`.
- **RT6. Another topic does not claim the SDR decision.**
  `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "Should we hire a designer?", "stream": false}' -TimeoutSec 900; 'intent {0} | past decisions {1} | {2}' -f $r.intent, @($r.past_decisions).Count, $r.answer`
  Expected: `intent decision | past decisions 0 |` then an answer that does not say you already decided this.
- **RT7. The fix is general: a new decision note, not about SDRs.** This writes one test note, asks, then deletes it:
  `$f = '.\vault\default\decisions\2026-10-cut-paid-search.md'; Set-Content -Path $f -Encoding utf8 -Value "---`ntitle: Cut paid search`ndate: 2026-10-01`nstatus: decided`nreview_date: 2027-01-15`nkill_criteria: if pipeline falls by a third, restore the budget`nprediction: 60% chance CAC falls within a quarter`n---`n# Cut paid search`n`n## Decision`nStop paid search for one quarter.`n"; Start-Sleep -Seconds 3; $r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "Should we cut paid search next quarter?", "stream": false}' -TimeoutSec 900; $d = $r.past_decisions[0]; Remove-Item $f; '{0} | {1} | review {2} | {3} | {4}' -f $d.path, $d.decided, $d.review_date, $d.kill_criteria[0], $d.predictions[0]`
  Expected: `decisions/2026-10-cut-paid-search.md | 2026-10-01 | review 2027-01-15 | if pipeline falls by a third, restore the budget | 60% chance CAC falls within a quarter`.
- **RT8. Live eval, 8 questions through the real model.** `.\.venv\Scripts\python.exe scripts\eval_vault.py --live`
  Expected: one `PASS [live]` line per question, ending `LIVE EVAL: 8/8 passed`, in about **2 minutes**. Model output
  varies: if one question fails, read the line, re-run it with `--only <id>`, and report it if it fails again.
- **RT9. Nothing else moved.** `'{0} | {1}' -f (Invoke-RestMethod http://127.0.0.1:8000/api/metrics/runway).value, (Invoke-RestMethod http://127.0.0.1:8000/api/search -Body @{q='annual prepayment discount'; mode='bm25'; k=1}).results[0].path`
  Expected: `10.65 | notes/pricing-strategy.md`. Steps 1–7 and 10–14 below are unchanged.

**M3a (Medium tier, about 20 min).** In PowerShell, from `D:\Founder-OS`. Every command works in Windows PowerShell
5.1 and PowerShell 7. Each check prints one summary line; compare it with **Expected**. When done, merge the PR or
write the issues under "Founder feedback".

**Prepare (once).**
1. `git fetch origin; git checkout claude/m3a-agents`, then `setup.bat` (installs `langgraph`).
   Expected, in the setup output: `Ollama 0.32.1 is running at http://localhost:11434`, `Ollama model qwen3:8b is pulled`,
   `Ollama model nomic-embed-text is pulled`, and **no** "Ollama not found" warning.
2. Your `.env` is never changed by setup. Check the chat model line:
   `Select-String -Path .env -Pattern '^OLLAMA_CHAT_MODEL'`
   Expected: `OLLAMA_CHAT_MODEL=qwen3:8b`. If it still says `qwen2.5:7b-instruct-q4_K_M`, change it to `qwen3:8b` in
   Notepad (or delete the line to use the default). Then start `run.bat`.
3. **Start-up log** (backend window). Expected: `Agents ready: local LLM ollama:qwen3:8b (thinking off), deep provider
   none (local only), team approval cloud_only`, then `Loading qwen3:8b into Ollama in the background`, then
   `Ollama model qwen3:8b is loaded (N s)`. N is ~5 s if the model was already in VRAM, and up to ~4 min from cold
   (see the note on the Docker bind mount under "Open questions"). Wait for this line before step 6.

**Checks.**
4. **Health shows VRAM (GPU shared with n8n).**
   `(Invoke-RestMethod http://127.0.0.1:8000/api/health).dependencies | Where-Object { $_.name -in 'ollama','gpu' } | ForEach-Object { '{0}: {1} - {2}' -f $_.name, $_.state, $_.detail }`
   Expected: `ollama: ok - Ollama is running; in VRAM: qwen3:8b 5.8 GB, ...` (plus any n8n models that are loaded) and
   `gpu: ok - NVIDIA GeForce RTX 4080 Laptop GPU: X/12.0 GB VRAM in use` (X about 6–7 with only qwen3 loaded).
5. **Agent registry.**
   `(Invoke-RestMethod http://127.0.0.1:8000/api/agents).agents | ForEach-Object { '{0}: {1} {2} ({3})' -f $_.type, $_.provider, $_.model, $_.privacy }`
   Expected: 5 lines (advisor, planner, financial_analyst, librarian, verifier), each `ollama qwen3:8b (local)`.
6. **The real Ollama run: "What's our runway?" with lineage, timed.**
   `$s = [Diagnostics.Stopwatch]::StartNew(); $r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "What''s our runway?", "stream": false}' -TimeoutSec 900; '{0:n1} s | {1} = {2} {3} | verified {4} | {5}' -f $s.Elapsed.TotalSeconds, $r.metrics[0].label, $r.metrics[0].value, $r.metrics[0].unit, $r.verified, $r.answer`
   Expected: about **15–20 s** (measured 14.6–19.5 s with the model loaded) `| Runway (actual burn) = 10.65 months | verified
   True |` followed by a 2–3 sentence answer that says 10.65 months and ends with a question.
   Lineage: `'{0} | {1} | {2}' -f $r.metrics[0].lineage.formula, $r.metrics[0].lineage.period, ($r.metrics[0].lineage.source_files -join ',')`
   Expected: `closing_balance[2026-10] / net_burn  (net_burn = average over 3 month(s)) | 2026-08..2026-10 | northwind_financials.xlsx`
   (the period may print slightly differently; the formula and file must match).
   Who did what: `'{0} via {1} {2}; tools {3}; advisor {4}; plan/agents/advise ms {5}/{6}/{7}' -f $r.agents[0].name, $r.agents[0].provider, $r.agents[0].model, ($r.agents[0].tool_calls.tool -join ','), $r.advisor_provider, $r.timings_ms.plan, $r.timings_ms.agents, $r.timings_ms.advise`
   Expected: `Financial Analyst via ollama qwen3:8b; tools get_metric; advisor ollama; ...` (agents ~7–13 s, advise ~6 s).
7. **Streaming (SSE).** PowerShell 5.1 has no streaming client, so use `curl.exe` with a body file:
   `Set-Content -Path $env:TEMP\ask.json -Value '{"message": "What''s our runway?"}' -Encoding ascii; $out = curl.exe -s -N -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" --data-binary "@$env:TEMP\ask.json"; ($out | Select-String '^event:' | ForEach-Object { $_.Line.Substring(7) } | Group-Object | ForEach-Object { '{0} x{1}' -f $_.Name, $_.Count }) -join ', '`
   Expected: one line containing `team.proposed x1`, `agent.spawned x1`, `agent.tool_call x1`, `agent.artifact x1`,
   `agent.done x1`, `delta xN` (N about 2–5: the Advisor's sentences, each checked before it is sent), `run.finished x1`, `done x1`.
8. **Librarian with citations.**
   `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "What do my notes say about annual prepayment?", "stream": false}' -TimeoutSec 900; '{0:n1} s | intent {1} | verified {2} | cites {3}' -f ($r.elapsed_ms/1000), $r.intent, $r.verified, (($r.citations.path | Select-Object -Unique) -join ', ')`
   Expected: about **10–40 s** `| intent knowledge | verified True | cites notes/pricing-strategy.md`, and
   `$r.agents[0].text` quotes the 15 % discount with `[notes/pricing-strategy.md]`. See also RT5.
9. **A decision: Planner team, scenario, no LLM arithmetic.**
   `$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "Should we hire two more SDRs next quarter?", "stream": false}' -TimeoutSec 900; '{0:n1} s | {1} | team {2} | verified {3} | {4}' -f ($r.elapsed_ms/1000), $r.planner, (($r.agents | ForEach-Object { $_.name + ':' + ($_.tool_calls.tool -join '+') }) -join ', '), $r.verified, $r.answer`
   Expected: about **25–45 s** `| rules; team by LLM | team ..., Librarian:past_decisions+search_vault |
   verified True |` and an answer that leads with the decision already on record (see RT3 and RT4). The analyst's
   runway 11.23 → 9.81 months is in `$r.agents` (computed in code: `runway_change_months`). LLM plans vary: another
   valid team (e.g. two analysts plus the Librarian, or a second Librarian) is fine if `verified` is True.
10. **Live Agent Activity events.** In a second PowerShell window run
    `curl.exe -s -N "http://127.0.0.1:8000/api/events"`, then repeat step 6 in the first window.
    Expected: the second window prints `event: run.started`, `team.proposed`, `agent.status` (queued, thinking,
    querying_data, verifying, done), `agent.step` with `running get_metric(name=\"runway\")`, ..., `run.finished`;
    when idle it prints `: keep-alive` every 15 s and stays open. Close it with Ctrl+C.
11. **Decision log.** `(Get-Content .\data\default\decision_log.jsonl | Measure-Object -Line).Lines`
    Expected: a number (≥ 0). It grows only when a message is ambiguous, e.g. after
    `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"message": "Tell me about Fabrikam", "stream": false}' -TimeoutSec 900 | Select-Object intent, planner`
    → planner `decision model (llm:qwen3:8b, p=...)` (or "unsure ... default team"), and the count goes up by 1.
12. **Fallback without the LLM (optional; pauses Ollama for n8n too).** `docker stop ollama`, repeat step 6.
    Expected: in a few seconds, `| Runway (actual burn) = 10.65 months | verified True | Runway (actual burn): 10.65
    months as of 2026-10. (Answer assembled without the language model.)`. Then `docker start ollama`. The next
    question loads the model first (up to ~4 min from cold, see the backend log line `loading it first`) and then
    answers with the LLM again.
13. **Regression.** `(Invoke-RestMethod http://127.0.0.1:8000/api/metrics/runway).value` → **10.65**;
    `(Invoke-RestMethod http://127.0.0.1:8000/api/search -Body @{q='annual prepayment discount'; mode='bm25'; k=1}).results[0].path`
    → `notes/pricing-strategy.md`; http://127.0.0.1:3000 still loads with the health strip.
14. **Founder feedback re-test ("(None)" warning).** With Ollama stopped (step 12) run
    `(Invoke-RestMethod http://127.0.0.1:8000/api/search -Body @{q='churn'}).warnings` three times within 30 s.
    Expected: every time `semantic search unavailable (Ollama embeddings failed (ConnectError: ...)); using keyword
    search (BM25) only`, and **never** `(None)`.

## Founder feedback
_Write results from your Windows checks, bugs and change requests here. The next session acts on them first._
### [M3b → M3c, first task] Decision prose still contradicts the structured frame (not blocking)
- Dubai memo (RD3): the Decision text says the travel-led pilot "aligns with the goal of extending runway past 12 months", but the Goal check (correctly) says it moves away from that goal (runway 10.65, pilot -0.21). Add a code check: Decision/answer text must never contradict goal statuses in the decision frame.
- Rejected alternatives: "Partner or distributor: Not proposed, though it takes no more runway than Travel-led pilot" gives no reason. A cheaper option that is not proposed must carry a reason (control, speed, reversibility).
- Agents off-brief: People & Ops says "stop non-essential travel" for a travel-led pilot and "depends on one person: you, you"; Regulatory & Tax talks about a physical office when a pilot is proposed; Librarian writes "You have already decided to 'Decide whether…'"; Devil's Advocate suggests using the vault for market data the Scout said is not there.
- Handle with M3c's offline prompt tuning against the eval set (add these cases to it), plus the code check above.
- Priority: medium

### [M3b] Dubai decision: plumbing works, decision reasoning is not trustworthy: RESOLVED (founder re-test RD1–RD10 pending)
**Fixed 2026-11-05, items 1–10;** see "Decision frame" under Current state. Item 10 (narration grouping, the specific question) is done in the backend lane too. A new `new_product` type was added beyond the list below.
M1–M11 otherwise pass. The run was "Should we open a Dubai office? Write a decision memo."
1. Wrong cost model: the office was modelled as "1 hire at $11,423.62/month, -0.76 months" ("not a quote for this role"). Decisions need a type (hire N people / new office or region / pricing change / spend change / fundraise / other). Multi-component decisions need a cost model with one-off and recurring costs. Inputs not in the data are founder-editable assumptions labelled "assumption, confirm", never shown as verified, with a low/base/high runway impact from `run_scenario`. Ask the founder for the 2–3 key inputs through the conversation lane. Never present a one-hire cost as the cost of a non-hire decision.
2. Goals are not decisions: the Librarian and memo said "the founder has decided to expand into a second sales region", but `profile/company.md` only has the goal "Decide whether to open a second sales region".
3. Goal awareness: compare every decision with the goals in `profile/company.md` (here "Extend runway past 12 months without new financing", with runway at 10.65) and say plainly when a decision moves away from one.
4. Memo consistency, enforced in code: exactly one chosen option, not under "Rejected alternatives", and the Decision text matches it. (The memo said "delay until research" but rejected both "open now" and "delay".)
5. Predictions must be outcomes (metric + threshold + date), not tasks. Never leave "[figure removed: no lineage]" in a memo: rewrite the sentence or move it to "Open numbers to confirm".
6. Kill criteria must be measurable (metric, threshold, date) and consistent with the cost model.
7. The Metrics section is for a founder: one plain sentence per figure with a short lineage note, no raw formula dumps, and only figures relevant to this decision (not the $308,437.67 payroll total).
8. Role discipline: specialists stay in role (People & Ops wrote its own "Decision Memo" and said "stop hiring SDRs" without basis). "Your adviser", not "Legal Team / Tax Team". Second person everywhere, including the memo and team findings.
9. Options: a memo compares realistic alternatives with their costs (for a new region: travel-led pilot, one remote rep, partner/distributor, free-zone desk, full office).
10. Narration (low priority, for M5): group "X finished" lines ("Analyst and Librarian are done; two to go"), and make the assumption question specific to the run's real brief.

### [M3a → M3b] Small items found in the M3a re-test (not blocking): RESOLVED
**Fixed in M3b.** Journal: 3 full live rounds reproduced no order or state effect. The search returned the journal at rank 2 and the model sometimes cited only the churn note, so this was the model's choice varying, not state. Code now guarantees it: asked what "my journal" says, an answer with no journal source gets the journal's own passage and path (`_surface_named_folder`). Advisor: code turns "the founder" into "you" and writes money one way (`in_one_voice`). API: JSON answers send `application/json; charset=utf-8`.
- Live eval `journal` question passes 4/4 when run alone (`--only journal`) but failed in 2 of 3 full `--live` runs (did not cite journal/2026-10-28.md). Likely an order or state effect between questions; investigate and make the full run pass reliably.
- Advisor wording: says "The founder has already committed..." instead of "You have..."; mixes "$11,423.62" and "11,423.62 USD" in one answer. Use second person and one money format.
- Windows PowerShell 5.1 shows curly apostrophes as "â€™" (display only; check the API sends `charset=utf-8`).
- Priority: low
### [M3a] Verifier passes a correct number with the wrong meaning
- Did: RT6 "Should we hire a designer?".
- Got: "The financial impact of hiring a designer would be a monthly cost of $308,437.67, reducing runway by that amount." and verified = True. Wrong twice: $308,437.67 is not a designer's cost (it is some other tool figure), and runway is in months, not dollars.
- Expected: a "verified" answer never attaches a tool figure to a different quantity or unit; otherwise it is not verified and the figure is replaced by a code-written sentence (as the existing fallbacks do). RT1–RT9 otherwise pass (RT8 7/8, then journal passed 2/2 on re-run).

- **Resolved (2026-11-04, PR #6; re-test: checklist steps RV1–RV9).** Root cause, seen in 4 of 4 live runs before the fix:
  - **The figure:** 308,437.67 is `get_metric headcount_cost`, the whole company's monthly payroll for 27 people. It is in no scenario output (the earlier note in "Known limits" guessing a scenario figure was wrong).
  - **The Analyst:** asked "the cost of hiring a designer", it called `get_metric headcount_cost` and never ran `run_scenario`, so there was no `new_hires` and no `cost_per_hire`.
  - **The Verifier:** it kept tool numbers as bare floats, so any real value passed, whatever the sentence said it was.
  - **The Advisor:** it reused the figure because the Analyst's text was "verified", and the metric card line put the raw total in its findings.
- **The fix:**
  - Every tool number is now a `Fact` with the label, unit, quantity and flow-or-balance of its field. The Verifier checks the claim around a figure, by rules only, with no LLM judge (`check_claims` in `verifier.py`).
  - A failing Analyst sentence is sent back once, then replaced by a code-written one, and the answer stays unverified. A failing Advisor sentence is replaced before it is streamed.
  - For a hire the founder counts ("a designer", "two SDRs"), code runs the scenario first. `decision_impact` (`cost_per_hire_monthly`, `monthly_cost_delta`, `runway_change_months` and others) is computed in code, returned by `/api/chat`, and given to the Advisor in place of raw totals. If the Advisor leaves it out, code adds it.
- **Correct figures:** one hire costs 11,423.62 a month (the company's average loaded cost, not a quote for a designer) and moves projected runway from 11.23 to 10.47 months (-0.76).

### [M3a] Librarian misses a past decision on the same topic
- Did: asked "Should we hire two more SDRs next quarter?" (checklist step 9). Steps 1–9 and 11 otherwise pass.
- Got: Librarian searched twice, then said "no specific SDR performance metrics or conversion rates are available". But `decisions/2026-09-hire-two-sdrs.md` exists: decided 2026-09-15, kill criterion "if qualified meetings per SDR stay under eight a month by December, pause the second seat", prediction 70%, review_date 2026-12-15. Separately, in step 8 the Librarian cited `decisions/2026-09-hire-two-sdrs.md` without using it.
- Expected: the answer says we already hired two SDRs in September and asks whether they hit the kill criterion before the 15 Dec review.
- **Resolved (2026-11-04, PR #6; re-test: checklist steps RT1–RT9).** Findings from checking each suspect:
  1. **Frontmatter: root cause.** `status`, `date`, `review_date` and `prediction` never reached the chunks, the search results or `read_note`, so the model could not see them whatever it did.
  2. **Stemming: root cause, not on your list.** Keyword search had none, so the Planner's "SDR" did not match "SDRs". The Planner's narrow brief ("SDR performance metrics") then matched little.
  3. **Librarian prompt: root cause.** Nothing made it check for prior decisions or answer beyond the brief.
  4. **The 900-character cut: not the cause here.** This note is 652 characters. It was a real defect for long notes, because a match late in a note was cut off. Fixed.
  5. **Ranking of `decisions/`: not the cause.** The note ranked second for your question. No boost was added; code now looks up decisions directly.
  6. **Step 8: separate bug.** `citations` listed everything the search returned, whether or not the answer used it.
  The fix is general, with nothing specific to SDRs. Details are under "Current state". The live eval found 4 more problems, all fixed with tests: the model limiting its only search to one folder and inventing an answer, the Advisor inventing a past decision when told about them in general, "by December" passing as the 15 December review, and "What do my notes say about churn?" going to the Analyst.

### [M2] Fallback warning shows "(None)" instead of the reason
- Did: stopped the Ollama container, then searched
- Expected: warning names the reason, e.g. "Ollama not reachable"
- Got: `semantic search unavailable (None); using keyword search (BM25) only` (the first search had the full ConnectError reason; later searches during the 30 s retry window show None)
- Priority: low (fix at the start of M3a)
- **Resolved (2026-11-03, M3a PR):** the retry thread found nothing to embed and cleared the error without asking the embedder, racing with the warning text. The sync now checks the embedder before clearing an error, and the warning reads the error once. Regression test `test_embedder_down_after_indexing_keeps_the_reason`. Re-test: checklist step 14.

### [Setup] Ollama runs in Docker on the founder's PC; qwen2.5 not pullable yet
- Ollama is the `ollama/ollama:0.32.1` container from my n8n stack (port 11434, GPU confirmed: 100% GPU). There is no `ollama` command on Windows, so setup.bat warns "Ollama not found" (harmless)
- `nomic-embed-text` pulled OK. Every `qwen2.5:7b*` tag fails at "pulling manifest: EOF" (other models pull fine), so health shows "Ollama (degraded)"
- Decision needed before M3a: retry qwen2.5, switch to a newer Qwen, or use another local model; record it in PRD §12
- Priority: medium (blocks the M3a Ollama run, not M2)
- **Resolved (2026-11-03, M3a PR), per the founder's decisions:** Ollama is an external service at `OLLAMA_BASE_URL`. `setup.bat` detects it over HTTP (`/api/version`), reports each model from `/api/tags`, and without the CLI prints `docker exec ollama ollama pull <model>`. The chat model is now `qwen3:8b` with thinking off (config default and `.env.example`). Tool calling was verified live, and health shows VRAM per loaded model. Recorded in PRD §12. Re-test: checklist steps 1–6.
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
1. **Ollama model storage (performance, optional).** Your `ollama` container mounts its models from `C:/Dev_Tools/LLM Models/ollama` (a Windows bind mount). Every Ollama request spends ~3.7 s before inference (`/api/tags` alone ~1.2 s), and a cold load of qwen3:8b takes ~3.5 min. A Docker named volume (or a folder inside WSL) usually cuts both to seconds, which would make answers 2–3x faster (runway: ~15–20 s now, likely ~5 s). It is your n8n stack, so I changed nothing. FounderOS works either way: it preloads the model at startup and loads it before a call when needed. Your call whether to move it.

Answered (2026-11-03, founder note at the start of the M1 session):
1. ~~Demo currency~~: **keep USD** for the shipped `sample_data/` (INR stays available with `--currency INR`).
2. ~~Demo runway~~: **keep runway at about 10 months** at the end of the data window.

## Decisions made
See PRD §12 (Decision log). Summary of the planning session on 2026-11-02:
- New repo, text-first build order (voice last), milestone-based sessions of about 2 hours.
- *(Replaced 2026-11-04: Claude needs an API key, see PRD §12.)* Ollama is the default LLM. Deep-work agents (risk, memo, scout) can use Claude via the **Claude Agent SDK on the founder's subscription** (`CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`), Anthropic API or Gemini, with automatic fallback to Ollama.
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

### M3b fix session (2026-11-05)
- Recorded the feedback first. Built the decision frame, guards, memo enforcement, role and voice rules, narration grouping; each with tests.
- Live on `qwen3:8b` (scratch backend, port 8011, your vault untouched), Dubai took about 2 to 4 minutes per run. Live runs showed what the fakes could not: duplicated option notes, rejected reasons repeating the description, a Goal check silent on the proposed option, "aligns with the goal" beside a runway loss, "assumptions are confirmed" listed as an assumption, an empty Regulatory answer, "use the web_search tool", and a churn stop rule already passed today. All fixed, with regression tests.
- Self-review (`/code-review medium`): 10 findings, all fixed: loose goal matching, "expand into a product" typed as an office, a smaller option inheriting the full model's MRR, stop-rule limits judged against the full model and misread ("$400k"), the Analyst's true figures being dropped, past decisions and decided memos treated wrongly as sources, false-comfort filter ignoring negation, ordinary "CRM tool" advice treated as tool talk.
- Results: `pytest` 820 passed, ruff clean, offline agent eval 24/24, vault eval 18/18. Live eval 11/12 before the last fixes; the miss was the churn stop rule, now fixed, and new-product-line was re-run on the final code. RD3–RD9 ran in PowerShell 5.1 on the final code bar the one-word "Founder's" fix.
- Process slip: one checkpoint was staged with `git add app tests` rather than explicit paths. I checked its contents: only intended files. It was not pushed alone.

### M3b session (2026-11-04)
- Tidied the stale status lines. Re-checked Anthropic's docs (decision in PRD §12).
- Cloud layer, privacy filter, cost ledger and cap, small items: committed and pushed.
- Specialists, stages, memo, cancel and re-run, conversation lane: committed and pushed.
- Live on `qwen3:8b` on a scratch test backend (cloud off): the Dubai run, the lane under GPU load, live vault eval 9/9, live agent eval 8/8. Scratch data only, the founder's vault was not touched.
- Self-review (`/code-review medium`): 10 findings, all fixed with tests: the privacy filter let short rows and unparseable results through; turns like "Cancel the Acme contract" counted as a stop; a second amendment could orphan a run; a run ending mid-classification lost a question; removing a figure could corrupt a backed one; a placeholder prediction was stored as a forecast; a rejected team was called an answer; Gemini and Anthropic tool histories were in a form those APIs refuse.
- Live checklist run found one more: the Advisor called a proposed memo something "you already decided". Records now say "not decided yet", and a memo no longer has a `date` read as its decision day.
- 2026-11-04 (second M3a bug-fix session, local on the founder's PC): acted on "[M3a] Verifier passes a correct number with the wrong meaning". Traced 308,437.67 to `headcount_cost` in 4 of 4 live runs. Added typed facts, claim checks, a code-run scenario for counted hires, `decision_impact`, and a sentence-by-sentence gate on the Advisor. Self-review (`/code-review medium`) gave 10 findings: 9 fixed with regression tests, and of the conventions finding only the duplicate code was fixed (see Decisions). Backend 576 tests pass, ruff clean, offline eval 18/18, live eval 9/9 on the final code, RV commands run in PowerShell 5.1 against a test backend on another port.
- 2026-11-04 (M3a bug-fix session, local on the founder's PC, ~03:19 UTC onwards): acted on the founder's review, "[M3a] Librarian misses a past decision". Added decision records, searchable frontmatter, a stemmer, centred passages, code-run decision lookup and whole-vault search for the Librarian, a guarantee that a past decision's facts reach the answer, citations limited to sources used, and an eval over the sample vault (`scripts/eval_vault.py`, offline 16/16). Ran the live eval on Ollama: 6/8, then 4/8 (a stricter check and a prompt change that backfired), 7/8, then 8/8. The self-review (`/code-review medium`) found 10 issues, all fixed with regression tests: written dates hid figures after a month name ("March 45"), an honest "nothing found" was sent back, the year in a file name counted as a topic word, decisions not taken were called decided, paths with spaces and `.markdown` lost their citation, mentions of kill criteria became criteria, mixed questions lost the Analyst, unrelated wording counted as stating a fact, search JSON could be cut, and frontmatter did not count for topic matching. Then all RT steps ran in PowerShell 5.1 with the expected lines, and the live eval passed 8/8. The live runs used the founder's `vault/default` and may have added a few lines to `data/default/decision_log.jsonl`; RT7's test note was deleted. 487 backend tests (90 new).
- 2026-11-03 (M3a session, 16:16 to ~17:45 UTC, local on the founder's PC): fixed the "(None)" warning; setup detects Ollama over HTTP; `app/llm` (Ollama/Anthropic/Gemini/Claude SDK/Fake, router), `app/decision`, `app/agents` (registry, prompts, tools, runtime, Verifier, LangGraph graph, events), `/api/chat`, `/api/events`, `/api/runs`, `/api/agents`, VRAM in health. The live Ollama run found 4 problems, all fixed with tests: (1) a 217 s cold load from the Docker bind mount was aborted by the 180 s chat timeout (now preload plus load-before-call; re-checked live: the first answer after an unload took 222 s and came from the LLM); (2) the analyst invented `month=2023-10` (now told the data range); (3) an LLM subtraction (11.23 − 9.81) passed the Verifier by matching the full scenario payload (now code-computed deltas and only numbers the model saw count); (4) a duplicate `run.finished` frame. The self-review (`/code-review high`) found 10 issues, all fixed with regression tests: the `/api/events` keep-alive killed the stream, a cut-off Advisor stream got a template appended, timed-out approvals looked open, non-object planner JSON crashed the run, Planner-written briefs whitelisted numbers, `DECISION_MIN_CONFIDENCE` had no effect, the Librarian citation rule never fired, the tolerance rejected correct rounding (`$1.2M`), the intent decision id was dropped, and `OLLAMA_WARMUP` was missing from `.env.example`. 397 backend tests.
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

## Decisions made (M3b fix session, 2026-11-05)
In PRD §12: the decision frame is code, built before the agents.
- New decision type `new_product`, beyond the founder's list: a new line has its own cost shape and would otherwise be `other`.
- Placeholder cost inputs in `_TEMPLATES` are round starting points, not market data, and always carry "assumption, confirm". No web lookup: cloud is off.
- Starter predictions and stop rules are labelled for the founder to set, and are not stored in the calibration store: scoring a placeholder would corrupt calibration.
- A proposed memo backs no figures in later runs; a decided one does.
- For a non-hire with a cost model the agents do not get `run_scenario` or `run_monte_carlo`: the frame has run them, so a model cannot offer a one-hire figure.

## Decisions made (M3b session, 2026-11-04)
Significant ones are in PRD §12: no Claude subscription path and the cloud layer; two lanes; stages rather than `depends_on`.
- A rerun of a finished agent in a still-running team is refused (409): its findings already went to the next stage, so re-running it alone would leave the rest out of date. Once the run has finished, a rerun starts a new run of the whole team with that brief edited.
- The Memo Writer joins only on an explicit request, so live evals and everyday questions do not write to the vault.
- People & Ops is called by "capacity", "key-person", "execution plan", "team structure" and similar, not by plain "hire": the Planner may still add it, and hiring questions keep their existing team and evals.
- The lane's narration is templates, not the small model: it cannot invent progress, and it works with no fast model installed.
- An idle turn uses rules only: with nothing running, an unclear turn is just a request, so it does not wait for a model first.
- `Regulatory & Tax` and `Market Scout` have privacy class `cloud`: with cloud on they need team approval, and they fall back to Ollama and the vault otherwise.

## Decisions made (second M3a bug-fix session, 2026-11-04)
- The cost of a hire is the company's average loaded cost (payroll / headcount), labelled as an average. `cost_per_hire_monthly` stays out of the tool spec the model sees, because a cost the model made up would produce "verified" numbers. A cost the code is given is called "stated", not average.
- Advisor streaming changed from per word to per sentence, because a sentence must be checked before the founder sees it. This is a visible change. Sentence-sized pieces should also suit voice later.
- A clause that names nothing can't be judged, so its figure is checked by value and unit only. The exception is a hire decision: there, a sum of money in such a clause is read as the hire's cost. This can occasionally replace a correct sentence, which seemed better than passing a wrong one.
- Query columns (`run_sql`) carry no meaning, because the model names them itself. They are checked by value, and can't count as the cost of a hire.
- No impact is produced when a scenario also moves another lever (the runway change wouldn't be the cost's alone), or when there is no payroll to average (0.00 would read as a free hire).
- The first scenario of a run is the decision's impact. Later ones are the model exploring.
- Self-review's conventions finding, partly left: the one-line findings heading for the impact stays in code, next to the other findings headings. The hire parsing also stays in two places with different word lists, since one counts people and the other finds the role. Worth merging in M3b if it grows.

## Decisions made (M3a bug-fix session, 2026-11-04)
- Facts of a past decision are guaranteed by code, not prompts: a small local model ignored instructions in live runs, so code does the lookup, gives the record to the model and adds whatever the answer leaves out. No second LLM call.
- No ranking boost for `decisions/`: dense search always returns something, so a boost would surface decisions on other topics. "On topic" is decided by words (see `decision_matches`).
- The sample note is unchanged: its kill criterion is read from the body, so the copy already in your vault works as it is.
- Outside the original list: `rule_intent` now sends questions that name the notes to the Librarian. The live eval showed the Analyst answering them with "I have no tool for notes".

## Decisions made (M3a session)
- Founder decisions (recorded in PRD §12): Ollama is an external service (the `ollama` Docker container, port 11434, GPU, shared with n8n) detected over HTTP; the chat model is `qwen3:8b` with thinking off; the EmbeddingGemma vs nomic comparison moves to M3c.
- Providers live in `app/llm/` with the cloud ones in one module (`cloud.py`). Anthropic and Gemini are called over REST with httpx (no SDK dependency, faked with `httpx.MockTransport`); the Claude Agent SDK is imported lazily. All agent code reads model IDs from config.
- The Verifier is deterministic code, not an LLM. Numbers must match what the model was shown by tools, within the written rounding or 1 %. Derived values (e.g. `runway_change_months`) are computed in tool code, so the model never subtracts.
- Intent routing goes rules first, then the decision model (qwen3:8b misrouted a clear finance question in a raw test). A low-confidence intent gets the default team (Analyst + Librarian).
- Every agent has a rules fallback (R3): without the LLM, the runway question still returns 10.65 with lineage.
- Ollama calls make sure the model is loaded first (`/api/ps`, then `/api/generate` with a 20-minute timeout), because a slow cold load would otherwise be aborted by every chat call. The chat model is also preloaded at startup (`OLLAMA_WARMUP`).
- Run state lives in memory (`AgentOrchestrator.runs`, last 100 runs; the event bus keeps 2,000 events). Persistent run history can come with M4 if needed.

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
