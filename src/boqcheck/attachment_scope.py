"""Compare explicitly labelled PDF specifications with an attached position description."""

import re
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
from itertools import chain, groupby

from .pdf_extract import Line
from .scope import _FIELDS, _OPEN

# A two-level OZ (one section level, as in some GAEB files) counts only after an explicit "OZ",
# because amounts such as "1.000 Stück" also have two levels.
_HEADING = re.compile(
    r"(?:OZ\s+|(?=\d+(?:\.\d+){2}))(\d+(?:\.\d+)+[A-Za-z]?)\.?\s+(?:[–—-]\s+)?(.+)", re.I
)
_PROPERTY = re.compile(rf"({'|'.join(_FIELDS)})\s*:\s*(.+?)\.?$", re.I)


def _key(oz: str, component: str) -> tuple:
    """Build the match key of a position: OZ levels as integers and the folded component.

    A DOCX may drop the zero padding of a GAEB OZ ("3.1.3" for "03.01.0003"). An OZ without
    numeric levels, as an XLSX cell may hold, stays text and so matches no DOCX heading.

    :param oz: OZ as written, with an optional index letter.
    :param component: position heading or Kurztext.
    :returns: comparable OZ and component.
    """
    levels = re.fullmatch(r"(\d+(?:\.\d+)*)([A-Za-z]?)", oz)
    number = (tuple(map(int, levels[1].split("."))), levels[2]) if levels else oz
    return number, " ".join(component.split()).casefold()


def _property(text: str) -> tuple[str, str] | None:
    """Parse one complete, unconditional labelled value.

    :param text: wording of one source line.
    :returns: field and normalized value, or None for unsupported wording.
    """
    m = _PROPERTY.fullmatch(text.strip())
    if not m:
        return None
    key, raw = m[1].casefold(), m[2]
    if re.fullmatch(_OPEN, raw, re.I):
        return key, "open"
    if not re.fullmatch(_FIELDS[key][1], raw, re.I):
        return key, "unknown"
    if key in ("dicke", "schichtdicke"):
        n, unit = re.fullmatch(r"(\d+(?:[,.]\d+)?)\s*(mm|cm|m)", raw, re.I).groups()
        return key, str(
            (
                Decimal(n.replace(",", ".")) * {"m": 1000, "cm": 10, "mm": 1}[unit.lower()]
            ).normalize()
        )
    return key, {"an": "auftragnehmer", "ag": "auftraggeber", "bauseits": "auftraggeber"}.get(
        raw.casefold(), raw.casefold()
    )


def pdf_properties(pages: list[list[Line]]) -> list[dict]:
    """Index labelled properties within positions having an explicit component heading.

    :param pages: extracted lines in reading order.
    :returns: comparable values and their source references.
    """
    values = []
    for oz, lines in groupby(chain.from_iterable(pages), key=lambda line: line.oz):
        rows = list(lines)
        heading = _HEADING.fullmatch(rows[0].text)
        if not heading or heading[1] != oz:
            continue
        for line in rows[1:]:
            if prop := _property(line.text):
                values.append(
                    {
                        "oz": oz,
                        "component": heading[2],
                        "key": prop[0],
                        "value": prop[1],
                        "source": {
                            "oz": oz,
                            "page": line.page + 1,
                            "excerpt": line.text,
                            "reference": f"PDF-Seite {line.page + 1}, OZ {oz} · {heading[2]}",
                        },
                    }
                )
    return values


def pdf_positions(pages: list[list[Line]]) -> list[dict]:
    """Collect the lines of positions having an explicit component heading.

    :param pages: extracted lines in reading order.
    :returns: OZ, component and lines with stable IDs and 1-based pages.
    """
    positions, number = [], 0
    for oz, lines in groupby(chain.from_iterable(pages), key=lambda line: line.oz):
        rows = list(lines)
        heading = _HEADING.fullmatch(rows[0].text)
        if heading and heading[1] == oz:
            positions.append(
                {
                    "oz": oz,
                    "component": heading[2],
                    "lines": [
                        {"id": f"L{number + i}", "page": line.page + 1, "text": line.text}
                        for i, line in enumerate(rows)
                    ],
                }
            )
        number += len(rows)
    return positions


