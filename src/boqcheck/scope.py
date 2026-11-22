"""Detect explicit open scope or pricing conditions in German LV positions."""

import re
from decimal import Decimal
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


_PROPERTY = re.compile(rf"({'|'.join(_FIELDS)})\s*:\s*(.+?)\.?$", re.I)


def _property(text: str) -> tuple[str, str] | None:
    """Parse one complete, unconditional labelled value.

    :param text: wording of one source line.
    :returns: field and normalized value, or None for unsupported wording.
    """
    m = _PROPERTY.fullmatch(text.strip())
    if not m:
        return None
    key, raw = m[1].casefold(), m[2]
    if re.fullmatch(_OPEN, raw, re.I):
        return key, "open"
    if not re.fullmatch(_FIELDS[key][1], raw, re.I):
        return key, "unknown"
    if key in ("dicke", "schichtdicke"):
        n, unit = re.fullmatch(r"(\d+(?:[,.]\d+)?)\s*(mm|cm|m)", raw, re.I).groups()
        return key, str(
            (
                Decimal(n.replace(",", ".")) * {"m": 1000, "cm": 10, "mm": 1}[unit.lower()]
            ).normalize()
        )
    return key, {"an": "auftragnehmer", "ag": "auftraggeber", "bauseits": "auftraggeber"}.get(
        raw.casefold(), raw.casefold()
    )


def _conflicting_fields(oz: str, lines: list[Line]) -> list[Finding]:
    """Find differing explicit values of one property inside the same position.

    :param oz: original position identifier.
    :param lines: source lines belonging to the position.
    :returns: candidates requiring a check of scopes and variants.
    """
    values: dict[str, dict[str, Line]] = {}
    for line in lines:
        if (field := _property(line.text)) and field[1] not in {"open", "unknown"}:
            values.setdefault(field[0], {}).setdefault(field[1], line)
    findings = []
    if any(re.search(r"\b(?:alternativ|wahlweise|variante)\b", line.text, re.I) for line in lines):
        return findings
    for key, alternatives in values.items():
        if len(alternatives) < 2:
            continue
        left, right, *_ = alternatives.values()
        label = _FIELDS[key][0]
        findings.append(
            Finding(
                "conflicting_specification",
                ((left,), (right,)),
                f"OZ {oz} enthält verschiedene Angaben zu {label}. "
                "Es ist zu prüfen, ob beide Angaben für dieselbe Ausführung gelten.",
                f"Welche Angabe zu {label} ist für OZ {oz} zu kalkulieren?",
            )
        )
    return findings


_DN = re.compile(r"\bDN\s*(\d+)\b", re.I)
_DN_RANGE = re.compile(r"\bDN\s*\d+\s*(?:[/–-]|bis\b|oder\b)", re.I)


def nominal_diameter_mismatch(title: str, description: str) -> tuple[int, int] | None:
    """Compare single, unqualified DN designations in a title and description.

    :param title: position title.
    :param description: opening description line.
    :returns: stated diameters if they differ.
    """
    left, right = _DN.findall(title), _DN.findall(description)
    if len(left) != 1 or len(right) != 1:
        return None
    if any(_DN_RANGE.search(text) for text in (title, description)):
        return None
    if any(
        re.search(r"\b(?:alternativ|wahlweise|Variante)\b", text, re.I)
        for text in (title, description)
    ):
        return None
    a, b = int(left[0]), int(right[0])
    return (a, b) if a != b else None


def _table_dn(oz: str, lines: list[Line]) -> Finding | None:
    """Compare the title and immediately following description in an aligned position row.

    :param oz: printed position number.
    :param lines: source lines belonging to this position.
    :returns: a scope candidate with both excerpts, if the diameters differ.
    """
    marker = next((line for line in lines if line.text == oz), None)
    if marker is None:
        return None
    base = marker.quad.rect
    text = [
        line
        for line in lines
        if line.page == marker.page
        and line.quad.rect.x0 > base.x1
        and -2 <= line.quad.rect.y0 - base.y0 <= 36
    ]
    if len(text) < 2:
        return None
    title, description = text[:2]
    if abs(title.quad.rect.y0 - base.y0) > 2 or (
        abs(title.quad.rect.x0 - description.quad.rect.x0) > 4
        or description.quad.rect.y0 <= title.quad.rect.y0 + 2
    ):
        return None
    mismatch = nominal_diameter_mismatch(title.text, description.text)
    if mismatch is None:
        return None
    left, right = mismatch
    return Finding(
        "nominal_diameter",
        ((title,), (description,)),
        f"OZ {oz}: Die Überschrift nennt DN {left}, die Beschreibung nennt DN {right}.",
        f"Welcher Nenndurchmesser ist für OZ {oz} anzusetzen: DN {left} oder DN {right}?",
    )


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
        if dn_finding := _table_dn(oz, lines):
            findings.append(dn_finding)
        findings.extend(_conflicting_fields(oz, lines))
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
