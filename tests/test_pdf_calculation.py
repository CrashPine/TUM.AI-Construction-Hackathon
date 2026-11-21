"""Check a typed model proposal through PDF extraction, validation and export."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest

from boqcheck import semantic
from boqcheck.numeric_roles import number_roles
from boqcheck.pdf_calculation import evaluate_price, price_groups
from boqcheck.pdf_extract import Line, extract
from boqcheck.price_table import table_prices
from boqcheck.review_pdf import review_pdf
from boqcheck.semantic import SemanticConfig


@pytest.mark.parametrize(
    ("total", "unit", "operand", "checked", "mismatch", "expected"),
    [
        ("12,34", "m", "qty", 1, True, "12.35"),
        ("12,35", "m", "qty", 1, False, ""),
        ("12,34", "kg", "qty", 0, False, ""),
        ("12,34", "m", "total", 0, False, ""),
        ("1.234,49", "cm", "qty", 1, True, "1234.50"),
        ("1.234,50", "cm", "qty", 1, False, ""),
        ("12,34", "cm2", "qty", 0, False, ""),
    ],
)
def test_price_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    total: str,
    unit: str,
    operand: str,
    checked: int,
    mismatch: bool,
    expected: str,
) -> None:
    """Require a matching source unit, exact operands and half-up cents.

    :param tmp_path: isolated output root.
    :param monkeypatch: substitute the model transport.
    :param total: stated euro amount.
    :param unit: price basis unit.
    :param operand: token used as the first factor.
    :param checked: expected number of verified expressions.
    :param mismatch: whether the export must contain a discrepancy.
    :param expected: normalized expected total when a discrepancy exists.
    """
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text(
            (55, 55),
            f"01.01.0010. Rohr\nMenge: 1.000,0 m\n"
            f"EP: 1,2345 EUR / 100 {unit}\nGesamtbetrag: {total} EUR",
        )
        data = pdf.tobytes()

    def propose(config: SemanticConfig, payload: dict) -> list:
        """Return a typed proposal for every offered target.

        :param config: local transport configuration.
        :param payload: source fields selected by the reviewer.
        :returns: model response records.
        """
        return [
            {
                "kind": "calculation",
                "target": t["total"],
                "expr": {
                    "op": "div",
                    "args": [{"op": "mul", "args": [t[operand], t["price"]]}, t["basis"]],
                },
            }
            for t in payload.get("price_fields", [])
        ]

    monkeypatch.setattr(semantic, "_request", propose)
    result = review_pdf("price.pdf", data, tmp_path / "out", semantic=SemanticConfig("", "test"))
    assert f"{checked}/1 beschriftete" in result["semantic_coverage"]
    assert (
        "Zahlenrollen: 3 Eingabe, 1 abgeleitet, 1 Kennung, 0 Spezifikation, 0 unklar; "
        f"{4 - 4 * checked} Werte ungeprüft"
    ) in result["semantic_coverage"]
    assert bool(result["findings"]) == mismatch
    if mismatch:
        (finding,) = result["findings"]
        assert len(finding["sources"]) == 3
        assert f"{expected} EUR" in finding["explanation"]
        if unit == "cm":
            assert (
                "100000,0 cm".replace(",", ".") in finding["explanation"]
                or "100000 cm" in finding["explanation"]
            )
        assert f"Gesamtbetrag: {total} EUR" in Path(
            tmp_path / "out/price.contradictions.md"
        ).read_text("utf8")


def test_real_ep_gp_table() -> None:
    """Verify real table geometry and detect a changed total in memory."""
    path = Path(__file__).resolve().parents[1] / "data/raw/Angebot AN24-0305.pdf"
    with pymupdf.open(path) as document:
        pages, _ = extract(document)
    findings, coverage = table_prices(pages)
    assert not findings
    assert "274/274" in coverage
    page = pages[2]
    index = next(i for i, line in enumerate(page) if line.text == "4.800,00")
    page[index] = replace(page[index], text="4.800,01")
    findings, _ = table_prices([page])
    (finding,) = findings
    assert "4800.01" in finding.explanation and "4800.00" in finding.explanation


def test_split_price_rows_across_pages() -> None:
    """Verify both the whole priced LV and an altered carry-over row after a page break."""
    path = Path(__file__).resolve().parents[1] / "data/raw/Abgabe LV.pdf"
    with pymupdf.open(path) as document:
        pages, _ = extract(document)
    findings, coverage = table_prices(pages)
    assert not findings
    assert "248/248" in coverage
    page = pages[30]
    index = next(i for i, line in enumerate(page) if line.text == "18.200,00")
    page[index] = replace(page[index], text="18.200,01")
    findings, _ = table_prices(pages[29:31])
    (finding,) = findings
    assert "18200.01" in finding.explanation and "18200.00" in finding.explanation
    assert all(line.page == 30 and line.oz == "3.1.3" for line in finding.passages[0])
    page[:] = [replace(line, text="USD") if line.text == "EUR" else line for line in page]
    assert not table_prices(pages[29:31])[0]


def _lines(*texts: str) -> dict[str, Line]:
    r"""Build source lines of one item on one page.

    :param \*texts: line texts in reading order.
    :returns: lines keyed like the semantic reviewer.
    """
    quad = pymupdf.Rect(0, 0, 1, 1).quad
    return {f"L{i}": Line(0, None, "01.01.0010", t, quad) for i, t in enumerate(texts, 1)}


def test_number_roles() -> None:
    """Give every standalone number one role, exact span and value only when unambiguous."""
    sources = _lines(
        "01.01.0010. Rohr DN100 nach DIN EN 1992-1-1, Länge 6 m2, [NUMMER_001] -5 Stück 7",
        "Menge: 1.000,0 m",
        "EP: 1,2345 EUR / 100 cm",
        "Gesamtbetrag: 12,34 EUR",
    )
    tokens = number_roles(sources)
    assert [(t.id, t.role, t.raw, t.value) for t in tokens] == [
        ("L1.c0", "identifier", "01.01.0010", None),
        ("L1.c19", "specification", "100", Decimal(100)),
        ("L1.c35", "identifier", "1992-1-1", None),
        ("L1.c51", "specification", "6", Decimal(6)),
        ("L1.c70", "unknown", "-5", None),
        ("L1.c79", "unknown", "7", Decimal(7)),
        ("L2.qty", "input", "1.000,0", Decimal("1000.0")),
        ("L3.price", "input", "1,2345", Decimal("1.2345")),
        ("L3.basis", "input", "100", Decimal(100)),
        ("L4.total", "derived", "12,34", Decimal("12.34")),
    ]
    assert all(sources[t.source].text[t.start : t.end] == t.raw for t in tokens)


def test_price_expressions() -> None:
    """Accept only allowlisted trees equal to quantity times price per basis."""
    sources = _lines("01.01.0010. Rohr", "Menge: 10 m", "EP: 2 EUR / 100 cm", "GB: 20,00 EUR")
    (group,) = price_groups(sources).values()
    q, p, b, t = (group[0][k] for k in ("qty", "price", "basis", "total"))

    def tree(op: str, *args: object) -> dict:
        r"""Build one expression node.

        :param op: operator name.
        :param \*args: operand trees or token IDs.
        :returns: expression node.
        """
        return {"op": op, "args": list(args)}

    accepted = [
        tree("div", tree("mul", q, p), b),
        tree("div", tree("mul", p, q), b),
        tree("mul", q, tree("div", p, b)),
    ]
    rejected = [
        tree("div", tree("mul", p, b), q),
        tree("mul", tree("mul", q, p), b),
        tree("div", tree("mul", q, q), b),
        tree("div", tree("mul", q, p), "L9.basis"),
        tree("div", tree("mul", q, p), t),
        tree("div", tree("mul", q, p), "100"),
        tree("div", tree("mul", q, p), 100),
        tree("div", tree("add", q, p), b),
        tree("sub", tree("add", tree("div", tree("mul", q, p), b), q), q),
        {"op": "div", "args": [tree("mul", q, p), b], "eval": "1"},
        tree("div", tree("mul", q, p, p), b),
        "__import__('os')",
    ]
    deep: object = q
    for _ in range(50):
        deep = tree("mul", deep, b)
    rejected.append(deep)
    assert all(evaluate_price(group, e) == (True, None) for e in accepted)
    assert not any(evaluate_price(group, e)[0] for e in rejected)
