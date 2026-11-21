"""Parser for GAEB DA XML bills of quantities (X83 files)."""

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from decimal import Decimal

from boqcheck.model import BoQ, Item, Section


def parse_gaeb_xml(data: bytes, source: str) -> BoQ:
    """Parse a GAEB DA XML bill of quantities.

    :param data: the file content.
    :param source: the file name, for the result and for error messages.
    :returns: the BoQ with its sections and items in document order.
    :raises ValueError: if the data is not well-formed XML or has no GAEB Award/BoQ element.
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError(f"{source}: not well-formed XML: {error}") from error
    # GAEB 3.1 and 3.2 use different namespaces for the same local names.
    for element in root.iter():
        element.tag = element.tag.rpartition("}")[2]
    boq = root.find("Award/BoQ")
    if boq is None:
        raise ValueError(f"{source}: not a GAEB DA XML bill of quantities (no Award/BoQ element)")
    breakdown = boq.findall("BoQInfo/BoQBkdn")
    level_widths = [
        int(b.findtext("Length")) for b in breakdown if b.findtext("Type") == "BoQLevel"
    ]
    item_width = next(int(b.findtext("Length")) for b in breakdown if b.findtext("Type") == "Item")
    entries = list(_entries(boq.find("BoQBody"), (), level_widths, item_width))
    return BoQ(
        source=source,
        phase=root.findtext("Award/DP"),
        sections=tuple(entry for entry in entries if isinstance(entry, Section)),
        items=tuple(entry for entry in entries if isinstance(entry, Item)),
    )


def _entries(
    body: ET.Element, prefix: tuple[str, ...], level_widths: list[int], item_width: int
) -> Iterator[Section | Item]:
    """Yield the sections and items below a BoQBody in document order.

    OZ parts are padded with zeros to the BoQBkdn widths: some files write "1" for "0001".

    :param body: a BoQBody element.
    :param prefix: the padded OZ parts of the enclosing sections.
    :param level_widths: the OZ widths of the section levels.
    :param item_width: the OZ width of the item level.
    :yields: each section before its contents, and each item.
    """
    for ctgy in body.iterfind("BoQCtgy"):
        oz = (*prefix, ctgy.get("RNoPart").zfill(level_widths[len(prefix)]))
        yield Section(oz=".".join(oz), title=_text(ctgy.find("LblTx")))
        yield from _entries(ctgy.find("BoQBody"), oz, level_widths, item_width)
    for item in body.iterfind("Itemlist/Item"):
        quantity = item.findtext("Qty")
        yield Item(
            oz=".".join((*prefix, item.get("RNoPart").zfill(item_width))),
            short_text=_text(item.find("Description/CompleteText/OutlineText/OutlTxt/TextOutlTxt")),
            # DetailTxt interleaves Text with TextComplement (owner text, bidder blanks).
            long_text=_text(item.find("Description/CompleteText/DetailTxt")),
            quantity=None if quantity is None else Decimal(quantity),
            unit=item.findtext("QU", ""),
            provisional=item.find("Provis") is not None,
            lump_sum=item.findtext("LumpSumItem") == "Yes",
        )


def _text(markup: ET.Element | None) -> str:
    """Return the plain text of GAEB text markup (p, span, br).

    :param markup: the element that holds the markup, or None if the file has none.
    :returns: the text, one line per paragraph or br, with single spaces; "" for None.
    """
    if markup is None:
        return ""
    lines = "".join(_pieces(markup)).split("\n")
    return "\n".join(" ".join(line.split()) for line in lines).strip()


def _pieces(element: ET.Element) -> Iterator[str]:
    """Yield the text of an element and its descendants in document order.

    :param element: an element of text markup.
    :yields: text pieces; each br and the end of each p as a newline. Newlines in the XML
        source are layout of pretty-printed files, so they become spaces.
    """
    yield (element.text or "").replace("\n", " ")
    for child in element:
        if child.tag == "br":
            yield "\n"
        else:
            yield from _pieces(child)
        yield (child.tail or "").replace("\n", " ")
    if element.tag == "p":
        yield "\n"
