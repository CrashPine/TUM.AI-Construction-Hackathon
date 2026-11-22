"""Recalculate PDF price tables: two priced EUR layouts and one layout without a currency."""

import re
from collections import Counter
from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .contradictions import Finding
from .pdf_calculation import _NUMBER
from .pdf_extract import Line
from .pdf_hierarchy_totals import hierarchy_totals
from .pdf_subtotals import _OPTION, SectionTotals

_QUANTITY_HEADER = ["Leistungsbeschreibung", "Menge ME", "Einheitspreis", "Gesamtbetrag"]
_BLANK = re.compile(r"\.{6,}")


def _rows(page: list[Line]) -> list[list[Line]]:
    """Group the cells of one page into rows on a shared top edge.

    :param page: cells of one page.
    :returns: rows from top to bottom, each sorted from left to right.
    """
    rows: list[list[Line]] = []
    for line in sorted(page, key=lambda cell: cell.quad.rect.y0):
        if not rows or line.quad.rect.y0 - rows[-1][0].quad.rect.y0 > 1.25:
            rows.append([])
        rows[-1].append(line)
    return [sorted(row, key=lambda line: line.quad.rect.x0) for row in rows]


def _price_check(
    oz: str, cells: list[Line], values: tuple[str, str, str], basis: str, currency: str
) -> tuple[Decimal, Finding | None] | None:
    """Compare a stated total with quantity × unit price, rounded half up to cents.

    :param oz: position of the row.
    :param cells: source cells of the row.
    :param values: quantity, unit price and stated total as printed.
    :param basis: text after the unit price in the explanation.
    :param currency: text after each amount in the explanation.
    :returns: stated total and a finding for a discrepancy, or ``None`` for a non-number.
    """
    if any(len(v) > 18 or not re.fullmatch(_NUMBER, v) for v in values):
        return None
    qty, price, actual = [Decimal(v.replace(".", "").replace(",", ".")) for v in values]
    with localcontext() as context:
        context.prec = 50
        expected = (qty * price).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    if actual == expected:
        return actual, None
    return actual, Finding(
        "table_price",
        (tuple(cells),),
        f"OZ {oz}: {qty} × {price} {basis} = {expected}{currency}. "
        f"Ausgewiesener Positionsbetrag: {actual}{currency}.",
        "Welcher Positionsbetrag ist anzusetzen?",
        "conflict",
    )


