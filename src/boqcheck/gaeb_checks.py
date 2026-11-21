"""Check normalized GAEB items for structural errors and comparable totals."""

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from boqcheck import parse
from boqcheck.model import BoQ


def check_boq(boq: BoQ) -> dict:
    """Return structural findings and deterministic arithmetic coverage.

    :param boq: parsed bill of quantities.
    :returns: serializable report with source, findings, and arithmetic counts.
    """
    findings = []
    positions: dict[str, list[int]] = defaultdict(list)
    checked = skipped = 0
    for row, item in enumerate(boq.items, 1):
        reference = {"oz": item.oz, "item": row}
        if item.oz:
            positions[item.oz].append(row)
        missing = []
        if not item.oz:
            missing.append("RNoPart")
        if not (item.short_text.strip() or item.long_text.strip()):
            missing.append("Description")
        invalid = dict(item.invalid_numbers)
        if not (item.lump_sum or item.provisional):
            if item.quantity is None and "Qty" not in invalid:
                missing.append("Qty")
            if not item.unit.strip():
                missing.append("QU")
        if missing:
            findings.append({"code": "missing_fields", **reference, "fields": missing})
        if item.price_basis is not None and item.price_basis <= 0:
            invalid["PriceBasis"] = str(item.price_basis)
        if invalid:
            findings.append({"code": "invalid_numbers", **reference, "values": invalid})

        qty, price, basis, total = item.quantity, item.unit_price, item.price_basis, item.line_total
        if price is None and total is None:
            continue
        if (
            invalid
            or qty is None
            or price is None
            or basis is None
            or total is None
            or item.adjusted_total
            or item.lump_sum
            or item.provisional
            or not item.unit.strip()
        ):
            skipped += 1
            continue
        # Decimal inputs are exact, so round the resulting rational number once, at the cent.
        scaled = Fraction(qty) * Fraction(price) / Fraction(basis) * 100
        cents = int(abs(scaled) + Fraction(1, 2))
        sign = "-" if scaled < 0 and cents else ""
        expected = Decimal(f"{sign}{cents // 100}.{cents % 100:02d}")
        checked += 1
        if total != expected:
            findings.append(
                {
                    "code": "line_total_mismatch",
                    **reference,
                    "quantity": str(qty),
                    "unit_price": str(price),
                    "price_basis": str(basis),
                    "actual": str(total),
                    "expected": str(expected),
                }
            )

    for oz, rows in positions.items():
        if len(rows) > 1:
            findings.append({"code": "duplicate_oz", "oz": oz, "items": rows})

    return {
        "source": boq.source,
        "phase": boq.phase,
        "version": boq.version,
        "version_date": boq.version_date,
        "namespace": boq.namespace,
        "warnings": list(boq.warnings),
        "items": len(boq.items),
        "arithmetic_checked": checked,
        "arithmetic_skipped": skipped,
        "findings": findings,
    }


def main() -> None:
    """Read one X83 file and print a JSON check report."""
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("file", type=Path)
    file = arguments.parse_args().file
    try:
        report = check_boq(parse(file.name, file.read_bytes()))
    except (ValueError, OSError) as error:
        arguments.exit(2, json.dumps({"error": str(error)}) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
