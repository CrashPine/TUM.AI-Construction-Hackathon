"""Check a typed model proposal through PDF extraction, validation and export."""

from pathlib import Path

import pymupdf
import pytest

from boqcheck import semantic
from boqcheck.review_pdf import review_pdf
from boqcheck.semantic import SemanticConfig


@pytest.mark.parametrize(
    ("total", "unit", "operand", "checked", "mismatch"),
    [
        ("12,34", "m", "qty", 1, True),
        ("12,35", "m", "qty", 1, False),
        ("12,34", "kg", "qty", 0, False),
        ("12,34", "m", "total", 0, False),
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
) -> None:
    """Require a matching source unit, exact operands and half-up cents.

    :param tmp_path: isolated output root.
    :param monkeypatch: substitute the model transport.
    :param total: stated euro amount.
    :param unit: price basis unit.
    :param operand: token used as the first factor.
    :param checked: expected number of verified expressions.
    :param mismatch: whether the export must contain a discrepancy.
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
    assert bool(result["findings"]) == mismatch
    if mismatch:
        (finding,) = result["findings"]
        assert len(finding["sources"]) == 3
        assert "12.35 EUR" in finding["explanation"]
        assert "12.34 EUR" in Path(tmp_path / "out/price.contradictions.md").read_text("utf8")
