"""What FounderOS expects to hear (founder re-test R6): a vocabulary for the speech recogniser, and code's own repair
of the few mishearings seen live. No model call: this adds no latency.

- `PROMPT` and `HOTWORDS` go to faster-whisper (`initial_prompt`, `hotwords`), which biases it towards the agents'
  names, the metric names and the words of a decision ("Dubai", "hires", "runway", "churn").
- `corrected` repairs a command's opening words where the mishearing is not a sentence anyone would say
  ("should be open a Dubai office", "Freerun the analyst").
- `count_reading` reads a number the way the open decision uses it: "2%" where the decision counts people is asked
  about ("Did you mean two people?") before anything changes.
"""

from __future__ import annotations

import re

from app.agents.registry import REGISTRY
from app.engine.metrics import METRICS

AGENT_NAMES = [spec.title for spec in REGISTRY.values()]
METRIC_NAMES = [m.label for m in METRICS.values()]
TERMS = [
    "FounderOS",
    "Advisor",
    "Verifier",
    "Dubai",
    "hires",
    "runway",
    "churn",
    "burn",
    "MRR",
    "ARR",
    "CAC",
    "LTV",
    "gross margin",
    "re-run",
    "redo",
    "restart",
    "memo",
    "kill criteria",
]
# Whisper reads the prompt as what was said just before: sentences in the founder's own register work best.
PROMPT = (
    "FounderOS. The founder talks to the Advisor about the company: runway, burn, churn, MRR, gross margin, hires. "
    "Should we open a Dubai office? Re-run the Financial Analyst, assume three hires. Make it a two person team. "
    "Redo the Devil's Advocate. What is our runway? Stop the team. Restart with my change."
)
HOTWORDS = ", ".join(dict.fromkeys([*TERMS, *AGENT_NAMES, *(n.split(" (")[0] for n in METRIC_NAMES)]))

_VERBS = (
    "open|hire|raise|launch|build|increase|cut|move|expand|start|stop|buy|sell|close|drop|add|change|switch|"
    "invest|spend|lower|reduce|price|take|do|go|make|keep"
)
_SHOULD_BE = re.compile(rf"^(should|shall|can|could) be (?=(?:{_VERBS})\b)", re.I)
_RERUN_HEARD = re.compile(
    r"^(?:free[\s-]?run|freerun|re[\s-]?run|rerun|rear[\s-]?run|we[\s-]run|three[\s-]run|read[\s-]?run|"
    r"rewrun|v[\s-]?run)\b[\s,]*",
    re.I,
)


def corrected(text: str) -> str:
    """The same words, with a command's opening repaired. Anything not listed above is left as it was heard."""
    out = text.strip()
    out = _SHOULD_BE.sub(lambda m: f"{m.group(1)} we ", out)
    if _RERUN_HEARD.match(out) and not re.match(r"^we\s+run\s+(?!the\b)", out, re.I):
        out = _RERUN_HEARD.sub("Re-run ", out, count=1)
    return out


_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_SAID = {v: k for k, v in _WORDS.items()}
_COUNT = rf"(?P<n>\d{{1,2}}|{'|'.join(_WORDS)})"
_PERCENT = re.compile(rf"\b{_COUNT}\s?(?:%|percent\b|per cent\b)(?P<team>\s+team\b)?", re.I)
_LEAD = (
    r"(?:(?:actually|ok|okay|so|and|no|sorry|wait|well)[,\s]+)*"
    r"(?:assume|assuming|make (?:it|that)|change (?:it|that) to|what if(?: it(?:'s| is| was))?|use|with|only|just|"
    r"let's say|say)?\s*(?:a |an )?"
)
_BARE = re.compile(rf"^{_LEAD}{_COUNT}[\s.!]*$", re.I)


def _count(word: str) -> int:
    return int(word) if word.isdigit() else _WORDS[word.lower()]


def count_reading(text: str, *, counts: bool, percents: bool) -> tuple[str, str] | None:
    """A number whose unit is in doubt, for a decision that counts people (`counts`) and has, or has not, a
    percentage of its own (`percents`). Returns the question to ask and the text to use if the founder says yes.

    - "make it a 2% team", "assume 2 percent": a percentage where the decision has none and does count people;
    - "two", "assume 3", "make it four": a number with no unit.
    None: nothing in doubt.
    """
    if not counts or text.rstrip().endswith("?"):
        return None
    percent = _PERCENT.search(text)
    if percent is not None and not percents:
        n = _count(percent["n"])
        if not 1 <= n <= 10:  # "15 percent" is a rate, not a head count misheard
            return None
        unit = "person" if n == 1 else "people"
        said = f"{n} person team" if percent["team"] else f"{n} {'hire' if n == 1 else 'hires'}"
        return f"Did you mean {_SAID.get(n, str(n))} {unit}?", text[: percent.start()] + said + text[percent.end() :]
    bare = _BARE.match(text.strip())
    if bare is not None and not percents:
        n = _count(bare["n"])
        if n < 1:
            return None
        unit = "person" if n == 1 else "people"
        return f"Did you mean {_SAID.get(n, str(n))} {unit}?", f"Assume {n} {'hire' if n == 1 else 'hires'}"
    return None
