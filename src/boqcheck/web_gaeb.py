"""Adapt the GAEB checker result to the shared web review contract."""

from . import parse
from .calculation import check_calculations
from .gaeb90 import parse_gaeb90
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
    records = {}
    boq = parse_gaeb90(data, name, records=records)
    if boq.phase != name[-2:]:
        raise ValueError("Dateiendung und Austauschphase in Satz 00 stimmen nicht überein.")
    priced = [item for item in boq.items if item.total is not None or item.unit_price is not None]
    issues = check_calculations(boq)
    skipped = sum(issue.kind == "line" and issue.status == "inconclusive" for issue in issues)
    warnings = []
    if skipped:
        warnings.append(f"{skipped} Positionsbeträge ohne vergleichbare Menge oder Preisangaben.")
    open_sums = sum(issue.kind != "line" and issue.status == "inconclusive" for issue in issues)
    if open_sums:
        warnings.append(f"{open_sums} ausgewiesene Summen sind nicht prüfbar.")
    findings = []
    for issue in issues:
        if issue.status != "mismatch":
            continue
        kind = {"line": "23", "section": "32", "total": "99"}[issue.kind]
        keys = [("21", issue.oz), (kind, issue.oz)] if issue.kind == "line" else [(kind, issue.oz)]
        sources = [
            {
                "record": i,
                "reference": f"Zeile {i} · Satz {code} · {oz or 'Gesamtsumme'}",
                "excerpt": raw,
            }
            for code, oz in keys
            for i, raw in records.get((code, oz), [])
        ]
        findings.append(
            {
                "id": f"BG-{len(findings) + 1:03d}",
                "assessment": "Rechenabweichung",
                "category": "Preisprüfung",
                "method": "GAEB-90-Preisprüfung",
                "evidence": "Ausgewiesene Werte aus der hochgeladenen Datei",
                "impact": "Die Abweichung kann die Angebotssumme ändern.",
                "explanation": issue.explanation,
                "question": "Welcher Betrag ist anzusetzen?",
                "sources": sources,
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
            "arithmetic_checked": len(priced) - skipped,
            "arithmetic_skipped": skipped,
        },
        "records": sorted(
            (i, f"Satz {code} · {oz or 'Gesamtsumme'}", raw)
            for (code, oz), lines in records.items()
            for i, raw in lines
        ),
    }
