"""Eval of decision quality: is the reasoning in a decision memo trustworthy, for every type of decision?

Each case goes through the whole graph, and the same rubric reads the reply and the memo.

Offline (pytest and `scripts/eval_agents.py`), over the sample data:
- `rules`: the LLM is down, so everything comes from code and templates.
- `sloppy`: a fake LLM makes every mistake seen on the founder's PC. It calls an office "1 hire", reports a goal as a
  decision, writes its own memo, chooses an option that is not on the list, forecasts tasks, invents a figure, cites a
  note that does not exist, builds a risk on that and asks about it in the reply. Code must still deliver a memo that
  passes.

Live (`scripts/eval_agents.py --live`): the same rubric on the real model's reply. Model output varies, so a failure
there is a prompt to read the answer.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.decision_frame import names_goal
from app.agents.events import EventBus
from app.agents.graph import AgentOrchestrator, ChatResult
from app.agents.sources import citation_inside_the_sentence, cited_sources
from app.agents.specialists import _OUTCOME_COMPARE
from app.agents.tools import ToolContext
from app.agents.verifier import extract_figures, number_supported, split_sentences
from app.decision.base import DecisionService, FakeDecisionProvider
from app.evals.vault_eval import make_sample_vault, sample_finance
from app.llm.base import LLMUnavailable
from app.llm.fake import FakeProvider, schema_example
from app.llm.router import LLMRouter

QUESTIONS_PATH = Path(__file__).with_name("decision_questions.json")
INVENTED = "73,219"
FABRICATED = "150 billion"  # seen live in C4, with [notes/economic-overview.md], a note that does not exist
FABRICATED_NOTE = "notes/economic-overview.md"
_DATE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
_COMPARE = re.compile(r"(>=|<=|>|<)\s*\$?\d|\d")
_NOT_YOU = re.compile(r"\b(?:we|We|us|our|Our)\b")
_CONTRADICTS = re.compile(r"\baligns? with\b[^.\n]*\bgoal|\bassumptions are confirmed\b", re.I)
_ALIGNS = re.compile(
    r"\b(?:aligns?|aligned|in line|supports?|within reach|on track)\b[^.\n]*\bgoal|\bgoal\b[^.\n]*\bwithin reach", re.I
)
_DECIDED_TO_DECIDE = re.compile(r"\bdecided to [\"\u201c']?decide\b", re.I)
_THIRD_PERSON = re.compile(r"\bthe founder\b|\blegal team\b|\btax team\b", re.I)
_ONE_HIRE = re.compile(r"\b(1|one|a single) hire\b|not a quote for this role|\bper hire\b", re.I)
_GOAL_AS_DECISION = re.compile(r"\b(you|founder|company) (has|have|had)( already)? (decided|committed)\b", re.I)
_CODE_SAYS_NOT = re.compile(r"says you have decided")
_TASK = re.compile(r"\b(research|report|study|plan)\b[^.\n]*\b(done|complete|completed|finished)\b", re.I)
_PAYROLL_TOTAL = "308,437.67"


@dataclass(frozen=True)
class DecisionCase:
    id: str
    question: str
    type: str
    components: list[str]
    goal_moves_away: list[str] = field(default_factory=list)
    assumes: bool = True


@dataclass
class DecisionEvalResult:
    id: str
    mode: str
    problems: list[str]

    @property
    def passed(self) -> bool:
        return not self.problems

    def line(self) -> str:
        verdict = "PASS" if self.passed else "FAIL: " + "; ".join(self.problems)
        return f"decision:{self.id:<16} {self.mode:<9} {verdict}"


def load_cases(path: Path = QUESTIONS_PATH) -> list[DecisionCase]:
    return [DecisionCase(**case) for case in json.loads(path.read_text(encoding="utf-8"))]


def _section(memo: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", memo)
    return match.group(1).strip() if match else ""


def _bullets(text: str) -> list[str]:
    return [line[2:].strip() for line in text.splitlines() if line.startswith("- ")]


def _without_goals(text: str, goals: list[str]) -> str:
    for goal in goals:
        text = re.sub(re.escape(goal), "the goal", text, flags=re.I)
    return re.sub(r"\bnot\b[^.\n]{0,25}\b(?:align|support)\w*", " ", text, flags=re.I)


def _gives_back(reply: dict[str, Any], chosen: str) -> bool:
    options = (reply.get("decision_frame") or {}).get("options", [])
    change = next((o.get("runway_change_months") for o in options if o.get("name") == chosen), None)
    return change is not None and change >= 0


def _measurable(line: str, today: dt.date) -> bool:
    dates = _DATE.findall(line)
    future = any(dt.date.fromisoformat(d) > today for d in dates)
    without = _DATE.sub(" ", line)
    return future and _OUTCOME_COMPARE.search(without) is not None and re.search(r"\d", without) is not None


def _data_files(reply: dict[str, Any]) -> str:
    """Where the routines' numbers came from. Those files are real, though they are not in the vault."""
    lineages = [a.get("lineage") for a in reply.get("artifacts", [])]
    return json.dumps([reply.get("metrics"), reply.get("decision_frame"), lineages], default=str)


