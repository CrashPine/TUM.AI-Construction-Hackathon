"""Validate local model spelling proposals against German word lists."""

import re
from collections.abc import Callable
from functools import cache
from pathlib import Path

from spellchecker import SpellChecker

from .contradictions import Finding
from .pdf_extract import Line

_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{5,40}")
_TECHNICAL = frozenset({"schachtvierung", "bedarfsposition", "pauschalposition", "kabelschutzrohr"})


def load_lexicon(path: Path) -> frozenset[str]:
    """Read the project lexicon, with one trusted word per line.

    :param path: UTF-8 word list.
    :returns: lowercased words, excluding blank lines and comments.
    """
    return frozenset(
        word.lower()
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if (word := line.strip()) and not word.startswith("#")
    )


def spelling_validator(lexicon: frozenset[str]) -> Callable[[dict, Line], Finding | None]:
    """Validate exact tokens and cache local lookups for one analysis.

    :param lexicon: lowercased project or trade vocabulary.
    :returns: validator that reuses dictionary lookups for the current analysis.
    """
    dictionary = SpellChecker(language="de", distance=1)
    trade_terms = lexicon | _TECHNICAL

    @cache
    def known(word: str) -> bool:
        """Test one normalized term in the two local word lists.

        :param word: normalized German word.
        :returns: whether either source attests the word.
        """
        return word in trade_terms or word in dictionary

    @cache
    def supported(original: str, correction: str) -> bool:
        """Accept an attested one-edit replacement of an unrecognized token.

        :param original: lowercased source token.
        :param correction: lowercased proposed replacement.
        :returns: whether the replacement has enough local support.
        """
        if known(original) or not known(correction):
            return False
        for index in range(4, len(original) - 3):
            prefix, suffix = original[:index], original[index:]
            if known(suffix) and (known(prefix) or prefix.endswith("s") and known(prefix[:-1])):
                return False
        return correction in dictionary.edit_distance_1(original)

    def validate(proposal: dict, line: Line) -> Finding | None:
        """Validate one proposal and return an exact, unique source token.

        :param proposal: unvalidated local model result.
        :param line: referenced line in the current PDF.
        :returns: a finding only for a grounded and locally supported spelling change.
        """
        token = proposal.get("token")
        correction = proposal.get("correction")
        explanation = proposal.get("explanation")
        if not (
            isinstance(token, str)
            and _WORD.fullmatch(token)
            and not token.isupper()
            and isinstance(correction, str)
            and _WORD.fullmatch(correction)
            and isinstance(explanation, str)
            and explanation.strip()
        ):
            return None
        # Embedded model numbers, bracketed placeholders and dashed compounds are ambiguous.
        pattern = rf"(?<![\w\[/-]){re.escape(token)}(?![\w\]/-])"
        spots = list(re.finditer(pattern, line.text))
        if len(spots) != 1 or not supported(token.lower(), correction.lower()):
            return None
        start, end = spots[0].span()
        return Finding(
            "spelling",
            ((line,),),
            explanation.strip(),
            "",
            spelling=(token, correction, start, end),
        )

    return validate
