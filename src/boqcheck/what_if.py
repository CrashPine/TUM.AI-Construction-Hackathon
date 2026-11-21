"""Evaluate one explicit hypothetical quantity or unit price for one position.

The result is plain arithmetic on a user's assumption: it is neither source data nor a market
price. The positions themselves are never changed.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .calculation import CENT
from .model import Item

FIELDS = {"quantity": "Menge", "unit_price": "EP"}
_VALUE = re.compile(r"[0-9]{1,12}(?:[.,][0-9]{1,6})?")


def parse_assumption(fields: dict[str, list[str]], count: int) -> dict | None:
    """Validate a submitted assumption.

    :param fields: parsed form fields ``position``, ``field`` and ``value``.
    :param count: number of positions in the review.
    :returns: the assumption, or None if the value is empty (clears the assumption).
    :raises ValueError: if the position, field or value is invalid.
    """
    position = fields.get("position", [""])[0]
    field = fields.get("field", [""])[0]
    value = fields.get("value", [""])[0].strip()
    if not (position.isascii() and position.isdigit() and 1 <= int(position) <= count):
        raise ValueError("Ungültige Position.")
    if field not in FIELDS:
        raise ValueError("Ungültiges Feld.")
    if not value:
        return None
    if not _VALUE.fullmatch(value):
        raise ValueError("Ungültiger Wert: nur eine Dezimalzahl ohne Vorzeichen.")
    return {
        "position": int(position),
        "field": field,
        "value": str(Decimal(value.replace(",", "."))),
    }


def _amount(quantity: Decimal | None, price: Decimal | None) -> Decimal | None:
    """Compute Menge × EP, rounded half up to cents.

    :param quantity: the quantity, if known.
    :param price: the unit price, if known.
    :returns: the amount, or None if an input is missing.
    """
    if quantity is None or price is None:
        return None
    return (quantity * price).quantize(CENT, ROUND_HALF_UP)


def evaluate(item: Item, assumption: dict) -> dict:
    """Compare the original and the hypothetical amount of one position.

    :param item: the source position.
    :param assumption: a result of :func:`parse_assumption`.
    :returns: ``refused`` with a reason, or ``original`` and ``hypothetical`` triples of
        quantity, unit price and amount (None where an input is missing) and the ``delta``.
    """
    if item.lump_sum:
        return {"refused": "Pauschalposition: Menge × EP ist hier nicht der Positionsbetrag."}
    if item.adjusted_total:
        return {"refused": "Preisanpassung in der Quelle: keine einfache Rechnung möglich."}
    invalid = dict(item.invalid_numbers)
    if item.price_basis not in (None, 1) or "PriceBasis" in invalid:
        return {"refused": "Preiseinheit ungleich 1: keine einfache Rechnung möglich."}
    original = (item.quantity, item.unit_price)
    changed = list(original)
    changed[list(FIELDS).index(assumption["field"])] = Decimal(assumption["value"])
    try:
        with localcontext(prec=60):
            rows = [(*pair, _amount(*pair)) for pair in (original, tuple(changed))]
            delta = None if None in (rows[0][2], rows[1][2]) else rows[1][2] - rows[0][2]
    except ArithmeticError:
        return {"refused": "Betrag nicht darstellbar."}
    return {"original": rows[0], "hypothetical": rows[1], "delta": delta}
