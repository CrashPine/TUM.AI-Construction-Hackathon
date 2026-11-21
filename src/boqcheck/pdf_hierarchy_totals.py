"""Reconcile stated summary hierarchies, tax and carried totals in the priced PDF layouts.

Each check compares a stated total with other stated amounts only. A check abstains when an
amount, a rate, a member row or a carried counterpart cannot be located without ambiguity.
"""

import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from .contradictions import Finding
from .pdf_calculation import _NUMBER
from .pdf_extract import Line

_CENT = Decimal("0.01")


def _value(cell: Line) -> Decimal:
    """Read a German-formatted amount.

    :param cell: cell holding the amount.
    :return: decimal value.
    """
    return Decimal(cell.text.replace(".", "").replace(",", "."))


def _amount(page: list[Line], label: Line, right: float | None) -> Line | None:
    """Locate the single amount on the row of a label.

    :param page: cells of the label's page.
    :param label: row label.
    :param right: right edge of the total column, if known.
    :return: amount cell, or ``None`` if none or several match.
    """
    if right is None:
        return None
    y = label.quad.rect.y0
    hits = [
        cell
        for cell in page
        if y - 0.6 <= cell.quad.rect.y0 <= y + 2.0
        and abs(cell.quad.rect.x1 - right) <= 10
        and len(cell.text) <= 18
        and re.fullmatch(_NUMBER, cell.text)
    ]
    return hits[0] if len(hits) == 1 else None


