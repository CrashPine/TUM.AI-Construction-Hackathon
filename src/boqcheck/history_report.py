"""Bind a local historical dataset to explicitly mapped estimate positions."""

import json
from collections import Counter
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError

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
    project_profiles: dict[str, str] | None = None
    current_profile: str = ""
    authorization: str = ""
    min_projects: int = 3
    deviation_threshold: Decimal = Decimal("0.30")


def _position(row: dict) -> HistoricalPosition:
    """Decode one observation without passing JSON numbers through binary floats.

    :param row: historical observation or current-position metadata.
    :returns: typed comparison input.
    :raises ValueError: if the price type is neither net nor gross.
    """
    if row.get("price_type", "") not in {"", "net", "gross"}:
        raise ValueError("Price type must be net or gross.")
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
    :raises ValueError: if the dataset cannot be decoded, a real dataset declares no
        authorization, one project source holds conflicting observations, or the anomaly
        rule needs fewer than two projects or a non-positive deviation.
    """
    try:
        data = json.loads(path.read_text("utf8"), parse_float=Decimal)
        authorization = data.get("authorization", "")
        if (
            not isinstance(data["filename"], str)
            or not isinstance(data["synthetic"], bool)
            or not isinstance(authorization, str)
            or not (data["synthetic"] or authorization.strip())
        ):
            raise ValueError("Invalid dataset metadata.")
        model = data.get("embedding_model", "")
        port = data.get("embedding_port", 11434)
        threshold = float(data.get("similarity", 0.75))
        unique = {}
        for row in [*data.get("peers", []), *workbook_peers(path.parent, data.get("projects", []))]:
            entry = (_position(row), row.get("description", ""))
            # Re-ingesting the same source is harmless; differing values are not.
            if unique.setdefault((entry[0].project, entry[0].source), entry) != entry:
                raise ValueError(f"Conflicting observations for {entry[0].source}.")
        positions = [position for position, _ in unique.values()]
        descriptions = tuple(description for _, description in unique.values())
        if (
            not isinstance(model, str)
            or type(port) is not int
            or not 1 <= port <= 65535
            or not 0 <= threshold <= 1
            or not all(isinstance(d, str) for d in descriptions)
        ):
            raise ValueError("Invalid embedding settings.")
        current_profile = data.get("current_profile", "")
        profiles = data.get("project_profiles", {})
        if (
            not isinstance(current_profile, str)
            or not isinstance(profiles, dict)
            or not all(isinstance(value, str) and value.strip() for value in profiles.values())
            or bool(current_profile.strip()) != bool(profiles)
            or (profiles and not model)
        ):
            raise ValueError("Invalid project similarity settings.")
        min_projects = data.get("min_projects", 3)
        deviation = data.get("deviation_threshold", Decimal("0.30"))
        # bool is excluded by the exact type checks; NaN and Infinity arrive as floats.
        if (
            type(min_projects) is not int
            or min_projects < 2
            or type(deviation) not in {int, Decimal}
            or not Decimal(deviation) > 0
        ):
            raise ValueError("Invalid anomaly settings.")
        return HistoryDataset(
            data["filename"],
            data["sha256"],
            data["synthetic"],
            {oz: _position(row) for oz, row in data["current"].items()},
            positions,
            descriptions,
            model,
            port,
            threshold,
            profiles,
            current_profile,
            authorization.strip(),
            min_projects,
            Decimal(deviation),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, InvalidOperation) as error:
        raise ValueError(f"Invalid historical dataset: {path.name}") from error


def _select(query: str, texts: list[str], dataset: HistoryDataset) -> list[int]:
    """Embed candidates in bounded batches and keep those above the similarity threshold.

    :param query: current description or project profile.
    :param texts: candidate descriptions or profiles.
    :param dataset: embedding model, port and threshold.
    :returns: indices of selected candidates.
    """
    selected = []
    for start in range(0, len(texts), 32):
        batch = texts[start : start + 32]
        selected.extend(
            start + i
            for i in similar_rows(
                query, batch, dataset.embedding_model, dataset.embedding_port, dataset.similarity
            )
        )
    return selected


def _failure(error: Exception, model: str) -> str:
    """Name why the local embedding request failed without guessing beyond the evidence.

    :param error: exception raised by the embedding request.
    :param model: configured model name.
    :returns: German reason for the report.
    """
    if isinstance(error, HTTPError):
        # Ollama answers 404 for unknown models, but other local services may too.
        detail = error.read(2000).decode("utf8", "replace")
        if error.code == 404 and "model" in detail and "not found" in detail:
            return f"Modell {model} nicht installiert"
        return f"lokaler Dienst antwortete mit HTTP {error.code}"
    if isinstance(error, OSError):
        return "lokaler Dienst nicht erreichbar"
    return "ungültige Antwort des lokalen Dienstes"


_FAILURES = (OSError, ValueError, TypeError, KeyError, OverflowError)


def report_history(dataset: HistoryDataset, items: tuple[Item, ...]) -> list[dict]:
    """Calculate results using numbers from the uploaded estimate.

    :param dataset: declared current mappings and local historical observations.
    :param items: normalized positions of the mapped upload.
    :returns: comparison records linked to unique position rows.
    """
    counts = Counter(item.oz for item in items)
    reports = []
    profiles = dataset.project_profiles
    model = dataset.embedding_model
    selected_projects = None
    project_coverage = ""
    if profiles:
        current_projects = {metadata.project for metadata in dataset.current.values()}
        projects = {peer.project for peer in dataset.peers} - current_projects
        keys = sorted(projects & profiles.keys())
        unprofiled = len(projects) - len(keys)
        try:
            selected = _select(dataset.current_profile, [profiles[key] for key in keys], dataset)
            selected_projects = {keys[i] for i in selected}
            project_coverage = f"Projektvorauswahl: {len(selected_projects)}/{len(keys)} ausgewählt"
        except _FAILURES as error:
            selected_projects = set()
            project_coverage = f"Projektvorauswahl nicht verfügbar: {_failure(error, model)}"
        if unprofiled:
            project_coverage += f", {unprofiled} Projekte ohne Profil ausgeschlossen"
        project_coverage += "."
    for index, item in enumerate(items, 1):
        metadata = dataset.current.get(item.oz)
        if not metadata or counts[item.oz] != 1 or item.unit != metadata.unit:
            continue
        current = replace(
            metadata, quantity=item.quantity, price=item.unit_price, price_basis=item.price_basis
        )
        peers = dataset.peers
        retrieval = "Keine Ähnlichkeitssuche konfiguriert; Auswahl nur nach Metadaten."
        if model:
            description = item.short_text or item.long_text
            described = [
                (peer, text)
                for peer, text in zip(peers, dataset.descriptions, strict=True)
                if text.strip()
                and (selected_projects is None or peer.project in selected_projects)
                and peer.project != current.project
            ]
            # Similar wording never overrides an incompatible trade, scope or unit.
            candidates = [
                (peer, text)
                for peer, text in described
                if (peer.trade, peer.scope, peer.unit)
                == (current.trade, current.scope, current.unit)
            ]
            peers = []
            retrieval = f"Lokale Ähnlichkeitssuche ({model}, Schwelle {dataset.similarity:g})"
            if not description.strip():
                retrieval += ": Position ohne Beschreibung"
            elif not candidates:
                retrieval += ": keine kompatiblen beschriebenen Vergleichspositionen"
            else:
                try:
                    selected = _select(description, [text for _, text in candidates], dataset)
                    peers = [candidates[i][0] for i in selected]
                    retrieval += f": {len(peers)}/{len(candidates)} ausgewählt"
                except _FAILURES as error:
                    retrieval += f" nicht verfügbar: {_failure(error, model)}"
            if gated := len(described) - len(candidates):
                retrieval += f", {gated} Positionen mit anderem Gewerk, Umfang oder Einheit"
            retrieval += "."
        reports.append(
            {
                "oz": item.oz,
                "position": index,
                "results": compare_history(
                    current,
                    peers,
                    min_projects=dataset.min_projects,
                    threshold=dataset.deviation_threshold,
                ),
                "retrieval": " ".join(filter(None, (project_coverage, retrieval))),
            }
        )
    return reports
