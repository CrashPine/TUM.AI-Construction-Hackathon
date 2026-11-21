"""Tests for the GAEB 90 parser, on the sample files and on synthetic records."""

import functools
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from boqcheck import parse
from boqcheck.gaeb90 import parse_gaeb90
from boqcheck.model import BoQ

RAW = Path(__file__).parents[1] / "data" / "raw"
D83 = "8209.003_Leistungsverzeichnis_leer.D83"
STBA = "StBALV23040.D86"
LV = "[ORT_024] LV24069.D86"
ANGEBOT = "Angebot AN24-0305.D84"


@functools.cache
def _boq(name: str) -> BoQ:
    """Parse a sample file once for all tests.

    :param name: the file name in data/raw.
    :returns: the parsed BoQ.
    """
    return parse(name, (RAW / name).read_bytes())


def _records(*records: str) -> bytes:
    r"""Build a synthetic GAEB 90 file with the OZ mask 1122PPPPI.

    :param \*records: the records after the header, without line numbers.
    :returns: the file content with 80-character CRLF lines.
    """
    header = "00        83L".ljust(62) + "1122PPPPI90"
    lines = [f"{r:<74.74}{n:06d}" for n, r in enumerate((header, *records), 1)]
    return "\r\n".join(lines).encode("cp850") + b"\r\n"


@pytest.mark.parametrize(
    ("name", "phase", "items", "sections"),
    [(D83, "83", 159, 28), (STBA, "86", 249, 34), (LV, "86", 197, 35), (ANGEBOT, "84", 274, 21)],
)
def test_counts(name: str, phase: str, items: int, sections: int):
    """parse() reads every 21 record and every 11 record, or 32 record if a file has no 11.

    :param name: the sample file.
    :param phase: the phase in record 00.
    :param items: the number of 21 records.
    :param sections: the number of 11 records, or of 32 records for the Angebot.
    """
    boq = _boq(name)
    assert (boq.phase, len(boq.items), len(boq.sections)) == (phase, items, sections)


def test_same_boq_as_gaeb_xml():
    """The D83 file gives the OZs, quantities and units of the X83 file of the same BoQ."""
    xml = _boq("8209.003_Leistungsverzeichnis_leer.X83")
    fields = [(i.oz, i.quantity, i.unit) for i in _boq(D83).items]
    assert fields == [(i.oz, i.quantity, i.unit) for i in xml.items]
    assert [s.oz for s in _boq(D83).sections] == [s.oz for s in xml.sections]
    assert _boq(D83).total is None


@pytest.mark.parametrize("name", [STBA, LV, ANGEBOT])
def test_prices_scale(name: str):
    """Quantity times unit price, rounded half up to cents, gives the line total of every item.

    :param name: a priced sample file.
    """
    for item in _boq(name).items:
        line = (item.quantity * item.unit_price).quantize(Decimal("0.01"), ROUND_HALF_UP)
        assert line == item.total, item.oz


def test_angebot_values():
    """The Angebot D84 is ISO-8859-1, pads OZs with spaces and states its net total in 99."""
    boq = _boq(ANGEBOT)
    first = boq.items[0]
    assert (first.oz, first.unit, first.unit_price, first.total) == (
        "01.01.0010",
        "psch",
        Decimal("72000.000"),
        Decimal("72000.00"),
    )
    assert boq.sections[0].oz == "01.01"
    assert boq.sections[0].total == Decimal("93387.50")
    assert boq.total == Decimal("988913.89")
    assert any("ä" in i.long_text for i in boq.items)


def test_stbalv_values():
    """The StBALV D86 is code page 850, has two-line short texts and zeros in its 99 record."""
    boq = _boq(STBA)
    item = boq.items[0]
    assert (item.oz, item.short_text.split("\n")[0], item.unit, item.total) == (
        "01.01.0001",
        "Sanitärcontainer aufstellen räumen doppelwandig, isoliert L 5m",
        "St",
        Decimal("16000.00"),
    )
    assert (boq.sections[0].oz, boq.sections[0].title) == (
        "01",
        "Baustelleneinrichtung Tiefbau + Leitungs",
    )
    assert {s.oz: s.total for s in boq.sections}["08.01"] == Decimal("25086.49")
    assert boq.total is None


def test_space_padded_oz_and_empty_unit():
    """LV24069 pads item numbers with spaces; some of its items have no unit."""
    boq = _boq(LV)
    assert boq.items[0].oz == "01.01.0001"
    assert sum(1 for i in boq.items if i.unit == "") == 38


def test_synthetic_index_and_long_text():
    """An index letter follows the OZ, long text drops its prefix, a lone 23 record fails."""
    boq = parse_gaeb90(
        _records(
            "1101",
            "12Titel",
            "2101010010ANNN         00000002500m3",
            "25Kurz",
            "2601BLang eins",
            "26   Lang zwei",
        ),
        "x.d83",
    )
    item = boq.items[0]
    assert (item.oz, item.quantity, item.unit, item.long_text) == (
        "01.01.0010A",
        Decimal("2.500"),
        "m3",
        "Lang eins\nLang zwei",
    )
    assert (item.unit_price, item.total) == (None, None)
    with pytest.raises(ValueError, match="23"):
        parse_gaeb90(_records("2301010001  0000000100  000000000100"), "x.d83")
    with pytest.raises(ValueError, match="23"):
        parse_gaeb90(
            _records(
                "2101010001 NNN         00000001000St",
                "2301010002  0000000100  000000000100",
            ),
            "x.d83",
        )


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "no 00 record"),
        ("00        84K".ljust(62).encode() + b"bad", "OZ mask"),
        (_records("1101", "12Titel"), "no items"),
    ],
)
def test_rejects(data: bytes, message: str):
    """parse_gaeb90 raises ValueError without a header, with a bad OZ mask or without items.

    :param data: the file content.
    :param message: a part of the error message.
    """
    with pytest.raises(ValueError, match=message):
        parse_gaeb90(data, "x.d84")
