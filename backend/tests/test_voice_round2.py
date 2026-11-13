"""M5 founder review (2026-11-13): the spoken mid-run question that was lost (V7), and how the Advisor speaks (A to E).

WAV fixtures in, fake STT and TTS, no GPU, microphone or network. `churn.wav` is Kokoro speech at 16 kHz like the
other fixtures, so the endpointer sees a real speech envelope.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.events import EventBus
from app.agents.graph import _DOUBLE_STOP, AgentOrchestrator
from app.agents.tools import ToolContext
from app.conversation.contexts import Turn, conversation_block
from app.conversation.manager import ConversationManager
from app.decision.base import DecisionService, FakeDecisionProvider
from app.engine.calibration import CalibrationStore
from app.engine.duckdb_engine import FinanceDB
from app.engine.metrics import MetricsEngine
from app.engine.scenario import ScenarioEngine
from app.llm.fake import FakeProvider
from app.llm.router import LLMRouter
from app.voice.audio import FRAME
from app.voice.session import ACK_METRIC, MISSED, QUEUE_OFFER
from app.voice.spoken import (
    cash_risk_line,
    metric_lead,
    produced_line,
    say_date,
    say_money,
    say_months,
    say_percent,
    spoken_text,
    summarise,
    team_line,
)
from app.voice.tts import for_speech
from tests.test_specialists import slow_provider
from tests.test_voice import make, stream, wav_bytes

DUBAI = "Should we open a Dubai office?"
EXACT_FIGURE = re.compile(r"\$|\d+\.\d{2}\b|\d,\d{3}")  # "$3,000.00", "10.65", "1,000": on screen, never spoken


@pytest.fixture
def finance(loaded_db: FinanceDB, tmp_path: Path) -> Any:
    return SimpleNamespace(
        db=loaded_db,
        metrics=MetricsEngine(loaded_db),
        scenario=ScenarioEngine(loaded_db),
        calibration=CalibrationStore(tmp_path / "cal"),
    )


async def wait_for(condition: Any, seconds: float = 30.0) -> None:
    for _ in range(int(seconds * 100)):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


def lane(finance: Any, provider: Any = None, **options: Any) -> ConversationManager:
    orch = AgentOrchestrator(
        LLMRouter(provider or FakeProvider(default=lambda m, t, s: "What would you cut first?")),
        DecisionService(FakeDecisionProvider()),
        EventBus(),
        lambda aid: ToolContext(finance, None, aid),
        approval_policy="never",
        approval_timeout_s=5,
        **options,
    )
    return ConversationManager(orch)


async def finished(manager: ConversationManager, run_id: str | None) -> Any:
    assert run_id is not None
    result = await manager.orchestrator.runs[run_id].task  # type: ignore[misc]
    await asyncio.sleep(0.05)  # the lane's narrator sees run.finished
    return result


# --- B: spoken numbers, by code --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("value", "currency", "said"),
    [
        (10_234.50, "USD", "around 10 thousand dollars"),
        (1_835_125.06, "USD", "about 1.8 million dollars"),
        (172_280.47, "USD", "around 170 thousand dollars"),
        (3_000, "USD", "3 thousand dollars"),  # already round: no "around"
        (87.5, "USD", "around 88 dollars"),
        (-11_923.62, "USD", "minus around 12 thousand dollars"),
        (2_400_000_000, "EUR", "2.4 billion euros"),
        (1_250_000, "INR", "12.5 lakh rupees"),
        (23_500_000, "INR", "about 2.4 crore rupees"),
        (45_000, "INR", "45 thousand rupees"),
    ],
)
def test_money_is_said_rounded(value: float, currency: str, said: str) -> None:
    assert say_money(value, currency) == said


@pytest.mark.parametrize(
    ("value", "said"),
    [
        (10.65, "about ten and a half months"),
        (2.07, "about two months"),
        (0.21, "about a week"),
        (1.0, "a month"),
        (24, "twenty-four months"),
        (0.05, "a few days"),
    ],
)
def test_months_are_said_in_words(value: float, said: str) -> None:
    assert say_months(value) == said


def test_percent_is_a_fraction_only_for_a_share() -> None:
    assert say_percent(81, share=True) == "about four in five"
    assert say_percent(50, share=True) == "half"
    assert say_percent(72.13) == "about 72 percent" and say_percent(72.13, share=True) == "about 72 percent"
    assert say_percent(1.5) == "1.5 percent"  # a rate keeps its decimal
    assert say_percent(10) == "10 percent"  # a price change of 10 % is never "one in ten"


def test_dates_are_said_as_dates() -> None:
    assert say_date("2027-09") == "September 2027"
    assert say_date("2026-12-08") == "the 8th of December 2026"
    assert say_date("soon") == "soon"


def test_a_sentence_keeps_its_words_and_changes_only_its_numbers() -> None:
    assert spoken_text(
        "Runway (actual burn) is 10.65 months as of October 2026: closing cash is $1,835,125.06, with a net burn of "
        "$172,280.47 per month, so cash reaches zero in September 2027."
    ) == (
        "Runway (actual burn) is about ten and a half months as of October 2026: closing cash is about 1.8 million "
        "dollars, with a net burn of around 170 thousand dollars per month, so cash reaches zero in September 2027."
    )
    assert spoken_text("moving projected runway from 11.23 to 9.16 months (-2.07); all assumptions.") == (
        "moving projected runway from about eleven months to about nine months; all assumptions."
    )
    assert spoken_text("in 81 % of 1,000 simulated futures") == "in about four in five of a thousand simulated futures"
    assert spoken_text("Revenue is ₹12,50,000; review on 2026-12-08 [notes/plan.md].") == (
        "Revenue is 12.5 lakh rupees; review on the 8th of December 2026."
    )
    assert spoken_text("It raised $1.8m in 2025.") == "It raised 1.8 million dollars in 2025."  # a year stays a year
    assert not EXACT_FIGURE.search(spoken_text("Costs are 45,000.00 INR and $30,000.00 up front, runway -0.21 months."))


def test_a_metric_is_led_by_its_rounded_figure() -> None:
    assert (
        metric_lead("Runway (actual burn)", 10.65, "months", "runway") == "Your runway is about ten and a half months."
    )
    assert metric_lead("Net burn (monthly)", 172_280.47, "USD", "net_burn") == (
        "Your net burn is around 170 thousand dollars a month."
    )
    assert metric_lead("Gross margin", 0.7213, "ratio", "gross_margin") == "Your gross margin is about 72 percent."
    assert metric_lead("MRR", 412_345.0, "USD", "mrr") == "Your MRR is around 410 thousand dollars."
    assert metric_lead("Runway (actual burn)", None, "months") == "I can't work out your runway from the data."
    assert cash_risk_line(0.81) == (
        "One warning: in about four in five of the simulated futures, cash runs out within a year."
    )


# --- A and B: the team, once; one line a stage -----------------------------------------------------------------------
TEAM = [
    {"type": "financial_analyst", "name": "Financial Analyst"},
    {"type": "librarian", "name": "Librarian"},
    {"type": "market_scout", "name": "Market Scout"},
    {"type": "regulatory_tax", "name": "Regulatory & Tax"},
    {"type": "devils_advocate", "name": "Devil's Advocate"},
]


def test_the_team_is_said_in_one_or_two_sentences() -> None:
    line = team_line(TEAM)
    assert line.startswith("Five on this: the Financial Analyst on the numbers, the Librarian on your notes")
    assert "the Devil's Advocate on what could go wrong." in line and "&" not in line
    assert len(re.findall(r"[.!?](?:\s|$)", line)) == 2
    assert len(re.findall(r"[.!?](?:\s|$)", team_line(TEAM[:3]))) == 1
    assert team_line(TEAM[:1]) == ""  # a one-agent lookup has no team to describe


def test_a_stage_gets_one_line_on_what_was_produced_and_no_figure() -> None:
    wave = [{**m, "status": "done", "verified": True} for m in TEAM[:3]]
    assert produced_line(wave) == (
        "The Financial Analyst has priced it, the Librarian has checked your notes and the Market Scout has looked "
        "at the market."
    )
    doubt = [{**TEAM[3], "status": "done", "verified": False}, {**TEAM[4], "status": "cancelled", "verified": False}]
    assert produced_line(doubt) == (
        "The Regulatory and Tax adviser has flagged the regulatory points. The Devil's Advocate did not finish. "
        "Part of that is unverified."
    )


# --- C: a summary and an offer, never the text card ------------------------------------------------------------------
async def test_a_decision_is_summarised_with_the_outcome_what_matters_and_an_offer(finance: Any) -> None:
    manager = lane(finance, cash_risk_warn_at=0.0)
    result = await finished(manager, (await manager.turn(None, DUBAI)).run_id)
    spoken = summarise(result)
    proposed = result.decision_frame.default_option
    assert spoken.lead[0].startswith(f"My proposal is {proposed}: ") and "a month" in spoken.lead[0]
    assert spoken.lead[1].startswith("One warning: in about ") and "cash runs out within a year" in spoken.lead[1]
    assert 2 <= len(spoken.lead) <= 3
    assert not any(EXACT_FIGURE.search(line) for line in spoken.lead)
    assert [s.key for s in spoken.more][-1] == "options" and spoken.more[0].offer.endswith("?")
    assert all(len(s.lines) <= 3 for s in spoken.more)
    # Not the on-screen text: no spoken line is a sentence of the answer card.
    assert not any(line in result.answer for line in spoken.lead)


async def test_a_metric_is_summarised_from_the_routines_figure(finance: Any) -> None:
    manager = lane(finance)
    result = await finished(manager, (await manager.turn(None, "What is our runway?")).run_id)
    spoken = summarise(result)
    assert spoken.lead == ["Your runway is about ten and a half months."]
    assert spoken.more[0].key == "detail" and "about 1.8 million dollars" in spoken.more[0].lines[0]


async def test_voice_says_the_team_a_line_a_stage_and_a_short_summary(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never")
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    run_id = wire.of("turn")[0]["outcome"]["run_id"]
    result = await finished(manager, run_id)
    await wait_for(lambda: any(m["text"].startswith("Want") for m in wire.of("say")))
    says = wire.of("say")
    talk = [m["text"] for m in says if m["lane"] == "conversation"]
    answer = [m["text"] for m in says if m["lane"] == "answer"]
    assert talk[0] == "On it."
    assert sum(" on this: " in t for t in talk) == 1  # A: who is on the team, said once
    assert any("has priced it" in t for t in talk)  # B: what a stage produced, not what it found
    assert not any("assumption would change" in t or "to go" in t for t in talk)  # no commentary on every step
    assert answer[0].startswith("My proposal is ") and answer[-1].startswith("Want")
    assert len(answer) <= 4  # C: two or three sentences, then the offer
    spoken = " ".join(m["text"] for m in says)
    assert not EXACT_FIGURE.search(spoken), spoken  # B: exact figures stay on screen
    assert not any(a in result.answer for a in answer)  # never the on-screen answer read aloud
    # "Yes": the next part, short, and then the next offer or the close.
    before = len(wire.of("say"))
    await session.control({"type": "text", "text": "Yes, go through the risks."})
    await wait_for(lambda: len(wire.of("say")) > before + 1)
    await asyncio.sleep(0.2)
    more = [m["text"] for m in wire.of("say")[before:]]
    assert 2 <= len(more) <= 4 and (more[-1].startswith("Want") or more[-1].startswith("That's the summary"))
    assert len(wire.of("turn")) == 1  # an answer to the offer, not a new question
    await session.close()


async def test_voice_metric_answer_is_a_summary_and_the_detail_is_on_offer(finance: Any) -> None:
    session, wire, *_ = make(finance, [])
    await session.start()
    await session.control({"type": "text", "text": "What is our runway?"})
    await wait_for(lambda: any(m["text"] == "Want the detail?" for m in wire.of("say")))
    says = [(m["lane"], m["text"]) for m in wire.of("say")]
    assert says == [
        ("conversation", ACK_METRIC),
        ("answer", "Your runway is about ten and a half months."),
        ("answer", "Want the detail?"),
    ]
    await session.control({"type": "text", "text": "no thanks"})
    await wait_for(lambda: wire.of("say")[-1]["text"] == "Okay. The rest is on screen.")
    assert session.offers.more == []
    await session.close()


# --- V7: a question spoken over narration ----------------------------------------------------------------------------
async def test_a_question_spoken_over_narration_is_queued_shown_and_offered(finance: Any) -> None:
    provider = slow_provider()
    session, wire, _, _tts, manager = make(
        finance, [DUBAI, "What is our churn?"], provider=provider, mode="duplex", approval_policy="never"
    )

    def said() -> list[str]:
        return [m["text"] for m in wire.of("say")]

    await session.start()
    await stream(session, wav_bytes("dubai"))
    await wait_for(lambda: bool(wire.of("turn")))
    dubai_run = wire.of("turn")[0]["outcome"]["run_id"]
    await wait_for(lambda: bool(manager.orchestrator.runs[dubai_run].agent_tasks))  # the team is working
    session.speaking_until = session.clock() + 30  # FounderOS is narrating
    await stream(session, wav_bytes("churn"))
    await wait_for(lambda: len(wire.of("turn")) == 2)
    kinds = [m["type"] for m in wire.messages if m["type"] in ("pause", "interrupt", "resume")]
    assert kinds[:2] == ["pause", "interrupt"] and "resume" not in kinds  # it stopped talking over the founder
    assert wire.of("transcript")[1]["text"] == "What is our churn?"  # shown as the founder's turn
    outcome = wire.of("turn")[1]["outcome"]
    assert outcome["kind"] == "new_question" and outcome["queue_id"] and outcome["run_id"] == dubai_run
    await wait_for(lambda: "I'll keep that for when this run finishes." in said())  # and said to be queued
    assert [e.type for e in manager.bus.history() if e.type.startswith("queue.")] == ["queue.added"]
    provider.release.set()
    await finished(manager, dubai_run)
    await wait_for(lambda: QUEUE_OFFER in said())
    await asyncio.sleep(0.2)
    assert said().index(QUEUE_OFFER) == len(said()) - 1  # after the summary, and no second question beside it
    assert session.offers.queue_id == outcome["queue_id"]
    await session.control({"type": "text", "text": "Ask it."})
    await wait_for(lambda: any(m["text"].startswith("Your logo churn is ") for m in wire.of("say")))
    assert session.metrics.turns[-1].kind == "queue_asked"
    await session.close()


async def test_an_old_verdict_never_resumes_playback_over_newer_speech(finance: Any) -> None:
    """The cause of V7: a noise paused the narration, and its "backchannel" verdict arrived while the founder was
    already asking the next question, so the narration resumed over them and the question was lost."""
    session, wire, stt, *_ = make(finance, ["Uh-huh.", "What is our churn?"], mode="duplex", barge_in_ms=3000)
    stt.delay_s = 0.4  # the first verdict is still being worked out when the question is spoken
    await session.start()
    session.speaking_until = session.clock() + 30
    await stream(session, wav_bytes("uh_huh"))
    await stream(session, wav_bytes("churn"))
    await wait_for(lambda: bool(wire.of("turn")))
    assert not wire.of("resume")
    assert [m["text"] for m in wire.of("transcript")] == ["Uh-huh.", "What is our churn?"]
    assert wire.of("interrupt") and session.metrics.turns[-1].text == "What is our churn?"
    await session.close()


async def test_nothing_new_is_played_while_the_founder_is_speaking(finance: Any) -> None:
    session, wire, *_ = make(finance, ["What is our churn?"], mode="duplex")
    await session.start()
    data = wav_bytes("churn")
    half = (len(data) // 2) // (FRAME * 2) * (FRAME * 2)
    await stream(session, data[:half])  # mid-question
    assert session.endpointer.in_speech
    await session._say("conversation", "The team is ready.", None, None)
    await asyncio.sleep(0.2)
    assert not wire.of("say") and not wire.audio  # it waits for the founder to finish
    await stream(session, data[half:])
    await wait_for(lambda: any(m["text"] == "The team is ready." for m in wire.of("say")))
    said = [m["text"] for m in wire.of("say")]
    assert said.index(ACK_METRIC) < said.index("The team is ready.")  # the reply to the founder comes first
    await session.close()


async def test_speech_that_cannot_be_made_out_is_not_lost_in_silence(finance: Any) -> None:
    session, wire, *_ = make(finance, [""], mode="duplex")
    await session.start()
    await stream(session, wav_bytes("churn"))
    await wait_for(lambda: any(m["text"] == MISSED for m in wire.of("say")))
    assert wire.of("missed") and not wire.of("turn")
    await stream(session, wav_bytes("churn"))  # a second time in a row it does not nag
    await wait_for(lambda: len(wire.of("transcript")) == 2)
    await asyncio.sleep(0.3)
    assert [m["text"] for m in wire.of("say")].count(MISSED) == 1
    await session.close()


async def test_a_cancelled_run_is_still_said_to_be_cancelled(finance: Any) -> None:
    provider = slow_provider()
    session, wire, *_ = make(finance, [], provider=provider, approval_policy="never")
    await session.start()
    await session.control({"type": "text", "text": "Should we expand the team this year?"})
    await wait_for(lambda: bool(wire.of("turn")))
    await session.control({"type": "text", "text": "stop"})
    await wait_for(lambda: len(wire.of("turn")) == 2)
    await wait_for(lambda: wire.of("interrupt") and wire.of("turn")[1]["outcome"]["reply"] == "Stopping the team.")
    provider.release.set()
    await session.close()


# --- D: follow-ups in context ----------------------------------------------------------------------------------------
async def test_and_what_about_a_metric_is_answered_as_that_metric(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, "What is our runway?")
    await finished(manager, first.run_id)
    follow = await manager.turn(first.session_id, "and what about churn?")
    result = await finished(manager, follow.run_id)
    assert follow.started_run and result.message == "What is our churn?"
    assert [m.metric for m in result.metrics] == ["logo_churn"] and result.verification.state == "verified"
    assert manager._in_context("And what about hiring a designer?") == "And what about hiring a designer?"


async def test_why_that_option_is_answered_from_the_open_decision(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    result = await finished(manager, first.run_id)
    why = await manager.turn(first.session_id, "Why that option?")
    assert why.kind == "answerable_now" and why.run_id == first.run_id and not why.started_run
    assert why.reply.startswith(f"I proposed {result.decision_frame.default_option} because ")
    assert not EXACT_FIGURE.search(why.reply)  # the lane states no figure
    # With no decision open, the same words are an ordinary question.
    fresh = await manager.turn(None, "Why that option?")
    assert fresh.started_run
    await finished(manager, fresh.run_id)


async def test_the_advisor_is_given_what_was_asked_and_answered_before(finance: Any) -> None:
    seen: list[str] = []

    def respond(messages: list[Any], tools: Any, schema: Any) -> str:
        seen.append("\n".join(str(m.content) for m in messages))
        return "What would you cut first?"

    manager = lane(finance, FakeProvider(default=respond))
    first = await manager.turn(None, DUBAI)
    answer = (await finished(manager, first.run_id)).answer
    seen.clear()
    second = await manager.turn(first.session_id, "Is the timing right for us?")
    await finished(manager, second.run_id)
    advisor = next(text for text in seen if "Earlier in this conversation" in text)
    assert f"- Founder: {DUBAI}" in advisor and f"- You answered: {answer[:40]}" in advisor
    assert "Take figures only from the team findings." in advisor


def test_the_conversation_block_holds_questions_and_answers_only() -> None:
    turns = (
        Turn(role="founder", text="Should we open a Dubai office?"),
        Turn(role="lane", text="Team: Financial Analyst, Librarian."),
        Turn(role="advisor", text="Proposed: Travel-led pilot."),
        Turn(role="founder", text="Why that option?"),
    )
    assert conversation_block(turns) == (
        "- Founder: Should we open a Dubai office?\n- You answered: Proposed: Travel-led pilot."
    )
    assert conversation_block(turns[:1]) == ""  # nothing answered yet: no block


# --- E: re-run an agent by voice -------------------------------------------------------------------------------------
async def test_rerun_restarts_a_working_agent_with_the_change(finance: Any) -> None:
    provider = slow_provider()
    manager = lane(finance, provider)
    first = await manager.turn(None, "Should we expand the team this year?")
    run = manager.orchestrator.runs[first.run_id or ""]
    await wait_for(lambda: len(run.agent_tasks) == 2)
    outcome = await manager.turn(first.session_id, "Re-run the analyst, assume three hires.")
    assert outcome.reply == "Re-running the Financial Analyst with your change." and outcome.run_id == run.run_id
    assert not outcome.started_run and not manager.sessions[first.session_id].queue
    await wait_for(lambda: any(e.type == "agent.rerun" for e in manager.bus.history(run.run_id)))
    missing = await manager.turn(first.session_id, "redo the Devil's Advocate")
    assert missing.reply == "The Devil's Advocate is not on this team."
    provider.release.set()
    await finished(manager, run.run_id)


async def test_rerun_after_the_answer_runs_the_same_team_with_the_new_brief(finance: Any) -> None:
    manager = lane(finance)
    first = await manager.turn(None, DUBAI)
    old = await finished(manager, first.run_id)
    again = await manager.turn(first.session_id, "Re-run the analyst, assume three hires")
    assert again.started_run and again.run_id != first.run_id
    assert again.reply == "Running it again with your change, the Financial Analyst first."
    new_run = manager.orchestrator.runs[again.run_id or ""]
    assert new_run.message == f"{DUBAI}\nThe founder then added: assume three hires"
    assert new_run.context.amendment_of == first.run_id  # the amendment path: the run it replaces is on record
    new = await finished(manager, again.run_id)
    assert [a.type for a in new.team] == [a.type for a in old.team]
    analyst = next(a for a in new.team if a.type == "financial_analyst")
    assert analyst.brief.endswith("The founder then added: assume three hires")
    redo = await manager.turn(first.session_id, f"Redo the Devil{chr(0x2019)}s Advocate.")  # a typeset apostrophe
    assert redo.started_run and redo.reply == "Running it again, with the Devil's Advocate redoing its part."
    assert manager.orchestrator.runs[redo.run_id or ""].message == new_run.message  # no change: the same request
    await finished(manager, redo.run_id)


async def test_a_rerun_request_that_names_no_agent_is_an_ordinary_turn(finance: Any) -> None:
    manager = lane(finance)
    assert manager._rerun(manager.session("s1"), "Redo the forecast for next year") is None
    assert manager._rerun(manager.session("s1"), "What is our runway?") is None
    nothing = manager._rerun(manager.session("s1"), "re-run the analyst")
    assert nothing is not None and nothing.reply == "There is no team to re-run yet. Ask me something first."


async def test_voice_rerun_is_acknowledged_and_its_outcome_is_summarised(finance: Any) -> None:
    session, wire, _, _tts, manager = make(finance, [], approval_policy="never")
    await session.start()
    await session.control({"type": "text", "text": DUBAI})
    await wait_for(lambda: bool(wire.of("turn")))
    await finished(manager, wire.of("turn")[0]["outcome"]["run_id"])
    await wait_for(lambda: any(m["text"].startswith("Want") for m in wire.of("say")))
    before = len(wire.of("say"))
    await session.control({"type": "text", "text": "Redo the Devil's Advocate."})
    await wait_for(lambda: len(wire.of("turn")) == 2)
    await finished(manager, wire.of("turn")[1]["outcome"]["run_id"])
    await wait_for(lambda: sum(m["text"].startswith("My proposal is ") for m in wire.of("say")) == 2)
    after = [m["text"] for m in wire.of("say")[before:]]
    assert after[0] == "Running it again, with the Devil's Advocate redoing its part."
    assert any("has listed the risks" in t for t in after)  # then the Advisor carries on as before
    await session.close()


# --- the double full stop --------------------------------------------------------------------------------------------
def test_an_answer_never_ends_a_sentence_twice() -> None:
    assert _DOUBLE_STOP.sub(".", "so protecting runway comes first..") == "so protecting runway comes first."
    assert _DOUBLE_STOP.sub(".", "It depends... on timing.") == "It depends... on timing."
    assert for_speech("Regulatory & Tax is done.") == "Regulatory and Tax is done."


async def test_the_cash_warning_ends_with_one_full_stop(finance: Any) -> None:
    manager = lane(finance, cash_risk_warn_at=0.0)
    result = await finished(manager, (await manager.turn(None, "What is our runway?")).run_id)
    assert result.answer.endswith("comes first.") and ".." not in result.answer
