"""Verify retrieval and explicit coverage when the embedding service fails."""

from dataclasses import replace
from decimal import Decimal

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
    assert "Ähnlichkeitssuche: 3/3" in report["retrieval"]
    assert report["results"]["quantity"]["status"] == "anomaly"
    monkeypatch.setattr(history_embeddings, "embed", raising_embedding)
    [report] = report_history(dataset, items)
    assert "nicht verfügbar" in report["retrieval"]
    assert report["results"]["quantity"]["status"] == "insufficient_evidence"


def raising_embedding(*args: object) -> None:
    r"""Simulate an unavailable local server.

    :param \*args: ignored transport arguments.
    :raises OSError: for simulated connection failure.
    """
    raise OSError("offline")
