"""Parser for GAEB DA XML bills of quantities (X83 files)."""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from decimal import Decimal

from boqcheck.model import BoQ, Item, Section

SHORT_TEXT = "Description/CompleteText/OutlineText/OutlTxt/TextOutlTxt"
LONG_TEXT = "Description/CompleteText/DetailTxt"
_VERSIONS = {
    "http://www.gaeb.de/GAEB_DA_XML/200407": "3.1",
    "http://www.gaeb.de/GAEB_DA_XML/DA83/3.2": "3.2",
}
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")


class _WithoutDTD(ET.TreeBuilder):
    """Build XML without processing document type declarations."""

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        """Reject DTDs, including those that contain entity declarations.

        :param name: document type name.
        :param pubid: optional public identifier.
        :param system: optional system identifier.
        :raises ValueError: always, because DTDs are unsupported.
        """
        raise ValueError("DTD and entity declarations are not allowed")


def parse_gaeb_xml(data: bytes, source: str) -> BoQ:
    """Parse a GAEB DA XML bill of quantities.

    :param data: the file content.
    :param source: the file name, for the result and for error messages.
    :returns: the BoQ with its sections and items in document order.
    :raises ValueError: if the data is not well-formed XML or has no GAEB Award/BoQ element, if a
        BoQBkdn element has no Length, if no BoQBkdn element has the Type Item, or for DTDs.
    """
    try:
        root = ET.fromstring(data, parser=ET.XMLParser(target=_WithoutDTD()))
    except ET.ParseError as error:
        raise ValueError(f"{source}: not well-formed XML: {error}") from error
    namespace = root.tag[1:].partition("}")[0] if root.tag.startswith("{") else None
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
    expected_version = _VERSIONS.get(namespace)
    version = root.findtext("GAEBInfo/Version", "").strip() or expected_version
    phase = root.findtext("Award/DP", "").strip() or None
    warnings = []
    if expected_version is None or version != expected_version:
        warnings.append("Unverified GAEB XML namespace or version; import may be incomplete.")
    if phase != "83":
        warnings.append("Only phase 83 (X83) is verified by this importer.")
    skipped = {"AddText", "Remark", "PerfDescr", "RefDescr", "RefRNo"}
    present = sorted({element.tag for element in root.iter() if element.tag in skipped})
    if present:
        warnings.append(f"Content not imported: {', '.join(present)}.")
    items = tuple(entry for entry in entries if isinstance(entry, Item))
    if any(item.unit_price is not None or item.line_total is not None for item in items):
        warnings.append("Price fields were read as extensions; standard X83 is unpriced.")
    return BoQ(
        source=source,
        phase=phase,
        sections=tuple(entry for entry in entries if isinstance(entry, Section)),
        items=items,
        version=version,
        namespace=namespace,
        version_date=root.findtext("GAEBInfo/VersDate", "").strip() or None,
        warnings=tuple(warnings),
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
        number = (item.get("RNoPart") or "").strip()
        invalid: list[tuple[str, str]] = []
        parsed = {
            name: _read_decimal(item, name, invalid) for name in ("Qty", "UP", "PriceBasis", "IT")
        }
        yield Item(
            oz=".".join((*prefix, number.zfill(item_width) + item.get("RNoIndex", "")))
            if number
            else "",
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
            quantity=parsed["Qty"],
            unit=item.findtext("QU", ""),
            provisional=item.find("Provis") is not None,
            lump_sum=item.findtext("LumpSumItem") == "Yes",
            unit_price=parsed["UP"],
            price_basis=parsed["PriceBasis"],
            total=parsed["IT"],
            invalid_numbers=tuple(invalid),
            adjusted_total=any(
                item.find(tag) is not None for tag in ("DiscountPcnt", "RedPriceComp")
            ),
        )


def _read_decimal(item: ET.Element, name: str, invalid: list[tuple[str, str]]) -> Decimal | None:
    """Read a decimal and record an invalid value for structural checks.

    :param item: item containing the field.
    :param name: XML field name.
    :param invalid: recipient for invalid raw values.
    :returns: decimal value or None if absent or invalid.
    """
    raw = item.findtext(name, "").strip()
    if not raw:
        return None
    if len(raw) <= 64 and _DECIMAL.fullmatch(raw):
        return Decimal(raw)
    invalid.append((name, raw))
    return None


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