def _quantity_table(pages: list[list[Line]]) -> tuple[list[Finding], Counter[str]]:
    """Check the table headed OZ, Leistungsbeschreibung, Menge ME, Einheitspreis, Gesamtbetrag.

    The OZ row comes before the row with the quantity and both price fields, so that row takes
    its position from ``Line.oz``. It is computed only for a known OZ without a second
    quantity row: another row would cite the wrong position. A filled ``Summe <OZ>.`` row is
    compared with the totals of the positions under that OZ. The header names no currency.

    :param pages: source lines in reading order, grouped by physical page.
    :returns: discrepancies and counts of rows, checks, unpriced rows and stated totals.
    """
    quantities = []
    sums = []
    for page in pages:
        header = None
        for row in _rows(page):
            texts = [cell.text for cell in row]
            if texts[0] in ("OZ", "Ordnungszahl") and texts[1:] == _QUANTITY_HEADER:
                header = [cell.quad.rect for cell in row]
                continue
            if header is None:
                continue
            _, text_head, qty_head, price_head, total_head = header
            prices = [cell for cell in row if abs(cell.quad.rect.x1 - price_head.x1) < 10]
            totals = [cell for cell in row if abs(cell.quad.rect.x1 - total_head.x1) < 10]
            if len(totals) != 1:
                continue
            if section := re.fullmatch(r"Summe (\d+(?:\.\d+)*)\.", texts[0]):
                sums.append((section[1], row[0], totals[0]))
            elif (
                (quantity := re.fullmatch(rf"({_NUMBER})\s+([A-Za-z][\w²³./-]*)", texts[0]))
                and text_head.x1 < row[0].quad.rect.x0 <= qty_head.x1
                and len(prices) <= 1
                and len(row) == 2 + len(prices)
            ):
                quantities.append((row, quantity, prices[0] if prices else None, totals[0]))
    counts = Counter(rows=len(quantities), sums=len(sums))
    per_oz = Counter(row[0].oz for row, *_ in quantities)
    amounts = dict.fromkeys(per_oz)
    unit_only = {}
    findings = []
    for row, quantity, price, total in quantities:
        oz = row[0].oz
        unique = oz is not None and per_oz[oz] == 1
        counts["ambiguous"] += not unique
        if total.text == "Nur Einh.-Pr.":
            counts["unit_only"] += 1
            unit_only[oz] = tuple(row)
        elif any(_BLANK.fullmatch(cell.text) for cell in (price, total) if cell):
            counts["blank"] += 1
        elif unique and price:
            values = (quantity[1], price.text, total.text)
            result = _price_check(oz, row, values, f"je Mengeneinheit ({quantity[2]})", "")
            if result:
                counts["checked"] += 1
                amounts[oz] = (result[0], total)
                if result[1]:
                    findings.append(result[1])
    positions = {line.oz for page in pages for line in page if line.oz}
    optional = {line.oz for page in pages for line in page if _OPTION.search(line.text)}
    for section, label, cell in sums:
        if _BLANK.fullmatch(cell.text):
            counts["blank_sums"] += 1
            continue
        prefix = section + "."
        members = {oz: value for oz, value in amounts.items() if oz and oz.startswith(prefix)}
        excluded = {oz: unit_only[oz] for oz in members if oz in unit_only}
        ledger = SectionTotals(
            section,
            amounts=members,
            optional=optional & members.keys(),
            excluded=set(excluded),
            markers=excluded,
            currency="",
        )
        # A row without a unique OZ, or a position without a recognised row, may belong here.
        ledger.ambiguous = counts["ambiguous"] > 0 or members.keys() != {
            oz for oz in positions if oz.startswith(prefix)
        }
        if len(cell.text) <= 18 and re.fullmatch(_NUMBER, cell.text):
            ledger.reconcile([label, cell])
        counts["sums_checked"] += ledger.checked
        findings.extend(ledger.findings)
    return findings, counts


