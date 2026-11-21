"""Adapt the GAEB checker result to the shared web review contract."""

from . import parse
from .gaeb_checks import check_boq

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
    boq = parse(name, data)
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
                    "reference": f"Position {index}" + (f" · OZ {item.oz}" if item.oz else ""),
                    "excerpt": item.short_text or item.long_text or "Keine Leistungsbeschreibung.",
                }
            )
        findings.append(
            {
                "id": f"BG-{number:03d}",
                "assessment": _TITLES[finding["code"]],
                "method": "GAEB-Struktur- und Preisprüfung",
                "category": "Preisprüfung"
                if finding["code"] == "line_total_mismatch"
                else "LV-Struktur",
                "evidence": "Aus den angegebenen GAEB-Feldern nachvollziehbar",
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
    }
