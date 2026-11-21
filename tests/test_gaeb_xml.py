"""Tests for the GAEB DA XML parser and the parse entry point, on sample files and synthetic XML."""

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
LEVEL = "<BoQBkdn><Type>BoQLevel</Type><Length>2</Length></BoQBkdn>"
ITEM = "<BoQBkdn><Type>Item</Type><Length>4</Length></BoQBkdn>"


@functools.cache
def _boq(name: str) -> BoQ:
    """Parse a sample file once for all tests.

    :param name: the file name in data/raw.
    :returns: the parsed BoQ.
    """
    return parse(name, (RAW / name).read_bytes())


def _xml(body: str, breakdown: str = LEVEL + ITEM, dp: str = "83") -> bytes:
    """Build a synthetic GAEB DA XML 3.2 document.

    :param body: the elements after BoQInfo in the BoQ element, usually a BoQBody.
    :param breakdown: the BoQBkdn elements.
    :param dp: the text of Award/DP.
    :returns: the document.
    """
    return (
        f'<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA83/3.2"><Award><DP>{dp}</DP><BoQ>'
        f"<BoQInfo>{breakdown}</BoQInfo>{body}</BoQ></Award></GAEB>"
    ).encode()


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


@pytest.mark.parametrize(
    ("breakdown", "body", "ozs"),
    [
        (
            "<BoQBkdn><Type>Lot</Type><Length>1</Length></BoQBkdn>" + LEVEL + ITEM,
            '<BoQBody><BoQCtgy RNoPart="1"><BoQBody><BoQCtgy RNoPart="2"><BoQBody><Itemlist>'
            '<Item RNoPart="3" RNoIndex="A"/></Itemlist></BoQBody></BoQCtgy></BoQBody></BoQCtgy>'
            "</BoQBody>",
            ["1", "1.02", "1.02.0003A"],
        ),
        (
            LEVEL + ITEM,
            '<BoQBody><BoQCtgy RNoPart="1"><NotApplBoQ>Yes</NotApplBoQ><BoQBody><Itemlist>'
            '<Item RNoPart="1"/></Itemlist></BoQBody></BoQCtgy><BoQCtgy RNoPart="2"><BoQBody>'
            '<Itemlist><Item RNoPart="1"><NotAppl>Yes</NotAppl></Item><Item RNoPart="2"/>'
            "</Itemlist></BoQBody></BoQCtgy></BoQBody>",
            ["02", "02.0002"],
        ),
        (LEVEL + ITEM, "", []),
        (LEVEL + ITEM, '<BoQBody><BoQCtgy RNoPart="1"/></BoQBody>', ["01"]),
    ],
    ids=["lot-and-index", "not-applicable", "boq-without-body", "section-without-body"],
)
def test_structure(breakdown: str, body: str, ozs: list[str]):
    """Lot widths, index letters, Entfällt marks and missing BoQBody elements give the right OZs.

    :param breakdown: the BoQBkdn elements.
    :param body: the elements after BoQInfo in the BoQ element.
    :param ozs: the expected OZs of the sections, then of the items.
    """
    boq = parse_gaeb_xml(_xml(body, breakdown), "synthetic.X83")
    assert [entry.oz for entry in (*boq.sections, *boq.items)] == ozs


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
        (LEER, "01.01.0002", "als Symbol,\nRohrleitungen,"),  # list items: ul/li/p
        (NUMMER, "07.01.0007", "EN 489.\nUnterbeschreibung 1:\nFertigabzweig,"),  # SubDescr
        (NUMMER, "07.01.0007", "EN 448\nUnterbeschreibung 2:\nAnschlussrohrleitung\nELE"),
    ],
)
def test_long_text(name: str, oz: str, fragment: str):
    """The long text has a line per paragraph and br, single spaces and the text complements.

    Each sub-description follows with its number, its Kurztext and its Langtext.

    :param name: the sample file.
    :param oz: the OZ of the item.
    :param fragment: a part of the expected long text.
    """
    item = next(item for item in _boq(name).items if item.oz == oz)
    assert fragment in item.long_text


@pytest.mark.parametrize("qty", ["", "<Qty/>", "<Qty> </Qty>"])
def test_item_without_quantity_unit_or_texts(qty: str):
    """An Item without QU and texts, and without Qty or with an empty one, parses with empty values.

    :param qty: the Qty element of the item, if any.
    """
    body = f'<BoQBody><Itemlist><Item RNoPart="7">{qty}</Item></Itemlist></BoQBody>'
    item = parse_gaeb_xml(_xml(body), "synthetic.X83").items[0]
    assert item == Item(oz="0007", short_text="", long_text="", quantity=None, unit="")


@pytest.mark.parametrize("dp", ["", " "])
def test_empty_phase_is_none(dp: str):
    """An empty or blank Award/DP gives the phase None.

    :param dp: the text of Award/DP.
    """
    assert parse_gaeb_xml(_xml("", dp=dp), "synthetic.X83").phase is None


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"%PDF-1.7", "not well-formed XML"),
        (b"<html/>", "no Award/BoQ element"),
        (_xml("", LEVEL), "invalid BoQBkdn"),
        (_xml("", "<BoQBkdn><Type>Item</Type></BoQBkdn>"), "invalid BoQBkdn"),
    ],
    ids=["pdf", "html", "no-item-entry", "no-length"],
)
def test_rejects_other_data(data: bytes, message: str):
    """Data that is not a usable GAEB DA XML BoQ raises ValueError with a clear message.

    :param data: the file content.
    :param message: a part of the expected error message.
    """
    with pytest.raises(ValueError, match=message):
        parse_gaeb_xml(data, "upload.x83")


def test_parse_rejects_unknown_suffix():
    """parse() raises ValueError for a file type that no parser handles."""
    with pytest.raises(ValueError, match="unsupported file type"):
        parse("LV.pdf", b"%PDF-1.7")
