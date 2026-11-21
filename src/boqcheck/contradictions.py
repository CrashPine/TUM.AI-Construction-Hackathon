"""Deterministic checks for two specific classes of German LV discrepancies."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

from .pdf_extract import Line

_FACADE = re.compile(r"nachfolgend\s+(?:beschriebene[nr]?\s+)?(?:Porenbeton)?fassade", re.I)
_ROOF = re.compile(r"\b(?:Porenbeton[ -]?)?Dachplatten\b", re.I)
_DRAWINGS = re.compile(r"Detail(?:zeichnungen|pläne)|Werkstattzeichnungen", re.I)
_SHAFT = re.compile(r"\bSchachtvierung(?:en)?\b", re.I)
_GRAIN = re.compile(r"Körnung\s+bis\s+höchstens\s+(\d+(?:[,.]\d+)?)\s*mm\b", re.I)


@dataclass(frozen=True)
class Finding:
    """A candidate supported by source passages.

    :ivar kind: deterministic check identifier.
    :ivar passages: source excerpts, each with one or more source lines.
    :ivar explanation: German explanation of the discrepancy and its uncertainty.
    :ivar question: proposed German Bieterfrage.
    :ivar status: conflict or needs_scope_check.
    :ivar spelling: original word, replacement and exact line offsets for a typo.
    """

    kind: str
    passages: tuple[tuple[Line, ...], ...]
    explanation: str
    question: str
    status: str = "needs_scope_check"
    spelling: tuple[str, str, int, int] | None = None


def _drawing_findings(lines: list[Line]) -> Iterator[Finding]:
    """Find forward facade references whose next position describes roof panels.

    :param lines: source lines in one file page.
    :yields: scope discrepancy candidates.
    """
    for index, line in enumerate(lines):
        if not line.oz or not _DRAWINGS.search(line.text):
            continue
        following = lines[index + 1 :]
        boundary = next((i for i, other in enumerate(following) if other.oz != line.oz), None)
        if boundary is None:
            continue
        body = following[:boundary]
        next_oz = following[boundary].oz
        next_item = []
        for other in following[boundary:]:
            if other.oz != next_oz:
                break
            next_item.append(other)
        roof = next((other for other in next_item if _ROOF.search(other.text)), None)
        if roof is None:
            continue
        for i in range(len(body)):
            excerpt = tuple(body[i : i + 2])
            if _FACADE.search(" ".join(part.text for part in excerpt)):
                yield Finding(
                    "scope_reference",
                    (excerpt, (roof,)),
                    "Die Zeichnungsposition verweist auf eine nachfolgend beschriebene Fassade. "
                    "Die nächste Position beschreibt Dachplatten. Der Umfang der zu "
                    "kalkulierenden Zeichnungsleistung ist daher zu klären.",
                    "Sind Zeichnungen für die Dachplatten, die Fassade oder beide Bauteile "
                    "einzukalkulieren?",
                )
                break


def find_contradictions(pages: list[list[Line]]) -> list[Finding]:
    """Check forward scope references and differing shaft curb aggregate limits.

    :param pages: extracted source lines by page.
    :returns: deduplicated candidates for scope review.
    """
    findings = [finding for lines in pages for finding in _drawing_findings(lines)]
    limits: list[tuple[Decimal, tuple[Line, ...]]] = []
    for lines in pages:
        for index, line in enumerate(lines):
            if not _SHAFT.search(line.text):
                continue
            excerpt = tuple(lines[index : index + 4])
            excerpt = tuple(part for part in excerpt if part.oz == line.oz)
            text = " ".join(part.text for part in excerpt)
            if "feinbeton" in text.casefold() and (match := _GRAIN.search(text)):
                limit = Decimal(match[1].replace(",", "."))
                end = match.end()
                for offset, part in enumerate(excerpt):
                    end -= len(part.text) + 1
                    if end <= 0:
                        excerpt = excerpt[: offset + 1]
                        break
                if not limits or limits[-1][1][-1] != excerpt[-1]:
                    limits.append((limit, excerpt))

    for index, (limit, excerpt) in enumerate(limits):
        for other_limit, other in limits[index + 1 :]:
            if limit != other_limit:
                findings.append(
                    Finding(
                        "aggregate_limit",
                        (excerpt, other),
                        f"Für Schachtvierungen aus Feinbeton werden {limit} mm und "
                        f"{other_limit} mm als Höchstwerte genannt. Ob beide Anforderungen "
                        "für dasselbe Bauteil gelten, beeinflusst die Materialkalkulation.",
                        "Welche maximale Körnung gilt für die jeweilige Schachtvierung?",
                    )
                )
    return findings


def rule_scope(pages: list[list[Line]]) -> list[str]:
    """Identify the position and component cues needed by the existing PDF rules.

    :param pages: source lines by page.
    :returns: rule identifiers with applicable text in the document.
    """
    has_drawings = has_roof = has_shaft = False
    for page in pages:
        for line in page:
            has_drawings |= bool(line.oz and _DRAWINGS.search(line.text))
            has_roof |= bool(_ROOF.search(line.text))
            has_shaft |= bool(_SHAFT.search(line.text))
    return [
        rule
        for rule, applicable in (
            ("scope_reference", has_drawings and has_roof),
            ("aggregate_limit", has_shaft),
        )
        if applicable
    ]
