"""Classify numbers in PDF lines by their role, with exact source spans."""

import re
from dataclasses import dataclass
from decimal import Decimal

from .pdf_extract import Line

_NUMBER = r"(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:,[0-9]+)?"
_UNITS = {
    "mm": ("length", -3),
    "cm": ("length", -2),
    "m": ("length", 0),
    "mm2": ("area", -6),
    "cm2": ("area", -4),
    "m2": ("area", 0),
    "mm3": ("volume", -9),
    "cm3": ("volume", -6),
    "m3": ("volume", 0),
    "g": ("mass", -3),
    "kg": ("mass", 0),
    "t": ("mass", 3),
    "st": ("count", 0),
    "stk": ("count", 0),
}
_UNIT = r"(?:mm|cm|m)(?:[²³23])?|kg|g|t|Stk?\.?"
_QTY = re.compile(rf"Menge\s*:\s*(?P<qty>{_NUMBER})\s*(?P<unit>(?:{_UNIT}))", re.I)
_PRICE = re.compile(
    rf"(?:EP|Einheitspreis)\s*:\s*(?P<price>{_NUMBER})\s*(?:EUR|€)\s*"
    rf"(?:/|je|pro)\s*(?P<basis>{_NUMBER})\s*(?P<unit>(?:{_UNIT}))",
    re.I,
)
_TOTAL = re.compile(rf"(?:GB|Gesamtbetrag)\s*:\s*(?P<total>{_NUMBER})\s*(?:EUR|€)", re.I)
_FIELDS = {"qty": "input", "price": "input", "basis": "input", "total": "derived"}
# Standards, nominal sizes and placeholders come first so that their digits never become numbers.
_LEXEME = re.compile(
    r"\b(?:(?:DIN|EN|ISO)\s+)+(?P<standard>[0-9]+(?:-[0-9]+)*)"
    r"|\b(?:DN|PN|C)\s*(?P<size>[0-9]+(?:/[0-9]+)?)(?![\w/])"
    r"|\[[A-Z]+_[0-9]+\]"
    r"|(?<![\w.,-])(?P<number>-?[0-9](?:[0-9.,]*[0-9])?)(?![0-9])"
)
_UNIT_AFTER = re.compile(rf"\s*(?:{_UNIT})(?!\w)", re.I)


@dataclass(frozen=True)
class Token:
    """A number in a source line.

    :ivar id: unique token ID; labelled price fields end with their field name.
    :ivar source: source line ID.
    :ivar start: start offset in the line text.
    :ivar end: end offset in the line text.
    :ivar raw: exact source spelling.
    :ivar role: input, derived, identifier, specification or unknown.
    :ivar value: parsed value, or ``None`` if signed, ambiguous or not a quantity.
    """

    id: str
    source: str
    start: int
    end: int
    raw: str
    role: str
    value: Decimal | None


def _unit(raw: str) -> tuple[str, int]:
    """Read the dimension and base-ten scale of a recognized unit.

    :param raw: source spelling captured by the unit grammar.
    :returns: dimension name and exponent relative to the base unit.
    """
    return _UNITS[raw.casefold().rstrip(".").replace("²", "2").replace("³", "3")]


def _decimal(raw: str, *, labelled: bool = False) -> Decimal | None:
    """Parse a German decimal number only when its format has one reading.

    :param raw: source spelling.
    :param labelled: whether a German euro field fixes the dot as thousands separator.
    :returns: value, or ``None`` for signed, malformed or ambiguous spellings.
    """
    if not re.fullmatch(_NUMBER, raw) or not labelled and "." in raw and "," not in raw:
        return None
    return Decimal(raw.replace(".", "").replace(",", "."))


def number_roles(sources: dict[str, Line]) -> list[Token]:
    """Assign one role to every number in the source lines.

    :param sources: extracted lines keyed by source ID.
    :returns: tokens in reading order with non-overlapping spans.
    """
    tokens = []
    for key, line in sources.items():
        text = line.text
        for pattern in (_QTY, _PRICE, _TOTAL):
            if match := pattern.fullmatch(text):
                for field, role in _FIELDS.items():
                    if field in match.groupdict():
                        raw = match[field]
                        value = _decimal(raw, labelled=True)
                        start = match.start(field)
                        tokens.append(
                            Token(f"{key}.{field}", key, start, start + len(raw), raw, role, value)
                        )
                break
        else:
            for match in _LEXEME.finditer(text):
                group = next((g for g in ("standard", "size", "number") if match[g]), None)
                if group is None:
                    continue
                raw, start = match[group], match.start(group)
                if group == "standard" or group == "number" and start == 0 and raw == line.oz:
                    role, value = "identifier", None
                else:
                    value = _decimal(raw)
                    unit = group == "size" or _UNIT_AFTER.match(text, match.end(group))
                    role = "specification" if unit else "unknown"
                tokens.append(
                    Token(f"{key}.c{start}", key, start, start + len(raw), raw, role, value)
                )
    return tokens
