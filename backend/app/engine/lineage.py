"""Lineage: the audit trail every financial number carries (PRD R1).

A `Lineage` says which routine produced a number, the exact SQL that was run, which source files and rows fed it and
the formula used to combine the intermediate values. The UI shows it in the lineage popover and agents must pass it
through untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

# Money and ratios are Decimal internally (exact) and plain JSON numbers on the wire.
Number = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class SourceRef(BaseModel):
    """Rows of one source file that fed a number. Row numbers match the CSV line / Excel row (header = row 1)."""

    table: str
    file: str
    sheet: str | None = None
    rows: str = Field(description='Compact row ranges, e.g. "2-16, 20"')
    row_count: int


class Lineage(BaseModel):
    metric: str
    sql: list[str] = Field(description="Every SQL statement executed to produce the value, verbatim")
    source_files: list[str]
    source_rows: list[SourceRef]
    formula: str
    inputs: dict[str, Number | None] = Field(default_factory=dict, description="Named intermediate values")
    period: str | None = Field(default=None, description='Months covered, e.g. "2026-08..2026-10"')
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MetricResult(BaseModel):
    """A number plus its lineage. `value` is None when the metric is undefined (e.g. runway while cash-positive)."""

    metric: str
    label: str
    value: Number | None
    unit: str = Field(description="currency code, 'months', 'ratio', 'percent', 'count' or 'date'")
    as_of: str
    note: str | None = None
    detail: dict[str, int | Number | str | None] = Field(default_factory=dict)
    lineage: Lineage


def compact_ranges(numbers: list[int]) -> str:
    """`[2, 3, 4, 7, 9, 10]` -> `"2-4, 7, 9-10"`. Input order does not matter; duplicates are ignored."""
    ordered = sorted(set(numbers))
    if not ordered:
        return ""
    parts: list[str] = []
    start = prev = ordered[0]
    for n in ordered[1:]:
        if n == prev + 1:
            prev = n
            continue
        parts.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = n
    parts.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(parts)
