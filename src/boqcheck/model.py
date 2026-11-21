"""Data model of a bill of quantities (BoQ, German LV): parsers return it, checks read it."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Section:
    """A section of the BoQ, such as a Titel or Bereich.

    :ivar oz: the full Ordnungszahl, levels joined by ".", for example "01.02".
    :ivar title: the section label.
    """

    oz: str
    title: str


@dataclass(frozen=True)
class Item:
    """A line item (Position).

    :ivar oz: the full Ordnungszahl, levels joined by ".", for example "01.02.0030".
    :ivar short_text: the Kurztext; line breaks are newlines.
    :ivar long_text: the Langtext; line breaks are newlines.
    :ivar quantity: the quantity (Menge), or None if the file gives none.
    :ivar unit: the unit (ME) as the file writes it, for example "m3", "m³" or "Stk.".
    :ivar provisional: True for a Bedarfsposition (provisional item).
    :ivar lump_sum: True for a lump-sum item (Pauschalposition).
    """

    oz: str
    short_text: str
    long_text: str
    quantity: Decimal | None
    unit: str
    provisional: bool = False
    lump_sum: bool = False


@dataclass(frozen=True)
class BoQ:
    """A parsed bill of quantities.

    :ivar source: the name of the parsed file.
    :ivar phase: the GAEB exchange phase, for example "83" (bid request), or None if unknown.
    :ivar sections: the sections in document order.
    :ivar items: the items in document order.
    """

    source: str
    phase: str | None
    sections: tuple[Section, ...]
    items: tuple[Item, ...]
