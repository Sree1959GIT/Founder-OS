# M7b design brief: Decision Room redesign

Locked by the founder on 22 Nov 2026. Replaces the old "Graphite & Signal" look. Goal: "love at first sight" for business owners, while saying what it does in plain words. No engineering-dashboard feel.

## Fix in the new screens
- **F8d:** the slow-agent offer is sent by the backend but never shown. Show it in the Advisor panel and on the agent's card, with "Continue on Qwen on our server" / "Keep waiting".
- **F19:** a 429 fallback is silent (Groq's free 8,000 tokens a minute ran out mid-run; agents finished on Qwen while the cards still said "Cloud · groq · Verified"). Show it: "Groq hit its per-minute limit, so People & Ops finished on Qwen on our server". Count only real cloud calls in the spend report.
- **F9:** voice (the Advisor, the mic, speech and its context) lives outside the pages. Changing pages never starts, stops or resets it.
- **F18:** memo page. A "Latest" badge with date and time; earlier versions listed under ONE memo per open decision (no more "-2.md" files); Close / Back to the decision; "Regenerate memo" and "Ask the team about this" on the memo itself.
- **Polish:** "Change model" shows "Recommended (3–4) · Show all"; auto-test on paste; "Test again" after a pass; Settings footer credit "Rates by Exchange Rate API".

## 1. Welcome (no open decision; light, editorial)
Cream `#F4EFE6`, ink `#141414`, accent tomato `#FF5B2E`.
- Headline in Instrument Serif: "Ask a hard question. Six AI advisors argue it out. You decide."
- Sub-line: "They read your own numbers, check each other's work, and give you clear options with costs and risks. In about four minutes."
- One input "What are you deciding?", a mic button and a "Call the team" button; 3 example-question chips.
- Quick (~1 min) / Thorough (~4 min) toggle (visual now; wired in M7g).
- "How it works": 1 You ask · 2 Your team debates · 3 You get a clear choice.
- "Meet your team" strip: a face and a one-line plain role for each agent.
- A small key-verified chip.

## 2. Boardroom (a decision is open; dark glass)
Navy `#070B1F` with two soft blurred colour glows.
- Frosted glass header; an oval glass table in the middle with the question in Instrument Serif.
- Agents sit around the table as simple ORIGINAL character faces (inline SVG): own shape and colour, two eyes, a small mouth; Devil's Advocate has small horns. One consistent face family for every agent type, including the Advisor (the host).
- The speaking agent glows orange and its eyes blink. Under each face: done ✓ / thinking… / next / slow / switched to Qwen.
- Right: "Options so far" on a SOLID panel `#0D1230`; leading option highlighted orange; numbers in JetBrains Mono; Accept / Ask more / Reject; evidence link ("12 sources · 9 checks").
- Bottom: LIVE caption bar of what is being said, plus "Hold to talk".
- Keep the existing data (decision frame, cost model, goal check, scenario chart), restyled as cards below or beside the table.

## 3. All other pages
Activity, Decisions, Data, Vault, Settings: same tokens, fonts and plain words.

## Rules
- Fonts: Instrument Serif, Inter, JetBrains Mono, self-hosted via @fontsource (no Google Fonts CDN calls).
- All text and numbers on solid panels; glass for frames only; glows as accents only.
- Real buttons, touch targets ≥ 44 px, visible focus, WCAG AA contrast.
- "Lite" mode with no blur: automatic on prefers-reduced-motion or slow devices, plus a Settings toggle.
- Animation: CSS and Framer Motion only.

## Phone (Android Chrome, iPhone Safari), mobile-first at 390 px
- Welcome: stacked; input full width; mic and "Call the team" side by side.
- Boardroom: question at the top; "Speaking now" glass card (face + caption); horizontal scroll strip of the other faces; options stacked on a solid panel; sticky bottom bar with "Accept…" and a big "Hold to talk".
- iPhone Safari plays audio only after a tap: the first "Call the team" tap unlocks audio. The mic needs HTTPS and permission: show a friendly message if blocked.

## Build
Keep every existing feature and test working (numbers rule, lineage, voice, panels, agent window). Official frontend-design skill; shadcn/ui only for new components. Playwright screenshots of Welcome and Boardroom at desktop 1440 px and phone 390 px in the PR. Windows checklist: Edge desktop plus phone checks (Android Chrome or iPhone Safari on the same Wi-Fi if possible).