def table_prices(pages: list[list[Line]]) -> tuple[list[Finding], str]:
    """Compare right-aligned prices on the same baseline as an item or its quantity.

    :param pages: source lines in reading order, grouped by physical page.
    :returns: source-grounded discrepancies and a German coverage summary.
    """
    findings = []
    checked = eligible = 0
    position = None
    sections = SectionTotals()
    split_sections: dict[str, SectionTotals] = {}
    active_split = None
    summary_checked = summary_stated = 0
    for page in pages:
        columns = None
        split_header = None
        split = False
        summary = False
        for row in _rows(page):
            texts = [line.text for line in row]
            if texts == ["Pos-Nr. (Pos-", "Menge", "Einheit", "Einheitspreis in", "Gesamtpreis in"]:
                split_header = row
                split = False
                columns = None
                continue
            if split_header is not None and not split:
                split = texts == ["Nr.)", "EUR", "EUR"] and all(
                    title.quad.rect.x0 <= currency.quad.rect.x0 <= title.quad.rect.x1
                    for title, currency in zip(split_header[-2:], row[-2:], strict=True)
                )
                if not split:
                    split_header = None
                    position = None
                continue
            if "Pos-Nr." in texts:
                position = None
                columns = None
                headers = row
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
            cells = row
            if split and texts == ["Zusammenstellung"]:
                summary = True
                continue
            if summary:
                if (
                    re.fullmatch(r"\d+\.\d+", texts[0])
                    and abs(cells[0].quad.rect.x0 - split_header[0].quad.rect.x0) < 5
                ):
                    summary_stated += 1
                    section = split_sections.get(texts[0])
                    amounts = [
                        cell
                        for cell in page
                        if abs(cell.quad.rect.y0 - cells[0].quad.rect.y0) <= 1.25
                        and abs(cell.quad.rect.x1 - split_header[-1].quad.rect.x1) < 10
                        and len(cell.text) <= 18
                        and re.fullmatch(_NUMBER, cell.text)
                    ]
                    if section and len(amounts) == 1:
                        previous = section.checked
                        section.reconcile([cells[0], amounts[0]])
                        summary_checked += section.checked - previous
                continue
            if split or columns is not None:
                left = split_header[0].quad.rect.x0 if split else columns[0].x0
                right = split_header[-1].quad.rect.x1 if split else columns[-1].x1
                if (
                    split
                    and re.fullmatch(r"\d+\.\d+", texts[0])
                    and abs(cells[0].quad.rect.x0 - left) < 5
                ):
                    section = SectionTotals()
                    duplicate = texts[0] in split_sections
                    if not duplicate:
                        split_sections[texts[0]] = section
                    else:
                        split_sections[texts[0]].ambiguous = True
                    section.observe(row, split, left, right)
                    active_split = section
                elif split and active_split is not None:
                    active_split.observe(row, split, left, right)
                elif not split:
                    sections.observe(row, split, left, right)
            is_position = re.fullmatch(r"\d+(?:\.\d+){2,}[A-Za-z]?", cells[0].text)
            if split:
                first, qty_head, unit_head, price_head, total_head = split_header
                if abs(cells[0].quad.rect.x0 - first.quad.rect.x0) < 5:
                    if is_position:
                        position = cells[0].text
                        eligible += 1
                    elif re.match(r"^\d+(?:\.|$)", cells[0].text):
                        position = None
                    continue
                if position is None or len(cells) != 4:
                    continue
                if not (
                    first.quad.rect.x1 < cells[0].quad.rect.x0 <= qty_head.quad.rect.x1
                    and qty_head.quad.rect.x1 < cells[1].quad.rect.x0 < unit_head.quad.rect.x1
                    and re.fullmatch(r"[A-Za-z²³][\w²³./-]*", cells[1].text)
                    and abs(cells[2].quad.rect.x1 - price_head.quad.rect.x1) < 10
                    and abs(cells[3].quad.rect.x1 - total_head.quad.rect.x1) < 10
                ):
                    continue
                oz, position = position, None
                cells = [replace(cell, oz=oz) for cell in cells]
                values = (cells[0].text, cells[2].text, cells[3].text)
            elif columns is not None and is_position:
                eligible += 1
                if len(cells) != 4 or abs(cells[0].quad.rect.x0 - columns[0].x0) > 5:
                    continue
                if any(abs(cells[i].quad.rect.x1 - columns[i].x1) > 10 for i in (1, 2, 3)):
                    continue
                quantity = re.fullmatch(rf"({_NUMBER})\s+[\w²³.]+", cells[1].text)
                if not quantity:
                    continue
                oz = cells[0].text
                values = (quantity[1], cells[2].text, cells[3].text)
            else:
                continue
            result = _price_check(oz, cells, values, "EUR", " EUR")
            if result is None:
                continue
            actual, finding = result
            checked += 1
            ledger = active_split if split else sections
            if ledger and ledger.section and oz in ledger.amounts:
                ledger.amounts[oz] = (actual, replace(cells[-1], oz=oz))
            if finding:
                findings.append(finding)
        if not split:
            position = None
        if not split and columns is None:
            sections.section = ""
            if active_split:
                active_split.ambiguous = True
                active_split = None
    findings.extend(sections.findings)
    for section in split_sections.values():
        findings.extend(section.findings)
    hierarchy, hierarchy_checked, hierarchy_stated = hierarchy_totals(pages)
    findings.extend(hierarchy)
    quantity_findings, counts = _quantity_table(pages)
    findings.extend(quantity_findings)
    coverage = (
        f"EP/GP-Tabellen: {checked + counts['checked']}/{eligible + counts['rows']} "
        "erkannte Positionszeilen geprüft. "
        f"Abschnittssummen: {sections.checked + summary_checked + counts['sums_checked']}/"
        f"{sections.stated + summary_stated + counts['sums']} geprüft. "
        f"Summenhierarchie: {hierarchy_checked}/{hierarchy_stated} geprüft."
    )
    if counts["rows"] or counts["sums"]:
        coverage += (
            f" Mengenzeilen: {counts['blank']} Preisfelder leer, {counts['unit_only']} nur "
            f"Einheitspreis, {counts['ambiguous']} ohne eindeutige OZ; "
            f"{counts['blank_sums']} Summenzeilen leer."
        )
    return findings, coverage
