"""What a founder's turn means while a run is working (PRD F5).

Rules decide the clear cases at once, because this lane must answer while the GPU is busy with the agents. Only an
unclear turn goes to the decision service, under a short timeout. If that is slow, down or unsure, the turn counts as a
new question: it is queued, so nothing is lost and the running work is not disturbed.
"""

from __future__ import annotations

import asyncio
import re
from typing import Literal

from loguru import logger
from pydantic import BaseModel

from app.decision.base import DecisionError, DecisionService

# "confirm": the lane asked a yes/no question back ("Stop the team? Say yes to stop.") and nothing has changed yet.
TurnKind = Literal["backchannel", "answerable_now", "amendment", "new_question", "stop", "confirm"]
KINDS: list[str] = ["backchannel", "answerable_now", "amendment", "new_question", "stop"]
TURN_QUESTION = (
    "A founder said this while their team is working on an earlier request. Which is it? backchannel: an "
    "acknowledgement. answerable_now: asks about the work's progress. amendment: changes the running request. "
    "new_question: a separate request. stop: stop the work."
)

# A whole turn, about the work itself: "Cancel the Acme contract" and "Stop hiring contractors" are requests.
_STOP = re.compile(
    r"^(please\s+)?(stop|cancel|abort|halt|hold it|never ?mind|forget it)"
    r"(\s+(it|that|this|the run|the team|the work|everything|now|please))*[\s.!]*$",
    re.I,
)
# Founder re-test R1: only these words can stop a team. A model's guess never does.
STOP_WORD = re.compile(r"\b(stop|cancel|abort|halt|hold it|never ?mind|forget it)\b", re.I)
_BACKCHANNEL = re.compile(
    r"^(ok|okay|k|thanks|thank you|thx|got it|cool|great|nice|sure|yes|yeah|yep|right|good|fine|mm+|hm+|"
    r"uh[- ]?huh|mm+[- ]?hm+|mhm+|i see|go on|go ahead|continue|sounds good|understood)[\s.!,]*(thanks|thank you)?"
    r"[\s.!]*$",
    re.I,
)
# A noise, not a word: what "uh-huh" and "mm" come out of the recogniser as ("Ugh!", "Huh.", "Oh.").
FILLER = re.compile(
    r"^(u+g+h+|u+h+|u+m+|e+r+m*|a+h+|o+h+|h+u+h+|h+a+h*|m+|h+m+|e+h+|aha|ooh|wow|oops|phew|hey|bye|you|the|a|and|"
    r"so|well|i)([\s,-]+(u+g+h+|u+h+|u+m+|a+h+|o+h+|h+u+h+|m+|h+m+))*[\s.!,?…-]*$",
    re.I,
)
# About this work, not the business: "How long is our runway?" and "the status of the Acme deal" are questions.
_STATUS = re.compile(
    r"^(what('s| is) the )?(status|progress)( update)?\s*\??$|^where are (we|you)( at| now)?\s*\??$|"
    r"\b(how long (will|does|is) (this|it|that)|how much longer|how far along|still (working|running)|"
    r"are you (done|finished)|is it (done|finished)|who is working|who's working|"
    r"what are you (doing|working on)|what's happening|which agents)\b",
    re.I,
)
# Seen live: "also make it a two person team" was queued as a new question. A change to the running request may
# start with "also", "add" or "only", and "make it a", "change it to" or "instead" may come anywhere in it.
_AMENDMENT = re.compile(
    r"^(actually|instead|wait|correction|sorry|no,|also|and also|plus|add|include|only|assume|what if|"
    r"make (it|that|this)|change (it|that|this|the))\b|"
    r"\b(i meant|assume|assuming|rather than|instead|make (it|that|this) (a|an|\d+|one|two|three|four|five)|"
    r"change (it|that|this|the \w+) to|use .{1,40} instead|not .{1,40} but|only (\d+|one|two|three|four|five))\b",
    re.I,
)
_QUESTION = re.compile(
    r"^(what|who|why|how|when|where|which|should|shall|can|could|do|does|did|is|are|will)\b.*\?$", re.I
)


class Classified(BaseModel):
    kind: TurnKind
    by: str
    probability: float | None = None
    decision_id: str | None = None


def is_filler(text: str) -> bool:
    """A listening noise or a single stray word that asks nothing and orders nothing (founder re-test R1): "Ugh!",
    "mm", "hmm", "right", "okay", "Thanks." Never a question, never a command."""
    words = text.strip()
    if not words or FILLER.match(words) or _BACKCHANNEL.match(words):
        return True
    if "?" in words or STOP_WORD.search(words):
        return False
    return len(words.split()) == 1 and not _AMENDMENT.search(words) and not _STATUS.search(words)


def by_rules(text: str) -> TurnKind | None:
    """The clear cases. Order matters: "actually, stop" is a stop, and "how long if we assume two?" is an amendment."""
    cleaned = re.sub(r"^(actually|wait|sorry)[,\s]+", "", text.strip(), flags=re.I)
    if _STOP.match(cleaned):
        return "stop"
    if _BACKCHANNEL.match(text.strip()) or FILLER.match(text.strip()):
        return "backchannel"
    if _AMENDMENT.search(text):
        return "amendment"
    if _STATUS.search(text):
        return "answerable_now"
    if _QUESTION.match(text.strip()):
        return "new_question"
    if is_filler(text):
        return "backchannel"  # one stray word while a team works changes nothing
    return None


class TurnClassifier:
    def __init__(self, decisions: DecisionService | None = None, timeout_s: float = 4.0) -> None:
        self.decisions = decisions
        self.timeout_s = timeout_s

    async def classify(self, text: str, running_message: str) -> Classified:
        ruled = by_rules(text)
        if ruled is not None:
            return Classified(kind=ruled, by="rules")
        if self.decisions is None:
            return Classified(kind="new_question", by="default")
        try:
            decision = await asyncio.wait_for(
                self.decisions.choose(TURN_QUESTION, KINDS, {"turn": text, "running": running_message}, kind="turn"),
                timeout=self.timeout_s,
            )
        except (TimeoutError, DecisionError) as exc:
            logger.info("Turn classifier fell back to new_question: {}", type(exc).__name__)
            return Classified(kind="new_question", by="default")
        if decision.probability < self.decisions.min_confidence or decision.choice not in KINDS:
            return Classified(kind="new_question", by="default", probability=decision.probability)
        if decision.choice == "stop" and not STOP_WORD.search(text):
            # Founder re-test R1: "Ugh!" was taken as stop. Without one of the stop words a turn never stops a team:
            # two words or fewer is a listening noise, anything longer is kept as a question.
            kind: TurnKind = "backchannel" if len(text.split()) <= 2 and "?" not in text else "new_question"
            return Classified(kind=kind, by="rules", probability=decision.probability, decision_id=decision.id)
        if decision.choice == "backchannel" and len(text.split()) >= 3:
            # Founder re-test S4: words said while the team works are never dropped on a model's guess. A listening
            # noise is short and the rules know it; three words or more are kept as a question, so nothing is lost.
            return Classified(
                kind="new_question", by="rules", probability=decision.probability, decision_id=decision.id
            )
        return Classified(
            kind=decision.choice,  # type: ignore[arg-type]
            by="decision",
            probability=decision.probability,
            decision_id=decision.id,
        )
