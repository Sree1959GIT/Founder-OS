---
version: alpha
name: FounderOS Decision Room
description: >-
  Cream and editorial on Welcome, navy glass in the Boardroom. Business owners ask a hard question, a team of
  AI advisors argues it out around a table, and the owner decides. Built from docs/design/M7B_DESIGN_BRIEF.md
  (locked 22 Nov 2026) and the live tokens in frontend/src/index.css and frontend/tailwind.config.ts.
colors:
  # The one accent everywhere: the speaking agent, the leading option, the main action.
  primary: "#FF5B2E"
  on-primary: "#141414"
  # Boardroom (dark glass, the app default; :root in index.css)
  navy-bg: "#070B1F"
  navy-panel: "#0B1029"
  navy-card: "#0D1230"
  navy-card-hover: "#161D41"
  navy-border: "#202850"
  navy-border-strong: "#2D3662"
  navy-text: "#EFF1F9"
  navy-text-muted: "#ACB2CF"
  navy-signal-soft: "#FFAA85"
  navy-info: "#8FB4FF"
  navy-ok: "#6EE0B0"
  navy-danger: "#FF7F7F"
  navy-bubble-user: "#1D244C"
  navy-attention: "#38220E"
  navy-attention-border: "#7C3A1C"
  glow-tomato: "#FF5B2E"
  glow-violet: "#5B4DFF"
  # Welcome (light, editorial; .theme-cream in index.css)
  cream-bg: "#F4EFE6"
  cream-panel: "#EBE3D6"
  cream-card: "#FCFAF6"
  cream-card-hover: "#F0EADF"
  cream-border: "#DBD1C2"
  cream-border-strong: "#B5A898"
  ink: "#141414"
  cream-text-muted: "#5B554E"
  cream-signal-soft: "#AF3410"
  cream-info: "#1F4B8A"
  cream-ok: "#18644A"
  cream-danger: "#A82424"
  # The memo sheet
  paper: "#F4EFE6"
  # One bright colour per agent (faces.tsx). Used for the face, its seat ring and its name tag.
  agent:
    advisor: "#F4EFE6"
    financial-analyst: "#6EE0B0"
    market-scout: "#8FB4FF"
    librarian: "#C9A7FF"
    people-ops: "#FFC857"
    revenue-customer: "#5ED6E0"
    regulatory-tax: "#B9C2DD"
    prioritiser: "#FF9DBB"
    perspective-lens: "#B5E655"
    devils-advocate: "#FF7A6B"
    memo-writer: "#F2D3A2"
    planner: "#A9B0D0"
    verifier: "#7FDCB8"
typography:
  display-xl:
    fontFamily: Instrument Serif
    fontSize: 84px
    fontWeight: 400
    lineHeight: 1.02
    letterSpacing: -0.01em
  display-lg:
    fontFamily: Instrument Serif
    fontSize: 64px
    fontWeight: 400
    lineHeight: 1.02
    letterSpacing: -0.01em
  display-md:
    fontFamily: Instrument Serif
    fontSize: 44px
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: -0.01em
  page-title:
    fontFamily: Instrument Serif
    fontSize: 34px
    fontWeight: 400
    lineHeight: 1.2
  table-topic:
    fontFamily: Instrument Serif
    fontSize: 26px
    fontWeight: 400
    lineHeight: 1.2
  memo-h1:
    fontFamily: Instrument Serif
    fontSize: 36px
    fontWeight: 400
    lineHeight: 1.2
  body-lg:
    fontFamily: Inter Variable
    fontSize: 15px
    fontWeight: 400
    lineHeight: 1.55
  body-md:
    fontFamily: Inter Variable
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: Inter Variable
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
  label-md:
    fontFamily: Inter Variable
    fontSize: 13px
    fontWeight: 600
    lineHeight: 1.3
  label-caps:
    fontFamily: Inter Variable
    fontSize: 11px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: 0.06em
  number-lg:
    fontFamily: JetBrains Mono
    fontSize: 22px
    fontWeight: 500
    lineHeight: 1.2
    fontFeature: '"tnum" 1'
  number-md:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.3
    fontFeature: '"tnum" 1'
  lineage:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: 400
    lineHeight: 1.3
