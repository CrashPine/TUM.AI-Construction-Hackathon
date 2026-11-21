"""Calculate anomalies from explicitly comparable historical positions."""

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


def _measure(position: HistoricalPosition, kind: str) -> tuple[tuple[str, ...], Decimal] | None:
    """Normalize one observation using its declared denominators.

    :param position: observation with source metadata.
    :param kind: quantity or unit price.
    :returns: the comparison dimensions and normalized value, if supported.
    """
    key = (position.trade, position.scope, position.unit)
    if not all((*key, position.project, position.source)):
        return None
    if kind == "quantity":
        if position.scale_unit and _positive(position.quantity) and _positive(position.scale):
            return (*key, position.scale_unit), position.quantity / position.scale
    elif (
        all((position.currency, position.price_type, position.market, position.price_period))
        and _positive(position.price)
        and _positive(position.price_basis)
    ):
        return (
            (*key, position.currency, position.price_type, position.market, position.price_period),
            position.price / position.price_basis,
        )
    return None


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
    :returns: quantity and price results with status, comparison basis and peer evidence.
    :raises ValueError: if the comparison settings are invalid.
    """
    if min_projects < 2 or not _positive(threshold):
        raise ValueError("Expected at least two projects and a positive deviation threshold.")
    output = {}
    for kind in ("quantity", "unit_price"):
        observed = _measure(current, kind)
        if observed is None:
            output[kind] = {"status": "unavailable"}
            continue
        basis, value = observed
        projects = {}
        seen = set()
        for peer in history:
            identifier = (peer.project, peer.source)
            if peer.project == current.project or identifier in seen:
                continue
            match = _measure(peer, kind)
            if match and match[0] == basis:
                projects.setdefault(peer.project, []).append((peer.source, match[1]))
                seen.add(identifier)
        peers = [
            {"project": project, "value": median([v for _, v in records]), "sources": records}
            for project, records in sorted(projects.items())
        ]
        result = {"status": "insufficient_evidence", "basis": basis, "value": value, "peers": peers}
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
