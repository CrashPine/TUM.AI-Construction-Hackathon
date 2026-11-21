"""Detect explicit open scope or pricing conditions in German LV positions."""

import re
from itertools import groupby

from .contradictions import Finding
from .pdf_extract import Line

_OPEN = r"(?:noch\s+)?(?:offen|nach\s+Absprache|zu\s+klären|noch\s+festzulegen|wird\s+nachgereicht)"
_FIELDS = {
    "dicke": ("Dicke", r"\d+(?:[,.]\d+)?\s*(?:mm|cm|m)\b"),
    "schichtdicke": ("Schichtdicke", r"\d+(?:[,.]\d+)?\s*(?:mm|cm|m)\b"),
    "oberflächengüte": ("Oberflächengüte", r"Q[1-4]\b"),
    "oberflächenqualität": ("Oberflächenqualität", r"Q[1-4]\b"),
    "lieferverantwortung": (
        "Lieferverantwortung",
        r"(?:bauseits|Auftragnehmer|Auftraggeber|AN|AG)\b",
    ),
}
_PARAMETER = re.compile(rf"^({'|'.join(_FIELDS)})\s*:\s*{_OPEN}\b", re.I)
_PRICE = re.compile(rf"^(?:Vergütung|Abrechnung|Preis)\s*:\s*{_OPEN}\b", re.I)
_REQUIRED = re.compile(r"\b(?:liefern|einbauen|herstellen|verlegen|montieren|auszuführen)\b", re.I)
_INCLUDED = re.compile(
    r"(?<!nicht )\b(?:im (?:Einheitspreis|Pauschalpreis) enthalten|"
    r"mit dem (?:Einheitspreis|Pauschalpreis) abgegolten)\b",
    re.I,
)
_POSITION = re.compile(r"^\d+(?:\.\d+){2,}[A-Za-z]?\.\s*")
_GENERAL = re.compile(r"^Für alle Positionen\s*:\s*", re.I)


def _title(lines: list[Line]) -> str:
    """Read a position heading for conservative adjacent-position matching.

    :param lines: lines belonging to one position.
    :returns: case-folded description after the OZ, if present.
    """
    text = _POSITION.sub("", lines[0].text).strip()
    if not text and len(lines) > 1:
        text = lines[1].text
    return " ".join(text.casefold().split())


def find_scope_questions(pages: list[list[Line]]) -> list[Finding]:
    """Flag explicitly open terms after checking position and general context.

    :param pages: original PDF lines in reading order.
    :returns: uncertainty findings with exact source evidence.
    """
    groups = [
        (oz, list(lines))
        for oz, lines in groupby(
            (line for page in pages for line in page), key=lambda line: line.oz
        )
    ]
    conditions = [line.text for oz, lines in groups if oz is None for line in lines]
    findings = []
    for index, (oz, lines) in enumerate(groups):
        if not oz:
            continue
        title = _title(lines)
        related = list(lines)
        for adjacent, neighbor in groups[max(0, index - 1) : index + 2]:
            if adjacent and adjacent != oz and title and _title(neighbor) == title:
                related.extend(neighbor)
        explicit = re.compile(rf"^Für (?:die )?OZ {re.escape(oz)}\s*:\s*", re.I)
        context = [line.text for line in related]
        for text in conditions:
            if _GENERAL.match(text) or explicit.match(text):
                context.append(explicit.sub("", _GENERAL.sub("", text)))
        has_work = any(_REQUIRED.search(line.text) for line in lines)
        included = bool(_INCLUDED.search(" ".join(context)))
        reported = set()
        for line in lines:
            if parameter := _PARAMETER.match(line.text):
                key = parameter[1].casefold()
                label, value = _FIELDS[key]
                answer = re.compile(rf"^{key}\s*:\s*{value}", re.I)
                if key in reported or any(answer.match(text) for text in context):
                    continue
                reported.add(key)
                findings.append(
                    Finding(
                        "open_scope",
                        ((line,),),
                        f"Die Angabe zu {label} ist ausdrücklich offen. "
                        "Die geprüften LV-Stellen legen dafür keinen eindeutigen Wert fest.",
                        f"Welche Angabe zu {label} ist für OZ {oz} verbindlich und zu kalkulieren?",
                    )
                )
            elif "price" not in reported and _PRICE.match(line.text) and has_work and not included:
                reported.add("price")
                findings.append(
                    Finding(
                        "open_pricing",
                        ((line,),),
                        "Die Position verlangt eine Leistung, lässt aber deren Vergütung offen.",
                        f"Wie ist die Leistung aus OZ {oz} zu kalkulieren und zu vergüten?",
                    )
                )
    return findings
