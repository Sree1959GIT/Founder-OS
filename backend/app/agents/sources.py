"""Source check: a source named must exist, and a figure cited to it must be in what was retrieved from it.

The Verifier reports. This removes, in code, whatever it still cannot back after the repair turn:

- A sentence naming a source that is not a real vault file (or a page a search really returned) goes.
- A figure cited to a source must appear in that source's retrieved passages, or come with lineage from a routine.
- A figure with no citation must come from a routine, a retrieved passage, code's own lines or the founder's message.
- A question is held to the same rule: "Are you sure about the $150 billion?" still states $150 billion.

Seen live, in the Dubai run: "Dubai's GDP is approximately $150 billion [notes/economic-overview.md]", with no such
note. The Devil's Advocate built a risk on it and the Advisor asked about it, with `verified: false` beside each.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from app.agents.verifier import PATH_RE, Fact, extract_figures, number_supported, split_sentences
from app.vault.manager import VaultError

REMOVED_NOTE = "(removed: unsupported source)"
FIGURE_TO_CONFIRM = "a figure to confirm"

_URL = re.compile(r"https?://[^\s\]\)>,\"']+")
_WIKI_LINK = re.compile(r"\[\[[^\[\]\n]*\]\]")
_BRACKETS = re.compile(r"(?<!\[)\[([^\[\]\n]{1,300})\](?!\])")
_NO_EXTENSION = re.compile(r"\b(?:notes|decisions|journal|sources|profile)/[\w-][\w./-]*")
_LOOKS_LIKE_A_SOURCE = re.compile(r"^(?:notes|decisions|journal|sources|profile)/|\.(?:markdown|md|pdf|csv|xlsx|txt)$")
_CITE_AFTER_STOP = re.compile(r"([.!?])(\s+)(\[[^\[\]\n]{1,300}\])(?=\s|$)")
_LIST_MARK = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_HEDGED = (
    r"(?:(?:approximately|approx\.?|about|around|roughly|nearly|almost|over|some|circa|~)\s*)?"
    r"(?:(?:USD|AED|EUR|GBP|INR|SAR|Rs\.?)\s*)?"
)
_A_CITATION = re.compile(r"\s*\[[^\[\]\n]{1,300}\]")


def _clean(source: str) -> str:
    return source.strip().strip("`'\"").replace("\\", "/").removeprefix("./").rstrip(".")


def cited_sources(text: str, known: Iterable[str] = ()) -> set[str]:
    """The paths and pages `text` names. A known path is matched whole: a vault path may contain spaces.

    `[[wiki links]]` are not citations: notes link to each other, and a passage may quote such a link.
    """
    found: set[str] = set()
    for url in _URL.findall(text):
        found.add(url.rstrip("."))
    rest = _WIKI_LINK.sub(" ", _URL.sub(" ", text))
    for path in sorted(known, key=len, reverse=True):
        if path in rest:
            found.add(path)
            rest = rest.replace(path, " ")
    for inside in _BRACKETS.findall(rest):
        for part in re.split(r"[,;]", inside):
            source = _clean(part)
            if _LOOKS_LIKE_A_SOURCE.search(source):
                found.add(source)
    rest = _BRACKETS.sub(" ", rest)
    found.update(_clean(path) for path in PATH_RE.findall(rest))
    rest = PATH_RE.sub(" ", rest)
    found.update(_clean(path) for path in _NO_EXTENSION.findall(rest))
    return found


def citation_inside_the_sentence(text: str) -> str:
    """A trailing citation belongs to its sentence: "$5. [a.md]" becomes "$5 [a.md]."."""
    return _CITE_AFTER_STOP.sub(lambda m: f" {m.group(3)}{m.group(1)}", text)


def masked(sentence: str) -> str:
    """What the sentence asks you to find, with no figure and no source left in it."""
    text = _URL.sub(" ", citation_inside_the_sentence(sentence))
    text = PATH_RE.sub(" ", _A_CITATION.sub("", text))
    for figure in sorted(extract_figures(text), key=lambda f: len(f.text), reverse=True):
        pattern = _HEDGED + re.escape(figure.text)
        text = re.sub(pattern, FIGURE_TO_CONFIRM, text, count=1, flags=re.I)
    text = re.sub(r"\[\s*\]|\(\s*\)", " ", text)
    return re.sub(r"\s+", " ", _LIST_MARK.sub("", text)).strip(" .")


@dataclass
class Evidence:
    """What a sentence may rest on in this run."""

    free: list[float] = field(default_factory=list)  # routines with lineage, code's own lines, the founder's message
    quoted: list[float] = field(default_factory=list)  # from a retrieved passage: fine uncited, but not as another's
    passages: dict[str, list[float]] = field(default_factory=dict)  # per source, the figures retrieved from it
    data_files: set[str] = field(default_factory=set)  # files a routine computed from: real, though not in the vault
    exists: Callable[[str], bool] | None = None

    def resolves(self, source: str) -> bool:
        if source in self.passages or source in self.data_files:
            return True
        if source.startswith(("http://", "https://")):
            return False  # no page exists for us unless a search returned it
        short = f"/{source}"
        if any(path.endswith(short) for path in [*self.passages, *self.data_files]):
            return True
        if self.exists is None:
            return False
        return self.exists(source) or ("." not in source.rsplit("/", 1)[-1] and self.exists(f"{source}.md"))

    def _figures_of(self, source: str) -> list[float]:
        short = f"/{source}"
        return [v for path, values in self.passages.items() if path == source or path.endswith(short) for v in values]

    def missing_sources(self, sentence: str) -> list[str]:
        return [s for s in sorted(cited_sources(sentence, self.passages)) if not self.resolves(s)]

    def supports(self, sentence: str) -> bool:
        """Does every source named exist, and is every figure backed where the sentence says it is?"""
        if self.missing_sources(sentence):
            return False
        cited = cited_sources(sentence, self.passages)
        from_sources = [v for source in cited for v in self._figures_of(source)]
        for figure in extract_figures(sentence):
            if number_supported(figure, self.free):
                continue
            allowed = from_sources if cited else [*self.quoted, *from_sources]
            if not number_supported(figure, allowed):
                return False
        return True


def without_unsupported(text: str, evidence: Evidence) -> tuple[str, list[str]]:
    """The text without what `evidence` cannot back, and what went. A list line goes whole: half a line makes no sense.

    Text that passes comes back unchanged.
    """
    if not text.strip():
        return text, []
    joined = citation_inside_the_sentence(text)
    removed: list[str] = []
    lines: list[str] = []
    for line in joined.splitlines():
        if evidence.supports(line):
            lines.append(line)
        elif _LIST_MARK.match(line):
            removed.append(line.strip())
        else:
            kept: list[str] = []
            for piece in split_sentences(line):
                if not piece.strip() or evidence.supports(piece):
                    kept.append(piece)
                else:
                    removed.append(piece.strip())
            kept_line = "".join(kept).strip()
            if kept_line:
                lines.append(kept_line)
    if not removed:
        return text, []
    return "\n".join(lines).strip(), removed


def figures_removed(removed: Iterable[str]) -> list[float]:
    return [f.value for sentence in removed for f in extract_figures(sentence)]


def vault_checker(ctx: Any) -> Callable[[str], bool] | None:
    """Whether a path is a real file in this vault. It only asks the file system; it reads nothing."""
    vault = getattr(ctx, "vault", None)
    if vault is None:
        return None

    def exists(path: str) -> bool:
        try:
            return bool(vault.vault.resolve(path).is_file())
        except (VaultError, OSError, ValueError):
            return False

    return exists


def simple_evidence(known: Iterable[Fact | float], message: str = "") -> Evidence:
    """From a list of facts alone, with no vault: enough for text that names no source."""
    evidence = Evidence(free=[f.value for f in extract_figures(message)])
    for item in known:
        if isinstance(item, Fact) and item.label:
            evidence.free.append(item.value)
        else:
            evidence.quoted.append(item.value if isinstance(item, Fact) else float(item))
    return evidence


def gather(
    message: str,
    results: Iterable[Any],
    frame: Any = None,
    exists: Callable[[str], bool] | None = None,
    code_lines: Iterable[str] = (),
    quoted_text: str = "",
) -> Evidence:
    """Everything a run may rest on: what its agents' tools returned, code's own lines and the founder's message.

    `quoted_text` is checked text the speaker was shown, so its figures count as quoted ones.
    """
    results = list(results)
    facts: list[Fact] = [f for r in results for f in r.known_facts]
    if frame is not None:
        facts.extend(frame.facts)
    evidence = simple_evidence(facts, message)
    evidence.exists = exists
    evidence.quoted.extend(f.value for f in extract_figures(quoted_text))
    lines: list[str] = list(code_lines)
    if frame is not None:
        lines.extend([frame.for_agents(), *frame.findings_block()])
        lines.extend(goal.sentence for goal in frame.goals)
        lines.extend(option.line(frame.currency) for option in frame.options)
        if frame.cost_model is not None:
            evidence.data_files.update(frame.cost_model.sources)
        for figure in frame.baseline:
            evidence.data_files.update(figure.sources)
    for r in results:
        lines.extend(record.summary() for record in r.past_decisions)
        if r.decision_impact is not None:
            lines.append(r.decision_impact.sentence())
        if r.memo is not None:
            lines.extend([*r.memo.predictions, *r.memo.kill_criteria])
        for path, texts in r.passages.items():
            evidence.passages.setdefault(path, []).extend(f.value for text in texts for f in extract_figures(text))
        for citation in [*r.retrieved, *r.citations]:
            evidence.passages.setdefault(citation.path, [])
        for lineage in r.lineage:
            evidence.data_files.update(lineage.source_files)
    evidence.free.extend(f.value for line in lines for f in extract_figures(line))
    return evidence