def compare_attachment(result: dict, attachment: dict) -> dict:
    """Compare unique same-position, same-component fields and retain both citations.

    :param result: PDF or GAEB review.
    :param attachment: imported DOCX with immutable source IDs.
    :returns: updated review, automatic comparison coverage and the number of DOCX headings
        without an LV position of the same OZ and component.
    """
    findings = [dict(f) for f in result["findings"]]
    positions = {_key(p["oz"], p["component"]) for p in result.get("attachment_positions", [])}
    candidates = defaultdict(list)
    unmatched = 0
    entries = attachment["entries"]
    for i, entry in enumerate(entries):
        header, sep, rest = entry["text"].partition(";")
        heading = _HEADING.fullmatch(header.strip())
        if not heading:
            continue
        position = _key(heading[1], heading[2])
        unmatched += position not in positions
        evidence_rows = [(entry, rest)]
        if not sep:
            if not entry["id"].startswith("P"):
                continue
            evidence_rows = []
            number = int(entry["id"][1:])
            for j in range(i + 1, len(entries)):
                evidence = entries[j]
                if evidence["id"] != f"P{number + j - i}" or not _PROPERTY.fullmatch(
                    evidence["text"]
                ):
                    break
                evidence_rows.append((evidence, evidence["text"]))
        for evidence, raw in evidence_rows:
            if prop := _property(raw):
                candidates[*position, prop[0]].append((prop[1], entry, evidence))
    grouped = defaultdict(list)
    for field in result.get("attachment_properties", []):
        grouped[*_key(field["oz"], field["component"]), field["key"]].append(field)
    checked = 0
    for key, fields in grouped.items():
        matches = candidates[key]
        if len(matches) != 1 or len(fields) != 1:
            continue
        field = fields[0]
        value, header, evidence = matches[0]
        if value in ("open", "unknown") or fields[0]["value"] == "unknown":
            continue
        checked += 1
        if field["value"] == value:
            continue
        src = field["source"]
        resolved = field["value"] == "open"
        existing = (
            next(
                (
                    f
                    for f in findings
                    if f.get("rule") == "open_scope"
                    and any(
                        s["oz"] == field["oz"] and s["excerpt"] == src["excerpt"]
                        for s in f["sources"]
                    )
                ),
                None,
            )
            if resolved
            else None
        )
        if resolved and existing is None:
            continue
        finding = existing if existing is not None else {}
        # Hashing the LV spelling keeps the IDs that PDF findings had before OZ normalization.
        identity = "|".join((field["oz"], field["component"].casefold(), key[2]))
        label = _FIELDS[key[2]][0]
        question = "" if resolved else f"Welche Angabe zu {label} gilt für OZ {field['oz']}?"
        if existing is not None and existing.get("review_edited"):
            question = existing["question"]
        finding.update(
            id=finding.get("id", "AX-" + sha256(identity.encode()).hexdigest()[:12]),
            assessment="Durch Anlage geklärt" if resolved else "Abweichung zwischen LV und Anlage",
            rule="attachment_scope",
            category="Leistungsumfang",
            method="Abgleich LV / DOCX",
            evidence="Gleiche OZ, Bauteilbezeichnung und Eigenschaft",
            impact=f"Die Angabe zu {label} beeinflusst die Kalkulation für {field['component']}.",
            explanation=(
                f"Die Anlage konkretisiert {label} für OZ {field['oz']}."
                if resolved
                else "LV und Anlage nennen unterschiedliche Werte für "
                f"{label} bei OZ {field['oz']}."
            ),
            question=question,
            review_status=finding.get("review_status", "open"),
            history_match=False,
            sources=[
                src,
                {
                    "docx": evidence["id"],
                    "reference": f"{attachment['name']} · {evidence['reference']}",
                    "excerpt": evidence["text"]
                    if header is evidence
                    else header["text"] + "\n" + evidence["text"],
                },
            ],
        )
        if existing is None:
            findings.append(finding)
    return {
        **result,
        "attachment": attachment,
        "findings": findings,
        "attachment_checked": checked,
        "attachment_unmatched": unmatched,
    }
