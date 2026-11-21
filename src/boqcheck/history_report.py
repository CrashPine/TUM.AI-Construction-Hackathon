"""Bind a local historical dataset to explicitly mapped estimate positions."""

import json
from collections import Counter
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .historical_comparison import HistoricalPosition, compare_history
from .model import Item

_NUMBERS = {"quantity", "scale", "price", "price_basis"}


@dataclass(frozen=True)
class HistoryDataset:
    """Historical observations and metadata for explicitly selected current positions."""

    filename: str
    sha256: str
    synthetic: bool
    current: dict[str, HistoricalPosition]
    peers: list[HistoricalPosition]


def _position(row: dict) -> HistoricalPosition:
    """Decode one observation without passing JSON numbers through binary floats.

    :param row: historical observation or current-position metadata.
    :returns: typed comparison input.
    """
    return HistoricalPosition(
        **{
            key: Decimal(str(value)) if key in _NUMBERS and value is not None else value
            for key, value in row.items()
        }
    )


def load_dataset(path: Path) -> HistoryDataset:
    """Load the local JSON comparison dataset.

    :param path: explicitly configured local JSON file.
    :returns: comparison inputs and dataset provenance.
    :raises ValueError: if the dataset cannot be decoded.
    """
    try:
        data = json.loads(path.read_text("utf8"), parse_float=Decimal)
        if not isinstance(data["filename"], str) or not isinstance(data["synthetic"], bool):
            raise ValueError("Invalid dataset metadata.")
        return HistoryDataset(
            data["filename"],
            data["sha256"],
            data["synthetic"],
            {oz: _position(row) for oz, row in data["current"].items()},
            [_position(row) for row in data["peers"]],
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, InvalidOperation) as error:
        raise ValueError(f"Invalid historical dataset: {path.name}") from error


def report_history(dataset: HistoryDataset, items: tuple[Item, ...]) -> list[dict]:
    """Calculate results using numbers from the uploaded estimate.

    :param dataset: declared current mappings and local historical observations.
    :param items: normalized positions of the mapped upload.
    :returns: comparison records linked to unique position rows.
    """
    counts = Counter(item.oz for item in items)
    reports = []
    for index, item in enumerate(items, 1):
        metadata = dataset.current.get(item.oz)
        if not metadata or counts[item.oz] != 1 or item.unit != metadata.unit:
            continue
        current = replace(
            metadata, quantity=item.quantity, price=item.unit_price, price_basis=item.price_basis
        )
        reports.append(
            {"oz": item.oz, "position": index, "results": compare_history(current, dataset.peers)}
        )
    return reports
