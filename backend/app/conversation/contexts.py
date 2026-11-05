"""The three contexts of the conversation lane (PRD F5).

- **Global**: what is true of the workspace (id, currency, months of data, cloud on or off). Read fresh when needed.
- **Run**: a snapshot frozen when a run starts. A question asked mid-run never changes what that run is working from.
- **Local**: the last few turns of this session's window, for the fast lane only.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

LOCAL_WINDOW = 12


class GlobalContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str = "default"
    currency: str = "USD"
    first_month: str | None = None
    latest_month: str | None = None
    cloud_allowed: bool = False


class Turn(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str = Field(description="founder or lane")
    text: str


class RunSnapshot(BaseModel):
    """What a run started from. Frozen: later turns and later data do not change it."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    message: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    workspace: GlobalContext
    recent_turns: tuple[Turn, ...] = ()
    amendment_of: str | None = Field(default=None, description="The run this one replaces, after an amendment")


class LocalContext:
    """The session window. Old turns fall off; nothing here reaches an agent or a cloud provider."""

    def __init__(self, size: int = LOCAL_WINDOW) -> None:
        self._turns: deque[Turn] = deque(maxlen=size)

    def add(self, role: str, text: str) -> None:
        self._turns.append(Turn(role=role, text=text))

    def recent(self) -> tuple[Turn, ...]:
        return tuple(self._turns)
