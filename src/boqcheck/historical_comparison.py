"""Calculate anomalies from explicitly comparable historical positions."""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from statistics import median


@dataclass(frozen=True)
class HistoricalPosition:
    """A sourced observation with canonical metadata supplied by the caller."""

    project: str
    source: str
    trade: str
    scope: str
    unit: str
    quantity: Decimal | None = None
    scale: Decimal | None = None
    scale_unit: str = ""
    price: Decimal | None = None
    price_basis: Decimal | None = None
    currency: str = ""
    price_type: str = ""
    market: str = ""
    price_period: str = ""


def _positive(value: Decimal | None) -> bool:
    """Check that the value can serve as a positive observation or denominator.

    :param value: decimal value if present.
    :returns: whether the value is finite and positive.
    """
    return value is not None and value.is_finite() and value > 0


_REQUIRED = {
    "quantity": (("quantity", "scale"), ("scale_unit",)),
    "unit_price": (("price", "price_basis"), ("currency", "price_type", "market", "price_period")),
}


def _missing(position: HistoricalPosition, kind: str) -> list[str]:
    """List the fields that prevent a normalized observation.

    :param position: observation with source metadata.
    :param kind: quantity or unit price.
    :returns: names of absent texts and of absent or non-positive numbers.
    """
    numbers, texts = _REQUIRED[kind]
    missing = [name for name in numbers if not _positive(getattr(position, name))]
    fields = ("project", "source", "trade", "scope", "unit", *texts)
    return missing + [name for name in fields if not getattr(position, name)]


def _measure(position: HistoricalPosition, kind: str) -> tuple[tuple[str, ...], Decimal] | None:
    """Normalize one observation using its declared denominators.

    :param position: observation with source metadata.
    :param kind: quantity or unit price.
    :returns: the comparison dimensions and normalized value, if supported.
    """
    if _missing(position, kind):
        return None
    numerator, denominator = (getattr(position, name) for name in _REQUIRED[kind][0])
    texts = (getattr(position, name) for name in _REQUIRED[kind][1])
    return (position.trade, position.scope, position.unit, *texts), numerator / denominator


def compare_history(
    current: HistoricalPosition,
    history: list[HistoricalPosition],
    *,
    min_projects: int = 3,
    threshold: Decimal = Decimal("0.30"),
) -> dict:
    """Compare normalized measurements against one median per independent project.

    :param current: current position including the comparison metadata.
    :param history: candidate historical observations.
    :param min_projects: minimum number of independent historical projects.
    :param threshold: relative deviation from the median required outside the peer range.
    :returns: quantity and price results with status, comparison basis, peer evidence,
        the applied rule, missing current fields and counts of skipped peers.
    :raises ValueError: if the comparison settings are invalid.
    """
    if min_projects < 2 or not _positive(threshold):
        raise ValueError("Expected at least two projects and a positive deviation threshold.")
    output = {}
    for kind in ("quantity", "unit_price"):
        observed = _measure(current, kind)
        if observed is None:
            output[kind] = {"status": "unavailable", "missing": _missing(current, kind)}
            continue
        basis, value = observed
        projects = {}
        seen = set()
        excluded = Counter()
        for peer in history:
            identifier = (peer.project, peer.source)
            match = _measure(peer, kind)
            if peer.project == current.project:
                excluded["current_project"] += 1
            elif identifier in seen:
                excluded["duplicate"] += 1
            elif match is None:
                excluded["missing_metadata"] += 1
            elif match[0] != basis:
                excluded["different_basis"] += 1
            else:
                projects.setdefault(peer.project, []).append((peer.source, match[1]))
            seen.add(identifier)
        peers = [
            {"project": project, "value": median([v for _, v in records]), "sources": records}
            for project, records in sorted(projects.items())
        ]
        result = {
            "status": "insufficient_evidence",
            "basis": basis,
            "value": value,
            "peers": peers,
            "min_projects": min_projects,
            "threshold": threshold,
        }
        if excluded:
            result["excluded"] = dict(excluded)
        if len(peers) >= min_projects:
            values = [p["value"] for p in peers]
            center, low, high = median(values), min(values), max(values)
            deviation = (value - center) / center
            anomaly = (value < low or value > high) and abs(deviation) >= threshold
            result.update(
                status="anomaly" if anomaly else "within_reference",
                median=center,
                low=low,
                high=high,
                deviation=deviation,
            )
        output[kind] = result
    return output
