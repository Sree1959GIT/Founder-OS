"""Calibration tracking (PRD §F1): probabilistic predictions, their outcomes and Brier scores.

Decision memos (M3b) record predictions such as "70%: churn stays under 2% for the next quarter"; the 30-day review
records what happened. The Brier score (mean squared error of the probability against the 0/1 outcome; 0 is
perfect, 0.25 is a coin flip) is tracked per owner, where the owner is the founder or an agent type.

Stored as JSON in `data/<ws>/calibration.json`, written atomically.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

CALIBRATION_FILE_NAME = "calibration.json"


class PredictionIn(BaseModel):
    statement: str = Field(min_length=1, max_length=500)
    probability: float = Field(ge=0, le=1)
    owner: str = Field("founder", pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    decision: str | None = Field(None, max_length=300, description="Memo path or decision id")
    resolve_by: date | None = None


class Prediction(PredictionIn):
    id: str
    created_at: datetime
    outcome: bool | None = None
    resolved_at: datetime | None = None


class OwnerCalibration(BaseModel):
    owner: str
    resolved: int
    pending: int
    brier_score: float | None
    mean_probability: float | None
    hit_rate: float | None


class CalibrationError(ValueError):
    pass


class CalibrationStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / CALIBRATION_FILE_NAME
        self._lock = threading.Lock()

    def _load(self) -> list[Prediction]:
        if not self.path.exists():
            return []
        try:
            return [Prediction.model_validate(p) for p in json.loads(self.path.read_text(encoding="utf-8"))]
        except (ValueError, TypeError) as exc:
            raise CalibrationError(f"{self.path.name} is corrupt: {exc}") from exc

    def _save(self, predictions: list[Prediction]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        payload = [p.model_dump(mode="json") for p in predictions]
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(tmp, self.path)  # atomic on Windows and POSIX

    def add(self, prediction: PredictionIn) -> Prediction:
        with self._lock:
            items = self._load()
            stored = Prediction(**prediction.model_dump(), id=uuid.uuid4().hex[:12], created_at=datetime.now(UTC))
            items.append(stored)
            self._save(items)
            return stored

    def resolve(self, prediction_id: str, outcome: bool) -> Prediction:
        with self._lock:
            items = self._load()
            for item in items:
                if item.id == prediction_id:
                    item.outcome = outcome
                    item.resolved_at = datetime.now(UTC)
                    self._save(items)
                    return item
            raise CalibrationError(f"no prediction with id {prediction_id!r}")

    def list(self, owner: str | None = None, pending: bool | None = None) -> list[Prediction]:
        with self._lock:
            items = self._load()
        return [
            p
            for p in items
            if (owner is None or p.owner == owner) and (pending is None or (p.outcome is None) == pending)
        ]

    def scores(self) -> list[OwnerCalibration]:
        """Per owner, plus an `all` row across owners."""
        items = self.list()
        owners = sorted({p.owner for p in items})
        return [_score(owner, [p for p in items if p.owner == owner]) for owner in owners] + [_score("all", items)]


def brier_score(pairs: list[tuple[float, bool]]) -> float | None:
    if not pairs:
        return None
    return sum((p - (1.0 if o else 0.0)) ** 2 for p, o in pairs) / len(pairs)


def _score(owner: str, items: list[Prediction]) -> OwnerCalibration:
    resolved = [(p.probability, p.outcome) for p in items if p.outcome is not None]
    brier = brier_score(resolved)
    return OwnerCalibration(
        owner=owner,
        resolved=len(resolved),
        pending=len(items) - len(resolved),
        brier_score=None if brier is None else round(brier, 4),
        mean_probability=round(sum(p for p, _ in resolved) / len(resolved), 4) if resolved else None,
        hit_rate=round(sum(1 for _, o in resolved if o) / len(resolved), 4) if resolved else None,
    )
