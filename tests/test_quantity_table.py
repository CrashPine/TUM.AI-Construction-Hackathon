"""Check the PDF price table with a separate quantity row and no currency in its header."""

from pathlib import Path

import pymupdf
import pytest

from boqcheck.pdf_extract import Line, extract
from boqcheck.price_table import table_prices

_RAW = Path(__file__).resolve().parents[1] / "data/raw"
# Left edges of the bold 10 pt header cells in LV_02_PVC_Fussbodenbelag.pdf.
_HEADER = {
    "OZ": 54,
    "Leistungsbeschreibung": 125,
    "Menge ME": 314,
    "Einheitspreis": 391,
    "Gesamtbetrag": 469,
}


def _pages(*rows: tuple[str, ...]) -> list[list[Line]]:
    r"""Print rows under the measured header geometry and extract them.

    A one-cell row such as ``1.1.10. Fliesen`` starts a position at the OZ column. In longer
    rows, the first cell is a quantity in the Menge ME column or a ``Summe`` label in the
    OZ column; the last cell ends at the Gesamtbetrag edge and the cell before it, if any, at the
    Einheitspreis edge.

    :param \*rows: cell texts per row, top to bottom.
    :returns: extracted cells of the single page.
    """
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        edges = {}
        for text, x in _HEADER.items():
            page.insert_text((x, 133), text, fontname="hebo", fontsize=10)
            edges[text] = x + pymupdf.get_text_length(text, "hebo", 10)
        for y, (first, *fields) in zip(range(160, 800, 16), rows, strict=False):
            page.insert_text((321 if fields and first[0].isdigit() else 54, y), first, fontsize=10)
            for text, column in zip(fields[::-1], ("Gesamtbetrag", "Einheitspreis"), strict=False):
                x = edges[column] - pymupdf.get_text_length(text, fontsize=10)
                page.insert_text((x, y), text, fontsize=10)
        with pymupdf.open(stream=pdf.tobytes()) as document:
            return extract(document)[0]


@pytest.mark.parametrize(
    ("name", "coverage"),
    [
        (
            "LV_02_PVC_Fussbodenbelag.pdf",
            "EP/GP-Tabellen: 0/11 erkannte Positionszeilen geprüft. Abschnittssummen: 0/2 geprüft. "
            "Summenhierarchie: 0/0 geprüft. Mengenzeilen: 7 Preisfelder leer, 4 nur "
            "Einheitspreis, 0 ohne eindeutige OZ; 2 Summenzeilen leer.",
        ),
        (
            "Leistungsverzeichnis.pdf",
            "EP/GP-Tabellen: 0/274 erkannte Positionszeilen geprüft. Abschnittssummen: 0/21 "
            "geprüft. Summenhierarchie: 0/0 geprüft. Mengenzeilen: 274 Preisfelder leer, 0 nur "
            "Einheitspreis, 0 ohne eindeutige OZ; 21 Summenzeilen leer.",
        ),
        (
            "LV_14_Sanitaeranlage.pdf",
            "EP/GP-Tabellen: 0/168 erkannte Positionszeilen geprüft. Abschnittssummen: 0/12 "
            "geprüft. Summenhierarchie: 0/0 geprüft. Mengenzeilen: 149 Preisfelder leer, 19 nur "
            "Einheitspreis, 168 ohne eindeutige OZ; 12 Summenzeilen leer.",
        ),
    ],
)
def test_unpriced_samples(name: str, coverage: str) -> None:
    """Count blank, unit-price-only and unattributed rows of real tenders without a finding.

    :param name: sample PDF with this layout.
    :param coverage: expected coverage text.
    """
    with pymupdf.open(_RAW / name) as document:
        pages, _ = extract(document)
    assert table_prices(pages) == ([], coverage)


def test_row_classes() -> None:
    """Compute only filled rows with a unique OZ and report the others by class."""
    pages = _pages(
        ("2,000 m2", "10,00", "20,01"),
        ("1.1.10. Fliesen",),
        ("2,000 m2", "10,00", "20,01"),
        ("1.1.20. Sockel",),
        ("3,000 m", "1,50", "4,50"),
        ("1.1.30. Zulage",),
        ("1,000 St", "5,00", "Nur Einh.-Pr."),
        ("1.1.40. Fugen",),
        ("1,000 m", "1,00", "9,99"),
        ("1,000 m", "1,00", "9,99"),
        ("1.1.50. Abdeckung",),
        ("4,000 m2", "........", "........"),
        ("1.1.60. Baustelle",),
        ("1,000 psch", "........"),
    )
    findings, coverage = table_prices(pages)
    assert coverage == (
        "EP/GP-Tabellen: 2/8 erkannte Positionszeilen geprüft. Abschnittssummen: 0/0 geprüft. "
        "Summenhierarchie: 0/0 geprüft. Mengenzeilen: 2 Preisfelder leer, 1 nur Einheitspreis, "
        "3 ohne eindeutige OZ; 0 Summenzeilen leer."
    )
    (finding,) = findings
    assert finding.kind == "table_price"
    assert finding.explanation == (
        "OZ 1.1.10: 2.000 × 10.00 je Mengeneinheit (m2) = 20.00. "
        "Ausgewiesener Positionsbetrag: 20.01."
    )
    ((quantity, price, total),) = finding.passages
    assert (quantity.text, price.text, total.text) == ("2,000 m2", "10,00", "20,01")
    assert {quantity.oz, price.oz, total.oz} == {"1.1.10"}


@pytest.mark.parametrize(
    ("first", "total", "checked", "explanation"),
    [
        ((), "24,50", 1, None),
        (
            (),
            "24,51",
            1,
            "Abschnitt 1.1: 20.00 (1.1.10) + 4.50 (1.1.20) = 24.50. Ausgewiesen: 24.51. "
            "Ohne Gesamtbetrag: 1.1.30.",
        ),
        ((("1.1.5. Hinweis",),), "24,51", 0, None),
        ((("1,000 St", "1,00", "1,00"),), "24,51", 0, None),
        ((("1.1.5. Bedarfsposition mit GB",), ("1,000 St", "1,00", "1,00")), "25,51", 0, None),
    ],
)
def test_section_total(
    first: tuple[tuple[str, ...], ...], total: str, checked: int, explanation: str | None
) -> None:
    """Sum the stated totals under the OZ of a Summe row, without unit-price-only rows.

    :param first: rows before the section: a position without a quantity row, a row before
        any OZ or a Bedarfsposition, each of which leaves the membership open.
    :param total: stated section total.
    :param checked: expected completed section checks.
    :param explanation: expected discrepancy, if any.
    """
    pages = _pages(
        *first,
        ("1.1.10. Fliesen",),
        ("2,000 m2", "10,00", "20,00"),
        ("1.1.20. Sockel",),
        ("3,000 m", "1,50", "4,50"),
        ("1.1.30. Zulage",),
        ("1,000 St", "5,00", "Nur Einh.-Pr."),
        ("Summe 1.1.", total),
    )
    findings, coverage = table_prices(pages)
    assert f"Abschnittssummen: {checked}/1 geprüft." in coverage
    assert [finding.explanation for finding in findings] == [explanation] * bool(explanation)
    if explanation:
        stated, *members, marker = findings[0].passages
        assert [cell.text for cell in stated] == ["Summe 1.1.", total]
        assert [line.text for (line,) in members] == ["20,00", "4,50"]
        assert marker[-1].text == "Nur Einh.-Pr."
