"""Check quantity and price comparisons against labelled synthetic peers."""

from dataclasses import replace
from decimal import Decimal as D

from boqcheck.historical_comparison import HistoricalPosition, compare_history


def test_comparable_projects() -> None:
    """Check both anomaly types, false matches and insufficient evidence."""
    current = HistoricalPosition(
        "current",
        "OZ 1",
        "roof",
        "deck",
        "m2",
        D("200"),
        D("100"),
        "m2 roof",
        D("3000"),
        D("100"),
        "EUR",
        "net",
        "demo market",
        "2026-Q4",
    )
    peers = [
        replace(current, project=f"demo-{i}", source=f"OZ {i}", quantity=D(qty), price=D(price))
        for i, qty, price in [(1, 90, 900), (2, 100, 1000), (3, 110, 1100)]
    ]
    results = compare_history(
        current,
        peers
        + [
            current,
            peers[0],
            replace(peers[0], project="wrong-unit", unit="kg"),
            replace(peers[1], project="wrong-market", scale_unit="buildings", market="other"),
        ],
    )
    assert results["quantity"]["status"] == results["unit_price"]["status"] == "anomaly"
    assert results["quantity"]["median"] == D("1")
    assert results["unit_price"]["median"] == D("10")
    assert results["unit_price"]["peers"][0]["sources"] == [("OZ 1", D("9"))]
    assert (
        compare_history(peers[1], peers, min_projects=2)["quantity"]["status"] == "within_reference"
    )
    assert compare_history(current, peers[:2])["quantity"]["status"] == "insufficient_evidence"
    assert (
        compare_history(replace(current, price=None), peers)["unit_price"]["status"]
        == "unavailable"
    )
