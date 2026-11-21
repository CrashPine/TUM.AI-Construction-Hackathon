"""PDF German typo detection for bills of quantities (LV).

Inspects ``Line`` objects from ``boqcheck.pdf_extract`` using an optional LLM
suspect callback or narrow deterministic heuristics, validates suspects against
``GERMAN_WORDS`` and an optional web lookup, and caches learned web results.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, MutableMapping
from dataclasses import dataclass

from boqcheck.german_dict import GERMAN_WORDS
from boqcheck.pdf_extract import Line

_VALID_TRIPLES = frozenset(["schiff", "ballle", "nummern"])
_SUFFIXES = ("en", "er", "es", "em", "e", "n", "s")
_PLACEHOLDER = re.compile(r"\[[A-ZÄÖÜ]+_\d+\]")
_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]+(?:\d+[A-Za-zÄÖÜäöüß]*)?")
_TRIPLE = re.compile(r"([a-zäöüß])\1\1")
_CAMEL_FLIP = re.compile(r"[a-zäöüß]{3,}[A-ZÄÖÜ][a-zäöüß]")
_LETTER_DIGIT = re.compile(r"[a-zäöüß]{4,}\d")


@dataclass(frozen=True)
class TypoFinding:
    """A potential spelling error detected in a PDF line.

    :ivar word: suspect token as written in the PDF.
    :ivar page: zero-based PDF page index.
    :ivar oz: item Ordnungszahl if known, otherwise None.
    :ivar context: full extracted source line text.
    :ivar suggestion: closest dictionary word within edit distance 1, if any.
    """

    word: str
    page: int
    oz: str | None
    context: str
    suggestion: str | None = None


def _is_in_dictionary(word: str) -> bool:
    """Check whether a word or its inflected stem is in the bundled dictionary.

    :param word: token to validate.
    :returns: True if the lowercased word or its stem is in ``GERMAN_WORDS``.
    """
    # Use lower() rather than casefold() so German ß stays intact and matches GERMAN_WORDS.
    lowered = word.lower()
    if lowered in GERMAN_WORDS:
        return True
    return any(
        lowered.endswith(suffix) and lowered[: -len(suffix)] in GERMAN_WORDS for suffix in _SUFFIXES
    )


def _has_triple_letters(word: str) -> bool:
    """Check whether a word contains three identical consecutive letters.

    :param word: token to inspect.
    :returns: True for non-uppercase alphabetic tokens with a non-whitelisted letter triple.
    """
    if word.isupper():
        return False
    lowered = word.lower()
    if not lowered.isalpha() or any(valid in lowered for valid in _VALID_TRIPLES):
        return False
    return bool(_TRIPLE.search(lowered))


def _is_heuristic_suspect(word: str) -> bool:
    """Apply narrow offline heuristics to flag a likely typo token.

    :param word: token extracted from a PDF line.
    :returns: True if the token has tripled letters, an internal case flip, or a trailing digit.
    """
    return (
        _has_triple_letters(word)
        or bool(_CAMEL_FLIP.search(word))
        or bool(_LETTER_DIGIT.search(word))
    )


def _edit_distance_one(left: str, right: str) -> bool:
    """Check whether two lowercased words are at Levenshtein distance 1.

    :param left: first lowercased word.
    :param right: second lowercased word.
    :returns: True if exactly one insertion, deletion, or substitution transforms left into right.
    """
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right, strict=True)) == 1
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    index = other = edits = 0
    while index < len(shorter) and other < len(longer):
        if shorter[index] == longer[other]:
            index += 1
        else:
            edits += 1
            if edits > 1:
                return False
        other += 1
    return True


def _find_suggestion(word: str) -> str | None:
    """Find a dictionary correction within edit distance 1 of a suspect token.

    :param word: suspect token.
    :returns: closest dictionary word in deterministic order, or None if none matches.
    """
    lowered = word.lower()
    collapsed = _TRIPLE.sub(r"\1\1", lowered)
    if collapsed != lowered and collapsed in GERMAN_WORDS:
        return collapsed
    for candidate in sorted(GERMAN_WORDS):
        if _edit_distance_one(lowered, candidate):
            return candidate
    return None


def _select_suspects(
    line: Line,
    llm_check: Callable[[str], list[str]] | None,
) -> Iterator[str]:
    """Yield suspect tokens from one line after stripping anonymization placeholders.

    :param line: extracted PDF source line.
    :param llm_check: optional callback proposing suspect tokens for cleaned line text.
    :yields: suspect tokens in source order.
    """
    cleaned = _PLACEHOLDER.sub(" ", line.text).strip()
    words = _WORD.findall(cleaned)
    if not words:
        return
    if llm_check is not None:
        proposed = {token.lower() for token in llm_check(cleaned)}
        for word in words:
            if word.lower() in proposed:
                yield word
        return
    for word in words:
        if _is_heuristic_suspect(word):
            yield word


def find_typos(
    pages: list[list[Line]],
    *,
    web_check: Callable[[str], bool] | None = None,
    cache: MutableMapping[str, bool] | None = None,
    llm_check: Callable[[str], list[str]] | None = None,
) -> list[TypoFinding]:
    """Detect potential German typos across extracted PDF lines.

    Suspects are proposed per line by ``llm_check`` when given, or by narrow
    deterministic heuristics otherwise. Suspects found in ``GERMAN_WORDS`` (or
    with standard German inflection suffixes) are skipped. Remaining suspects
    are optionally verified with ``web_check`` and cached in ``cache``; valid
    web-checked words are learned and not reported.

    :param pages: extracted PDF lines grouped by page.
    :param web_check: optional callable returning True when a suspect word is valid.
    :param cache: optional mapping storing lowercased word validity across checks.
    :param llm_check: optional callable returning suspect words for a line of text.
    :returns: typo findings in document order.
    """
    known: MutableMapping[str, bool] = {} if cache is None else cache
    findings: list[TypoFinding] = []

    for page_lines in pages:
        for line in page_lines:
            for suspect in _select_suspects(line, llm_check):
                if _is_in_dictionary(suspect):
                    continue
                key = suspect.lower()
                if key in known:
                    if known[key]:
                        continue
                elif web_check is not None:
                    is_valid = bool(web_check(suspect))
                    known[key] = is_valid
                    if is_valid:
                        continue
                findings.append(
                    TypoFinding(
                        word=suspect,
                        page=line.page,
                        oz=line.oz,
                        context=line.text,
                        suggestion=_find_suggestion(suspect),
                    )
                )

    return findings