rounded:
  none: 0px
  sm: 6px
  md: 8px
  lg: 10px
  xl: 12px
  2xl: 14px
  table: 9999px
  full: 9999px
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
  3xl: 48px
  gutter-phone: 16px
  touch-min: 44px
  centre-min: 560px
  side-panel-min: 240px
  side-panel-default: 320px
motion:
  state-change:
    duration: 150ms
    timingFunction: ease-out
  surface-enter:
    duration: 450ms
    timingFunction: ease-out
  surface-exit:
    duration: 200ms
    timingFunction: ease-in
  speaking-glow:
    duration: 1800ms
    timingFunction: ease-in-out
  speaking-blink:
    duration: 3200ms
    timingFunction: linear
  lite:
    duration: 0ms
    timingFunction: linear
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: 12px
    height: 44px
  button-secondary-navy:
    backgroundColor: "{colors.navy-card}"
    textColor: "{colors.navy-text}"
    borderColor: "{colors.navy-border-strong}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    height: 44px
  button-secondary-navy-hover:
    backgroundColor: "{colors.navy-card-hover}"
    textColor: "{colors.navy-text}"
  welcome-input:
    backgroundColor: "{colors.cream-card}"
    textColor: "{colors.ink}"
    borderColor: "{colors.cream-border-strong}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.2xl}"
    height: 56px
  welcome-chip:
    backgroundColor: "{colors.cream-panel}"
    textColor: "{colors.ink}"
    borderColor: "{colors.cream-border}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.full}"
    height: 44px
  welcome-chip-hover:
    backgroundColor: "{colors.cream-card-hover}"
    textColor: "{colors.ink}"
  welcome-step-number:
    textColor: "{colors.cream-signal-soft}"
    typography: "{typography.display-md}"
  welcome-note:
    backgroundColor: "{colors.cream-bg}"
    textColor: "{colors.cream-text-muted}"
    typography: "{typography.body-sm}"
  welcome-status-ok:
    backgroundColor: "{colors.cream-card}"
    textColor: "{colors.cream-ok}"
  welcome-status-error:
    backgroundColor: "{colors.cream-card}"
    textColor: "{colors.cream-danger}"
  welcome-link:
    backgroundColor: "{colors.cream-bg}"
    textColor: "{colors.cream-info}"
  app-background:
    backgroundColor: "{colors.navy-bg}"
    textColor: "{colors.navy-text}"
  glass-header:
    backgroundColor: "{colors.navy-panel}"
    textColor: "{colors.navy-text}"
    height: 56px
  solid-panel:
    backgroundColor: "{colors.navy-card}"
    textColor: "{colors.navy-text}"
    borderColor: "{colors.navy-border}"
    rounded: "{rounded.xl}"
    padding: 16px
  metric-card:
    backgroundColor: "{colors.navy-card}"
    textColor: "{colors.navy-text}"
    borderColor: "{colors.navy-border}"
    typography: "{typography.number-lg}"
    rounded: "{rounded.xl}"
    padding: 12px
  metric-card-label:
    backgroundColor: "{colors.navy-card}"
    textColor: "{colors.navy-text-muted}"
    typography: "{typography.label-caps}"
  lineage-chip:
    backgroundColor: "{colors.navy-card}"
    textColor: "{colors.navy-info}"
    typography: "{typography.lineage}"
    rounded: "{rounded.sm}"
  option-leading:
    backgroundColor: "{colors.navy-card}"
    textColor: "{colors.navy-signal-soft}"
    borderColor: "{colors.primary}"
    rounded: "{rounded.xl}"
    padding: 16px
  table-topic:
    textColor: "{colors.navy-text}"
    typography: "{typography.table-topic}"
    rounded: "{rounded.table}"
  agent-seat:
    size: 72px
    rounded: "{rounded.full}"
  agent-name-tag:
    backgroundColor: "{colors.navy-card}"
    textColor: "{colors.navy-text}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: 6px
  speaking-tag:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.full}"
    height: 44px
  live-bar:
    backgroundColor: "{colors.navy-panel}"
    textColor: "{colors.navy-text}"
    typography: "{typography.body-lg}"
    height: 64px
  chat-bubble-member:
    backgroundColor: "{colors.navy-bubble-user}"
    textColor: "{colors.navy-text}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.xl}"
  offer-card:
    backgroundColor: "{colors.navy-attention}"
    textColor: "{colors.navy-text}"
    borderColor: "{colors.navy-attention-border}"
    rounded: "{rounded.xl}"
    padding: 12px
  status-ok:
    backgroundColor: "{colors.navy-card}"
    textColor: "{colors.navy-ok}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
  status-error:
    backgroundColor: "{colors.navy-card}"
    textColor: "{colors.navy-danger}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
  memo-sheet:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.lg}"
    padding: 48px
  memo-title:
    textColor: "{colors.ink}"
    typography: "{typography.memo-h1}"
  page-title:
    textColor: "{colors.navy-text}"
    typography: "{typography.page-title}"
  welcome-headline:
    textColor: "{colors.ink}"
    typography: "{typography.display-xl}"
  welcome-headline-tablet:
    textColor: "{colors.ink}"
    typography: "{typography.display-lg}"
  welcome-headline-phone:
    textColor: "{colors.ink}"
    typography: "{typography.display-md}"
  welcome-body:
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
  number-inline:
    textColor: "{colors.navy-text}"
    typography: "{typography.number-md}"
  glow:
    backgroundColor: "{colors.glow-tomato}"
  glow-secondary:
    backgroundColor: "{colors.glow-violet}"
  agent-face-advisor:
    backgroundColor: "{colors.agent.advisor}"
  agent-face-financial-analyst:
    backgroundColor: "{colors.agent.financial-analyst}"
  agent-face-market-scout:
    backgroundColor: "{colors.agent.market-scout}"
  agent-face-librarian:
    backgroundColor: "{colors.agent.librarian}"
  agent-face-people-ops:
    backgroundColor: "{colors.agent.people-ops}"
  agent-face-revenue-customer:
    backgroundColor: "{colors.agent.revenue-customer}"
  agent-face-regulatory-tax:
    backgroundColor: "{colors.agent.regulatory-tax}"
  agent-face-prioritiser:
    backgroundColor: "{colors.agent.prioritiser}"
  agent-face-perspective-lens:
    backgroundColor: "{colors.agent.perspective-lens}"
  agent-face-devils-advocate:
    backgroundColor: "{colors.agent.devils-advocate}"
  agent-face-memo-writer:
    backgroundColor: "{colors.agent.memo-writer}"
  agent-face-planner:
    backgroundColor: "{colors.agent.planner}"
  agent-face-verifier:
    backgroundColor: "{colors.agent.verifier}"