def _shown_figures(reply: dict[str, Any], memo: str) -> list[float]:
    """Every figure the run's own records hold. A figure in the answer that is in none of them came from nowhere."""
    records = json.dumps(
        [reply.get("metrics"), reply.get("decision_frame"), reply.get("decision_impact"), reply.get("past_decisions")],
        default=str,
    )
    agents = " ".join(str(a.get("text", "")) for a in reply.get("agents", []))
    return [f.value for f in extract_figures(f"{records} {agents} {memo} {reply.get('message', '')}")]


def _source_problems(reply: dict[str, Any], memo: str, exists: Callable[[str], bool] | None) -> list[str]:
    """Checklist C4 on the sources: every path cited is real, and no figure stands without a backing."""
    problems: list[str] = []
    answer = str(reply.get("answer", ""))
    texts = {"answer": answer, "memo": memo}
    texts.update({str(a.get("name")): str(a.get("text", "")) for a in reply.get("agents", [])})
    data = _data_files(reply)
    pages = {str(c.get("path")) for c in reply.get("citations", [])}
    for name, text in texts.items():
        if FABRICATED in text or FABRICATED_NOTE in text:
            problems.append(f"the {name} still has the fabricated figure or note")
        for source in cited_sources(text):
            real = source in pages or source in data or (exists is not None and exists(source))
            if not real:
                problems.append(f"the {name} cites {source}, which does not exist")
    shown = _shown_figures(reply, memo)
    for sentence in split_sentences(answer):
        for figure in extract_figures(sentence):
            if not number_supported(figure, shown):
                kind = "question" if sentence.strip().endswith("?") else "sentence"
                problems.append(f"a {kind} in the answer has the unsupported figure {figure.text}")
    return problems


def _scout_problems(reply: dict[str, Any]) -> list[str]:
    """With cloud off the Market Scout says what is missing, and states nothing that has no source in the vault."""
    scout = next((a for a in reply.get("agents", []) if a.get("type") == "market_scout"), None)
    if scout is None or any(c.get("tool") == "web_search" and not c.get("error") for c in scout.get("tool_calls", [])):
        return []
    text = str(scout.get("text", ""))
    problems = [] if "o find:" in text else ["the Market Scout does not list what to find"]
    for sentence in split_sentences(citation_inside_the_sentence(text)):
        if extract_figures(sentence) and not cited_sources(sentence):
            problems.append(f"the Market Scout states a figure with no source: {sentence.strip()}")
    return problems


