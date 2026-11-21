"""Check quantity and price comparisons against labelled synthetic peers."""

import json
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest

from boqcheck.historical_comparison import HistoricalPosition, compare_history
from boqcheck.history_report import load_dataset


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


def test_missing_fields_and_exclusions() -> None:
    """Name missing current metadata and count peers skipped at the comparison stage."""
    current = HistoricalPosition(
        "current", "OZ 1", "roof", "deck", "m2", D("200"), D("100"), "m2 roof",
        D("3000"), D("100"), "EUR", "net", "demo market", "2026-Q4",
    )  # fmt: skip
    peers = [replace(current, project=f"demo-{i}", source=f"OZ {i}") for i in range(3)]
    missing = compare_history(replace(current, quantity=D("0"), currency="", price=None), peers)
    assert missing["quantity"] == {"status": "unavailable", "missing": ["quantity"]}
    assert missing["unit_price"]["missing"] == ["price", "currency"]
    results = compare_history(
        current,
        [
            *peers,
            current,
            peers[0],
            replace(peers[0], source="OZ 9", unit="kg"),
            replace(peers[1], project="no-meta", scale_unit="", price_period=""),
        ],
    )
    for kind in ("quantity", "unit_price"):
        assert results[kind]["excluded"] == {
            "current_project": 1,
            "duplicate": 1,
            "missing_metadata": 1,
            "different_basis": 1,
        }
    assert "excluded" not in compare_history(current, peers)["quantity"]


def test_price_compatibility() -> None:
    """Normalize prices per basis and exclude peers that differ in any one price field."""
    current = HistoricalPosition(
        "current", "OZ 1", "roof", "deck", "m2", price=D("1500"), price_basis=D("100"),
        currency="EUR", price_type="net", market="demo market", price_period="2026-Q4",
    )  # fmt: skip
    peers = [
        replace(current, project="per-m2", source="OZ 1", price=D("12"), price_basis=D("1")),
        replace(current, project="per-10", source="OZ 2", price=D("140"), price_basis=D("10")),
        replace(current, project="per-100", source="OZ 3", price=D("1600")),
    ]
    normal = compare_history(current, peers)["unit_price"]
    assert normal["status"] == "within_reference"
    assert (normal["median"], normal["low"], normal["high"]) == (D("14"), D("12"), D("16"))
    assert [peer["sources"] for peer in normal["peers"]] == [
        [("OZ 2", D("14"))],
        [("OZ 3", D("16"))],
        [("OZ 1", D("12"))],
    ]
    assert compare_history(replace(current, price=D("3000")), peers)["unit_price"]["status"] == (
        "anomaly"
    )
    for field, value in (
        ("trade", "facade"),
        ("scope", "insulation"),
        ("unit", "m"),
        ("currency", "CHF"),
        ("price_type", "gross"),
        ("market", "other market"),
        ("price_period", "2020-Q1"),
    ):
        changed = [*peers[:2], replace(peers[2], **{field: value})]
        result = compare_history(current, changed)["unit_price"]
        assert result["status"] == "insufficient_evidence", field
        assert result["excluded"] == {"different_basis": 1}, field
    assert compare_history(current, [])["unit_price"]["status"] == "insufficient_evidence"


def _dataset(tmp_path: Path, **changes: object) -> Path:
    r"""Write a minimal dataset manifest.

    :param tmp_path: folder for the manifest.
    :param \*\*changes: top-level fields to override.
    :returns: manifest path.
    """
    row = dict(project="p", source="s", trade="t", scope="c", unit="m2", price=100)
    data = dict(filename="a.xlsx", sha256="", synthetic=True, current={}, peers=[row])
    path = tmp_path / "history.json"
    path.write_text(json.dumps({**data, **changes}), "utf8")
    return path


def test_dataset_validation(tmp_path: Path) -> None:
    """Accept identical re-ingest, reject conflicts, invalid price types and unapproved data.

    :param tmp_path: folder for the manifests.
    """
    row = dict(project="p", source="s", trade="t", scope="c", unit="m2", description="x")
    dataset = load_dataset(_dataset(tmp_path, peers=[dict(row, price=100), dict(row, price="1E2")]))
    assert len(dataset.peers) == 1 and dataset.descriptions == ("x",)
    for peers in (
        [dict(row, price=100), dict(row, price=101)],
        [row, dict(row, description="y")],
        [dict(row, price_type="brutto")],
    ):
        with pytest.raises(ValueError, match="Invalid historical dataset"):
            load_dataset(_dataset(tmp_path, peers=peers))
    with pytest.raises(ValueError, match="Invalid historical dataset"):
        load_dataset(_dataset(tmp_path, synthetic=False))
    approved = load_dataset(_dataset(tmp_path, synthetic=False, authorization="Vertrag 7"))
    assert approved.authorization == "Vertrag 7"


def test_anomaly_settings(tmp_path: Path) -> None:
    """Read the minimum peer count and deviation, rejecting values that are not exact numbers.

    :param tmp_path: folder for the manifests.
    """
    default = load_dataset(_dataset(tmp_path))
    assert (default.min_projects, default.deviation_threshold) == (3, D("0.30"))
    dataset = load_dataset(_dataset(tmp_path, min_projects=4, deviation_threshold=1))
    assert (dataset.min_projects, dataset.deviation_threshold) == (4, D(1))
    assert load_dataset(_dataset(tmp_path, deviation_threshold=0.5)).deviation_threshold == D("0.5")
    for changes in (
        dict(min_projects=True),
        dict(min_projects=1),
        dict(min_projects=3.0),
        dict(deviation_threshold=True),
        dict(deviation_threshold=0),
        dict(deviation_threshold=-0.1),
        dict(deviation_threshold=None),
        dict(deviation_threshold="0.3"),
        dict(deviation_threshold=float("nan")),
        dict(deviation_threshold=float("inf")),
    ):
        with pytest.raises(ValueError, match="Invalid historical dataset"):
            load_dataset(_dataset(tmp_path, **changes))