---

# FounderOS Decision Room

The source of truth for how FounderOS looks and feels. Read it before any UI change (CLAUDE.md). The tokens above
mirror `frontend/src/index.css` (CSS variables as HSL channels) and `frontend/tailwind.config.ts`. If the two
disagree, fix one of them in the same PR; the founder's brief `docs/design/M7B_DESIGN_BRIEF.md` wins over both.

## Overview

FounderOS is for business owners, not engineers. A member asks a hard question; six or so AI advisors argue it out
around a glass table; the member gets clear options with costs and risks and decides. The feeling we want is
"love at first sight": calm, warm, confident, a little theatrical, and never an engineering dashboard.

Two moods, one system:
- **Welcome** (no decision open): light and editorial. Cream paper, ink type, one tomato accent, a big serif
  headline. It says what the product does in plain words.
- **Boardroom** (a decision is open): dark navy glass with two soft colour glows. A frosted header, an oval glass
  table with the topic in serif, original character faces in the seats, solid panels for every number.

Every other page (Activity, Decisions, Data, Vault, Settings) uses the same tokens, fonts and plain words.

## Colors

- **Tomato `primary` (#FF5B2E) is the only accent.** It marks the speaking agent, the leading option and the main
  action. On a tomato fill, text is ink (#141414, 6.6:1). For tomato *text* use `navy-signal-soft` on navy and
  `cream-signal-soft` on cream (5.9:1), never raw tomato.
- **Navy** is the Boardroom and app default. `navy-card` (#0D1230) is the solid panel that all text and numbers sit
  on; `navy-text-muted` reaches 8:1 on it.
- **Cream** is Welcome (`.theme-cream`) and the memo sheet (`paper`).
- **Status colours** (`ok`, `info`, `danger`, `attention`) always come with a text label. Status is never shown by
  colour alone.
- **Agent colours**: each agent has its own bright colour, used for its face, its seat ring and its coloured name tag
  (F25). Pick a new agent's colour so that it stays distinct from the others and from tomato.
- **Glows** (`glow-tomato`, `glow-violet`) are blurred background accents only, never behind text.
- Hard-coded hex values in components (e.g. `common.tsx`, `ScenarioSimulator.tsx`, `AIModelCard.tsx`) are debt: move
  them to tokens when you touch the file.

## Typography

- **Instrument Serif**: headlines, the table topic, page titles and the memo title. Weight 400 only, slight negative
  tracking. Welcome headline: 44 px on a phone, 64 px from `sm`, 84 px from `lg`.
- **Inter Variable**: all UI text. The body is 13 to 15 px; labels are 11 to 13 px semibold; caps labels are tracked
  +0.06em.
- **JetBrains Mono** with tabular figures (`.num`): every number, lineage ID and code. No exceptions.
- All fonts are self-hosted through `@fontsource` (no Google Fonts CDN calls; the app must run offline).
- **Numbers are never truncated** (F20). A long figure shrinks (a smaller mono step) or wraps onto a second line. It
  is never cut with an ellipsis.

## Layout

- **Base unit 4 px.** Use the spacing scale; phone side gutter 16 px; touch targets at least 44 px.
- **Desktop Boardroom**: three columns. Left, the Advisor (typing only); centre, the table and the decision cards;
  right, "Options so far". Both side panels are resizable and foldable, with drag handles, and the size is remembered
  per viewer (F26). The centre keeps a minimum width (`centre-min`); below it, the table switches to the phone-style
  layout instead of squeezing. A "Focus on the team" button folds both side panels.
- **The table adapts to the team** (F25): one seat for each agent the planner chose (2 to 8), evenly spaced around the
  oval. There are no empty seats, and no face overlaps the topic.
- **Metric cards wrap** onto new rows; they never break apart or overlap.
- **Phone (390 px, mobile-first)**: Welcome is stacked, with a full-width input and the mic and "Call the team" side by
  side. Boardroom: the topic at the top, a "Speaking now" card (face and caption), a horizontal strip of the other
  faces, options stacked on a solid panel, and a sticky bottom bar with "Accept…" and a big hold-to-talk button.
- **The app always opens on Welcome** (F22). An unfinished decision is offered in one line ("You have an open
  decision: Dubai office. Continue it?"); it is never reopened automatically.

## Elevation & Depth

- Three layers: the navy background with glows, then glass **frames** (the header, the table, panel edges), then
  **solid panels** (`navy-card`) carrying all text and numbers.
- Glass is `rgba(255,255,255,0.06)` with a 13 % white border and an 18 px blur at 140 % saturation. The header glass is
  86 % solid panel, so its text reads over anything scrolled beneath it.
- **Lite mode** (`html[data-lite="1"]`): no blur, no glows, no animation. Glass becomes a solid panel. It turns on
  automatically on `prefers-reduced-motion` or a slow device, and there is a Settings toggle. Every screen must
  look finished in Lite mode.

## Shapes

- Radius: 6 px for small chips, 8 px for controls, 12 to 14 px for cards and panels, and full (pill) for buttons,
  chips, name tags and the oval table.
- **Faces** are simple, original inline-SVG characters, one consistent family: each has its own shape (circle,
  square, hexagon, tall, squircle, pill, shield, diamond, drop), two eyes and a small mouth. The Devil's Advocate
  has small horns; the Advisor (the host) wears a tomato dot. Never use stock avatars, emoji or anything that looks
  like an existing character.

## Motion

- Use CSS and Framer Motion only. Motion is short and purposeful: 150 ms for a state change, 450 ms "rise" for new
  content.
- **Speaking**: the speaking agent's seat has a pulsing tomato glow (1.8 s) and its eyes blink (3.2 s). Only one
  agent glows at a time.
- `prefers-reduced-motion` and Lite mode remove all of it (durations go to about 0).

## Voice & Content Strategy

- Plain words for business owners. Never show "Ollama", "Qdrant", "GPU", "429" or model IDs to members. The top bar
  shows one plain status ("All systems OK" / "Slow right now"); the details live in Settings (F21).
- **The Advisor speaks in 3 sentences or fewer** (F23). Details (kill criteria, predictions, sources) stay in the
  memo; the Advisor links to it and never recites earlier work unasked (F22).
- "On the table" names the current topic ("Dubai office") and updates with each new question. It never says "This
  decision" (F24).
- Name the real reason in a fallback or slow notice: "Groq hit its per-minute limit, so People & Ops finished on
  Qwen on our server."
- Buttons are verbs: "Call the team", "Accept", "Ask more", "Continue on Qwen on our server", "Keep waiting".

## Components

- **Buttons** (`button-primary`, `button-secondary-navy`): real `<button>` elements, at least 44 px tall, with a
  visible 2 px tomato focus ring offset from the background.
- **Metric card**: a caps label, then the figure in `number-lg`, then its lineage chip. The figure shrinks or wraps
  and is never truncated.
- **Lineage chip**: mono, `info` colour, dashed border. Every computed number carries one (numbers come from DuckDB
  routines, never from the LLM).
- **Options so far**: a solid panel; the leading option has a tomato border; Accept / Ask more / Reject; an evidence
  link ("12 sources · 9 checks").
- **Agent seat**: the face, a coloured name tag under it, and a status line (done ✓ / thinking… / next / slow /
  switched to Qwen).
- **Voice on the faces** (F27): tapping a face starts talking to that agent, and the LIVE bar reads "Talking to
  <agent>". The speaker gets a `speaking-tag` with a stop button under its face. Stopping a voice only stops the
  speech: research and number work go on, and the cards keep updating. Keyboard: Space = hold to talk, Esc = stop
  speaking, M = mute the mic. There are no separate "Start voice" buttons, and the left panel is for typing only.
- **LIVE bar**: the caption of what is being said, on a solid panel at the bottom.
- **Offer card** (`attention`): a slow agent, a fallback or a change waiting for the member, with two clear choices.
  One line per agent, updated in place, never repeated.
- **Memo sheet**: cream paper, a serif title, a "Latest" badge with date and time, and earlier versions listed under one
  memo per decision.

## Do's and Don'ts

**Do**
- Put every number in JetBrains Mono on a solid panel, with its lineage chip.
- Let numbers shrink or wrap; keep the whole figure visible.
- Size the table to the team the planner chose, and give each agent its own colour and name tag.
- Keep the centre usable: give it a minimum width, switch to the phone layout when it is narrow, and let both side
  panels resize and fold.
- Keep Advisor answers to 3 sentences, and link to the memo for detail.
- Open on Welcome, and offer an unfinished decision in one line.
- Make 44 px targets, visible focus and WCAG AA contrast, and test Lite mode, 390 px and Edge on Windows.
- Use tokens; if you need a new one, add it here and in `index.css` in the same PR.

**Don't**
- Truncate a number with "…", or let cards overlap or break apart.
- Put text over glass or over a glow.
- Show technical service names, error codes or model IDs to members.
- Show empty seats, or let a face sit on the topic.
- Make stopping the voice stop the team's work.
- Repeat the same status line, or recite old memos in the chat.
- Load fonts or scripts from a CDN, or use emoji or stock avatars.
- Copy another product's layout, illustrations or brand (see References).

## References (learn from, do not copy)

- **Midday** (midday.ai): a calm financial UI for small-business owners; numbers that stay readable.
- **Linear**: density without clutter, keyboard-first interaction, restrained motion.
- **ElevenLabs**: voice as a first-class, friendly control; clear speaking and listening states.
- **Vercel dashboard**: one plain status for the whole system with details a click away; strong empty and loading
  states.

Study how they solve a problem, then solve it our way, with our tokens, faces and words.
