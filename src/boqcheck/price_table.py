"""Check priced PDF rows with an explicit EUR unit-price and total header."""

import re
from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .contradictions import Finding
from .pdf_calculation import _NUMBER
from .pdf_extract import Line
from .pdf_hierarchy_totals import hierarchy_totals
from .pdf_subtotals import SectionTotals


def table_prices(pages: list[list[Line]]) -> tuple[list[Finding], str]:
    """Compare right-aligned EUR prices on the same baseline as an item and quantity.

    :param pages: source lines in reading order, grouped by physical page.
    :returns: source-grounded discrepancies and the number of verified item rows.
    """
    findings = []
    checked = eligible = 0
    position = None
    sections = SectionTotals()
    split_sections: dict[str, SectionTotals] = {}
    active_split = None
    summary_checked = summary_stated = 0
    for page in pages:
        rows: list[list[Line]] = []
        for line in sorted(page, key=lambda cell: cell.quad.rect.y0):
            if not rows or line.quad.rect.y0 - rows[-1][0].quad.rect.y0 > 1.25:
                rows.append([])
            rows[-1].append(line)
        columns = None
        split_header = None
        split = False
        summary = False
        for row in rows:
            row = sorted(row, key=lambda line: line.quad.rect.x0)
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
            if any(len(v) > 18 or not re.fullmatch(_NUMBER, v) for v in values):
                continue
            qty, price, actual = [Decimal(v.replace(".", "").replace(",", ".")) for v in values]
            with localcontext() as context:
                context.prec = 50
                expected = (qty * price).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            checked += 1
            ledger = active_split if split else sections
            if ledger and ledger.section and oz in ledger.amounts:
                ledger.amounts[oz] = (actual, replace(cells[-1], oz=oz))
            if actual != expected:
                findings.append(
                    Finding(
                        "table_price",
                        (tuple(cells),),
                        f"OZ {oz}: {qty} × {price} EUR = {expected} EUR. "
                        f"Ausgewiesener Positionsbetrag: {actual} EUR.",
                        "Welcher Positionsbetrag ist anzusetzen?",
                        "conflict",
                    )
                )
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
    return findings, (
        f"EP/GP-Tabellen: {checked}/{eligible} erkannte Positionszeilen geprüft. "
        f"Abschnittssummen: {sections.checked + summary_checked}/"
        f"{sections.stated + summary_stated} geprüft. "
        f"Summenhierarchie: {hierarchy_checked}/{hierarchy_stated} geprüft."
    )
