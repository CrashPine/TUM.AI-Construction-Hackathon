"""Import historical positions from explicitly selected workbook rows."""

from pathlib import Path

from .xlsx_lv import read_xlsx


def workbook_peers(directory: Path, projects: list[dict]) -> list[dict]:
    """Read historical XLSX data and attach declared comparison metadata.

    :param directory: directory of the local dataset manifest.
    :param projects: workbook, project ID, defaults and selected positions.
    :returns: historical observations with original worksheet and row evidence.
    :raises ValueError: if a workbook or explicitly selected position is invalid.
    """
    peers = []
    for project in projects:
        path = (directory / project["workbook"]).resolve()
        if path.suffix.lower() != ".xlsx" or not path.is_relative_to(directory.resolve()):
            raise ValueError(
                "Historical workbooks must be XLSX files inside the manifest directory."
            )
        with path.open("rb") as stream:
            data = stream.read(16_000_001)
        if len(data) > 16_000_000:
            raise ValueError(f"Historical workbook too large: {path.name}")
        boq, references = read_xlsx(path.name, data)
        positions = {}
        duplicates = set()
        for item, reference in zip(boq.items, references, strict=True):
            if item.oz in positions:
                duplicates.add(item.oz)
            positions[item.oz] = (item, reference)
        for oz, metadata in project["positions"].items():
            if oz in duplicates or oz not in positions:
                raise ValueError(f"Missing or ambiguous historical OZ {oz} in {path.name}")
            item, reference = positions[oz]
            if item.invalid_numbers or not item.unit:
                raise ValueError(f"Invalid historical position {oz} in {path.name}")
            peers.append(
                {
                    **project.get("defaults", {}),
                    **metadata,
                    "project": project["project"],
                    "source": f"{project['workbook']} · {reference} · OZ {oz}",
                    "description": item.short_text or item.long_text,
                    "unit": item.unit,
                    "quantity": item.quantity,
                    "price": item.unit_price,
                    "price_basis": item.price_basis,
                }
            )
    return peers