class _Checks:
    """Collect stated totals, completed comparisons and findings."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.checked = 0
        self.stated = 0

    def compare(
        self,
        name: str,
        total: tuple[Line, Line | None],
        terms: list[tuple[str, tuple[Line, Line | None]]] | None,
        expected: Decimal | None = None,
    ) -> None:
        """Compare one stated total with its stated operands.

        :param name: name of the total in the explanation.
        :param total: label and amount of the stated total.
        :param terms: operand names with label and amount, or ``None`` if incomplete.
        :param expected: expected value if it is not the sum of the operands.
        """
        self.stated += 1
        if total[1] is None or terms is None or any(amount is None for _, (_, amount) in terms):
            return
        self.checked += 1
        actual = _value(total[1])
        values = [(term, _value(amount)) for term, (_, amount) in terms]
        if expected is None:
            expected = sum((value for _, value in values), Decimal(0))
        if actual != expected:
            sum_text = " + ".join(f"{value} ({term})" for term, value in values)
            self.findings.append(
                Finding(
                    "hierarchy_total",
                    (total, *(row for _, row in terms)),
                    f"{name}: {sum_text} = {expected} EUR. Ausgewiesen: {actual} EUR.",
                    "Welcher Betrag gilt in der Summenhierarchie?",
                    "conflict",
                )
            )


def _right(page: list[Line], header: str, unit: str | None) -> float | None:
    """Find the right edge of the total column from its header.

    :param page: cells of one page.
    :param header: first header cell text.
    :param unit: optional unit cell right of the header on the same row.
    :return: right edge, or ``None`` if the header is missing or ambiguous.
    """
    heads = [cell for cell in page if cell.text == header]
    if len(heads) != 1:
        return None
    if unit is None:
        return heads[0].quad.rect.x1
    head = heads[0].quad.rect
    units = [
        cell.quad.rect.x1
        for cell in page
        if cell.text == unit
        and abs(cell.quad.rect.y0 - head.y0) < 3
        and 0 <= cell.quad.rect.x0 - head.x1 < 40
    ]
    return units[0] if len(units) == 1 else None


def _rows(pages: list[list[Line]], pattern: str, right: dict[int, float | None]) -> dict:
    """Index labels by their identifier.

    :param pages: cells per page.
    :param pattern: label regex whose first group is the identifier.
    :param right: total column edge per page index.
    :return: identifier to ``(label, amount)`` rows in document order.
    """
    rows = defaultdict(list)
    for i, page in enumerate(pages):
        for cell in page:
            match = re.fullmatch(pattern, cell.text)
            if match:
                rows[match[1]].append((cell, _amount(page, cell, right[i])))
    return rows


def _members(ids: list[str], rows: dict) -> list | None:
    """Pick one row for each expected member.

    :param ids: expected member identifiers.
    :param rows: identifier to candidate rows.
    :return: named member rows, or ``None`` if any is missing or duplicated.
    """
    if not ids or any(len(rows.get(i, ())) != 1 for i in ids):
        return None
    return [(i, rows[i][0]) for i in ids]


def _tax(page: list[Line], label: Line, rate: str, net: Line | None) -> Decimal | None:
    """Compute the tax from a stated rate and net amount, rounded half up to cents.

    :param page: cells of the tax row's page.
    :param label: tax row label.
    :param rate: regex for the rate cell, or the label itself, with the rate as group 1.
    :param net: stated net amount.
    :return: expected tax, or ``None`` if the rate is missing or ambiguous.
    """
    y = label.quad.rect.y0
    cells = [label] if re.fullmatch(rate, label.text) else page
    rates = [
        match[1]
        for cell in cells
        if abs(cell.quad.rect.y0 - y) <= 2 and (match := re.fullmatch(rate, cell.text))
    ]
    if net is None or len(rates) != 1:
        return None
    percent = Decimal(rates[0].replace(",", "."))
    return (_value(net) * percent / 100).quantize(_CENT, ROUND_HALF_UP)


def _totals(checks: _Checks, net: tuple, tax: tuple, gross: tuple, rate: Decimal | None) -> None:
    """Check the tax and the gross total.

    :param checks: collector.
    :param net: net label and amount.
    :param tax: tax label and amount.
    :param gross: gross label and amount.
    :param rate: expected tax.
    """
    if rate is None:
        checks.stated += 1
    else:
        checks.compare("Steuer", tax, [("Netto", net)], rate)
    checks.compare("Brutto", gross, [("Netto", net), ("Steuer", tax)])


def _single(rows: list) -> tuple:
    """Return the only row or an incomplete placeholder.

    :param rows: candidate rows.
    :return: row with a missing amount unless exactly one row exists.
    """
    return rows[0] if len(rows) == 1 else (rows[0][0], None)


def _angebot(pages: list[list[Line]], checks: _Checks) -> None:
    """Check section copies, area totals, the overall summary and carried totals.

    :param pages: cells per page.
    :param checks: collector.
    """
    right = {i: _right(page, "GP /", "EUR") for i, page in enumerate(pages)}
    body = [
        m[1] for p in pages for c in p if (m := re.fullmatch(r"Abschnitt (\d+\.\d+)\.", c.text))
    ]
    areas = [m[1] for p in pages for c in p if (m := re.fullmatch(r"Bereich (\d+)\.", c.text))]
    originals = _rows(pages, r"Summe Abschnitt (\d+\.\d+)\.", right)
    copies = _rows(pages, r"Summe Abschnitt (\d+\.\d+)\. \S.*", right)
    for section, rows in copies.items():
        for row in rows:
            terms = _members([section], originals)
            checks.compare(f"Abschnitt {section}", row, terms and [("Abschnittsende", terms[0][1])])
    area_rows = _rows(pages, r"Summe Bereich (\d+)\.", right)
    for area, rows in area_rows.items():
        for label, amount in rows:
            ids = [s for s in body if s.split(".")[0] == area]
            checks.compare(f"Bereich {area}", (label, amount), _members(ids, copies))
    summary = _rows(pages, r"Summe Bereich (\d+)\. \S.*", right)
    for area, rows in summary.items():
        for row in rows:
            terms = _members([area], area_rows)
            checks.compare(f"Bereich {area}", row, terms and [("Zusammenstellung", terms[0][1])])
    net = _rows(pages, r"(Summe \(netto\))", right).get("Summe (netto)")
    if net:
        checks.compare("Netto", _single(net), _members(areas, summary))
        tax = _rows(pages, r"(zzgl\. Mehrwertsteuer)", right).get("zzgl. Mehrwertsteuer", [])
        gross = _rows(pages, r"(Gesamtsumme:)", right).get("Gesamtsumme:", [])
        if len(tax) == 1 and len(gross) == 1:
            label = tax[0][0]
            page = next(p for p in pages if label in p)
            rate = _tax(page, label, r"(\d+,\d+) %", _single(net)[1])
            _totals(checks, _single(net), tax[0], gross[0], rate)
    carried = defaultdict(list)
    for i, page in enumerate(pages):
        for cell in page:
            if cell.text == "Übertrag:":
                side = "out" if cell.quad.rect.y0 > 400 else "in"
                carried[side, cell.page].append((cell, _amount(page, cell, right[i])))
    for (side, number), rows in sorted(carried.items()):
        incoming = carried.get(("in", number + 1), [])
        for row in rows if side == "out" else ():
            pair = len(rows) == 1 and len(incoming) == 1
            total = incoming[0] if pair else (row[0], None)
            checks.compare("Übertrag", total, [("Vorseite", row)])


def _abgabe(pages: list[list[Line]], checks: _Checks) -> None:
    """Check the final summary page against the numbered sections of the body.

    :param pages: cells per page.
    :param checks: collector.
    """
    summaries = [
        i
        for i, page in enumerate(pages)
        if any(c.text == "Zusammenstellung" and c.quad.rect.x0 < 50 for c in page)
        and any(c.text == "Gesamtpreis in" for c in page)
    ]
    if len(summaries) != 1:
        return
    index = summaries[0]
    page = pages[index]
    right = _right(page, "Gesamtpreis in", None)
    body = [
        c.text
        for p in pages[:index]
        for c in p
        if 40 <= c.quad.rect.x0 <= 46 and re.fullmatch(r"\d+(?:\.\d+)?", c.text)
    ]
    rows = defaultdict(list)
    for cell in page:
        if cell.quad.rect.x0 < 46 and re.fullmatch(r"\d+(?:\.\d+)?", cell.text):
            rows[cell.text].append((cell, _amount(page, cell, right)))
    top = [i for i in body if "." not in i]
    for section in top:
        if section in rows:
            ids = [i for i in body if i.split(".")[0] == section and "." in i]
            checks.compare(f"Abschnitt {section}", _single(rows[section]), _members(ids, rows))
    labels = {
        c.text: (c, _amount(page, c, right))
        for c in page
        if c.text in ("Summe:", "Summe Brutto (ohne Nachlass):") or c.text.startswith("USt ")
    }
    net = labels.get("Summe:")
    if net:
        checks.compare("Summe", net, _members(top, rows))
        tax = [row for text, row in labels.items() if text.startswith("USt ")]
        gross = labels.get("Summe Brutto (ohne Nachlass):")
        if len(tax) == 1 and gross:
            rate = _tax(page, tax[0][0], r"USt (\d+,\d+) %:", net[1])
            _totals(checks, net, tax[0], gross, rate)


def hierarchy_totals(pages: list[list[Line]]) -> tuple[list[Finding], int, int]:
    """Reconcile the stated summary totals of the two demonstrated priced layouts.

    :param pages: extracted cells per page.
    :return: findings, completed checks and stated totals.
    """
    checks = _Checks()
    if any(c.text.startswith("Zusammenstellung Bereich ") for page in pages for c in page):
        _angebot(pages, checks)
    else:
        _abgabe(pages, checks)
    return checks.findings, checks.checked, checks.stated
