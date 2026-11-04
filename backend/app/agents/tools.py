"""Agent tools: thin, typed wrappers over the deterministic engine (M1) and the vault (M2).

Each tool returns a `ToolOutcome`. `content` is a compact JSON summary for the model, small enough for an 8k
context. `artifacts` carry the full results (with `Lineage`) for the canvas. `numbers` lists every number the tool
produced, so the Verifier can check that the agent's answer only uses those numbers (PRD R1). Tools never raise;
an error becomes `ToolOutcome.error`, which the model sees.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agents.events import Artifact, ArtifactKind, Citation
from app.agents.verifier import extract_figures
from app.engine.decision_science import EVOption, ScoringRequest, expected_values, weighted_scoring
from app.engine.duckdb_engine import NoDataError
from app.engine.lineage import Lineage
from app.engine.metrics import METRICS, SUMMARY_METRICS, MetricError
from app.engine.montecarlo import MonteCarloRequest, run_monte_carlo
from app.engine.scenario import Adjustments
from app.engine.sql_guard import SqlGuardError, run_guarded_query
from app.llm.base import ToolSpec
from app.vault.manager import VaultError

WRITABLE_FOLDERS = ("decisions/", "journal/")
MAX_TOOL_CHARS = 6000
PASSAGE_SIZES = (1200, 800, 500, 300)  # characters per search hit: the largest that fits MAX_TOOL_CHARS


@dataclass
class ToolOutcome:
    content: dict[str, Any]
    artifacts: list[Artifact] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    numbers: list[float] = field(default_factory=list)
    error: str | None = None

    def for_model(self) -> str:
        payload = {"error": self.error} if self.error else self.content
        return json.dumps(payload, ensure_ascii=False, default=str)[:MAX_TOOL_CHARS]


def collect_numbers(value: Any) -> list[float]:
    """Every number inside a JSON-like value (dict keys excluded; SQL text and ids are strings, so skipped)."""
    found: list[float] = []
    if isinstance(value, bool):
        return found
    if isinstance(value, int | float):
        found.append(float(value))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(collect_numbers(item))
    elif isinstance(value, list | tuple):
        for item in value:
            found.extend(collect_numbers(item))
    return found


@dataclass
class ToolContext:
    """What tools may touch. `finance` is `deps.FinanceServices`; `vault` is a `VaultService` (or None)."""

    finance: Any
    vault: Any | None
    agent_id: str = ""


Handler = Callable[[ToolContext, dict[str, Any]], ToolOutcome]


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    handler: Handler
    status: str = "querying_data"  # agent.status while it runs
    model_callable: bool = True  # False: code runs it for the agent, so the model is not offered it


def _artifact(ctx: ToolContext, kind: ArtifactKind, title: str, data: dict[str, Any], **extra: Any) -> Artifact:
    return Artifact(
        id=f"art_{uuid.uuid4().hex[:10]}", kind=kind, title=title, agent_id=ctx.agent_id, data=data, **extra
    )


def _lineage_summary(lineage: Lineage) -> dict[str, Any]:
    inputs = {k: (float(v) if v is not None else None) for k, v in lineage.inputs.items()}
    return {"formula": lineage.formula, "period": lineage.period, "inputs": inputs, "sources": lineage.source_files}


def _difference(new: Decimal | None, old: Decimal | None) -> float | None:
    """Deltas are computed here, in code, so the model never subtracts (PRD R1)."""
    return None if new is None or old is None else float(new - old)


# --- finance ----------------------------------------------------------------------------------------------------
def _list_metrics(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    return ToolOutcome({"metrics": {name: d.label for name, d in METRICS.items()}})


def _get_metric(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    name = str(args.get("name", "")).strip().lower()
    result = ctx.finance.metrics.compute(name, args.get("month") or None, args.get("window") or None)
    data = result.model_dump(mode="json")
    content = {
        "metric": result.metric,
        "label": result.label,
        "value": data["value"],
        "unit": result.unit,
        "as_of": result.as_of,
        "note": result.note,
        "detail": data["detail"],
        "lineage": _lineage_summary(result.lineage),
    }
    card = _artifact(ctx, "metric_card", result.label, data, lineage=[result.lineage])
    return ToolOutcome(content, artifacts=[card], numbers=collect_numbers(content))


def _metrics_summary(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    results, unavailable = ctx.finance.metrics.summary(list(SUMMARY_METRICS), args.get("month") or None)
    rows = [r.model_dump(mode="json") for r in results]
    content = {
        "metrics": [{"metric": r["metric"], "label": r["label"], "value": r["value"], "unit": r["unit"]} for r in rows],
        "as_of": rows[0]["as_of"] if rows else None,
        "unavailable": unavailable,
    }
    cards = [_artifact(ctx, "metric_card", r.label, d, lineage=[r.lineage]) for r, d in zip(results, rows, strict=True)]
    return ToolOutcome(content, artifacts=cards, numbers=collect_numbers(content))


def _run_scenario(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    adjustments = Adjustments(**{k: v for k, v in args.items() if k in Adjustments.model_fields})
    result = ctx.finance.scenario.run(adjustments, horizon=int(args.get("horizon") or 12))
    data = result.model_dump(mode="json")
    content = {
        "as_of": result.as_of,
        "growth_mode": result.growth_mode,
        "growth_assumption": result.growth_assumption,
        "base_runway_months": data["base_runway_months"],
        "scenario_runway_months": data["scenario_runway_months"],
        "base_zero_cash_month": result.base_zero_cash_month,
        "scenario_zero_cash_month": result.scenario_zero_cash_month,
        "runway_change_months": _difference(result.scenario_runway_months, result.base_runway_months),
        "final_month": data["points"][-1] if data["points"] else None,
        "labels": result.labels,
    }
    card = _artifact(ctx, "scenario", "What-if scenario", data, lineage=[result.lineage])
    return ToolOutcome(content, artifacts=[card], numbers=collect_numbers(content))


def _run_monte_carlo(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    adjustments = Adjustments(**{k: v for k, v in args.items() if k in Adjustments.model_fields})
    request = MonteCarloRequest(adjustments=adjustments, runs=int(args.get("runs") or 1000))
    result = run_monte_carlo(ctx.finance.scenario, request)
    data = result.model_dump(mode="json")
    content = {
        k: data[k]
        for k in (
            "as_of",
            "runs",
            "growth_mode",
            "runway_p10",
            "runway_p50",
            "runway_p90",
            "probability_cash_out_within_12_months",
        )
    }
    card = _artifact(ctx, "monte_carlo", "Monte Carlo cash range", data, lineage=[result.lineage])
    return ToolOutcome(content, artifacts=[card], numbers=collect_numbers(content))


def _run_sql(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    result = run_guarded_query(ctx.finance.db, str(args.get("sql", "")), max_rows=50)
    data = result.model_dump(mode="json")
    content = {"columns": result.columns, "rows": data["rows"][:20], "row_count": result.row_count}
    card = _artifact(ctx, "table", "Query result", data, lineage=[result.lineage])
    return ToolOutcome(content, artifacts=[card], numbers=collect_numbers(content))


def _weighted_scoring(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    result = weighted_scoring(ScoringRequest(**args))
    data = result.model_dump(mode="json")
    card = _artifact(ctx, "priority_matrix", "Priority matrix", data)
    return ToolOutcome(data, artifacts=[card], numbers=collect_numbers(data))


def _expected_value(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    options = [EVOption(**o) for o in args.get("options", [])]
    rows = [r.model_dump(mode="json") for r in expected_values(options)]
    card = _artifact(ctx, "table", "Expected value", {"options": rows})
    return ToolOutcome({"options": rows}, artifacts=[card], numbers=collect_numbers(rows))


def _calibration_scores(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    rows = [s.model_dump(mode="json") for s in ctx.finance.calibration.scores()]
    return ToolOutcome({"owners": rows}, numbers=collect_numbers(rows))


# --- vault ------------------------------------------------------------------------------------------------------
def _require_vault(ctx: ToolContext) -> Any:
    if ctx.vault is None:
        raise VaultError("the vault is not available")
    ctx.vault.ensure_started()
    ctx.vault.wait_ready()
    return ctx.vault


def passage(text: str, snippet: str, limit: int) -> str:
    """Up to `limit` characters of a parent chunk, centred on the child that matched.

    Cutting from the start would hide a match at the end of a long note, however well it ranked.
    """
    if len(text) <= limit:
        return text
    at = text.find(snippet)
    if at < 0 or len(snippet) >= limit:
        return (snippet if at >= 0 else text)[:limit]
    start = min(max(0, at - (limit - len(snippet)) // 2), len(text) - limit)
    return text[start : start + limit]


def _fit_hits(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hits for the model, sized so the JSON is never cut mid-string (or figures it never saw counted as shown)."""

    def build(limit: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        seen_decisions: set[str] = set()
        for r in rows:
            hit = {"path": r["path"], "heading": r["heading"], "text": passage(r["text"], r["snippet"], limit)}
            if r.get("decision") is not None and r["path"] not in seen_decisions:
                seen_decisions.add(r["path"])
                hit["decision"] = r["decision"].with_review_state(dt.date.today()).for_model()
            hits.append(hit)
        return hits

    def fits(hits: list[dict[str, Any]]) -> bool:
        # 200: room for the mode and warnings around the hits.
        return len(json.dumps(hits, ensure_ascii=False, default=str)) + 200 <= MAX_TOOL_CHARS

    for limit in PASSAGE_SIZES:
        hits = build(limit, results)
        if fits(hits):
            return hits
    while hits and not fits(hits):
        hits = hits[:-1]
    return hits


def _search_vault(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    vault = _require_vault(ctx)
    k = max(1, min(int(args.get("k") or 4), 8))
    result = vault.index.search(str(args.get("query", "")), k=k, folder=args.get("folder") or None)
    hits = _fit_hits(result["results"])
    result["results"] = result["results"][: len(hits)]
    citations = [Citation(**r["citation"]) for r in result["results"]]
    content = {"mode": result["mode"], "results": hits, "warnings": result["warnings"]}
    cards = [
        _artifact(ctx, "citation", f"{c.path} > {c.heading}", {"snippet": r["snippet"]}, citations=[c])
        for c, r in zip(citations, result["results"], strict=True)
    ]
    # A figure quoted from a returned passage is backed by that passage's citation.
    quoted = [f.value for h in hits for f in extract_figures(json.dumps(h, ensure_ascii=False))]
    return ToolOutcome(content, artifacts=cards, citations=citations, numbers=quoted)


def _past_decisions(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    vault = _require_vault(ctx)
    records = vault.index.past_decisions(str(args.get("query", "")))
    rows = [r.for_model() for r in records]
    citations = [Citation(path=r.path, heading=r.title, chunk_id=f"{r.path}#decision") for r in records]
    cards = [
        _artifact(ctx, "citation", f"Past decision: {r.title}", row, citations=[c])
        for r, row, c in zip(records, rows, citations, strict=True)
    ]
    quoted = [f.value for row in rows for f in extract_figures(json.dumps(row, ensure_ascii=False))]
    return ToolOutcome({"decisions": rows}, artifacts=cards, citations=citations, numbers=quoted)


def _read_note(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    vault = _require_vault(ctx)
    note = vault.vault.read_note(str(args.get("path", "")))
    citation = Citation(path=note["path"], heading=note.get("title") or note["path"], chunk_id=f"{note['path']}#note")
    frontmatter = note.get("frontmatter") or {}
    content = {
        "path": note["path"],
        "title": note.get("title"),
        "frontmatter": frontmatter,
        "body": str(note.get("body", ""))[:4000],
    }
    quoted = [f.value for f in extract_figures(f"{json.dumps(frontmatter, ensure_ascii=False)}\n{content['body']}")]
    return ToolOutcome(content, citations=[citation], numbers=quoted)


def _write_note(ctx: ToolContext, args: dict[str, Any]) -> ToolOutcome:
    vault = _require_vault(ctx)
    path = str(args.get("path", "")).strip().lstrip("/")
    if not path.startswith(WRITABLE_FOLDERS):
        return ToolOutcome({}, error=f"agents may only write under {' or '.join(WRITABLE_FOLDERS)}")
    written = vault.vault.write_note(path, str(args.get("content", "")))
    vault.apply_changes({written})
    return ToolOutcome({"written": written})


def _spec(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> ToolSpec:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return ToolSpec(name=name, description=description, parameters=schema)


def _model_params(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    return {k: v for k, v in schema.items() if k in ("type", "properties", "required", "$defs")}


_MONTH = {
    "type": "string",
    "description": "As-of month YYYY-MM. Leave out for the latest month; set only when the founder names a month.",
}
_ADJ = {
    name: {"type": "number", "description": str(f.description or name)}
    for name, f in Adjustments.model_fields.items()
    if name not in ("growth_mode", "start_month", "cost_per_hire_monthly")
}
_ADJ["growth_mode"] = {"type": "string", "enum": ["trend", "none", "flat"], "description": "Growth assumption"}

TOOLS: dict[str, Tool] = {
    t.spec.name: t
    for t in (
        Tool(_spec("list_metrics", "List the metric routines that get_metric can run.", {}), _list_metrics),
        Tool(
            _spec(
                "get_metric",
                "Compute one financial metric from the company's data. Returns the value, unit and lineage. "
                "'runway' is Runway (actual burn).",
                {
                    "name": {"type": "string", "enum": sorted(METRICS)},
                    "month": _MONTH,
                    "window": {"type": "integer", "description": "Trailing months (default per metric)"},
                },
                ["name"],
            ),
            _get_metric,
        ),
        Tool(
            _spec(
                "metrics_summary",
                "Headline metrics (MRR, ARR, burn, runway, margin, growth, CAC, LTV:CAC).",
                {"month": _MONTH},
            ),
            _metrics_summary,
        ),
        Tool(
            _spec(
                "run_scenario",
                "What-if projection: base vs scenario cash and projected runway (with growth assumptions).",
                {**_ADJ, "horizon": {"type": "integer", "description": "Months to project (1-36, default 12)"}},
            ),
            _run_scenario,
        ),
        Tool(
            _spec(
                "run_monte_carlo",
                "Seeded Monte Carlo over churn, price and acquisition uncertainty: runway P10/P50/P90 and "
                "the probability that cash runs out within 12 months.",
                {**_ADJ, "runs": {"type": "integer", "description": "Number of runs (default 1000)"}},
            ),
            _run_monte_carlo,
        ),
        Tool(
            _spec(
                "run_sql",
                "One read-only SELECT over the tables pnl, bank_balance, customers, subscriptions, pipeline, "
                "marketing_spend, headcount. Use only when no metric routine fits.",
                {"sql": {"type": "string"}},
                ["sql"],
            ),
            _run_sql,
        ),
        Tool(
            ToolSpec(
                name="weighted_scoring",
                description="Weighted scoring of options against criteria (priority matrix).",
                parameters=_model_params(ScoringRequest),
            ),
            _weighted_scoring,
        ),
        Tool(
            _spec(
                "expected_value",
                "Expected value, spread and probability of loss for options with probabilistic outcomes.",
                {"options": {"type": "array", "items": _model_params(EVOption)}},
                ["options"],
            ),
            _expected_value,
        ),
        Tool(_spec("calibration_scores", "Brier scores of past predictions per owner.", {}), _calibration_scores),
        Tool(
            _spec(
                "search_vault",
                "Hybrid search over the founder's notes, decisions, journal and documents. Returns passages "
                "with their source path and heading.",
                {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "description": "Number of passages (default 4)"},
                    "folder": {"type": "string", "description": "Limit to a folder, e.g. decisions"},
                },
                ["query"],
            ),
            _search_vault,
            status="searching_vault",
        ),
        Tool(
            _spec(
                "past_decisions",
                "Decisions already on record on a topic, with status, decision date, review date, prediction and "
                "kill criteria.",
                {"query": {"type": "string", "description": "The topic or question"}},
                ["query"],
            ),
            _past_decisions,
            status="searching_vault",
            model_callable=False,
        ),
        Tool(
            _spec(
                "read_note",
                "Read one vault note (frontmatter and body) by its path.",
                {"path": {"type": "string"}},
                ["path"],
            ),
            _read_note,
            status="searching_vault",
        ),
        Tool(
            _spec(
                "write_note",
                "Write a Markdown note under decisions/ or journal/.",
                {"path": {"type": "string"}, "content": {"type": "string"}},
                ["path", "content"],
            ),
            _write_note,
            status="searching_vault",
        ),
    )
}

EXPECTED_ERRORS = (
    MetricError,
    NoDataError,
    SqlGuardError,
    VaultError,
    ValidationError,
    ValueError,
    KeyError,
    TypeError,
)


async def run_tool(name: str, ctx: ToolContext, args: dict[str, Any], allowed: tuple[str, ...]) -> ToolOutcome:
    """Run an allow-listed tool in a worker thread (DuckDB and the vault are synchronous). Never raises."""
    if name not in allowed or name not in TOOLS:
        return ToolOutcome({}, error=f"tool {name!r} is not available to this agent; use one of {', '.join(allowed)}")
    try:
        return await asyncio.to_thread(TOOLS[name].handler, ctx, args)
    except EXPECTED_ERRORS as exc:
        return ToolOutcome({}, error=f"{type(exc).__name__}: {exc}"[:800])
    except Exception as exc:  # a tool bug must not kill the run; it is reported to the model and logged
        from loguru import logger

        logger.exception("Tool {} failed", name)
        return ToolOutcome({}, error=f"tool failed ({type(exc).__name__}: {exc})"[:800])


def specs_for(allowed: tuple[str, ...]) -> list[ToolSpec]:
    return [TOOLS[name].spec for name in allowed if name in TOOLS and TOOLS[name].model_callable]
