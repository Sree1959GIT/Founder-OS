"""The last pass over an answer: no sentence that says again what an earlier one said (founder re-test 54).

Seen live: code's opening named the goal and the model's next sentence named it again; and "what has changed since
you drafted it? What has changed since you drafted the proposal?". The first sentence stays (code's comes first), a
near-duplicate after it goes. Two sentences with different figures are never duplicates, with one exception (founder
re-test S5, 2026-11-14): a second sentence on the same goal goes even when its figures differ.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.agents.decision_frame import names_goal
from app.agents.verifier import extract_figures, split_sentences

# Words that carry no meaning of their own when comparing two sentences.
_STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "so",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "by",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "you",
        "your",
        "we",
        "our",
        "i",
        "my",
        "me",
        "us",
        "they",
        "them",
        "their",
        "he",
        "she",
        "his",
        "her",
        "do",
        "does",
        "did",
        "has",
        "have",
        "had",
        "will",
        "would",
        "can",
        "could",
        "should",
        "may",
        "might",
        "what",
        "which",
        "who",
        "when",
        "where",
        "how",
        "why",
        "there",
        "here",
        "than",
        "then",
        "also",
        "just",
        "only",
        "very",
    ]
)
NEAR = 0.6  # share of content words in common (Jaccard) from which two sentences say the same thing


def _content(sentence: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z]+", sentence.lower()) if w not in _STOP and len(w) > 1}


def _figures(sentence: str) -> list[float]:
    return sorted(round(f.value, 2) for f in extract_figures(sentence))


def _question(sentence: str) -> str:
    """The question a sentence asks: what follows its last colon or dash, if any."""
    return re.split(r":\s|\s[-\u2013\u2014]\s", sentence.rstrip())[-1]


# Which way a decision moves a goal. A later sentence that is the first to say so is news, not a repeat.
_DIRECTION = re.compile(
    r"\b(away|against|further from|short of|hurts?|conflicts?|towards?|closer|helps?|supports?|serves?)\b", re.I
)


def same_goal(sentence: str, earlier: str, goals: Iterable[str] = ()) -> bool:
    """The same goal, told twice (founder re-test S5): "…, which moves you away from your goal "Extend runway…""
    and then "This moves you away from your goal "Extend runway…": …". The second telling goes whatever figures it
    carries: the first already said which way the decision moves the goal, and the figures are on the card."""
    for goal in goals:
        if goal and names_goal(goal, sentence) and names_goal(goal, earlier):
            if _DIRECTION.search(sentence) and not _DIRECTION.search(earlier):
                continue  # the earlier one only named the goal; this one says which way it moves
            return True
    return False


def near_duplicate(sentence: str, earlier: str, goals: Iterable[str] = ()) -> bool:
    """Does `sentence` say again what `earlier` said?"""
    if same_goal(sentence, earlier, goals):
        return True
    if _figures(sentence) != _figures(earlier):
        return False
    mine, theirs = _content(sentence), _content(earlier)
    if len(mine) >= 3 and len(theirs) >= 3 and len(mine & theirs) / len(mine | theirs) >= NEAR:
        return True
    # The same question, asked twice, even when the first one came after a statement ("…[path]: what has changed?").
    if sentence.rstrip().endswith("?"):
        asked, before = _content(_question(sentence)), _content(_question(earlier)) if "?" in earlier else set()
        return len(asked) >= 3 and len(before) >= 3 and len(asked & before) / len(asked | before) >= NEAR
    return False


def without_repeats(text: str, goals: Iterable[str] = (), said: Iterable[str] = ()) -> str:
    """`text` with every near-duplicate sentence after the first taken out. `said`: sentences already shown."""
    goals = list(goals)
    kept: list[str] = []
    earlier = [s for s in said if s.strip()]
    for piece in split_sentences(text):
        if piece.strip() and any(near_duplicate(piece, e, goals) for e in earlier):
            continue
        kept.append(piece)
        if piece.strip():
            earlier.append(piece)
    return "".join(kept)
