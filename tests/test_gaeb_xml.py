"""Tests for the GAEB DA XML parser and the parse entry point, on the sample files."""

import functools
from pathlib import Path

import pytest

from boqcheck import parse
from boqcheck.gaeb_xml import parse_gaeb_xml
from boqcheck.model import BoQ, Item

RAW = Path(__file__).parents[1] / "data" / "raw"
SAS = "501-24-01_GAEB-XML_sas.x83"
LEER = "8209.003_Leistungsverzeichnis_leer.X83"
PROJEKT = "GAEB-[PROJEKT_004].X83"
NUMMER = "[NUMMER_001]_leer.X83"

MINIMAL = b"""<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA83/3.2"><Award><BoQ>
<BoQInfo><BoQBkdn><Type>BoQLevel</Type><Length>2</Length></BoQBkdn>
<BoQBkdn><Type>Item</Type><Length>4</Length></BoQBkdn></BoQInfo>
<BoQBody><BoQCtgy RNoPart="1"><BoQBody><Itemlist><Item RNoPart="7"/></Itemlist></BoQBody>
</BoQCtgy></BoQBody></BoQ></Award></GAEB>"""


@functools.cache
def _boq(name: str) -> BoQ:
    """Parse a sample file once for all tests.

    :param name: the file name in data/raw.
    :returns: the parsed BoQ.
    """
    return parse(name, (RAW / name).read_bytes())


@pytest.mark.parametrize(
    ("name", "items", "sections", "provisional", "lump_sum"),
    [
        (SAS, 296, 25, 24, 0),
        (LEER, 159, 28, 0, 14),
        (PROJEKT, 50, 4, 0, 6),
        (NUMMER, 248, 32, 0, 5),
    ],
)
def test_counts(name: str, items: int, sections: int, provisional: int, lump_sum: int):
    """parse() reads every Item and BoQCtgy, the phase, Provis and LumpSumItem, for .x83 and .X83.

    :param name: the sample file.
    :param items: the number of Item elements.
    :param sections: the number of BoQCtgy elements.
    :param provisional: the number of items with Provis.
    :param lump_sum: the number of items with LumpSumItem "Yes".
    """
    boq = _boq(name)
    assert (boq.source, boq.phase) == (name, "83")
    assert (len(boq.items), len(boq.sections)) == (items, sections)
    assert sum(item.provisional for item in boq.items) == provisional
    assert sum(item.lump_sum for item in boq.items) == lump_sum


@pytest.mark.parametrize(
    ("name", "second_section", "first_item"),
    [
        (SAS, "01.01", "01.01.0001"),
        (LEER, "01.01", "01.01.0001"),  # items write "1"
        (PROJEKT, "02", "01.0001"),  # items sit below the first of two section levels
        (NUMMER, "01.01", "01.01.0001"),  # sections and items write "1"
    ],
)
def test_oz_padded_to_breakdown_widths(name: str, second_section: str, first_item: str):
    """OZ parts are joined with "." and padded with zeros to the BoQBkdn widths.

    :param name: the sample file.
    :param second_section: the expected OZ of the second section.
    :param first_item: the expected OZ of the first item.
    """
    boq = _boq(name)
    assert (boq.sections[1].oz, boq.items[0].oz) == (second_section, first_item)


def test_quantity_and_unit_as_written():
    """Qty keeps the digits of the file and QU is not normalized."""
    item = next(item for item in _boq(LEER).items if item.oz == "02.02.0001")
    assert (str(item.quantity), item.unit) == ("30.000", "m³")


def test_short_text_and_title():
    """The Kurztext comes from OutlTxt and the section title from LblTx."""
    boq = _boq(PROJEKT)
    assert boq.items[0].short_text == "Baustelleneinrichtung und -räumung"
    assert boq.sections[1].title == "Tiefbauarbeiten"


@pytest.mark.parametrize(
    ("name", "oz", "fragment"),
    [
        (PROJEKT, "01.0001", "sämtliche\nin der"),  # br inside a paragraph
        (SAS, "01.01.0001", "die zur\nvertragsgemäßen"),  # paragraph end in pretty-printed XML
        (LEER, "03.01.0001", "Hersteller Pumpe: '."),  # TextComplement; a tab before the quote
    ],
)
def test_long_text(name: str, oz: str, fragment: str):
    """The Langtext has a line per paragraph and br, single spaces and the text complements.

    :param name: the sample file.
    :param oz: the OZ of the item.
    :param fragment: a part of the expected long text.
    """
    item = next(item for item in _boq(name).items if item.oz == oz)
    assert fragment in item.long_text


def test_item_without_quantity_unit_or_texts():
    """An Item without Qty, QU and Description parses, so that checks can report the gaps."""
    item = parse_gaeb_xml(MINIMAL, "minimal.X83").items[0]
    assert item == Item(oz="01.0007", short_text="", long_text="", quantity=None, unit="")


@pytest.mark.parametrize(
    ("data", "message"),
    [(b"%PDF-1.7", "not well-formed XML"), (b"<html/>", "no Award/BoQ element")],
)
def test_rejects_other_data(data: bytes, message: str):
    """Data that is not a GAEB DA XML BoQ raises ValueError with a clear message.

    :param data: the file content.
    :param message: a part of the expected error message.
    """
    with pytest.raises(ValueError, match=message):
        parse_gaeb_xml(data, "upload.x83")


def test_parse_rejects_unknown_suffix():
    """parse() raises ValueError for a file type that no parser handles."""
    with pytest.raises(ValueError, match="unsupported file type"):
        parse("LV.pdf", b"%PDF-1.7")
