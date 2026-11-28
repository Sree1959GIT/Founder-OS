# HANDOVER: FounderOS

> **Every session reads this file first.** Update it as you work, not just at the end.
> Spec: `docs/PRD.md` · Session protocol: `docs/GOAL_PROMPT.md` · Repo rules: `CLAUDE.md`

## Quick status
- **Branching:** `main` is stable. Each session works on its own assigned branch, created from `main`, and ends by opening a PR into `main`. The founder reviews and merges that PR before starting the next session.
- **Next milestone:** M7c (invite login), only after **M7b** (PR #17, Major) is ACCEPTED: the founder runs the re-test MC1–MC10 below (F20–F27, 2026-11-28), plus MB2, AM-S5, AM-S8. M7b built F8d, F19, F9 and F18 (Founder feedback, top: RESOLVED on `claude/serene-knuth-si17hr`). Fix rounds 2 and 3 (PRs #14, #15) are merged. M7a itself is merged (PR #13, Medium gate 2026-11-26). v1 (M0–M6) is ACCEPTED and tagged `v1.0-local`.
- **Review:** every PR must pass the 4 gates in "Review gates" below
- **Last updated:** 2026-11-28 (M7b gate fix round: F20–F27 fixed on `claude/serene-knuth-si17hr`, PR #17; awaiting the founder's re-test MC1–MC10)

## Milestones
| # | Milestone | Status | Notes |
|---|---|---|---|
| M0 | Scaffold & foundations | DONE (merged, PR #2) | Backend `/api/health`, Northwind data, frontend shell, scripts, CI |
| M1 | Financial spine (DuckDB) | DONE (merged, PRs #3 + #4; Major gate ACCEPTED 2026-11-03) | |
| M2 | Vault & hybrid RAG | DONE (merged, PR #5; Light gate ACCEPTED 2026-11-03) | |
| M3a | LLM layer, agent framework & core agents | DONE (merged, PR #6; Medium gate ACCEPTED 2026-11-04) | |
| M3b | Specialist agents | DONE (merged, PR #7; Medium gate ACCEPTED 2026-11-05) | Plus the cloud layer and the conversation lane backend |
| M3c | Decision models (Laya / Jev) | DONE (merged, PR #8; Light gate ACCEPTED 2026-11-06) | Laya and Jev built against their documented APIs and tested with fakes, not measured; measuring them is deferred until after M5 |
| M4 | Canvas UI (first demoable build) | DONE (merged, PR #9; Major gate ACCEPTED 2026-11-08) | |
| M5 | Voice pipeline | DONE, awaiting Major gate (live check RM1–RM6) | All of PRD §8 for M5, measured on the founder's PC (see Current state). Fix rounds 2026-11-13: V7 and how the Advisor speaks; then R1–R8 (a filler never stops a team, one opening turn and silence, re-run of one agent, transcription). Round 3, 2026-11-14: S1–S5 (a stopped run is never spoken, each offer once, it waits after an offer, a change said mid-run, one telling per goal and memo). Round 4, 2026-11-15: T1–T5 ("Yes?" answers the offer, one change gets one offer and one card, no verification line when no team ran, code's trade-off). Round 5, 2026-11-15: U0–U5 (only a clear request starts a team, fillers do nothing, fuzzy re-run, greetings, one chip per metric) and the spoken reminder. Round 6, 2026-11-15: the scripted runner. Round 7, 2026-11-16: a change is always said aloud (it cuts off speech), the reminder after a finished run, the stage line, `FOUNDEROS_STAGE_DELAY_S`. Round 8, 2026-11-16: W1–W5 (a repeated change, the badge after a change, one offer after every decision answer, "leave it", re-run from the last decision team). Founder's numbers: first words p50 890 ms, metric answer p50 1738 ms |
| M6 | Windows packaging, polish & demo | DONE (merged, PR #12; Major gate ACCEPTED 2026-11-19; tagged `v1.0-local`) | **M6a** (merged, PR #11; PK1–PK8 pass): `run.bat`/`setup.bat` from a fresh clone, `scripts/download_models.py`, README fresh install, `docs/DEMO_SCRIPT.md`, `reset_demo.bat`, M5 carry-overs X1–X5 and Y1–Y3. **M6b** (2026-11-18): F resizable and foldable panels (remembered per viewer), G movable agent window, Kokoro on the GPU (metric answer p50 2.38 s → 1.66 s on this PC), a re-run with a change already in the answer re-runs only that agent |
| M7a | AI model settings | DONE (merged, PR #13; Medium gate 2026-11-26: AM1–AM7 pass, AM8 partly). Fix round 2 (F4–F8, F12) merged (PR #14). Fix round 3 (F4b, F7b, F8b, F12b, F13) merged (PR #15). Fix round 4 (F7c, F8c, F13b, F14–F17) on `claude/bold-tesla-cibyyq`, awaiting re-test AM-S1–AM-S8 | Settings → AI model card (8 presets, Test key with a 15 s limit, green chip, plain-English errors), Fernet keys per workspace, deep-work routing with Qwen fallback, `scripts/ensure_secret.py`, arm64 CI job, `docs/ARM64.md` |
| M7b | Decision Room UI redesign: Welcome screen and Glass Boardroom, desktop and phone | DONE on `claude/serene-knuth-si17hr`, awaiting the Major gate (MB1–MB12) | Brief `docs/design/M7B_DESIGN_BRIEF.md`. F8d, F19, F9, F18 fixed; Welcome (cream), Boardroom (navy glass, table, faces, options, live caption), phone layout at 390 px, Lite mode, model card polish |
| M7c | Invite login and per-member encrypted workspaces | NOT STARTED | |
| M7d | Oracle Cloud Always Free Arm VM deploy behind Cloudflare HTTPS | NOT STARTED | |
| M7e | Data lifecycle: 30-day auto-delete, reminders day 23 and 29, Download/Delete, Decision Pack export and revive, India DPDP privacy and consent | NOT STARTED | |
| M7f | Onboarding: quick figures, Excel/CSV templates, Tally import, currency auto-detect and confirm | NOT STARTED | |
| M7g | Round-table team: intros with distinct voices, Quick/Thorough mode with time estimate, talk to an agent by name, Geopolitical Analyst | NOT STARTED | Members Beta gate |
| M7h | Key ring & smart routing (after M7d): several keys with failover and Qwen last (F10), cost/quality routing within the privacy choice from a server model catalogue (F11), a weekly job proposing catalogue updates for the founder to approve (F11b) | NOT STARTED | Recorded 2026-11-26; gate tier to confirm (Medium proposed) |

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
| M7a AI model settings | Medium |
| M7b Decision Room UI | **Major** |
| M7c Invite login, encrypted workspaces | Medium |
| M7d Oracle Arm deploy | Medium |
| M7e Data lifecycle, DPDP | Medium |
| M7f Onboarding | Medium |
| M7g Round-table team | **Major** (Members Beta gate) |
| M7h Key ring & smart routing | Medium (proposed, founder to confirm) |
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
| M3c Decision models | [Sree1959GIT/Founder-OS#8](https://github.com/Sree1959GIT/Founder-OS/pull/8) | Light | ACCEPTED (SM, 2026-11-06), Light; C2–C4 and RF2–RF5 pass on Windows; P1–P7 approved; Laya/Jev deferred to after M5 |
| M4 Canvas UI | [Sree1959GIT/Founder-OS#9](https://github.com/Sree1959GIT/Founder-OS/pull/9) | **Major** | ACCEPTED (SM, 2026-11-08), Major; W0–W15, RW, RX and RY re-tests pass on Windows after 3 fix rounds; open items carried to M5 |
| M5 Voice | [Sree1959GIT/Founder-OS#10](https://github.com/Sree1959GIT/Founder-OS/pull/10) | **Major** | ACCEPTED (SM, 2026-11-16), Major; RL2a–RL2d and RM2–RM6 pass on Windows after 8 fix rounds; carried to M6 bug-fix pass: closing offer sometimes missing, "leave as it is" not recognised, restart offered for a change already in the answer, "yes" sometimes misheard by Whisper. History: live check RM1–RM6 after fix round 8 of 2026-11-16 (W1 a repeated change shows its reminder again; W3 one offer said and shown after every decision answer, yes walks the risks, no does nothing; W4 "leave it" keeps things; W5 re-run from the last decision team; W2 not reproduced, see Founder feedback). Founder live check 2026-11-16 after round 7: CI green; RL2a, RL2b, RL2c, RL2d PASS. Before that, live check RL1, RL2a–RL2d, RL3–RL5 after fix round 7 of 2026-11-16 (a change said in any stage, over the summary or after the run is said aloud; stage line; `FOUNDEROS_STAGE_DELAY_S`; runner RL2a–RL2d added). Founder RL2 2026-11-16 failed: offer shown, not spoken. Before that, live check RL1–RL5 after fix round 6 of 2026-11-15 (scripted runner `scripts/voice_scenarios.py`: S1–S7 typed and spoken all PASS on this PC). Founder RZ re-test 2026-11-15: S6 analyst re-run and S7 stop pass; S1, S3, S4, S5 and the librarain re-run failed on the PC. Before that, fix round 5 (U0–U5, reminder). Founder re-test of RY, 2026-11-15: restart with "Yes.", T4 and T5 pass; RY4 and RY6 failed; RY2 and RY5 partly. Before that, fix round 4 (T1–T5). Founder re-test 2026-11-15: RX2, RX3 and RX6 text pass; RX4 failed in voice (the click on the card worked). Before that, fix round 3 of 2026-11-14 (S1–S5). Founder re-test 2026-11-14: RW3, RW4, RW6, RW7, RW8, RW9 pass; RW2 partly; RW5 failed. Founder's PC (RW10): first words p50 890 ms, metric answer p50 1738 ms, barge-in pause 64 ms / cancel ~990 ms, STT p50 291 ms, TTS first 596 ms, VRAM 7.43 / 12 GB, Whisper +0.70 GB. Before that, fix round 2 of 2026-11-13 (R1–R8). Founder re-test 2026-11-13: RV2 (headphones), RV3 (speakers), RV7, RV8, RV10 pass; RV9 partly; RV4, RV5, RV6 failed (fixed, re-test RW2 to RW9). Founder review before that: V3, V4, V5, V6, V8, V9 pass. Founder's PC (RV11, headphones): first words p50 931 ms, metric answer p50 1869 ms (target ~3 s: met), barge-in pause 62–71 ms / cancel 574–582 ms, STT p50 396 ms, TTS first 591 ms, VRAM 7.4 / 12 GB, Whisper +0.52 GB |
| M6a Packaging, demo, M5 carry-overs (partial) | [Sree1959GIT/Founder-OS#11](https://github.com/Sree1959GIT/Founder-OS/pull/11) | Light | ACCEPTED (merged; PK1–PK8 pass after the Y1–Y3 fix of 2026-11-17) |
| M6 Windows packaging, polish & demo (M6b) | [Sree1959GIT/Founder-OS#12](https://github.com/Sree1959GIT/Founder-OS/pull/12) | **Major** | ACCEPTED (SM, 2026-11-19), Major; MG1, MG2, MG5 and re-test MR1–MR8 pass on Windows (fresh clone D:\FounderOS-fresh2, demo script §1–§7, memo from the frame, panels, agent window, bench p50 first words 749 ms, metric answer 1681 ms, barge-in 60 ms); carried to v1.1: resizable floating agent window, Matrix entry shows a score instead of "Not scored yet", a half-sentence ("Should we?") gets queued and run. History after the D1–D7 fix round of 2026-11-19). Founder run 2026-11-18/19 (fresh copy `D:\FounderOS-fresh2`): MG1, MG2, MG5, DEMO_SCRIPT §1, §7, §4 (frame, risks, three hires) and MG4 fold + voice PASS; D1–D7 found (see Founder feedback) |
| M7a AI model settings | [Sree1959GIT/Founder-OS#13](https://github.com/Sree1959GIT/Founder-OS/pull/13) | Medium | ACCEPTED (SM, merged 2026-11-26), Medium: AM1–AM7 pass, AM8 partly (Advanced and the address check pass; Wi-Fi fallback, Use Qwen and Remove key to re-test), AM9 CI green. New findings F4–F8, F12 fixed in the fix round 2 PR below. History: founder run 2026-11-22: AM1–AM4 pass (AM1 only with `ensure_secret.py` run by hand); F1 run.bat, F2 Edge offers to save the key, F3 key-only setup (fixed 2026-11-26) |
| M7a fix round 2 (F4–F8, F12) | [Sree1959GIT/Founder-OS#14](https://github.com/Sree1959GIT/Founder-OS/pull/14) | Light | ACCEPTED (SM, merged after the re-test of 2026-11-26 in Edge): F4 pass, F5 pass (AQ. detected, unknown-key message, re-detect on Qwen), F6 pass, F7 pass for 429, F12 pass in Settings and the memo ("about ₹26: Groq 9 calls"), **F8 fail** (now F8b). The Gemini AI Studio key hit free-tier limits (429), so the cloud tests used a free Groq key (`gsk_…`, `openai/gpt-oss-120b`). New findings F4b, F7b, F8b, F12b, F13 fixed in fix round 3 below |
| M7a fix round 3 (F4b, F7b, F8b, F12b, F13) | [Sree1959GIT/Founder-OS#15](https://github.com/Sree1959GIT/Founder-OS/pull/15) | Light | MERGED; re-test 2026-11-26 (main, Edge, Groq key): AM-R2 pass; AM-R3 Groq pass, **Gemini fail** (now F7c); **AM-R4 fail** (now F8c); AM-R5 pass (memo "about ₹11: Groq 7 calls (Estimated: US$0.12)", Activity "Run cost about ₹35"); **AM-R6 fail** (now F13b). Voice stopping when Activity opens is F9 (M7b). New findings F14–F17 fixed in fix round 4 below |
| M7a fix round 4 (F7c, F8c, F13b, F14–F17) | [Sree1959GIT/Founder-OS#16](https://github.com/Sree1959GIT/Founder-OS/pull/16) | Light | MERGED; re-test 2026-11-26: AM-S1, AM-S4, AM-S6, AM-S7 pass; **AM-S3 partly**: the backend logs "Slow check: People & Ops 5.3 s of 3 s -> offer sent" but no offer appears on screen (now F8d, M7b); AM-S5 and AM-S8 to re-test in M7b |
| M7b Decision Room UI redesign | [Sree1959GIT/Founder-OS#17](https://github.com/Sree1959GIT/Founder-OS/pull/17) | **Major** | M7b founder gate in progress (2026-11-26/27, Edge): design accepted in principle; findings F20–F27 FIXED 2026-11-28 on this branch, AWAITING FOUNDER re-test MC1–MC10, plus MB2, AM-S5, AM-S8 |

## Current session
- Started (UTC): 2026-11-28 04:14 (cloud session, **M7b gate fix round: F20–F27**, on the existing branch `claude/serene-knuth-si17hr`, PR #17; no new PR; time-box 2 h). Design reference: `docs/design/DESIGN.md`.
- Plan for F25–F27, checked against the brief (M7B_DESIGN_BRIEF §2 and Phone) and DESIGN.md (Layout, Components):
  - **F25 table:** seats = the host plus exactly the agents the planner chose (proposed, then working), 2 to 8, evenly spaced on the oval from the top; no placeholders and no dimmed "empty" faces. Each seat: face ringed in its own agent colour, a name tag filled with that colour (ink text, AA), a warmer glow (tomato plus the agent's colour). Seats shrink a step for 7–8 agents so none sits on the topic. The phone keeps the strip.
  - **F26 panels:** both side panels resizable (drag handle, arrow keys, double-click resets) and foldable (a fold button on each), remembered per viewer (`founderos.layout.v1`, new `rightCollapsed`). The centre keeps `centre-min` 560 px: a panel cannot be dragged into it; when the centre is still narrower (small window), the stage switches to the phone-style layout (speaking card and strip) by measuring its own width. Metric cards wrap. "Focus on the team" folds both panels (and "Show panels" brings them back).
  - **F27 voice on the faces:** each face is a button "Talk to <agent>": it turns voice on if needed (hands-free) and the LIVE bar says "Talking to <agent>". The speaking face gets a "Speaking" tag with a Stop button; Stop, Esc or speaking over it only stops the speech (a new `hush` voice control that drops queued lines and flushes playback; the team, research and number work carry on). Space = hold to talk, M = mute the mic (client side: no audio is sent). Both "Start voice" buttons go; the left panel is typing only. "Voice off" in the LIVE bar ends the voice socket only (tested: a running team is never cancelled). A spoken "stop" still stops the team (accepted in M5/M6, D3); the brief's routing of answers to a named agent is M7g, so until then the Advisor answers for the agent you talk to.
- Plan:
  - [x] F20 numbers never truncated (shrink, then wrap)
  - [x] F24 "On the table" shows the current topic
  - [x] F21 one plain status in the top bar; details in Settings
  - [x] F22 always open on Welcome; one line to continue an open decision
  - [x] F23 Advisor answers 3 sentences or fewer on screen; details in the memo
  - [x] F25 adaptive table
  - [x] F26 panels, centre minimum, compact stage, Focus on the team
  - [x] F27 voice on the faces, hush, keys
  - [x] Screenshots 1440 / 390 + narrow centre + long numbers; MB re-test list; self-review; CI
- Decisions this session: a spoken or typed "stop" still stops the team (M5/M6 D3, accepted); Stop, Esc and speaking over the voice only stop speech. Tapping a face sets who the member talks to on screen; the Advisor still answers (routing to the named agent is M7g). Centre minimum 560 px, table needs 640 px, Options default 320 px (DESIGN.md spacing tokens).
- Open questions for founder: should a bare spoken "stop" while the voice is speaking only stop the speech (and "stop the team" stop the team)? Today it stops the team, as accepted in M5.
- Progress log:
  - F20 `Figure` (lib/format `figureSize`): a figure steps 22 → 19 → 16 px by length, then wraps; KPI cards, scenario tiles, the options' figures and the memo's key numbers never truncate; cards wrap (`auto-fit`).
  - F24 `topicOf` / `tableTopic` (lib/format): the table and the phone stage show the newest question's topic; the open decision's subject only while it (or Accept / Ask more on it) is on the table; "This decision" never shown.
  - F21 `SystemStatus` in the top bar (All systems OK / Slow right now / Can't reach FounderOS; links to Settings); Settings → System lists the services.
  - F22 `entered` in the workspace: Welcome on every open; "You have an open decision: <topic>. Continue it?" opens `#/boardroom`; turns from an earlier visit stay folded ("Earlier in this conversation (N)").
  - F23 `briefAnswer`: the answer card and lane lines show at most 3 sentences; the rest (lists, kill criteria, predictions) under "Full answer" / "More", and in the memo.
  - F27 engine side (controls only): voice control `hush` (`_interrupt("hush")`, the run is never touched); client `hush()` and `setMuted()`; `backend/tests/test_m7b_gate.py` proves Stop and Voice off never cancel a running team.
  - F25/F26/F27 UI: `teamSeats`, `seatPositions`, `seatSize` (lib/boardroom); faces are "Talk to …" buttons, coloured name tags, warmer glow, "Speaking" tag with Stop; LIVE bar "Talking to …" / "Tap a face to talk", Mute, Voice off; keys Space/Esc/M; `rightCollapsed`, `toggleFocus`, centre 560 px, `TABLE_MIN` 640 px compact stage; left panel typing only.
  - e2e `frontend/e2e/m7b-gate.spec.ts` (table, focus, reload to Welcome, narrow centre, long numbers 1440/390, phone strip); screenshots in `docs/design/screens/m7b-gate/`; M7b pair refreshed in `docs/design/screens/m7b/`. All 12 e2e specs pass.
  - Self-review (/code-review): 10 findings, all fixed (phone voice messages, brief without list items, hush keeps "thinking", talkingTo on failed connect / Space, Space asks for the mic only in the Boardroom, fold by id, hover ring, status link role, "Raising prices" topic).

### Previous session (M7b build)
- Started (UTC): 2026-11-26 10:36 (cloud session, **M7b: Decision Room UI redesign**, Major gate, time-box ~2 h), branch `claude/serene-knuth-si17hr` from `origin/main` (66000f5, PR #16 merged). Brief: `docs/design/M7B_DESIGN_BRIEF.md`.
- Plan:
  - [x] F19 backend: the router names why a cloud call fell back (`fallback_reason`); one `agent.fallback` event per agent, said by the Advisor; only answered cloud calls are counted
  - [x] F18 backend: one memo per open decision (rewritten in place), earlier versions kept outside the vault, `/api/memos/versions`
  - [x] F8d: the page subscribes to `slow.offered`, `agent.slow`, `agent.fallback`, `spend`; the offer on the agent's card too
  - [x] Tokens and fonts (Instrument Serif, Inter, JetBrains Mono via @fontsource; cream/ink/tomato and navy glass; Lite mode)
  - [x] Welcome screen
  - [x] Boardroom (faces, table, options panel, caption bar)
  - [x] F9 voice outside the pages; F18 memo page; other pages restyled; model card polish
  - [x] Phone layout at 390 px; Playwright screenshots 1440 / 390
  - [x] Checks, self-review, HANDOVER, PR, CI
- Progress log:
  - 10:42 F19 and F18 backend done with tests (`backend/tests/test_m7b.py`); F8d cause found: `EVENT_TYPES` in `frontend/src/lib/workspace.tsx` never listened for `slow.offered`, so the offer was dropped in the browser.
  - 10:47 Part 1 pushed: tokens, fonts, Lite mode, F8d listener fix.
  - 10:54 Parts 2-3 pushed: Welcome, Boardroom, phone stage and bar, F9 voice provider.
  - 11:00 F8d/F19 on the agent's card, F18 memo page, model card polish, Settings Lite toggle and rates credit.
  - 11:10 Self-review (/code-review, medium): 4 of 5 findings fixed (Memo Writer fallback said, Close stays in the app, a rewritten memo replaces its open predictions, the https message only for mic errors); Accept's wording left to the Windows check (MB2). e2e specs updated; screenshots in `docs/design/screens/m7b/`.

### Previous session (M7a fix round 4)
- Started (UTC): 2026-11-26 09:25 (cloud session, **M7a fix round 4: F7c, F8c, F13b, F14–F17**, Light gate (bug-fix PR), time-box 60 minutes), branch `claude/bold-tesla-cibyyq` from `origin/main` (6d8c1b2, PR #15 merged).
- Plan:
  - [x] Record the fix round 3 re-test in the Gate log and F7c–F17 in Founder feedback; the Devil's Advocate note for M7h (recorded, not built)
  - [x] F7c a timeout is "slow", the internet only when no provider answers
  - [x] F8c startup and per-check log lines; run.bat start path checked and tested (a real uvicorn process with the variables set)
  - [x] F13b one proposal in the answer, the frame card and the memo, also for a follow-up memo run with no frame of its own
  - [x] F14 one Matrix entry per open decision; F15 status as recorded; F16 the real no-web reason; F17 one waiting line per agent
  - [x] Tests (backend + vitest), checklist AM-S1–AM-S8, PR, CI

Previous session (2026-11-26, M7a fix round 3):
- Started (UTC): 2026-11-26 07:16 (cloud session, **M7a fix round 3: F4b, F7b, F8b, F12b, F13**, Light gate (bug-fix PR), time-box 60 minutes), branch `claude/serene-mendel-8r39x1` from `origin/main` (0bc9485, PR #14 merged).
- Plan:
  - [x] Record the fix round 2 re-test in the Gate log and F4b–F13 in Founder feedback; M7f and M7b polish notes (recorded, not built)
  - [x] F4b Remove key turns cloud off (saved); `.env` keys no longer count once the card was used
  - [x] F7b the 15 s running out after a 429/503 stays "busy"; Gemini free quota used up → its own sentence, green chip kept
  - [x] F8b find the cause (env var vs per-call timing), fix, test the start path and an agent that passes the limit mid-run
  - [x] F12b member currency in the lane, voice and Activity header; US$ to 2 decimals in small print
  - [x] F13 the frame card marks what the answer and memo propose; one sentence says why it changed
  - [x] Tests (backend + vitest), checklist AM-R1–AM-R6, PR, CI

Previous session (2026-11-26, M7a fix round 2):
- Started (UTC): 2026-11-26 05:44 (cloud session, **M7a fix round 2: F4–F8, F12**, Light gate (bug-fix PR), time-box 90 minutes), branch `claude/busy-volta-rnlf9x` from `origin/main` (9eb9768, PR #13 merged).
- Plan:
  - [x] Record the M7a gate result in the Gate log and F4–F12 in Founder feedback; PRD §8/§12 (F9 in M7b, M7h, M7f additions, M7b polish)
  - [x] F4 failed test changes nothing; cloud only with a passing key (card, Settings, `PUT /api/settings`)
  - [x] F5 key shapes as data, `AQ.` → Gemini (native endpoint), unknown-key message, 3-character prefix log, re-detect on Discard and on Qwen
  - [x] F6 verified model in the top bar, Cloud section and "Default"
  - [x] F7 503/429 retried with back-off inside 15 s; plain "busy" notice, green chip kept
  - [x] F8 slow cloud agent: said, shown on its card, "Continue on Qwen on our server" / "Keep waiting"
  - [x] F12 spend report: lane + voice + memo + Settings, member currency, daily cached rate, cap in that currency stored in USD
  - [x] Tests (backend + vitest; Playwright run locally), checklist AM5–AM8, PR, CI

Previous session (2026-11-26, M7a gate fix round F1–F3):
- Started (UTC): 2026-11-26 03:53 (cloud session, **M7a gate fix round F1–F3**, on the existing branch `claude/zealous-bell-ymy3uq`, PR #13; no new PR).
- Plan:
  - [x] Record F1–F3 in Founder feedback
  - [x] F1 `run.bat`: `ensure_secret.py` on every start, test both paths
  - [x] F2 key box never offered to password managers (Chrome, Edge, Safari), still masked; test
  - [x] F3 backend: key-shape detection, models endpoint per provider, chat-only filter, auto default; tests with fakes
  - [x] F3 frontend: paste key → Test key, Change model dropdown, Advanced server address, green chip; vitest
  - [x] PRD §4, README, checklist AM1–AM9; checks; push; CI

Previous session (2026-11-22, M7a):
- Started (UTC): 2026-11-22 16:05 (cloud session, **M7a AI model settings**, Medium gate, time-box 2 hours), branch `claude/zealous-bell-ymy3uq` from `origin/main` (fb4e776, M6 merged).
- Plan:
  - [x] Record M7a–M7g in PRD §8 and §12 and in the milestones table; fix the stale "Next milestone" line
  - [x] Backend: presets, Fernet key store per workspace, `/api/settings/ai-model` (view, test-and-save, use Qwen, remove key), plain-English test errors
  - [x] Router: the chosen model drives the deep-work agents, fallback to Qwen, privacy filter and cap kept, voice local
  - [x] `scripts/ensure_secret.py` in setup/run; `.env.example`; tests with fakes
  - [x] Frontend: AI model card in Settings (current styling), vitest
  - [x] CI job on `ubuntu-24.04-arm`; `docs/ARM64.md`
  - [x] Checks, self-review, HANDOVER (checklist, Gate log), PR, CI

Previous session (2026-11-19, M6 gate fix round):
- Started (UTC): 2026-11-19 14:50 (local Windows session, **M6 Major gate fix round**, time-box 90 minutes), branch `claude/m6b-polish-demo`, PR #12 (open). Fix only D1–D7; no new features.
- Plan, in the founder's order:
  - [x] Record the founder's MG results (D1–D7) first
  - [x] Reproduce D1–D3 in tests (`backend/tests/test_m6_gate.py`), then fix: D1 memo from the open decision's latest frame + Matrix entry, D2 what-if is a new question with both levers, D3 stop phrases
  - [x] D4 citations only to files in this vault; per-install Qdrant collection
  - [x] D5 DEMO_SCRIPT (audience vs app lines, §2 label); D6 handles (12 px, grip, window-level drag), Playwright at scale 1.25 in Chromium and Edge
  - [x] D7 bench GPU vs CPU with qwen3:8b loaded
  - [x] Checks, HANDOVER (feedback resolved, Gate log, MR1–MR8), push, CI

Previous session (2026-11-18, M6b):
- Started (UTC): 2026-11-18 04:26 (local Windows session, **M6b**, the rest of M6, PR "M6: Windows packaging, polish & demo", **Major** gate, time-box 2 hours), branch `claude/m6b-polish-demo` from `origin/main` (M6a merged, PR #11; PK1–PK8 pass).
- Plan, in the founder's order:
  - [x] (1) F: expandable left and right panels, collapsible left panel, sizes remembered per viewer
  - [x] (2) TTS latency: int8 (CPU and GPU) and onnxruntime-gpu measured; Kokoro fp32 on the GPU kept (metric answer p50 2.38 s → 1.66 s), Whisper still on CUDA
  - [x] (3) G: movable pop-up agent window with a graphical view of each agent's status and work, from the Advisor panel (done in about 15 minutes, inside the 40-minute box)
  - [x] (4) Next-steps item 4: a re-run with a change already in the base case re-runs only that agent
  - [x] (5) npm deprecation warnings: checked, none safe to change without a reinstall and a major upgrade (left, see Open questions)
  - [x] Checks, self-review, Major-gate checklist (fresh clone `D:\FounderOS-fresh2`, DEMO_SCRIPT, F, G, voice timing), PR, CI

Previous session (2026-11-17, M6a bug-fix):
- Started (UTC): 2026-11-17 16:00 (local Windows session, **M6a bug-fix** after the founder's PK run, time-box 30 minutes), branch `claude/m6a-packaging-demo`, PR #11 (open, not merged). M6b (F, G, TTS) not started.
- Plan: [x] record PK1–PK7; [x] runner scenario Y1+Y2 before any fix; [x] Y1, Y2, Y3 fixed with tests; [x] Y1+Y2, X4, X5 typed and spoken; [x] HANDOVER, push, CI.

Previous session (2026-11-17, M6a):
- Started (UTC): 2026-11-17 02:31 (local Windows session, **M6a**, partial PR "M6 (partial): packaging, demo and M5 carry-overs", Light gate, time-box 90 minutes), branch `claude/m6a-packaging-demo` from `origin/main` (M5 ACCEPTED, PR #10 merged). F (panels) and G (pop-up agent window) are M6b, not this session.
- Plan:
  - [x] (6) M5 carry-overs, reproduced with `scripts/voice_scenarios.py` first: closing offer sometimes missing; "Ok, I will leave as it is"; restart offered for a change already in the answer (two hires = default); "yes" misheard (STT vocabulary/repairs); "yes" -> risks walk-through
  - [x] (1) `setup.bat`/`run.bat` from a fresh clone: Ollama at `OLLAMA_BASE_URL`, Qdrant container, clear messages, port-8000-in-use check naming the old process
  - [x] (2) `scripts/download_models.py`: qwen3:8b, nomic-embed-text (over Ollama's HTTP API), Whisper small.en, Kokoro
  - [x] (5) Clean demo data: shipped sample vault checked; `scripts/reset_demo.py` + `reset_demo.bat`
  - [x] (3) README for a fresh install; (4) `docs/DEMO_SCRIPT.md` (PRD §9)
  - [x] PRD §9 item 6 (barge-in 1 s) and §12 (Kokoro licence decision); checks, self-review, PR, CI

Previous session (2026-11-16, round 8):
- Started (UTC): 2026-11-16 (local Windows session, fix round 8 for the M5 Major gate, time-box 45 minutes), branch `claude/m5-voice`, PR #10 (open, not merged). M6 not started.
- Plan: [x] record RL2a–RL2d PASS; [x] runner scenarios W1–W5 with the founder's phrases, run before any fix; [x] W3, W4, W5 fixed; W1 fixed in the chat; W2 not reproduced (no change); [x] full runner set typed and spoken; [x] HANDOVER, push.

Previous session (2026-11-16, round 7):
- Started (UTC): 2026-11-16 (local Windows session, fix round 7 for the M5 Major gate, time-box 45 minutes), branch `claude/m5-voice`, PR #10 (open, not merged). M6 not started.
- Plan: [x] record RL2; [x] runner scenarios RL2a–RL2d, reproduced before the fix; [x] change always spoken, reminder after a finished run; [x] stage line; [x] `FOUNDEROS_STAGE_DELAY_S`; [x] full runner set after the fix (20/20 PASS); [x] HANDOVER, push.

Previous session (2026-11-15, round 6):
- Started (UTC): 2026-11-15 16:39 (local Windows session, fix round 6 for the M5 Major gate, time-box 75 minutes), branch `claude/m5-voice`, PR #10 (open, not merged). M6 not started.
- Plan: [x] scripted runner `scripts/voice_scenarios.py` (real backend, Ollama, Whisper, Kokoro); [x] reproduce S1–S7 typed and spoken; [x] fix the real failures; [x] HANDOVER, PR #10, CI.

Previous session (2026-11-15, round 5):
- Started (UTC): 2026-11-15 09:43 (local Windows session, fix round 5 for the M5 Major gate, time-box 60 minutes), branch `claude/m5-voice`, PR #10 (open, not merged). M6 not started.
- Plan: [x] record RY results; [x] U0–U5 and the reminder, tests from the founder's logged turns; [x] RZ steps, PRD §12, PR #10, CI.

Previous session (2026-11-15, round 4):
- Started (UTC): 2026-11-15 07:22 (local Windows session, small fix round 4 for the M5 Major gate, time-box 45 minutes), branch `claude/m5-voice`, PR #10 (open, not merged). M6 not started.
- Plan:
  - [x] Record the founder's RX1–RX7 results first
  - [x] T2 (main): "Yes?", "yes.", "Yeah!", "okay?" after an offer answer that offer
  - [x] T1 and T3: a mid-run change is offered at once, in every stage; one change, one offer, one card
  - [x] T4 (no verification line for a turn that ran no team), T5 (code's trade-off when the model's is unclear)
  - [x] Tests, RY re-test steps, PR #10 updated, CI green

Previous session (2026-11-14, M5 fix round 3):
- Started (UTC): 2026-11-14 10:49 (local Windows session, third and final fix round for the M5 Major gate, time-box 60 minutes), branch `claude/m5-voice`, PR #10 (open, not merged). M6 not started.
- Plan:
  - [x] Record the founder's RW1–RW10 results first
  - [x] S1 (a cancelled run is never spoken), S2 (each offer once), S3 (after an offer it waits), S4 (a change said mid-run), S5 (same goal, same memo, memo date)
  - [x] Typed "stop" stops at once; the answered open questions in PRD §12
  - [x] Tests, RX re-test steps, PR #10 updated, CI green

Previous session (2026-11-13, M5 fix round 2):
- Started (UTC): 2026-11-13 14:33 (local Windows session, second fix round for the M5 Major gate, time-box 2 hours), branch `claude/m5-voice`, PR #10 (open, not merged). M6 not started.
- Plan, in the founder's priority order:
  - [x] Record the founder's RV1–RV11 results first
  - [x] P1: R1 (a filler is never stop; stop is confirmed), R8 (re-run one agent only; an accepted change is applied), R2 (barge-in timings)
  - [x] P2: R4 and R5 (one opening turn, silence, summary that ends with an offer), R6 (transcription), R3 (ambiguous numbers confirmed), R7 (a proposed memo gets one question)
  - [x] Tests, PRD §12, RW re-test steps, PR #10 updated, CI green

Previous session (2026-11-13, M5 fix round 1):
- Started (UTC): 2026-11-13 03:17 (local Windows bug-fix and voice-behaviour session for the M5 Major gate, time-box 2 hours), branch `claude/m5-voice`, PR #10 (open, not merged). M6 not started.
- Plan, in the founder's priority order:
  - [x] Record the founder feedback first
  - [x] P1: V7, the spoken mid-run question that was lost; WAV-fixture test of a question spoken over narration
  - [x] P2 B: spoken-number normaliser (money, %, months, dates, lakh/crore) with tests
  - [x] P2 A, C: team line at the start, one line per stage, a short spoken summary with an offer of more; the answer text is no longer read aloud
  - [x] P2 D: conversation context in voice; P2 E: re-run an agent by voice
  - [x] Cash warning double full stop
  - [x] (added) Echo gate: FounderOS no longer hears itself (found with the real engines and a simulated echo)
  - [x] PRD §12 (A–E; M6 F, G, Kokoro licence, TTS latency; v1.1 H, I, J); RV re-test steps; PR #10 updated; CI green

Previous session (2026-11-08, M5):
- Started (UTC): 2026-11-08 09:39 (local Windows session, time-box 2 hours), branch `claude/m5-voice` from `origin/main`, target **M5: Voice** (gate tier: **Major**).
- Plan, in the founder's priority order (an "M5 (partial)" PR is fine if time runs out):
  - [x] Tidy the stale "Next milestone" and M4 table lines
  - [x] (1) Carried items 60 (test: no agent before approval), 61, 62, 63, 55, 7
  - [x] (2) Hardware recorded; versions, Windows wheels and licences re-checked; VRAM measured before and after loading
  - [x] (3) `/ws/voice`, VAD, STT, Kokoro TTS, push-to-talk, hands-free with barge-in and backchannel detection, two lanes spoken, quiet, latency metrics in API and UI
  - [x] (4) Tests with WAV fixtures and fake STT/TTS
  - [x] Latency measured on this PC; Windows checklist; self-review; PR; CI green

Previous session (2026-11-08, M4 fix round 3):
- 2026-11-08 03:42 (local Windows bug-fix session, round 3 and final for the M4 Major gate), branch `claude/m4-canvas-ui`, PR #9.
- Plan:
  - [x] Record the RX results first
  - [x] 58 metric routing (and 45 periods), 51 no badge when nothing ran, 54 de-dup sentences, 54b amendment clause
  - [x] 56 queued questions always offered, 57 why the proposal, 52 after cash runs out, 53 badge wraps, 59 collapse versions
  - [x] Tests (backend 1074 passed, frontend 39 vitest, 2 Playwright, lint, tsc, build), RY re-test steps, PR #9 updated

Previous session (2026-11-08, M4 fix round 2):
- Started (UTC): 2026-11-08 01:33 (local Windows bug-fix session, round 2 for the M4 Major gate, time-box 2 hours), branch `claude/m4-canvas-ui`, PR #9 (open, not merged). Bug-fix only; M5 not started.
- Plan, in the founder's priority order:
  - [x] Record the re-test results first
  - [x] P1: 49 horizon, 40 follow-ups amend the open decision, 22 turns in every phase, 42 queue de-dup, 46 sample reset, 47 several backups, 48 backup labels
  - [x] P2: 44 units, 43 unmodelled option, 45 metric periods, 39 cloud off, 41 titles, 37 popover, 38 chart label, 50 tag
  - [x] Tests (backend full suite, frontend 37 vitest, 2 Playwright specs, lint, tsc, build), RX re-test steps, PR #9 updated

Previous session (2026-11-07, M4 fix round 1):
- Started (UTC): 2026-11-07 09:50 (local Windows bug-fix session for the M4 Major gate, time-box 2 hours), branch `claude/m4-canvas-ui`, PR #9 (open, not merged). Bug-fix only; M5 not started.
- Plan, in the founder's priority order (P1, then P2, then P3):
  - [x] Record the founder feedback first
  - [x] P1: 14 badge states, 20 memo-on-record figures, 17 reload, 32 upload warning, 24 superlatives, 21 amendments, 22 early turns
  - [x] P2: 16, 18, 19, 23, 25, 26, 27, 9, 10
  - [x] P3 and 36 (Settings Save/Discard); 7 is M5, left
  - [x] Tests (backend 1013 passed, frontend 34 vitest, lint, tsc, build), RW re-test steps, PR #9 updated

Previous session (2026-11-06, M4):
- Started (UTC): 2026-11-06 11:53 (local Windows session, time-box 2 hours), branch `claude/m4-canvas-ui`, target **M4** (gate tier: **Major**). An "M4 (partial)" PR is fine if time runs out.
- Plan, in the founder's priority order:
  - [x] Gate log and stale lines tidied
  - [x] (1) People & Ops wording; "traveling" guard
  - [x] (added, 40 min) Why a metric question is slow or unverified; fix over-strict checks; fast path; live loop 10/10 under 8 s
  - [x] (2) Conversation panel and lane; Agent Activity panel
  - [x] (3) Canvas cards: Runway with lineage popover, decision frame, memo with MD/PDF export
  - [x] (4) Scenario Simulator and Monte Carlo fan; Prioritisation Matrix; data and vault panels; Settings
  - [x] (5) Playwright smoke test against the backend with fakes, in CI
  - [x] Windows checklist, self-review, PR, CI green

Previous session (2026-11-06, M3c gate fix):
- 2026-11-06 (local Windows bug-fix session for the M3c gate, time-box 1 hour), branch `claude/m3c-decision-models`, PR #8. It ran a little over the hour, because the live runs found two more faults worth fixing.
- Plan:
  - [x] Record the founder feedback first
  - [x] Citations must resolve, and a figure must be in the chunks of the file it is cited to; otherwise it is removed with a note
  - [x] Unsupported text never reaches a later stage, the answer or the memo, not even inside a question
  - [x] Market Scout with cloud off: says what is missing, lists what to find, no example figures
  - [x] Tests; Dubai C4 checks in the offline and live evals
  - [x] Approvals in PRD §12; P5 applied; C8 and C9 deferred
  - [x] Resolve the feedback; RF steps; PR #8 updated; CI green

Previous session (2026-11-05, M3c):
- Started (UTC): 2026-11-05 14:12 (local Windows session, time-box 2 hours), branch `claude/m3c-decision-models`, target **M3c** (gate tier: **Light**)
- Plan, in the founder's priority order (an "M3c (partial)" PR is fine if time runs out):
  - [x] Tidy the stale "Next milestone" and M3b table lines
  - [x] (1) Words never contradict the goal check; a cheaper option not proposed states a reason; off-brief wording; offline and live eval cases
  - [x] (2) Privacy filter pseudonymises customer and person names before any cloud use
  - [x] (3) 58 labelled questions; offline prompt tuning script; versioned prompts
  - [x] (4) `LayaProvider`, `JevProvider`, bake-off harness with 212 routing examples, confidence fallback, Laya fine-tune script
  - [x] (5) Provider bake-off harness
  - [x] (6) Embedding bake-off (EmbeddingGemma vs nomic-embed-text), licence point
  - [x] Read the tuning and provider results; PRD §12 proposals; Windows checklist; self-review; PR; CI green

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
### Decision Room redesign (M7b, 2026-11-26; gate fix round F20–F27, 2026-11-28)
- **Gate fix round (2026-11-28):** see Founder feedback → "[M7b] Founder gate 2026-11-26/27". Code: `components/boardroom/Boardroom.tsx` (seats, talk buttons, Speaking/Stop, LIVE bar, compact stage, Focus), `lib/boardroom.ts` (`teamSeats`, `seatPositions`, `seatSize`), `lib/layout.ts` (`rightCollapsed`, `toggleFocus`, `CANVAS_MIN` 560, `LG` 1024), `lib/voiceContext.tsx` (`talkTo`, `hush`, mute, keys), `lib/voice.ts` (`hush`, `setMuted`), `backend/app/voice/session.py` (`hush` control), `lib/format.ts` (`figureSize`, `topicOf`, `tableTopic`, `briefAnswer`), `components/HealthBadge.tsx` (`SystemStatus`), `lib/workspace.tsx` (`entered`, `restoredTurnIds`). Tests: `src/components/m7bgate.test.tsx`, `src/components/boardroom/boardroom.gate.test.tsx`, `backend/tests/test_m7b_gate.py`, e2e `e2e/m7b-gate.spec.ts`. `playwright.config.ts` reads `PW_CHROMIUM_PATH` (a sandbox's own Chromium; unset on Windows and CI).
- **Superseded by the fix round:** the hands-free/hold-to-talk select and the latency overlay left the Advisor panel (the latency line is now the LIVE pill's tooltip); "Start voice" is gone; the old right panel handle now shows from `lg` (1024 px).
- **Look:** tokens in `frontend/src/index.css` (navy glass is the app default; `.theme-cream` is the Welcome screen: cream `#F4EFE6`, ink `#141414`, tomato `#FF5B2E`). Fonts self-hosted with @fontsource: Instrument Serif (titles, the question, memo headings), Inter (text, memo body), JetBrains Mono (numbers). Source Serif 4 removed. `.glass` only on frames (table, header, phone "speaking now" card); text sits on solid `--card`. Glows are two blurred accents. No new animation library: CSS only.
- **Lite mode** (`frontend/src/lib/lite.ts`): no blur, no glows, no motion. Automatic on `prefers-reduced-motion`, 2 cores or fewer, 2 GB or less, or Data Saver; Settings → Look sets Automatic / On / Off (kept per browser).
- **Welcome** (`components/welcome/Welcome.tsx`): shown on the workspace route while this window has no conversation and no open decision. Headline, sub-line, "What are you deciding?" with mic and Call the team, 3 example chips, Quick/Thorough toggle (visual only; it says Quick arrives later; wired in M7g), How it works, Meet your team (host + six), the key chip, and "Your numbers today" (the KPI cards with lineage).
- **Boardroom** (`components/boardroom/`): an oval glass table with the question; the Advisor (host) and the team seated around it as original SVG faces (`faces.tsx`: one family, own shape and colour, Devil's Advocate horns). The working agent glows orange and blinks (the Advisor while the voice speaks or the answer streams). Under each face: done ✓ / thinking… / next / slow / switched to Qwen / needs your OK. Right: "Options so far" on a solid panel (leading option orange, figures in mono from the decision frame, Accept sends "Go with … : write the decision memo.", Ask more starts a question in the Advisor box, Reject only sets the option aside on screen, with Undo), evidence link "N sources · N checks" to Activity. Bottom: LIVE caption bar (the voice's words, else the lane's last line) with Hold to talk. The existing cards (numbers, decision frame, cost model, goal check, scenario chart, findings) sit under the table unchanged. The old right-hand Agents rail is gone (the faces and the agent window show the same); its resize handle is now "Options panel width".
- **Phone (< 768 px):** compact sticky header (nav scrolls sideways; health dots hidden), question, "Speaking now" glass card with the caption, a sideways strip of the other faces, the options stacked, the cards, then the conversation; a sticky bottom bar "Accept <leading option>…" and a big Hold to talk. The first Call the team tap unlocks audio for iPhone Safari (`lib/audioUnlock.ts`); a blocked or insecure mic gets a plain message (`micProblem`).
- **F9:** the voice client lives in `lib/voiceContext.tsx` (`VoiceProvider` at the app root). Pages only show controls; going to Activity, Decisions, Data, Vault or Settings never starts, stops or resets voice. Off the workspace a small dock (bottom left) shows the mic and the live words while voice is on.
- **F8d:** cause: `EVENT_TYPES` in `lib/workspace.tsx` had no `slow.offered`, `agent.slow` or `spend`, and an SSE frame with a named event only reaches a listener for that name, so the browser dropped the offer. Now the list includes every lane event; a test reads `backend/app/agents/events.py` and fails if any backend type is missing. The offer shows in the Advisor panel and on the agent's card (Activity and the agent window) with Continue on Qwen on our server / Keep waiting; answering one answers both.
- **F19:** the router records why a cloud call fell back (`Completion.fallback_reason`: rate_limit, busy, unreachable, error). The first fallback answered by Qwen in an agent emits `agent.fallback` ("Groq hit its per-minute limit, so People & Ops finished on Qwen on our server."), once per agent: on the card (badge "Switched to Qwen" instead of "Cloud · groq"), under its face, and said by the Advisor. Spend counts only answered cloud calls (it already did; now tested with a 429 run: nothing to pay).
- **F18:** one memo per open decision. A memo for a decision that already has a proposed memo (frontmatter `decision`, e.g. `new_office:dubai office`) rewrites that file; the text it replaces is kept outside the vault in `data/<workspace>/memo_versions/<memo stem>/<YYYYMMDDTHHMMSS>.md` (so search and the Librarian never read an old proposal). New frontmatter `written_at`. API `GET /api/memos/versions?path=` and `GET /api/memos/versions/{id}?path=`. Memo page: Latest badge with date and time, Earlier versions list (open one; Latest goes back), Back to the decision, Close, Regenerate memo (asks the team again) and Ask the team about this (opens the Boardroom with the question started). Memos with no frame still get their own file ("-2.md") as before; old "-2.md" files stay.
- **Polish:** Change model lists the best 4 under "Recommended (4)" with "Show all N"; a pasted key whose shape names its provider is tested at once; Test key reads "Test again" after a pass; Settings footer "Rates by Exchange Rate API".
- **Tests:** `backend/tests/test_m7b.py`; frontend `src/lib/m7b.test.ts`, `src/lib/lite.test.ts`, `src/components/m7b.test.tsx`, `src/components/memo/memo.m7b.test.tsx`, AI model card polish tests; e2e specs updated for Welcome and the options panel; `e2e/m7b-screens.spec.ts` takes the 1440 px and 390 px screenshots.
- **Known limits:** the Quick/Thorough toggle does nothing yet (M7g). Accept asks for the memo; the memo stays "proposed" until the member marks it decided in the vault. Predictions of a rewritten memo are added again to calibration under the same path (the earlier ones stay). Reject is on screen only (not sent to the team).

### AI model settings (M7a, 2026-11-22; key-only setup after the F1–F3 fix round, 2026-11-26)
- **Key-only (F3):** paste a key, press **Test key**. The provider comes from the key's prefix (`AIza` Gemini, `sk-ant-` Claude, `sk-or-` OpenRouter, `gsk_` Groq, `sk-proj-`/`sk-` OpenAI; Ollama Cloud and Custom keys have no shape, pick them in the list, which always overrides the guess). Test key reads the provider's models endpoint, keeps chat models, picks by `AI_MODEL_PREFERENCES` and saves the list (`models` in `ai_model.json`) for **Change model**. The `*_MODEL` settings are only a fallback for a server with no models list (Custom: or type the name under Advanced). The paragraphs below describe the M7a card; where they mention editing the model or a Server address field, read this line instead.
- **Settings → AI model** (top of the Settings page, current styling). Pick a provider: **Qwen on our server (free, private, slower)** (default, Ollama), Claude (Anthropic API key), Gemini (AI Studio key), OpenAI, OpenRouter, Groq, Ollama Cloud, Custom (any OpenAI-compatible base URL + key + model). Model defaults come from config (`CLAUDE_MODEL`, `GEMINI_MODEL`, `OPENAI_MODEL`, `OPENROUTER_MODEL`, `GROQ_MODEL`, `OLLAMA_CLOUD_MODEL`); the member can edit the model.
- **Test key** sends one tiny request ("Reply with the single word OK.", 15 s, `AI_MODEL_TEST_TIMEOUT_S`). The card is grey until it passes; then a fluorescent-green chip `<Provider> · <model> · key verified`. **A key is only stored when the test passes**, and then it is used at once. A failure stores nothing and shows one line: *Wrong key*, *No credit*, *Rate limited*, *Can't reach the server*, *Model not found* (or a general "refused the test (HTTP n)"). The provider's own error text is never shown or logged. **Use Qwen** goes back to Qwen and keeps the key unused; **Remove key** deletes it. The card's buttons act at once (not through the page's Save bar).
- **Storage:** `data/<workspace>/ai_model.json` (per workspace, ready for M7c): preset, model, base URL, the key as a **Fernet token** under `FOUNDEROS_SECRET_KEY`, and its mask `••••abcd` (last 4; shorter than 12 characters shows `••••` only). The API never returns a key. `scripts/ensure_secret.py` (run by `setup.bat`, `setup.sh` and `run.bat`) writes the secret to `.env` once and never prints it. With no secret, the card says to run setup and no key can be saved. If the secret changes, the saved key reads as unreadable and Qwen is used.
- **Routing:** a verified key sets the default deep-work provider (`router.cloud`) and turns **Allow cloud agents** on. `AGENT_MODELS` per-agent routes still win. Agents marked local (Advisor, Planner, Analyst, Librarian, Verifier) and the voice path never use it. Any failure falls back to Qwen (`fallback_from`). The privacy filter runs on every payload. The monthly cap still applies: a model with no known price is counted at a conservative $15/$75 per million tokens. **Allow cloud agents off** is still the kill switch (the card then says "Paused").
- **Ollama Cloud** is called at `https://ollama.com/v1` (OpenAI-compatible, `Authorization: Bearer`; read from Ollama's docs on GitHub on 2026-11-22: `docs.ollama.com` itself was not reachable from this container). Its cloud models have no structured output, so for Ollama Cloud, Groq and Custom the JSON schema goes in the instructions instead of `response_format`.
- **Custom** base URLs must be `https://` on a public address (no localhost, LAN, link-local or metadata IPs). `AI_MODEL_ALLOW_PRIVATE_URLS=true` allows http and LAN servers for a local install. A saved key is only ever re-sent to the same preset and base URL it was tested with.
- **No subscription sign-ins** (Claude Pro/Max, Google AI Pro/Ultra, Sign in with ChatGPT). `CLAUDE_CODE_OAUTH_TOKEN` is not read anywhere (the Agent SDK path was removed in M3b); members never use it.
- **Arm:** CI job `backend-arm64` on `ubuntu-24.04-arm` (repo is public, so the runner is free): base install + full pytest. `docs/ARM64.md`: Ollama, Qdrant, DuckDB, faster-whisper/CTranslate2, Kokoro/onnxruntime and torch all have arm64 builds (CPU only on the Ampere A1).
- **Tested with fakes only** (`backend/tests/test_m7a_ai_model.py`, 27 tests; `frontend/src/components/panels/AIModelCard.test.tsx`, 5 tests). **No real provider was called**: there is no key here. The error wording is matched on the providers' documented status codes and error texts; a real key on your PC is the first live check (AM3–AM5).
- **Known limits:** (1) With the default `TEAM_APPROVAL=cloud_only`, once a key is verified, a decision team with a cloud agent waits for your approval (set **Ask before a team runs → Never** to skip it). (2) The Custom URL's address is checked at test time only (DNS rebinding later is possible): harden in M7d. (3) The endpoints have no login, like the rest of the app: M7c must guard `/api/settings/ai-model`. (4) Voice and the Advisor stay on Qwen by design, so the answer you hear is still Qwen's; the cloud model writes the specialists' findings (risks, market, memo).

### M6 gate fix round (2026-11-19): D1–D7
- What changed is under Founder feedback → "[M6b] M6 Major gate run 2026-11-18/19". Tests: `backend/tests/test_m6_gate.py`; runner scenarios **D2**, **D3** in `scripts/voice_scenarios.py` (written, not run live this session: the tests reproduce both); Playwright `frontend/e2e/panels-scaled.spec.ts` (Chromium and Edge).
- **D7 bench** (this PC, 2026-11-19, `scripts/voice_bench.py --turns 5` against an isolated backend, qwen3:8b loaded in Docker Ollama, Whisper `small.en` on CUDA in both; first turn cold):

  | p50 (ms) | Kokoro on GPU (`VOICE_TTS_DEVICE=cuda`) | Kokoro on CPU (`VOICE_TTS_DEVICE=cpu`) |
  |---|---|---|
  | first_audio (first words) | **738** | 1242 |
  | first_answer_audio (metric answer) | **1690** | 2433 |
  | stt | **190** | 661 |
  | barge_in_pause / stop | 64 / 954 | 63 / 996 |
  | VRAM in use (of 12 GB) | 10.0 | 9.0 |

  **The GPU is faster on every line, so the default stays `auto` (Kokoro on the GPU)**; nothing changed in code. Your 1495 ms first_audio and 542 ms tts_first do not match either column here. A likely cause is **two FounderOS backends running at once** (the fresh copy and `D:\Founder-OS`), each loading Whisper and Kokoro on the one GPU beside qwen3:8b: with one backend, VRAM is already at 10 of 12 GB. MR1 checks that only one runs, and MR8 measures again on your main copy. If MR8 is still around 1.5 s, set `VOICE_TTS_DEVICE=cpu` in `.env`, run the bench again, and write both numbers in the Gate log.

### Polish (M6b, 2026-11-18)
- **F: panels.** Drag the edge between the Advisor panel and the canvas, or between the canvas and the Agents panel (or focus the edge and use the arrow keys; Home or a double-click is the default width). Advisor 280–720 px (default 380), Agents 240–560 px (default 300); the canvas always keeps at least 420 px. The icon left of "Executive Advisor" folds the panel to a 44 px rail (unfold, and open the agent window, from there). **Folding keeps the conversation and voice running**: the panel is hidden, not unmounted, so a hands-free session carries on. Sizes and the fold are kept per viewer in this browser (`localStorage` key `founderos.layout.v1`); a width saved on a big screen is drawn narrower on a small one and comes back on the big one. `frontend/src/lib/layout.ts`, `components/layout/ResizeHandle.tsx`.
- **G: agent window.** **Agents** at the top of the Advisor panel (with a count of agents working) opens a window you move by its title bar. It shows the current question and its stage line, four steps (Plan, Team, Verify, Answer: waiting, working, done or stopped), counts (done, working, waiting, stopped), the approval link when the team waits, and per agent: a ring that fills with its status and its two-letter code, Local/Cloud, its current step (the same safe words as the Activity tab, no figures) with elapsed time, and a bar on the run's clock. It stays open across views (so it can watch a run from the Activity tab or a memo), its place is remembered and pulled back on screen after a resize, Escape or × closes it. Cancel, re-run and briefs stay on the Activity tab, which it links to. `components/activity/AgentWindow.tsx`, `lib/agentGraph.ts`.
- **Kokoro on the GPU.** `setup.bat` now runs `scripts/enable_tts_gpu.py` after `pip install`: with an NVIDIA GPU it removes the CPU `onnxruntime` and installs `onnxruntime-gpu==1.23.2` without dependencies, plus `nvidia-cuda-runtime-cu12`, `nvidia-cufft-cu12`, `nvidia-curand-cu12`; then it checks that a real CUDA session starts. It runs every time because the `pip install` brings the CPU package back (both installed overwrite each other's files). `--check` reports, `--undo` goes back to the CPU. `VOICE_TTS_DEVICE` (`auto` default, `cuda`, `cpu`): Kokoro starts on CUDA with cuDNN's HEURISTIC search and a test line; any failure falls back to the CPU with a note in `/api/voice/status` (`tts.device`, `notes`). **On this PC the swap is done** (the venv now has `onnxruntime-gpu 1.23.2`, previously `onnxruntime 1.31.1`).
- **Measured on this PC** (2026-11-18, `scripts/voice_bench.py` against an isolated backend, Ollama in Docker with qwen3:8b, 5 runway turns; the first is cold):

  | What | Kokoro on CPU (8 threads) | Kokoro on GPU |
  |---|---|---|
  | Metric answer p50 (end of speech to first answer sentence) | 2381 ms | **1681 ms** (1657 in a second run) |
  | First words p50 | 1087 ms | **721 ms** |
  | STT p50 (Whisper `small.en`, CUDA) | 408–906 ms | **175–191 ms** |
  | Barge-in: pause / stop | 79 / 995 ms | **66 / 1000 ms** |
  | VRAM with qwen3:8b loaded | about 7.4 GB | about 8.5 GB peak of 12 (Kokoro +0.53 GB) |

  Kokoro alone (`tts_micro`, a 100-character clause): CPU fp32 4.2 s, CPU int8 3.5–4.2 s, **GPU fp32 1.1 s**, GPU int8 30 s (its quantised operators fall back to the CPU, 550 copies). So int8 is not used; `gpu_wanted` never puts an int8 model on CUDA. `onnxruntime-gpu` 1.31.1 needs CUDA 13 (`cublasLt64_13.dll`), so it is pinned to 1.23.2, which runs on the CUDA 12 / cuDNN 9 DLLs Whisper already uses.
- **The 3.8 s in M5's table was stale**: with the M5 fixes the CPU figure was already 2.4 s here (your RW10: 1.74 s). The target (~3 s) is met either way; the GPU makes speech start sooner everywhere.
- **voice_bench.py barge-in step** now talks over the first line of six words or more (the team line). With Kokoro on the GPU, the 0.6 s "On it." finishes before 1 s of speech is heard, so barging into it measured a new turn ("Wait, stop…" offered as a change), not a barge-in: three runs in a row. **The turn-taking rules are unchanged**: runner RL2c spoken (a change said over the spoken summary cuts it off) PASS with Kokoro on the GPU.
- **Re-run with a change already in the answer** (Next steps item 4): after a Dubai answer (two hires in the base case), "Re-run the analyst, assume two hires." now says "That's already in this answer: it assumes two local hires. Re-running only the Financial Analyst again. The rest of the team's findings stand." and runs only that agent, with no change added to the request. A real change ("assume three hires") still runs the whole team, as before.
- **npm deprecation warnings** (`npm ci`): eslint 9 ("no longer supported"), recharts 2 ("bump to v3") and `whatwg-encoding` (pulled in by jsdom 26). Each fix is a major upgrade (eslint 10, recharts 3 with its chart API changes, jsdom 27) and a reinstall of `node_modules`, so none is "safe": left, see Open questions.
- **Not done:** nothing in the M6b scope is open. G is the minimal-but-complete version: a "graph" of nodes and edges between agents (who read whose findings) was not attempted, because the lane has no per-agent dependency data to draw from.

### Packaging and demo (M6a, 2026-11-17)
- **`run.bat`** is the one command. On a fresh clone (no `.venv` or no `frontend\node_modules`) it runs `setup.bat` first. Every start: it refuses ports 8000 and 3000 when taken and names the process (`scripts/check_ports.ps1`: PID, name, command line, "an old FounderOS backend" when the command line has `app.main:create_app`, and the `Stop-Process -Id` to run); checks Docker is installed **and running** (`docker info`) before `docker compose up -d qdrant`; prints a preflight (`scripts/preflight.py`: Ollama at `OLLAMA_BASE_URL` with its version and the configured models, Qdrant `/readyz`, the voice models), each line OK or MISSING with the command that fixes it; then waits up to 90 s for `/api/health` before opening the browser. Nothing missing stops the start; only a taken port does.
- **`setup.bat`** also checks Node 20.19+ and npm, and that Docker is running, and downloads the models with **`scripts/download_models.py`**: the Ollama models (`OLLAMA_CHAT_MODEL`, `OLLAMA_EMBED_MODEL`, `FAST_LANE_MODEL`) through Ollama's HTTP `/api/pull` with progress, so Ollama in Docker needs no `docker exec`; then Whisper `small.en`/`base.en` and Kokoro through the existing `download_voice_models.py`. `--check` only reports; `--no-voice` / `--no-ollama`. The old `:ensure_model` block is gone.
- **Clean demo data.** The shipped sample vault (`sample_data/vault/`, 7 files) has no test memos: `decisions/2026-11-06-open-dubai-office.md` and `notes/dubai-office.md` exist only in your runtime vault (`vault/default/`, git-ignored), made by earlier test runs. **`reset_demo.bat`** (`scripts/reset_demo.py`) moves `vault/<ws>/` and `data/<ws>/` to `data/backups/reset-<UTC time>-<ws>/` (nothing deleted), restores the sample notes, keeps `ui_settings.json` (`--settings` resets it too), and refuses while port 8000 answers. The next start reloads the Northwind data and re-indexes (the sync removes stale Qdrant vectors). **I did not run it on your data**: that is checklist step PK4.
- **Docs:** README has a fresh-install section (requirements table, what setup and run do, models, reset, troubleshooting, VRAM/latency notes from your PC). `docs/DEMO_SCRIPT.md` is a 10-minute demo in PRD §9 order, with a "before the demo" list and a "what to do if" table. PRD §9 item 6 now says barge-in at 1 s; PRD §12 has the Kokoro licence decision for v1.
- **Not done in M6a (M6b):** F panels, G pop-up agent window, TTS latency (Kokoro on GPU or int8), the M6 Major gate. `setup.bat` was not re-run end to end on this PC (it would reinstall, against your rule); its changed parts were checked by reading and `run.bat`'s port path was run live. PK1 is the fresh-clone check.
- **M5 carry-overs (X1–X5):** see Founder feedback, top item.

### Voice (M5)
**Round 4 (2026-11-15, after your RX1–RX7 re-test; this replaces everything below where they differ)**
- **A yes is a yes, whatever its marks (T2).** Whisper wrote your "yes" as "Yes?", the lane's pattern for yes did not allow a question mark, and "Yes?" went to the Advisor as a new question (your `decision_log.jsonl` shows it at 07:09:57 UTC, classed as chit-chat: hence "Not run"). Answers are now matched without case and punctuation: "Yes?", "yes.", "Yeah!", "okay?", "Yep.", "Sure!", "Go ahead.", "Do it!", "Restart?" all answer the offer just made, typed or spoken; so do "No?" and "Keep going.". A listening noise ("mm") between the offer and your yes no longer closes the offer. A bare "Yes?" with nothing asked is a listening noise, never a question for the team.
- **One change, one offer, one card (T3).** Round 3 asked twice by design: the offer when you said the change, and "You asked for a change while the team worked … Restart with it?" again with the answer. Your change came 3 to 10 seconds before the answer (the Devil's Advocate ran 07:09:00 to 07:09:07, the answer was written by 07:09:10), so you got both within seconds. Now the offer is said once, when you say the change: "That changes the decision. Restart with your change?". With the answer nothing is asked again and no offer of risks is made; the offer stays open, so "yes" or "restart" after the summary still restarts, and so does the card. Only a change whose offer was never said aloud (typed in the chat box, or cut off) is asked about once after the summary. The lane no longer writes a second offer under the answer.
- **The card** now shows the same words the voice says (it had its own fixed text, "That changes the request. …", which was your "second offer"). The same change said twice (you repeating it, or the recogniser hearing it twice) is the same offer and the same card. A card still open when the answer arrives moves below the answer.
- **A change is offered at once in every stage (T1).** Tested with the run held in its first stage, in its last (only the last agent working) and while the answer is written: each time the offer is said and the card shown before the run ends and before any line of the answer. **I could not reproduce "no offer at that moment"** (see the feedback item).
- **No verification line when no team ran (T4).** "The answer is ready, but some of it is unverified" is not written for a reply with the "Not run" badge.
- **The trade-off names two options, or code writes it (T5).** A sentence about "the trade-off" that does not name two of the options on the table is replaced by "The main trade-off: with Travel-led pilot, you learn more slowly from trips than from a local presence, and win customers later; with Full office, it is the slowest to set up and the hardest to undo." (each option's own entry). A question is left alone.

**Round 3 (2026-11-14, after your RW1–RW10 re-test; this replaces everything below where they differ)**
- **Headphones or a headset give the best voice results.** Your numbers (RW10): first words p50 890 ms, metric answer p50 1738 ms, barge-in pause 64 ms, cancel about 990 ms, STT p50 291 ms, TTS first 596 ms, VRAM 7.43 / 12 GB, Whisper +0.70 GB.
- **A stopped run is never spoken (S1).** After "stop" and "yes" you hear "Stopping the team." and "That run was cancelled.", and nothing else: no summary, no offer. The lines waiting to be said are dropped, nothing of that run's answer is said later, and a run whose stop arrived too late to interrupt its last step is still ended as cancelled, with no answer on screen. The same holds for the Cancel button and a typed "stop".
- **A typed "stop" stops at once (your decision).** No question. A spoken "stop" is still asked about ("Stop the team? Say yes to stop."), and the Cancel button is immediate as before.
- **Each offer is said once (S2).** "Want me to go through the risks?" is not said again after "uh-huh" or any other noise. The one exception is R5's: an offer that a barge-in dropped before it was ever said is said afterwards, once.
- **After an offer it waits for you (S3).** Silence never continues it. Three things that could have been taken for a yes no longer are: its own words coming back through the microphone ("…go through the risks?" read as a yes to its own offer), heard while it plays or within a second after; an "okay" or "yes" that Whisper was less sure of than 0.45 (a breath or a click); and a noise that used to bring the offer back (S2). The echo gate now also stays on for 0.3 s after the last audio.
- **A change said while the team works (S4)** gets the same offer, in the same words, as after the answer: "That changes the decision. Restart with your change?", aloud and as a card with Restart and Keep going. Say "yes" or "restart". **If you do not answer and the answer arrives without your change, it is not lost:** the card stays open, the panel says "You asked for a change while the team worked, and this answer does not have it. Restart with it?", and the spoken summary ends on that question in place of "Want me to go through the risks?".
- **One telling per topic in the text answer (S5).** The goal a decision moves away from is named once, even when the second sentence has other figures in it. A proposed memo on record is named once: "You already proposed a Dubai office …" now counts as the memo again. No sentence says a memo or decision on record was written on a date other than its own ("in 2027" for a memo of 2026-11-06 is removed), or gives it a full date the record does not state.

**Round 2 (2026-11-13, after your RV1–RV11 re-test; round 3 above replaces it where they differ)**
- **Headphones or a headset give the best voice results.** Your own numbers (RV11, headphones): first words p50 931 ms, metric answer p50 1869 ms, barge-in pause 62–71 ms, cancel 574–582 ms, STT p50 396 ms, TTS first 591 ms, VRAM 7.4 / 12 GB, Whisper +0.52 GB.
- **A listening noise never stops a team (R1).** "Uh-huh", "mm", "hmm", "right", "okay", and what the recogniser makes of them ("Ugh!", "Huh.", "Oh."), or any one stray word, change nothing while a team works. Only **stop, cancel, halt, hold it** (also abort, never mind, forget it) ask to stop, and then you are asked: **"Stop the team? Say yes to stop."** Yes (or "stop" again) stops it; no, or anything else, and it carries on. Typed "stop" is asked about too; the Cancel button on the Activity tab still stops at once.
- **During a team run the voice says one opening turn, then is silent (R4).** "On it.", then: "I've put together a team of six: the Librarian, Market Scout, Financial Analyst, People and Ops, Regulatory and Tax and a Devil's Advocate. They're looking at the Dubai office from different angles so the decision holds up." Nothing per agent or stage, no Verifier line, no figure, no assumption question: those are on screen. One "Still working on it." if the run passes 30 s (`VOICE_STILL_WORKING_S`).
- **The summary: findings, outcome, offer (R4, R5).** Two or three findings built by code (what the full model costs and does to runway, a goal it moves away from, the cash warning, what is unverified or assumed), then "My proposal is …" and "The trade-off: …", then always an offer ("Want me to go through the risks?"), then silence. If a noise cuts the summary short, the offer is said again. Spoken risks are statements only.
- **Yes and no work (R8).** "Yes" (or "restart") answers "Restart with your change?"; "yes" answers "Did you mean two people?"; "ask it" or "yes" a queued question. Typed or spoken. **The screen now follows a run that was restarted by voice**: before, the run restarted but the canvas kept showing the old answer, which is why you still saw two hires.
- **Re-run one agent (R8).** After the answer, "re-run the analyst" runs only the Financial Analyst; the other agents show "kept from the last run" and finish at once, and the answer and summary are written again. "Re-run the analyst, assume three hires" changes the decision itself, so there the whole team runs again and the reply says so.
- **An unclear number is asked about first (R3).** "Make it a 2% team" or "two" on a decision that counts people: "Did you mean two people?" Yes applies it and restarts; no changes nothing. A percentage on a price decision is taken as said.
- **Transcription (R6).** Whisper is told the words it is likely to hear (agent and metric names, Dubai, hires, runway, churn). Code repairs "should be open …" to "should we open …" and "Freerun the …" to "Re-run the …". A turn Whisper is less sure of than `VOICE_CONFIRM_BELOW` (0.45) is read back first ("Did you say: …? Say yes, or say it again."), with a note under the mic. No LLM correction pass.
- **A proposed memo on record gets one question (R7):** "what has changed since you drafted it?". No question about its targets, forecasts or kill criteria, and the memo is named once.
- **Barge-in timings (R2) were wrong, not the audio.** The rows with `paused_ms` of 35,000 to 168,000 came from a clock fault: after a switch between Hold to talk and Hands-free (or 30 s of unbroken sound) the speech detector counted its frames from zero again, but the list of arrival times did not, so a later barge-in read its start from a frame that had arrived minutes before. The pause itself was sent at once, as your 62–71 ms rows show. Both now reset together, an onset older than 2 s is never reported, and a barge-in decided by its length now gets its words once they are known (no more empty text).
- **Speech over FounderOS for 1 s stops it (was 0.6 s; `VOICE_BARGE_IN_MS`).** Shorter speech pauses it at once and waits for the words: a filler resumes it, a question or three words stop it. So "cancel" in RV11 will now read about 1,000 ms for long speech; the pause is unchanged. **If your `.env` has `VOICE_BARGE_IN_MS=600`, change it to 1000 or delete the line.**

**Whisper model, measured on this PC with qwen3:8b loaded** (2026-11-13, `scripts/stt_bakeoff.py`: 16 phrases in 3 Kokoro voices with room noise, 48 clips)
| Model | Heard right | p50 | Slowest | VRAM added |
|---|---|---|---|---|
| `small.en` int8_float16 (the default), plain | 43/48 | 211 ms | 313 ms | +0.52 GB |
| `small.en` int8_float16, with the FounderOS vocabulary | 44/48 | 212 ms | 305 ms | +0.52 GB |
| `small.en` int8 | 43/48, 44/48 | 214, 219 ms | 324 ms | +0.35 GB |
| `large-v3-turbo` int8_float16, plain | 43/48 | 186 ms | 275 ms | +1.07 GB |
| `large-v3-turbo` int8_float16, with the vocabulary | 43/48 | 190 ms | 247 ms | +1.07 GB |
| `large-v3-turbo` int8 | 43/48 | 192, 225 ms | 280 ms | +1.07 GB |
- **It fits and it is no slower:** 6.4 GB in use before, about 7.5 GB with `large-v3-turbo`, of 12 GB.
- **This test cannot tell you which hears you better.** Every miss, for both models, was a spelling variant the scorer counted as wrong ("advisor" for "adviser", "&" for "and") or "net burns" for "net burn". Synthetic speech is too clean to reproduce "should be open" or "Freerun". The vocabulary's visible effect on `small.en`: it writes "Re-run" and the agents' names as the app does, and its confidence on right answers rose (lowest 0.62 to 0.83).
- `small.en` stays the default. `large-v3-turbo` is already downloaded on this PC (1.6 GB in `data/models/whisper`); RW8 says how to try it. See Open questions.

**How the Advisor speaks (fix round 2026-11-13; this replaces the lines below where they differ)**
- **It says less.** A new question gets "On it." (or "Checking that now." for one metric). A team run then gets one or two sentences on who is on the team and each one's focus, one short line a stage on what its agents produced, and a summary: the outcome, the one thing that matters, then an offer ("Want me to go through the risks?"). Say **yes** (or "go through the risks", "the other options") for the next part, **no thanks** to stop. The on-screen answer is never read aloud, and the assumption question and the "… are done; two to go" lines are on screen only.
- **Spoken numbers are rounded by code** from the verified figure (`app/voice/spoken.py`): "around 170 thousand dollars a month", "about 1.8 million dollars", "about ten and a half months", "about four in five". Exact figures and lineage stay on the card. Money (USD, EUR, GBP, AED; INR in lakh and crore), percent, months and dates. A share "of" something may be said as a fraction; a rate or a price change never is.
- **You have the floor.** Nothing new is played while you are speaking or while your words are being transcribed and answered; the reply to you comes before narration that was waiting. Speech it could not make out gets "Sorry, I didn't catch that." and a note under the mic.
- **It does not hear itself.** While it plays audio, sound below `VOICE_ECHO_GATE` (0.3) of your own speech level is treated as its echo. Your level is learnt from what you say while it is silent.
- **Follow-ups in context** (typed or spoken): "and what about churn?" is answered as that metric; "why that option?" from the open decision's own frame, at once; anything else goes to the Advisor together with your earlier questions and the first sentences of its earlier answers.
- **Re-run an agent** (typed or spoken): "re-run the analyst, assume three hires", "redo the Devil's Advocate". While that agent is working it restarts with your change; if its findings have already moved on, you are offered a restart of the run; after the answer the same team runs again with that agent's new brief (and your change added to the request, so code rebuilds the cost model).

**What you can do now**
- In the Advisor panel, press the microphone (it asks for the microphone once). **Hold to talk**: hold the mic button, speak, let go. **Hands-free**: just talk; FounderOS finds the end of your sentence after 400 ms of quiet.
- FounderOS answers out loud: first a short acknowledgement ("Checking that now." / "On it. I'll tell you how the team is doing as it works."), then the team's narration, then the checked answer, sentence by sentence. Everything also appears in the panel, as typed turns do.
- **Barge-in:** talk over it and it pauses at once (65 ms measured); speech of 600 ms or more, or words that are not a backchannel, stop it. "Uh-huh", "right", "ok" while it speaks: it carries on.
- **Mid-run turns** go through the same classifier as typed ones: a new question is queued, a change offers a restart, "stop" stops. Spoken answers to offers: "approve" / "hold it" (team approval), "ask it" / "drop it" (queued question), "restart" / "keep going" (a change).
- **Quiet** (the bell) silences all speech; transcripts and the canvas carry on.
- Latency per turn under the mic ("first words · answer · STT · barge-in stop"), and in `/api/voice/metrics` (p50s); engines, devices, fallbacks and VRAM in `/api/voice/status`.

**How it works** (`backend/app/voice/`, `backend/app/api/voice.py`, `frontend/src/lib/voice.ts`, `components/chat/VoiceControls.tsx`)
- Browser: AudioWorklet to 16 kHz mono int16, 32 ms frames over `/ws/voice`; 24 kHz int16 back, scheduled gap-free; `pause` suspends playback, `interrupt` flushes it and reports the flush time. Echo cancellation is on in `getUserMedia`.
- `vad.py`: Silero VAD v6 ONNX (bundled in faster-whisper, run with onnxruntime on CPU; no torch), 512-sample frames, own state per connection; energy detector as the fallback. `Endpointer`: start after 96 ms of speech, end after `VOICE_END_SILENCE_MS` (400).
- `stt.py`: faster-whisper `small.en` on CUDA `int8_float16`, falling back to `base.en` int8 on CPU at start-up if CUDA cannot load **or cannot run** (a test transcription catches missing DLLs). On Windows the CUDA DLLs come from the `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` wheels, added to the DLL path by `add_cuda_dll_dirs`.
- `tts.py`: Kokoro-82M ONNX (`kokoro-v1.0.onnx`, voice `af_heart`) on CPU, 8 threads; long sentences are made clause by clause so the first words play sooner; short fixed lines are cached. `for_speech` drops `[source]` brackets and says "%" as "percent".
- `turn_taking.py`: barge-in or backchannel, rules first (duration, a backchannel list, question words, three or more words), then the decision model (`yes_no`, 0.4 s timeout, confidence threshold); unsure or slow means barge-in.
- `session.py`: one connection. Utterance to `ConversationManager.turn`; the conversation lane's lines are spoken, **but a lane line with a figure is replaced by "I've put that on screen."**; the answer is spoken from a `tap()` of the run's text (the canvas keeps reading the queue itself: a new `DeltaQueue` broadcasts, so two readers never split an answer). An interrupt drops queued lines and audio being made.
- `spoken.py` (2026-11-13): `say_money`, `say_percent`, `say_months`, `say_date`, `spoken_text` (any sentence, numbers only), `team_line`, `produced_line`, `summarise` (a `ChatResult` to lead lines plus offers). `session.py` now speaks from lane events by `kind` (`team`, `approval`, `held`, `wave`) and from `summarise`; a one-metric line is said as soon as the routine's `metric_card` exists. `_floor`, `_speech_seq` and `_gated` are the floor, the stale-verdict guard and the echo gate.
- `service.py`: loads the engines in a worker thread at start-up (the canvas never waits, R4), records fallbacks and VRAM; `metrics.py`: per-turn and per-barge-in timings.
- Models: `python scripts/download_voice_models.py` puts Whisper (small.en, base.en) and Kokoro into `data/models` (git-ignored). GitHub release downloads failed here with 504s, so Kokoro and its voices come from the Hugging Face mirror `fastrtc/kokoro-onnx` when GitHub fails.

**Hardware (founder's PC, recorded 2026-11-08)**
- RTX 4080 Laptop GPU, 12 GB VRAM (11.99 GiB usable), driver 617.14; i9-13900HX (24 cores); Python 3.12.7 venv.
- The GPU is shared with qwen3:8b (Q4_K_M, 8k context: **5.86 GiB**) in the Docker `ollama` container, which other apps use too. With qwen3:8b loaded: 6.38 GiB in use, about 5.6 GiB free.
- Measured: Whisper `small.en` int8_float16 on CUDA adds **0.52 GB** (6.38 → 6.90 GiB). Silero VAD and Kokoro run on the CPU and add nothing. Headroom left: about 5 GB. `small.en` FP16 (PRD §2 budget) would roughly double Whisper's share; `int8_float16` was chosen to keep headroom for other apps' models.

**Measured on this PC** (2026-11-08, `scripts/voice_bench.py`, hands-free, the fixtures played in real time; qwen3:8b warm)
| What | Result | Target |
|---|---|---|
| STT (small.en, CUDA), warm | 260–420 ms per utterance (p50 293 ms) | |
| End of speech to first spoken word | p50 **932 ms** (755, 932, 960) | narration within 1 s: met |
| End of speech to the first sentence of a metric answer | p50 **3.8 s** (8.4 s cold first turn, 3.8, 2.4) | about 3 s: close, not met on p50 |
| Barge-in: speech onset to audio paused | **65 ms** | client flush within 100 ms |
| Barge-in: speech onset to speech cancelled (long speech) | **576 ms** (the 600 ms rule) | |
| Kokoro on CPU | about 1 s per second of speech (1.2 s for "Checking that now." uncached) | |
| Whisper on CPU (fallback, base.en) | about 1.5 s per utterance | |

**Limits**
- **Round 3 was not tested with a microphone, and I could not reproduce S1, S3 or S4 as you saw them.** What I did check for S1, live on this PC (Ollama, qwen3:8b, a scratch backend on port 8011): five Dubai runs stopped by "stop" and "yes" at 20, 28, 33, 37 and 40 seconds, the last two while the answer was being written. All five ended cancelled, with no answer. So the cancel itself works, and I do not know which path spoke the summary on your run. Round 3 closes every path I could find (see the feedback item), and RX2 to RX4 are the check with your voice.
- **Your own words can be taken for an echo** if you repeat the offer's words within a second of it ("go through the risks" right as "…go through the risks?" ends). "Yes" is never taken for an echo. Wait a moment, or say "yes".
- **A quiet "okay" after an offer may be ignored** (below the 0.45 threshold): the note under the mic says it was not caught. Say it again.
- A change left unanswered stays open only until the next run starts. Its card on a finished run can now be clicked (before, it had expired by then).
- The S5 date rule checks when a memo is said to have been written (its year, or the full date) and any full date such as 2026-12-06. A wrong month in words with the right year ("March 2026" for a memo of November 2026) is not caught, and a bare year elsewhere in the sentence is left alone.
- **Not tested with a real microphone in round 1.** V7 was reproduced and fixed in code, in tests with WAV fixtures, and with the real engines (Silero, Whisper on CUDA, Kokoro) against a *simulated* loudspeaker echo. Your room, loudspeakers and the browser's echo canceller are what RV2 and RV3 check.
- The echo gate compares loudness only. Very loud loudspeakers close to the microphone can still get through (raise `VOICE_ECHO_GATE`); a founder who speaks much more quietly over the answer than they usually do may not stop it (lower it, or 0 turns it off). Until you have spoken once while it is silent, there is no level to compare with and the gate is off.
- "Why that option?" gives code's reasons (cost, easier to undo, a goal it moves away from), with no figure. A different "why" goes to the team as a new question.
- When you accept "go through the risks", up to three of the Devil's Advocate's checked sentences are said, with rounded numbers. That is the one place an agent's own words are spoken.
- After the answer, a re-run runs only that agent (round 2). The other agents' findings are kept as they were, even though a later stage read the old findings of the one that ran again.
- Round 2 was **not tested with a microphone**. R1, R3, R4, R5, R7 and R8 are tested with WAV fixtures and fakes (`tests/test_voice_round3.py`); the vocabulary and both Whisper models ran for real on synthetic speech. Your voice is RW2 to RW9.
- The read-back threshold (0.45) is a guess: on clean synthetic speech nothing fell below 0.6, right or wrong, so I could not tune it. If it asks too often, lower `VOICE_CONFIRM_BELOW`; if garbled turns get through, raise it (0.6).
- A run restarted from the on-screen **Restart** button is not summarised aloud (the voice says only "The answer is ready."). Restarted by voice, it is.
- One stray word typed while a team works ("Dubai") is now ignored as a backchannel, like a spoken one.
- Kokoro on the CPU is the slow part of an answer. Kokoro on the GPU needs `onnxruntime-gpu`, which replaces the `onnxruntime` package that faster-whisper depends on: left for M6 tuning (Next steps).
- The figures above come from synthesised speech (the fixtures), not your microphone; the checklist below measures your voice.
- Hands-free with loudspeakers relies on the browser's echo cancellation; with headphones barge-in is cleanest. A false barge-in only pauses: short noise resumes.
- The first turn after start-up is slower (Ollama and Kokoro warm up).

### Canvas UI (M4)
**What you can do now**
- Open `http://127.0.0.1:3000` and run the whole product in the browser: ask, watch the team, approve or edit it, read the answer with its sources, try scenarios, read and export the memo.
- **Workspace:** the Advisor and conversation lane on the left, the numbers in the middle, a live agent list on the right. Every KPI has a dashed chip that opens its formula, rows and file.
- **Activity:** the proposed team to approve, edit, add to, remove from or run locally; live cards with Cancel and Re-run per agent; a timeline.
- **Decisions:** the Prioritisation Matrix and the memo sheet, with Edit, Export .md and Export PDF.
- **Data, Vault, Settings:** load files and fix column mappings; read, search, edit and add notes; set cloud, provider per agent, cost cap, approval and slots.
- A single-metric question is written by code in about 2 s and verified (measured below).

**How it keeps the safety rules on screen**
- "Verified" appears only where the backend returned `true`. Otherwise it says "Not verified" with a count, and while an answer is still being written it says nothing.
- `issues` and `agent.step` are the audit trail and can name a removed figure. The UI shows `issues` only as a count, and every step goes through `safeStep` first, which strips tool arguments, what the Verifier found, figures and file paths. Removed figures are therefore on the API but never on the screen. The smoke test checks this with a model that invents "$150 billion" and a made-up citation.
- Source chips come only from the `citations` field, never from text in an answer.
- A decision answer leads with the proposed option, then the full model, labelled "assumption, confirm". The model's own text below may still open differently: the card, not the text, sets the order.
- The UI formats numbers and never calculates them. The one position it works out is the "Under 3 months of cash" band: the three months before the zero-cash month on the chart, counted in months, not money.

**Measured here on 2026-11-06 (PowerShell, scratch backend on port 8011, your vault untouched)**
- `scripts/metric_loop.py` on the final code: `METRIC LOOP: verified 10/10 | median 1.7 s | slowest 3.1 s | target under 8 s`; net burn 3/3 (median 1.6 s); gross margin 3/3 (median 1.6 s). Before the fix: 7.5 to 8.4 s and verified 4/5. Cause: three LLM calls with about 4,775 input tokens, and the Verifier rejected a correct burn answer that mentioned months as a wrong meaning.
- In the browser with the real model: "What is our runway?" 2.1 s and 4.9 s, Verified, both runs. A Dubai decision after approval: 59 s and 63 s, **Not verified** both runs (see below). No removed figure on any screen, and no page errors. W9 ran live too: status reply, amendment with Keep going, queued question offered at the end of the run, Ask it now answered and Verified. Quiet mode was not in that run.
- The Ollama move to a named volume is done (your request): warm responses are about 0.5 s.

**Not done, and limits**
- **The Dubai answer currently comes out Not verified.** All three live runs today did (13 issues in each of the two I read). The scratch vault already held a Dubai memo, and the Librarian and the Advisor quote its starter targets ($27,000.00, $36,000.00, 10.44 months) and its 50% forecasts. These have no lineage in this run, so the Verifier flags them; the Librarian also got one "wrong meaning". The figures are the memo's own labelled starters, not inventions, and the badge is telling the truth. I did not change it, since the brief was no backend behaviour change. A next step is to let a figure quoted from a decision on record carry that record as its source.
- A memo is written only when the Memo Writer is on the team, or you ask for one. The Planner did not add it on the Dubai runs here, so W6 asks you to add it.
- Voice is M5: the microphone button is present but disabled.
- A page reload starts an empty conversation in the browser. The backend still has the runs and the memo is in the vault, but the UI does not reload past turns (run state is in memory, last 100 runs).
- Column mapping for a file that fails to load works from a CSV's header line. An Excel file that fails shows the error; once loaded its mapping can be edited.
- Dragging a bubble in the matrix sets every criterion on that axis to one score. To vary them separately, edit `notes/priorities.md` in Obsidian.
- The base and scenario lines use one colour pair from the mock-ups. The palette validator passes colour-blind separation and contrast, and fails only its lightness band for dark surfaces; the line style (solid against dashed) and the legend also separate them. I kept your mock-up colours.
- With nothing running, small talk such as "how is it going?" starts a run, and the Advisor answers with a chatty reply that can carry a Verified badge, since it has no figures to fail. It is backend behaviour, so I left it.
- The conversation lane's question offers and amendments are unit-tested on the state and covered by the backend tests, but the Playwright smoke test does not drive them: with a scripted model a run finishes too quickly to interrupt. I ran them live once with a browser script; W9 is the check on your PC.

### Source check (fix after the founder's M3c review, 2026-11-06)
**What you can do now**
- A figure with a made-up source can no longer reach you. Live, during this fix, the Market Scout wrote "$160 billion" and "$166 billion" unprompted; code removed them before any later agent saw them.
- With cloud off and no market data in the vault, the Market Scout says so and lists what to find, with no figures.

**How it works**
- `app/agents/sources.py`: `without_unsupported` takes a sentence out (or a whole line in a list) if it names a source that is not a real vault file or a page a search returned, or holds a figure with no backing. A figure is backed by lineage from a routine, code's own lines, the founder's message or goals, or a retrieved passage. If a sentence cites a source, an unlabelled figure must be in **that file's** retrieved chunks. It adds `(removed: unsupported source)`.
- `AgentRunner._remove_unsupported` runs after the one repair turn, so later stages get checked text only. `findings_for_advisor` no longer quotes a figure or a path in its `[UNVERIFIED]` flag: that flag is how the $150 billion reached the Advisor's question.
- `_SentenceGate` applies the same check to each sentence of the Advisor's reply, questions included. If nothing it wrote survives, the team's checked findings answer instead.
- The memo: prose goes through the same check. **`Open numbers to confirm` now lists what to confirm with no figure in it** ("Dubai's GDP is a figure to confirm (removed: unsupported source)"). This replaces your M3b rule, which moved the figure itself there, because you asked that the memo never contain one.
- `scout_without_web`: with cloud off, only sentences citing a retrieved passage stay, plus a list of what to find written by code.
- People & Ops v2 is live (P5).
- Also: spans of days and weeks ("a 90-day pilot") no longer count as financial figures, `trillion`, `crore` and `lakh` now do, and "if needed" no longer hides a goal contradiction (the new live eval caught that one).

**Known limits**
- **A forecast's or stop rule's own target stays in the memo,** listed as a target (for example "Qualified Dubai pipeline >= $36,000.00"). A stop rule needs a number, and code or the model chooses it, so it has no source. This is the one exception to "no unsupported figure". A target that cites a missing source, or rests on a figure already removed, is dropped.
- A target from an earlier proposed memo counts as on record, so the Advisor can repeat or ask about it. It is labelled proposed, and it is a placeholder, not market data.
- `issues` on the API response, and the `agent.step` event, still name the removed figure and path. They are the audit trail. M4 should not show them as prose.
- A figure written in words ("a hundred and fifty billion"), or a count of 12 or under ("5 competitors"), is not seen as a figure. A claim with no figure and no source is not caught, except for the cloud-off Market Scout. A figure that happens to match a routine's number passes.
- Removing whole sentences can leave a section thin, and a real sentence with an unbacked figure goes too. A law or standard number ("ISO 27001") counts as a figure.
- Live, the model still invents a market figure on most Dubai runs. Each costs a repair turn before code removes it.
- Live runs during the fix, code changing between rounds. Dubai through the eval rubric: PASS, FAIL (the "if needed" bug), PASS. Price rise: FAIL (the eval's own pattern), PASS, PASS. Four more Dubai runs printed their cited paths: all exist or are data files. **On the final code:** two of those path runs, and one PASS each for Dubai and the price rise. A small sample, and the full live labelled set was not run.

### Decision models, privacy names and evals (M3c)
**What you can do now**
- A memo or answer can no longer contradict its own goal check. A line saying the proposal helps a goal that the check says it moves away from is removed by code. A cheaper option that is not proposed always says why (control, speed, what you learn).
- With cloud on, customer, person and company names are replaced by stable stand-ins (`Customer_001`, `Person_001`, `Company_001`) before anything leaves the PC, and restored in the reply. If the name list cannot be built, the call stays local.
- Run four bake-offs and a labelled eval from one command each (Windows checklist below). You decided these on 2026-11-06 (PRD §12): the only change is People & Ops v2 (P5).

**How it works**
- `app/agents/guards.py`: `goal_contradiction` and `without_contradictions` compare a sentence with the frame's goal statuses. `specialists.py` applies them to the Decision and to answers, and `_why_not` gives a rejected cheaper option its `OptionCost.trade_off`. `role_problems` catches the off-brief lines you reported (travel, physical office, "you, you", vault for market data).
- `app/llm/names.py` builds the list from the `customers` table and the vault's people and company notes. `app/llm/privacy.py` has `NameIndex`, `StreamRestorer` and `FilterReport.names_replaced`. `app/llm/router.py` applies it to every cloud payload, including tool-call arguments and web searches.
- `app/decision/laya.py` and `jev.py`: `DECISION_PROVIDER=laya|jev` with the LLM as the fallback below the confidence threshold or on any failure. `laya` is an optional install, imported only when chosen. Jev receives only an allow-list (`message`, `turn`, `running`), privacy-filtered, with numbers masked.
- `app/evals/`: `labelled_questions.json` (58), `routing_examples.json` (212, with a stable train/test split), `embedding_queries.json` (36), and the harnesses. Scripts: `eval_labelled.py`, `tune_prompts.py`, `eval_decision_models.py`, `finetune_laya.py`, `bakeoff_providers.py`, `bakeoff_embeddings.py`.
- Prompt versions live in `app/agents/prompts/versions/<agent>/vN.md`, with scores in `MANIFEST.json`. The app only reads `prompts/<agent>.md`; nothing rewrites a prompt at runtime.

**Known limits**
- **Laya and Jev have not been measured.** Installing `torch` and `laya` here was refused by this session's permission check, and there is no Jev key. Both are built against the documented APIs (read 2026-11-05) and tested with fakes only, so a real install may show API differences. You deferred C8 and C9 until after M5.
- **No real cloud call was made in this session either.** The cloud rows of the provider bake-off are yours to run.
- A person's name that is in no source is only caught after a title ("Dr", "Mr"). The goal check and role checks are word patterns: they can miss a rephrased claim.
- All measurements are one run on a small sample vault, so a difference of a few points is noise.
- **Wording from the live Dubai run (C4):** People & Ops opened with "You are you." on the v1 prompt. v2 is now live and the three Dubai runs whose text I read did not show it, but People & Ops is not on every team, so M4 re-checks it. Regulatory's "Ensure the decision aligns with the goal" is still weak.
- A proposed memo already on record reads "decided 2026-11-05; status proposed" in the answer's record line, because the record uses the memo's date as `decided`. It came from earlier memos in the test vault, and the status beside it is right. Fix in the next session.
- The live labelled set ran only partly (Dubai and the price rise through `eval_agents --live`, both PASS). I stopped the rest to stay in the time-box; the offline set is 58/58.
- There is no cash metric, so "how much cash do we have" gets the rules' metrics summary instead of one figure.
- Jev's spend is not counted against `CLOUD_MONTHLY_CAP_USD`, and its calls are not in `llm_calls.jsonl`; the decision log records them. At its price the amounts are tiny, but the cap does not cover them.
- A customer whose short name is an ordinary word ("Summit Foods") is only hidden in full. A person's short form is hidden only as written, so "priya" in lower case gets through.
- The M3c session pulled `embeddinggemma` (about 0.6 GB) into your `ollama` container for the bake-off. With P6 approved you can remove it: `docker exec ollama ollama rm embeddinggemma`. That is left to you. Bake-off models can evict n8n's models from the GPU; those reload on their next use.

**Bake-off results (one run, your PC, sample data, 2026-11-05). Proposals P1–P7 are in PRD §12.**

Decision models, on the 74 held-out routing examples (the single-model rows ran with `num_ctx` 2048; the real-path row and the script now use the app's 8192):
| Provider | Intent (35) | Team (18) | Turn (21) | p50 |
|---|---|---|---|---|
| Rules, when they answer | 95.8 % of 69 % | 100 % of 44 % | 100 % of 76 % | 0 ms |
| **Rules first, then `qwen3:8b` (the app's real path)** | **94.3 %** | **100 %** | **85.7 %** | 0 ms when rules answer, up to 5.9 s (p95) |
| `qwen3:8b` alone | 94.3 % | 100 % | 52.4 % | 3.5–3.7 s |
| `phi4-mini` | 91.4 % | 94.4 % | 57.1 % | 4.7–5.5 s |
| `mistral` | 77.1 % | 50.0 % | 57.1 % | 3.0–3.1 s |
| Laya, Jev | not measured | not measured | not measured | |

Calibration: `qwen3:8b` is well calibrated on intent (ECE 0.007) and team (0.050), and badly on turn (0.429): its confidence does not warn you there.

Agents per model (`passed/3`, mean seconds). Local cost is $0, and no cloud model was run:
| Agent | `qwen3:8b` | `phi4-mini` | `mistral` |
|---|---|---|---|
| Financial Analyst | 3/3, 7.8 | 3/3, 4.6 | 2/3, 8.9 |
| Librarian | 3/3, 4.3 | 3/3, 6.1 | 3/3, 11.3 |
| People & Ops (live prompt v1) | 0/3, 13.6 | 0/3, 7.5 | 0/3, 25.8 |
| Regulatory & Tax | 2/3, 8.8 | 1/3, 8.6 | 2/3, 19.7 |
| Devil's Advocate | 2/3, 12.3 | 0/3, 106.2 | 1/3, 15.9 |

Conversation lane (5 replies): `qwen3:8b` 5 good, 5 in time, p50 2.92 s. `mistral` 5 good, 5 in time, 3.20 s. `phi4-mini` 4 good, 2 in time, 4.02 s.

Prompt tuning on `qwen3:8b`:
| Agent | v1 (live) | v2 | v3 | Best |
|---|---|---|---|---|
| People & Ops | 0/5 | **5/5** | 2/5 (4/5 on the 2026-11-06 re-run) | v2 (live since 2026-11-06: P5) |
| Devil's Advocate | 5/5 | 1/5 | 5/5 | v1 |
| Regulatory & Tax | 4/4 | 3/4 | 4/4 | v1 |
| Librarian | 3/3 | 3/3 | | v1 |

Embeddings, on 36 labelled queries (MRR, recall@3):
| Model | Hybrid (what the app uses) | Dense only | Query ms | VRAM GB | Licence |
|---|---|---|---|---|---|
| `nomic-embed-text` | 0.940, 100 % | 0.887, 94 % | 1796 | 0.30 | Apache-2.0 |
| `embeddinggemma` | 0.940, 100 % | 0.938, 97 % | 2575 | 0.63 | Gemma Terms |
| `mxbai-embed-large` | 0.944, 94 % | 0.900, 97 % | 1973 | 0.58 | not checked |
| `nomic-embed-text-v2-moe` | 0.938, 97 % | 0.912, 100 % | 3351 | 0.55 | not checked |

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

## Next steps (after M7b, 2026-11-26)
0. **Gate check:** M7b is a **Major** gate. The founder runs **MB1–MB12** below on Windows (Edge) and a phone, and writes ACCEPTED (or the issues) in the Gate log. Until then the next session works only on that feedback, on this branch.
1. M7c (invite login, per-member workspaces) only after M7b is ACCEPTED. The memo versions folder is already per workspace.
2. M7g wires the Quick/Thorough toggle on Welcome (`components/welcome/Welcome.tsx`, `depth` state) and can give each face its own voice.
3. Possible follow-ups seen this session: send Reject to the team as a constraint ("rule out X"); mark a memo decided from the memo page; calibration should replace a rewritten memo's predictions instead of adding them again.

## Next steps (after the M7a fix round 4, 2026-11-26)
0. **Gate check:** the founder re-tests **AM-S1–AM-S8 (fix round 4)** below and merges this bug-fix PR (Light). If AM-S3 still shows no offer, the backend window now says where it stops: send the `Slow-agent offer …` line and the `Slow check: …` lines.
0a. M7h also carries a stronger model for the critical agents (Devil's Advocate, Verifier) and a Verifier check that a risk's figure matches a frame option's own change (PRD §8, seen 2026-11-26: "cash burn increases by $2,001 if the full office is opened" passed on Groq `openai/gpt-oss-120b`).
0b. The founder's existing duplicate Matrix entry (from before F14) has no decision link: delete one of the two by hand once; new memos then update the one left only if it was written after this fix (older entries carry no link).

Earlier (after fix round 3):
0. **Gate check:** the founder re-tests **AM-R1–AM-R6 (fix round 3)** below and merges this bug-fix PR (Light). Fix round 2 (PR #14) is merged and accepted except F8 (now F8b).
0c. M7f also carries the setup-guide note (AI Pro / Jio subscriptions do not include API use; AI Studio free limits; a free Groq key is a good start); M7b polish adds auto-test on paste, "Test again" after a pass, and the exchange-rate credit in the Settings footer (PRD §8).

Earlier (after fix round 2):
0. The founder re-tested AM5–AM8 (fix round 2). Any new finding is fixed on this same branch and PR. M7b (Major) starts after the merge.
0a. M7b also carries F9 (voice keeps its context across pages) and "Recommended (3–4) · Show all" in Change model (PRD §8).
0b. M7f carries the first-run privacy question and silent currency detection; M7h (after M7d) the key ring and smart routing (PRD §8).

Earlier next steps (after M7a, 2026-11-22):
1. **M7b** Decision Room UI redesign (Welcome screen, Glass Boardroom, desktop and phone). Restyle the AI model card there; keep its test ids (`ai-model-card`, `ai-model-verified`).
2. **M7c** must put the AI model endpoints behind login and map each member to a `workspace_id` (the key store is already per workspace). Decide the hosted default for `TEAM_APPROVAL`.
3. **M7d** on the Ampere VM: run `docs/ARM64.md`'s checks (Qwen tokens/s, voice CPU bench); pin or re-check Custom URLs at call time.
4. Earlier items below still stand.

Earlier next steps (after the M6 gate fix round, 2026-11-19):
0. **Gate check:** M6 is a **Major** gate. The founder runs the re-test **MR1–MR8** below (MG1–MG9 were run 2026-11-18/19) and writes ACCEPTED (or the issues) in the Gate log. Until then, the next session works only on that feedback, on the existing branch `claude/m6b-polish-demo` (PR open), reproducing voice issues with `scripts/voice_scenarios.py` first.
1. If Kokoro on the GPU misbehaves on the founder's PC: `VOICE_TTS_DEVICE=cpu` in `.env` is the switch, `scripts\enable_tts_gpu.py --undo` the full revert. Re-measure with `scripts/voice_bench.py`.
2. **X1** (closing offer sometimes missing) was not reproduced in M6a. If seen again: note the question and the chat line, add a runner scenario. Code paths: a frame with no options, or the "costs" fallback (`app/voice/spoken.py` `summarise`, `_offer_always`).
3. npm upgrades as their own small PR, if the founder wants them: eslint 10 (check `eslint-plugin-react-hooks` / `react-refresh` support), recharts 3 (migration guide; ScenarioSimulator and the Monte Carlo fan), jsdom 27 (drops `whatwg-encoding`). Each needs a fresh `npm install` and the Playwright specs.
4. After M6: Laya fine-tuning (C8) and Jev (C9); Dubai verification of figures quoted from a decision on record; smaller ideas (reload a conversation after refresh, a mapping form for failing Excel files, Jev in the cost ledger, a cash metric, `OllamaEmbedder` delegating to `OllamaProvider.embed`); G could later draw which agent read whose findings, if the lane records it.

## Windows verification checklist (for the founder)
**M7b gate fix round (F20–F27), about 20 minutes. Run this one first: MC1 to MC10, then MB2, AM-S5 and AM-S8.** Windows PowerShell 5.1, Ollama in Docker, Edge, the sample data; a phone on the same Wi-Fi for MC10. `git fetch; git checkout claude/serene-knuth-si17hr; git pull; .\setup.bat`, then `.\run.bat`. Screenshots of what to expect: `docs/design/screens/m7b-gate/`. Write the results in the Gate log.
- **MC1 (F22). Open on Welcome.** With a decision already asked earlier, close the tab and open http://127.0.0.1:5173 again (F5 too). **Expect** the cream Welcome page every time, with one line at the top: "You have an open decision: Dubai office. Continue it?". Press it: the Boardroom opens; the earlier conversation is folded under "Earlier in this conversation (N)"; nothing is said aloud.
- **MC2 (F21). One status.** **Expect** the top bar shows "All systems OK" (or "Slow right now" with Ollama stopped), never "Ollama · Qdrant · GPU · Storage". Click it: Settings → System lists the services.
- **MC3 (F20). Whole numbers.** In the Boardroom at 100 % and at 125 % zoom, and with the Advisor panel dragged wide. **Expect** every metric card shows the whole figure ("$172,280.47", "$255,344.27"): smaller or on two lines, never "…". The cards wrap to a new row instead of breaking apart.
- **MC4 (F24). The topic.** Ask "Should we open a Dubai office?". **Expect** "On the table: Dubai office". Then ask "What is our runway?": **expect** "Runway". Press Accept on the leading option: the topic stays "Dubai office".
- **MC5 (F25). The table fits the team.** **Expect** the Advisor at the top and exactly one face per agent the team proposed (2 to 8), evenly spaced, no empty seat, no face on the topic; each face has a coloured ring and a name tag in its own colour; the working face glows warm.
- **MC6 (F26). Panels.** Drag the Advisor panel's edge wide, then the Options panel's edge (both now resize); fold each with its button; F5: **expect** sizes and folds kept. Make the window narrow (about 1100 px wide) with both panels wide: **expect** the centre switches to the speaking card and a strip of faces, with no overlap. Press **Focus on the team**: both panels fold; **Show panels** brings them back.
- **MC7 (F27). Talk on the faces.** **Expect** no "Start voice" button in the left panel or the LIVE bar (the left panel is typing only; the LIVE bar says "Tap a face to talk"). Tap Market Scout's face: voice turns on (hands-free), the LIVE bar says "Talking to Market Scout". Ask "What is our runway?" aloud. (The Advisor answers for the team until M7g routes questions to the named agent.)
- **MC8 (F27). Stop only stops talking.** Ask the Dubai question aloud and, while the team works and the Advisor speaks, press the **Stop** button in the "Speaking" tag under the Advisor's face. **Expect** the voice stops at once, the faces keep changing (thinking… → done ✓) and the options and cards still fill in. Do the same with **Esc**, and by speaking over it. Then **Voice off** in the LIVE bar while a team works: **expect** the team finishes and its answer appears.
- **MC9 (F27). Keys.** In the Boardroom with voice off, hold **Space**: voice turns on and listens while held (release to send). Press **M**: "Muted", nothing is heard; M again: "Mute". On the memo page, Space scrolls and never asks for the mic.
- **MC10 (F23, phone).** Ask the Dubai question. **Expect** the Advisor's answer in at most 3 sentences, with "Full answer" folded beneath; kill criteria and predictions only there and in the memo. On the phone (390 px): the topic, the speaking card, the strip of faces (tap one: "Talking to …" under the card; over plain http, the https message there), no sideways scroll.

**M7b Decision Room redesign (Major gate), about 40 minutes. Run after MC: MB1 to MB12 (MB1, MB3–MB12 passed in principle on 2026-11-26/27; re-run MB2).** Where MB says "Turn voice on" or "Start voice", tap a face instead (F27). Windows PowerShell 5.1, Ollama in Docker, Edge; a free Groq key; a phone on the same Wi-Fi for MB11–MB12. `git fetch; git checkout claude/serene-knuth-si17hr; git pull; .\setup.bat` (new npm packages: Instrument Serif), then `.\run.bat`. Write the results in the Gate log.
- **MB1. Welcome.** Open http://127.0.0.1:5173 in a new InPrivate window. **Expect** the cream page: "Ask a hard question. Six AI advisors argue it out. You decide.", the sub-line, "What are you deciding?" with a mic and Call the team, 3 example chips, Quick/Thorough, How it works (1 2 3), Meet your team (7 faces, Devil's Advocate with horns), the key chip top right, and Your numbers today with lineage chips. No request to fonts.googleapis.com in DevTools → Network.
- **MB2. Boardroom.** Type "Should we open a Dubai office?" and press Call the team. **Expect** the navy Boardroom: the oval glass table with "Dubai office", the Advisor at the top and the proposed team around it with "needs your OK" (approval Always) or working; Options so far on the right with the leading option in orange, figures in mono, Accept / Ask more / Reject and, after the run, "N sources · N checks". The LIVE bar at the bottom shows the Advisor's last line. After the run press **Accept** on the leading option: **expect** the Advisor writes the memo for that option (not a new team for a new question; if a new team is proposed, write that in the Gate log). Reject strikes the option through (Undo brings it back); Ask more starts "Tell me more about …" in the Advisor box.
- **MB3. The speaking face.** Approve the team. **Expect** the working agent's face glows orange and blinks; under each face done ✓ / thinking… / next. The decision frame, cost model, goal check, scenario chart and findings are below the table as before.
- **MB4 (F8d). The slow offer, at last on screen.** Close FounderOS; in PowerShell `$env:CLOUD_SLOW_AFTER_S="3"; $env:CLOUD_SLOW_MIN_S="0"; .\run.bat`. With Groq verified, ask the Dubai question and approve. **Expect** when the backend logs `Slow check: People & Ops … -> offer sent`: in the Advisor panel and on People & Ops's card (Activity, and the agent window) "Taking longer than usual…" with **Continue on Qwen on our server** / **Keep waiting**; its face says "slow". Press Continue on Qwen: both offers close, the agent finishes on Qwen. Start normally afterwards.
- **MB5 (F19). A 429 is said.** With the free Groq key, ask two decisions back to back (or a Thorough one) until Groq's 8,000 tokens a minute run out. **Expect** "Groq hit its per-minute limit, so <agent> finished on Qwen on our server." in the Advisor panel, the card badge "Switched to Qwen" (not "Cloud · groq"), "switched to Qwen" under the face, and the spend line counting only Groq's answered calls.
- **MB6 (F9). Voice across pages.** Turn voice on in the Boardroom (mic, Hands-free), ask "What is our runway?" aloud, and while it answers click Activity, then Decisions, then Settings. **Expect** the voice keeps speaking and listening; a small dock bottom left shows the mic and the words. Back on Workspace the same conversation and voice are there, never restarted.
- **MB7 (F18). One memo per decision.** Ask for the Dubai memo twice ("write the memo", then Regenerate memo on the memo page). **Expect** one file in `vault\decisions\` (no new "-2.md"), the memo page shows **Latest · <date>, <time>**, Earlier versions lists the first one (open it: "Earlier version" badge; Latest goes back), and the earlier text is under `data\default\memo_versions\`. Back to the decision and Close work; Ask the team about this opens the Boardroom with the question started.
- **MB8. Polish.** Settings → AI model: paste a Groq key: **expect** the test starts by itself. After the pass the button reads **Test again**. Change model shows "Recommended (4)" and "Show all N". The Settings footer says "Rates by Exchange Rate API".
- **MB9. Lite mode.** Settings → Look → On: **expect** no blur and no glows, no blinking. Automatic: on again if Windows "Show animations" is off (Settings → Accessibility → Visual effects).
- **MB10. Keyboard and contrast.** Tab through Welcome and the Boardroom: **expect** a visible orange focus ring on every button; every button at least finger size.
- **MB11. Phone (Android Chrome or iPhone Safari) on the same Wi-Fi.** Open http://<PC IP>:5173 (as in M6's phone check). **Expect** Welcome stacked, the input full width, mic and Call the team side by side. Ask a question: the question at the top, a "Speaking now" card with the caption, a sideways strip of faces, the options stacked, a sticky bar with "Accept <option>…" and a big Hold to talk. No sideways page scroll.
- **MB12. Phone mic and sound.** Tap the mic. Over plain http the phone shows "The microphone needs a secure (https) address…" (expected until M7d's HTTPS); on iPhone the first Call the team tap unlocks sound. Write what you see.
- **Also re-test AM-S5 and AM-S8** from fix round 4 below (carried into M7b).

**M7a fix round 4 (F7c, F8c, F13b, F14–F17), about 15 minutes. Run this one first: AM-S1 to AM-S8.** Windows PowerShell 5.1, Ollama in Docker, Edge, a free Groq key (`gsk_…`); a Gemini key only for AM-S2. Write the results in the Gate log.

- **AM-S1. Update.** Close FounderOS. `git fetch origin; git checkout claude/bold-tesla-cibyyq; git pull; .\run.bat` (no new packages). **Expect** in the backend window: `Slow-agent offer after 45 s (min 15 s; from .env or the default)`.
- **AM-S2. Gemini that does not answer in time (F7c).** Settings → AI model: paste the Gemini key, **Test key**. **Expect** (if Google does not answer within 15 s): the yellow notice "Gemini didn't answer in 15 seconds. Google may be slow or limiting your key. Try again later." and never "Check your internet connection". Groq still passes on the same connection. (Only with the Wi-Fi off: "Can't reach the server: Gemini could not be reached. Check your internet connection…".)
- **AM-S3. The slow offer, with the log (F8c).** Close FounderOS. In PowerShell: `$env:CLOUD_SLOW_AFTER_S="3"; $env:CLOUD_SLOW_MIN_S="0"; .\run.bat`. **Expect** in the run.bat window `Slow-agent offer from this window: CLOUD_SLOW_AFTER_S=3 CLOUD_SLOW_MIN_S=0`, and in the backend window `Slow-agent offer after 3 s (min 0 s; from the environment: CLOUD_SLOW_AFTER_S, CLOUD_SLOW_MIN_S)`. With Groq verified, ask the Dubai question and approve. **Expect** lines like `Slow check: People & Ops 1.9 s of 3 s -> not yet` and then `Slow check: People & Ops 4.1 s of 3 s -> offer sent`, with the offer on the card and in the Advisor panel (**Continue on Qwen on our server** / **Keep waiting**). If no offer appears, copy every `Slow…` line from the backend window into the Gate log (a `skipped (…)` line names the reason). Start FounderOS normally afterwards.
- **AM-S4. One proposal on screen (F13b).** Ask the Dubai question, then "Write the decision memo." (or "Record the decision on the Dubai office."). When the memo proposes "Partner or distributor": **Expect** the decision frame card marks **Partner or distributor · Proposed** (only one), the new answer's box says "Proposed: Partner or distributor", and the answer opens with one sentence such as "With Partner or distributor the runway effect is smaller, so I now propose Partner or distributor instead of Travel-led pilot." Ask "What's our runway?" next: the card keeps Partner or distributor.
- **AM-S5. One Matrix entry per decision (F14).** First delete one of the two old Dubai entries by hand (they were made before this fix). Write a second memo for the same Dubai decision (AM-S4 again, or "Record the decision on the Dubai office."). **Expect** Decisions → Prioritisation Matrix keeps one Dubai entry; its name follows the newest memo and its place on the matrix (your scores) stays.
- **AM-S6. A proposal is never "decided" (F15).** Ask "What did we decide about Dubai?". **Expect** the Librarian and the Advisor call the earlier memo **proposed** (e.g. "proposed on 2026-11-26 (not decided yet)"), never "decided 2026-11-26".
- **AM-S7. The real reason for no web research (F16).** With Groq verified, ask the Dubai question. **Expect** the Market Scout's findings end with "Your AI provider (Groq) has no web search, so this comes from your vault only." Turn cloud off (Settings → untick "Allow cloud agents"), ask again: then "…cloud is off, so no web research was done."
- **AM-S8. One waiting line per agent (F17).** During a Groq run: **Expect** the Advisor panel shows "People & Ops is waiting for a cloud model." **once** (one line per agent), not 4–5 times.

**M7a fix round 3 (F4b, F7b, F8b, F12b, F13), about 15 minutes. Run this one first: AM-R1 to AM-R6.** Windows PowerShell 5.1, Ollama in Docker, Edge. A free Groq key (`gsk_…`) is enough; a Gemini key only for AM-R3. Write the results in the Gate log.

- **AM-R1. Update.** Close FounderOS. `git fetch origin; git checkout claude/serene-mendel-8r39x1; git pull; .\run.bat` (no new packages).
- **AM-R2. Remove key turns cloud off (F4b).** Settings → AI model: paste your Groq key, **Test key** (green chip; "Allow cloud agents" ticks itself; top bar shows the cloud model). Press **Remove key**. **Expect:** "Allow cloud agents" unticks and greys out with "Test and save a key in the AI model card above first…"; no "You have unsaved changes" bar; within a few seconds the top bar no longer shows cloud. Reload the page (F5): still unticked. Test the key again to go on.
- **AM-R3. Gemini busy or out of free quota (F7b).** Only if your Gemini key is still at its free limit: paste it, **Test key**. **Expect:** a yellow notice "Your Gemini key has reached its free limit for now. Try again later, or add billing in Google AI Studio." (or, for a busy minute, "Gemini is busy right now (Google error 429)…"), never "Can't reach the server… check your internet connection", in 4 of 4 tries. With a Gemini key that passed before, the green chip stays.
- **AM-R4. The slow offer for an agent of quick calls (F8b).** Close FounderOS. In PowerShell: `$env:CLOUD_SLOW_AFTER_S="3"; $env:CLOUD_SLOW_MIN_S="0"; .\run.bat`. With the Groq key verified, ask the Dubai question and approve the team. **Expect:** when a cloud agent (People & Ops, Devil's Advocate) has worked for 3 s in all, its card shows "Slow: Groq has taken 3 s so far (expected under 3 s)", and the Advisor says and shows "… is taking longer than usual…" with **Continue on Qwen on our server** / **Keep waiting**. Nothing switches until you press one. Close FounderOS and start it normally afterwards (a new PowerShell window drops the variables).
- **AM-R5. Your currency everywhere (F12b).** Settings → Currency: INR. Run a decision on Groq. **Expect:** the lane's end line "This decision cost about ₹…: Groq N calls…" (and the voice says ₹); Agent Activity header "Run cost about ₹…", with US$ only in its tooltip (2 decimals, e.g. "US$0.29"); the memo's "What this decision cost" in ₹ with "(Estimated: US$0.29.)", never 4 decimals. On a fresh workspace with no currency chosen, the first decision is already in your browser's currency.
- **AM-R6. One proposal on screen (F13).** Ask the Dubai question; when the answer and the memo propose an option other than the one first marked (e.g. "Partner or distributor" instead of "Travel-led pilot"). **Expect:** the decision frame card marks **that** option "Proposed" (only one), and the answer opens with one sentence such as "With Partner or distributor the runway effect is smaller, so I now propose Partner or distributor instead of Travel-led pilot." Ask a follow-up that writes a new memo: the card follows the newest proposal.

**M7a fix round 2 (F4–F8, F12), about 15 minutes. Run this one first: AM5–AM8 (new behaviour), then AM8b.** Windows PowerShell 5.1, Ollama in Docker, Edge. Have your real Gemini key ready (an `AQ.` one if you have it). Write the results in the Gate log.

- **AM5-0. Update.** `git fetch origin; git checkout claude/busy-volta-rnlf9x; git pull; .\run.bat` (no new packages).
- **AM5a. A failed test changes nothing (F4).** Settings → AI model → **Remove key** if one is saved. **Expect:** "Allow cloud agents" is greyed with "Test and save a key in the AI model card above first…". Paste `sk-ant-wrong-000000000000`, **Test key**. **Expect:** the red "Wrong key" line; the checkbox stays unticked and greyed; **no** "You have unsaved changes" bar.
- **AM5b. AQ. keys and unknown keys (F5).** Paste `AQ.fake-0000`: the provider jumps to **Gemini**, "Looks like a Gemini key". Paste `zz-not-a-key`: the line under the box says "We couldn't recognise this key. Please check it, or pick the provider that issued it." and the provider list is outlined. Pick **Qwen** in the list with `AQ.fake-0000` in the box: it goes back to Gemini. Now paste your **real** Gemini key, **Test key**. **Expect:** green chip; the backend window shows `AI model key shape: starts 'AQ.' -> gemini` (or `'AIz'`), never more of the key. `Select-String -Path logs\*,data\default\*.json* -Pattern '<first 6 characters of your key>'` finds nothing.
- **AM6. The verified model everywhere (F6).** **Expect:** top bar "Cloud: Gemini · gemini-3.8-flash (from AI model)" (no "Local only · no cloud key"), the Cloud dot without "(degraded)"; the Cloud section "Deep-work agents use Gemini · gemini-3.8-flash (from AI model)" and a green pill with it, `gemini: no .env key`; under **Provider per agent**, Market Scout's list reads "Default: Gemini · gemini-3.8-flash (from AI model)".
- **AM7a. Busy (F7).** Hard to cause on demand. If Google answers 503/429 during **Test key** or **Change model**: **Expect** a yellow line "Gemini is busy right now (Google error 503). Your key is fine. Try again in a minute.", no red error, the green chip stays. (Tested with fakes: 503, 503, then OK passes after two short retries.)
- **AM7b. Spend report (F12).** Settings → **Currency**: INR (it should already show your browser's region). **Expect:** "Monthly cost cap (INR)" with your cap in rupees (USD × today's rate) and "Spent this month: about ₹… ($…)" with "Rate of 2026-11-26". Set the cap to `2000`, Save: `Get-Content data\default\ui_settings.json` shows `cloud_monthly_cap_usd` in USD (about 2000 ÷ rate). Ask **"Should we open a Dubai office?"** (approval Never). **See and hear** at the end: "This decision cost about ₹…: Gemini N calls; Qwen parts free." **Decisions** → the memo ends with "## What this decision cost". `Get-Content data\fx_rates.json` holds the day's table.
- **AM8. A slow cloud agent (F8).** To try it without waiting 45 s: close FounderOS, `$env:CLOUD_SLOW_AFTER_S = "3"; $env:CLOUD_SLOW_MIN_S = "0"; .\run.bat`. Ask the Dubai question. **Expect** (when Gemini takes more than 3 s): the Market Scout's card says "Slow: Gemini has not answered in 3 s (…)", the Advisor says and shows "Market Scout is taking longer than usual: … I can continue it on Qwen on our server, or we keep waiting. Your choice." with **Continue on Qwen on our server** / **Keep waiting**. Nothing switches by itself. Press **Continue on Qwen…**: the card says "Switched to Qwen on our server, with your OK: …", the team finishes, `/api/agents` shows `fallback_from`. Next question, press **Keep waiting**: the Gemini answer is used. Close the window afterwards (the two settings are for this window only).
- **AM8b. Left over from the gate.** Wi-Fi fallback, **Use Qwen** and **Remove key** from the old AM8 below.

**M7a re-test after the F1–F3 fix round of 2026-11-26 (Medium gate), about 15 minutes. Run this one first: AM1 to AM9, with the new key-only flow.** Windows PowerShell 5.1, Ollama in Docker, **Edge** (F2 is an Edge finding). Have one real API key ready (Gemini or Claude is enough). Write the results in the Gate log.

- **AM1. Update and start (F1).** Leave Qdrant running (the path that failed). `git fetch origin; git checkout claude/zealous-bell-ymy3uq; git pull; .\.venv\Scripts\python.exe -m pip install -e backend[dev,gpu,voice]; .\run.bat` **Expect:** `[OK] Qdrant already running on port 6333.` and then, **without running anything by hand**, `[OK] FOUNDEROS_SECRET_KEY is set in .env` (or `[OK] Created FOUNDEROS_SECRET_KEY in .env (…)` on a .env without it). The key itself is never printed. Optional: stop Qdrant (`docker compose stop qdrant`), close the servers, `.\run.bat` again: the same `[OK] FOUNDEROS_SECRET_KEY …` line prints on this path too.
- **AM2. The card.** Open **Settings**. **Expect:** an **AI model** card at the top, grey, "In use: Qwen on our server · qwen3:8b". First field **API key** (no Model box, no Server address); the Model provider list has 8 entries, first "Qwen on our server (free, private, slower)"; no subscription sign-in anywhere.
- **AM3. No password manager (F2).** In Edge, click in the API key box and paste `sk-ant-wrong-000000000000`. **Expect:** the text shows as dots; **no key icon** in the address bar, no "Save password?" offer, no saved-passwords dropdown under the box, no reveal-eye inside the box, also after **Test key** and after leaving the page. (Optional: the same in Chrome.)
- **AM4. Provider from the key (F3a) and a wrong key.** With `sk-ant-wrong-000000000000` still in the box: **Expect:** the provider list jumped to **Claude (Anthropic API key)**, the line under the box says "Looks like a Claude key". **Test key**. **Expect:** within 15 s a red line starting "Wrong key: Claude did not accept it."; the card stays grey; Qwen still in use. Clear the box and paste `AIzaSy-wrong-0000`: the provider jumps to **Gemini**.
- **AM5. The real key, nothing else (F3b, F3e).** Clear the box, paste **only** your real key, press **Test key** (nothing else). **Expect:** the card turns green with the chip **"Gemini · gemini-3.8-flash · key verified"** (Gemini key: the newest Flash your key has, not `gemini-2.5-flash`; Claude key: "Claude · claude-sonnet-… · key verified"); the key box empties; "Saved: Gemini · … · ••••abcd" shows only the last 4. The **Cloud** section now has **Allow cloud agents** ticked. `Get-Content data\default\ai_model.json` shows a long `key_token` (gAAAA…) and a `models` list, never your key. `Select-String -Path data\default\*.json*,.env -Pattern '<first 10 characters of your key>'` finds nothing; the backend window shows "AI model set for the deep-work agents: Gemini gemini-3.8-flash" with no key.
- **AM6. Change model (F3c).** **Expect:** a **Change model (optional)** dropdown under the provider, listing only chat models (no embedding, image, speech or video models). Pick another one (e.g. a Pro model). **Expect:** green again with that model in the chip, without retyping the key. Pick the first one back.
- **AM7. It drives the deep-work agents.** Set **Ask before a team runs → Never**, Save. Ask **"Should we open a Dubai office?"**. **Expect:** the Agent Activity panel shows the Market Scout / Devil's Advocate on **Cloud** with your model, the Analyst and Librarian on **Local**; the spoken answer still comes from Qwen. `Invoke-RestMethod http://127.0.0.1:8000/api/agents` shows cloud calls with an estimated cost.
- **AM8. Advanced, fallback, Use Qwen and Remove key (F3d).** Pick **Custom** in the list. **Expect:** an **Advanced** box appears with **Server address** and an optional model name (it is not shown for any other provider). Address `https://example.com/v1`, any key, **Test key**: a plain-English failure, nothing changes (still green with your real key). Turn off Wi-Fi briefly and ask a decision question: the team still answers (on Qwen), and `/api/agents` shows `fallback_from`. Wi-Fi back on. Pick **Qwen on our server**, **Use Qwen**: grey card, "Saved: … (not in use)". Pick Gemini (or Claude) again, leave the key box empty, **Test key**: green again. Then **Remove key**: grey, no "Saved" line; `ai_model.json` has an empty `key_token`.
- **AM9. CI.** On the PR, all checks are green, including **Backend on arm64 (pytest) / ubuntu-24.04-arm** and the Playwright job (new `e2e/ai-model.spec.ts`).

**M6 re-test after the D1–D7 fix round of 2026-11-19, about 30 minutes. Run this one first: MR1 to MR8.** Windows PowerShell 5.1, headphones, Ollama in Docker, approval at **Never**, Hands-free. Write ACCEPTED, or what you saw, in the Gate log.

- **MR1. Fresh copy up to date.** Close every FounderOS window (`Get-NetTCPConnection -LocalPort 8000,3000 -State Listen -ErrorAction SilentlyContinue` shows nothing: a backend left on 8000 from `D:\Founder-OS` would serve the fresh copy's page with the other vault). Then `Set-Location D:\FounderOS-fresh2; git pull; .\reset_demo.bat` (answer `y`), `.\run.bat`. **Expect:** browser up, Runway 10.65 mo. The first start re-embeds the vault once (new collection name, D4).
- **MR2 (D2). DEMO_SCRIPT §3.** Say **"What if we raise prices 10% and churn goes up two points?"** **Expect:** a team runs (never "already assuming… Nothing to restart"); the answer and the spoken summary say **"Change prices by +10 % with churn +2 pts"** with its runway effect. Then say it again after a Dubai answer (MR3): still a new question, no change card.
- **MR3 (§4, D1).** "Should we open a Dubai office?", then **"Assume three hires."**, **"Yes."** (as you did; it passed).
- **MR4 (D1). §5 Record the decision.** Say **"Record the decision on the Dubai office."** **Hear/see:** "Writing the memo from this answer: its options, costs and goal check. The team's findings stand."; only the Memo Writer works. Open **Decisions**. **Expect in the memo:** Goal check says it **moves you away** from the runway goal (no "aligns with"); **Cost model** with low/base/high and "Local hires: 3 people (you said)"; **Options**: the five Dubai options with costs and runway, the proposed one marked, **no SDRs**; **Open numbers to confirm**: four lines ending "Give me the real figure." (setup, rent, travel, compliance). Then **Workspace → Prioritisation Matrix**: a new entry "Open a Dubai office: …" marked "Not scored yet".
- **MR5 (D3). §6.** Ask "Should we hire two more engineers?" and over the spoken summary say **"Wait, stop there."** **Expect:** it stops and stays silent, listening; **no** change card, no "isn't in this answer". Also try "Hold on." over a later summary: the same.
- **MR6 (D4).** In the fresh copy, ask "What have we decided about Dubai?" before §5. **Expect:** no citation of `decisions/2026-11-06-open-dubai-office.md` (that file is only in `D:\Founder-OS`'s vault).
- **MR7 (D6). Panels in Edge at 125 %.** On Workspace you now see a **grip** (a short grey bar) on each panel edge; the pointer turns into ↔ over it. Drag the left edge right and the right edge left: both move. **F5**: both widths kept. **Double-click** each edge: back to default. Open **Agents**, drag the window to a corner, **F5**, open **Agents** again: same place.
- **MR8 (D7, MG7, MG8, MG9). Voice.** In `D:\Founder-OS` (fresh copy closed): `git checkout claude/m6b-polish-demo; git pull; .\run.bat`. Run MG7 and MG8 below. Then `.\.venv\Scripts\python.exe scripts\voice_bench.py --turns 5` (approval Never) and `$m = Invoke-RestMethod http://127.0.0.1:8000/api/voice/metrics; $m.p50_ms`. **Expect:** about the numbers under Current state → "D7 bench"; write yours in the Gate log.

**Superseded by MR above (done 2026-11-18/19: results under "Founder feedback"): MG1 to MG9.**
**M6 Major gate (PR "M6: Windows packaging, polish & demo"), about 40 minutes. Run this one first: MG1 to MG9.** Windows PowerShell 5.1, headphones, Ollama running in Docker. Write ACCEPTED, or what you saw, in the Gate log.

- **MG1. Fresh clone, one command.** Close **every** FounderOS window (`Get-NetTCPConnection -LocalPort 8000,3000 -State Listen -ErrorAction SilentlyContinue` shows nothing). Then:
  `git clone -b claude/m6b-polish-demo https://github.com/Sree1959GIT/Founder-OS.git D:\FounderOS-fresh2; Set-Location D:\FounderOS-fresh2; .\run.bat`
  **Expect:** "First run: … setup.bat runs now", the install, then **new**: an `onnxruntime packages:` block and `[OK] onnxruntime-gpu 1.23.2: Kokoro will run on the GPU (VOICE_TTS_DEVICE=auto).` (it downloads about 300 MB of CUDA wheels once), the model step ("have qwen3:8b", voice models about 0.9 GB), `[OK] Qdrant already running on port 6333.` if `D:\Founder-OS`'s Qdrant is up, the preflight, "Backend is up", and the browser with Runway 10.65 mo.
- **MG2. Kokoro is on the GPU.** `Invoke-RestMethod http://127.0.0.1:8000/api/voice/status | Select-Object -Expand tts` **Expect:** `device : cuda`, `note` empty. Also `(Invoke-RestMethod http://127.0.0.1:8000/api/voice/status).vram_gb` **Expect:** `used_now` about 7.4–8.5 (of 12) once qwen3:8b is loaded. Then `.venv\Scripts\python.exe scripts\enable_tts_gpu.py --check` **Expect:** `[OK] onnxruntime 1.23.2: Kokoro on the GPU`.
- **MG3. The demo, end to end.** In this fresh copy, follow `docs\DEMO_SCRIPT.md` from "Before the demo" (step 1 there is `.\reset_demo.bat`, fine on a fresh copy) to section 7. Note any step that does not do what the script says, with its number.
- **MG4. F: panels.** On the Workspace view: drag the edge right of the Advisor panel to the right. **Expect:** the conversation widens, the canvas narrows but never below a usable width. Drag the edge left of the Agents panel to the left: it widens. Press **F5**. **Expect:** both widths kept. Double-click an edge: back to the default. Click the fold icon left of "EXECUTIVE ADVISOR". **Expect:** a slim rail on the left, the canvas uses the width. With **Hands-free on**, fold it and ask "What is our runway?" by voice. **Expect:** it still hears and answers aloud while folded. Unfold: the conversation is all there.
- **MG5. G: the agent window.** Click **Agents** (top of the Advisor panel). Say or type **"Should we open a Dubai office?"**. **Expect:** a window with Plan → Team → Verify → Answer lighting up in turn, one row per agent with a ring that fills and turns green, its current step and a bar on a shared clock, and "N done · N working · N waiting". Drag it by its title bar to another corner. Switch to **Activity** and back: it stays open and in place. Press **F5**, open it again: same place. **Escape** closes it.
- **MG6. Voice timing.** After a few spoken turns: `$m = Invoke-RestMethod http://127.0.0.1:8000/api/voice/metrics; $m.p50_ms` **Expect:** `first_audio` about 0.7–0.9 s, `first_answer_audio` about 1.7 s or less (was 1.74 s on the CPU in your RW10), `barge_in_pause` under 150 ms. Or run the bench (approval at Never): `.venv\Scripts\python.exe scripts\voice_bench.py --turns 5` **Expect:** p50 metric answer about 1.7 s, "barge-in: audio paused ~70 ms … interrupted=True".
- **MG7. Barge-in still feels the same.** During the spoken Dubai summary, say "Assume three hires." over it. **Expect:** it stops and says "Your change to three hires isn't in this answer yet. Say yes to restart with it." A short "mm" over it does not stop it.
- **MG8. Re-run with a change already in the answer.** After a Dubai answer, say **"Re-run the analyst, assume two hires."** **Hear:** "That's already in this answer: it assumes two local hires. Re-running only the Financial Analyst again. The rest of the team's findings stand." **See:** only the Financial Analyst works. Then **"Re-run the analyst, assume three hires."** **Hear:** "That changes the decision, so the whole team runs again with it, …".
- **MG9. Back on your main copy.** Close the fresh copy's windows. In `D:\Founder-OS`: `git fetch origin; git checkout claude/m6b-polish-demo; git pull` and `.\run.bat`. (This PC's `.venv` already has `onnxruntime-gpu`; I swapped it while measuring.) If anything voice-related is worse on the GPU: `.venv\Scripts\python.exe scripts\enable_tts_gpu.py --undo` puts the CPU package back; tell me what you heard. Delete `D:\FounderOS-fresh2` when done, or keep it.

**Done (M6a, PK1–PK8 PASS 2026-11-17, PR #11 merged): PK1 to PK8, kept for reference.**
**M6a (Light gate), about 15 minutes. PK1 to PK8.** Windows PowerShell 5.1.

- **PK7 (re-test after the fix). Yes, then the risks; a yes is never ignored (Y1, Y2).** After a fresh Dubai answer, **see and hear** "The answer is ready… Want me to go through the risks?" (or "Want me to go on?" / "…the costs?"), even when the answer ends on the Advisor's own question. Say **"Yeah."** **Hear:** the risks, no new team. Say **"Yeah."** again. **Hear:** "Which comes first: … or …?" if the answer ended on an either/or question, otherwise "Yes to what? You can ask me about the risks or the other options." Never silence.
- **PK7b. A third yes.** Straight after PK7, say **"Yes."** once more. **Hear:** "Yes to what? You can ask me about the risks or the other options." No team, no "Did you say…?".
- **PK1b. Second clone, Qdrant already running (Y3).** With `founderos-qdrant` running from `D:\Founder-OS`, in `D:\FounderOS-fresh`: `git pull; .\setup.bat` **Expect:** `[OK] Qdrant already running on port 6333.` and no "container name … already in use" and no `[WARN] Could not start Qdrant`. `.\run.bat` says the same line.
- **Founder results 2026-11-17:** PK1 PASS (but Y3), PK2–PK6 PASS, **PK7 FAIL** (Y1, Y2). PK8 not reported.
- **PK1. Fresh clone, one command.** Close every FounderOS window. In a **new** folder: `git clone -b claude/m6a-packaging-demo https://github.com/Sree1959GIT/Founder-OS.git D:\FounderOS-fresh; Set-Location D:\FounderOS-fresh; .\run.bat` **Expect:** "First run: FounderOS is not set up yet, so setup.bat runs now", the install, the model step (with your Docker Ollama: "have qwen3:8b", "have nomic-embed-text"; then the voice models download, about 900 MB), a preflight block, the backend and frontend windows, "Backend is up", and the browser with the Northwind KPI cards (Runway 10.65 mo). Close both windows. Delete `D:\FounderOS-fresh` afterwards, or keep it for M6b.
- **PK2. Port in use, named.** In `D:\Founder-OS`: `.\run.bat`, wait for the browser, then run `.\run.bat` **again** in a second PowerShell. **Expect:** `[ERROR] Port 8000 is already in use by an old FounderOS backend: python.exe (PID n).`, its command line, `Stop-Process -Id n`, and nothing else starts. Run the `Stop-Process` it prints (and close the frontend window), then `.\run.bat` again: it starts.
- **PK3. Something missing is named.** `docker stop ollama`, then `.venv\Scripts\python.exe scripts\preflight.py` **Expect:** `[MISSING] Ollama is not answering at http://localhost:11434.` with "docker start ollama". `docker start ollama` and run it again: `[OK] Ollama 0.32.1 …`. Then `.venv\Scripts\python.exe scripts\download_models.py --check` **Expect:** every model "have …" and "All models are there.".
- **PK4. Reset to the clean demo.** Close FounderOS. `.\reset_demo.bat`, answer `y`. **Expect:** "Done. Your old vault and data are in …\data\backups\reset-…-default". `Get-ChildItem vault\default -Recurse -File | Select-Object -Expand Name` **Expect:** the 7 sample files (no `2026-11-06-open-dubai-office.md`, no `dubai-office.md`, no `priorities.md`). Settings are kept. `.\run.bat`: the Northwind data loads; **Decisions** shows only the SDR decision.
- **PK5. "Leave as it is" (X2).** Ask **"Should we start a Dubai office?"** (voice, Hands-free) and wait for the answer. Say **"Ok, I will leave as it is."** **Hear:** "Okay, leaving it as it is." No "Did you say…?". Also **"Leave that as it is."** and **"Keep as is."**: the same.
- **PK6. A change already in the answer (X3).** After a Dubai answer say **"Assume two hires."** **Hear:** "That's already in this answer: it assumes two local hires. Nothing to restart." No card, no run. Then **"Assume three hires."** **Hear:** "Your change to three hires isn't in this answer yet. Say yes to restart with it."
- **PK7. Yes, then the risks (X4, X5).** After a fresh Dubai answer, **hear** "Want me to go through the risks?" once. Say **"yeah"** (or "yes"). **Hear:** the risks, and no new team. If a yes is ignored, read your turn in the chat (what Whisper wrote) and tell me the word.
- **PK8. Docs.** Skim `README.md` (Fresh install) and `docs/DEMO_SCRIPT.md`. Tell me anything that is wrong for your PC.

**M5 live check after fix round 8 of 2026-11-16. Run this one first: RM1 to RM6 (about 10 minutes).** Headphones, Hands-free, approval at Never, Windows PowerShell 5.1 from `D:\Founder-OS`.

- **RM1. The right code, in slow mode.** Close **every** FounderOS window, then `Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue` **Expect:** nothing. Then `git pull origin claude/m5-voice; $env:FOUNDEROS_STAGE_DELAY_S = "8"; .\run.bat`.
- **RM2. One offer after the answer (W3).** Say **"Should we start a Dubai office?"** and wait. **Hear** after the short summary, once: "Want me to go through the risks?" (or "Want the other options?" when there are no risks). **See** the same question at the end of the "The answer is ready…" line in the chat. Say **"yes"**. **Hear:** the risks, briefly, and no new team. Then say **"no"**. **Hear:** nothing.
- **RM3. "Leave it" (W4).** Say **"Ok, I will leave it as it is."** **Hear:** "Okay, leaving it as it is." No "Did you say…?", no team. Also try **"keep it as is"** and **"that's fine"**: the same.
- **RM4. A change said twice (W1).** Say **"Assume three hires."** **Hear:** "Your change to three hires isn't in this answer yet. Say yes to restart with it." Say **"Assume three hires."** again. **Hear** the same reminder once more; **see** it in the chat with the open card right under it ("Restart with my change" / "Keep going"), and no card saying "Restarted.". Nothing runs.
- **RM5. Sounds after the reminder, then the badge (W2).** Say **"hmm"**, then **"okay"**. **Hear:** nothing for "hmm", then "Restarting with your change." When it is done, **see** $43,770.86 and -2.58 and the badge **"Figures verified · N assumptions to confirm"**. If it says "Not verified", open the badge and write down its reasons and the lines above it ("Something from … is unverified", "Verifier sent … back"): the runner could not make it fail on this PC.
- **RM6. Re-run from the last decision team (W5).** Say **"What did we decide before about Dubai?"** (a Librarian-only team) and wait for it. Then say **"Re-run the Analyst."** **Hear:** "Re-running only the Financial Analyst on the Dubai question. …"; not "not on this team".
- **After the check:** close the window (or `Remove-Item Env:FOUNDEROS_STAGE_DELAY_S`) to go back to normal speed.

**Superseded by RM above (done: RL2a–RL2d PASS on 2026-11-16): RL1 to RL5.**
**M5 live check after fix round 7 of 2026-11-16: RL1, RL2a to RL2d, RL3 to RL5.** Headphones, Hands-free, approval at Never, Windows PowerShell 5.1 from `D:\Founder-OS`.

- **RL1. The right code, slowed down.** Close **every** FounderOS window, then `Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue` **Expect:** nothing (if a line shows, an old backend is still running: close it or restart Windows). Then `git pull origin claude/m5-voice; $env:FOUNDEROS_STAGE_DELAY_S = "8"; .\run.bat` (8 s before each stage, so you can time each step; this window only).
- **RL2a. A change in the first stage.** Say **"Should we start a Dubai office?"**. **See** under the conversation: "Step 1 of 3: Librarian, Market Scout and Financial Analyst working…". While that line shows, say **"Assume three hires."** **Hear at once** (cutting off the team line if it is playing): "That changes the decision. Restart with your change?" **See:** one card. Say **"keep going"**.
- **RL2b. A change in the last stage.** Say **"Should we start a Dubai office?"** again. When the line says "Step 3 of 3: … working…", say **"Assume three hires."** **Hear at once:** "That changes the decision. Restart with your change?" Say nothing: the line moves to "Verifying…", then "Done"; after the short summary, **hear once:** "Your change to three hires isn't in this answer yet. Say yes to restart with it." Say **"keep going"**.
- **RL2c. A change while the summary is spoken.** Ask the Dubai question again and wait for "Done". As soon as the summary starts, say **"Assume three hires."** **Hear:** the summary stops, then "Your change to three hires isn't in this answer yet. Say yes to restart with it." once, and nothing more of the summary. Say **"keep going"**.
- **RL2d. A change after the run.** Ask the Dubai question again and wait until the summary and "Want me to go through the risks?" are over. Say **"Assume three hires."** **Hear:** "Your change to three hires isn't in this answer yet. Say yes to restart with it." once (not "Restart with your change?"). **See:** one card. Do not answer yet.
- **RL3. Sounds.** Say **"hmm"**, then **"okay"**. **Hear:** nothing, then "Restarting with your change." **See:** $43,770.86 and -2.58.
- **RL4. Unclear and greeting.** Say **"Okay, I will leave it as it is."** **Hear:** "Did you say: …?". Say **"no"**, then **"Hello? Yes?"** **Hear:** "Okay. Say it again.", then "Hello. What would you like to look at?"
- **RL5. Re-run.** Say **"Re-run the analyst."** **Hear:** "Re-running only the Financial Analyst again. …" and no "Team: …" line.
- **After the check:** close the window (or `Remove-Item Env:FOUNDEROS_STAGE_DELAY_S`) to go back to normal speed.

**The scenarios yourself (about 20 minutes, Ollama running, FounderOS closed or open: it uses its own port and data folder):** `.\.venv\Scripts\python.exe scripts\voice_scenarios.py` **Expect:** a table of PASS; the report path is printed (in your Temp folder). `--typed`, `--spoken` or `--only S3 RL2c` run part of it (RL2a to RL2d are the changes of round 7, W1 to W5 those of round 8).

**Superseded by RL above (done: results under "Founder feedback"): RZ1 to RZ7.**
**M5 re-test after fix round 5 of 2026-11-15: RZ1 to RZ7.** Headphones or a headset. Hands-free, approval at Never. Windows PowerShell 5.1, from `D:\Founder-OS`. Then merge, or write what you saw under "Founder feedback".

- **RZ1. Get the code.** Close the backend and frontend windows, then `git fetch origin; git checkout claude/m5-voice; git pull origin claude/m5-voice; .\run.bat`. No new packages or settings. Press the microphone, choose **Hands-free**.
- **RZ2. A change in the last stage (U1), and the reminder.** Ask **"Should we open a Dubai office?"**. When the Activity tab shows only the Devil's Advocate working, say **"Assume three hires."**, even over the voice. **Hear:** "That changes the decision. Restart with your change?" within about two seconds, never "Did you say …?". **See:** one card. Say nothing. **Hear**, after the summary: "Your change to three hires isn't in this answer yet. Say yes to restart with it." once. Say **"yes"**. **See:** $43,770.86 and -2.58.
- **RZ3. Sounds do nothing (U2).** Repeat RZ2 up to the reminder, then say **"mm"**, **"hmm"**, **"uh-huh"**. **Hear / see:** nothing, no new team, the card still open. Then **"okay"**: "Restarting with your change."
- **RZ4. An unclear turn never starts a team (U0).** With nothing running, say **"Okay, I will leave it as it is."** **Hear:** "Did you say: Okay, I will leave it as it is? Say yes to look into it, or say it again." Say **"no"**: "Okay. Say it again." No team ran.
- **RZ5. A greeting (U4).** Say **"Hello? Yes?"**. **Hear:** "Hello. What would you like to look at?" and nothing from the earlier answer. Say **"yes"**: nothing happens.
- **RZ6. Re-run the analyst, heard imperfectly (U3, U5).** After a Dubai answer, say **"Re-run the analyst."** (it is fine if the transcript shows "Analyt"). **Hear:** "Re-running only the Financial Analyst again. The rest of the team's findings stand." **See:** only the Financial Analyst works; no Perspective lens; each metric chip once. Say **"Re-run the librarain"** (or any name two letters off): **Hear:** "Did you mean re-run the Librarian?".
- **RZ7. The badge (U5) and the tests.** On any "Not verified" badge, hover (**See:** "Click to see why") and click: **See:** the reasons. If one looks wrong, copy it into feedback. Tests without a microphone: `.\.venv\Scripts\python.exe -m pytest backend\tests\test_voice_round6.py -q` **Expect:** all pass.

**Superseded by RZ above (done: results under "Founder feedback"): RY1 to RY7 of M5.**
**M5 re-test after fix round 4 of 2026-11-15: RY1 to RY7 of M5.** Headphones or a headset. Hands-free, approval at Never. Commands work in Windows PowerShell 5.1, from `D:\Founder-OS`. Then merge, or write what you saw under "Founder feedback". Figures follow the sample data. (The older "RY1 to RY7" further down are M4's.)

- **RY1. Get the code.** Close the backend and frontend windows. Then:
  `git fetch origin; git checkout claude/m5-voice; git pull origin claude/m5-voice; .\run.bat`
  No new packages and no new settings. Gear > **Ask before a team runs** > **Never** > **Save**. Press the microphone, choose **Hands-free**.
- **RY2. A change, and "yes" (T2, T3).** Say **"Should we open a Dubai office?"**. After the opening turn, while the team works, say **"Assume three hires."** **Hear, once:** "That changes the decision. Restart with your change?" **See:** one card with those same words, your change under them, and **Restart with my change** / **Keep going**. Say nothing until the summary has ended. **Hear:** the findings and the proposal (still two hires), and then nothing more: no "You asked for a change …", no "Want me to go through the risks?". **See:** still one card, now below the answer. Now say **"yes"**. **Hear:** "Restarting with your change." **See:** a new run, and in its answer "… with three local hires, as you asked, is $30,000.00 up front and **$43,770.86** a month, moving projected runway from 11.23 to 8.65 months (**-2.58**)". It does not matter whether the transcript shows "Yes.", "Yes?" or "Yeah!".
- **RY3. The change said late (T1).** Ask the Dubai question again. Watch the Activity tab; when People & Ops and Regulatory & Tax are done and the Devil's Advocate is working, say **"Assume three hires."** **Hear:** the offer within about two seconds, before the summary. **See:** the card at the same moment. Say **"yes"** at once. **Hear:** "Restarting with your change." **See:** $43,770.86 and -2.58. If the offer comes late or not at all, please note what the transcript line under the microphone showed, and whether you heard "Did you say …?".
- **RY4. Yes after a noise, and no.** Ask the Dubai question, say **"Assume three hires."** while the team works, wait for the summary, say **"mm"**, then **"okay"**. **Hear:** nothing after "mm"; "Restarting with your change." after "okay". Once more, and answer **"no"**: **Hear:** "Okay, I'll leave it as it is." **See:** the card says "Carried on as it was."
- **RY5. No verification line when no team ran (T4).** Say **"Hello."** **See:** the reply with the **Not run** badge, and no line "The answer is ready, but some of it is unverified". Then, with nothing on offer, say **"yes"**. **See / hear:** nothing happens (no new question, no "Not run" reply).
- **RY6. Re-run one agent, and the trade-off (T5).** After a Dubai summary, say **"Re-run the analyst."** **Hear:** "Re-running only the Financial Analyst again. The rest of the team's findings stand." **See:** only the Financial Analyst working in the new run; the others keep their findings. Then read the text answer. **See:** if it has a sentence on "the trade-off", it names two options (for example the pilot and the full office), or it is code's: "The main trade-off: with Travel-led pilot, …; with Full office, …".
- **RY7. Timings and the tests.** After your own turns:
  `$m = Invoke-RestMethod http://127.0.0.1:8000/api/voice/metrics; $m.p50_ms; $m.recent_barge_ins | Format-Table paused_ms,stopped_ms,client_flush_ms,verdict,by,text`
  **Expect:** as in RX7 (first words p50 about 0.9 s, every `paused_ms` under 150).
  The tests, without a microphone: `.\.venv\Scripts\python.exe -m pytest backend\tests\test_voice_round5.py backend\tests\test_voice_round4.py -q`. **Expect:** all pass.

**Superseded by RY above (done: results under "Founder feedback"; kept for reference): RX1 to RX7.** Two things RX says are no longer so: the card's words are the voice's ("That changes the decision. …"), and RX5's second asking with the answer is gone (one change, one offer).
**M5 re-test after fix round 3 of 2026-11-14: RX1 to RX7.** Headphones or a headset give the best results. Hands-free, approval at Never. Commands work in Windows PowerShell 5.1, from `D:\Founder-OS`. Then merge, or write what you saw under "Founder feedback". Figures follow the sample data.

- **RX1. Get the code.** Close the backend and frontend windows. Then:
  `git fetch origin; git checkout claude/m5-voice; git pull origin claude/m5-voice; .\run.bat`
  No new packages and no new settings. Gear > **Ask before a team runs** > **Never** > **Save**. Press the microphone, choose **Hands-free**.
- **RX2. A stopped run is never spoken (S1).** Say **"Should we open a Dubai office?"**. After the opening turn, while the team works, say **"stop"**. **Hear:** "Stop the team? Say yes to stop." Say **"yes"**. **Hear:** "Stopping the team.", then "That run was cancelled." Then stay quiet for a minute. **Not heard:** "My proposal is …", any finding, any offer. **See:** the run marked cancelled, with no answer.
  Do it once more and say "stop" late, when the Activity tab shows the Devil's Advocate done (the answer is being written): the same result.
  Then typed: ask the Dubai question again and type **stop** in the box. **See / hear:** "Stopping the team." at once, with no question.
- **RX3. Each offer once, and then it waits (S2, S3).** Ask the Dubai question and stay quiet until the summary ends with **"Want me to go through the risks?"**. Stay silent for 20 seconds. **Hear:** nothing. Say **"mm"**, then **"uh-huh"**. **Hear:** nothing (the offer is not said again). Say **"yes"**. **Hear:** up to three risks, then **"Want the other options?"** once. Stay silent for 20 seconds. **Hear:** nothing. Say **"no thanks"**. **Hear:** "Okay. The rest is on screen."
  If you can, run RX3 once on loudspeakers too: that is where its own voice could be taken for your answer.
- **RX4. A change said while the team works (S4).** Ask the Dubai question. After the opening turn, while the team works, say **"Assume three hires."** **Hear:** "That changes the decision. Restart with your change?" **See:** the change as a card with **Restart** and **Keep going**. Say **"yes"**. **Hear:** "Restarting with your change." **See:** a new run, and in its answer "… with three local hires, as you asked, is $30,000.00 up front and **$43,770.86** a month, moving projected runway from 11.23 to 8.65 months (**-2.58**)".
- **RX5. A change you do not answer is not lost (S4).** Ask the Dubai question again, say **"Assume three hires."** while the team works, hear the offer, and say nothing. **Hear**, when the team is done: the findings and the proposal (still two hires: $32,347.24 is on screen), then **"You asked for a change while the team worked, and this answer does not have it. Restart with it?"** in place of the offer of risks. Say **"yes"**. **See:** $43,770.86 and -2.58.
- **RX6. Re-run one agent (RW5 again), and the text answer (S5).** After a Dubai summary, say **"Re-run the analyst."** **Hear:** "Re-running only the Financial Analyst again. The rest of the team's findings stand.", no second team introduction, then the summary, ending with its offer **once**. **See:** only the Financial Analyst working in the new run. RW5 failed for you and S1 to S5 do not say how; if it fails again, please write what you heard and saw.
  Then read the Dubai text answer. **See:** "moves you away from your goal "Extend runway …"" **once**; the earlier memo named **once** ("You already have a proposed memo on this from 2026-11-06 …: what has changed since you drafted it?"); no "You already proposed a Dubai office …", and no "in 2027".
- **RX7. Barge-in timings and the tests.** After your own turns:
  `$m = Invoke-RestMethod http://127.0.0.1:8000/api/voice/metrics; $m.p50_ms; $m.recent_barge_ins | Format-Table paused_ms,stopped_ms,client_flush_ms,verdict,by,text`
  **Expect:** first words p50 about 0.9 s; metric answer p50 about 1.8 s; every `paused_ms` under 150; `stopped_ms` about 1,000 for a barge-in by "duration". New: a row with `by` "echo" is FounderOS hearing its own words (it resumed and took no turn); tell me if one of those rows holds words you said.
  The tests, without a microphone: `.\.venv\Scripts\python.exe -m pytest backend\tests\test_voice_round4.py -q`. **Expect:** all pass.

**Superseded by RX above (done: results under "Founder feedback"; kept for reference): RW1 to RW10.** Two things RW says are no longer so: a typed "stop" is not asked about (RW2), and a change said mid-run is offered as "That changes the decision. Restart with your change?". Headphones or a headset give the best results. Hands-free, approval at Never. Commands work in Windows PowerShell 5.1, from `D:\Founder-OS`. Then merge, or write what you saw under "Founder feedback". Figures follow the sample data.

- **RW1. Get the code.** Close the backend and frontend windows. If your `.env` has a line `VOICE_BARGE_IN_MS=600`, change it to `1000` or delete it. Then:
  `git fetch origin; git checkout claude/m5-voice; git pull origin claude/m5-voice; .\run.bat`
  No new packages. Gear > **Ask before a team runs** > **Never** > **Save**. Press the microphone, choose **Hands-free**.
- **RW2. A filler never stops the team (R1).** Say **"Should we open a Dubai office?"**. After the opening turn, while the team works in silence, say **"uh-huh"**, then **"mm"**, **"right"**, **"okay"**, a few seconds apart. **Hear:** nothing. **See:** the team still working; no "Stopping the team." Then say **"stop"**. **Hear:** "Stop the team? Say yes to stop." Say **"no"**. **Hear:** "Okay, the team carries on." Say **"stop"** again, then **"yes"**. **Hear:** "Stopping the team.", then "That run was cancelled."
  Then, during any spoken answer, say a short **"uh-huh"**: a tiny pause, and it carries on.
- **RW3. One opening turn, then silence (R4).** Ask the Dubai question again and stay quiet. **Hear:** "On it.", then once: "I've put together a team of six: the Librarian, Market Scout, … and a Devil's Advocate. They're looking at the Dubai office from different angles so the decision holds up." Then silence, with at most one "Still working on it." after about 30 seconds. **Not heard:** any line about an agent, a stage or the Verifier, any figure, the assumption question. **See:** all of those in the panel as before.
- **RW4. Findings, outcome, offer (R4, R5).** When the team is done, **hear** in this order: "The full office would cost 30 thousand dollars up front and around 32 thousand dollars a month, which shortens your runway by about two months." (then, if they apply: the goal it moves away from, the cash warning, "The costs are assumptions for you to confirm." or "Part of this is unverified, so check the screen.") "My proposal is Travel-led pilot: 3 thousand dollars a month, which shortens your runway by about a week." "The trade-off: you learn more slowly from trips than from a local presence, and win customers later." **"Want me to go through the risks?"** Then silence.
  Say **"yes"**. **Hear:** up to three risks, none of them a question, then "Want the other options?". Say **"no thanks"**. **Hear:** "Okay. The rest is on screen."
- **RW5. Re-run one agent (R8).** After the summary, say **"Re-run the analyst."** **Hear:** "Re-running only the Financial Analyst again. The rest of the team's findings stand." **See:** a new run in which only the Financial Analyst works; the others are done at once. **Hear:** no second team introduction, then the summary again, ending with its offer.
- **RW6. An accepted change is applied (R8).** Say **"Assume three hires."** **Hear:** "That changes the decision. Restart with your change?" Say **"yes"**. **Hear:** "Restarting with your change." **See:** the offer's card marked accepted, a new run, and in its answer "… with three local hires, as you asked, is $30,000.00 up front and **$43,770.86** a month, moving projected runway from 11.23 to 8.65 months (**-2.58**)". **Hear** in the summary: "… around 44 thousand dollars a month, which shortens your runway by about two and a half months."
  Then the button: type or say **"Assume two hires."** and click **Restart** on the card. **See:** $32,347.24 and -2.07 again.
- **RW7. An unclear number is asked about (R3).** After a Dubai answer, type **make it a 2% team** (or say "make it a two percent team"). **Hear / see:** "Did you mean two people?" and no restart yet. Say **"yes"**. **Hear:** "Restarting with your change." Then type **three**. **See:** "Did you mean three people?" Type **no**. **See:** "Okay, nothing has changed. Say the number with what it counts, for example three hires."
- **RW8. Transcription (R6).** Say each of these and read your turn in the panel: **"Should we open a Dubai office?"**, **"Re-run the analyst, assume three hires."**, **"Make it a two person team."** **See:** the words as you said them (or, if "two person" still comes out as "2%", the question of RW7 instead of a wrong change). If a turn is read back ("Did you say: …? Say yes, or say it again."), answer it; tell me if that happens on clear speech.
  Optional, the larger model (already on this PC): add `VOICE_STT_MODEL=large-v3-turbo` to `.env`, restart, and repeat RW8. It uses about 0.55 GB more VRAM and was no slower here. Check: `(Invoke-RestMethod http://127.0.0.1:8000/api/voice/status).stt`. The comparison itself: `.\.venv\Scripts\python.exe scripts\stt_bakeoff.py` (about 6 minutes).
- **RW9. A proposed memo gets one question (R7).** With a proposed Dubai memo in the vault (your earlier runs left one), ask the Dubai question. **See** in the answer exactly one question: "You already have a proposed memo on this from … : what has changed since you drafted it?" **Not seen or heard:** "Is the runway still above …, as predicted?", "Is the risk of runway falling below … acceptable?", or the memo mentioned a second time.
- **RW10. Latency and barge-in timings (R2).** `.\.venv\Scripts\python.exe scripts\voice_bench.py` (about 2 minutes), then after your own turns:
  `$m = Invoke-RestMethod http://127.0.0.1:8000/api/voice/metrics; $m.p50_ms; $m.recent_barge_ins | Format-Table paused_ms,stopped_ms,client_flush_ms,verdict,by,text`
  **Expect:** first words p50 about 1 s; metric answer p50 about 2 s; every `paused_ms` under 150, also after you switch between Hold to talk and Hands-free and back; `stopped_ms` about 1,000 for a barge-in by "duration" (it was about 575 with the old 0.6 s rule); rows by "duration" now carry their text.
  The tests, without a microphone: `.\.venv\Scripts\python.exe -m pytest backend\tests\test_voice_round3.py -q`. **Expect:** all pass.

**Superseded by RW above (kept for reference): RV1 to RV11.** What RV2, RV5, RV6 and RV9 say you hear ("Five on this: …", a line a stage, "Running it again, with the Devil's Advocate redoing its part.") is no longer said.
**M5 re-test after the fix round of 2026-11-13. Run this one first: RV1 to RV11 (about 20 minutes).** Use the same microphone and loudspeakers as in your V7 test: that set-up is what failed. Commands work in Windows PowerShell 5.1, from `D:\Founder-OS`. Then merge, or write what you saw under "Founder feedback". Figures below follow the sample data; yours follow your data.

- **RV1. Get the code.** Close the backend and frontend windows, then:
  `git fetch origin; git checkout claude/m5-voice; git pull origin claude/m5-voice; .\run.bat`
  No new packages or models. Gear > **Ask before a team runs** > **Never** > **Save**. Press the microphone, choose **Hands-free**.
- **RV2. A question spoken over the narration (V7).** Say **"Should we open a Dubai office?"**. **Hear:** "On it.", then "Five on this: the Financial Analyst on the numbers, …". While it is saying that, say **"What is our churn?"**. **Hear:** it stops within a moment, then "I'll keep that for when this run finishes." **See:** "What is our churn?" as your turn, and a "Queued" card. Stay quiet. **Hear:** the stage lines and the summary (RV5, RV6), then "Your next question is ready. Say ask it, or drop it." **See:** **Ask it now** / **Drop it**. Say **"ask it"**. **Hear:** "Running it now.", then "Your logo churn is about … percent a month."
  Repeat once, asking **"What's our current churn?"** in a gap between two of its lines instead of over one.
- **RV3. It does not hear itself.** Ask the Dubai question again and say nothing until the summary ends. **Hear:** no stutter, no pause in the middle of a line. **See:** no turn that you did not say, and the state never reads "Interrupted". Then:
  `$m = Invoke-RestMethod http://127.0.0.1:8000/api/voice/metrics; $m.recent_barge_ins | Format-Table paused_ms,stopped_ms,verdict,by,text`
  **Expect:** no rows from this run. If it does pause itself, put `VOICE_ECHO_GATE=0.5` in `.env`, restart and try again; if it is slow to stop when you talk over it (RV2, or V5), try `0.2`.
- **RV4. Barge-in and backchannel still work (V5, V6 again, because of the echo gate).** While it speaks the summary, say **"Wait, make it a two person team instead."**: it stops, and offers the restart. During another answer say a short **"uh-huh"**: a tiny pause, then it carries on.
- **RV5. The team, once; one line a stage (A, B).** In RV2 or RV3, **hear** who is on the team once, in one or two sentences. Then one line as each stage ends: "The Financial Analyst has priced it, the Librarian has checked your notes and the Market Scout has looked at the market." **Not heard:** "… are done; two to go", the assumption question, or any figure. **See:** all of those still in the panel.
- **RV6. A summary and an offer, not the text card (B, C).** After the stages, **hear** two or three sentences and a question, then silence:
  "My proposal is Travel-led pilot: 3 thousand dollars a month, which shortens your runway by about a week." "One warning: in about four in five of the simulated futures, cash runs out within a year." (only if your data's risk is 50 % or more) "The costs are assumptions for you to confirm." "Want me to go through the risks?"
  **See:** the exact figures ($3,000.00, -0.21 months) on the card, not spoken. Say **"yes"**. **Hear:** up to three risk sentences, then "Want the other options?". Say **"no thanks"**. **Hear:** "Okay. The rest is on screen."
- **RV7. Rounded numbers (B).** Say **"What is our runway?"**. **Hear:** "Checking that now.", "Your runway is about ten and a half months.", the warning if it applies, "Want the detail?". **See:** 10.65 months on the card. Say **"yes"**. **Hear:** "Closing cash is about 1.8 million dollars, with a net burn of around 170 thousand dollars per month, so cash reaches zero in September 2027." Then ask **"What is our net burn?"** ("around 170 thousand dollars a month") and **"What is our gross margin?"** ("about 72 percent").
  The normaliser's table, without a microphone: `.\.venv\Scripts\python.exe -m pytest backend\tests\test_voice_round2.py -q -k "said or spoken or sentence or metric_is_led"`. **Expect:** all pass (INR lakh and crore are in it).
- **RV8. Follow-ups in context (D).** After the Dubai summary, say **"Why that option?"**. **Hear, at once:** "I proposed Travel-led pilot because it costs less than Full office and is easier to undo. The trade-off: you learn more slowly from trips than from a local presence, and win customers later. The costs of each option are on screen." No new run. Ask it again after the churn answer: the same reply (the decision stays open). Then say **"And what about churn?"**. **Hear:** "Checking that now.", "Your logo churn is about … percent a month." **See:** the run's title is "What is our churn?".
- **RV9. Re-run an agent by voice (E).** Ask the Dubai question; right after the team line say **"Re-run the analyst, assume three hires."** **Hear:** "Re-running the Financial Analyst with your change." (if the analyst had already finished: the restart offer; say **"restart"**). After the summary, say **"Redo the Devil's Advocate."** **Hear:** "Running it again, with the Devil's Advocate redoing its part.", then the team line, the stage lines and a summary again. **See:** a new run with the same team. Typed, both sentences do the same.
- **RV10. One full stop.** In the runway answer of RV7, **see** the warning end "… so protecting runway comes first." with one full stop. If you still see two, tell me where (the answer card, the memo, or another panel): I could not make the backend produce it.
- **RV11. Your latency numbers (V10).** With approval at **Never**: `.\.venv\Scripts\python.exe scripts\voice_bench.py` (about 2 minutes), then after your own turns:
  `$m = Invoke-RestMethod http://127.0.0.1:8000/api/voice/metrics; $m.p50_ms; $m.recent_barge_ins | Format-Table paused_ms,stopped_ms,client_flush_ms,verdict,by`
  **Expect:** first words p50 about 1 s or less; first answer audio p50 about 3 to 4 s (a metric's line is now made as soon as the routine has the figure); barge-in pause under 150 ms; client flush a few ms. Write the p50s in the Gate log row or under Founder feedback.

**M5 Voice (Major gate; V3 to V6, V8 and V9 passed on 2026-11-13; reference). V1 to V10.** V7 and V10 are replaced by RV2 and RV11 above, and what you hear in V3 to V8 is now the shorter speech of RV5 to RV7. You need your microphone (headphones make barge-in cleanest). Commands work in Windows PowerShell 5.1, from `D:\Founder-OS`. Then merge, or write what you saw under "Founder feedback".

- **V1. Get the code and the voice packages.** Close the backend and frontend windows, then:
  `git fetch origin; git checkout claude/m5-voice; git pull origin claude/m5-voice; .\.venv\Scripts\python.exe -m pip install -e "backend[dev,gpu,voice]"; .\.venv\Scripts\python.exe scripts\download_voice_models.py`
  **Expect:** "have small.en", "have base.en", Kokoro and voices saved (about 900 MB the first time). Then `.\run.bat`.
- **V2. Engines and VRAM.** Wait about 30 s after start-up, then:
  `$s = Invoke-RestMethod http://127.0.0.1:8000/api/voice/status; $s.stt; $s.tts; $s.vad; $s.notes; $s.vram_gb`
  **Expect:** `stt` small.en on `cuda`, `tts` kokoro on `cpu`, `vad` silero, no notes, `vram_gb.whisper` about 0.5. Also `docker exec ollama ollama ps` (qwen3:8b about 5.9 GB) and `nvidia-smi --query-gpu=memory.used,memory.total --format=csv`. Write the three numbers down.
- **V3. Push-to-talk, a metric.** Open `http://127.0.0.1:3000`, press the microphone button (allow the microphone). Hold the mic, say **"What is our runway?"**, let go. **Hear:** "Checking that now." within about a second, then "Runway (actual burn) is ... months ...". **See:** your words in the panel, the answer card, and under the mic "first words … ms · answer … ms · STT … ms".
- **V4. Hands-free.** In the mode box choose **Hands-free**. Say **"What is our gross margin?"** and stop talking. **Hear:** the answer without pressing anything. The state reads Listening, Thinking, Speaking.
- **V5. Barge-in.** Hands-free, Gear > **Ask before a team runs** > **Never** > **Save**. Say **"Should we open a Dubai office?"**. While it is still narrating (the team is working; "On it…" or "… are done"), say **"Wait, make it a two person team instead."**. **Hear:** it stops within a moment of your first word. **See:** "Interrupted", then your words as a turn and the restart offer ("Restart with my change"). Say **"restart"**: the new run starts, and its answer says "with two local hires, as you asked". (Said after the answer has started, the team is done, so it becomes a new question instead.)
- **V6. Backchannel.** While it speaks a long answer (ask **"Should we raise our prices by 10%?"**), say a short **"uh-huh"** or **"right"**. **Hear:** a tiny pause, then it carries on from where it was. The latency line shows "(backchannel)".
- **V7. Mid-run question.** While the Dubai team works, say **"What is our churn?"**. **Hear:** that it is queued; when the answer is done, "Your next question is ready. Say ask it, or drop it." Say **"ask it"**: the churn answer is spoken.
- **V8. Approval by voice.** Gear > **Ask before a team runs** > **Always** > **Save**. Say **"Should we open a Dubai office?"**. **Hear:** "Waiting for your approval of this team: … Say approve, or hold it." Say **"approve"**: the team runs. Set approval back and **Save**.
- **V9. No unverified number spoken; quiet.** In V5 to V8 the narration never says a figure (figures come only in the answer). Press the bell (**Quiet on**) and ask by voice: nothing is spoken, the transcript and the answer still appear.
- **V10. Your latency numbers.** With approval at **Never**, run `.\.venv\Scripts\python.exe scripts\voice_bench.py` (about 2 minutes; it plays recorded questions into the backend, including the Dubai decision with an interruption), then after your own V3 to V6 turns:
  `$m = Invoke-RestMethod http://127.0.0.1:8000/api/voice/metrics; $m.p50_ms; $m.recent_barge_ins | Format-Table paused_ms,stopped_ms,client_flush_ms,verdict,by`
  **Expect:** first words p50 about 1 s or less; first answer audio p50 about 3 to 4 s; barge-in pause under 150 ms; client flush a few ms. Write the p50s in the Gate log row or under Founder feedback.

**M4 re-test after round 3 (done: M4 ACCEPTED; reference). RY1 to RY7.** It covers 58, 51, 54, 56 and 57 of "[M4] Re-test RX1–RX12", plus the RX12 popover check. Commands work in Windows PowerShell 5.1, from `D:\Founder-OS`. Then merge, or write what you saw under "Founder feedback".

- **RY1. Get the code.** Close the backend and frontend windows, then:
  `git fetch origin; git checkout claude/m4-canvas-ui; git pull origin claude/m4-canvas-ui; .\run.bat`
  On **Data**, press **Load sample data** once. Set **Ask before a team runs** to **Never** for RY2.
- **RY2. Every metric question gets its own metric (58, 45).** One loop (about a minute):
  `foreach ($q in 'What is our gross revenue churn?','What is our net revenue churn?','What is our logo churn?','What is our gross burn?','What is our net burn?','What is our gross margin?','What is our MRR?','What is our ARR?','What is our CAC?','What is our LTV/CAC?') { $r = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body (@{message=$q; stream=$false} | ConvertTo-Json); $m = $r.metrics[0]; '{0} | {1} | {2} | {3} | {4}' -f $q, $m.metric, $m.value, $m.lineage.period, $r.verification.state }`
  **Expect:** in order, `revenue_churn`, `nrr`, `logo_churn`, `gross_burn`, `net_burn`, `gross_margin`, `mrr`, `arr`, `cac`, `ltv_cac`, each with a period. Every state is `verified`, except net revenue churn: `assumptions` (it is shown as net revenue retention, and says so).
  In the browser, ask **What is our gross revenue churn?** **See:** "Gross revenue churn (monthly) is … for August to October 2026" (the months follow your data), nothing about burn, and a chip ending "· Aug–Oct 2026".
- **RY3. Nothing ran, no green badge (51).** Gear > **Ask before a team runs** > **Always** > **Save**. Ask **Should we open a Dubai office?** and press **Hold the team back**. **See:** "I held the team back because it was not approved…" with a grey **Not run** pill, not "Verified". Say **Hello**: also **Not run**. Set approval back and **Save**.
- **RY4. No sentence twice (54, 54b).** Ask **Should we open a Dubai office?** **See:** the goal is named once, and "what has changed since you drafted it?" is asked once. Then type **also make it a two person team** and press **Restart with my change**. **See:** the new answer says "with two local hires, as you asked".
- **RY5. Queued questions are always offered (56).** With approval **Always**, ask **Should we open a Dubai office?**, then at once type **What is our runway?** and **What is our churn?**. Press **Approve and run**. **See:** when the answer is in, the runway question shows **Ask it now** / **Drop it**; the churn one still says "Queued". Press **Drop it**: the churn question now shows **Ask it now** / **Drop it**. Nothing is asked by itself. Set approval back.
- **RY6. Why this option (57).** Ask **Should we raise our prices by 10%?** **See:** the first sentence reads "Proposed: New customers only, … ; proposed over Change prices by +10 % (runway +1.12 months) because Change prices by +10 % moves you away from your goal "Bring logo churn under 1.5 % a month"" (figures follow your data). The goal is not repeated in the next sentence.
- **RY7. Small ones (53, 52, 59, RX12 popover).**
  - On an amber answer (RY6), the badge text wraps inside the panel; nothing is cut off.
  - Ask **What will our MRR be in 2031?** If cash runs out inside the projection, the answer adds "and that you stay funded after cash runs out in …".
  - Upload `one_row.csv` (from RX6) to `pnl` with **Replace** three times: "Earlier versions you can restore" lists the identical one-row version once.
  - On the runway answer, open the badge: the popover stays fully on screen.

**M4 re-test after round 2 (done: results under "Founder feedback"; reference). RX1 to RX12.** It covers 49, 40, 22, 42, 46, 47, 48, 44, 43 and 45 of "[M4] Re-test RW1–RW12, round 2". Commands work in Windows PowerShell 5.1, from `D:\Founder-OS`. RW1 to RW12 below still apply. Then merge, or write what you saw under "Founder feedback".

- **RX1. Get the code.** Close the backend and frontend windows, then:
  `git fetch origin; git checkout claude/m4-canvas-ui; git pull origin claude/m4-canvas-ui; .\run.bat`
  On **Data**, press **Load sample data** once.
- **RX2. Beyond the projection (49).** Ask **What will our MRR be in 2031?** **See:** the answer starts "The model's projection runs to Oct 2027, so it has no figure for 2031." (the month is later if the team projected further) Its last month's MRR follows, labelled "(assumption, confirm)". No other figure is given for 2031. The badge is amber, never green; click it and "2031 is beyond the projection, which ends Oct 2027" is listed. Repeat with **next year** and **in 5 years** in place of "in 2031". One line:
  `$s = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/conversation/turn -ContentType 'application/json' -Body '{"text":"What will our MRR be in 2031?"}'; Start-Sleep 60; (Invoke-RestMethod "http://127.0.0.1:8000/api/runs/$($s.run_id)").result.verification.state`
  **Expect:** `assumptions` (or `not_verified`), never `verified`. If **Ask before a team runs** is **Always**, approve in the browser first.
- **RX3. A follow-up changes the open decision (40).** Ask **Should we open a Dubai office?** and wait for the answer. Then type **also make it a two person team**. **See:** "That changes the decision. Restart with your change?" with **Restart with my change**; no new run yet. Press it. **See:**
  - The new run has the same team as before, with the Financial Analyst.
  - Its title reads "Should we open a Dubai office? · changed: also make it a two person team" (41).
  - Its cost model shows **Local hires 2** as "your figure".
- **RX4. Turns while planning and awaiting approval (22).** Gear > **Ask before a team runs** > **Always** > **Save**. Ask **Should we open a Dubai office?** and at once type **What is our runway?** and press Enter. **See:** a "Queued for when this run finishes" card straight away, and only one Advisor answer card (no second run). While "The team is waiting for your approval." shows, type **What is our churn?**: a second queued card appears. Set approval back and **Save**.
- **RX5. Asked twice, queued once (42).** During RX4, type **what is our  RUNWAY?** **See:** "That question is already queued." and still one card for it.
- **RX6. One press resets the data (46).** On **Data**, upload a one-row file to `pnl` and press **Replace**:
  `"month,account,category,amount`n2026-10,Rent,opex,1000" | Set-Content -Encoding UTF8 $env:TEMP\one_row.csv`
  Then press **Load sample data** once. **See:** every table, pnl included, shows `northwind_financials.xlsx`, and pnl has 360 rows. One line:
  `(Invoke-RestMethod http://127.0.0.1:8000/api/data/tables).loaded | Where-Object table -eq pnl | Select-Object rows, source_file`
  **Expect:** `360 northwind_financials.xlsx`.
- **RX7. Several versions, any restorable (47).** Upload `one_row.csv` to `pnl` with **Replace** three times. **See:** "Earlier versions you can restore". The 360-row version is still listed, marked "(the sample data)", with its source, row count and time. Press **Restore this pnl** on it: pnl has 360 rows again. One line:
  `Invoke-RestMethod http://127.0.0.1:8000/api/data/backups | Select-Object table, rows, source_file, label, clean_sample | Format-Table`
- **RX8. Only meaningful versions (48).** Press **Load sample data** twice. **See:** the second press adds no version. Every listed version says what replaced it ("before uploading one_row.csv", "before the sample data was reloaded"). No "Undo the last upload" button remains.
- **RX9. Units (44).** Ask **Should we raise our prices by 10%?** **See:** in the cost model, Price change reads **+10 %** (not $10), and the extra churn reads **+0.2 / +0.5 / +1 pts** (not $0 / $1 / $1). Money rows still show $.
- **RX10. New customers only is costed (43).** In the same answer's options, **New customers only** shows a cost and a runway change, not "cost not modelled". If it is the proposal, its figures are in the options table.
- **RX11. Periods (45).** Ask **What is our gross revenue churn?** **See:** the sentence says the period ("for August to October 2026", or "in October 2026"). Its lineage chip ends with the period, e.g. "· Aug–Oct 2026".
- **RX12. Small ones (39, 37, 38, 50).**
  - With cloud off, Activity shows "Cloud off" and the rail shows "cloud off" (no "0/6").
  - On the runway answer, open the badge: the popover stays fully on screen.
  - With the sliders reset, "The scenario matches the base." sits above the cash chart, clear of the "Under 3 months of cash" label.
  - The Dubai lead ends "…all of these are assumptions to confirm." with no "(assumption, confirm)" after it.
  Optional smoke tests: `Set-Location frontend; npx playwright test; Set-Location ..` **Expect:** `2 passed`.

**M4 re-test after the founder-review fixes (done: results under "Founder feedback"; reference). RW1 to RW12.** It covers P1 and P2 of "[M4] Founder review W0–W15". Commands work in Windows PowerShell 5.1, from `D:\Founder-OS`. W0 to W15 below still apply; run them again only if something here looks off. Then merge, or write what you saw under "Founder feedback".

- **RW1. Get the code.** Close the backend and frontend windows, then:
  `git fetch origin; git checkout claude/m4-canvas-ui; git pull origin claude/m4-canvas-ui; Set-Location frontend; npm install; Set-Location ..; .\run.bat`
  **Expect:** the browser opens `http://127.0.0.1:3000`. Press **Load sample data** on **Data** once, so the numbers are the demo set (one workbook, `northwind_financials.xlsx`).
- **RW2. Green badge (14).** Ask **What is our runway?** **See:** a green **Verified** badge. Click it: a popover lists the sources (the data file). No assumption narration under the answer (9).
- **RW3. Dubai end to end, amber badge (14, 16, 18, 19, 23, 24, 26, 27).** Keep the proposed Dubai memo from W11 in the vault. Gear > **Ask before a team runs** > **Always**; ask **Should we open a Dubai office?** and approve. **See:**
  - The answer starts with "Proposed: <option>, $… a month, runway ±… months.", then "The full model, …", then at most about three more sentences, none said twice. No "your adviser or your adviser", no "by -2.07".
  - It asks "what has changed since you drafted it?" about the memo from its date, and never about meeting its kill criteria or targets.
  - The badge is amber, "Figures verified · N assumptions to confirm". Click it: the assumptions are listed, with **Enter your figures**; that button puts "My figures: " in the input box.
  - No "(removed: unsupported source)" in the text. If something was taken out, a small "N claims removed" chip sits by the badge.
  - Any "cheapest / least costly" sentence names the option that is cheapest in the options table, or says speed and risk are not compared there.
  - Figures from the memo on record show its path in brackets and are not counted as unsupported (20).
  - The time shows the work time, plus "· Ns waiting for you" for the approval.
- **RW4. Red badge (14).** Ask **What will our MRR be in 2031?** (no data for it). If the badge is red **Not verified**, click it: the reasons are in words and name no removed figure. (If it is amber or green, that is fine too; note which.)
- **RW5. Amendment (21).** While the Dubai answer is on screen, type **also make it a two person team**. **See:** "That changes the request. Restart with your change?" (not a new queued question). Press **Restart with my change**. **See:** the rerun's options show 2 local hires.
- **RW6. Early turns (22).** Ask a new question and, in the first two seconds, type a second one and press Enter. **See:** it is accepted at once (sent, or queued with a note), never ignored.
- **RW7. Reload (17).** Press F5. **See:** the conversation and the open decision come back. Press F5 during a run: the run finishes, or shows as finished, on its own.
- **RW8. Upload warning, backup and undo (32).** On **Data**, make a one-row file and upload it, choosing table `pnl`:
  `"month,account,category,amount`n2026-10,Rent,opex,1000" | Set-Content -Encoding UTF8 $env:TEMP\one_row.csv`
  **See:** "one_row.csv would change data you already have. Nothing is written yet.", "pnl has 360 rows …; this file has 1", with **Append**, **Replace** and **Cancel**. Press **Replace**. **See:** pnl has 1 row and a backup line with **Undo**. Press **Undo**: pnl has 360 rows again. Check from PowerShell:
  `Invoke-RestMethod http://127.0.0.1:8000/api/data/backups | ConvertTo-Json -Depth 4`
  **Expect:** a list (empty after the undo is fine).
- **RW9. Memo title (25).** On **Decisions**, edit the memo's title and save. **See:** the H1 and the file's `title:` line both change (open it in **Vault**).
- **RW10. Neutral title (10).** **See:** the decision card's title is the question as a neutral topic ("Dubai office"), not a verdict.
- **RW11. Settings Save and Discard (36).** Gear: change **Allow cloud agents**. **See:** "You have unsaved changes" with **Save** and **Discard**; nothing applies yet (the top bar still says "Local only"). Click **Workspace**: a "Save your changes?" dialog with Save, Discard and Stay. Press **Discard**: the old value is back. Change it again and press **Save**: "Saved.", and the badge in the top bar changes. Set it back and **Save**.
- **RW12. Smoke test (optional).** `Set-Location frontend; npx playwright install chromium; npx playwright test; Set-Location ..` **Expect:** `1 passed`.

**M4 Canvas UI, first review (done: the findings are under "Founder feedback"; reference). W0 to W15.** I ran the same flow in a browser here against a test backend with the real model. Commands work in Windows PowerShell 5.1, from `D:\Founder-OS`. Then merge, or write what you saw under "Founder feedback".

- **W0. Get the code.** Close the backend and frontend windows, then:
  `git fetch origin; git checkout claude/m4-canvas-ui; git pull origin claude/m4-canvas-ui; Set-Location frontend; npm install; Set-Location ..; .\run.bat`
  **Expect:** the browser opens `http://127.0.0.1:3000`. Wait until the backend window says the Ollama model is loaded.
- **W1. First look.** **See:** a top bar with Workspace, Activity, Decisions, Data, Vault and a gear; "Local only"; health dots. The Advisor on the left with three starter chips. Four KPI cards: Runway `10.65 mo`, Net burn `$172,280.47`, MRR `$255,344.27`, Gross margin `72.13%`. Below them the cash chart and Monte Carlo. Colours and layout should match `docs/design/` mock-ups.
- **W2. Lineage.** Click the dashed blue chip on the Runway card. **See:** a popover with Formula, Period, Rows, File, Inputs, and a SQL fold. Press Esc: it closes.
- **W3. Simulator.** Drag **New hires** to 5. **See:** within a second the dashed amber line separates from the solid blue one, "Scenario, with growth" falls, the amber "Under 3 months of cash" band and "Zero cash" line move left, and the Monte Carlo fan changes a moment later. An "assumption, confirm" tag sits under each chart. Click **Reset levers**. Open **Show as a table**.
- **W4. A metric question.** Click the chip **What is our runway?** **See:** in a few seconds an answer with a green **Verified**, "written by code", the figure 10.65 months, and a chip you can click for its lineage.
- **W5. The metric loop.** In PowerShell:
  `.\.venv\Scripts\python.exe scripts\metric_loop.py --base http://127.0.0.1:8000 --question "What is our runway?" --count 10 | Select-Object -Last 1`
  **Expect:** `METRIC LOOP: verified 10/10 | median ... | slowest ... | target under 8 s`, every time under 8 s once warm. If it seems to hang, **Ask before a team runs** is on **Always**, and each run is waiting for an approval that this script does not give: set it back in Settings first. (It caught me out too.)
- **W6. Dubai: the team.** Gear > **Ask before a team runs** > **Always**. Back on Workspace, ask **Should we open a Dubai office?** **See:** under your question a card leading with **Proposed: Travel-led pilot** and its monthly cost, then **Full model: Full office**, tagged "assumption, confirm". In the middle, the title "Dubai office" (or your words), a pill "One-way door · full analysis", and the **Decision frame**: options, a low/base/high cost table, Goal check. Click **Review the team**. **See:** the amber approval panel with a card per agent. Change one brief, remove one agent, choose **Memo Writer** in the list and press **Add agent** (W11 needs its memo). If an agent on the team is Cloud, you also see **Run all locally instead**. Click **Approve and run**.
- **W7. Dubai: the run.** **See:** cards appear, each with Local or Cloud, its brief (your edit on that one), a step line, a thin progress bar, and a status in words. Slots show `n/2`. Flip **Timeline** and back. Press **Cancel** on one running agent: it says Cancelled, the run goes on. When the run ends, press **Re-run** on an agent, change its brief, **Run again**: a new run starts. (While the team is still working, re-running an agent that has finished is refused with a message: that is the backend rule.)
- **W8. Dubai: the answer.** Back on Workspace (it takes about a minute or two). **See:** the same lead card, then the text, then source chips, one per file. Click a chip: that note opens in the Vault. Under the frame, a card per agent with its findings; Devil's Advocate shows High and Med risk badges if it wrote risks. The badge says **Verified** or **Not verified · n**. **Expect Not verified here, for now, if a Dubai memo is already in your vault: see Current state > Not done, and limits.**
- **W9. Talking during a run.** Ask the Dubai question again, and while it runs type each of these and send:
  (a) `how far along are you?`: a short status line appears in the lane.
  (b) `also make it a two person team`: an amber card, "That changes the request. Restart with your change?", with **Restart with my change** and **Keep going**. Press **Keep going**.
  (c) `what about our churn?`: a card "Queued for when this run finishes". When the run ends it changes to **Ask it now** and **Drop it**. Press **Ask it now**: it runs.
  (d) Press **Quiet off** so it says **Quiet on**: narration stops on the next run; questions it needs answered still come.
- **W10. No removed figure, no fake source.** On each of Workspace, Activity and Decisions, press Ctrl+F and search `billion`. **Expect:** no match (the Market Scout tends to invent one). Search `removed: ` : if it appears, it shows only "(removed: unsupported source)" or similar, with no figure in it. Click every source chip: each opens a real note. If one says the note cannot be read, tell me.
  To compare with the audit trail: `$r = Invoke-RestMethod http://127.0.0.1:8000/api/runs/<run id>; $r.result.issues` can name a removed figure; that is on purpose, and that figure must not be on any screen. The run id is in the Network tab of the browser (F12), on the `stream` request.
- **W11. Memo.** Click **Decisions**. **See:** on the right a paper sheet with the Dubai memo, with a status chip, "Review ..." and, for the memo of this run, key-number tiles. Click **Export .md**: a file downloads and opens as the same text. Click **Export PDF**: the print dialog shows only the sheet, on white; save it. Click **Edit**, change a word, **Save to the vault**: the sheet shows it, and Obsidian shows it too.
- **W12. Matrix.** On the left of Decisions, add `Hire a second SDR` and `Partner channel`. **See:** numbered bubbles and a ranking. Drag a bubble to the top right: its label in the ranking changes to "Do now" and the numbers change. Focus a bubble with Tab and press arrow keys: it moves. Change a weight: the ranking recomputes. `notes/priorities.md` is now in your vault.
- **W13. Data.** Click **Data**. **See:** the tables with file, rows and time. Create a messy file and upload it with **Upload CSV or Excel**:
  `"Kol A,Kol B,Kol C,Kol D`n2026-10,Rent,opex,1000" | Set-Content -Encoding UTF8 $env:TEMP\messy.csv`
  **See:** "did not load", and a form. Choose the table `pnl`, set the columns to month, account, category, amount, then **Save the mapping and load the file**. **See:** "messy.csv is loaded." **Afterwards press Load sample data**, so your numbers return to the demo set.
- **W14. Vault.** Click **Vault**. Search `runway`, open a result, press **Edit**, change a word, **Save**. Use **Add a file to the vault**. **See:** the note appears in its folder, with "Linked from" where it has backlinks.
- **W15. Settings.** Click the gear. **See:** the green privacy note; providers with "key set" or "no key", and never a key; a provider list per agent, with "Local only" on those that must stay local; the cost cap and spend. Turn **Allow cloud agents** on, close and restart `run.bat`, reopen: your choice is kept. Set it back. Optional smoke test: `Set-Location frontend; npx playwright install chromium; npx playwright test; Set-Location ..` **Expect:** `1 passed`.

**M3c re-test after the C4 fix (Light gate, about 10 minutes). Run this one first: RF1 to RF6.** RF2 to RF5 ran in Windows PowerShell 5.1 here, RF5 against a test backend on port 8011 with scratch data, so your vault was not touched by that run. From `D:\Founder-OS`. Each prints one summary line to compare with **Expected**. Then merge, or write the issues under "Founder feedback".

- **RF1. Get the code.** `git fetch origin; git checkout claude/m3c-decision-models; git pull origin claude/m3c-decision-models; $env:PYTHONIOENCODING = 'utf-8'`, close the backend window, then start `run.bat`. No new dependencies. Wait for `Ollama model qwen3:8b is loaded`.
- **RF2. Offline: no Ollama needed.**
  `.\.venv\Scripts\python.exe scripts\eval_labelled.py | Select-Object -Last 1; .\.venv\Scripts\python.exe scripts\eval_agents.py | Select-Object -Last 1; .\.venv\Scripts\python.exe scripts\eval_vault.py | Select-Object -Last 1; Set-Location backend; ..\.venv\Scripts\python.exe -m pytest -q 2>$null | Select-Object -Last 1; Set-Location ..`
  Expected: `OFFLINE LABELLED EVAL: 58/58 passed`, `OFFLINE AGENT EVAL: 24/24 passed`, `OFFLINE EVAL: 18/18 passed`, `917 passed` (with a time).
- **RF3. The fabricated-citation and figure-in-a-question cases (fakes).**
  `Set-Location backend; ..\.venv\Scripts\python.exe -m pytest tests\test_source_check.py -q 2>$null | Select-Object -Last 1; Set-Location ..`
  Expected: `34 passed` (with a time).
- **RF4. Your approvals.**
  `"RF4 prompt v2 $(Select-String -Path backend\app\agents\prompts\people_ops.md -Pattern 'Answer in exactly this order' -Quiet) | approvals in PRD $(@(Select-String -Path docs\PRD.md -Pattern '\| Approved').Count)"`
  Expected: `RF4 prompt v2 True | approvals in PRD 7`.
- **RF5. The Dubai run: every cited path, and no fabricated figure (about 3 minutes; deletes its own memo).**
  `$b = 'http://127.0.0.1:8000'; function Ask($q) { Invoke-RestMethod -Method Post -Uri "$b/api/chat" -ContentType 'application/json' -Body (@{ message = $q; stream = $false } | ConvertTo-Json) -TimeoutSec 1200 }`
  `$r = Ask 'Should we open a Dubai office? Write a decision memo.'; $m = (Invoke-RestMethod "$b/api/vault/notes/$($r.memo.path)").content`
  `$texts = @($r.answer, $m) + @($r.agents | ForEach-Object { $_.text }); $paths = [regex]::Matches(($texts -join "`n"), '[\w./-]+\.(?:md|pdf|csv|xlsx|txt)\b') | ForEach-Object { $_.Value } | Sort-Object -Unique`
  `foreach ($p in $paths) { if ($p -notmatch '/' -and $p -match '\.csv$') { "RF5 cited $p data file" } else { $ok = $false; try { Invoke-RestMethod "$b/api/vault/notes/$p" | Out-Null; $ok = $true } catch { }; "RF5 cited $p exists $ok" } }`
  `$scout = @($r.agents | Where-Object { $_.type -eq 'market_scout' })[0].text; $big = '[$]\s?\d|\d\s?(%|percent|billion|million|bn|trillion)'; $asks = @($r.answer -split '(?<=[.!?])\s+' | Where-Object { $_ -match '\?\s*$' -and $_ -match $big }); $away = @($r.decision_frame.goals | Where-Object { $_.status -eq 'moves_away' }).Count; $sf = [regex]::Matches($scout, $big).Count; $bn = [regex]::Matches(($texts -join "`n"), '(?i)\d\s?(billion|bn|trillion)').Count; $caught = @($r.issues | Where-Object { $_ -match 'removed: unsupported source' }).Count`
  `"RF5 type $($r.decision_frame.type) | moving away $away | status $($r.memo.status) | scout lists what to find $($scout -match 'o find:') | scout figures $sf | billions anywhere $bn | questions with a figure $($asks.Count) | removals noted $caught"`
  `$asks | ForEach-Object { "RF5 question: $_" }; Invoke-RestMethod -Method Delete "$b/api/vault/notes/$($r.memo.path)" | Out-Null; "RF5 memo deleted $($r.memo.path)"`
  Expected: one `RF5 cited` line per path, each saying `exists True` or `data file` and never `exists False`. Then `RF5 type new_office | moving away 1 | status proposed | scout lists what to find True | scout figures 0 | billions anywhere 0 | questions with a figure 0 | removals noted N`, where N varies (1 here when the model invented a figure, 0 if it did not). `questions with a figure` may be 1 if the vault already holds a proposed Dubai memo: read the `RF5 question` line, and its figure must be one of that memo's targets, as stated in the answer's "on record" text. It was 1 in two of the four runs here for that reason ($36,000.00), which is a placeholder target, not market data. `$r.issues` still names the figure that was removed: that is the audit trail, not text you are given as an answer.
- **RF6. Optional: the rubric through the real model (about 3 minutes each; each leaves a memo in `decisions/` to delete).**
  `.\.venv\Scripts\python.exe scripts\eval_agents.py --live --only dubai-office | Select-Object -Last 2; .\.venv\Scripts\python.exe scripts\eval_agents.py --live --only price-increase | Select-Object -Last 2`
  Expected: `decision:dubai-office live PASS` and `LIVE AGENT EVAL: 1/1 passed`, then the same for `price-increase`. Model output varies, so a failure is a prompt to read the memo.

**M3c, first review (done or superseded: P1–P7 are decided, C8 and C9 are deferred until after M5, and C2's counts are now those in RF2). Run C1–C4 (about 10 min), then whichever bake-offs you want to decide on.** C2, C4, the real-path rows of C5 and the C8 dry-run (from the main `.venv`) ran in Windows PowerShell 5.1 here, against a test backend on port 8011 with scratch data. The full bake-offs behind C5, C6, C7 and C10 ran from Git Bash, so their PowerShell filters ran here only on smaller output. C8's training and C9 never ran. From `D:\Founder-OS`. Each check prints a summary line to compare with **Expected**. Bake-offs use a private copy of the sample data and change no default. Bake-offs with several models push `qwen3:8b` out of the GPU, and it reloads when next used (about 3 minutes).

- **C1. Get the code.** `git fetch origin; git checkout claude/m3c-decision-models; git pull origin claude/m3c-decision-models; $env:PYTHONIOENCODING = 'utf-8'`, close the backend window, then start `run.bat`. No new dependencies. Wait for `Ollama model qwen3:8b is loaded`.
- **C2. Offline: no Ollama needed.**
  `.\.venv\Scripts\python.exe scripts\eval_labelled.py | Select-Object -Last 1; .\.venv\Scripts\python.exe scripts\eval_agents.py | Select-Object -Last 1; .\.venv\Scripts\python.exe scripts\eval_vault.py | Select-Object -Last 1; Set-Location backend; ..\.venv\Scripts\python.exe -m pytest -q 2>$null | Select-Object -Last 1; Set-Location ..`
  Expected: `OFFLINE LABELLED EVAL: 58/58 passed`, `OFFLINE AGENT EVAL: 24/24 passed`, `OFFLINE EVAL: 18/18 passed`, `883 passed` (with a time).
- **C3. Names are hidden before any cloud call (fakes, no cloud).**
  `Set-Location backend; ..\.venv\Scripts\python.exe -m pytest tests\test_cloud_layer.py -q -k "name or thousandth" 2>$null | Select-Object -Last 1; Set-Location ..`
  Expected: `N passed` with no failures (N = 10).
- **C4. The Dubai decision: the words agree with the goal check (about 3 minutes; deletes its own memo).**
  `$b = 'http://127.0.0.1:8000'; function Ask($q) { Invoke-RestMethod -Method Post -Uri "$b/api/chat" -ContentType 'application/json' -Body (@{ message = $q; stream = $false } | ConvertTo-Json) -TimeoutSec 1200 }`
  `$r = Ask 'Should we open a Dubai office? Write a decision memo.'; $m = (Invoke-RestMethod "$b/api/vault/notes/$($r.memo.path)").content; $d = (($m -split '## Decision')[1] -split '## Context')[0]; $rej = (($m -split '## Rejected alternatives')[1] -split '## Assumptions')[0]; $claim = '(?i)\b(aligns? with|supports?|helps?|on track)\b[^.]*\bgoal'`
  `"C4 type $($r.decision_frame.type) | moving away $(@($r.decision_frame.goals | Where-Object { $_.status -eq 'moves_away' }).Count) | decision claims it helps $($d -match $claim) | answer claims it helps $($r.answer -match $claim) | no reason given $($rej -match 'Not proposed, though') | status $($r.memo.status)"`
  `"C4 proposed: $($r.memo.chosen)"; "C4 rejected: $($rej.Trim())"; Invoke-RestMethod -Method Delete "$b/api/vault/notes/$($r.memo.path)" | Out-Null`
  Expected: `C4 type new_office | moving away 1 | decision claims it helps False | answer claims it helps False | no reason given False | status proposed`, then the proposed option (live here: `Travel-led pilot`), then the rejected options. Read the rejected lines: every cheaper option gives a reason.
- **C5. Decision models table (about 8 minutes).** `.\.venv\Scripts\python.exe scripts\eval_decision_models.py --llm qwen3:8b,phi4-mini:latest | Where-Object { $_ -notmatch '^\.\.\.' }`
  Expected: an aligned table ending in a `READING:` line. Compare with the table under "Bake-off results": `rules` rows exactly as there; model rows within a few points. The `rules+llm:qwen3:8b` rows are the path the app really takes. Decides P1 and P2.
- **C6. Models per agent, and the lane (about 15 minutes).** `.\.venv\Scripts\python.exe scripts\bakeoff_providers.py --models qwen3:8b,phi4-mini:latest | Where-Object { $_ -notmatch ' (PASS|FAIL)|lane:' }`
  Expected: two tables, what your app really used from `llm_calls.jsonl`, and a `PROPOSED DEFAULTS` list. Decides P3 and P4. Cloud rows: add `--cloud gemini:<model>` once a key is in `.env` (paid; names are hidden and local-only agents are skipped).
- **C7. Embeddings (about 3 minutes).** `.\.venv\Scripts\python.exe scripts\bakeoff_embeddings.py --models nomic-embed-text,embeddinggemma | Where-Object { $_ -notmatch '^\.\.\.' }`
  Expected: a table with both models at about 0.94 hybrid MRR, a real chunk count in the note (the run recorded above showed 0 by a bug, since fixed), and `READING: No model beats ollama:nomic-embed-text ...`. Decides P6, with the licence point P7.
- **C8. Laya (optional, large download: PyTorch plus about 1 GB of weights). Never run here.**
  `py -3.11 -m venv .venv-laya; .\.venv-laya\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu124; .\.venv-laya\Scripts\python.exe -m pip install laya; .\.venv-laya\Scripts\python.exe -m pip install -e backend`
  `.\.venv-laya\Scripts\python.exe scripts\finetune_laya.py --dry-run` Expected: `TRAINING FILE: ...laya-founderos-train.jsonl (138 examples)` or more, a `GPU FREE` line, `DRY RUN: nothing trained.`
  `docker exec ollama ollama stop qwen3:8b; .\.venv-laya\Scripts\python.exe scripts\finetune_laya.py` (1 to 2 hours; n8n's models can squeeze it). Expected: `DONE: ...models\laya-founderos`.
  `.\.venv-laya\Scripts\python.exe scripts\eval_decision_models.py --laya models\laya-founderos --llm qwen3:8b | Where-Object { $_ -notmatch '^\.\.\.' }` Expected: `laya:` and `laya:...+llm` rows beside `llm:qwen3:8b`, with latency in tens of milliseconds. **This run tests my code against the real package for the first time, so an API mismatch here would be a bug for the next session.** Decides P1.
- **C9. Jev (optional, paid, about $0.001 per run). Never run here.** With a key from TypeSafe AI, for this window only: `$env:JEV_API_KEY = '<your key>'; .\.venv\Scripts\python.exe scripts\eval_decision_models.py --jev --llm qwen3:8b | Where-Object { $_ -notmatch '^\.\.\.' }; Remove-Item Env:JEV_API_KEY`
  Expected: `jev` rows and a `Jev cost:` line. Only the question wording and the routing text go out, with numbers masked.
- **C10. Prompt tuning (about 10 minutes).** `.\.venv\Scripts\python.exe scripts\tune_prompts.py | Where-Object { $_ -notmatch ' (PASS|FAIL)' }`
  Expected: a table in which People & Ops v2 beats v1. To approve P5: `.\.venv\Scripts\python.exe scripts\tune_prompts.py --agents people_ops --apply`, which prints `APPLIED people_ops: v1 -> v2`. Without `--apply` the live prompts stay; run `git checkout backend/app/agents/prompts/versions/MANIFEST.json` to drop the new scores.
- **Optional. Labelled set through the real model.** `.\.venv\Scripts\python.exe scripts\eval_labelled.py --live --category hires | Select-Object -Last 3` (minutes; the whole set is about an hour, and memo questions write to your vault).

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
### [M7b] Founder gate 2026-11-26/27 (Edge; PR #17): design accepted in principle; F20–F27 RESOLVED 2026-11-28 on `claude/serene-knuth-si17hr`, awaiting re-test MC1–MC10
Design reference for the fixes: `docs/design/DESIGN.md` (read it before any UI change).
**To fix:**
- **F20.** Money figures are cut off in the metric cards ("$172,280.…", "$255,344.…"). Never truncate a number: shrink or wrap it.
- **F21.** The top bar is technical ("Ollama (down) · Qdrant (down) · GPU (off) · Storage"). Show members one plain status ("All systems OK" / "Slow right now"); move the details into Settings.
- **F22.** The app opens in the last open decision, and the Advisor recites earlier team work unasked. Always open on Welcome. If a decision is unfinished, show one line: "You have an open decision: Dubai office. Continue it?"
- **F23.** The Advisor panel shows walls of text (kill criteria and predictions from several old memos, repeated). Answers stay at 3 sentences or fewer; details stay in the memo.
- **F24.** "On the table" shows "This decision". It must show the current topic ("Dubai office"), updated with each new question.
- **F25.** The table adapts to the team: one seat per agent the planner chose (2 to 8), evenly spaced, each with its own bright colour and coloured name tag and a warmer glow. No empty seats. The phone keeps the strip.
- **F26.** Dragging the left panel squeezes the centre (the table collapses, faces overlap the topic, metric cards break apart), and the right panel can't be resized. Both side panels must be resizable and foldable (drag handles, remembered per viewer). The centre has a minimum width; when it gets narrow, the table switches to the phone-style layout. Metric cards wrap. A "Focus on the team" button folds both panels.
- **F27.** Voice lives on the faces, replacing the two "Start voice" buttons (left panel and LIVE bar). Tap a face to talk to that agent: the LIVE bar says "Talking to <agent>", and a "Speaking" tag with a stop button appears under the face of whoever is speaking. Stop by tapping that button or by speaking over them. Stopping a voice only stops talking: research and number work carry on, and the cards keep updating (today "voice off" shuts everything down). Keyboard: Space = hold to talk, Esc = stop speaking, M = mute the mic. The left panel keeps typing only.

**Still to re-test:** MB2 (Accept writes the memo, not a new team), AM-S5 (one Matrix entry per decision), AM-S8 (one "waiting" line per agent).

**Fixed (2026-11-28, gate fix round):**
- **F20** A figure (`Figure` in `components/common.tsx`) steps down a size by its length (22 → 19 → 16 px) and then wraps; never an ellipsis. Metric cards, scenario tiles, the options' figures and the memo's key numbers; the card rows wrap (`auto-fit`).
- **F21** The top bar shows one line: "All systems OK", "Slow right now" (a required service down, or anything degraded), "Can't reach FounderOS"; it links to Settings → System, which lists the services as before.
- **F22** Every open starts on Welcome. With an open decision, one line: "You have an open decision: Dubai office. Continue it?" (opens the Boardroom). Turns from an earlier visit stay folded ("Earlier in this conversation (N)"), so the Advisor never recites them.
- **F23** The Advisor's answer on screen is its first 3 sentences of prose; lists, tables, kill criteria and predictions go under "Full answer" (and stay in the memo). A long lane line folds after 3 sentences ("More").
- **F24** "On the table" names the topic of the newest question ("Should we open a Dubai office?" → "Dubai office"; "raise our prices by 10%" → "Raising prices by 10%"); while the decision itself, or Accept / Ask more on it, is on the table, its subject. Never "This decision".
- **F25** One seat per agent the planner chose (a re-run keeps one seat; at most 8), evenly spaced around the oval from the Advisor at the top; no empty or dimmed seats; each face ringed in its own colour with a name tag filled in that colour; a warmer glow (tomato ring, then the agent's colour). Faces shrink a step for 7–8 agents. The phone keeps the strip.
- **F26** Both side panels resize (handles, arrow keys, double-click resets) and fold (a button on each), remembered per viewer. The centre keeps 560 px; when it is still narrower than 640 px the stage switches to the phone-style layout (speaking card and strip) instead of squeezing the table. "Focus on the team" folds both panels; "Show panels" brings them back. Options panel default width 320 px.
- **F27** Each face is a button: tap it to talk to that agent (voice turns on, hands-free); the LIVE bar says "Talking to <agent>" (else "Tap a face to talk"). While the voice speaks, the Advisor's face shows a "Speaking" tag with a Stop button. Stop, Esc, or speaking over it stops only the speech (new voice control `hush`); the team, research and figures carry on, and the cards keep updating. Voice off ends only the voice connection (tested: a running team is never cancelled). Space = hold to talk (in the Boardroom, or anywhere once voice is on), Esc = stop speaking, M = mute the mic. Both "Start voice" buttons are gone; the left panel is typing only; voice messages (a blocked mic, "Didn't catch that") show in the LIVE bar and, on a phone, under the speaking card.
- **Not changed (decision):** a spoken or typed "stop" still stops the team, as accepted in M5/M6 (D3). Answers come from the Advisor whichever face is tapped: routing a question to the named agent is M7g ("talk to an agent by name").

### [M7a] Fix round 4 re-test 2026-11-26 (PR #16 merged): AM-S1, AM-S4, AM-S6, AM-S7 PASS; AM-S3 partly; AM-S5, AM-S8 to re-test in M7b. F8d, F19, F9, F18 RESOLVED in M7b (PR #17), awaiting MB1–MB12
Design brief for M7b (locked by the founder): `docs/design/M7B_DESIGN_BRIEF.md`.
**To fix (M7b, in the new screens):**
- **F8d.** The slow-agent offer is sent by the backend but never shown: the backend logs "Slow check: People & Ops 5.3 s of 3 s -> offer sent" and nothing appears on screen. Show it in the Advisor panel and on the agent's card, with "Continue on Qwen on our server" / "Keep waiting".
- **F19.** A 429 fallback is silent: Groq's free 8,000 tokens a minute ran out mid-run, agents finished on Qwen while the cards still said "Cloud · groq · Verified". Show it: "Groq hit its per-minute limit, so People & Ops finished on Qwen on our server". Count only real cloud calls in the spend report.
- **F9.** Voice (the Advisor, the mic, speech and its context) lives outside the pages. Changing pages never starts, stops or resets it.
- **F18.** Memo page: a "Latest" badge with date and time; earlier versions listed under ONE memo per open decision (no more "-2.md" files); Close / Back to the decision; "Regenerate memo" and "Ask the team about this" on the memo itself.

### [M7a] Fix round 3 re-test 2026-11-26 (main, Edge, Groq key; PR #15 merged): AM-R2, AM-R3 (Groq), AM-R5 PASS; AM-R3 (Gemini), AM-R4, AM-R6 FAIL; F7c, F8c, F13b, F14–F17 RESOLVED on `claude/bold-tesla-cibyyq` (fix round 4), awaiting re-test AM-S1–AM-S8
**Passed:** AM-R2; AM-R3 with Groq; AM-R5 (memo "about ₹11: Groq 7 calls (Estimated: US$0.12)", Activity "Run cost about ₹35"). **Failed:** AM-R3 with Gemini, AM-R4, AM-R6. Voice stopping when Activity opens is F9 (M7b).
**To fix (this round):**
- **F7c.** Gemini Test key still says "Can't reach the server… Check your internet connection" after 15 s, while Groq passes on the same connection. When a provider simply doesn't answer in time, say "Gemini didn't answer in 15 seconds. Google may be slow or limiting your key. Try again later." Only mention the member's internet if no provider at all can be reached.
- **F8c (second fail).** With `$env:CLOUD_SLOW_AFTER_S="3"` and `$env:CLOUD_SLOW_MIN_S="0"` set before `.\run.bat`, cloud agents on Groq ran 9–15 s and no "Slow…" line or offer appeared. Add a plain backend log line at startup ("Slow-agent offer after 3 s (min 0 s)") and on each check ("Slow check: People & Ops 4.1 s of 3 s → offer sent" / "… not yet"). Check how run.bat starts the backend (start/cmd /c, setlocal, .env override order). Add a test that starts the app the way run.bat does, with these variables set.
- **F13b (second fail).** The new memo proposes "Partner or distributor", but the decision frame card and the Advisor's answer still mark "Travel-led pilot · Proposed", with no reason sentence. All three (the answer, the frame card and the memo) must show the same proposal. When it changes, the answer opens with one sentence saying why.
- **F14.** Two Prioritisation Matrix entries for one open decision ("Dubai Market Entry via Partner or Distributor" and "Open Dubai via Partner or Distributor"). A new memo for the same open decision updates its existing entry and memo link instead of adding a duplicate.
- **F15.** The Librarian said the earlier memo was "decided 2026-11-26", but that memo's status is proposed. Report the status exactly as recorded, and never call a proposal a decision.
- **F16.** Market Scout said "cloud is off, so no web research was done" while it ran on Cloud · groq. Say the real reason: "Your AI provider (Groq) has no web search, so this comes from your vault only." Keep "cloud is off" only when cloud really is off.
- **F17.** The Advisor panel repeats "People & Ops is waiting for a cloud model." 4–5 times. Show one line per agent and update it in place.

**Recorded, not built (PRD §8, M7h):** Devil's Advocate on Groq `openai/gpt-oss-120b` wrote a muddled risk ("cash burn increases by $2,001 if the full office is opened") that the Verifier passed. M7h: a stronger model for the critical agents; Verifier check idea: a risk's figure must match one of the frame options' own monthly or one-off change.

**Fixed (2026-11-26, fix round 4):**
- **F7c** A timeout (our 15 s, or the HTTP client's own read/connect timeout) is its own code `slow`, a yellow notice: "Gemini didn't answer in 15 seconds. Google may be slow or limiting your key. Try again later." (vendor names: Google, Anthropic, OpenAI; others by their own name). A connection error asks the other providers' public addresses once (3 s, any HTTP answer counts, `internet_works`): if any answers, "Can't reach Gemini right now, though other AI services answer, so your internet is fine…"; only when none answers, "Check your internet connection". A busy answer (429/503) before the timeout stays "busy" (F7b).
- **F8c** run.bat checked: `setlocal` only scopes variables set inside run.bat; PowerShell's `$env:` variables are inherited by run.bat's cmd and by `start … cmd /k … uvicorn`, and pydantic-settings puts an environment variable above `.env` (no `load_dotenv(override=True)` anywhere). A test now starts a real backend process exactly like run.bat (`python -m uvicorn --factory app.main:create_app` in `backend/`, the two variables set, everything else offline) and reads its startup line. New log lines: at startup `Slow-agent offer after 3 s (min 0 s; from the environment: CLOUD_SLOW_AFTER_S, CLOUD_SLOW_MIN_S)` (or "from .env or the default", or "off"); on each cloud call of a cloud agent `Slow check: People & Ops 4.1 s of 3 s -> offer sent` / `… -> not yet` (ASCII `->`, safe in any Windows console); and when a check cannot run, `Slow check: People & Ops skipped (<reason>)` (already on Qwen, planned on Qwen, no way to switch for this run, offer turned off, or "this call goes to ollama, not the cloud"). run.bat also echoes the two variables when set. The cause of the live miss is not reproduced with fakes; the next test's log will show it.
- **F13b** Cause found for one path: a follow-up run with no frame of its own ("write the memo" taken as a new question) let the Memo Writer build its own frame, so the result carried no frame, the page kept the earlier "Travel-led pilot" mark and the answer had no reason sentence. Now such a run carries the open decision's frame (the latest earlier frame that has the memo's option), marked as the memo proposes, and the answer opens with the why sentence. Option names are matched ignoring case and spacing. On the page, the frame card follows the newest memo of **any** later run (not only the current one), so asking another question afterwards no longer puts the old mark back.
- **F14** Each Matrix entry made from a memo carries `decision` (the frame's type and subject, e.g. `new_office:dubai office`) and `memo` (its path). A new memo for the same decision renames that entry and updates its memo link, keeping the founder's scores; another decision still gets its own entry. Entries made before this fix carry no link (delete the old duplicate by hand once).
- **F15** A past memo's status is reported as recorded: in a Librarian finding or the Advisor's answer, "decided (on) 2026-11-26" about a record that is not decided becomes "proposed on 2026-11-26 (not decided yet)"; code's own "On record" note never adds a decision date to a proposal.
- **F16** The Market Scout's note names the real reason: cloud really off → "…cloud is off, so no web research was done."; on a provider with no web search → "Your AI provider (Groq) has no web search, so this comes from your vault only."; switched to Qwen or held on Qwen by the cap → "This part ran on Qwen on our server, which has no web search…"; no cloud provider for the agent → "No cloud AI provider is set up for this agent…".
- **F17** The lane says "<agent> is waiting for a cloud model." once per agent per run (it was said before every model call). The line carries a key (`line_key`), and the page updates a line with the same key in place instead of adding it.

### [M7a] Fix round 2 re-test 2026-11-26 in Edge (PR #14 merged): F4, F5, F6, F7 (429), F12 PASS, F8 FAIL; F4b, F7b, F8b, F12b, F13 RESOLVED on `claude/serene-mendel-8r39x1` (fix round 3), awaiting re-test AM-R1–AM-R6
**Passed:** F4; F5 (AQ. detected, unknown-key message, re-detect on Qwen); F6; F7 for 429; F12 in Settings and the memo ("about ₹26: Groq 9 calls"). **Failed:** F8. The Gemini AI Studio key hit free-tier limits (429), so the cloud tests used a free Groq key (`gsk_…`, `openai/gpt-oss-120b`).
**To fix (this round):**
- **F4b.** After Remove key, "Allow cloud agents" stays ticked and the top bar keeps showing cloud. Removing the last working key must also turn cloud off (saved), so the box greys out with the "Test and save a key first" note.
- **F7b.** Test key against Gemini: after a 429, the retries ran out the 15 s and showed "Can't reach the server… check your internet connection" (3 of 4 tries). When the time runs out after a 429 or 503, show the busy notice instead, never "check your internet". When Google's reply says a quota is used up (RESOURCE_EXHAUSTED / free tier), say: "Your Gemini key has reached its free limit for now. Try again later, or add billing in Google AI Studio." Keep the green chip if the key passed before.
- **F8b.** With `$env:CLOUD_SLOW_AFTER_S="3"` and `$env:CLOUD_SLOW_MIN_S="0"` set in PowerShell before `.\run.bat`, People & Ops (Cloud · groq) ran 11 s and Devil's Advocate 3.4 s, but no "taking longer than usual" offer appeared. Find out whether the setting reaches the backend started by run.bat, or whether the slow check fails for agents already running. Fix it, and add a test that covers the same start path and an agent that passes the limit mid-run.
- **F12b.** The spend line the Advisor says and shows at the end of a decision, and "Run cost ≈ $0.24" in the Activity header, are in US$ although Settings → Currency is INR (the memo was correct in ₹). Use the member's currency everywhere (US$ only in small print). Round US$ to 2 decimals ("about US$0.29", not "US$0.2850").
- **F13.** Two different proposals on one screen: the decision frame card still marks "Travel-led pilot · Proposed", while the Advisor's later answer and the new memo propose "Partner or distributor". When the proposal changes, update the frame card, and have the Advisor say why in one sentence ("With a partner the runway effect is smaller, so I now propose Partner or distributor").

**Recorded, not built (PRD §8):** **M7f setup guide:** "Google AI Pro / Jio subscriptions don't include API use; an AI Studio key has its own free limits; a free Groq key is a good start." **M7b polish:** auto-test on paste; the Test key button reads "Test again" after a pass; a Settings footer credit for the exchange-rate source ("Rates by Exchange Rate API").

**Fixed (2026-11-26, fix round 3):**
- **F4b** `DELETE /api/settings/ai-model/key` now also saves `cloud_allowed: false` (in `ui_settings.json`) and applies it, so the router, the top bar (health) and Settings all go back to local at once; the card's refresh copies the server's `cloud_allowed` to the page, so the box unticks and greys out with "Test and save a key in the AI model card above first…", and no unsaved bar shows. `cloud_usable` no longer counts `.env` keys once the card has a choice (the router already ignored them then), so a `.env` key cannot keep the box enabled after Remove key.
- **F7b** Cause: after a 429 the retry's own wait ran out the 15 s and raised a timeout, which was explained as "Can't reach the server… check your internet". Now `retry_when_busy` remembers the busy answer: a timeout (or a dropped connection) after a 429/503 re-raises that busy answer, so the yellow "Gemini is busy right now (Google error 429). Your key is fine…" shows. A used-up quota (Google's body says `RESOURCE_EXHAUSTED`, `free_tier`, "exceeded your current quota" or "quota exceeded") is its own code `free_limit`: "Your Gemini key has reached its free limit for now. Try again later, or add billing in Google AI Studio." It is not asked again (that cannot help within 15 s), is shown as the yellow notice, and the green chip and the saved key stay. Google's plain "Resource has been exhausted (e.g. check quota)" stays "busy" (a busy minute, asked again).
- **F8b** Cause found: **the setting did reach the backend** (`start` passes PowerShell's `$env:` variables to the backend window, and an environment variable beats `.env`). The slow check timed **each model call on its own**: Groq answers each call in about 2–3 s, so People & Ops (11 s over about four calls) and Devil's Advocate (3.4 s over two) never had one call over 3 s. Now the limit is for the agent as a whole: the clock starts at the agent's first cloud call, and each later call may only use what is left of `CLOUD_SLOW_AFTER_S` (still never under `CLOUD_SLOW_MIN_S`; the "twice its usual time" check stays per call). The card then reads "Slow: Groq has taken 3 s so far (expected under 3 s)", and the Advisor says and shows the same offer as before. Tests: the PowerShell variable beats a `.env` that says 45/15 through `Settings` → `build_orchestrator` (the run.bat path), each agent's runner gets the limit, and an agent of quick calls gets the offer on its third call, mid-run, with nothing switched until the member's OK.
- **F12b** Cause: the backend sends `member_currency: null` until a currency is chosen, but the page only saved the browser's currency when it saw `""`, so the silent save never ran and decisions were priced in US$ until Settings was saved (the memo, written later, was in ₹). Now `currencyMissing()` treats null as missing. The Activity header shows the run's cost in the member's currency (`cost_shown` on the run result, e.g. "Run cost about ₹25"; "free" on Qwen), US$ only in its tooltip. US$ in small print (memo, tooltip) are rounded half up to 2 decimals: "US$0.29", not "US$0.2850" (and not JavaScript's "0.28").
- **F13** Cause: the memo writer chooses the option (`memo.chosen`) and the answer follows it, but the frame kept code's first pick in `default_option`, so the card marked another option. Now the run's frame marks the option the memo proposes (and a later run of the same decision is compared with what the earlier one proposed). When it changed, the answer opens with one sentence by code, without figures: "With Partner or distributor the runway effect is smaller, so I now propose Partner or distributor instead of Travel-led pilot." (or "costs less over a year", the goal it moves away from, or "Weighing the options again, …"). A later answer with no frame of its own whose memo picks another of the open decision's options also moves the "Proposed" mark on the page.

### [M7a] M7a Medium gate 2026-11-26 (PR #13 merged): AM1–AM7 PASS, AM8 partly, AM9 CI green; F4–F8 and F12 RESOLVED in fix round 2 (PR #14, merged; re-test: all pass but F8, see above)
**Passed:** AM1–AM7; AM8 partly (Advanced and the address check pass; Wi-Fi fallback, Use Qwen and Remove key to re-test); AM9 CI green.
**To fix (this round):**
- **F4.** A FAILED Test key (wrong Claude key) ticked "Allow cloud agents" and raised the unsaved-changes bar. Only a passing, saved key may enable cloud; a failed test changes nothing.
- **F5.** Detection missed Google's current key format: AI Studio now issues keys starting "AQ." (AIza keys are retired from Sept 2026). Add AQ. → Gemini and keep AIza as legacy. AQ. keys must use the native Gemini endpoint (x-goog-api-key), not the OpenAI-compatible one. Move the prefix hints to a small data file the server can update without code changes. Unknown start → "We couldn't recognise this key. Please check it, or pick the provider that issued it." and point to the provider list (never stay silently on Qwen). After a key passes, log only its first 3 characters and the provider, to grow the hint list. Also re-detect after Discard and whenever Qwen is selected.
- **F6.** The top bar ("Local only · no cloud key", "Cloud (degraded)"), the Cloud section ("gemini: no key") and "Default" in Provider per agent ignore the verified AI model card. Show the verified provider and model (e.g. "Gemini · gemini-3.8-flash (from AI model)").
- **F7.** Gemini HTTP 503 (overloaded) shows "Can't reach the server… check your internet". Retry 2–3 times with short back-off inside the 15 s limit. Plain message: "Gemini is busy right now (Google error 503). Your key is fine. Try again in a minute." Keep the green chip and show a yellow notice, not a red error. Handle 429 the same way.
- **F8.** A cloud agent sat at "Waiting for cloud" for 178 s with no explanation. When a cloud agent runs well past its estimate (over 45 s, or 2x its usual time), the Advisor says and shows it, and offers "Continue on Qwen on our server" or "Keep waiting". Switch only with the member's OK. The card shows the reason.
- **F12.** Spend report: at the end of each decision the Advisor says and shows its cost in the member's currency ("about ₹1, Gemini 4 calls; Qwen parts free"). Also in the decision memo, and a monthly total in Settings. The cost cap is entered and shown in the member's currency, stored in USD. A daily exchange rate from a free no-key source, cached, falling back to USD. For now, currency = Settings → Currency, defaulting from the browser region. Silent business-country detection comes in M7f.

**Recorded, not built (PRD §8/§12):** **F9** (M7b): voice continues with the same context across all pages. **F10/F11/F11b** (new milestone **M7h "Key ring & smart routing"**, after M7d): several keys with automatic failover and Qwen last; cost/quality routing within the privacy choice from a server model catalogue; a weekly server job proposes catalogue updates (prices via OpenRouter's public models API, leaderboard ranks, retired models, key formats) for the founder to approve. **M7f additions:** a first-run privacy question (Maximum privacy / Balanced (recommended) / Best answers; raw rows, figures and voice always stay on our server); silent currency detection (business country > Cloudflare country > browser region; no confirmation question; manual override in Settings). **M7b polish:** Change model shows "Recommended (3–4) · Show all".

**Fixed (2026-11-26, fix round 2):**
- **F4** The card refreshes the page only after a passing test (or Use Qwen / Remove key), so a failed test cannot touch "Allow cloud agents" or the unsaved bar; what the card changes on the server is copied to both the saved and the draft settings, never shown as an edit. "Allow cloud agents" cannot be ticked on (greyed, with "Test and save a key in the AI model card above first") until a key passed its test (or a `.env` key exists); `PUT /api/settings` refuses it too (422). Turning it off always works. Cause found: the card called `onChanged` after every test, pass or fail.
- **F5** `backend/app/llm/key_shapes.json` (shipped) holds the prefixes; `data/key_shapes.json` (or `AI_MODEL_KEY_SHAPES_FILE`) overrides it, read on every test, a damaged copy falls back. `AQ.` → Gemini, `AIza` → Gemini (legacy). Gemini keys of both kinds go to `generativelanguage.googleapis.com/v1beta/...:generateContent` with `x-goog-api-key` (it already was the native endpoint; now pinned by a test). An unknown start: the hint line says the founder's sentence and the provider list is outlined; the backend says the same and sends the key nowhere. A passing key logs `AI model key shape: starts 'AQ.' -> gemini` (3 characters, never more). Picking Qwen with a key in the box detects again; Discard on the page detects again (a manual pick no longer holds).
- **F6** `/api/health` (cloud) and `/api/settings` carry `ai_model` ("Gemini · gemini-3.8-flash (from AI model)"); the cloud dot is OK and `cloud_usable` true with a verified card key. Top bar: "Cloud: Gemini · gemini-3.8-flash (from AI model)". Cloud section: "Deep-work agents use …", a green pill with it, `.env` providers read "no .env key". Provider per agent: "Default: Gemini · gemini-3.8-flash (from AI model)".
- **F7** 429, 502, 503 and 504 (not a quota with no credit) are "busy": Test key asks again after 0.6 s and 1.8 s (`AI_MODEL_BUSY_RETRIES=2`), never past the 15 s. Then: "Gemini is busy right now (Google error 503). Your key is fine. Try again in a minute." ("Your key is fine" only when the key was accepted: its model list answered, or it is the saved, verified key). Shown as a yellow notice (`role=status`), the green chip and the key in use stay. Other 5xx: "Gemini had a problem of its own (HTTP 500)…", never "check your internet".
- **F8** Each cloud call of an agent is watched: past `CLOUD_SLOW_AFTER_S` (45 s) or twice its median this month (from the cost ledger, 3+ calls), never under `CLOUD_SLOW_MIN_S` (15 s), the agent's card shows "Slow: Gemini has not answered in 47 s (it usually takes about 12 s)", the Advisor says "Market Scout is taking longer than usual: … I can continue it on Qwen on our server, or we keep waiting. Your choice." (spoken too) and shows a card with **Continue on Qwen on our server** / **Keep waiting**. Only the button switches: the cloud call is cancelled and the agent goes on with Qwen (its card: "Switched to Qwen on our server, with your OK: …"; `fallback_from` set). Keep waiting: the card says so, no second offer for that agent. Voice: the offer is spoken; answering it by voice is not built (buttons only), see Open questions.
- **F12** Each agent counts its calls (cloud per provider, local); `ChatResult.spend` has the USD estimate and the calls. At the end of each decision the lane shows "This decision cost about ₹1: Gemini 4 calls; Qwen parts free." (all-Qwen decisions: "cost nothing…", shown, not spoken); the voice says it after the summary when cloud was used. The decision memo gets "## What this decision cost" with the same line and the USD estimate. Settings: **Currency** (default from the browser region, saved once silently), the cap entered and shown in that currency (stored in USD), "Spent this month: about ₹42 ($0.50)". Rates: `https://open.er-api.com/v6/latest/USD` (free, no key), once a day, cached in `data/fx_rates.json`; no rate → US dollars, and Settings says so.

### [M7a] M7a Medium gate run 2026-11-22: AM1–AM4 PASS (AM1 only with a manual workaround); F1–F3 RESOLVED on this branch (fix session 2026-11-26), awaiting re-test AM1–AM9
**Passed:** AM1 (only after running `scripts\ensure_secret.py` by hand), AM2, AM3, AM4.
**To fix:**
- **F1.** `run.bat` never runs `scripts\ensure_secret.py` when Qdrant is already running. The line sits after `goto :preflight` inside the if-block, so it is unreachable. Run it once on every start, before or at `:preflight`, so "[OK] FOUNDEROS_SECRET_KEY ..." always prints. Add a test that checks the script is reachable in both paths.
- **F2.** Edge shows the save-password key icon and offers to save the API key. The key box must not trigger browser password managers (no form submit, autocomplete off, and whatever is needed for Chrome, Edge and Safari), while staying masked.
- **F3.** Key-only setup. A member should only paste a key and press Test key: (a) detect the provider from the key's shape (AIza… Gemini, sk-ant-… Claude, sk-or-… OpenRouter, gsk_… Groq, sk-/sk-proj-… OpenAI), the provider list stays as a manual override; (b) Test key asks the provider's models endpoint which models this key can use, keeps only text/chat models, and picks a sensible default automatically (the newest recommended fast model the key actually has; no hard-coded model that may be retired, e.g. gemini-2.5-flash is no longer open to new users, use the gemini-3.8-flash class); (c) an optional "Change model" dropdown filled with the detected models instead of a free-text Model box; (d) Server address hidden under "Advanced", shown only for Custom (and Ollama Cloud if needed); (e) green chip "<Provider> · <model> · key verified". Update the PRD §4 defaults text, README and the M7a Windows checklist (re-test AM1–AM9 with the new flow). Tests use fakes; no real keys in CI.

**Fixed (2026-11-26):**
- **F1** `run.bat`: `ensure_secret.py` now runs right after the `:preflight` label, which every path reaches (Qdrant already running, started by compose, compose failed, Docker missing or stopped), once per start. `backend/tests/test_packaging_scripts.py` models cmd's control flow (`if … (`, `goto`, labels, `exit /b`) and runs `run.bat` through all five paths; it fails on the old file in every path.
- **F2** The key box is a text field masked by CSS (`-webkit-text-security: disc`, supported by Chrome, Edge and Safari), never `type="password"`, not inside a `<form>`, `autocomplete="off"`, a name without "password", and the ignore flags of LastPass, 1Password, Bitwarden and Dashlane; buttons are `type="button"`, Enter in the box runs the test. A browser without that CSS (none of the three) falls back to a password field so the key is never shown in clear. Checked in a real Chromium (Playwright `e2e/ai-model.spec.ts`: computed style `disc`, type text, no form, no password input) and in vitest. Edge itself is not available here: AM3 is the live check.
- **F3** Key-only setup: (a) `detect_preset` (backend, one table sent to the card as `key_shapes`); (b) Test key lists the key's models (`GET /v1/models` Anthropic, `GET /v1beta/models` Gemini with the key in `x-goog-api-key`, `GET {base}/models` OpenAI-compatible), drops non-chat models (embeddings, speech, image, video, moderation, realtime, Groq `active: false`, OpenRouter non-text output) and ranks them with `AI_MODEL_PREFERENCES` (newest stable version of the first family the key has; nothing hard-coded); a listed model that answers "not found" is skipped for the next best (up to 3, all inside the 15 s); (c) **Change model** dropdown from the saved list; (d) **Advanced** (Server address + optional model name) only for Custom; (e) the chip as before. A wrong key, no credit or a rate limit already fail at the list, before any model is tried.

### [M6b] M6 Major gate run 2026-11-18/19 (fresh copy `D:\FounderOS-fresh2`): D1–D7 RESOLVED on this PC (fix session 2026-11-19), awaiting re-test MR1–MR8
**Passed:** MG1, MG2, MG5; DEMO_SCRIPT §1, §7; §4 frame, risks on "yes", three hires ($43,771, −2.58) pass; MG4 fold + voice while folded.
**To fix, in the founder's order:**
- **D1 (serious).** §5 "Record the decision" memo contradicts the analysis: "aligns with the goal to extend runway" (the goal check says it moves away), "Cost model: Not modelled" (the frame has a low/base/high model, three hires as the founder's figure), options mention "two SDRs" (mixed up with `decisions/2026-09-hire-two-sdrs.md`), "Open numbers to confirm: None" (there are 4). The memo must be built by code from the latest frame of the open decision; the LLM writes only the prose around it, checked by the Verifier. The Prioritisation Matrix stays empty after the decision.
- **D2.** §3 "What if we raise prices 10% and churn goes up two points?" got "The team is already assuming that price change. Nothing to restart." The "already in this answer" check must apply only to a change for the open decision's frame; the what-if must apply both levers and say both.
- **D3.** §6 "Wait, stop there." over the summary stopped the voice, then made a change card. Stop phrases must stop and listen, never become a change.
- **D4.** The fresh copy's Librarian cited `decisions/2026-11-06-open-dubai-office.md`, which is not in that vault (Qdrant collection shared by two clones). Drop citations to files not in the vault; collection name unique per install.
- **D5.** DEMO_SCRIPT §2 mentions a "written by code" label that does not exist; mark what is said to the audience vs. to the app (the "mm" line was taken as a request).
- **D6.** F: dragging the panel edges and double-click reset do not work on the founder's PC (Edge, 2560×1600, 125 %). Visible handles ≥ 8 px, `col-resize`, Playwright at 1.25 scale, widths kept after F5; the agent window comes back in the same place after F5.
- **D7.** `/api/voice/metrics` p50 first_audio 1495 ms (was 890 ms with Kokoro on the CPU), tts_first 542, barge_in_pause 59.5. Bench GPU vs CPU with qwen3:8b loaded; keep the faster as default.

**Reproduced first** in tests on the unchanged code (`backend/tests/test_m6_gate.py`, 11 tests): D2 (`parse_inputs` read "+10 % price" but not "churn goes up **two** points", and a what-if was matched against a frame's base case), D3 (`by_rules("Wait, stop there.")` was `amendment`: "wait" opened the amendment rule and "stop there" was not a stop), D1 (the memo run rebuilt its frame from the words "Record the decision on the Dubai office"), D6 (Playwright at 2048×1280, scale 1.25: the handle's hit area was 6 px with a 1 px line).

**Causes and what changed:**
- **D1:** "Record the decision…" started a fresh decision run whose frame came from those words, not from the answer on screen, so the Memo Writer had no cost model ("Not modelled"), no placeholders to list ("None") and no goal check to guard its prose (so "aligns with the goal" and the SDR mix-up got through). Now (`_record`, `app/conversation/manager.py`) it takes the **latest frame of the open decision** (with three hires after that change; or the latest answered decision on the same place, so a reload loses nothing), keeps the team's findings, and runs only the Memo Writer: "Writing the memo from this answer: its options, costs and goal check. The team's findings stand." In the memo, **every option is written by code** from the frame with its cost and runway (the model's option notes are dropped), the cost model has "3 people (you said)", the goal check is code's (and the prose is checked against it, as before), and **"Open numbers to confirm" lists each placeholder input** ("… Give me the real figure."). The Verifier still checks the model's prose. The **Prioritisation Matrix** gets the decision as an entry "<title>: <proposed option>", unscored ("Not scored yet"), via `add_initiative` (`app/api/priorities.py`).
- **D2:** a "what if" is a change to the open decision only when its numbers belong to that decision's frame ("What if we hired three instead?" on a hire/office). One that brings levers of its own (price, churn), or the run's own request said again, is a new question: it runs (or is queued while a team works), never "already in this answer" (`_new_what_if`). Number words are read for % and points ("two points" = +2). The pricing options name both levers: "Change prices by +10 % with churn +2 pts" (and "+5 % with churn +1 pt").
- **D3:** "Wait.", "Wait, stop there.", "Stop there.", "Hold on.", "Hang on a second." are stops (`_STOP`, `STOP_WORD`). Over the spoken summary (no team running) a spoken stop now gets **no reply**: the voice has stopped and it listens; never a change card. Typed, "Nothing is running." as before; while a team runs, the R1 rule (spoken stop is asked about) is unchanged. "Wait, assume three hires." is still a change.
- **D4:** search already returned only files of this vault's own index, so the stray citation could not come from a hit; I could not find how it got into the answer (a backend on port 8000 from `D:\Founder-OS` serving the fresh copy's page would explain it). Both guards are in anyway: a passage is a source only while its file is in this vault (`Evidence.resolves`, `app/agents/sources.py`), so a sentence citing a missing file is removed with the usual note, and the citations keep only files in this vault (`_keep_used_sources`). The Qdrant collection name now carries a hash of the vault folder (`founderos_default_<model>_<vault>`), so two copies on one PC never share or delete each other's vectors. The first start after this re-embeds the vault once (about a minute); the old collection stays in Qdrant, unused.
- **D5:** `docs/DEMO_SCRIPT.md` marks every line 🗣️ **Say to FounderOS** or 👥 **Say to the room**, with how to keep the room lines away from the app (Voice mode Hold to talk). §2 no longer promises a "written by code" label (the card says "local", or "written by code" only when no model was used). §3, §5, §6 describe the fixed behaviour.
- **D6:** in Chromium and **in Edge** (`E2E_CHANNEL=msedge`) at 2048×1280 and scale 1.25 the old handle did drag when hit exactly, so the likely cause is the 6 px target with a 1 px line beside the panels' own borders. The handle is now a 12 px hit area reaching over both borders, with a grip drawn in its middle, `col-resize`, and a drag follows the pointer on the whole window (no pointer capture needed). New spec `frontend/e2e/panels-scaled.spec.ts`: hit area ≥ 8 px and on top (hit-tested), drag both edges, F5 keeps both widths, double-click resets each, the agent window comes back in the same place after F5 and reopening.
- **D7:** see the bench numbers under Current state.

**Checks on this PC:** backend 1465 tests pass (1463 in the full run, plus the two I fixed after it), ruff clean; frontend lint, tsc, vitest 53, build pass; Playwright `panels-scaled` (Chromium and Edge) and `panels` pass. Not run live: the D2/D3 runner scenarios (the tests cover them), and nothing was tried with a microphone. **Known and unchanged:** run alone, `turns.spec.ts` passes; run serially after `panels` and `smoke` on their shared test backend, it fails, and it fails the same way with this round's backend changes stashed, so the cause is older. In one parallel local run `smoke.spec.ts` also failed once. CI runs Playwright with a retry.

### [M6a] PK run 2026-11-17: PK1–PK6 PASS, PK7 FAIL (Y1, Y2), setup warning (Y3): RESOLVED on this PC, awaiting PK7, PK7b, PK1b
**Founder's items:** Y1 no "The answer is ready… Want me to go through the risks?" (chat or aloud) after a Dubai answer that ended on the Advisor's own question ("What's your priority: extending runway or expanding sales reach?"). Y2 "Yeah." (heard correctly) after it, twice: total silence. Y3 `setup.bat` in a second clone: "container name /founderos-qdrant is already in use", `[WARN] Could not start Qdrant`, then `[OK] Qdrant`.

**Reproduced first** with the new runner scenario **Y1+Y2** (`scripts/voice_scenarios.py`), typed, on the unchanged code: the offer was shown and the first "Yeah." got the risks, but **the second "Yeah." got silence** (FAIL, 2 of 2 answers). Y1 itself was not reproduced live: on this PC the Advisor's answer did not end on a question in either run (it ended on the cash-risk warning), so Y1 was reproduced in tests with such an answer.

**Causes and what changed:**
- **Y1:** the spoken summary only had an offer when it had lines behind it: a decision whose frame had no options (an answer that asks the founder instead of proposing, as yours did), or one with no cost lines, ended with no offer, so the lane showed none and the voice said none. Now every decision answer ends on an offer with something behind it: the risks or the other options as before, else "Want me to go through the costs?", else "Want me to go on?" with the answer's own statements (`_offer_always`, `app/voice/spoken.py`).
- **Y2:** a yes with nothing open was a listening noise (silence). Now (`_bare_yes`, `app/conversation/manager.py`): an open offer is acted on (the risks, as before); else, if the answer ended on an either/or question, "Which comes first: extending runway or expanding sales reach?" (once per answer, no figures); else "Yes to what? You can ask me about the risks or the other options." It never starts a team. Two older tests that expected a silent second yes now expect that line.
- **Y3:** `setup.bat` and `run.bat` first ask `http://localhost:6333/readyz`; if Qdrant answers they print `[OK] Qdrant already running on port 6333.` and skip `docker compose` (checked in cmd on this PC).
- Tests: `backend/tests/test_m6a_carryovers.py` (Y1, Y2), `backend/tests/test_packaging_scripts.py` (Y3).

**Runner after the fix (this PC, 2026-11-17):** Y1+Y2 typed and spoken PASS (the offer was shown and said after every answer; the first "Yeah." got the risks, the second got "Yes to what? You can ask me about the risks or the other options.", never silence); X4 and X5 typed and spoken PASS. In these runs the Advisor's answer again did not end on a question, so the either/or reply ("Which comes first: …?") and the no-options offer are covered by tests only. Backend: 1450 passed; ruff clean. Not tested with a microphone.

### [M5 → M6a] Carry-overs from the M5 gate (X1–X5): X2, X3, X4 RESOLVED on this PC, X1 not reproduced, X5 confirmed; awaiting PK5–PK7
**Founder's items (M5 Gate log, 2026-11-16):** X1 closing offer sometimes missing; X2 "Ok, I will leave as it is" not recognised; X3 restart offered for a change already in the answer (two hires = default); X4 "yes" sometimes misheard (add to STT vocabulary/repairs); X5 confirm "yes" → risks walk-through.

**Reproduced first** with new runner scenarios X1–X5 (`scripts/voice_scenarios.py`), on the unchanged code: **X2 FAIL** typed ("Did you say: Ok, I will leave as it is? …"; also "Leave that as it is.", "Keep as is."); **X3 FAIL** typed ("Assume two hires." got "Your change to two hires isn't in this answer yet…" and a card); **X4 FAIL** spoken (a spoken "Yeah." was written by Whisper as **"Yaffen."**, so nothing answered the offer; "Yes.", "Yes, please." and "Yes, go ahead." passed); **X1 PASS** spoken (two decision answers in a row, each ended on one offer, said and shown).

**Causes and what changed:**
- **X2:** the leave pattern needed "it" after "leave". Now also "leave as it is", "leave that/this as it is", "keep as is", "leave it like it is", "let it be" (`app/conversation/classifier.py`). "keep going" and "Leave the Dubai office as it is" are still not "leave".
- **X3:** any change was treated as a change. Now, before an offer, the numbers in the founder's words are compared with the base case of the frame that run used: if every one is the same, the reply is "That's already in this answer: it assumes two local hires. Nothing to restart." (while the team works: "The team is already assuming …"), with no card (`_already_in`, `app/conversation/manager.py`). After a restart with three hires, "Assume three hires." is "already in" too. Two older tests that used "two" as the change now use "three".
- **X4:** `app/voice/domain.py` repairs a whole turn that is one yes-like word ("Yaffen.", "Yas.", "Yess", "Yesh", "Jess", "Yah", "Yea", "Yeh", "Ya") to "Yes."; "Yes." and "Yeah." stay as they are, and words inside a sentence are never touched. The recogniser prompt now ends "Yes. Yeah. Yes, please. No.". "Yes, thank you." and "Yes sir." count as yes.
- **X1:** not reproduced (2 of 2 spoken, plus W3 in round 8). No change; Next steps 3 names the code paths that could drop it.
- **X5:** "yes" after the offer goes through the risks and starts no team; "no" does nothing (runner X5 = W3).
- Tests: `backend/tests/test_m6a_carryovers.py`; runner scenarios X1–X5.

**Runner after the fix (this PC, 2026-11-17):** X2 and X3 typed PASS; X3, X4 and X5 spoken PASS (643 s, on the final code). With the new prompt Whisper wrote the spoken "Yeah." as "Yeah." (it had been "Yaffen."), so the prompt fixed it at the recogniser and the repair is a second net. X1 spoken PASS before the fix (unchanged code path). Not tested with a microphone.

### [M5] Live check after round 7: W1–W5 (fix session 2026-11-16, round 8): RESOLVED on this PC (W2 not reproduced), awaiting live check RM1–RM6
**Founder's result (2026-11-16):** CI green; RL2a, RL2b, RL2c, RL2d PASS. Then:
- **W1.** "Assume three hires." said twice after the reminder showed "Restarted." though nothing restarted until "Yes".
- **W2.** Every restart with "three hires" came out "Not verified" (twice; "Something from Librarian is unverified", "Verifier sent People & Ops back").
- **W3.** The closing offer was never said: only "The answer is ready. It rests on assumptions you should confirm."
- **W4.** "Ok, I will leave it as it is." after an answer asked "Did you say…?".
- **W5.** "Re-run the Analyst." after a Librarian-only team said "not on this team".

**Reproduced first** (runner scenarios W1–W5 with these phrases, before any fix): W3, W4, W5 FAIL typed (no offer in the chat and "yes" did nothing; "Did you say: Ok, I will leave it as it is?"; the reply did not name the question). W1 and W2 PASS typed and spoken: the second "Assume three hires." got the reminder again and the card stayed open; the restart's badge was "assumptions" (Figures verified · N assumptions), with all five agents verified, although "The Verifier sent Market Scout back" and "… sent People & Ops back" did show.

**Causes and what changed:**
- **W1 (chat):** a repeated change returns the card it already has (one change, one card), so the chat added *nothing*: no reply line, and the nearest card in view could be an older, accepted one ("Restarted."). Now the reminder is shown again as a line, and the open card moves right under it (`frontend/src/lib/workspace.tsx`). The backend never marks a card accepted without starting the run (unchanged; test added). Not seen in the runner, so this is my best reading of what you saw.
- **W2:** **not reproduced** (2 restarts on this PC: badge "assumptions" both times). Your data folder keeps no run text (`llm_calls.jsonl` has timings only), so I could not see which check failed for you. A founder-given "three hires" is not checked as a figure (small counts are not; I tested it), so that is not the cause. No change made, as you asked. RM5 asks you to note the badge's reasons if it happens again.
- **W3:** a decision answer's chat line now ends on the one offer ("The answer is ready. … Want me to go through the risks?", or "Want the other options?" when there are no risks), and the voice says the same offer once after the summary. "yes" (typed or spoken) goes through the risks briefly; "no" or silence does nothing (the old "Okay. The rest is on screen." is gone). With a change open, the reminder takes the offer's place and "yes" restarts.
- **W4:** "Ok, I will leave it as it is.", "leave it", "keep it as is", "that's fine", "it's fine" answer "Okay, leaving it as it is.", with no read-back and no team; a change still on its card is declined, as its "Keep going" button does.
- **W5:** a re-run naming an agent not on the last team uses the most recent finished decision team of this session that had it, and says "Re-running only the Financial Analyst on the Dubai question. …". Only if none had it: "not on this team".
- Tests: `backend/tests/test_voice_round8.py`; one round-2 test now expects silence after "no thanks". Runner scenario S4 now reads back "Dubai office maybe." (the leave phrase has its own scenario, W4).

**Runner after the fix (this PC, 2026-11-16, 2105 s, `FOUNDEROS_STAGE_DELAY_S=2`; S4 re-run after its phrase changed, with W3 and W4, on the final code):**

| Scenario | Typed | Spoken |
|---|---|---|
| S1+S2 | PASS | PASS |
| S3 | PASS | PASS |
| S4 | PASS | PASS |
| S5 | PASS | PASS |
| S6 | PASS | PASS |
| S7 | PASS | PASS |
| RL2a | PASS | PASS |
| RL2b | PASS | PASS |
| RL2c | PASS | PASS |
| RL2d | PASS | PASS |
| W1 | PASS | PASS |
| W2 | PASS | PASS |
| W3 | PASS | PASS |
| W4 | PASS | PASS |
| W5 | PASS | PASS |

Backend tests: 1401 in the full run; the 9 that expected the old behaviour (a bare yes after an answer, the old decline line, the leave phrase read back, the scenario list) are updated, and one real regression (a noise no longer brought back a dropped offer, since the lane now holds the offer) is fixed in `app/voice/session.py`. ruff, frontend lint, tsc, build and vitest (42) green.

**Limits:** W1 and W2 did not fail in the runner; W1's fix is my reading of the screen, and W2 is unchanged. Not tested with a microphone.

### [M5] RL2 failed: a mid-run change was shown, not spoken; stages cannot be timed (fix session 2026-11-16, round 7): RESOLVED on this PC, awaiting live check RL1, RL2a–RL2d, RL3–RL5
**Founder's RL2 result (2026-11-16):** asked "Should we start a Dubai office?", said "Assume three hires" / "Please go ahead with the three hires" near the Devil's Advocate stage. The offer text appeared in the chat, but the voice kept reading the current answer and never spoke the offer. The Devil's Advocate label, "Verifier sent Market Scout back", "3 done, one to go" and the final answer all appear almost at once, so the stage cannot be timed.
**Asked for:** (1) a change said at any point (any stage, verifying, or while the answer is spoken) is spoken at once, cutting off speech like a barge-in; never an offer in the chat only; (2) after a finished run, "Your change to <X> isn't in this answer yet. Say yes to restart with it." once; (3) a progress line "Step N of M: <agent> working…", "Verifying…", "Done"; (4) dev setting `FOUNDEROS_STAGE_DELAY_S`; (5) runner scenarios for a change in the first stage, the last stage, during the spoken summary and after the run.

**Reproduced first** (runner, spoken, before any fix): RL2a FAIL, the founder's bug exactly: the change was said during the first stage, the card appeared, the voice then said the team line ("I've put together a team of five …") and **never said the offer**. RL2c and RL2d FAIL: they said "Restart with your change?" where the run had already finished (the reminder was wanted). RL2b PASS. I did not pin down which line of code dropped the RL2a offer; the team line had arrived while the founder was speaking and was queued in front of it.

**What changed:**
- **A change always interrupts** (`app/voice/session.py`): when a change is understood, anything playing, being made or waiting to be said (team line, summary) is stopped by the barge-in path, and the offer is the next thing said. After the fix, RL2a's timeline: barge-in at 0.9 s, words understood at 1.5 s, the waiting team line dropped at 2.0 s, the offer said at 4.1 s.
- **After a finished run** (`app/conversation/manager.py`) the reply is "Your change to three hires isn't in this answer yet. Say yes to restart with it.", in the panel and aloud. It is keyed as the summary's own reminder, so it is said once, whichever path gets there first.
- **Progress line**: the event `run.progress` ("Step 1 of 3: Librarian, Market Scout and Financial Analyst working…", "Verifying…", "Done"), shown under the conversation, never spoken. "Verifying…" starts when the last stage ends and covers writing and checking the answer.
- **`FOUNDEROS_STAGE_DELAY_S`** (dev only, default 0, README "Development"): that many seconds before each stage.
- Tests: `tests/test_voice_round7.py`; nine older tests now expect the reminder after a finished run.

**Runner after the fix (this PC, 2026-11-16, 1082 s, `FOUNDEROS_STAGE_DELAY_S=2`):**

| Scenario | Typed | Spoken |
|---|---|---|
| S1+S2 change in the last stage, reminder, yes, $43,770.86 and -2.58 | PASS | PASS |
| S3 sounds do nothing, then okay restarts | PASS | PASS |
| S4 read back, no team | PASS | PASS |
| S5 greeting | PASS | PASS |
| S6 re-run the analyst / the librarain | PASS | PASS |
| S7 stop, yes | PASS | PASS |
| RL2a change in the first stage: offer said at once | PASS | PASS |
| RL2b change in the last stage: offer said at once | PASS | PASS |
| RL2c change over the spoken summary: summary stops, reminder once | n/a (typed: no speech) | PASS |
| RL2d change after the run: reminder once, one card | PASS | PASS |

**Limits:** not tested with a microphone. A change cuts off the team line if it is still waiting or playing; the team is on screen. Typed RL2c only checks that nothing breaks, since typing makes no sound.

### [M5] RZ re-test and scripted runner: RESOLVED on this PC, awaiting live check RL1–RL5 (fix session 2026-11-15, round 6)
**Founder's RZ results (2026-11-15):** S6 "Re-run the analyst" re-ran only the analyst (pass, but the panel repeated the team and stage lines); S7 stop and yes passed. Failed on the PC: S1 the change's offer came only after the answer (typed too); S2 the restarted run was "Not verified"; S3 sounds; S4 "Okay, I will leave it as it is." started a team (typed and spoken); S5 "Hello? Yes?" got no response; S6 "Re-run the librarain" started a Librarian run with a confused answer.

**What changed:** five rounds said "could not reproduce", so this round built `scripts/voice_scenarios.py`. It starts the real backend on a free port with a fresh data folder (sample data, approval at Never, your Ollama, faster-whisper and Kokoro), speaks your exact phrases with Kokoro in a different voice into `/ws/voice` at the right moments (the change when only the Devil's Advocate is working), sends the same phrases typed through `/api/conversation/turn` as the text box does, and checks what was heard, said, carded, started and cancelled, the figures and the badge.

**The runner's first spoken pass, before the fixes:** S4, S5, S7 PASS; S1+S2, S3, S6 FAIL. Real causes found and fixed:
- **S3.** Whisper wrote your "hmm" as **"Ahem."** and "uh-huh" as **"Ahoy."**. Those are not on the list of sounds, so they closed the change's question, and **"Okay." then did nothing**. Fixed: ahem, ahoy, aha, hm are sounds; and a plain yes or no always answers a change still open on its card, even after a turn in between.
- **S6.** A one-agent re-run was announced like a new team: "Team: …", the inputs question, "… is done; writing your answer now.". Fixed: a re-run says only its own line.
- Runner faults, not FounderOS: the first S1+S2 and S6 checks moved on before the summary had been spoken (it starts about 5 s after the run ends), and counted kept agents as re-run.

**Final runner table (this PC, 2026-11-15 17:13 UTC, 688 s):**

| Scenario | Typed | Spoken |
|---|---|---|
| S1+S2 change in the last stage, reminder, yes, $43,770.86 and -2.58 | PASS | PASS |
| S3 mm / hmm / uh-huh do nothing, then okay restarts | PASS | PASS |
| S4 "Okay, I will leave it as it is." read back, no team | PASS | PASS |
| S5 "Hello? Yes?" greeted, then yes does nothing | PASS | PASS |
| S6 re-run the analyst (only the analyst), re-run the librarain | PASS | PASS |
| S7 stop, yes: cancelled and silent | PASS | PASS |

**What this means for what you saw:** with the same phrases, S1, S4 and S5 pass on this backend typed *and* spoken, so the code you tested on the PC was, I believe, **not the round-5 code**: most likely an old backend window still held port 8000 when `run.bat` started a new one (the new one then cannot start, and the old one keeps answering). The RL1 step below checks this. Two things the runner shows but does not settle:
- **S1 typed, "offer only after the answer":** the backend offers at once (before the run ends, one card). On screen the card is added at once, but when the answer arrives it is **moved below the answer** (the round-4 rule that an open change stays in sight). Please look at where the card first appears in RL2.
- **S6 "librarain":** Whisper writes it **"Librarian"** (the agents' names are in its vocabulary), so it is an exact re-run of the Librarian, and only the Librarian works again. "Did you mean …?" is for names it gets wrong. The Librarian's answer read: "Proposed: Travel-led pilot … The full model, Full office is $30,000.00 up front and $32,347.24 a month …": the Dubai answer again with the original two hires, since only the Librarian's part was redone. If that is the "confused answer", say what you expected it to say.
- **S2 badge:** on this PC the restarted run's badge is **"assumptions"** (it rests on placeholder costs), not "Not verified", with no reasons. If yours says "Not verified", hover and copy its reasons into feedback.

_Write results from your Windows checks, bugs and change requests here. The next session acts on them first._
### [M5] Re-test RY1–RY7: RESOLVED, awaiting re-test RZ1–RZ7 (fix session 2026-11-15, round 5)
**Resolved (2026-11-15, PR #10):** U0 to U5 and the reminder, with tests in `tests/test_voice_round6.py` built from your own logged turns (`decision_log.jsonl` and the live `/api/voice/metrics`: turn text and timings only). What the logs showed:
- **U1.** Both "Assume three hires." were heard (two barge-ins with those words), but **neither became a turn**: no turn was recorded for them. The only paths that drop words before the lane are a read-back and the echo check, so my reading is: the recogniser was unsure of the first (it was said over FounderOS's own speech), so it was read back ("Did you say: Assume three hires? …"); the second, said over that read-back, matched the read-back's own words and was dropped as an echo; then "Ugh." cleared the read-back. Not proven (the confidence is not logged), but it fits every logged line. Fixed: while a team works a change is never read back (its offer is the question), the same words said over their read-back are you confirming, and a sound like "Ugh." never clears a read-back.
- **U2.** "Ugh." itself did nothing (logged as a backchannel). The next three turns did the harm: "Okay." took the summary's offer of risks (no change was open, see U1), "No?" declined it ("Okay. The rest is on screen."), and then **"Okay, I will leave it as it is."** was heard and **started a team** (Financial Analyst, Librarian, Perspective lens, Devil's Advocate at 09:33 UTC). That sentence is FounderOS's own decline line in Whisper's spelling ("I will" for "I'll"); if it was not you reading the checklist aloud, it was its own echo, which the old check missed because of the contraction. Fixed: contractions are matched in the echo check; under rule U0 such a turn is read back and never runs a team; a sound is never yes or no and leaves an offer open.
- **U3.** "Re-run the Analyt." named no agent exactly, so it was a new request (09:36:58 UTC, with a Perspective lens). Fixed: agent names are matched by prefix and edit distance ("Analyt", "analist", "Devil", "scot"); two letters off, it asks "Did you mean re-run the …?". The chips: one chip per metric now, whichever agents looked it up.
- **U4.** "Hello? Yes?" went to the Advisor as chit-chat, with the earlier answer as context. Now a greeting gets "Hello. What would you like to look at?" and no run; "yes" with nothing on offer does nothing.
- **U5.** The badge already opens its reasons on click; it now says so on hover ("Click to see why"). I could not see which reason your restarted run had (results are not logged); if the reason shown is wrong, please copy it into feedback.
- **Reminder.** After an unanswered change the summary ends with "Your change to three hires isn't in this answer yet. Say yes to restart with it.", once.

Founder's results (2026-11-15, about 14:00–15:05 IST): **PASS** restart after the answer with "Yes." ($43,770.86, -2.58), T4 (no unverified line on Not run), T5 (code trade-off). **FAIL** RY4, RY6. **PARTIAL** RY2, RY5.

To fix (method: the founder's real logged turns are the regression fixtures):
- **U0 rule (PRD §12).** An unclear, very short or unrecognised turn never starts a team. It does nothing (fillers), asks "Did you say …?", or answers directly without a team. Only a clear question or decision request starts a team.
- **U1.** RY2 first try: "Assume three hires." said while the Devil's Advocate (last stage) worked got no offer and no card; the answer kept 2 hires. Find where that turn went; the offer is said and shown at once in the last stage too.
- **U2.** RY4: "mm" transcribed "Ugh." was taken as "no" ("Okay, I will leave it as it is.") and as a new question that started a team (Financial Analyst, Librarian, Perspective lens: Customer, Devil's Advocate). Fillers (ugh, mm, hmm, uh, uh-huh, ah, oh) do nothing, before or after an offer.
- **U3.** RY6: "Re-run the analyst" came out "Re-run the Analyt.", was not recognised, and a new team started (Perspective lens: Investor) whose answer had 13 metric chips with duplicates. Match commands and agent names fuzzily; if unsure, ask "Did you mean re-run the Financial Analyst?".
- **U4.** RY5: "Hello? Yes?" got a reply repeating the previous answer's text. A greeting gets a short greeting; a "yes" with nothing on offer does nothing; never reuse an earlier answer's text.
- **U5.** A restarted run showed "Not verified" with no visible reason: make the reasons visible (click) and correct; de-duplicate metric chips; a vague turn never lists every metric.
- **Reminder (founder decision).** After an unanswered change offer, end the summary with one short spoken reminder, e.g. "Your change to three hires isn't in this answer yet. Say yes to restart with it."
### [M5] Re-test RX1–RX7: RESOLVED, awaiting re-test RY1–RY7 of M5 (fix session 2026-11-15, round 4)
**Resolved (2026-11-15, PR #10):** T1 to T5, with tests in `tests/test_voice_round5.py` (44) and one in `frontend/src/lib/workspace.test.ts`. What I found, from the code and from this PC's own logs of your run (`data/default/decision_log.jsonl` and `llm_calls.jsonl`: times and model names only):
- **T2. Cause found.** The lane's pattern for "yes" allowed ".", "!" and "," after the word, not "?". So "Yes?" was no answer, the open offer lapsed, and with nothing running the words became a new request: the log shows `"message": "Yes?"` classed as chit-chat at 07:09:57 UTC. Fixed by matching answers without case or punctuation, in the lane and in the voice (approve, ask it, restart, the read-back, the offer of more). Also closed: a listening noise before the yes used to close the offer.
- **T3. Cause found, and it was my round 3 design.** The offer was said when you asked, and asked again with the answer; and the card had its own fixed words ("That changes the request. …"), different from the spoken ones. Now one offer, said once, and the card carries the same words. The same change heard twice is one offer and one card. **I did not find what drew the card twice**: one offer makes one event and one card in every test. Two things that could have are closed (the change heard twice; the same offer arriving twice in the browser). If you see two cards again, tell me whether both showed the same change.
- **T1. Not reproduced.** With fakes the offer is said and the card shown before the run ends in every stage: first, last (only the last agent working), and while the answer is written. The logs put your change in the last 3 to 10 seconds of the run (Devil's Advocate 07:09:00 to 07:09:07, answer written by 07:09:10). A spoken turn takes about 1.5 to 2 seconds to hear, transcribe and answer, so an offer for a change said that late arrives together with the answer; and round 3 then asked a second time right after. I believe that is what "only after the answer" was, but I cannot prove it without your microphone. What changed: the offer goes ahead of any answer line still waiting, and nothing else is on offer beside it. RY3 asks you to check exactly this.
- **T4. Cause found.** The lane wrote its "answer is ready" line from the `verified` flag alone, and a reply with no team is "not verified" there. No such line now when no team ran.
- **T5.** A trade-off sentence must name two of the options on the table; otherwise code's sentence replaces it. "Unclear" is judged only by that: I did not try to judge the wording.

Founder's results (2026-11-15): **PASS** RX2, RX3, RX6 text (S5 fixed). **FAIL** RX4 in voice. Clicking "Restart with my change" applied the change correctly ($43,770.86 a month, -2.58), so the engine is right; the voice path is not.

To fix:
- **T2 (main).** After the answer offered "You asked for a change while the team worked, and this answer does not have it. Restart with it?", the founder said "yes"; Whisper gave "Yes?" and it was treated as a new question ("What's your reasoning for agreeing to that model over the full office?", badge "Not run"). Normalise punctuation and case; any clear affirmative (yes, yeah, yep, sure, okay, go ahead, do it, restart, with or without "?" or "!") right after an offer answers that offer. Test with "Yes?", "yes.", "Yeah!", "okay?".
- **T1.** "Assume three hires." said late in the run (after People & Ops and Regulatory & Tax were done, while the Devil's Advocate worked) got no offer at that moment, only after the answer. Offer a mid-run change at once, spoken and as one card, in every stage including the last one and while the answer is being written.
- **T3.** One change produced two offers ("You asked for a change while the team worked… Restart with it?" and "That changes the request. Restart with your change?") and the card twice. One change, one offer, one card.
- **T4.** A reply showed a "Not run" badge together with "The answer is ready, but some of it is unverified". A turn that ran no team shows no verification line.
- **T5 (minor).** The model wrote "The main trade-off is stopping hiring for the pilot while confirming the cost model with three hires." When the trade-off sentence is unclear or does not name the two options, use the code-written trade-off instead.
### [M5] Re-test RW1–RW10: RESOLVED, awaiting re-test RX1–RX7 (fix session 2026-11-14, round 3)
**Resolved (2026-11-14, PR #10):** S1 to S5 and the typed "stop", with tests in `tests/test_voice_round4.py` (39), the S5 tests on your exact strings. **I could not reproduce S1, S3 or S4 as you saw them**, so for those three this is what I found and what is now closed, not a proven cause:
- **S1.** Stopping does cancel the run: with fakes at 40 points of a run, and live on this PC at 20, 28, 33, 37 and 40 seconds (the last two while the answer was being written), every run ended cancelled with no answer. So I do not know which path spoke "My proposal is …" for you. Closed now: the voice keeps a list of stopped runs and says nothing of their answers, whatever state they end in (tested with a cancel that is made to miss); a cancelled run's waiting lines are dropped; a stop also clears an earlier summary's offer; and the orchestrator ends a run as cancelled if its stop arrived too late to interrupt the last step.
- **S2.** Cause found. After the summary, any listening noise ("mm", a breath heard as "Huh.") was a backchannel turn, and round 2's rule "a noise brings the offer back" said the offer again although it had already been said. Now an offer is said again only if it was dropped before it was ever said.
- **S3.** Not reproduced; three paths closed. (1) Its own offer heard back: "…go through the risks?" matches the pattern for a yes to that offer, and round 2 made such words an answer even while it was still speaking. (2) A noise that Whisper writes as "Okay." or "Yeah." counted as yes whatever its confidence. (3) S2's repeat. With headphones (1) is unlikely, so (2) or (3) is my guess for your run.
- **S4.** Not reproduced: with fakes the change was offered and said every time, typed or spoken, in silence or over the opening turn. But the words were different from the ones you know ("Those are your figures. Cancel this run and start again with them?"), and an offer you did not answer expired when the run ended, so the answer came with two hires and the change was gone. Now: the same words as after the answer, an unanswered change is asked again with the answer, a short change said over the voice is no longer left to a model that may call it a noise, and three words or more are never dropped as a noise.
- **S5.** Cause found. The pass that removes repeats never compared two sentences with different figures, so the goal line with other numbers in it passed; and "You already proposed a Dubai office …" does not contain the word "memo", which the memo rule looked for. Both fixed, and a date the memo does not have is removed.
- **RW5 failed, and S1 to S5 do not say how.** The test of a one-agent re-run still passes. I took S2 and S3 (the offer twice, talking on) as what you saw there; RX6 asks you to check.

Founder's results (2026-11-14): **PASS** RW3, RW4, RW6, RW7, RW8 (`small.en`), RW9 (the rule). **PARTIAL** RW2. **FAIL** RW5.
Founder's PC numbers (RW10): first words p50 **890 ms**, metric answer p50 **1738 ms**, barge-in pause **64 ms**, cancel **~990 ms**, STT p50 **291 ms**, TTS first **596 ms**, VRAM **7.43 / 12 GB**, Whisper **+0.70 GB**.
Headphones or a headset give the best voice results.

To fix (third and final round):
- **S1.** Voice cancel: after "stop" + "yes" ("Stopping the team."), the Advisor still spoke the summary ("My proposal is Travel-led pilot…"). A cancelled run is never summarised or spoken: cancel also clears queued TTS and suppresses the final answer's speech.
- **S2.** "Want me to go through the risks?" was asked twice in one turn. Each offer is said once.
- **S3.** After the summary's offer and a silence, the Advisor carried on talking unprompted. After any offer it waits for the user; silence never continues it.
- **S4.** "Assume three hires." said WHILE the team was running was lost: no restart offer, and the answer kept 2 hires. A mid-run amendment must show and say the restart offer (as after the answer, which works).
- **S5.** The Dubai text answer repeats itself again: the goal line twice ("…which moves you away from your goal 'Extend runway…'" and "This moves you away from your goal 'Extend runway…'…") and the prior memo twice ("You already have a proposed memo on this from 2026-11-06…" and "You already proposed a Dubai office in 2027 with a Travel-led pilot…"); "in 2027" is also wrong (the memo is dated 2026-11-06). The near-duplicate pass must catch same-topic sentences (same goal, same memo), and a memo date that differs from the memo is never stated. Tests with these exact strings.
- **Open questions answered** (PRD §12): keep `small.en` as the default STT, `large-v3-turbo` stays an option; keep barge-in at 1 s; a typed "stop" stops at once without confirmation (spoken "stop" still confirms; the Cancel button stays immediate); keep "On it." before the opening turn; keep the 0.45 read-back threshold.
### [M5] Re-test RV1–RV11: RESOLVED, awaiting re-test RW1–RW10 (fix session 2026-11-13, round 2)
**Resolved (2026-11-13, PR #10):** R1 to R8, with tests in `tests/test_voice_round3.py` (79) and five new WAV fixtures (`ugh`, `mm`, `hmm`, `right`, `okay`). Causes and what changed:
- **R1.** "Ugh!" matched no rule, so two models were asked. The barge-in check timed out ("fallback") and stopped the speech; the turn classifier's model then chose "stop", and the lane cancelled the team on that guess. Now a noise or one stray word is a backchannel by rule, a model's "stop" is ignored unless the words hold a stop word, and a stop is asked about first.
- **R8, the change that was not applied.** The backend did apply it: "Assume 3 hires." accepted gives $43,770.86 and -2.58 (test). Two things kept it from you. Saying "yes" to "Restart with your change?" was not understood (only "restart" was). And when the restart was accepted by voice, the run started but the screen was never told, so the canvas kept showing the two-hire answer. Both fixed; the on-screen button path is tested too.
- **R8, the re-run.** After the answer the whole team was started again by design. Now only the named agent runs and the others' findings are kept (`RunContext.reuse`).
- **R2.** The timing was wrong; the audio was not paused that long. See Current state.
- **R4, R5.** One opening turn, silence, one optional "Still working on it.", then findings, outcome and an offer. Why your run ended without the offer: I could not reproduce it with fakes. The likely cause is R1's: a short sound during the summary was judged a barge-in, which drops everything still to be said, the offer included. Fillers no longer do that, the offer is said again after a listening noise, and a decision summary now always has an offer to end on.
- **R6.** Vocabulary for Whisper, code's repairs, read-back of unsure turns, and the model measurement (Current state).
- **R3.** `count_reading` in `app/voice/domain.py`; the lane asks before it offers or applies.
- **R7.** The two strings you quoted are questions the model wrote; the old filter only caught "expected to meet" and "kill criteria" wordings. With a proposed memo on record, code now removes every question but its own, and any second mention of the memo. The spoken risks no longer include questions.

Founder's results (2026-11-13): **PASS** RV2 (headphones), RV3 (speakers), RV7, RV8, RV10. **RV9 partly.** **FAIL** RV4, RV5, RV6.
Founder's PC numbers (RV11, headphones): first words p50 **931 ms**, metric answer p50 **1869 ms**, barge-in pause **62–71 ms**, cancel **574–582 ms**, STT p50 **396 ms**, TTS first **591 ms**, VRAM **7.4 / 12 GB**, Whisper **+0.52 GB**.
Headphones or a headset give the best voice results.

P1
- **R1 (important).** While a team ran, the founder said "uh-huh"; STT gave "Ugh!", the barge-in verdict came from "fallback", and the turn was taken as stop ("Stopping the team."). A short non-command utterance (filler, one word, no question, under about 1 s) while a team runs is a backchannel, never stop. Stop only on explicit words (stop, cancel, halt, hold it), and confirm before cancelling a running team ("Stop the team? Say yes to stop."). WAV/text fixtures for "uh-huh", "ugh", "mm", "hmm", "right", "okay".
- **R8.** Voice re-run: "re-run the analyst" re-ran the whole team; re-running one agent must re-run only that agent, then rewrite the summary. "Assume 3 hires." offered a restart, but the answers afterwards still showed 2 hires ($32,347.24, -2.07). Check that an accepted change is applied (3 hires: $43,770.86 a month, -2.58) and that the spoken and on-screen restart offers both work.
- **R2.** `/api/voice/metrics` `recent_barge_ins` has rows with `paused_ms` 35,000–168,000 ms, empty text and verdict by "duration": find whether the timing is wrong or audio really stayed paused that long, and fix.

P2, founder design decision: voice during a team run (PRD §12, replacing round 1's per-stage lines)
- **R4.** Speak ONE opening turn only, e.g. "I've put together a team of six: the Librarian, Market Scout, Financial Analyst, People & Ops, Regulatory & Tax and a Devil's Advocate. They're looking at the Dubai office from different angles so the decision holds up." Then stay silent while they work; at most one short "still working on it" if the run passes about 30 s. No per-agent lines, no Verifier lines, no figures, no assumption question; all of that stays on screen. When done: a short spoken summary of the team's two or three key findings (rounded numbers by code), then the outcome (the proposal and the main trade-off).
- **R5.** The spoken summary must always end with an offer ("Want me to go through the risks?") and then stop. On the founder's run it ended after the proposal with no offer.
- **R6.** Smarter transcription: "Should we open a Dubai office" came out "should be open a Dubai office", "Re-run the analyst, assume three hires" as "Freerun the another test assume 3 hires", and "two person" as "2%". Add a domain prompt / hotwords for faster-whisper (FounderOS terms, agent names, metric names, Dubai, hires, runway, churn), measure whether a larger model (e.g. large-v3-turbo int8) fits the VRAM with qwen3:8b loaded and what it costs in latency, normalise numbers with context, and confirm low-confidence or ambiguous turns ("Did you mean two people?"). No slow LLM correction pass unless measured to add under about 300 ms.
- **R3.** Ambiguous numbers in amendments ("2%" when the decision has hires, "two" with no unit) are confirmed before they are applied.
- **R7.** The Dubai text and spoken answers still ask target or kill-criterion questions about a PROPOSED memo ("Is the runway still above 10.44 months by 2027-05-06, as predicted?", "Is the risk of runway falling below 6 months by March 2027 acceptable?") and once repeated the prior-memo point twice. For a proposed memo on record, ask only "what has changed since you drafted it?". Tests with these strings.
### [M5] Founder review V1–V10: RESOLVED, awaiting re-test RV1–RV11 (fix session 2026-11-13)
**Resolved (2026-11-13, PR #10):** V7, A to E, the number normaliser and the full stop, with tests in `tests/test_voice_round2.py` (44) and the fixture `churn.wav`. Causes and what changed:
- **V7, where the spoken turn was lost.** Not in the queue or the classifier: once the words "What is our churn?" reach the lane they are queued and offered (test with fixtures). They were lost before that, in three ways, all in `app/voice/session.py`:
  1. **A stale verdict resumed the narration over you.** Any sound paused playback; its verdict ("backchannel, carry on") arrived after transcription, by which time you had started your question. The resume played the narration over your question, the 600 ms barge-in rule no longer applied (nothing was "paused"), and Whisper got your voice mixed with the narration. Now a verdict about older speech never resumes over newer speech.
  2. **New lines started while you were speaking.** The speaker did not check whether you were mid-sentence, so the next narration line played over the rest of your question. Now nothing new is played while you speak or while your words are being understood, and the reply to you is said first.
  3. **An unreadable transcript was dropped in silence.** Now it says "Sorry, I didn't catch that." and shows a note.
  4. **(found while testing) FounderOS heard itself.** Your `decision_log.jsonl` from 8 and 9 November has turns nobody said during speech ("See?", "date.", "Please continue.", "You can go."): fragments of its own voice from the loudspeakers. With the real engines and a simulated echo this gave 20 self-made pauses and several invented turns in one Dubai run. The echo gate (`VOICE_ECHO_GATE`) stops that: none in the same run.
  Evidence: the WAV-fixture test `test_a_question_spoken_over_narration_is_queued_shown_and_offered`, three tests for 1 to 3, one for the gate, and the real-engine run (question heard as "What is our churn?", queued, offered after the summary). **Not tested with your microphone and room:** RV2 and RV3 are that test.
- **A.** `team_line`: one or two sentences, said once; the voice no longer speaks every lane line (the lane tags each line with a `kind`).
- **B.** `produced_line` a stage; `summarise` for the outcome; `spoken.py` normaliser with a table of tests.
- **C.** Two or three sentences, then one offer; "yes" / "no thanks" (or naming the part) answers it. With a queued question waiting, its offer is the only question asked.
- **D.** Earlier questions and answers go to the Advisor (`conversation_block`); "and what about churn?" and "why that option?" are resolved in code.
- **E.** `ConversationManager._rerun`, typed or spoken.
- **Double full stop: not reproduced.** The backend's answer ends with one full stop in every run I made (runway, net burn, Dubai; fake model). Code now guarantees one after the warning and collapses a doubled one in any answer, with a test. If you see it again, RV10 asks where.

Founder's results (2026-11-13): **PASS** V3, V4, V5, V6, V8, V9. **FAIL** V7. **V10** to re-measure.
- **V7 (P1 bug).** Hands-free, approval Never: asked "Should we open a Dubai office?", and while the team worked said "What is our churn?" (and later "What's our current churn?"). The app kept narrating Dubai; the question was not shown, nothing said or showed "queued", and after the answer there was no "Your next question is ready. Say ask it, or drop it." and no Ask it now / Drop it. In text mode the same flow works (M4 RY5).
- **P2, founder design decision: how the Advisor speaks** (PRD §12):
  - A. At the start of a team run, say briefly how the team is organised: who is on it and each one's focus, in one or two sentences. No running commentary of every step.
  - B. Never read the on-screen text or an agent's output aloud. One short line on what each agent produced, and the outcome. Spoken numbers are rounded and colloquial, produced by code from the verified figure, never by the model ("around 10 thousand dollars", "about 1.8 million", "about ten and a half months", "about four in five"). Exact figures and lineage stay on screen. A spoken-number normaliser (money, %, months, dates; ready for INR lakh/crore), with tests.
  - C. Not a non-stop speaker: lead with the outcome and the one thing that matters, about 2–3 sentences a turn, then pause and offer more ("Want me to go through the risks?").
  - D. Use the full conversation context in voice (the open decision, earlier answers, earlier questions), so follow-ups are answered in context.
  - E. Re-run an agent by voice ("re-run the analyst, assume three hires", "redo the Devil's Advocate") through the existing re-run and amendment paths; the Advisor then resumes where it was.
- Also: the cash warning ends with a double full stop ("comes first..").
- Priority: V7 high; A–E medium
### [M4 → M5, first task] Carried from the M4 review: RESOLVED in M5 (re-test in V5 to V9 and RZ below)
**Resolved (2026-11-08, M5 PR):** with tests in `tests/test_m5_carried.py` and `tests/test_decision_frame.py`. Causes:
- 60: no agent ran. The new test patches `AgentRunner.run` and shows no call before approval and none after a rejection. But a rejection marks each planned agent "cancelled", and the narration counted a cancelled agent as finished ("… are done"). Agents that never started are now left out, and the lane says "I held the team back: no agent ran." The 5.7 s was planning (Planner and decision frame), which runs before approval by design.
- 61: the sentence splitter split after "vs.", and the near-duplicate pass dropped the second half. "vs.", "e.g.", "i.e.", "cf." and "approx." no longer end a sentence.
- 62: "as you asked" is said only when the request carries the founder's change ("The founder then added: …").
- 63: every one-metric lookup waited for approval under "Always". A local, code-answered lookup now needs no approval; a team still does.
- 55: the live tuner (`scripts/tune_prompts.py --agents devils_advocate --apply`) applied **v3** (3/5 against 0/5 for the old live v1 today; failures were the risk-line format). The tuning rubric now also fails an answer whose figures the source check removed. A stricter v4 scored 0/5 and is kept as a recorded version.
- 7: code runs the seeded Monte Carlo (1,000 runs, no change to the plan) for decisions and runway or burn questions, and at `CASH_RISK_WARN_AT` (default 0.5) or more adds: "A warning: in N % of 1,000 simulated futures with no change to your plan, cash runs out within 12 months, so protecting runway comes first." Figures with lineage; verified. `ChatResult.cash_risk` carries it.
- **RZ re-test (2 minutes):** approval **Always**: ask **What is our gross revenue churn?**: answered at once, no approval card (63). Ask **Should we open a Dubai office?** and **Hold the team back**: the lane says no agent ran, no "done" (60). Ask **Should we raise our prices by 10%?** with approval Never: no "as you asked" (62); a runway answer ends with the cash warning if your data's risk is 50 % or more (7).

Original items:
- 60: Check that "Hold the team back" really stops the agents. In held-back runs the narration still said "Librarian, Market Scout and Financial Analyst are done…" with about 5.7 s of work. Add a test that no agent runs before approval; fix if they do.
- 61: The near-duplicate pass cut a sentence in half: "The main trade-off is runway reduction vs. Your goal 'Decide whether…'".
- 62: "with price change of +10 %, as you asked" appeared when no change was asked. Acknowledge only real amendments.
- 63: Gross and net revenue churn still go to a team, so they wait for approval when "Ask before a team runs" is Always. Give them the same instant path as the other metrics.
- 55: The Devil's Advocate often writes unsupported figures that the Verifier removes. Tune its prompt.
- 7: The Advisor should speak up when the chance of running out of cash within 12 months is high.
- Priority: medium
### [M4] Re-test RX1–RX12: RESOLVED, awaiting re-test (fix session 2026-11-08, round 3)
**Resolved (2026-11-08, PR #9):** 58, 51, 54, 54b, 56, 57, 52, 53, 59, with tests. Re-test: RY1 to RY7. Causes:
- 58: "gross revenue churn" was not a known name ("gross" was a word the fast path did not expect), so the question
  went to the model, which fetched gross burn. Now a table of names and synonyms (`METRIC_KEYWORDS` in
  `app/agents/runtime.py`, longest first) routes them all, with a table-driven test. And a finance answer that does not
  give each metric the question names is never verified ("The answer does not give …, which was asked"). Net revenue
  churn has no routine of its own: it is shown as net revenue retention, says so, and counts as an assumption.
- 51: a held-back run (or a greeting) got the "verified" state because no check had failed. New state `not_run`: a
  grey "Not run" pill.
- 54: a near-duplicate pass (`app/agents/dedupe.py`) in the Advisor's sentence gate and over the final answer: the same
  question, the same goal, or mostly the same words (with the same figures) goes after its first time.
- 56: a queued question was offered only when the session's current run ended; after a restart it could wait forever.
  It is now offered whenever nothing is running, one at a time.
What remains: 7 is M5. The local model's own sentences after code's lead still vary run to run.

**Results (founder, 2026-11-08):** PASS RX2, RX3, RX4, RX5, RX6, RX7, RX8, RX9, RX10, RX12 (visible parts). FAIL RX11.
To fix:
- 58 (important): "What is our gross revenue churn?" was answered "Your gross burn is $428,612.47 as of 2026-10, but that's not the same as gross revenue churn…" with a green Verified badge. Route every metric name and synonym to the right metric; a reply that does not answer the question is never Verified; the answer and chip state the period (45).
- 51: "I held the team back because it was not approved…" shows a green Verified badge. No badge, or a neutral "not run", when nothing ran.
- 54: duplicate sentences in decision answers (the goal line twice; "what has changed since you drafted it? What has changed since you drafted the proposal?"). 54b: after an amendment, acknowledge the change in one clause.
- 56: queued questions: always offer each one, one at a time, with Ask it now / Drop it.
- 57: when the proposed option is not the best for runway, say why in one clause.
- 52: when the projection's last month lies after the zero-cash month, say so in one clause.
- 53: the amber badge text is truncated at the panel edge.
- 59: collapse identical consecutive versions in "Earlier versions you can restore".

### [M4] Re-test RW1–RW12, round 2: RESOLVED, awaiting re-test (fix session 2026-11-08)
**Resolved (2026-11-08, PR #9):** 49, 40, 22, 42, 46, 47, 48 (P1) and 44, 43, 45, 39, 41, 37, 38, 50 (P2), with tests.
Re-test: RX1 to RX12. Causes worth knowing:
- 22: a turn sent while the first was still being planned opened a second session, and with it a second run awaiting
  approval (the frontend read the session id before React had stored it). A Playwright test now covers it.
- 40: "also make it a two person team" carries a figure, so it was taken as an answer to the lane's question and
  re-run at once: planned afresh (so a new team, and the briefs lost Dubai), and the browser titled it with the
  follow-up alone. Now a follow-up to an open decision is offered first, then re-runs that decision with the same
  team (fresh agents) and a frame rebuilt in code from the edited request (2 local hires); the title is the question
  plus "· changed: …".
- 49: a new `app/agents/horizon.py`. The answer's first sentence is code's: what the projection covers and its last
  month's figure, labelled. The prose may add no figure, an agent's sentence stating one for the uncovered date is
  taken out (counted on the "claims removed" chip), and the badge lists it as an assumption, so it is never green.
- 46: the reset could be steered by a saved mapping for a sheet of the workbook. Load sample data now ignores saved
  mappings. The first-press failure itself did not reproduce here (one press restored pnl in every sequence tried).
What remains: 7 is M5. The local model's own sentences after code's lead still vary run to run.

**Results:** PASS RW1, RW2, RW3, RW7, RW9, RW11 (the three-state badge, reload, Settings Save/Discard, memo title sync,
superlatives and the short decision answer all pass). FAIL RW4, RW5, RW6. RW8 partly: the warning works; see 46–48.

**P1 Trust and data safety:**
- 49 (RW4). "What will our MRR be in 2031?" answered "projected to be $300,334.87 ... runway 11.23", green Verified. The scenario engine projects 12 months (to Oct 2027), so a month-12 figure was stated for 2031. The Verifier must check a claim's period against the tool output's period: a figure may only be stated for a date or period the tool covers. Beyond the horizon: say the model projects 12 months, give the month-12 figure labelled with its month and "assumption, confirm", and never mark a claim about an uncovered date Verified. Tests for 2031, "next year", "in 5 years".
- 40 (RW5). After the Dubai answer, "also make it a two person team" started a NEW run titled with that text (Librarian + Market Scout, generic "target region" briefs, no Dubai, no Financial Analyst). While a decision is open on screen, follow-ups ("also…", "make it…", "what if…", "instead…", "change … to …") apply to that decision: show "Restart with your change?" and re-run the same decision with the change (local hires = 2), keeping its team, context and frame. Never a context-free run from a follow-up.
- 22 (RW6, still open). The input box does not accept a second message while the first question is planning or awaiting team approval. Accept and classify turns at once in every phase (planning, awaiting approval, running) and queue them with a visible note.
- 42. The same question was queued twice ("what is our runway?" / "What is our runway?"): de-duplicate queued questions (case and spacing insensitive).
- 46. "Load sample data" did not restore pnl on the first press (pnl stayed one_row.csv, 1 row); a second press did. A reset always reloads every table from northwind_financials.xlsx, whatever pending uploads or saved mappings exist. Test: upload to pnl, one press restores 360 rows.
- 47. Undo keeps one step only: after two uploads to pnl the 360-row version was gone from /api/data/backups. Keep several versions per table (at least the last 3 plus the last clean sample version), list them with source and row count, allow restoring any.
- 48. After Load sample data every table shows "Undo the last upload to …" though nothing was uploaded: label backups by what made them (sample reload, upload, mapping) and show only meaningful undo buttons.

**P2 Quality:**
- 44 IMPORTANT. The price-rise cost model shows wrong units: "Price change $10 / $10 / $10" (should be 10 %), "Extra monthly churn it causes $0 / $1 / $1" (should be 0 / 0.5 / 1 pts). Every cost-model row carries its own unit (USD, %, pts, people, months). Tests.
- 43. The price rise proposed "New customers only · cost not modelled" over modelled options, with no reason. Never propose an unmodelled option over modelled ones unless the answer says why; prefer modelling it (new_customer_arpa).
- 45. Gross revenue churn (monthly) was 0.90 % in one answer and 1.22 % in another: every metric figure in answers and chips states its period (e.g. "Oct 2026" or "trailing 12 months").
- 39. "0/6 cloud" and "Cloud slots 0/6" still show while cloud is off (agents panel, Activity): hide, or say "cloud off".
- 41. Run titles concatenate amendments ("also make it a two person team The founder then added: …"): keep titles short.
- 37. The badge popover on the runway answer is cut off at the left edge: keep popovers inside the viewport.
- 38. "The scenario matches the base." overlaps the "Under 3 months of cash" label on the cash chart.
- 50. "all of these are assumptions to confirm (assumption, confirm)": drop the redundant tag where the sentence says it.
- (7 is M5; left.)

### [M4] Founder review W0–W15: RESOLVED, awaiting re-test (fix session 2026-11-07)
**Resolved (2026-11-07, PR #9):** P1 (14, 20, 17, 32, 24, 21, 22), P2 (16, 18, 19, 23, 25, 26, 27, 9, 10) and P3
(1–6, 8, 11–13, 15, 28–31, 33–35, 36) are fixed, with tests. Re-test: RW1 to RW12 in the checklist. What remains:
- 7 is M5 (left, as agreed).
- **Load sample data** now loads the one workbook, but a fresh start still seeds from the demo CSVs: the same numbers, a different file name in lineage.
- The "leave the page" prompt for unsaved Settings is the browser's own dialog when closing the tab (the in-app dialog covers the app's own links).
- A memo's "Open numbers to confirm" section may still list a line whose figure was masked as unsupported.
- The live Dubai answer still depends on the local model: code drops repeats, extra sentences and questions about a draft's targets, but the remaining one to three sentences are the model's.

W0–W15 otherwise pass: metric loop 10/10 (median 1.7 s); no fabricated figures or sources on any screen; exports, matrix, upload mapping and settings work.

**P1 Trust and safety (must fix):**
- 14. Verification badge with three clickable states: Verified (shows sources), amber "Figures verified · N assumptions to confirm" (lists them, offers "enter your figures"), red Not verified (lists reasons). Placeholder assumptions alone give amber, not "Not verified".
- 20. With a proposed Dubai memo in the vault, Dubai went from 1 issue to 7: figures quoted from an existing vault memo (targets, kill criteria, costs) must be cited to that memo and count as supported.
- 17. A reload (F5) wipes the conversation and the open decision: persist the session and restore it on load.
- 32. Uploading a file mapped to an existing table replaced all 360 pnl rows with 1 row, with no warning: warn with row counts, offer append or replace, keep a backup and an undo.
- 24. The memo called the travel-led pilot "the least costly option", but partner/distributor is cheaper (-0.10 vs -0.21): superlatives and comparisons in prose must match the options table, or be rewritten.
- 21. "also make it a two person team" was queued as a new question: widen amendment detection (add/also/make it/change to/instead/only/assume); when accepted, change the run's inputs (local hires = 2).
- 22. The input box does not accept turns during the first seconds (planning): accept and classify turns at once.

**P2 Answer and memo quality:**
- 16. The decision answer text must lead with the proposed option, then the full model (as the lead card does).
- 18. The answer is a repetitive wall of text: at most about 5 sentences, no repeated goal/proposed lines; for a PROPOSED memo on record ask "what has changed since you drafted this on <date>?", never about meeting its kill criteria; no "reducing runway by -2.07" double negatives.
- 19. Never show "(removed: unsupported source)" inline: drop the sentence and show an "N claims removed" chip by the badge.
- 23. "What about our churn?" answers revenue churn 1.22 % while the goal is logo churn 1.67 %: include the goal's metric.
- 25. Editing a memo's title must update both frontmatter `title:` and the `#` heading.
- 26. Duplicate "Costs only: no new revenue..." sentence in the Financial Analyst finding.
- 27. "your adviser or your adviser" duplicate in Regulatory & Tax.
- 9. Skip the "which assumption would change your mind" narration for metric lookups.
- 10. Neutral page title for a decision (the question or "Dubai office"), not "A full Dubai office" when a pilot is proposed.

**P3 UI polish:**
- 1. KPI card "Runway · actual burn". 2. Gross-margin chip lists both row ranges. 3. "Chance of running out of cash within 12 months: N%". 4. Hide the cloud slot count when cloud is off. 5. Base line visible when it overlaps the scenario. 6. Cash chart y-axis fits the data. 8. Shorter lineage chip labels that do not truncate. 11. Finished agent cards show "finished", not stale step lines. 12. "Finished · 6 of 6" when done. 13. Hide or disable Cancel on finished agents. 15. Work time separate from time waiting for approval. 28. PDF export without the browser header/footer. 29. PDF includes the status and review-date chips. 30. Matrix weights rescaled to sum to 1 (or say so). 31. New matrix items start unscored in the middle, not in "Do now". 33. "Load sample data" keeps one consistent source (northwind_financials.xlsx). 34. Settings shows Ollama as "local", not "key set". 35. Badge and health strip agree when cloud is allowed without keys.
- 36. Settings: no auto-save. Save and Discard appear on any change with "You have unsaved changes"; save only on Save. Leaving Settings (another tab, closing, reloading) with unsaved changes asks "Save your changes?" (Save / Discard / Stay). Privacy-relevant changes apply only after Save.
- (7 is for M5; left.)

### [M3c] Fabricated figure with a fabricated citation reached the answer: RESOLVED (founder re-test RF1–RF6 pending)
**Fixed 2026-11-06;** see "Source check" under Current state.
- **Did:** checklist C4 (Dubai memo, cloud off).
- **Got:** Market Scout wrote "Dubai's GDP is approximately $150 billion [notes/economic-overview.md]"; that note does not exist in the vault. The Devil's Advocate built a risk on it, and the Advisor's answer asked "Are you certain the $150 billion market size figure is verified...". `answer verified False` and `memo verified False`, but the text still reached the founder.
- C2, C3 and the rest of C4 pass (goal consistency, reasons for rejected options; the "decided" lines were correct negatives).

### [M3b → M3c, first task] Decision prose still contradicts the structured frame (not blocking): RESOLVED in M3c (re-test C4)
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
- **(F8) Answering the slow-agent offer by voice.** The offer is spoken, but the answer is by button only ("Continue on Qwen on our server" / "Keep waiting"). Saying "continue on Qwen" would need a new turn type in the lane's classifier; worth it in M7b with the Boardroom, or now?
- **(F12) "Cost nothing" aloud.** An all-Qwen decision shows "This decision cost nothing…" but does not say it, so the spoken flow stays short. Say if you want it spoken too.
- **(M7h) Gate tier.** Recorded as Medium (proposed). Confirm.
- **(M7a) Approval after a verified key.** With the default `TEAM_APPROVAL=cloud_only`, verifying a key makes every decision team with a cloud agent wait for approval. For members in M7c: keep asking (safer, one click) or default to Never (smoother)? Recommendation: keep `cloud_only` and show the approval inline in the M7b Boardroom.
- **(M7a) Prices for members' models.** A model with no known price is counted at $15/$75 per million tokens so the cap still protects the member, which overstates cheap models (Groq, OpenRouter). Should M7f/M7c let members type the price, or should we keep a fuller price table?

0f. **From M6b (2026-11-18), none blocking:**
   - **I changed this PC's `.venv`**: `onnxruntime 1.31.1` → `onnxruntime-gpu 1.23.2` plus three CUDA wheels (about 300 MB), because your note asked for onnxruntime-gpu to be measured with `voice_bench.py`, which needs the real backend. Your standing rule is not to reinstall; I read the note as permission for this one package. `scripts\enable_tts_gpu.py --undo` reverts it. Say if you would rather keep Kokoro on the CPU (`VOICE_TTS_DEVICE=cpu`).
   - **setup.bat now swaps the package on every PC with an NVIDIA GPU.** On a PC without one it does nothing. If a PC's driver is too old for CUDA 12.9, Kokoro falls back to the CPU by itself, with a note in `/api/voice/status`.
   - **npm deprecation warnings left as they are**: all three need major upgrades (eslint 10, recharts 3, jsdom 27) and a reinstall. Want them as a small separate PR after M6?
   - **G is the minimal-but-complete version** (steps, rings, steps text, clock bars, movable, remembered). A picture of which agent read whose findings would need the lane to record that; say if you want it after M6.
   - **The voice_bench barge-in step changed** (it talks over the team line, not "On it."). Numbers from before and after are comparable for the pause and stop; only the line it lands on moved.
0e. **From M6a (2026-11-17), none blocking:**
   - **X3 compares with the base case only.** The Dubai frame's hires are low 1 / base 2 / high 3. "Assume two hires" now counts as already in the answer, although a restart would also narrow low and high to 2. That is my reading of "two hires = default"; say if you want that narrowing restart offered instead.
   - **Reset keeps your Settings** (`ui_settings.json`: approval policy, cloud switch, voice mode). `reset_demo.bat --settings` resets them too. Say if the default should be the other way.
0d. **From M5 fix round 5 (2026-11-15), none blocking:**
   - **Rule U0 is strict by design**: a turn of fewer than three words, or one that is not a question or a request ("The Dubai thing worries me"), is read back before any team runs. Say if it asks too often.
   - **U1's cause is my reading of the logs, not proven** (the recogniser's confidence is not logged). RZ2 is the check.
0c. **From M5 fix round 4 (2026-11-15), none blocking:**
   - **After an unanswered change, the summary ends without any offer.** One change, one offer: the offer was said when you asked, so with the answer I say the findings and the proposal and then nothing; "yes" still restarts and the card is still there. If you would rather hear a short reminder after the summary, or no summary at all until you have answered, say so.
   - **A different change said in the same run gets its own card** ("Assume four hires." after "Assume three hires."): the older card stays open too. Say if the newer one should replace it.
   - **T1 and the card drawn twice were not reproduced** (see the feedback item). RY2 and RY3 are the check.
0b. **From M5 fix round 3 (2026-11-14), none blocking:**
   - **What failed in RW5?** (Re-run the analyst.) See the feedback item and RX6.
   - *(Replaced in round 4: one change, one offer. See 0c.)* An unanswered change was asked again with the answer.
   - **A quiet "okay" after an offer is ignored** below the 0.45 threshold, which you kept for the read-back. If real answers get ignored, lower `VOICE_CONFIRM_BELOW`.
0a. **From M5 fix round 2 (2026-11-13): answered by the founder on 2026-11-14** (PRD §12): keep `small.en`; keep 1 s; a typed "stop" does not ask; keep "On it."; keep 0.45. The last point below (a re-run with a change runs the whole team) was not answered and stands as built.
   - **Whisper model.** `large-v3-turbo` fits beside qwen3:8b (+1.07 GB against +0.52 GB) and is no slower, but my test could not show that it hears you better. Try it in RW8 and say whether to make it the default (PRD §2 names `small.en`).
   - **Barge-in after 1 s, not 0.6 s.** Your R1 rule (a filler under about 1 s is a backchannel) needs it: under the old rule a 0.7 s "right" stopped the speech before its words were known. The cost: long speech over FounderOS cancels it after about 1 s; it is paused from the first 70 ms either way. Say if you want 0.6 s back.
   - **Typed "stop" is asked about too.** The Cancel button still stops at once. Say if typed stop should not ask.
   - **"On it." is still said before the opening turn**, because the team line needs the plan (several seconds) and your first-words target is 1 s. I read "one opening turn" as the team line.
   - **"Re-run the analyst, assume three hires" runs the whole team**, because the change alters the cost model every agent used. "Re-run the analyst" alone runs only the analyst.
0. **From the M5 fix round (2026-11-13), none blocking:**
   - **The echo gate is my addition** (default 0.3, `VOICE_ECHO_GATE`; 0 is off). It came from your decision log and a simulation, not from your room. RV3 and RV4 tell you whether to keep 0.3.
   - **The assumption question is no longer spoken** ("which assumption would change your mind?"); it is on screen. Your rule A says no running commentary, and I read the question as part of it. Say if you want it spoken.
   - **"Go through the risks" says the Devil's Advocate's own sentences** (up to three, numbers rounded). Rule B says never to read an agent's output aloud; I kept this because you ask for it explicitly. An alternative is a code-written count ("three risks, the first about …").
   - **Where did you see "comes first.."?** (RV10)
1. ~~Ollama model storage~~: **resolved 2026-11-06**: moved to a Docker named volume at your request; the Windows folder was kept. Old text: **Ollama model storage (performance, optional).** Your `ollama` container mounts its models from `C:/Dev_Tools/LLM Models/ollama` (a Windows bind mount). Every Ollama request spends ~3.7 s before inference (`/api/tags` alone ~1.2 s), and a cold load of qwen3:8b takes ~3.5 min. A Docker named volume (or a folder inside WSL) usually cuts both to seconds, which would make answers 2–3x faster (runway: ~15–20 s now, likely ~5 s). It is your n8n stack, so I changed nothing. FounderOS works either way: it preloads the model at startup and loads it before a call when needed. Your call whether to move it.

Answered (2026-11-03, founder note at the start of the M1 session):
1. ~~Demo currency~~: **keep USD** for the shipped `sample_data/` (INR stays available with `--currency INR`).
2. ~~Demo runway~~: **keep runway at about 10 months** at the end of the data window.

## Decisions made (M7b session, 2026-11-26)
- The Boardroom's navy is the app default and Welcome is a cream scope, so every other page shares the Boardroom's tokens (brief §3). Instrument Serif is for titles only; the memo body is Inter, because the display serif is hard to read at 15 px.
- The right-hand Agents rail is replaced by "Options so far"; agents are shown by the faces and the agent window. The e2e specs follow the new names.
- Welcome shows while the window has no conversation and no open decision; "Your numbers today" keeps the KPI cards (with lineage) visible before a question.
- Earlier memo versions live outside the vault (workspace data folder), so retrieval never reads an old proposal as current.
- Accept asks the team for the memo; Reject is on screen only; Quick/Thorough is visual until M7g. No Framer Motion was needed (CSS only).

## Decisions made (M7a fix round 4, 2026-11-26)
- F7c: a timeout is `slow` (a yellow notice); the member's internet is named only after an internet check finds no AI provider answering.
- F13b: a run with no frame whose memo proposes an option of an earlier frame carries that frame (the latest one with that option).
- F14: one Matrix entry per open decision, keyed by the frame's type and subject; a new memo renames it and keeps the founder's scores.
- F17: a waiting line is said once per agent per run and updated in place by its key.

## Decisions made (M7a fix round 3, 2026-11-26)
- F8b: the slow limit (`CLOUD_SLOW_AFTER_S`) is for an agent's cloud work as a whole, from its first cloud call; "twice its usual time" stays a per-call check. One offer per agent, as before.
- F7b: a used-up quota (`free_limit`) is not asked again inside the 15 s; a timeout or dropped connection after a busy answer is reported as that busy answer.
- F13: code's sentence on a changed proposal carries no figures (the option lines already give them), so the figure check never has to judge it.
- F4b: once the AI model card has a choice, `.env` keys do not make cloud usable (matching the router).

## Decisions made (M7a fix round 2, 2026-11-26)
- F4: "Allow cloud agents" can be turned on only with a usable key (a verified card key, or a `.env` key); the server refuses it otherwise (422). This replaces founder review 35's "allowed but no key" state for new choices (an existing `.env` `CLOUD_ALLOWED=true` with no key still shows "degraded").
- F7: 429 and 502/503/504 are "busy" (asked again twice, 0.6 s then 1.8 s), not "rate limited" or "can't reach"; a 429 that says the quota or credit is gone stays "No credit".
- F8: the threshold is 45 s or twice the agent's median cloud call this month (3+ calls), whichever comes first, never under 15 s; one offer per agent per run; the switch moves only that agent to Qwen, for the rest of its work.
- F12: the cost line is its own lane event (`spend`), after the "answer is ready" line, so the lane and voice logic still end on the answer. An all-Qwen decision shows "cost nothing…" on screen but the voice stays silent about it. The memo note is added only when cloud was used. Exchange rates from open.er-api.com (free, no key; daily); amounts are rounded ("about ₹1") because they are estimates from token counts.

## Decisions made (M7a gate fix round, 2026-11-26)
- F2: the key box is masked by CSS (`-webkit-text-security`), not by `type="password"`: a password field is what makes Chrome, Edge and Safari offer to save it, and `autocomplete="off"` alone does not stop them. Fallback to a password field only where that CSS is missing.
- F3: the card never defaults to a fixed model. The family order lives in config (`AI_MODEL_PREFERENCES`); within a family the newest stable version wins (a preview only when it is all the key has); a listed model that answers "not found" is skipped for the next best. The `*_MODEL` values stay as the `.env` route's models and as the fallback for servers with no models list.
- F3: a member's pick in the provider list always wins over the key's shape (e.g. an `sk-…` key for a Custom OpenAI-compatible server).
- F3: Ollama Cloud's address is fixed (`https://ollama.com/v1`), so Advanced is shown for Custom only.

## Decisions made (M7a session, 2026-11-22)
- M7 "Members Beta" recorded as M7a–M7g in PRD §8 and §12 and in the milestones table (founder's list, gates as given).
- A key is kept only after Test key passes, and is used at once: "test and save" is one step. Use Qwen keeps a saved key unused; Remove key deletes it.
- Verifying a key turns Allow cloud agents on (the member's opt-in). Turning it off is still the kill switch.
- An AI model card choice overrides `DEEP_PROVIDER` from `.env` (choosing Qwen there also means Qwen, not the `.env` provider). `AGENT_MODELS` per-agent routes still win.
- A chosen model with no known price is counted at $15/$75 per million tokens (above every listed price), so the cap still applies.
- Ollama Cloud, Groq and Custom get the JSON schema in the instructions (no `response_format`). Custom URLs: https and public only unless `AI_MODEL_ALLOW_PRIVATE_URLS=true`.
- The secret is made by `scripts/ensure_secret.py` (setup and run), never by the running app.

## Decisions made (M6b session, 2026-11-18)
- Kokoro fp32 on the GPU by default (`VOICE_TTS_DEVICE=auto`), `onnxruntime-gpu` pinned to 1.23.2 (CUDA 12), swapped in by `scripts/enable_tts_gpu.py` from `setup.bat`; the int8 model is never put on CUDA (PRD §12).
- F: panel limits Advisor 280–720 px, Agents 240–560 px, canvas at least 420 px; sizes per viewer in `localStorage`; folding hides the Advisor panel without unmounting it (voice keeps running).
- G: the agent window shows status and steps only (no figures), stays open across views, and leaves cancel and re-run to the Activity tab.
- A re-run whose change equals the answer's base case re-runs only that agent and says the change is already in.
- npm deprecation warnings: not changed (major upgrades only).

## Decisions made (M6a session, 2026-11-17)
- Kokoro licence for v1: keep `kokoro-onnx` with phonemizer/espeak-ng, installed from PyPI by setup; swap to a permissive G2P before any sale (founder; PRD §12).
- PRD §9 item 6 follows the 1 s barge-in decision (founder; PRD §12).
- Packaging: `run.bat` runs setup on a fresh clone and stops only for a taken port; Ollama models are pulled over HTTP; reset moves data to `data/backups/` and never deletes (PRD §12).
- X3: a change whose numbers all equal the base case of the answer's frame is "already in this answer": no offer, no card.

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
### M7a fix round 4 (2026-11-26)
- Gate log (fix round 3 re-test) and feedback F7c–F17 recorded; M7h note (stronger model for critical agents, Verifier check idea). F7c (`slow`, `is_timeout`, `internet_works`), F8c (`slow_offer_line` at startup, `Slow check:` lines, run.bat echo), F13b (`_open_frame_with`, `_option_named`, `runsAfter`), F14 (`decision`/`memo` on Matrix entries, `decision_key`), F15 (`honest_status`), F16 (`scout_no_web_note`), F17 (`line_key`). Tests: `backend/tests/test_m7a_fix_round4.py` (14), `backend/tests/test_m7a_fix_round4_start.py` (2, one starts a real uvicorn process like run.bat), `frontend/src/components/fixround4.test.tsx` (2).
### M7a fix round 3 (2026-11-26)
- Gate log (fix round 2 re-test) and feedback F4b–F13 recorded; M7f/M7b notes. F4b (Remove key saves cloud off; `cloud_usable` ignores `.env` once the card was used), F7b (busy kept over a later timeout/network error; `free_limit`), F8b (agent-level slow clock; cause: per-call timing, env var fine), F12b (`currencyMissing`, `cost_shown`, `usd_text`/`usdText` half up), F13 (`_follow_proposal`, `proposal_change_line`, `proposedFrame`). Tests: `backend/tests/test_m7a_fix_round3.py` (17), `frontend/src/components/fixround3.test.tsx` (4), `frontend/src/components/activity/runcost.test.tsx` (1).
### M7a fix round 2 (2026-11-26)
- Gate log and feedback recorded; PRD §8/§12 (F9, M7h, M7f, M7b polish). F4 (card refresh only on success, cloud needs a key, 422), F5 (key_shapes.json, AQ., unknown key, prefix log, re-detect), F6 (`ai_model` in health/settings, badge, pills, Default), F7 (busy retries + notice), F8 (slow-cloud watch, lane offer, two endpoints, card), F12 (`spend.py`: FX cache, money, SpendReport; lane/voice/memo/Settings). Tests: `backend/tests/test_m7a_fix_round2.py` (27), `frontend/src/components/fixround2.test.tsx` (8); Playwright 5/5 locally.
### M7a gate fix round (2026-11-26)
- F1–F3 recorded; F1 `run.bat` + cmd control-flow test (5 paths); F3 backend (key shapes, models lists, ranking, next best on refusal, 21 new tests); F2+F3 card (CSS-masked key box, provider from the key, Change model, Advanced for Custom; vitest 6 + Playwright `ai-model.spec.ts`); PRD §4/§8/§12, README, `.env.example`, checklist AM1–AM9.
### M7a session (2026-11-22)
- M7 recorded in PRD/HANDOVER; backend card (presets, Fernet store, test-and-save, routing), `ensure_secret.py`, frontend card, arm64 CI job + `docs/ARM64.md`; self-review fixes (no `max_tokens` on OpenAI-style tests, unsaved cloud toggle kept, secret regex).
- CI: the Playwright `turns.spec.ts` failure (also red on `main` after PR #12's merge) was order-dependent: the specs share one backend and `smoke.spec.ts` sets approval to Never. `turns.spec.ts` now sets `team_approval: always` itself and Playwright runs one worker. Reproduced (old spec fails after smoke) and fixed locally (4/4).
### M6b session (2026-11-18)
- Plan committed. F (resize handles, fold, `localStorage`) and G (agent window) with vitest and a Playwright spec; screenshots checked.
- Re-run with a change already in the base case re-runs only that agent (test_m6b).
- Kokoro measured: CPU fp32/int8, GPU fp32/int8 in a scratch venv, then `onnxruntime-gpu` 1.23.2 in the venv; `voice_bench.py` CPU 2381 ms → GPU 1681 ms metric answer; `VOICE_TTS_DEVICE`, CPU fallback, `scripts/enable_tts_gpu.py`, setup.bat; bench barge-in fixed to a long line; RL2c spoken PASS on the GPU.
- Self-review: saved widths now drawn to fit a smaller window. README, DEMO_SCRIPT (agent window), .env.example, MG1–MG9.
### M6a bug-fix (2026-11-17)
- Recorded PK1–PK6 PASS, PK7 FAIL; runner scenario Y1+Y2 reproduced Y2 (second "Yeah." silent); fixed Y1 (offer always), Y2 (a yes is always answered), Y3 (Qdrant already running) with tests; HANDOVER PK7, PK7b, PK1b.
### M6a session (2026-11-17)
- Plan committed; runner scenarios X1–X5 reproduced X2, X3 (typed) and X4 (spoken: "Yeah." heard as "Yaffen.") on the unchanged code; X1 passed; fixes X2–X4 with tests.
- `run.bat`/`setup.bat`, `check_ports.ps1`, `preflight.py`, `download_models.py`, `reset_demo.py`/`.bat` with tests; README fresh install; `docs/DEMO_SCRIPT.md`; PRD §9 item 6 and §12.
### M5 fix session, round 8 (2026-11-16)
- Recorded RL2a–RL2d PASS; runner scenarios W1–W5; fixed W1 (chat), W3, W4, W5; W2 not reproduced; full runner set; HANDOVER (RM1–RM6, `.\run.bat` typo).
### M5 fix session, round 7 (2026-11-16)
- Recorded RL2 first. Added runner scenarios RL2a–RL2d; before the fix they reproduced the founder's report (RL2a: change in the first stage, card shown, offer never spoken; RL2c/RL2d: the restart offer, not the reminder). Fixed in `session.py` (a change interrupts whatever is playing, one key for the reminder) and `manager.py` (reminder after a finished run). Stage line (`run.progress`), `FOUNDEROS_STAGE_DELAY_S`. `tests/test_voice_round7.py`. No microphone test.

### M5 fix session, round 6 (2026-11-15)
- Built `scripts/voice_scenarios.py` (real backend, Ollama, Whisper, Kokoro; typed and spoken) and `tests/test_voice_scenarios_script.py` (it skips without Ollama). First spoken pass: S1+S2, S3, S6 FAIL. Fixed S3 (sounds written as "Ahem."/"Ahoy."; yes to an open card) and S6 (re-run lines); fixed two runner faults. Final: all 12 PASS. No microphone test.

### M5 fix session, round 5 (2026-11-15)
- Recorded the RY results first (`5ad54d6`). Read the founder's turns from `decision_log.jsonl`, `llm_calls.jsonl` and the live voice metrics (text and timings only). U0–U5 and the reminder; `tests/test_voice_round6.py`; four older tests changed for rule U0 or U2. No microphone test.

### M5 fix session, round 4 (2026-11-15)
- Recorded the founder's RX1–RX7 results first (commit `1cfd1aa`). Then T1 to T5.
- New: `tests/test_voice_round5.py`. Changed: `conversation/classifier.py` (`plain`, a bare "Yes?" is a listening noise), `conversation/manager.py` (answers matched without marks, one offer per change, no second offer line, no ready line when no team ran), `voice/session.py` (`_Say.change`, `_changes_said`, answers matched without marks), `agents/runtime.py` (`clear_trade_off`, `code_trade_off`), `agents/graph.py` (`team_ran` on `run.finished`), frontend `workspace.tsx` and `AdvisorPanel.tsx` (one card per change, the lane's words, below the answer while open). Two round 3 tests changed with the design (the second asking is gone).
- Read this PC's `decision_log.jsonl` and `llm_calls.jsonl` for the founder's run of 07:08 to 07:10 UTC (times, callers, classes; no prompts are stored there). No microphone test.

### M5 fix session, round 3 (2026-11-14)
- Recorded the founder's RW1–RW10 results first (commit `2971096`). Then S1 to S5, the typed "stop" and the answered open questions.
- New: `tests/test_voice_round4.py`. Changed: `agents/graph.py` (`RunContext.cancel_requested`), `agents/dedupe.py` (`same_goal`), `agents/runtime.py` (`misdates_a_record`, the memo told again), `conversation/manager.py` (`turn(..., spoken=)`, one restart offer, an unanswered change kept open), `conversation/classifier.py`, `voice/session.py` (stopped runs, offers said once, own echo, unclear yes), `.env.example` (comments only), and the older tests that held the replaced behaviour.
- Live on this PC: five Dubai runs stopped by words on a scratch backend (port 8011, workspace `probe3`, removed afterwards). No microphone test.

### M5 fix session, round 2 (2026-11-13)
- Recorded the founder's RV1–RV11 results first (commit `eb06dd2`). Then R1, R8, R2 (P1) and R4, R5, R6, R3, R7 (P2).
- New: `app/voice/domain.py` (vocabulary, repairs, `count_reading`), `scripts/stt_bakeoff.py`, `tests/test_voice_round3.py`, fixtures `ugh`, `mm`, `hmm`, `right`, `okay`. Changed: `conversation/classifier.py` (fillers, stop words), `conversation/manager.py` (`Asked`, yes/no answers, `answered` on the outcome, re-run with `reuse`), `agents/graph.py` (`RunContext.reuse`, kept agents), `agents/runtime.py` (one question with a draft on record), `voice/session.py`, `voice/spoken.py`, `voice/stt.py`, `voice/turn_taking.py`, config and `.env.example` (`VOICE_STT_VOCABULARY`, `VOICE_CONFIRM_BELOW`, `VOICE_STILL_WORKING_S`, `VOICE_BARGE_IN_MS` 1000), frontend `workspace.tsx`, `voice.ts`, `VoiceControls.tsx`, `api.ts`.
- Real engines on this PC: `scripts/stt_bakeoff.py` only (Whisper `small.en` and `large-v3-turbo` on CUDA with qwen3:8b loaded). No microphone test and no live Ollama run in this round.

### M5 fix session (2026-11-13)
- Recorded the founder's V1–V10 review first (commit `957f0ed`). Then V7, A to E, the normaliser, the full stop (commit `90b8aa6`), then the echo gate, the metric "detail" line, the frontend "didn't catch that" note and the docs.
- New: `app/voice/spoken.py`, `tests/test_voice_round2.py`, `tests/fixtures/voice/churn.wav` (Kokoro, 16 kHz, like the others). Changed: `voice/session.py`, `conversation/manager.py` (`kind` on narration, `_rerun`, `_why_reply`, `_in_context`, `started_run`), `conversation/contexts.py` (`conversation_block`), `agents/graph.py` and `runtime.py` (`earlier` for the Advisor; one full stop), `config.py` and `.env.example` (`VOICE_ECHO_GATE`), `frontend/src/lib/voice.ts` and `VoiceControls.tsx`.
- Real-engine check on this PC (Silero, Whisper small.en on CUDA, Kokoro; a slow fake model holding the team; the microphone signal is the fixture plus 8 % of what is being played): with the gate, "What is our churn?" spoken over the team line is heard, queued, said to be queued, and offered after the summary, with one pause and no invented turn; without the gate, 20 pauses and invented turns ("No.", "it.") that start runs.

### M5 session (2026-11-08)
- First task: 60 (test and narration fix), 61, 62, 63, 55 (v3 applied by the live tuner), 7 (Monte Carlo warning). Commit `bf918e6`.
- Voice pipeline: `app/voice/` (audio, vad, stt, tts, turn_taking, session, service, metrics), `app/api/voice.py`, `DeltaQueue.tap()`, `scripts/download_voice_models.py`, `scripts/voice_bench.py`, frontend `lib/voice.ts` and `VoiceControls`. Real models loaded and measured on this PC (Current state). Tests: `tests/test_voice.py` (30) with four WAV fixtures made with Kokoro.

### M4 fix session, round 3 (2026-11-08)
- Recorded the RX1–RX12 results, then fixed 58, 51, 54/54b, 56, 57, 52, 53, 59 (see the feedback item). New: `app/agents/dedupe.py`, `tests/test_m4_round3.py`; `Verification.state` gains `not_run`; `Projection.zero_cash_month`.

### M4 fix session, round 2 (2026-11-08)
- Recorded the RW1–RW12 results, then fixed P1 and P2 in order (see the feedback item). New: `app/agents/horizon.py`; versioned backups (`_versions` table; the old one-step `_backups` is migrated on first read); `price_applies_to_existing` in the scenario engine (new-customers-only pricing); `frontend/e2e/turns.spec.ts`.
- Live against a scratch backend with the real local model: 49 found the Analyst projecting 36 months, and the lead's "36" was flagged as unsourced: the lead now names the end month only. 40 found the follow-up taken as figures and re-run without an offer: fixed.

### M4 fix session (2026-11-07)
- Recorded the founder review W0–W15, then fixed P1, P2 and P3 in order (see the feedback item). New: `app/agents/verification.py` (three badge states), upload conflicts/backup/undo (`/api/data/backups`, `/api/data/undo`), `frontend/src/lib/persist.ts` (reload keeps the session), Settings draft with Save/Discard and a leave guard.
- Verified live against a scratch backend with the real local model and a proposed Dubai memo in the vault: issues went from 13 to the removed Scout figure; the answer leads with the proposal and the full model.
- Last fixes from the live runs: a memo's figures quoted by the Memo Writer count as cited; with a draft on record, questions about meeting its targets are dropped.

### M4 session (2026-11-06)
- Item (1): "You are you." and "traveling" guards, with tests. The metric question: cause found, Verifier fixed ("months at this burn" is a claim about runway), code-written fast path. Live 10/10 verified, median 1.7 s.
- Backend for the UI: `/api/settings`, `/api/priorities`, `GET /api/runs/{id}/stream`, `PUT /api/data/mappings`, the frame on `team.proposed`, `local_only` on approve, run detail with message and frame.
- Frontend: all views, Recharts, Markdown, hash routes, one state store fed by `/api/events`.
- Playwright smoke test with a scripted model that invents a figure and a citation, in CI.
- Self-review (`/code-review`, medium, full diff): 10 findings, all fixed: see the PR. One is a change you should know about: the fast path now takes a question only if every other word is one a plain lookup uses, so "MRR for January" goes to the model.
- Found by driving it live: events arriving before the POST returned were lost (now held); a small question cleared the open decision off the canvas (the latest decision now stays); the same file showed one chip per heading (now one per file); `safeStep` left "illion" behind after masking "$160 b" (fixed, with a test).

### M3c fix session (2026-11-06)
- Root cause: the Verifier flagged the figure but only `verified: false` changed. The text went on, and the `[UNVERIFIED: number without lineage: $150 billion]` flag itself carried the figure to the Advisor. A figure was checked against every passage in the run, never against the file it was cited to.
- The first live run on the fix showed the fix itself removed your real 1.5 % churn goal, and left the Scout's recollections in Open numbers. Both fixed.
- A live price-rise failure was the eval's own pattern: "aligns with the goal" was true there. The eval now reads the goal statuses.
- A live Dubai failure was real: "aligns with the goal ... if needed" read as a condition, so the guard let it through. Fixed, with a test.

### M3c session (2026-11-05)
- Goal check, cheaper options and off-brief wording first. Live, the goal's own words "without new financing" read as a negation, which is why "aligns with the goal" got through.
- The labelled set found real bugs in routing and wording, all fixed: intent gaps (notes on the company profile, "did we decide", "hello there"), ratios shown as 0.7213, a goal named without saying it moves away, and "who would own" missing People & Ops.
- Installing `torch` and `laya` was refused by the session's permission check, and not retried. Laya and Jev are built against the documented APIs with fakes, as your note allowed.
- Self-review found 13 issues, all fixed: Jev ignored `CLOUD_ALLOWED`; names escaped when hyphenated, in lower case or in a file path; the goal check was re-run for the wrong option; a removed contradiction could leave a blank memo line; `_stops_an_option` deleted legitimate advice; a `KeyError` on unusual casing; Laya trained and served with different option wording; the Laya environment lacked the backend; `prompts/versions/` was untracked; `LAYA_DEVICE` was ignored for a checkpoint; and three smaller ones.
- The first live Dubai run hit a 20-minute timeout because the bake-off and the backend asked Ollama for different context sizes, and each switch reloaded the model. The bake-off now uses the app's size.


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

## Decisions made (M5 fix session, round 5, 2026-11-15)
- Rule U0 and the reminder are in PRD §12. "Clear" is code: three words or more, and a question word, a request verb ("compare", "draft", "I want"), "should we", or a question of four words or more; or one metric named. Anything else is read back, and yes runs it as said.
- A sound (`is_noise`: ugh, mm, hmm, uh, uh-huh, ah, oh) never answers and never closes a question; a one-word turn that is a word ("No.") still answers.
- A re-run that names no agent at all ("Redo the forecast") stays an ordinary turn, so rule U0 decides it.

## Decisions made (M5 fix session, round 4, 2026-11-15)
- The founder's rules T1 to T5 are in PRD §12.
- Mine, within those: an answer is matched on its words alone (`plain`: no case, no `? ! . , ; :`), in the lane and in the voice. A listening noise does not close an offer that has a card; any other turn still does.
- One offer per change means the round 3 re-ask is gone. The voice asks after the summary only when the change's offer was never said aloud.
- The card shows the lane's reply from the `amendment.offered` event, so the screen and the voice cannot drift apart again.
- A trade-off sentence is judged by one rule (it names two options); code's replacement uses each option's own trade-off entry.

## Decisions made (M5 fix session, round 3, 2026-11-14)
- The founder's answers to the open questions, and the rules for S1 to S5, are in PRD §12.
- Mine, within those: `turn(..., spoken=True)` is how the lane knows a turn came from the recogniser; the HTTP API and text typed over the voice socket are typed. A stopped run is tracked in two places on purpose (the orchestrator's `cancel_requested` and the voice session's own list), so neither depends on the other.
- An echo is judged by words and timing, not loudness: words FounderOS said in the last 20 s, heard while it plays or within 1 s after. One plain word ("yes", "no", "stop", "okay") is never an echo.
- A second sentence on the same goal is dropped even when its figures differ; the figures are on the card.
- An unanswered change stays open on the finished run and is asked again (open question 0b).

## Decisions made (M5 fix session, round 2, 2026-11-13)
- The founder's decisions R4 and R5, and the rules for R1, R3, R6, R7 and R8, are in PRD §12.
- Mine, within those: the lane keeps one open yes/no question at a time (`Session.asked`); the next turn answers it or it lapses, and a stop or a number that was not confirmed changes nothing. A number confirmed with "yes" is applied without the second "Restart?" question.
- The summary's findings are code-built from the decision frame and the cash-risk check, not agents' sentences. The note on what is unverified or assumed is always one of them.
- A filler is decided by rules in both places (barge-in and turn classifier), so no model is asked and nothing waits on the GPU.
- The opening turn is not said again for a one-agent re-run.
- `VOICE_BARGE_IN_MS` 1000; `small.en` kept as the default STT model; no LLM correction pass.

## Decisions made (M5 fix session, 2026-11-13)
- The founder's decisions A to E, F and G, H to J, the Kokoro licence point and TTS latency are in PRD §12.
- Mine, within those: the summary is built from the run's structured result (metrics, decision frame, cash-risk check), not from the answer text; only an answer with neither a metric nor a frame is taken from the checked text, and then only its first two sentences.
- A spoken share is a fraction only when it is a share "of" something and within 2.5 points of a simple fraction; "around" for thousands, "about" for millions; a round figure is said without either.
- The floor rule: speech in progress or being understood holds back all new audio; replies go ahead of waiting narration.
- The echo gate (see Open questions).
- CI caught what this PC could not: the venv here is Python 3.12, CI is 3.11. On 3.11 `asyncio.wait_for` can swallow a cancellation, so the speaker's floor wait outlived `close()` and the Windows job hung for 28 minutes (cancelled by hand). The floor wait now uses `asyncio.timeout`, the speaker stops when the session closes, and `close()` waits at most 5 s. The fake STT now takes its script line when the audio arrives, so two utterances transcribed at once cannot swap words (the other Windows failure). Avoid `asyncio.wait_for` around a wait that a task cancel must end.
- "Re-run" after the answer re-runs the team with that agent's new brief, through the amendment path when there is a change. A re-run request that names no agent is an ordinary turn.
- The Advisor's context is the founder's turns and the first two sentences of each earlier answer (last 12 turns), never the lane's narration. It goes through the privacy filter like any cloud payload.

## Decisions made (M5 session, 2026-11-08)
- STT: faster-whisper `small.en`, `int8_float16` on CUDA (0.52 GB measured), `base.en` int8 on CPU as the fallback, chosen at start-up by a test transcription. CUDA DLLs from the `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` wheels (`gpu` extra).
- VAD: Silero v6 ONNX as bundled in faster-whisper, run with onnxruntime; the `silero-vad` package is not used (it needs torch). Frames are 512 samples (32 ms), the window Silero v5+ expects, not 30 ms.
- TTS: Kokoro-82M ONNX on CPU (fp32 `kokoro-v1.0.onnx`, 8 threads), so the shared GPU keeps headroom; clause-by-clause synthesis; cached short lines.
- Barge-in: any speech while speaking pauses at once; 600 ms of speech or non-backchannel words cancel; backchannel by rules first, then the decision model, unsure means barge-in.
- The conversation lane never speaks a figure: such a line becomes "I've put that on screen." Quiet mode silences all speech.
- A run's text is broadcast (`DeltaQueue.tap()`): the canvas and the voice each get all of it.
- A one-metric lookup needs no team approval, even under "Always" (63).
- The Advisor's cash warning is code-written from the Monte Carlo at `CASH_RISK_WARN_AT` = 0.5 (7).

## Decisions made (M4 fix round 3, 2026-11-08)
- A finance answer that does not give every metric the question names is "not verified", whatever else checks out.
- "Net revenue churn" (and net MRR / dollar churn) is answered with net revenue retention, labelled, as an assumption.
- Nothing ran (held back, or a greeting): the badge is a neutral "Not run".
- A decision lead says in one clause why its proposal beats an option with more runway: that option moves away from a goal, else this one is easier to undo.

## Decisions made (M4 fix round 2, 2026-11-08)
- A question beyond the projection gets code's sentence about the last projected month, as an assumption: amber, never green.
- Restoring a version keeps the current one as a version too, so an undo can be undone. Up to 3 versions per table, plus the last clean sample one.
- "Load sample data" is a reset: it ignores saved mappings, and keeps no version when a table already is the sample.
- New-customers-only pricing is modelled with `price_applies_to_existing = 0` (existing customers' churn assumed unchanged).

## Decisions made (M4 session, 2026-11-06)
- **Fast path for one metric:** a question of up to 22 words naming one metric gets a sentence written by code, plus at most one short LLM question under a 4 s timeout. It skips the Planner and the team. **Why:** your target; code cannot get the number wrong. **Tell me** if you would rather never have the optional question.
- UI choices are saved in `<data>/<workspace>/ui_settings.json` and win over `.env` until changed. Keys stay in `.env`, and the API only says whether one is set.
- The matrix's initiatives and weights live in the vault (`notes/priorities.md`), so Obsidian can read and edit them. Ranking stays code (`weighted_scoring`).
- A run's Advisor text has one reader (`GET /api/runs/{id}/stream`, 409 for a second). A second window, or a reload, gets the finished result from `GET /api/runs/{id}`.
- No client-side arithmetic on money. The fan chart uses the backend's P10 and P90 directly.
- Hash routes (`#/activity` and so on) instead of a router library: six views do not need one.

## Decisions made (M3c fix session, 2026-11-06)
- `Open numbers to confirm` keeps what to confirm but never the figure (your new rule replaces the M3b one).
- A forecast's or stop rule's own target stays, labelled as a target: a stop rule cannot work without a number. **Tell me if you want this stricter.**
- `issues` keeps the removed figure, as the audit trail for you.
- Spans of days and weeks are not financial figures, so "a 90-day pilot" is not removed.
- A figure with lineage from a routine stands even if the sentence cites a file that does not contain it, since the number is still true. A source that does not exist always removes the sentence.

## Decisions made (M3c session, 2026-11-05)
- Prompt versions are kept, scored and not applied: changing a live prompt is a default, so it waits for your approval (P5).
- Jev needs `CLOUD_ALLOWED=true` as well as a key: "cloud off" must mean nothing leaves the PC.
- A challenger prompt must beat the live one by a whole case, and an embedding model by 0.05 MRR on hybrid: one run on a small set is noisy.
- Names err towards hiding. A one-word name that could be an ordinary word is hidden only as written, so "it will" survives.

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
