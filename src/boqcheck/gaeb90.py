"""Parser for GAEB 90 bills of quantities (D83, D84 and D86 files).

GAEB 90 writes fixed-width records of 80 characters; columns 1-2 hold the record type. The field
positions below come from the sample files; each was checked against the data (for example
quantity times unit price gives the line total of every priced item).
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from boqcheck.model import BoQ, Item, Section

_MASK = re.compile(r"(1+)(2*)(3*)(4*)(P+)(I?)")


@dataclass
class _Draft:
    """An item while its records are read."""

    oz: str
    quantity: Decimal | None
    unit: str
    short: list[str] = field(default_factory=list)
    long: list[str] = field(default_factory=list)
    unit_price: Decimal | None = None
    total: Decimal | None = None


def parse_gaeb90(data: bytes, source: str, *, records: dict | None = None) -> BoQ:
    """Parse a GAEB 90 bill of quantities.

    Sections come from the 11/12 records; a file without them gets a section, with an empty
    title, for each section total (32 record).

    :param data: the file content.
    :param source: the file name, for the result and for error messages.
    :param records: optional evidence index for position, price and total records.
    :returns: the BoQ with its sections and items in document order.
    :raises ValueError: if the file has no 00 record or no valid OZ mask in it, if a 23 record
        does not follow the 21 record of its item, or if the file has no 21 record.
    """
    lines = _decode(data).split("\r\n")
    header = next((line for line in lines if line.startswith("00")), None)
    if header is None:
        raise ValueError(f"{source}: no 00 record")
    mask = _MASK.fullmatch(header[62:71].rstrip())
    if mask is None:
        raise ValueError(f"{source}: no valid OZ mask in columns 63-71 of record 00")
    widths = [len(level) for level in mask.groups()[:5] if level]
    titles: dict[str, str] = {}
    totals: dict[str, Decimal] = {}
    drafts: list[_Draft] = []
    grand = None
    oz = ""
    prices_only = header[10:12] == "84" and not any(line.startswith("21") for line in lines)
    for number, line in enumerate(lines, 1):
        kind = line[:2]
        if records is not None and kind in ("21", "23", "32", "99"):
            key = (kind, "" if kind == "99" else _oz(line[2:11], widths))
            records.setdefault(key, []).append((number, line))
        if kind == "11":
            oz = _oz(line[2:11], widths)
        elif kind == "12":
            titles[oz] = line[2:74].rstrip()
        elif kind == "21":
            drafts.append(
                _Draft(_oz(line[2:11], widths), _number(line[23:34], 3), line[34:38].strip())
            )
        elif kind == "23":
            if prices_only:
                drafts.append(_Draft(_oz(line[2:11], widths), None, ""))
            if not drafts or drafts[-1].oz != _oz(line[2:11], widths):
                raise ValueError(f"{source}: 23 record {line[2:11]!r} without its 21 record")
            # The unit price has 3 decimals in 11 digits, or 2 in 10 digits and a blank.
            price = line[12:23]
            drafts[-1].unit_price = (
                _number(price, 2 if price.endswith(" ") else 3) if price.strip() else None
            )
            drafts[-1].total = _number(line[24:36], 2) if line[24:36].strip() else None
        elif kind == "25" and drafts:
            drafts[-1].short.append(line[2:74].rstrip())
        elif kind == "26" and drafts:
            # Columns 3-5 hold a control field, for example "01B" before a text complement.
            drafts[-1].long.append(line[5:74].rstrip())
        elif kind == "32":
            totals[_oz(line[2:11], widths)] = _number(line[12:24], 2)
        elif kind == "99":
            # The D83 sample leaves the field blank, the D86 samples write zeros: no total.
            net = line[2:14].strip()
            grand = _number(net, 2) or None if net else None
    if not drafts:
        raise ValueError(f"{source}: no items (21 records)")
    sections = tuple(Section(s, titles.get(s, ""), totals.get(s)) for s in titles or totals)
    items = tuple(
        Item(
            d.oz,
            "\n".join(d.short),
            "\n".join(d.long),
            d.quantity,
            d.unit,
            unit_price=d.unit_price,
            total=d.total,
        )
        for d in drafts
    )
    return BoQ(source, header[10:12], sections, items, grand)


def _decode(data: bytes) -> str:
    """Decode a GAEB 90 file with the code page that gives German umlauts.

    :param data: the file content.
    :returns: the text.
    """
    # Code page 850 writes umlauts as bytes 0x81-0x9A; ISO-8859-1 has no characters there.
    if any(0x80 <= byte < 0xA0 for byte in data):
        return data.decode("cp850")
    return data.decode("latin-1")


def _oz(field_: str, widths: list[int]) -> str:
    """Normalize an OZ field to levels padded with zeros and joined with ".".

    :param field_: columns 3-11 of the record: the levels as the OZ mask places them, then the
        index letter.
    :param widths: the widths of the levels and the item number, from the OZ mask.
    :returns: the OZ, for example "01.02.0030A"; blank trailing levels are left out.
    """
    levels = []
    start = 0
    for width in widths:
        level = field_[start : start + width].strip()
        start += width
        if not level:
            break
        levels.append(level.zfill(width))
    return ".".join(levels) + field_[start:].strip()


def _number(digits: str, decimals: int) -> Decimal:
    """Read a number with implied decimal places.

    :param digits: the digits of the field.
    :param decimals: the number of implied decimal places.
    :returns: the number.
    :raises ValueError: if the field does not contain a signed or unsigned integer.
    """
    if not re.fullmatch(r"[+-]?[0-9]+", digits.strip()):
        raise ValueError("Ungültiges Zahlenfeld im GAEB-90-Datensatz.")
    return Decimal(digits.strip()).scaleb(-decimals)
