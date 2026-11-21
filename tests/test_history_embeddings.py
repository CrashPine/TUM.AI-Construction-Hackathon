"""Verify retrieval and explicit coverage when the embedding service fails."""

from dataclasses import replace
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from boqcheck import history_embeddings
from boqcheck.historical_comparison import HistoricalPosition
from boqcheck.history_report import HistoryDataset, report_history
from boqcheck.model import Item


def test_embedding_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exclude dissimilar peers before measuring the current quantity.

    :param monkeypatch: substitute the local embedding transport.
    """
    current = HistoricalPosition(
        "new", "OZ 1", "roof", "deck", "m2", scale=Decimal(100), scale_unit="m2 roof"
    )
    peers = [
        HistoricalPosition(
            f"project-{i}", f"OZ {i}", "roof", "deck", "m2", Decimal(100), Decimal(100), "m2 roof"
        )
        for i in range(4)
    ]
    dataset = HistoryDataset(
        "test.xlsx",
        "",
        True,
        {"1": current},
        peers,
        ("Deck A", "Deck B", "Deck C", "Unrelated"),
        "test",
    )
    items = (Item("1", "Roof deck", "", Decimal(200), "m2"),)

    def embeddings(model: str, port: int, texts: list[str]) -> list[tuple[float, ...]]:
        """Return synthetic normalized vectors for the submitted descriptions.

        :param model: configured model.
        :param port: configured loopback port.
        :param texts: requested descriptions in order.
        :returns: vectors for the query and four candidates.
        """
        if texts[0] == "Current roof project":
            assert texts[1:] == ["Roof A", "Roof B", "Roof C", "Road project"]
            return [(1.0, 0.0)] * 4 + [(0.0, 1.0)]
        if len(texts) == 4:
            assert texts == ["Roof deck", "Deck A", "Deck B", "Deck C"]
            return [(1.0, 0.0)] * 4
        assert (model, port, texts) == ("test", 11434, ["Roof deck", *dataset.descriptions])
        return [(1.0, 0.0)] * 4 + [(0.0, 1.0)]

    monkeypatch.setattr(history_embeddings, "embed", embeddings)
    [report] = report_history(dataset, items)
    assert "3/4" in report["retrieval"]
    comparison = report["results"]["quantity"]
    assert comparison["status"] == "anomaly"
    assert len(comparison["peers"]) == 3
    dataset = replace(
        dataset,
        current_profile="Current roof project",
        project_profiles=dict(
            zip(
                (peer.project for peer in peers),
                ("Roof A", "Roof B", "Roof C", "Road project"),
                strict=True,
            )
        ),
    )
    [report] = report_history(dataset, items)
    assert "Projektvorauswahl: 3/4" in report["retrieval"]
    assert "(test, Schwelle 0.75): 3/3 ausgewählt." in report["retrieval"]
    assert report["results"]["quantity"]["status"] == "anomaly"
    monkeypatch.setattr(history_embeddings, "embed", raising_embedding)
    [report] = report_history(dataset, items)
    assert "nicht verfügbar: lokaler Dienst nicht erreichbar" in report["retrieval"]
    assert report["results"]["quantity"]["status"] == "insufficient_evidence"


def dataset_with(peers: list[HistoricalPosition], **changes: object) -> HistoryDataset:
    r"""Build a dataset whose current roof deck has 100 m2 of roof.

    :param peers: historical positions, each described as a roof deck.
    :param \*\*changes: dataset fields to override.
    :returns: synthetic dataset with the embedding model ``test``.
    """
    current = HistoricalPosition(
        "new", "OZ 1", "roof", "deck", "m2", scale=Decimal(100), scale_unit="m2 roof"
    )
    dataset = HistoryDataset(
        "test.xlsx", "", True, {"1": current}, peers, ("Roof deck",) * len(peers), "test"
    )
    return replace(dataset, **changes)


def peer(project: str, unit: str = "m2", trade: str = "roof") -> HistoricalPosition:
    """Return a historical roof deck position.

    :param project: independent project ID.
    :param unit: position unit.
    :param trade: position trade.
    :returns: peer with quantity 100 per 100 m2 of roof.
    """
    return HistoricalPosition(
        project, "OZ 1", trade, "deck", unit, Decimal(100), Decimal(100), "m2 roof"
    )


def matching_embedding(model: str, port: int, texts: list[str]) -> list[tuple[float, ...]]:
    """Return identical vectors so every submitted candidate is similar.

    :param model: configured model.
    :param port: configured loopback port.
    :param texts: query followed by candidates.
    :returns: one vector per text.
    """
    return [(1.0, 0.0)] * len(texts)


ITEMS = (Item("1", "Roof deck", "", Decimal(100), "m2"),)


def test_metadata_gate_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Count same-wording peers with another unit or trade and never select them.

    :param monkeypatch: substitute the local embedding transport.
    """
    monkeypatch.setattr(history_embeddings, "embed", matching_embedding)
    peers = [peer("a"), peer("b"), peer("c"), peer("d", unit="m"), peer("e", trade="road")]
    [report] = report_history(dataset_with(peers), ITEMS)
    assert report["retrieval"] == (
        "Lokale Ähnlichkeitssuche (test, Schwelle 0.75): 3/3 ausgewählt, "
        "2 Positionen mit anderem Gewerk, Umfang oder Einheit."
    )
    sources = report["results"]["quantity"]["peers"]
    assert [entry["project"] for entry in sources] == ["a", "b", "c"]
    [report] = report_history(dataset_with(peers[3:]), ITEMS)
    assert report["retrieval"] == (
        "Lokale Ähnlichkeitssuche (test, Schwelle 0.75): keine kompatiblen beschriebenen "
        "Vergleichspositionen, 2 Positionen mit anderem Gewerk, Umfang oder Einheit."
    )
    assert report["results"]["quantity"]["status"] == "insufficient_evidence"


