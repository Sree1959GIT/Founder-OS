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

TurnKind = Literal["backchannel", "answerable_now", "amendment", "new_question", "stop"]
KINDS: list[str] = ["backchannel", "answerable_now", "amendment", "new_question", "stop"]
TURN_QUESTION = (
    "A founder said this while their team is working on an earlier request. Which is it? backchannel: an "
    "acknowledgement. answerable_now: asks about the work's progress. amendment: changes the running request. "
    "new_question: a separate request. stop: stop the work."
)

_STOP = re.compile(r"^(please\s+)?(stop|cancel|abort|halt|never ?mind|forget it)\b[\w\s]{0,20}[.!]*$", re.I)
_BACKCHANNEL = re.compile(
    r"^(ok|okay|k|thanks|thank you|thx|got it|cool|great|nice|sure|yes|yep|right|good|fine|mm+|hm+|uh[- ]huh|"
    r"go on|go ahead|continue|sounds good|understood)[\s.!,]*(thanks|thank you)?[\s.!]*$",
    re.I,
)
_STATUS = re.compile(
    r"\b(status|progress|how long|how far|how much longer|still (working|running)|are you (done|finished)|"
    r"is it (done|finished)|who is working|who's working|what are you (doing|working on)|what's happening|"
    r"where are (we|you)|which agents)\b",
    re.I,
)
_AMENDMENT = re.compile(
    r"^(actually|instead|wait|correction|sorry|no,)\b|\b(i meant|assume|change (it|that|this|the)|make (it|that)|"
    r"rather than|use .{1,40} instead|not .{1,40} but)\b",
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


def by_rules(text: str) -> TurnKind | None:
    """The clear cases. Order matters: "actually, stop" is a stop, and "how long if we assume two?" is an amendment."""
    cleaned = re.sub(r"^(actually|wait|sorry)[,\s]+", "", text.strip(), flags=re.I)
    if _STOP.match(cleaned):
        return "stop"
    if _BACKCHANNEL.match(text.strip()):
        return "backchannel"
    if _AMENDMENT.search(text):
        return "amendment"
    if _STATUS.search(text):
        return "answerable_now"
    if _QUESTION.match(text.strip()):
        return "new_question"
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
        return Classified(
            kind=decision.choice,  # type: ignore[arg-type]
            by="decision",
            probability=decision.probability,
            decision_id=decision.id,
        )
