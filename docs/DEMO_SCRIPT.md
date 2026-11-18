# FounderOS: 10-minute stakeholder demo

A script for showing FounderOS to someone in about ten minutes, with the Northwind Analytics demo data. It follows the
acceptance demo in [PRD §9](PRD.md#9-acceptance-demo-end-of-m6), in the same order. **What to say** is in bold;
*what to point at* is in italics. Figures are those of the shipped demo data; if yours differ, you have changed the
data (run the reset in "Before the demo").

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
- **"FounderOS is a decision copilot for a founder. It runs on this laptop: the models, the data and the notes. One
  command starts it: `run.bat`, from a fresh clone."**
- *Top bar: "Local only", health dots.* **"Nothing goes to a cloud model unless I allow it."**

### 2. A number you can trust (0:45–2:15), §9.2
- Say: **"What's our runway?"**
- *Hear* a short spoken answer (two or three sentences): about **10.65 months** of runway at the actual burn.
- *See* the answer with a green **Verified** badge, "written by code", and the Runway card.
- *Click the dashed chip on the Runway card:* the lineage popover: formula, period, rows, the source file and the SQL.
- **"The language model never does the arithmetic. Every number comes from a database routine, and you can trace it
  to the exact rows of the spreadsheet."**

### 3. What-if (2:15–3:30), §9.3
- Say or type: **"What if we raise prices 10% and churn goes up 2 points?"**
- *See* the Scenario Simulator: the projected cash line and runway change against the base case.
- *Drag the price and churn sliders:* the chart updates as you move them (under 200 ms, no model involved).
- *Point at the Monte Carlo fan:* **"And this is the spread of outcomes, not just one line."**

### 4. A real decision (3:30–6:30), §9.4
- Say: **"Should we open a Dubai office?"**
- *Hear* "On it." and one opening line naming the team (Librarian, Market Scout, Financial Analyst, People and Ops,
  Regulatory and Tax, Devil's Advocate). Then it works in silence.
- *Click **Agents** at the top of the Advisor panel:* the agent window opens. Drag it by its title bar to a free
  corner. It shows where the run is (Plan, Team, Verify, Answer), a ring per agent that fills as it works, its current
  step and a bar on the run's clock. It stays open if you switch views; **Escape** closes it. (The Activity view still
  has the full cards, with cancel and re-run.)
- *Optional:* drag the edge of the Advisor panel to make the conversation wider, or fold it with the icon left of
  "Executive Advisor" to give the numbers the whole width. The sizes are remembered in this browser.
- **"A planner chose this team for this decision. They run in parallel, and a verifier checks every figure before I see
  it."**
- When it is done, *hear* the short summary: the full office's cost and its effect on runway, the proposal (a
  travel-led pilot), its trade-off, then one question: **"Want me to go through the risks?"** Say **"yes"**: it goes
  through the Devil's Advocate's risks (the pre-mortem).
- *See* on the canvas: the decision frame (options, a low/base/high cost table, goal check), the questions it asks you
  (Socratic), the risk register with High/Med badges, and the entry in the **Prioritisation Matrix**.
- Optional, 30 seconds: say **"Assume three hires."** *Hear:* "Your change to three hires isn't in this answer yet. Say
  yes to restart with it." Say **"yes"**: the team runs again with three hires (about $43,770.86 a month, runway down
  2.58 months).

### 5. Record the decision (6:30–7:45), §9.5
- Say or type: **"Record the decision on the Dubai office."** (The Memo Writer joins the team.)
- *Click **Decisions**:* the memo, with its chosen option, predictions, kill criteria and a review date.
- **"It's a plain Markdown file in the vault, `vault/default/decisions/`. I can open the vault in Obsidian."**
- *Click **Export PDF**:* the print dialog shows the memo alone. Cancel.

### 6. Interrupt it (7:45–8:45), §9.6
- Ask something with a longer answer, for example **"Should we hire two more engineers?"**, and while the summary is
  being spoken, talk over it: **"Wait, stop there."**
- *Hear* it pause at once (about 70 ms) and stop after about a second of your speech, then listen.
  **"A short 'mm' or 'right' doesn't cut it off: only real speech does. That is on purpose."** (Barge-in at 1 s,
  decided 2026-11-14.)

### 7. Offline (8:45–10:00), §9.7
- *Turn Wi-Fi off (or unplug the network).*
- Ask again: **"What's our runway?"** *Hear and see* the same verified answer.
- **"Everything you saw ran locally. Only the Market Scout and any cloud agents need the network, and they say so when
  it is not there."**
- *Turn the network back on.*

## If something goes wrong
| What you see | What to do |
|---|---|
| `run.bat` says "Port 8000 is already in use by an old FounderOS backend" | Close the old window, or `Stop-Process -Id <PID>` as it says, then `.\run.bat` |
| Health dot for Ollama is red | Start Ollama (`docker start ollama` if it runs in Docker); `run.bat` prints what is missing |
| The first answer is slow (30 s or more) | The model was cold: step 3 of "Before the demo" warms it |
| The voice does not answer | Check the microphone permission in the browser and the mode (Hands-free); typing works the same |
| A test memo or note shows up | `.\reset_demo.bat` (with FounderOS closed) |
| "Not verified" on the Dubai answer | Open the badge: it lists what could not be checked. The figures that are shown are still code's |
