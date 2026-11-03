The Verifier is deterministic code (`app/agents/verifier.py`), not an LLM prompt. It checks:

- every number in an agent's answer matches a value in that agent's tool results (which carry lineage), within
  rounding (1 %, and percentages may be written as ratios);
- every Librarian answer cites at least one vault source, and every path it cites was returned by a search.

An answer that fails is sent back to its agent once with the list of problems. If it still fails, it is passed on
flagged as unverified, and the Advisor says that the number needs checking.

This file documents the rules; edit the code to change them.
