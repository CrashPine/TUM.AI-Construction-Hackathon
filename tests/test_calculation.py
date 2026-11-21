"""Tests of the calculation check on the priced GAEB 90 samples and on synthetic BoQs."""

from decimal import Decimal
from pathlib import Path

import pytest

from boqcheck import parse
from boqcheck.calculation import check_calculations
from boqcheck.model import BoQ, Item, Section

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def _boq(name: str) -> BoQ:
    """Parse a sample file.

    :param name: file name in ``data/raw``.
    :returns: the parsed BoQ.
    """
    return parse(name, (RAW / name).read_bytes())


def _item(oz: str, quantity: str | None, unit_price: str | None, total: str | None) -> Item:
    """Build a priced item.

    :param oz: the Ordnungszahl.
    :param quantity: the quantity, or None.
    :param unit_price: the unit price, or None.
    :param total: the line total, or None.
    :returns: the item.
    """

    def number(value: str | None) -> Decimal | None:
        """Convert an optional string to a Decimal.

        :param value: the number as text, or None.
        :returns: the Decimal, or None.
        """
        return None if value is None else Decimal(value)

    return Item(
        oz, "", "", number(quantity), "St", unit_price=number(unit_price), total=number(total)
    )


def test_stbalv_section_totals_exceed_their_items_where_an_oz_is_missing() -> None:
    """Sections 08 and 08.01 state 982.20 more than their items and lack 08.01.0003."""
    findings = check_calculations(_boq("StBALV23040.D86"))
    assert [(f.kind, f.oz, f.status) for f in findings] == [
        ("section", "08", "mismatch"),
        ("section", "08.01", "mismatch"),
    ]
    assert {f.stated - f.computed for f in findings} == {Decimal("982.20")}
    assert "08.01.0003" in findings[1].explanation
    assert "08.01.0003" in findings[0].explanation


@pytest.mark.parametrize(
    "name",
    ["Angebot AN24-0305.D84", "[ORT_024] LV24069.D86", "8209.003_Leistungsverzeichnis_leer.D83"],
)
def test_consistent_or_unpriced_files_have_no_findings(name: str) -> None:
    """Files whose sums match, or that have no prices, give no findings.

    :param name: file name in ``data/raw``.
    """
    assert check_calculations(_boq(name)) == []


def test_line_total_is_rounded_half_up() -> None:
    """0.5 × 0.25 = 0.125 rounds half up to 0.13."""
    ok = BoQ("x", None, (), (_item("1", "0.5", "0.25", "0.13"),))
    assert check_calculations(ok) == []
    wrong = BoQ("x", None, (), (_item("1", "0.5", "0.25", "0.12"),))
    [finding] = check_calculations(wrong)
    assert (finding.kind, finding.oz, finding.status) == ("line", "1", "mismatch")
    assert (finding.stated, finding.computed) == (Decimal("0.12"), Decimal("0.13"))


def test_line_with_a_missing_operand_is_inconclusive() -> None:
    """A priced line without quantity or total cannot be checked."""
    boq = BoQ("x", None, (), (_item("1", None, "2", "4"), _item("2", "2", "2", None)))
    findings = check_calculations(boq)
    assert [(f.kind, f.oz, f.status) for f in findings] == [
        ("line", "1", "inconclusive"),
        ("line", "2", "inconclusive"),
    ]


def test_line_findings_identify_the_original_item_occurrence() -> None:
    """Duplicate OZs retain distinct 1-based indexes, including after a correct item."""
    items = (
        _item("01.1", "1", "1", "1"),
        _item("01.1", "1", "1", "2"),
        _item("02.1", None, "2", "4"),
    )
    findings = check_calculations(BoQ("x", None, (Section("01", "", Decimal("4")),), items))
    assert [(f.kind, f.status, f.item_index) for f in findings] == [
        ("line", "mismatch", 2),
        ("line", "inconclusive", 3),
        ("section", "mismatch", None),
    ]


def test_sum_with_a_missing_item_total_is_inconclusive() -> None:
    """A sum over an item without a total cannot be checked."""
    items = (_item("01.1", "1", "5", "5"), _item("01.2", "1", None, None))
    boq = BoQ("x", None, (Section("01", "", Decimal("9")),), items, Decimal("9"))
    findings = check_calculations(boq)
    assert [(f.kind, f.oz, f.status, f.computed) for f in findings] == [
        ("section", "01", "inconclusive", None),
        ("total", "", "inconclusive", None),
    ]


def test_zero_stated_total_with_priced_items_is_inconclusive() -> None:
    """A stated zero over priced items may be a blank, not an error."""
    items = (_item("01.1", "1", "5", "5"),)
    boq = BoQ("x", None, (Section("01", "", Decimal("0")), Section("02", "", Decimal("0"))), items)
    [finding] = check_calculations(boq)
    assert (finding.kind, finding.oz, finding.status) == ("section", "01", "inconclusive")


def test_grand_total_mismatch_and_gap_hint() -> None:
    """A grand total mismatch names the skipped OZ in a numbering in tens."""
    items = (_item("01.0010", "1", "5", "5"), _item("01.0030", "1", "5", "5"))
    boq = BoQ("x", None, (Section("01", "", Decimal("10")),), items, Decimal("15"))
    [finding] = check_calculations(boq)
    assert (finding.kind, finding.oz, finding.status) == ("total", "", "mismatch")
    assert (finding.stated, finding.computed) == (Decimal("15"), Decimal("10"))
    assert "Lücken in der OZ-Nummerierung (01.0020)" in finding.explanation
    assert "kein Nachweis fehlender Leistungen" in finding.explanation


def test_sum_with_a_provisional_item_is_inconclusive() -> None:
    """Whether a Bedarfsposition counts in a sum is unknown, so the sum is not judged."""
    priced = _item("01.1", "1", "5", "5")
    provisional = Item(
        "01.2", "", "", Decimal("1"), "St", True, unit_price=Decimal("5"), total=Decimal("5")
    )
    boq = BoQ("x", None, (Section("01", "", Decimal("5")),), (priced, provisional))
    [finding] = check_calculations(boq)
    assert (finding.kind, finding.status) == ("section", "inconclusive")


def test_provisional_line_with_zero_total_is_inconclusive() -> None:
    """A Bedarfsposition may state a zero total on purpose, so it is not a mismatch."""
    item = Item(
        "01.1", "", "", Decimal("2"), "St", True, unit_price=Decimal("5"), total=Decimal("0")
    )
    [finding] = check_calculations(BoQ("x", None, (), (item,)))
    assert (finding.kind, finding.status) == ("line", "inconclusive")


def test_section_covers_only_its_own_ozs() -> None:
    """Section 1 does not include the items of section 10."""
    items = (_item("1.1", "1", "5", "5"), _item("10.1", "1", "7", "7"))
    sections = (Section("1", "", Decimal("5")), Section("10", "", Decimal("7")))
    assert check_calculations(BoQ("x", None, sections, items)) == []
