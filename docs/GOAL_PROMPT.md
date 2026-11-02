# FounderOS: `/goal` prompt for each dev session

Use **the same prompt for every session**. It works out which milestone is next from `HANDOVER.md`, builds only
that milestone, and stops. You never need to edit it between sessions.

## How to start a session

1. Open Claude Code in the `Founder-OS` repo, either on the web (claude.ai/code, repo `Sree1959GIT/Founder-OS`) or locally.
2. Paste the block below as one message.
3. When the session stops, read the summary at the top of `HANDOVER.md`, run the **Windows checklist** on your PC,
   and write your feedback in the `## Founder feedback` section of `HANDOVER.md` (or just tell the next session).
4. Start the next session with the same prompt.

To redo or adjust something, add one line after the prompt, e.g. `Founder note: in M1, use INR as default currency.`

---

```text
/goal Complete exactly ONE FounderOS milestone (the next unfinished one in HANDOVER.md), or reach a clean ~2-hour checkpoint inside it, then stop. The goal is met when all of these are true: (a) that milestone's Definition of Done in docs/PRD.md §8 is satisfied, or a clean checkpoint has been reached; (b) all tests and lint pass; (c) the work is committed and pushed; (d) HANDOVER.md is fully updated, including a Windows verification checklist for the founder.

PROTOCOL (follow strictly):

1. ORIENT, before writing any code
   - Read CLAUDE.md, then HANDOVER.md (all of it, including "Founder feedback"), then docs/PRD.md.
   - Run `git status`, `git log --oneline -15`. Confirm you are on the development branch named in HANDOVER.md; pull it.
   - Run `date -u` and record the session start time in HANDOVER.md under "Current session".
   - Find the target: the first milestone not marked DONE. If it is marked IN PROGRESS, resume from its "Next steps" list.
   - Act on any founder feedback first (bugs found on Windows take priority over new features).
   - Write a short plan for this session as a checklist in HANDOVER.md, then commit it.

2. BUILD
   - Implement only the target milestone's scope from docs/PRD.md. Don't start the next milestone.
   - Production-quality code: no pseudocode, no TODO stubs in delivered features, typed, with error handling.
   - Follow the key rules in PRD §3: deterministic math with lineage, privacy routing, never crash on missing services, voice never blocks the canvas.
   - Every external dependency (Ollama, Gemini, Claude, Qdrant, Whisper, Kokoro, VAD) goes behind an interface with a fake used in tests. This container has no GPU, Ollama, Docker or Windows, so never let a test depend on them.
   - Write tests as you go. Run the relevant tests after each meaningful change.
   - Commit small and often, with clear messages. Push at least every ~30–45 minutes (`git push -u origin <branch>`).
   - Update HANDOVER.md "Progress log" at each commit-worthy step (1–2 lines each), so a crash loses nothing.

3. TIME-BOX
   - Run `date -u` periodically. At about 1h45m after session start, stop adding features and start wrapping up, even mid-milestone.
   - If blocked (missing decision, credential, or a hard environment limit), don't guess on scope or architecture. Record the blocker and the options in HANDOVER.md "Open questions for founder", then finish the remaining unblocked work and wrap up.

4. WRAP UP (mandatory, even if the milestone is unfinished)
   - Run the full checks: backend `pytest -q` and `ruff check`, and frontend `npm run lint`, `npx tsc --noEmit` and `npm run build` (whichever exist so far). Everything must pass. If something can't pass, document exactly why.
   - Update HANDOVER.md:
       * Milestone table: mark DONE, or IN PROGRESS with a % estimate.
       * "Current state": what works, what is stubbed or faked, known issues.
       * "Next steps": an ordered, concrete list a fresh session can start on immediately.
       * "Windows verification checklist": numbered commands and expected results for the founder to run on the PC for this milestone.
       * "Decisions made this session" (also append significant ones to PRD §12).
       * "Open questions for founder".
   - Commit and push. Confirm the push succeeded.
   - Give a final message of 10 lines or fewer: what was done, the test status, what the founder should check, and what comes next. Then STOP and don't start further work.

NEVER: push to any branch other than the one in HANDOVER.md; commit secrets or .env; rewrite git history; skip or disable tests to get green; change the agreed stack or scope (PRD §12) without recording it as an open question.
```

---

## Optional variants

- **Bug-fix-only session** (after Windows testing):
  `/goal Fix every issue listed under "Founder feedback" in HANDOVER.md, add regression tests, update HANDOVER.md, commit and push, then stop. Follow the PROTOCOL in docs/GOAL_PROMPT.md.`
- **Shorter session to save credits:** add `Time-box this session to 1 hour instead of 2.` after the prompt.
