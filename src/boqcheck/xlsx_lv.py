"""Read an explicitly mapped XLSX bill of quantities."""

import re
from decimal import Decimal
from io import BytesIO
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .model import BoQ, Item

_NUMBERS = {"Menge": "Qty", "EP": "UP", "Preisbasis": "PriceBasis", "Gesamtbetrag": "IT"}
_REQUIRED = {"OZ", "Kurztext", "Menge", "ME"}


def read_xlsx(name: str, data: bytes) -> tuple[BoQ, list[str]]:
    """Read mapped sheets and retain physical row references.

    :param name: uploaded workbook name.
    :param data: original XLSX bytes.
    :returns: parsed positions and matching sheet/row references.
    :raises ValueError: when the workbook is invalid or contains no mapped positions.
    """
    items, references, warnings = [], [], []
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 32_000_000:
                raise ValueError("Entpackte XLSX-Datei zu groß.")
        book = load_workbook(BytesIO(data), read_only=True, data_only=False, keep_links=False)
        try:
            for sheet in book.worksheets:
                sheet.reset_dimensions()
                rows = sheet.iter_rows(values_only=True)
                first = next(rows, ())
                headers = [str(value).strip() for value in first]
                known = _REQUIRED | _NUMBERS.keys()
                if not _REQUIRED.issubset(headers) or any(headers.count(key) > 1 for key in known):
                    warnings.append(f"Blatt {sheet.title}: Kopfzeile fehlt oder ist mehrdeutig.")
                    continue
                for row, values in enumerate(rows, 2):
                    if row > 20001 or len(items) >= 20000:
                        raise ValueError("XLSX-Zeilenlimit überschritten.")
                    fields = dict(zip(headers, values, strict=False))
                    fields = {key: value for key, value in fields.items() if key in known}
                    if all(value is None or value == "" for value in fields.values()):
                        continue
                    numbers, invalid = {}, []
                    for label, code in _NUMBERS.items():
                        value = fields.get(label)
                        if value is None or value == "":
                            continue
                        raw = str(value).strip()
                        if isinstance(value, str) and "," in raw:
                            if re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+),\d+", raw):
                                raw = raw.replace(".", "").replace(",", ".")
                        if not re.fullmatch(r"[+-]?\d{1,18}(?:\.\d{1,12})?", raw):
                            invalid.append((code, str(value)))
                        else:
                            numbers[label] = Decimal(raw)
                    items.append(
                        Item(
                            oz=str(fields.get("OZ") or "").strip(),
                            short_text=str(fields.get("Kurztext") or "").strip(),
                            long_text="",
                            quantity=numbers.get("Menge"),
                            unit=str(fields.get("ME") or "").strip(),
                            unit_price=numbers.get("EP"),
                            price_basis=numbers.get("Preisbasis"),
                            total=numbers.get("Gesamtbetrag"),
                            invalid_numbers=tuple(invalid),
                        )
                    )
                    references.append(f"Blatt {sheet.title} · Zeile {row}")
        finally:
            book.close()
    except (BadZipFile, InvalidFileException, KeyError, OSError, ParseError) as error:
        raise ValueError("XLSX-Datei nicht lesbar.") from error
    if not items:
        raise ValueError("XLSX benötigt OZ, Kurztext, Menge und ME in der ersten Zeile.")
    return BoQ(name, None, (), tuple(items), warnings=tuple(warnings)), references
