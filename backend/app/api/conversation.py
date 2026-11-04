"""`/api/conversation/*`: the conversation lane (PRD F5). M4 builds the text UI on this and M5 the voice.

The lane's narration, offers and queue events arrive on `/api/events` with the rest of a run's events.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.conversation.manager import ConversationError, ConversationManager, TurnOutcome

router = APIRouter(tags=["conversation"])


def get_conversation(request: Request) -> ConversationManager:
    manager: ConversationManager = request.app.state.conversation
    return manager


ManagerDep = Annotated[ConversationManager, Depends(get_conversation)]


class TurnRequest(BaseModel):
    session_id: str | None = Field(None, max_length=64, description="Empty starts a new session")
    text: str = Field(min_length=1, max_length=4000)


class QuietRequest(BaseModel):
    quiet: bool


class AnswerRequest(BaseModel):
    accept: bool


@router.post("/conversation/turn")
async def turn(body: TurnRequest, manager: ManagerDep) -> TurnOutcome:
    """One founder turn: starts a run when idle, otherwise it is classified and handled without touching the run."""
    return await manager.turn(body.session_id, body.text)


@router.get("/conversation/{session_id}")
async def state(session_id: str, manager: ManagerDep) -> dict[str, Any]:
    found = manager.state(session_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"unknown session {session_id}")
    return found


@router.post("/conversation/{session_id}/quiet")
async def quiet(session_id: str, body: QuietRequest, manager: ManagerDep) -> dict[str, Any]:
    return {"session_id": session_id, "quiet": manager.set_quiet(session_id, body.quiet).quiet}


@router.post("/conversation/{session_id}/amendments/{amendment_id}")
async def answer_amendment(
    session_id: str, amendment_id: str, body: AnswerRequest, manager: ManagerDep
) -> dict[str, Any]:
    """Accept: cancel the run and start again with the edited request. Decline: the run goes on."""
    try:
        return manager.answer_amendment(session_id, amendment_id, body.accept)
    except ConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/conversation/{session_id}/queue/{queue_id}")
async def answer_queue(session_id: str, queue_id: str, body: AnswerRequest, manager: ManagerDep) -> dict[str, Any]:
    """Accept: run the offered question. Decline: drop it and offer the next."""
    try:
        return manager.answer_queue(session_id, queue_id, body.accept)
    except ConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
