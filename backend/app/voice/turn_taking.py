"""Barge-in or backchannel? (PRD F5 and F7: decision-model backchannel detection, rules first.)

While FounderOS speaks, any speech pauses the audio at once. When the founder's sound ends:
- longer than `barge_in_ms`: a barge-in, decided without waiting for the words;
- the words are a backchannel ("uh-huh", "ok", "right"): playback resumes where it paused;
- clearly words of their own (three or more, or a question): a barge-in;
- a listening noise or one stray word ("Ugh!", "Huh.", "Thanks."): a backchannel (founder re-test R1: "uh-huh" came
  out of the recogniser as "Ugh!" and stopped the team);
- two other words: the decision model is asked, with a short timeout; unsure or slow means barge-in, because
  talking over the founder is worse than stopping once too often. A barge-in only stops the speech: whether the
  words stop the team is the conversation lane's decision, and that takes an explicit word and a yes.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Literal

from app.conversation.classifier import is_filler
from app.decision.base import DecisionError, DecisionService

Verdict = Literal["backchannel", "barge_in"]

BACKCHANNEL = re.compile(
    r"^(uh[- ]?huh|mm+[- ]?hm+|mhm+|hm+|mm+|yeah|yep|yes|ok|okay|right|sure|got it|i see|go on|cool|nice|great|"
    r"alright|all right|true|exactly|indeed)[\s.!,]*$",
    re.I,
)
QUESTION = re.compile(r"\?|^(what|why|how|when|where|who|which|can|could|should|is|are|do|does|stop|wait|no)\b", re.I)
DECISION_QUESTION = (
    "The founder spoke briefly while the assistant was talking. Is this only a backchannel (listening noise such as "
    "'uh-huh' or 'right') rather than an attempt to interrupt? Words: "
)


@dataclass
class TurnVerdict:
    verdict: Verdict
    by: str  # "duration", "rules", "decision model", "fallback"
    probability: float = 1.0


def by_rules(text: str, speech_ms: float, barge_in_ms: float) -> TurnVerdict | None:
    if speech_ms >= barge_in_ms:
        return TurnVerdict("barge_in", "duration")
    words = text.strip()
    if not words:
        return TurnVerdict("backchannel", "rules")  # a cough or a noise: carry on speaking
    if BACKCHANNEL.match(words):
        return TurnVerdict("backchannel", "rules")
    if QUESTION.search(words) or len(words.split()) >= 3:
        return TurnVerdict("barge_in", "rules")
    if is_filler(words):
        return TurnVerdict("backchannel", "rules")
    return None


async def decide(
    text: str,
    speech_ms: float,
    barge_in_ms: float,
    decisions: DecisionService | None,
    timeout_s: float = 0.4,
) -> TurnVerdict:
    ruled = by_rules(text, speech_ms, barge_in_ms)
    if ruled is not None:
        return ruled
    if decisions is None:
        return TurnVerdict("barge_in", "fallback", 0.0)
    try:
        decision = await asyncio.wait_for(
            decisions.yes_no(DECISION_QUESTION + repr(text.strip()), {"kind": "backchannel", "speech_ms": speech_ms}),
            timeout=timeout_s,
        )
    except (TimeoutError, DecisionError):
        return TurnVerdict("barge_in", "fallback", 0.0)
    if decision.choice == "yes" and decision.probability >= decisions.min_confidence:
        return TurnVerdict("backchannel", "decision model", decision.probability)
    return TurnVerdict("barge_in", "decision model", decision.probability)
