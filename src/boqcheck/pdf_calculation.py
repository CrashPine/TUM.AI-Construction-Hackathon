"""Validate PDF line-price proposals against explicitly labelled German source fields."""

import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .contradictions import Finding
from .numeric_roles import _NUMBER, _PRICE, _QTY, _TOTAL, _unit
from .pdf_extract import Line

__all__ = ["_NUMBER", "evaluate_price", "price_groups"]


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
        if (
            max(positions) - min(positions) != 2
            or _unit(parts["qty"][4])[0] != _unit(parts["price"][4])[0]
        ):
            continue
        if any(len(part[3]) > 18 for part in parts.values()):
            continue
        tokens = {role: f"{part[1]}.{role}" for role, part in parts.items()}
        targets[tokens["total"]] = (tokens, parts)
    return targets


def _polynomial(expr: object, leaves: dict[str, int], depth: int = 0) -> dict | None:
    """Expand an allowlisted tree into exponents of quantity, price and basis.

    The tree is accepted only if it is algebraically equal to quantity times price per
    basis, so a dimensionally valid but different formula such as price times basis per
    quantity is rejected.

    :param expr: binary ``add``/``sub``/``mul``/``div`` nodes over input token IDs.
    :param leaves: input token IDs of this target mapped to their operand index.
    :param depth: nesting depth of ``expr``.
    :returns: exponent tuples mapped to non-zero coefficients, or ``None`` if invalid.
    """
    if isinstance(expr, str):
        return {tuple(int(i == leaves[expr]) for i in range(3)): 1} if expr in leaves else None
    if (
        depth > 6
        or not isinstance(expr, dict)
        or expr.keys() != {"op", "args"}
        or expr["op"] not in ("add", "sub", "mul", "div")
        or not isinstance(expr["args"], list)
        or len(expr["args"]) != 2
    ):
        return None
    left, right = (_polynomial(arg, leaves, depth + 1) for arg in expr["args"])
    if left is None or right is None:
        return None
    result: dict = {}
    if expr["op"] in ("add", "sub"):
        # Quantity and basis share a dimension; price is euro per that dimension.
        if len({(c, a - c + b) for a, c, b in left | right}) != 1:
            return None
        sign = 1 if expr["op"] == "add" else -1
        for term, coefficient in [*left.items(), *((t, sign * c) for t, c in right.items())]:
            result[term] = result.get(term, 0) + coefficient
    elif expr["op"] == "mul":
        for x, cx in left.items():
            for y, cy in right.items():
                term = tuple(a + b for a, b in zip(x, y, strict=True))
                result[term] = result.get(term, 0) + cx * cy
    elif len(right) == 1 and (divisor := next(iter(right.items())))[1] == 1:
        result = {
            tuple(a - b for a, b in zip(x, divisor[0], strict=True)): c for x, c in left.items()
        }
    else:
        return None
    return {term: c for term, c in result.items() if c}


def evaluate_price(group: tuple, expr: object) -> tuple[bool, Finding | None]:
    """Evaluate an explicit line-price expression using only its source operands.

    :param group: labelled evidence for this target.
    :param expr: proposed typed multiplication and division tree.
    :returns: whether checked and a finding only for a verified discrepancy.
    """
    tokens, parts = group
    if _polynomial(expr, {tokens[r]: i for i, r in enumerate(("qty", "price", "basis"))}) != {
        (1, 1, -1): 1
    }:
        return False, None
    qty, price, basis, actual = (
        Decimal(parts[key][3].replace(".", "").replace(",", "."))
        for key in ("qty", "price", "basis", "total")
    )
    if not basis or actual.as_tuple().exponent < -2:
        return False, None
    source_unit, price_unit = parts["qty"][4], parts["price"][4]
    shift = _unit(source_unit)[1] - _unit(price_unit)[1]
    with localcontext() as context:
        context.prec = 80
        converted = qty.scaleb(shift)
        expected = (converted * price / basis).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    if actual == expected:
        return True, None
    conversion = f"{qty} {source_unit} = {converted:f} {price_unit}. " if shift else ""
    explanation = (
        f"Gesamtbetrag laut LV: {actual} EUR. {conversion}"
        f"Rechnung: {converted:f} × {price} / {basis} "
        f"= {expected} EUR (auf Cent gerundet)."
    )
    return True, Finding(
        "calculation",
        tuple((parts[key][2],) for key in ("total", "qty", "price")),
        explanation,
        "Welcher Gesamtbetrag ist für diese Position anzusetzen?",
        "conflict",
    )
