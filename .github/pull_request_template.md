## Milestone
<!-- e.g. M1: Financial spine (or "M1 (partial)") -->

**Gate tier:** Light / Medium / Major  <!-- from HANDOVER.md "Review gates" -->

## What changed
<!-- 3 to 8 bullets -->

## Definition of Done (from docs/PRD.md §8)
- [ ] <!-- copy each DoD item for this milestone and tick what is done -->

## Gate 1: CI
- [ ] All CI checks green (or explain exactly why not)

## Gate 2: Self-review
- [ ] Full diff reviewed for bugs, security issues and scope creep
- Open findings (if any):

## Gate 3: Checklist
- [ ] New or changed behaviour has tests; tests use fakes (no GPU, Ollama, network or Windows needed)
- [ ] No LLM arithmetic on financial data; every number carries lineage
- [ ] No secrets, `.env` or large binaries committed
- [ ] `HANDOVER.md` updated (status, next steps, Gate log row)
- [ ] `.env.example` and README updated if config or setup changed

## Gate 4: Founder review (Windows checklist)
<!-- numbered commands and expected results, copied from HANDOVER.md -->
1.

## Known issues / open questions
