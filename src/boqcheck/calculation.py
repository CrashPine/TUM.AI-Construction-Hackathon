"""Check the arithmetic of a priced BoQ: line totals, section totals and the grand total.

A line total must equal quantity × unit price, rounded half up to cents. A section total must
equal the sum of the line totals of its items, and the grand total the sum of all line totals.
A check that lacks a number it needs, or that meets a stated total of zero, is reported as
inconclusive rather than as an error.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import gcd

from .model import BoQ, Item

CENT = Decimal("0.01")


@dataclass(frozen=True)
class CalculationFinding:
    """A calculation that does not add up, or that cannot be checked.

    :param kind: ``line``, ``section`` or ``total`` (the grand total).
    :param oz: the OZ of the item or section; empty for the grand total.
    :param status: ``mismatch`` or ``inconclusive``.
    :param stated: the amount the BoQ states, if any.
    :param computed: the amount computed from the BoQ, if it can be computed.
    :param explanation: a German explanation for the report.
    :param item_index: 1-based position in the BoQ for line findings; None for totals.
    """

    kind: str
    oz: str
    status: str
    stated: Decimal | None
    computed: Decimal | None
    explanation: str
    item_index: int | None = None


def check_calculations(boq: BoQ) -> list[CalculationFinding]:
    """Check line totals, section totals and the grand total of a BoQ.

    Unpriced items (no unit price and no total) are not checked. Section and grand totals are
    checked only where the BoQ states them.

    :param boq: the parsed BoQ.
    :returns: the findings: line checks in item order, then sections, then the grand total.
    """
    findings = [f for index, item in enumerate(boq.items, 1) if (f := _check_line(item, index))]
    for section in boq.sections:
        items = [i for i in boq.items if i.oz.startswith(section.oz + ".")]
        finding = _check_sum("section", section.oz, section.total, items)
        if finding:
            findings.append(finding)
    finding = _check_sum("total", "", boq.total, boq.items)
    if finding:
        findings.append(finding)
    return findings


def _check_line(item: Item, index: int) -> CalculationFinding | None:
    """Check that the total of a priced item is quantity × unit price.

    :param item: the item.
    :param index: the 1-based item position in the BoQ.
    :returns: a finding, or None if the item is unpriced or correct.
    """
    if item.unit_price is None and item.total is None:
        return None
    if item.quantity is None or item.unit_price is None or item.total is None:
        return CalculationFinding(
            "line", item.oz, "inconclusive", item.total, None,
            f"Position {item.oz}: Menge, Einheitspreis oder Gesamtbetrag fehlt.",
            item_index=index,
        )  # fmt: skip
    computed = (item.quantity * item.unit_price).quantize(CENT, ROUND_HALF_UP)
    if computed == item.total:
        return None
    # A Bedarfsposition may be priced without a Gesamtbetrag; no sample shows which.
    if item.provisional and item.total == 0:
        return CalculationFinding(
            "line", item.oz, "inconclusive", item.total, computed,
            f"Bedarfsposition {item.oz}: Gesamtbetrag 0, {item.quantity} × {item.unit_price} "
            f"ergibt {computed}.",
            item_index=index,
        )  # fmt: skip
    return CalculationFinding(
        "line", item.oz, "mismatch", item.total, computed,
        f"Position {item.oz}: {item.quantity} × {item.unit_price} ergibt {computed}, "
        f"angegeben ist {item.total}.",
        item_index=index,
    )  # fmt: skip


def _check_sum(
    kind: str, oz: str, stated: Decimal | None, items: Sequence[Item]
) -> CalculationFinding | None:
    """Check a stated total against the sum of its item totals.

    :param kind: ``section`` or ``total``.
    :param oz: the section OZ, or empty for the grand total.
    :param stated: the stated total; None means there is nothing to check.
    :param items: the items the total covers.
    :returns: a finding, or None if there is nothing to check or the sum matches.
    """
    if stated is None:
        return None
    label = f"Abschnitt {oz}" if oz else "Gesamtsumme"
    totals = [i.total for i in items]
    if None in totals or any(i.provisional for i in items):
        return CalculationFinding(
            kind, oz, "inconclusive", stated, None,
            f"{label}: nicht prüfbar, weil Positionen ohne Gesamtbetrag "
            "oder Bedarfspositionen enthalten sind.",
        )  # fmt: skip
    computed = sum(totals, Decimal(0))
    if computed == stated:
        return None
    if stated == 0:
        return CalculationFinding(
            kind, oz, "inconclusive", stated, computed,
            f"{label}: Summe 0 angegeben, die Positionen ergeben {computed}.",
        )  # fmt: skip
    gaps = _missing_ozs(items)
    hint = (
        f" Lücken in der OZ-Nummerierung ({', '.join(gaps)}) "
        "sind kein Nachweis fehlender Leistungen."
        if gaps
        else ""
    )
    return CalculationFinding(
        kind, oz, "mismatch", stated, computed,
        f"{label}: angegeben {stated}, Summe der Positionen {computed}, "
        f"Differenz {stated - computed}.{hint}",
    )  # fmt: skip


def _missing_ozs(items: Sequence[Item]) -> list[str]:
    """Find item numbers skipped within a numbering sequence.

    The step of a sequence is the greatest common divisor of its item numbers, so numbering
    in tens (0010, 0020, ...) reports 0020 as missing between 0010 and 0030. A gap only hints
    at a removed item; it does not prove that the item caused a difference.

    :param items: the items of a section.
    :returns: the missing OZs in order.
    """
    groups: dict[str, list[str]] = {}
    for item in items:
        parent, _, number = item.oz.rpartition(".")
        if number.isdigit():
            groups.setdefault(parent, []).append(number)
    missing = []
    for parent, numbers in groups.items():
        values = sorted({int(n) for n in numbers})
        step = gcd(*values) or 1
        width = len(numbers[0])
        prefix = f"{parent}." if parent else ""
        for low, high in zip(values, values[1:], strict=False):
            missing += [f"{prefix}{n:0{width}d}" for n in range(low + step, high, step)]
    return missing