def check_decision(
    case: DecisionCase,
    mode: str,
    reply: dict[str, Any],
    today: dt.date | None = None,
    exists: Callable[[str], bool] | None = None,
) -> DecisionEvalResult:
    """The rubric. Everything here holds whatever the model wrote, because code guarantees it.

    `exists` says whether a path is a real vault file; without it, a path counts only if the run itself returned it.
    """
    today = today or dt.date.today()
    problems: list[str] = []
    if reply.get("decision_type") != case.type:
        problems.append(f"decision type {reply.get('decision_type')}, wanted {case.type}")
    memo_ref = reply.get("memo") or {}
    artifact = next((a for a in reply.get("artifacts", []) if a.get("kind") == "decision_memo"), None)
    if not memo_ref or artifact is None:
        return DecisionEvalResult(case.id, mode, [*problems, "no memo written"])
    memo = str(artifact["data"].get("markdown", ""))
    answer = str(reply.get("answer", ""))
    if memo_ref.get("status") != "proposed":
        problems.append(f"the memo's status is {memo_ref.get('status')}, not proposed")
    problems += _source_problems(reply, memo, exists)
    problems += _scout_problems(reply)
    # Cost components
    costs = _section(memo, "Cost model")
    problems += [f"no cost component {c!r}" for c in case.components if c.lower() not in costs.lower()]
    if case.assumes and "assumption, confirm" not in costs:
        problems.append("assumptions are not labelled")
    if not all(f"{c} case:" in costs for c in ("Low", "Base", "High")):
        problems.append("no low, base and high case")
    if case.assumes and memo_ref.get("verified"):
        problems.append("a memo resting on assumptions is shown as verified")
    # One-hire framing, in the words that carry the decision
    for name, text in (("answer", answer), ("memo", memo)):
        if _ONE_HIRE.search(text):
            problems.append(f"one-hire framing in the {name}")
    # Goals
    goals = _section(memo, "Goal check")
    if not goals or "No goals found" in goals:
        problems.append("no goal check")
    for goal in case.goal_moves_away:
        if not re.search(rf"moves you away from your goal \"{re.escape(goal)}", memo):
            problems.append(f"does not say it moves away from {goal!r}")
        if not names_goal(goal, answer):
            problems.append(f"the reply does not name the goal {goal!r}")
    before_findings = memo.split("## Team findings")[0]
    if _NOT_YOU.search(before_findings):
        problems.append("the memo says we, us or our")
    if _CONTRADICTS.search(before_findings):
        problems.append("the memo contradicts the goal check, or says assumptions were confirmed")
    moves_away = bool(case.goal_moves_away)
    chosen_gives_back = bool(reply.get("decision_frame")) and _gives_back(reply, str(memo_ref.get("chosen", "")))
    if moves_away and not chosen_gives_back:
        for name, text in (
            ("Decision", _section(memo, "Decision")),
            ("Context", _section(memo, "Context")),
            ("answer", answer),
        ):
            if _ALIGNS.search(_without_goals(text, case.goal_moves_away)):
                problems.append(f"the {name} says it helps a goal the goal check says it moves away from")
    if _DECIDED_TO_DECIDE.search(memo + " " + answer):
        problems.append("a goal to decide something is reported as decided")
    team = str(_section(memo, "Team findings"))
    if re.search(r"\byou, you\b", memo + " " + answer):
        problems.append("says 'you, you'")
    if re.search(r"\bstop\s+(?:\w+[- ]){0,2}travel\b", team, re.I) and "Travel-led pilot" in memo:
        problems.append("a finding tells you to stop what an option depends on")
    if re.search(r"\b(?:use|check|search)\s+(?:\w+\s+){0,2}vault\b[^.\n]*\bmarket\b", team, re.I):
        problems.append("a finding points at the vault for market data")
    if _GOAL_AS_DECISION.search(_CODE_SAYS_NOT.sub(" ", memo + " " + answer)):
        problems.append("reports something as already decided")
    # Options
    options = _bullets(_section(memo, "Options"))
    chosen = str(memo_ref.get("chosen", ""))
    proposed = [line for line in options if "**(proposed)**" in line]
    if len(options) < 3:
        problems.append(f"only {len(options)} options")
    if len(proposed) != 1:
        problems.append(f"{len(proposed)} proposed options, not exactly one")
    if not chosen or not (proposed and proposed[0].startswith(chosen)):
        problems.append("the proposed option is not the chosen one")
    if chosen and chosen not in _section(memo, "Decision"):
        problems.append("the Decision text does not match the chosen option")
    rejected = _bullets(_section(memo, "Rejected alternatives"))
    if any(line.startswith(f"{chosen}:") for line in rejected):
        problems.append("the chosen option is also rejected")
    if len(rejected) != len(options) - 1:
        problems.append("not every other option is rejected")
    for line in rejected:
        if "Not proposed, though" in line or line.rstrip().endswith("Not chosen for now."):
            problems.append(f"a rejected option has no reason: {line}")
    costed = [line for line in options if "$" in line or "cost not modelled" in line]
    if len(costed) != len(options):
        problems.append("an option has no cost")
    # Outcomes
    predictions = _bullets(_section(memo, "Predictions"))
    if not predictions or not all(_measurable(p, today) for p in predictions):
        problems.append(f"predictions are not outcomes: {predictions}")
    if any(_TASK.search(p) for p in predictions):
        problems.append("a prediction is a task")
    kills = _bullets(_section(memo, "Kill criteria"))
    if not kills or not all(_measurable(k, today) for k in kills):
        problems.append(f"kill criteria are not measurable: {kills}")
    # Scars, dumps and voice
    if "[figure removed" in memo:
        problems.append("the memo has a scar where a figure was")
    metrics = _section(memo, "Metrics")
    if "formula:" in metrics:
        problems.append("the Metrics section dumps a formula")
    if _PAYROLL_TOTAL in metrics:
        problems.append("the Metrics section has the payroll total")
    for name, text in (("answer", answer), ("memo", memo)):
        if _THIRD_PERSON.search(text):
            problems.append(f"third person in the {name}")
    if INVENTED in memo + answer:
        problems.append("an invented figure is in the memo or the reply")
    return DecisionEvalResult(case.id, mode, problems)


