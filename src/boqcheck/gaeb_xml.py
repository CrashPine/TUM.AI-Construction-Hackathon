"""Parser for GAEB DA XML bills of quantities (X83 files)."""

import xml.etree.ElementTree as ET
from collections.abc import Iterator
from decimal import Decimal

from boqcheck.model import BoQ, Item, Section

SHORT_TEXT = "Description/CompleteText/OutlineText/OutlTxt/TextOutlTxt"
LONG_TEXT = "Description/CompleteText/DetailTxt"


def parse_gaeb_xml(data: bytes, source: str) -> BoQ:
    """Parse a GAEB DA XML bill of quantities.

    :param data: the file content.
    :param source: the file name, for the result and for error messages.
    :returns: the BoQ with its sections and items in document order.
    :raises ValueError: if the data is not well-formed XML or has no GAEB Award/BoQ element, if a
        BoQBkdn element has no Length, or if no BoQBkdn element has the Type Item.
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
    breakdown = [
        (b.findtext("Type"), b.findtext("Length")) for b in boq.iterfind("BoQInfo/BoQBkdn")
    ]
    if "Item" not in dict(breakdown) or not all(length for _, length in breakdown):
        raise ValueError(f"{source}: invalid BoQBkdn: each needs a Length, one needs the Type Item")
    # A Lot (Los) is the top section level, above the BoQLevel entries.
    level_widths = [int(length) for kind, length in breakdown if kind in ("Lot", "BoQLevel")]
    entries = list(_entries(boq, (), level_widths, int(dict(breakdown)["Item"])))
    return BoQ(
        source=source,
        phase=root.findtext("Award/DP", "").strip() or None,
        sections=tuple(entry for entry in entries if isinstance(entry, Section)),
        items=tuple(entry for entry in entries if isinstance(entry, Item)),
    )


def _entries(
    parent: ET.Element, prefix: tuple[str, ...], level_widths: list[int], item_width: int
) -> Iterator[Section | Item]:
    """Yield the sections and items in the BoQBody of a BoQ or BoQCtgy, in document order.

    OZ parts are padded with zeros to the BoQBkdn widths: some files write "1" for "0001".
    Parts marked as not applicable (Entfällt) are skipped with everything below them.

    :param parent: a BoQ or BoQCtgy element; without a BoQBody it has no entries.
    :param prefix: the padded OZ parts of the enclosing sections.
    :param level_widths: the OZ widths of the section levels, Lot first.
    :param item_width: the OZ width of the item level.
    :yields: each section before its contents, and each item.
    """
    for ctgy in parent.iterfind("BoQBody/BoQCtgy"):
        if ctgy.findtext("NotApplBoQ") == "Yes":
            continue
        oz = (*prefix, ctgy.get("RNoPart").zfill(level_widths[len(prefix)]))
        yield Section(oz=".".join(oz), title=_text(ctgy.find("LblTx")))
        yield from _entries(ctgy, oz, level_widths, item_width)
    for item in parent.iterfind("BoQBody/Itemlist/Item"):
        if item.findtext("NotAppl") == "Yes":
            continue
        quantity = item.findtext("Qty", "").strip()
        number = item.get("RNoPart").zfill(item_width) + item.get("RNoIndex", "")
        yield Item(
            oz=".".join((*prefix, number)),
            short_text=_text(item.find(SHORT_TEXT)),
            # DetailTxt interleaves Text with TextComplement (owner text, bidder blanks).
            # Sub-descriptions (Unterbeschreibungen) are part of the scope; the label line
            # follows the printed LV of the same BoQ.
            long_text="\n".join(
                [_text(item.find(LONG_TEXT))]
                + [
                    f"Unterbeschreibung {sub.findtext('SubDNo')}:\n"
                    f"{_text(sub.find(SHORT_TEXT))}\n{_text(sub.find(LONG_TEXT))}"
                    for sub in item.iterfind("SubDescr")
                ]
            ),
            quantity=Decimal(quantity) if quantity else None,
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
