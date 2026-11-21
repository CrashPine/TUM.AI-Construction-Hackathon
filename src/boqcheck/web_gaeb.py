"""Adapt the GAEB checker result to the shared web review contract."""

from . import parse
from .calculation import CalculationFinding, check_calculations
from .gaeb90 import ItemRecords, parse_gaeb90
from .gaeb_checks import check_boq
from .model import BoQ

_TITLES = {
    "duplicate_oz": "Doppelte OZ",
    "missing_fields": "Pflichtfelder fehlen",
    "invalid_numbers": "Ungültiger Zahlenwert",
    "line_total_mismatch": "Abweichender Gesamtbetrag",
}
_IMPACTS = {
    "duplicate_oz": "Gleiche OZ erschweren die eindeutige Zuordnung von Preisen und Leistungen.",
    "missing_fields": "Die betroffene Position ist nur eingeschränkt kalkulierbar.",
    "invalid_numbers": "Die betroffenen Werte sind für die Kalkulation nicht verwendbar.",
    "line_total_mismatch": "Der Positionsbetrag kann die Angebotssumme verändern.",
}


def _explanation(finding: dict) -> str:
    """Explain the check outcome and quote the fields that triggered it.

    :param finding: one finding from the GAEB checker.
    :returns: German explanation.
    """
    code = finding["code"]
    if code == "duplicate_oz":
        return "Mehrere Positionen haben dieselbe Ordnungszahl."
    if code == "missing_fields":
        return "Fehlende Felder: " + ", ".join(finding["fields"])
    if code == "invalid_numbers":
        return ", ".join(f"{key}: {value}" for key, value in finding["values"].items())
    return (
        f"Menge {finding['quantity']} × EP {finding['unit_price']} ÷ "
        f"Preisbasis {finding['price_basis']}; erwartet {finding['expected']}, "
        f"angegeben {finding['actual']}."
    )


def review_x83(name: str, data: bytes) -> dict:
    """Import one X83 and prepare structural findings for the web workflow.

    :param name: uploaded file name.
    :param data: uploaded XML bytes.
    :returns: findings with position references and arithmetic coverage.
    """
    return review_positions(parse(name, data))


def review_positions(boq: BoQ, references: list[str] | None = None) -> dict:
    """Prepare the shared structural and arithmetic report.

    :param boq: normalized positions.
    :param references: optional sheet and row labels in source order.
    :returns: shared web review.
    """
    report = check_boq(boq)
    findings = []
    for number, finding in enumerate(report["findings"], 1):
        indices = finding["items"] if "items" in finding else [finding["item"]]
        sources = []
        for index in indices:
            item = boq.items[index - 1]
            sources.append(
                {
                    "position": index,
                    "reference": (references[index - 1] if references else f"Position {index}")
                    + (f" · OZ {item.oz}" if item.oz else ""),
                    "excerpt": item.short_text or item.long_text or "Keine Leistungsbeschreibung.",
                }
            )
        findings.append(
            {
                "id": f"BG-{number:03d}",
                "assessment": _TITLES[finding["code"]],
                "method": "Struktur- und Preisprüfung",
                "category": "Preisprüfung"
                if finding["code"] == "line_total_mismatch"
                else "LV-Struktur",
                "evidence": "Aus den angegebenen Quellfeldern nachvollziehbar",
                "impact": _IMPACTS[finding["code"]],
                "explanation": _explanation(finding),
                "question": "",
                "sources": sources,
            }
        )
    return {
        "findings": findings,
        "warnings": report["warnings"],
        "gaeb": report,
        "positions": boq.items,
        "sheet_references": references,
    }


