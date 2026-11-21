"""Exercise subtotal membership, coverage and source evidence on the priced PDFs."""

from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from boqcheck.pdf_extract import extract
from boqcheck.price_table import table_prices

_RAW = Path(__file__).resolve().parents[1] / "data/raw"


def test_summary_cent_difference() -> None:
    """Detect a changed keyed summary and keep all member prices as source evidence."""
    with pymupdf.open(_RAW / "Abgabe LV.pdf") as document:
        pages, _ = extract(document)
    findings, coverage = table_prices(pages)
    assert "23/23" in coverage and not findings
    page = pages[-1]
    i = next(i for i, cell in enumerate(page) if cell.text == "4.353,60")
    page[i] = replace(page[i], text="4.353,61")
    findings, _ = table_prices(pages)
    (finding,) = findings
    assert finding.kind == "section_total" and "4353.61" in finding.explanation
    assert "4353.60" in finding.explanation and finding.passages[0][-1] == page[i]
    assert len(finding.passages) == 10


@pytest.mark.parametrize(
    ("label", "checked", "difference"),
    [
        ("Bedarfsposition mit GP", 14, False),
        ("Bedarfsposition ohne GP", 14, True),
        ("Bedarfsposition", 13, False),
    ],
)
def test_optional_section_member(label: str, checked: int, difference: bool) -> None:
    """Use only explicit membership instructions when summing an optional price.

    :param label: review marker applied to a real position in memory.
    :param checked: expected completed subtotal checks.
    :param difference: whether the retained source subtotal now differs.
    """
    with pymupdf.open(_RAW / "Angebot AN24-0305.pdf") as document:
        pages, _ = extract(document)
    page = pages[1]
    i = next(i for i, cell in enumerate(page) if cell.text == "Beweissicherung durchführen")
    page[i] = replace(page[i], text=label)
    findings, coverage = table_prices(pages)
    assert f"Abschnittssummen: {checked}/14" in coverage
    assert bool(findings) == difference
    if difference:
        (finding,) = findings
        assert "92707.50" in finding.explanation and "93387.50" in finding.explanation
        assert all(line.oz != "1.1.170" for passage in finding.passages[1:] for line in passage)
