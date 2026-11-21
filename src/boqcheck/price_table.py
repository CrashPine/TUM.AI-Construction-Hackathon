"""Check priced PDF rows with an explicit EUR unit-price and total header."""

import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .contradictions import Finding
from .pdf_calculation import _NUMBER
from .pdf_extract import Line


def table_prices(pages: list[list[Line]]) -> tuple[list[Finding], str]:
    """Compare right-aligned EUR prices on the same baseline as an item and quantity.

    :param pages: source lines in reading order, grouped by physical page.
    :returns: source-grounded discrepancies and the number of verified item rows.
    """
    findings = []
    checked = eligible = 0
    for page in pages:
        rows = defaultdict(list)
        for line in page:
            rows[round(line.quad.rect.y0)].append(line)
        columns = None
        for row in rows.values():
            texts = [line.text for line in row]
            if "Pos-Nr." in texts:
                columns = None
                headers = sorted(row, key=lambda line: line.quad.rect.x0)
                if [line.text for line in headers] == [
                    "Pos-Nr.",
                    "Menge ME",
                    "EP /",
                    "EUR",
                    "GP /",
                    "EUR",
                ]:
                    columns = [headers[i].quad.rect for i in (0, 1, 3, 5)]
                continue
            if columns is None:
                continue
            cells = sorted(row, key=lambda line: line.quad.rect.x0)
            if not re.fullmatch(r"\d+(?:\.\d+){2,}[A-Za-z]?", cells[0].text):
                continue
            eligible += 1
            if len(cells) != 4 or abs(cells[0].quad.rect.x0 - columns[0].x0) > 5:
                continue
            if any(abs(cells[i].quad.rect.x1 - columns[i].x1) > 10 for i in (1, 2, 3)):
                continue
            quantity = re.fullmatch(rf"({_NUMBER})\s+[\w²³.]+", cells[1].text)
            if not quantity or any(not re.fullmatch(_NUMBER, c.text) for c in cells[2:]):
                continue
            values = (quantity[1], cells[2].text, cells[3].text)
            if any(len(v) > 18 for v in values):
                continue
            qty, price, actual = [Decimal(v.replace(".", "").replace(",", ".")) for v in values]
            with localcontext() as context:
                context.prec = 50
                expected = (qty * price).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            checked += 1
            if actual != expected:
                findings.append(
                    Finding(
                        "table_price",
                        (tuple(cells),),
                        f"OZ {cells[0].text}: {qty} × {price} EUR = {expected} EUR. "
                        f"Ausgewiesener Positionsbetrag: {actual} EUR.",
                        "Welcher Positionsbetrag ist anzusetzen?",
                        "conflict",
                    )
                )
    return findings, f"EP/GP-Tabellen: {checked}/{eligible} erkannte Positionszeilen geprüft."
