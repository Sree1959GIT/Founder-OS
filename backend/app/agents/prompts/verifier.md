The Verifier is deterministic code (`app/agents/verifier.py`), not an LLM prompt. It checks:

- every number in an agent's answer matches a value the model was shown by its tools (which carry lineage), within
  the written rounding or 1 % (percentages may be written as ratios); numbers in the founder's own message may be
  repeated, numbers in a Planner-written brief may not;
- every Librarian answer names at least one vault source its searches returned, and every path it names was
  returned by a search.

An answer that fails is sent back to its agent once with the list of problems. If it still fails, it is passed on
flagged as unverified, and the Advisor says that the number needs checking.

This file documents the rules; edit the code to change them.