def test_unprofiled_projects_and_unconfigured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report projects without a profile and say when no similarity search runs.

    :param monkeypatch: substitute the local embedding transport.
    """
    monkeypatch.setattr(history_embeddings, "embed", matching_embedding)
    peers = [peer("a"), peer("b"), peer("c")]
    dataset = dataset_with(peers, current_profile="Roof", project_profiles={"a": "Roof"})
    [report] = report_history(dataset, ITEMS)
    assert report["retrieval"].startswith(
        "Projektvorauswahl: 1/1 ausgewählt, 2 Projekte ohne Profil ausgeschlossen. "
    )
    [report] = report_history(dataset_with(peers, embedding_model=""), ITEMS)
    assert (
        report["retrieval"] == "Keine Ähnlichkeitssuche konfiguriert; Auswahl nur nach Metadaten."
    )
    assert len(report["results"]["quantity"]["peers"]) == 3


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (
            HTTPError("u", 404, "", None, BytesIO(b'{"error":"model \\"test\\" not found"}')),
            "Modell test nicht installiert",
        ),
        (
            HTTPError("u", 404, "", None, BytesIO(b"page not found")),
            "lokaler Dienst antwortete mit HTTP 404",
        ),
        (
            HTTPError("u", 500, "", None, BytesIO(b"model not found")),
            "lokaler Dienst antwortete mit HTTP 500",
        ),
        (TimeoutError(), "lokaler Dienst nicht erreichbar"),
        (ValueError("Invalid embedding vector."), "ungültige Antwort des lokalen Dienstes"),
    ],
)
def test_failure_reason(monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str) -> None:
    """Name the failure only as far as the response proves it.

    :param monkeypatch: substitute the local embedding transport.
    :param error: exception raised by the transport.
    :param reason: expected reason in the report.
    """
    monkeypatch.setattr(history_embeddings, "embed", Mock(side_effect=error))
    [report] = report_history(dataset_with([peer("a")]), ITEMS)
    assert f"nicht verfügbar: {reason}." in report["retrieval"]


def raising_embedding(*args: object) -> None:
    r"""Simulate an unavailable local server.

    :param \*args: ignored transport arguments.
    :raises OSError: for simulated connection failure.
    """
    raise OSError("offline")


def test_quantity_anomaly_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flag a labelled outlier per m2 of roof by the configured rule, never by similarity.

    :param monkeypatch: substitute the local embedding transport.
    """
    monkeypatch.setattr(history_embeddings, "embed", matching_embedding)
    peers = [replace(peer(p), quantity=Decimal(q)) for p, q in (("a", 90), ("b", 100), ("c", 110))]
    anomaly = (Item("1", "Roof deck", "", Decimal(200), "m2"),)

    def quantity(dataset: HistoryDataset, items: tuple[Item, ...] = anomaly) -> dict:
        """Return the quantity comparison of the only position.

        :param dataset: historical dataset.
        :param items: current positions.
        :returns: quantity result.
        """
        return report_history(dataset, items)[0]["results"]["quantity"]

    result = quantity(dataset_with(peers))
    assert (result["status"], result["value"], result["deviation"]) == ("anomaly", 2, 1)
    assert (result["low"], result["high"], result["min_projects"]) == (
        Decimal("0.9"),
        Decimal("1.1"),
        3,
    )
    assert result["basis"][:4] == ("roof", "deck", "m2", "m2 roof")
    assert [p["sources"] for p in result["peers"]][0] == [("OZ 1", Decimal("0.9"))]
    assert quantity(dataset_with(peers), ITEMS)["status"] == "within_reference"
    assert quantity(dataset_with(peers, embedding_model=""))["status"] == "anomaly"
    relaxed = dataset_with(peers, deviation_threshold=Decimal("1.5"))
    assert quantity(relaxed)["status"] == "within_reference"
    wider = [*peers, replace(peer("d"), scale_unit="m2 facade")]
    result = quantity(dataset_with(wider, min_projects=4))
    assert result["status"] == "insufficient_evidence" and "median" not in result
    assert result["excluded"] == {"different_basis": 1} and len(result["peers"]) == 3
    unscaled = dataset_with(peers)
    unscaled.current["1"] = replace(unscaled.current["1"], scale=None)
    assert quantity(unscaled) == {"status": "unavailable", "missing": ["scale"]}
