"""What code guarantees about the words of any answer, because prompts drift.

- One voice: the founder is "you", money is written one way, and it is "your adviser", not "the legal team".
- A goal, an open question or a proposal is never reported as a decision.
- A one-hire cost is never the cost of a decision that is not a hire.
- A specialist stays in its role: no memo of its own, no order to stop other work that nobody asked about.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.agents.decision_frame import DecisionFrame, names_goal
from app.agents.verifier import one_money_format, split_sentences
from app.engine.hybrid_rag import bm25_tokens
from app.vault.decisions import DecisionRecord

_VERB_FORMS = {"has": "have", "is": "are", "was": "were", "does": "do"}
_THE_FOUNDER = re.compile(r"\b(the) founder(?:(['\u2019]s)|\s+([a-z]+))?", re.I)
_BARE_FOUNDERS = re.compile(r"\b[Ff]ounder['\u2019]s\b")  # seen live: "Founder's personal involvement"
_NOT_A_VERB = frozenset({"and", "or", "as", "at", "by", "for", "from", "in", "of", "on", "to", "with", "this", "that"})
_THE_DEPARTMENT = re.compile(
    r"\b(?:(?:your|the|a|an|our)\s+)?(?:(?:legal|tax|compliance|regulatory|accounting)(?:\s*(?:and|/|&)\s*)?)+"
    r"\s*(?:team|teams|department|departments|counsel|dept)\b",
    re.I,
)


def _to_you(match: re.Match[str]) -> str:
    capital = match.group(1)[0].isupper()
    if match.group(2):
        return "Your" if capital else "your"
    word = match.group(3)
    pronoun = "You" if capital else "you"
    if word is None or word.lower() in _NOT_A_VERB:
        return f"{pronoun} {word}" if word else pronoun
    if word in _VERB_FORMS:
        return f"{pronoun} {_VERB_FORMS[word]}"
    if word.endswith("s") and not word.endswith("ss"):
        return f"{pronoun} {word[:-1]}"
    return f"{pronoun} {word}"


def _to_adviser(match: re.Match[str]) -> str:
    return "Your adviser" if match.group(0)[0].isupper() else "your adviser"


# Seen live: "depends on one person: you, the founder" became "you, you".
_YOU_TWICE = re.compile(r"\b(you),\s*you\b(?=\s*[.,;:!?]|\s*$)", re.I)
# Seen live: "You are the founder." became "You are you."
_OWNER_YOU_ARE_YOU = re.compile(r"(\bowner:\s*)you are you\b", re.I)
_YOU_ARE_YOU = re.compile(r"\s*\byou are you\b[.!]?", re.I)


def in_one_voice(text: str) -> str:
    """Spoken to the founder, not about them, with one way to write money and one word for outside advice."""
    spoken = _BARE_FOUNDERS.sub(lambda m: "Your" if m.group()[0] == "F" else "your", _THE_FOUNDER.sub(_to_you, text))
    spoken = _YOU_TWICE.sub(lambda m: m.group(1), spoken)
    spoken = _OWNER_YOU_ARE_YOU.sub(lambda m: f"{m.group(1)}you", spoken)
    if _YOU_ARE_YOU.search(spoken):
        spoken = _YOU_ARE_YOU.sub("", spoken).lstrip()
    spoken = _THE_DEPARTMENT.sub(_to_adviser, one_money_format(spoken))
    # Seen in the founder's review: "your adviser or your adviser", once two job titles became the same word.
    spoken = _SAME_TWICE.sub(r"\1", spoken)
    # "reducing runway by -2.07 months" says it twice: the verb already carries the sign.
    spoken = _DOUBLE_NEGATIVE.sub(lambda m: f"{m.group(1)} by {m.group(2)}", spoken)
    # "...assumptions to confirm (assumption, confirm)": the sentence already says it (founder re-test 50).
    return _TAG_TWICE.sub(r"\1", spoken)


_SAME_TWICE = re.compile(r"\b((?:your|an?|the)\s+advis[eo]rs?)(?:\s*(?:,|/|\bor\b|\band\b)\s*\1\b)+", re.I)
_TAG_TWICE = re.compile(
    r"(\bassumptions?\s+(?:to|you should|for you to)\s+confirm\b[^.(]*?)\s*\(assumption, confirm\)", re.I
)
_DOUBLE_NEGATIVE = re.compile(
    r"\b((?:reduc|lower|cut|shorten|shrink|decreas)\w*\s+(?:your\s+|the\s+|projected\s+)*runway)\s+by\s+-\s?(\d)",
    re.I,
)


def without_repeats(text: str) -> str:
    """A sentence said twice in one text is said once (founder review 26: "Costs only: ..." twice in a finding)."""
    seen: set[str] = set()
    kept: list[str] = []
    for piece in split_sentences(text):
        key = re.sub(r"\W+", " ", piece).strip().lower()
        if key and len(key) > 12 and key in seen:
            continue
        seen.add(key)
        kept.append(piece)
    out = "".join(kept)
    return out if len(out) == len(text) else out.rstrip() + text[len(text.rstrip()) :]


# --- a goal is not a decision ----------------------------------------------------------------------------------------
_CLAIMS_DECIDED = re.compile(
    r"\b(?:you|we|i|company|team|management|leadership)\b[^.!?]{0,40}?"
    r"\b(?:decided|committed|resolved|agreed|chosen|chose|opted)\b|"
    r"\b(?:your|our|the company's|company's)\s+decision to\b|"
    r"\b(?:the )?decision (?:has been|was) (?:made|taken)\b",
    re.I,
)
_NOT_A_CLAIM = re.compile(
    r"\b(?:not|never|whether|if|once|when|until|before|undecided|have you|did you|nothing on record)\b|n['\u2019]t\b",
    re.I,
)
_POINTS_BACK = re.compile(
    r"\b(?:decided|chosen|committed to|agreed)\s+(?:this|that|it)\b|\bthis (?:was|is) decided\b", re.I
)
_CLAIM_STOP = frozenset(
    {"you", "your", "already", "decided", "decision", "committed", "chose", "chosen", "agreed", "has", "have"}
)
NOTHING_ON_RECORD = "Nothing on record says you have decided this."


def _backed_by_a_record(sentence: str, records: Iterable[DecisionRecord]) -> bool:
    decided = [r for r in records if r.is_decided]
    if not decided:
        return False
    if _POINTS_BACK.search(sentence):
        return True
    words = set(bm25_tokens(sentence)) - _CLAIM_STOP
    return any(words & set(bm25_tokens(f"{r.title} {r.decision}")) for r in decided)


_QUOTED = re.compile(r"[\"\u201c\u2018][^\"\u201d\u2019]{3,}[\"\u201d\u2019]")


def unbacked_decision_claim(sentence: str, records: Iterable[DecisionRecord]) -> bool:
    # A quoted goal's words say nothing about the claim. Seen live: 'You have already decided to "Decide whether..."'.
    outside_quotes = _QUOTED.sub(" ", sentence)
    return (
        _CLAIMS_DECIDED.search(sentence) is not None
        and _NOT_A_CLAIM.search(outside_quotes) is None
        and not _backed_by_a_record(sentence, records)
    )


# --- the words never contradict the goal check -----------------------------------------------------------------------
_HELPS = re.compile(
    r"\b(?:aligns?|aligned|aligning|alignment|supports?|supporting|advances?|furthers?|serves?|meets?|achieves?|"
    r"helps?|consistent|in line|fits?|compatible|moves? (?:you )?(?:toward|towards|closer)|"
    r"(?:gets?|brings?|takes?) you closer|on track|within reach|achievable)\b",
    re.I,
)
_HURTS = re.compile(
    r"\b(?:moves? (?:you )?away|hurts?|conflicts? with|works? against|undermines?|contradicts?|at odds with)\b", re.I
)
_RUNWAY_CLAIM = re.compile(
    r"\b(?:extends?|lengthens?|improves?|increases?|protects?|preserves?|adds? to|boosts?|grows?)\b[^.!?]{0,40}"
    r"\brunway\b|"
    r"\b(?:no|without|not|never)\b[^.!?]{0,20}\b(?:impact\w*|effect\w*|affect\w*|chang\w*|hurt\w*|harm\w*|reduc\w*)\b"
    r"[^.!?]{0,20}\brunway\b|\brunway[- ]neutral\b",
    re.I,
)
_CHURN_CLAIM = re.compile(r"\b(?:reduces?|lowers?|cuts?|improves?|brings? down)\b[^.!?]{0,30}\bchurn\b", re.I)
_NEGATED_BEFORE = re.compile(
    r"(?:\bnot\b|\bnever\b|\bcannot\b|n['\u2019]t\b|\bno longer\b|\bfails? to\b|\bunlikely to\b|\bhard to\b|"
    r"\bwithout\b|\bnor\b)[^.!?]{0,25}$",
    re.I,
)
_ONLY_IF = re.compile(r"\b(?:if|unless|only when|would need|needs? to|to (?:align|meet|achieve|support|reach))\b", re.I)
# Seen live: "aligns with the goal of extending runway while keeping the option to scale later if needed". An aside
# like that puts no condition on the claim.
_IDLE_IF = re.compile(r"\bif (?:needed|necessary|required|so|any|possible|desired|appropriate|applicable)\b", re.I)
_COMPARES = re.compile(r"\b(?:than|compared|against|relative to|more|less|better|least|most)\b", re.I)


def _claims_with(pattern: re.Pattern[str], text: str) -> bool:
    return any(not _NEGATED_BEFORE.search(text[: m.start()]) for m in pattern.finditer(text))


def _effective(goal_status: str, frame: DecisionFrame, chosen: str) -> str:
    """The goal check prices the full model. A smaller option that gives runway back may truly help the goal."""
    option = next((o for o in frame.options if o.name == chosen), None)
    if option is None or option.is_full or option.runway_change_months is None:
        return goal_status
    if goal_status == "moves_away" and option.runway_change_months >= 0:
        return "not_affected"
    if goal_status == "moves_towards" and option.runway_change_months < 0:
        return "not_affected"
    return goal_status


def goal_contradiction(sentence: str, frame: DecisionFrame | None, chosen: str = "") -> str | None:
    """The goal this sentence contradicts, by the frame's statuses, or None.

    Code's own sentences say "moves you away", so they pass. The quoted goal's own words are taken out first: "without
    new financing" in the goal once read as a negation, and let "aligns with the goal" through beside a runway loss.
    """
    if frame is None or not frame.goals or not sentence.strip():
        return None
    for goal in frame.goals:
        status = _effective(goal.status, frame, chosen)
        if status not in ("moves_away", "moves_towards"):
            continue
        text = re.sub(re.escape(goal.goal), " the goal ", sentence, flags=re.I)
        # A sentence naming another goal says nothing about this one: a rise can help one goal and hurt another.
        other = any(g.goal != goal.goal and names_goal(g.goal, sentence) for g in frame.goals)
        named = names_goal(goal.goal, sentence)
        names_it = named or (re.search(r"\bgoals?\b", text, re.I) is not None and not other)
        conditional = _ONLY_IF.search(_IDLE_IF.sub(" ", text)) is not None
        if status == "moves_towards":
            if names_it and not conditional and _claims_with(_HURTS, text):
                return goal.goal
            continue
        if conditional:
            continue
        if names_it and _claims_with(_HELPS, text):
            return goal.goal
        if _COMPARES.search(text):  # "uses less runway than a full office" is true
            continue
        if re.search(r"\brunway\b", goal.goal, re.I) and _claims_with(_RUNWAY_CLAIM, text):
            return goal.goal
        if re.search(r"\bchurn\b", goal.goal, re.I) and _claims_with(_CHURN_CLAIM, text):
            return goal.goal
    return None


def without_contradictions(text: str, frame: DecisionFrame | None, chosen: str = "") -> str:
    """For a memo, whose Goal check section already says what is true: the contradicting sentences just go."""
    kept = "".join(p for p in split_sentences(text) if goal_contradiction(p, frame, chosen) is None)
    return re.sub(r"[ \t]{2,}", " ", kept).strip()


def _open_goal_sentence(frame: DecisionFrame | None) -> str:
    if frame is None:
        return NOTHING_ON_RECORD
    return next((g.sentence for g in frame.goals if g.status == "open_question"), NOTHING_ON_RECORD)


# --- a hire's cost is the cost of a hire -----------------------------------------------------------------------------
_HIRE_FRAMING = re.compile(
    r"\b(?:adding |removing )?(?:1|one|a single)\s+hire\b|\bnot a quote for this role\b|\bper hire\b|"
    r"\bcost of (?:a|one) hire\b",
    re.I,
)
_NAMES_PEOPLE = re.compile(r"\b(hires?|people|person|staff|rep|reps|team|salary|payroll|headcount)\b", re.I)


def _one_hire_claim(sentence: str, frame: DecisionFrame) -> bool:
    if not frame.non_hire:
        return False
    if _HIRE_FRAMING.search(sentence):
        return True
    model = frame.cost_model
    each = f"{model.cost_per_person_monthly:,.2f}" if model and model.cost_per_person_monthly else None
    return each is not None and each in sentence and _NAMES_PEOPLE.search(sentence) is None


# --- superlatives and comparisons must match the options table ------------------------------------------------------
# Seen in the founder's review: the memo called the travel-led pilot "the least costly option", while the partner route
# costs less runway in the same table (-0.10 against -0.21 months).
_CHEAPEST = re.compile(
    r"\b(?:the\s+)?(?:least[- ](?:costly|expensive)|cheapest|lowest[- ]cost|most affordable|least runway|"
    r"costs? the least|smallest (?:cost|spend|outlay))\b",
    re.I,
)
_CHEAPER_THAN = re.compile(
    r"\b(?:cheaper|less (?:costly|expensive)|lower[- ]cost|costs? less|uses? less runway)\s+than\s+"
    r"(?:a\s+|an\s+|the\s+)?(?P<other>[^.,;!?]{3,60})",
    re.I,
)
_UNCHECKED = re.compile(
    r"\b(?:the\s+)?(?:fastest|quickest|lowest[- ]risk|least risky|safest)(?:\s+(?:option|route|path|way|choice))?\b",
    re.I,
)
UNCHECKED_NOTE = "one option (speed and risk are not compared in the options table)"


def _option_words(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", name.lower()) if w not in {"with", "first", "then", "only"}}


def _named_option(text: str, frame: DecisionFrame) -> str | None:
    """The option a stretch of text is about, by its distinctive words ("partner", "travel-led", "full office")."""
    lowered = text.lower()
    best, score = None, 0
    for option in frame.options:
        if option.name.lower() in lowered:
            return option.name
        hits = sum(1 for w in _option_words(option.name) if re.search(rf"\b{re.escape(w)}", lowered))
        if hits > score:
            best, score = option.name, hits
    return best


def _runway_cost(frame: DecisionFrame, name: str) -> float | None:
    """How much runway an option takes, from the table. Higher is costlier. None: not modelled."""
    option = next((o for o in frame.options if o.name == name), None)
    if option is None or not option.modelled:
        return None
    if option.runway_change_months is not None:
        return -option.runway_change_months
    return option.monthly * 12 + option.one_off


def _cost_words(frame: DecisionFrame, name: str) -> str:
    option = next(o for o in frame.options if o.name == name)
    if option.runway_change_months is not None:
        return f"{option.name}: runway {option.runway_change_months:+.2f} months"
    return f"{option.name}: {one_money_format(f'${option.monthly:,.0f}')} a month"


def false_comparison(sentence: str, frame: DecisionFrame | None, chosen: str = "") -> str | None:
    """A code-written sentence in place of a cost superlative or comparison the table does not back, else None."""
    if frame is None or len([o for o in frame.options if o.modelled]) < 2 or not sentence.strip():
        return None
    priced = [(o, _runway_cost(frame, o.name)) for o in frame.options]
    costs = {o.name: c for o, c in priced if c is not None}
    cheapest = min(costs, key=lambda n: costs[n])
    match = _CHEAPEST.search(sentence)
    if match is not None:
        subject = _named_option(sentence[: match.start()], frame) or _named_option(sentence, frame) or chosen
        if subject and subject in costs and costs[subject] > costs[cheapest]:
            return (
                f"{cheapest} costs the least runway in the options table ({_cost_words(frame, cheapest)}; "
                f"{_cost_words(frame, subject)}; assumption, confirm)."
            )
        return None
    match = _CHEAPER_THAN.search(sentence)
    if match is not None:
        other = _named_option(match.group("other"), frame)
        subject = _named_option(sentence[: match.start()], frame) or chosen
        if subject and other and subject != other and costs.get(subject, 0.0) > costs.get(other, float("inf")):
            return (
                f"In the options table, {other} costs less runway than {subject} ({_cost_words(frame, other)}; "
                f"{_cost_words(frame, subject)}; assumption, confirm)."
            )
    return None


def without_unchecked_superlatives(sentence: str) -> str:
    """ "Fastest" and "lowest risk" are in no table, so they are not stated as facts."""
    return _UNCHECKED.sub(UNCHECKED_NOTE, sentence)


def guarded(
    text: str,
    frame: DecisionFrame | None,
    records: Iterable[DecisionRecord] = (),
    used: set[str] | None = None,
    chosen: str = "",
) -> str:
    """The text with those sentences replaced by what is true. `used` stops a reply repeating a replacement."""
    text = without_repeats(in_one_voice(text))
    used = set() if used is None else used
    records = list(records)
    parts: list[str] = []
    changed = False
    for piece in split_sentences(text):
        replacement = None
        if piece.strip() and unbacked_decision_claim(piece, records):
            replacement = _open_goal_sentence(frame)
        elif piece.strip() and frame is not None and _one_hire_claim(piece, frame):
            replacement = frame.cost_sentence()
        elif frame is not None and (goal := goal_contradiction(piece, frame, chosen)) is not None:
            replacement = next(g.sentence for g in frame.goals if g.goal == goal)
        elif frame is not None and (fixed := false_comparison(piece, frame, chosen)) is not None:
            replacement = fixed + piece[len(piece.rstrip()) :]
        elif frame is not None and frame.options and _UNCHECKED.search(piece):
            replacement = without_unchecked_superlatives(piece)
        if replacement is None:
            parts.append(piece)
            continue
        changed = True
        if replacement and replacement not in used:
            used.add(replacement)
            parts.append(replacement)
    if not changed:
        return text
    trailing = text[len(text.rstrip()) :]
    return re.sub(r"[ \t]{2,}", " ", "".join(parts)).strip() + trailing


# --- staying in role -------------------------------------------------------------------------------------------------
_MEMO_LINE = re.compile(
    r"(?im)^[\s#*_>-]*(?:decision memo|memo\b)[^\n]*$|^[\s#*_>-]*(?:final decision|decision)[*_]*\s*[:\u2014][^\n]*$"
)
_STOP_OTHER_WORK = re.compile(
    r"\b(?:stop|freeze|pause|halt|cease|cancel)\s+(?:all\s+|any\s+|further\s+|more\s+|new\s+)*"
    r"(?:hiring|recruit\w*|the\s+\w+\s+hires?|sdrs?\b|hir(?:e|es)\b)[^.!?]*|"
    r"\bstop\s+doing\W+hiring\b[^.!?]*",
    re.I,
)
# Seen live: "use the web_search tool" said to a founder, with cloud off.
_TOOL_TALK = re.compile(
    r"\b(?:web_search|request_metric|run_scenario|run_monte_carlo|search_vault|read_note|hiring_impact)\b", re.I
)
_ASKED_ABOUT_HIRING = re.compile(r"\b(hir\w*|recruit\w*|headcount|sdrs?|layoffs?)\b", re.I)
# Seen live: People & Ops said "stop non-essential travel" with a travel-led pilot on the table.
_STOP_VERB = r"\b(?:stop|cut|pause|avoid|freeze|halt|cease|drop|ban)\b(?:\s+[a-z-]+){0,2}?\s+"
_OPTION_NOISE = frozenset(
    {
        *("full", "pilot", "first", "then", "review", "only", "change", "amount", "test", "half", "price", "prices"),
        *(
            "hire",
            "hires",
            "one",
            "the",
            "now",
            "not",
            "new",
            "customers",
            "line",
            "product",
            "local",
            "office",
            "desk",
        ),
    }
)
# Seen live: the Devil's Advocate sent the founder to the vault for market data the Scout had just said is not there.
_VAULT_FOR_MARKET = re.compile(
    r"\b(?:use|check|search|consult|look (?:in|at)|review|mine|draw on|rely on)\s+(?:\w+\s+){0,2}(?:vault|notes)\b"
    r"[^.!?\n]*\b(?:market|competitor\w*|demand|local|pricing|rent\w*|cost\w*|data)\b|"
    r"\b(?:market|competitor\w*|demand|local)\b[^.!?\n]*\b(?:from|in) (?:the |your )?(?:vault|notes)\b",
    re.I,
)
OUTSIDE_SOURCE = "get this from an outside source, such as a local quote or your adviser"
_PREMISES = re.compile(r"\b(?:physical office|premises|lease|tenancy|office space|fit[- ]out)\b", re.I)
# The Librarian quotes past decisions and memos: that is its job.
_KEEPS_ITS_ROLE = frozenset({"memo_writer", "advisor", "planner", "librarian"})


def _stops_an_option(text: str, frame: DecisionFrame | None) -> bool:
    """Unconditional advice to stop what the option on the table runs on: "stop travel" for a travel-led pilot.

    Other options can be argued against, "pause travel if no customer signs" is a stop rule, and "cut burn" is not
    against an option that itself says "cut burn".
    """
    name = frame.default_option.lower() if frame is not None else ""
    words = {
        w
        for w in re.findall(r"[a-z]{4,}", name)
        if w not in _OPTION_NOISE and not re.search(_STOP_VERB + rf"{w}\b", name)
    }
    if not words:
        return False
    # Seen live: "Stop traveling for the pilot" got past a match on the whole word "travel".
    stops = re.compile(_STOP_VERB + rf"(?:{'|'.join(sorted(words))})(?:l?ing|l?ed|s)?\b", re.I)
    return any(stops.search(s) and not _ONLY_IF.search(s) for s in split_sentences(text))


def _covers_only_the_full_option(text: str, frame: DecisionFrame | None) -> bool:
    """Regulatory points about premises, with a smaller option on the table that this answer never mentions."""
    if frame is None or frame.type != "new_office" or not _PREMISES.search(text):
        return False
    smaller = [o.name for o in frame.options if not o.is_full]
    return not any(
        w in text.lower() for name in smaller for w in re.findall(r"[a-z]{4,}", name.lower()) if w != "local"
    )


def smaller_options_note(frame: DecisionFrame) -> str:
    return (
        f"These points are for the full office. A smaller option, such as {frame.default_option}, may need fewer: "
        "check with your adviser which still apply."
    )


def role_problems(agent_type: str, text: str, message: str, frame: DecisionFrame | None = None) -> list[str]:
    """What this answer does outside the agent's job, for the Verifier's one repair turn."""
    problems: list[str] = []
    if _TOOL_TALK.search(text):
        problems.append("you told the founder about your tools: they have none of them, so say what to check instead")
    if agent_type in _KEEPS_ITS_ROLE:
        return problems
    if _MEMO_LINE.search(text):
        problems.append("you wrote a memo or a final decision: the Memo Writer does that, so give only your part")
    if not _ASKED_ABOUT_HIRING.search(message) and _STOP_OTHER_WORK.search(text):
        problems.append("you told the founder to stop hiring, which nobody asked about: stay with your brief")
    if _stops_an_option(text, frame):
        problems.append("you told the founder to stop something one of the options depends on: do not")
    if agent_type == "devils_advocate" and _VAULT_FOR_MARKET.search(text):
        problems.append("the vault has no market data unless a finding quotes it: name an outside source instead")
    if agent_type == "regulatory_tax" and _covers_only_the_full_option(text, frame):
        problems.append("you covered only a physical office: say which points apply to the smaller options too")
    return problems


def in_role(agent_type: str, text: str, message: str, frame: DecisionFrame | None = None) -> str:
    """Still out of role after the repair turn: the out-of-role lines and sentences go."""
    if _TOOL_TALK.search(text):
        text = "".join(p for p in split_sentences(text) if not _TOOL_TALK.search(p)).strip()
    if agent_type in _KEEPS_ITS_ROLE:
        return text
    kept = _MEMO_LINE.sub("", text)
    if not _ASKED_ABOUT_HIRING.search(message):
        kept = "".join(p for p in split_sentences(kept) if not _STOP_OTHER_WORK.search(p))
    if _stops_an_option(kept, frame):
        # An empty answer is worse than one wrong line.
        kept = "".join(p for p in split_sentences(kept) if not _stops_an_option(p, frame)) or kept
    if agent_type == "devils_advocate":
        kept = _VAULT_FOR_MARKET.sub(OUTSIDE_SOURCE, kept)
    if agent_type == "regulatory_tax" and frame is not None and _covers_only_the_full_option(kept, frame):
        kept = f"{kept.rstrip()} {smaller_options_note(frame)}"
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", kept)).strip() if kept != text else text
