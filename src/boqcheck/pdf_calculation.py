"""Validate PDF line-price proposals against explicitly labelled German source fields."""

import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .contradictions import Finding
from .pdf_extract import Line

_NUMBER = r"(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:,[0-9]+)?"
_UNIT = r"(?:m²|m³|m2|m3|m|kg|t|Stk\.?|St\.)"
_QTY = re.compile(rf"Menge\s*:\s*(?P<qty>{_NUMBER})\s*(?P<unit>{_UNIT})", re.I)
_PRICE = re.compile(
    rf"(?:EP|Einheitspreis)\s*:\s*(?P<price>{_NUMBER})\s*(?:EUR|€)\s*"
    rf"(?:/|je|pro)\s*(?P<basis>{_NUMBER})\s*(?P<unit>{_UNIT})",
    re.I,
)
_TOTAL = re.compile(rf"(?:GB|Gesamtbetrag)\s*:\s*(?P<total>{_NUMBER})\s*(?:EUR|€)", re.I)


def price_groups(sources: dict[str, Line]) -> dict:
    """Index adjacent explicit fields within one unambiguous position on one page.

    :param sources: extracted lines in reading order.
    :returns: target IDs mapped to typed operands, amounts and source lines.
    """
    groups = defaultdict(list)
    for key, line in sources.items():
        if line.oz:
            groups[line.page, line.oz].append((key, line))
    targets = {}
    for rows in groups.values():
        if any(
            re.search(r"Bedarf|optional|Rabatt|Nachlass|Zuschlag|alternativ", line.text, re.I)
            for _, line in rows
        ):
            continue
        fields = {}
        for i, (key, line) in enumerate(rows):
            for pattern in (_QTY, _PRICE, _TOTAL):
                if match := pattern.fullmatch(line.text):
                    for role, raw in match.groupdict().items():
                        if role != "unit":
                            fields.setdefault(role, []).append(
                                (i, key, line, raw, match.groupdict().get("unit"))
                            )
        if any(len(fields.get(role, [])) != 1 for role in ("qty", "price", "basis", "total")):
            continue
        parts = {role: entries[0] for role, entries in fields.items()}
        positions = [part[0] for part in parts.values()]
        if max(positions) - min(positions) != 2 or parts["qty"][4] != parts["price"][4]:
            continue
        if any(len(part[3]) > 18 for part in parts.values()):
            continue
        tokens = {role: f"{part[1]}.{role}" for role, part in parts.items()}
        targets[tokens["total"]] = (tokens, parts)
    return targets


def evaluate_price(group: tuple, expr: object) -> tuple[bool, Finding | None]:
    """Evaluate an explicit line-price expression using only its source operands.

    :param group: labelled evidence for this target.
    :param expr: proposed typed multiplication and division tree.
    :returns: whether checked and a finding only for a verified discrepancy.
    """
    tokens, parts = group
    product = {"op": "mul", "args": [tokens["qty"], tokens["price"]]}
    inverse = {"op": "mul", "args": [tokens["price"], tokens["qty"]]}
    if expr not in ({"op": "div", "args": [p, tokens["basis"]]} for p in (product, inverse)):
        return False, None
    qty, price, basis, actual = (
        Decimal(parts[key][3].replace(".", "").replace(",", "."))
        for key in ("qty", "price", "basis", "total")
    )
    if not basis or actual.as_tuple().exponent < -2:
        return False, None
    with localcontext() as context:
        context.prec = 80
        expected = (qty * price / basis).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    if actual == expected:
        return True, None
    explanation = (
        f"Gesamtbetrag laut LV: {actual} EUR. Rechnung: {qty} × {price} / {basis} "
        f"= {expected} EUR (auf Cent gerundet)."
    )
    return True, Finding(
        "calculation",
        tuple((parts[key][2],) for key in ("total", "qty", "price")),
        explanation,
        "Welcher Gesamtbetrag ist für diese Position anzusetzen?",
        "conflict",
    )
