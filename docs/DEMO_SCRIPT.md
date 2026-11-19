# FounderOS: 10-minute stakeholder demo

A script for showing FounderOS to someone in about ten minutes, with the Northwind Analytics demo data. It follows the
acceptance demo in [PRD §9](PRD.md#9-acceptance-demo-end-of-m6), in the same order. Figures are those of the shipped
demo data; if yours differ, you have changed the data (run the reset in "Before the demo").

**Two kinds of lines** (founder M6 gate D5: an audience line read aloud near the microphone is heard as a request):
- 🗣️ **Say to FounderOS:** words for the app, spoken into the microphone (or typed in the chat box).
- 👥 **Say to the room:** words for the audience. With **Hands-free** on, FounderOS hears these too: switch **Voice mode**
  to **Hold to talk** while you talk to the room (it hears only while you hold the button), or step away from the
  microphone. Never read them over its speech.
- *Italics* are what to point at or click.

## Before the demo (5 minutes, the day before)
1. **Clean demo data.** Close FounderOS, then from `D:\Founder-OS`: `.\reset_demo.bat`, answer `y`. Your old vault and
   data are moved to `data\backups\` (nothing is deleted), and the shipped Northwind notes come back, with no test memos.
2. **Start it once** with `.\run.bat` and wait for the browser. The first start loads the data and indexes the vault
   (about a minute). Check the top bar: health dots green (Ollama, storage; Qdrant green or "in memory"),
   **Local only**.
3. **Warm the model.** Click the chip **What is our runway?** once, so qwen3:8b is loaded on the GPU (the first answer
   after a cold start is slower). Then reload the page.
4. **Settings (gear):** *Ask before a team runs* = **Never** (the team starts at once; use **Always** if you want to
   show the approval panel), *Voice* on, mode **Hands-free**. Use headphones, or a quiet room with speakers.
5. Optional: `$env:FOUNDEROS_STAGE_DELAY_S` must **not** be set (it slows teams down for tests).

## The demo

### 1. It runs on this PC (0:00–0:45), PRD §9.1
- *The browser at http://127.0.0.1:3000 and the two server windows.*
- 👥 **Say to the room:** "FounderOS is a decision copilot for a founder. It runs on this laptop: the models, the data
  and the notes. One command starts it: `run.bat`, from a fresh clone."
- *Top bar: "Local only", health dots.* 👥 **Say to the room:** "Nothing goes to a cloud model unless I allow it."

### 2. A number you can trust (0:45–2:15), §9.2
- 🗣️ **Say to FounderOS:** "What's our runway?"
- *Hear* a short spoken answer (two or three sentences): about **10.65 months** of runway at the actual burn.
- *See* the answer card with a green **Verified** badge, and the Runway card on the canvas. (The card's header says who
  wrote it: "local" for the model on this PC, or "written by code" when no model was needed.)
- *Click the dashed chip on the Runway card:* the lineage popover: formula, period, rows, the source file and the SQL.
- 👥 **Say to the room:** "The language model never does the arithmetic. Every number comes from a database routine,
  and you can trace it to the exact rows of the spreadsheet."

### 3. What-if (2:15–3:30), §9.3
- 🗣️ **Say to FounderOS:** "What if we raise prices 10% and churn goes up two points?"
- *Hear and see* an answer that names **both** levers ("Change prices by +10 % with churn +2 pts") with its effect on
  projected runway, and a cheaper option (new customers only). It is a new question: it never says "already in this
  answer", even right after the Dubai decision.
- *Scenario Simulator (Workspace):* drag the price and churn sliders: the chart updates as you move them (under 200 ms,
  no model involved). *Point at the Monte Carlo fan:* 👥 **Say to the room:** "And this is the spread of outcomes, not
  just one line."

### 4. A real decision (3:30–6:30), §9.4
- 🗣️ **Say to FounderOS:** "Should we open a Dubai office?"
- *Hear* "On it." and one opening line naming the team (Librarian, Market Scout, Financial Analyst, People and Ops,
  Regulatory and Tax, Devil's Advocate). Then it works in silence.
- *Click **Agents** at the top of the Advisor panel:* the agent window opens. Drag it by its title bar to a free
  corner. It shows where the run is (Plan, Team, Verify, Answer), a ring per agent that fills as it works, its current
  step and a bar on the run's clock. It stays open if you switch views; **Escape** closes it. (The Activity view still
  has the full cards, with cancel and re-run.)
- *Optional:* drag the edge of the Advisor panel (the grip between the panels) to make the conversation wider, or fold
  it with the icon left of "Executive Advisor" to give the numbers the whole width. The sizes are remembered in this
  browser; a double-click on the edge goes back to the default.
- 👥 **Say to the room** (while it works, in Hold to talk): "A planner chose this team for this decision. They run in
  parallel, and a verifier checks every figure before I see it."
- When it is done, *hear* the short summary: the full office's cost and its effect on runway, the proposal (a
  travel-led pilot), its trade-off, then one question: "Want me to go through the risks?"
  🗣️ **Say to FounderOS:** "Yes." It goes through the Devil's Advocate's risks (the pre-mortem).
- *See* on the canvas: the decision frame (options, a low/base/high cost table, goal check), the questions it asks you
  (Socratic) and the risk register with High/Med badges.
- Optional, 30 seconds: 🗣️ **Say to FounderOS:** "Assume three hires." *Hear:* "Your change to three hires isn't in
  this answer yet. Say yes to restart with it." 🗣️ **Say to FounderOS:** "Yes." The team runs again with three hires
  (about $43,770.86 a month, runway down 2.58 months).

### 5. Record the decision (6:30–7:45), §9.5
- 🗣️ **Say to FounderOS:** "Record the decision on the Dubai office."
- *Hear* "Writing the memo from this answer: its options, costs and goal check. The team's findings stand." Only the
  Memo Writer works; the rest of the team's findings are kept.
- *Click **Decisions**:* the memo of **the answer on screen** (with three hires, if you made that change): the proposed
  option, every option with its cost and runway effect (written by code), the low/base/high cost model with "3 people
  (you said)", the goal check (it says the full office moves you away from the runway goal), the assumptions to confirm
  listed under "Open numbers to confirm", predictions, kill criteria and a review date.
- *Workspace → Prioritisation Matrix:* the decision is there as a new entry, "Not scored yet": drag it to where you
  think it belongs.
- 👥 **Say to the room:** "It's a plain Markdown file in the vault, `vault/default/decisions/`. I can open the vault in
  Obsidian."
- *Click **Export PDF**:* the print dialog shows the memo alone. Cancel.

### 6. Interrupt it (7:45–8:45), §9.6
- 🗣️ **Say to FounderOS:** "Should we hire two more engineers?" While the summary is being spoken, talk over it:
  🗣️ **Say to FounderOS:** "Wait, stop there."
- *Hear* it pause at once (about 70 ms) and stop after about a second of your speech, then listen: no reply, no change
  card. ("Hold on." and "Stop." do the same.)
- 👥 **Say to the room** (after it has stopped, in Hold to talk): "A short 'mm' or 'right' doesn't cut it off: only real speech
  does. That is on purpose." (Barge-in at 1 s, decided 2026-11-14.)

### 7. Offline (8:45–10:00), §9.7
- *Turn Wi-Fi off (or unplug the network).*
- 🗣️ **Say to FounderOS:** "What's our runway?" *Hear and see* the same verified answer.
- 👥 **Say to the room:** "Everything you saw ran locally. Only the Market Scout and any cloud agents need the network,
  and they say so when it is not there."
- *Turn the network back on.*

## If something goes wrong
| What you see | What to do |
|---|---|
| `run.bat` says "Port 8000 is already in use by an old FounderOS backend" | Close the old window, or `Stop-Process -Id <PID>` as it says, then `.\run.bat` |
| Health dot for Ollama is red | Start Ollama (`docker start ollama` if it runs in Docker); `run.bat` prints what is missing |
| The first answer is slow (30 s or more) | The model was cold: step 3 of "Before the demo" warms it |
| The voice does not answer | Check the microphone permission in the browser and the mode (Hands-free); typing works the same |
| A test memo or note shows up | `.\reset_demo.bat` (with FounderOS closed) |
| FounderOS answers something you said to the room | Switch Voice mode to Hold to talk before talking to the room; "Leave it." keeps things as they are |
| "Not verified" on the Dubai answer | Open the badge: it lists what could not be checked. The figures that are shown are still code's |