def _down(messages: list[Any], tools: Any, schema: Any) -> str:
    raise LLMUnavailable("down")


def _sloppy(messages: list[Any], tools: Any, schema: Any) -> str:
    """Every mistake seen live."""
    system = str(messages[0].content)
    if schema is not None and "chosen" in schema.get("properties", {}):
        return json.dumps(
            {
                "title": "Decision Memo: the decision",
                "chosen": "Delay until research is finished",
                "why_chosen": (
                    f"The founder has decided to expand. It costs ${INVENTED} a month. "
                    "It aligns with the goal of extending runway. It allows us to test the market."
                ),
                "context": "The founder has decided to expand into a second region. The Legal Team will check it.",
                "options": [{"name": "Open now", "note": "Too early."}, {"name": "Delay", "note": "Too slow."}],
                "assumptions": [f"Rent is ${INVENTED} a month", "Cost model assumptions are confirmed."],
                "decision": (
                    "It aligns with the goal of extending runway past 12 months without new financing. "
                    "This goal is still within reach."
                ),
                "predictions": [{"statement": "Research done in 30 days", "probability": 0.9}],
                "kill_criteria": ["It does not work"],
            }
        )
    if schema is not None:
        return json.dumps(schema_example(schema))
    if "Financial Analyst" in system:
        return "Adding 1 hire at the average loaded cost per hire of $11,423.62 a month, not a quote for this role."
    if "Librarian" in system:
        return (
            'You have already decided to "Decide whether to open a second sales region". '
            "The founder has decided to expand into a second sales region. [profile/company.md]"
        )
    if "People & Ops" in system:
        return (
            "# Decision Memo\nDecision: go ahead.\nStop hiring SDRs. Ask the Legal Team to check it. "
            "Stop non-essential travel. It depends on one person: you, the founder."
        )
    if "Regulatory" in system:
        return "Check the lease and the physical office licence with the Tax Team."
    if system.startswith("You are the Market Scout"):
        return f"Dubai's GDP is approximately ${FABRICATED} [{FABRICATED_NOTE}]. The market is growing fast."
    if "Devil's Advocate" in system:
        return (
            f"- Risk: this costs ${INVENTED} a month. Likelihood: high. Impact: high. "
            "Mitigation: use the vault for market data.\n"
            f"- Risk: the ${FABRICATED} market may not be real. Likelihood: high. Impact: high. Mitigation: verify it."
        )
    if "Advisor" in system or "advisor" in system:
        return (
            "The founder has already decided this. It aligns with your goal of extending runway. "
            "It needs the Tax Team. "
            f"Are you certain the ${FABRICATED} market size figure is verified before proceeding?"
        )
    return "The founder has already decided this. It needs the Tax Team."


async def _run_case(case: DecisionCase, mode: str, finance: Any, vault: Any) -> DecisionEvalResult:
    provider = FakeProvider(default=_sloppy if mode == "sloppy" else _down)
    orchestrator = AgentOrchestrator(
        LLMRouter(provider),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda agent_id: ToolContext(finance, vault, agent_id),
    )
    result: ChatResult = await orchestrator.start(case.question).task  # type: ignore[misc]
    return check_decision(
        case, mode, result.model_dump(mode="json"), exists=lambda path: (vault.vault.root / path).is_file()
    )


async def run_offline_async(cases: list[DecisionCase] | None = None) -> list[DecisionEvalResult]:
    results: list[DecisionEvalResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        finance = sample_finance(root / "finance")
        for mode in ("rules", "sloppy"):
            vault = make_sample_vault(root / f"vault-{mode}")
            for case in cases or load_cases():
                results.append(await _run_case(case, mode, finance, vault))
    return results


def run_offline(cases: list[DecisionCase] | None = None) -> list[DecisionEvalResult]:
    return asyncio.run(run_offline_async(cases))