def review_legacy(name: str, data: bytes) -> dict:
    """Review one GAEB 90 exchange file and retain the actual record for each price.

    :param name: uploaded filename with phase suffix.
    :param data: original file bytes.
    :returns: shared review result with physical line numbers and source records.
    :raises ValueError: when the phase marker and extension differ.
    """
    records: dict[tuple[str, str], list[tuple[int, str]]] = {}
    item_records: list[ItemRecords] = []
    boq = parse_gaeb90(data, name, records=records, item_records=item_records)
    if boq.phase != name[-2:]:
        raise ValueError("Dateiendung und Austauschphase in Satz 00 stimmen nicht überein.")
    priced = [item for item in boq.items if item.total is not None or item.unit_price is not None]
    issues = check_calculations(boq)
    line_skipped = sum(issue.kind == "line" and issue.status == "inconclusive" for issue in issues)
    unpriced = len(boq.items) - len(priced) if boq.phase != "83" or priced else 0
    skipped = line_skipped + unpriced
    warnings = [
        "Experimentell: Die Preisprüfung nimmt an, dass der Einheitspreis für genau eine "
        "Mengeneinheit gilt. Positionsarten und Preisbasen sind nicht vollständig erkannt."
    ]
    if skipped:
        warnings.append(
            f"{skipped} Positionsprüfungen wegen fehlender Mengen oder Preise übersprungen."
        )
    open_sums = sum(issue.kind != "line" and issue.status == "inconclusive" for issue in issues)
    if open_sums:
        warnings.append(f"{open_sums} ausgewiesene Summen sind nicht prüfbar.")
    findings = []
    for duplicate in check_boq(boq)["findings"]:
        if duplicate["code"] != "duplicate_oz":
            continue
        findings.append(
            {
                "id": f"BG-{len(findings) + 1:03d}",
                "assessment": _TITLES["duplicate_oz"],
                "category": "LV-Struktur",
                "method": "GAEB-90-Strukturprüfung",
                "evidence": "Gleiche Ordnungszahl in mehreren GAEB-90-Positionssätzen",
                "impact": _IMPACTS["duplicate_oz"],
                "explanation": _explanation(duplicate),
                "question": "Welche Ordnungszahl gilt für die betroffenen Positionen?",
                "sources": [
                    _legacy_source(item_records[index - 1].position, boq.items[index - 1].oz)
                    for index in duplicate["items"]
                ],
            }
        )
    for issue in issues:
        if issue.kind == "line" and issue.status == "inconclusive":
            continue
        mismatch = issue.status == "mismatch"
        findings.append(
            {
                "id": f"BG-{len(findings) + 1:03d}",
                "assessment": "Mögliche Rechenabweichung" if mismatch else "Summe nicht prüfbar",
                "category": "Preisprüfung" if mismatch else "Prüfumfang",
                "method": "GAEB-90-Preisprüfung",
                "evidence": "Ausgewiesene Werte aus der hochgeladenen Datei",
                "impact": (
                    "Bei zutreffender Zuordnung kann sich die Angebotssumme ändern."
                    if mismatch
                    else "Die Summe lässt sich mit den verfügbaren Positionsbeträgen nicht prüfen."
                ),
                "explanation": issue.explanation
                + (
                    " Positionsarten und Preisbasen sind nicht vollständig erkannt; "
                    "der Vergleich ist vorläufig."
                    if mismatch
                    else ""
                ),
                "question": (
                    "Welche Positionsart und Preisbasis gelten, und welcher Betrag ist anzusetzen?"
                    if mismatch
                    else "Welche Werte sind für die Summenprüfung maßgeblich?"
                ),
                "sources": _calculation_sources(issue, boq, records, item_records),
            }
        )
    return {
        "positions": boq.items,
        "findings": findings,
        "warnings": warnings,
        "gaeb": {
            "version": "90",
            "phase": boq.phase,
            "items": len(boq.items),
            "arithmetic_checked": len(priced) - line_skipped,
            "arithmetic_skipped": skipped,
        },
        "records": sorted(
            (i, f"Satz {code} · {oz or 'Gesamtsumme'}", raw)
            for (code, oz), lines in records.items()
            for i, raw in lines
        ),
    }


def _legacy_source(record: tuple[int, str], oz: str) -> dict:
    """Describe one physical GAEB 90 record as a finding source.

    :param record: 1-based line number and its original text.
    :param oz: item or section OZ, or empty for a grand total.
    :returns: source reference and verbatim excerpt.
    """
    number, raw = record
    return {
        "record": number,
        "reference": f"Zeile {number} · Satz {raw[:2]} · {oz or 'Gesamtsumme'}",
        "excerpt": raw,
    }


def _calculation_sources(
    issue: CalculationFinding,
    boq: BoQ,
    records: dict[tuple[str, str], list[tuple[int, str]]],
    item_records: list[ItemRecords],
) -> list[dict]:
    """Select the effective source records used for a calculation.

    :param issue: line, section or grand-total finding.
    :param boq: parsed BoQ with items in source order.
    :param records: all physical records grouped by type and OZ.
    :param item_records: effective position and price records in item order.
    :returns: source references for the stated value and its operands.
    :raises RuntimeError: if a line finding has no original item index.
    """
    if issue.kind == "line":
        if issue.item_index is None:
            raise RuntimeError("Line calculation finding has no item index.")
        item = item_records[issue.item_index - 1]
        lines = [item.position]
        if item.price is not None and item.price != item.position:
            lines.append(item.price)
        return [_legacy_source(line, issue.oz) for line in lines]
    kind = "32" if issue.kind == "section" else "99"
    sources = [_legacy_source(records[(kind, issue.oz)][-1], issue.oz)]
    for item, source in zip(boq.items, item_records, strict=True):
        if issue.kind == "total" or item.oz.startswith(issue.oz + "."):
            sources.append(_legacy_source(source.price or source.position, item.oz))
    return sources
