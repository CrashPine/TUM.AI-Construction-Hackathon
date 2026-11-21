"""Bind a local historical dataset to explicitly mapped estimate positions."""

import json
from collections import Counter
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .historical_comparison import HistoricalPosition, compare_history
from .history_embeddings import similar_rows
from .history_ingest import workbook_peers
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
    descriptions: tuple[str, ...] = ()
    embedding_model: str = ""
    embedding_port: int = 11434
    similarity: float = 0.75


def _position(row: dict) -> HistoricalPosition:
    """Decode one observation without passing JSON numbers through binary floats.

    :param row: historical observation or current-position metadata.
    :returns: typed comparison input.
    """
    return HistoricalPosition(
        **{
            key: Decimal(str(value)) if key in _NUMBERS and value is not None else value
            for key, value in row.items()
            if key != "description"
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
        model = data.get("embedding_model", "")
        port = data.get("embedding_port", 11434)
        threshold = float(data.get("similarity", 0.75))
        peers = [*data.get("peers", []), *workbook_peers(path.parent, data.get("projects", []))]
        descriptions = tuple(row.get("description", "") for row in peers)
        if (
            not isinstance(model, str)
            or type(port) is not int
            or not 1 <= port <= 65535
            or not 0 <= threshold <= 1
            or not all(isinstance(d, str) for d in descriptions)
        ):
            raise ValueError("Invalid embedding settings.")
        return HistoryDataset(
            data["filename"],
            data["sha256"],
            data["synthetic"],
            {oz: _position(row) for oz, row in data["current"].items()},
            [_position(row) for row in peers],
            descriptions,
            model,
            port,
            threshold,
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
        peers = dataset.peers
        retrieval = ""
        if dataset.embedding_model:
            description = item.short_text or item.long_text
            candidates = [
                (peer, text)
                for peer, text in zip(peers, dataset.descriptions, strict=True)
                if text.strip()
                and peer.project != current.project
                and (peer.trade, peer.scope, peer.unit)
                == (current.trade, current.scope, current.unit)
            ]
            peers = []
            retrieval = "Keine beschreibbaren Vergleichspositionen."
            if description.strip() and candidates:
                try:
                    for start in range(0, len(candidates), 32):
                        batch = candidates[start : start + 32]
                        selected = similar_rows(
                            description,
                            [text for _, text in batch],
                            dataset.embedding_model,
                            dataset.embedding_port,
                            dataset.similarity,
                        )
                        peers.extend(batch[i][0] for i in selected)
                    retrieval = (
                        f"Lokale Ähnlichkeitssuche: {len(peers)}/{len(candidates)} ausgewählt."
                    )
                except (OSError, ValueError, TypeError, KeyError, OverflowError):
                    peers = []
                    retrieval = "Lokale Ähnlichkeitssuche nicht verfügbar."
        reports.append(
            {
                "oz": item.oz,
                "position": index,
                "results": compare_history(current, peers),
                "retrieval": retrieval,
            }
        )
    return reports
