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
# A DOCX heading can end with the unit in brackets ("[Mt.]"), which an LV keeps in its own
# column. Placeholders such as [FIRMA_096] replace words of the Kurztext, so they stay.
_UNIT = re.compile(r"\s+\[[^\s\[\]_]+\]$")
_PROPERTY = re.compile(rf"({'|'.join(_FIELDS)})\s*:\s*(.+?)[.,]?$", re.I)
# Free text and compound labels ("Wanddicke") also name a field.
_MENTION = re.compile("|".join(_FIELDS), re.I)
# Qualifiers, comparisons, alternatives and ranges make a value inexact. The model comparison
# caps its status on the same markers.
_AMBIGUOUS = re.compile(
    r"\b(?:ca|circa|min|mind|mindestens|max|höchstens|bis|über|oder)\b\.?|[<>]"
    r"|\d+(?:[,.]\d+)?\s*[-–]\s*(?=\d+(?:[,.]\d+)?\s*(?:mm|cm|m)\b)",
    re.I,
)


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


def _heading_key(text: str) -> tuple | None:
    """Read the match key of a DOCX position heading without a bracketed unit at its end.

    :param text: paragraph or cell text before an optional ";".
    :returns: key as built by _key, or None if the text is no position heading.
    """
    heading = _HEADING.fullmatch(text.strip())
    return _key(heading[1], _UNIT.sub("", heading[2])) if heading else None


def _property(text: str) -> tuple[str, str] | None:
    """Parse one labelled value; only a value in a supported form alone is exact.

    :param text: one statement: a ";" segment, or a label line joined with its value line.
    :returns: field and normalized value, "open" or "ambiguous", or None if the text does not
        start with a supported label and a colon.
    """
    m = _PROPERTY.fullmatch(text.strip())
    if not m:
        return None
    key, raw = m[1].casefold(), m[2]
    if re.fullmatch(_OPEN, raw, re.I):
        return key, "open"
    if not re.fullmatch(_FIELDS[key][1], raw, re.I):
        return key, "ambiguous"
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


def _statements(texts: list[str]) -> list[tuple[str, str, int, int]]:
    """Read the fields that the lines of one position or one DOCX block state.

    A line that ends with a field label ("Dicke:") and a next line that starts with a value,
    after optional qualifiers, form one statement. Each ";" segment is read on its own.

    :param texts: lines in reading order.
    :returns: field, value ("ambiguous" for a field named without its own label, else as
        _property gives it) and the indices of the first and the last source line.
    """
    found, i = [], 0
    while i < len(texts):
        text, last = texts[i].strip(), i
        label = _MENTION.search(text) if text.endswith(":") else None
        if label and i + 1 < len(texts):
            form = _FIELDS[label[0].casefold()][1]
            qualified = rf"(?:(?:{_AMBIGUOUS.pattern})\s*)*(?:{_OPEN}|{form})"
            if re.match(qualified, texts[i + 1].strip(), re.I):
                last += 1
                text += " " + texts[last].strip()
        for segment in text.split(";"):
            if prop := _property(segment):
                found.append((*prop, i, last))
            else:
                named = dict.fromkeys(m[0].casefold() for m in _MENTION.finditer(segment))
                found.extend((key, "ambiguous", i, last) for key in named)
        i = last + 1
    return found


def _component(rows: list[Line]) -> str | None:
    """Read the component that the first row of one OZ group states.

    The row is one line "OZ Component", or an OZ cell followed by the Kurztext cell on the
    same row, as in the sample PDFs. A cell with the position type ("*** Bedarfsposition ohne
    GB") is no Kurztext.

    :param rows: lines of one OZ in reading order.
    :returns: heading or Kurztext, or None if the lines have no OZ or their first row states
        no component.
    """
    first, oz = rows[0], rows[0].oz
    if heading := _HEADING.fullmatch(first.text):
        return heading[2] if heading[1] == oz else None
    if len(rows) < 2 or first.text.removesuffix(".") != oz:
        return None
    # The first line of a wrapped Kurztext extracts before the OZ cell, so the line after the
    # cell is then a fragment on the next row.
    cell, text = first.quad.rect, rows[1].quad.rect
    same_row = rows[1].page == first.page and cell.y0 < (text.y0 + text.y1) / 2 < cell.y1
    return rows[1].text if same_row and not rows[1].text.startswith("*") else None


def pdf_properties(pages: list[list[Line]]) -> list[dict]:
    """Index field statements within positions whose first row states the component.

    :param pages: extracted lines in reading order.
    :returns: classified values and their source references; a value on the line after its
        label cites the page of the value line and both lines.
    """
    values = []
    for oz, lines in groupby(chain.from_iterable(pages), key=lambda line: line.oz):
        rows = list(lines)
        component = _component(rows)
        if component is None:
            continue
        texts = [line.text for line in rows[1:]]
        for key, value, first, last in _statements(texts):
            page = rows[last + 1].page + 1
            source = {
                "oz": oz,
                "page": page,
                "excerpt": "\n".join(texts[first : last + 1]),
                "reference": f"PDF-Seite {page}, OZ {oz} · {component}",
            }
            values.append(
                {"oz": oz, "component": component, "key": key, "value": value, "source": source}
            )
    return values


def pdf_positions(pages: list[list[Line]]) -> tuple[list[dict], int]:
    """Collect the lines of positions whose first row states the component.

    :param pages: extracted lines in reading order.
    :returns: OZ, component and lines with stable IDs and 1-based pages, and the number of
        positions with an OZ.
    """
    positions, number, count = [], 0, 0
    for oz, lines in groupby(chain.from_iterable(pages), key=lambda line: line.oz):
        rows = list(lines)
        count += oz is not None
        if component := _component(rows):
            positions.append(
                {
                    "oz": oz,
                    "component": component,
                    "lines": [
                        {"id": f"L{number + i}", "page": line.page + 1, "text": line.text}
                        for i, line in enumerate(rows)
                    ],
                }
            )
        number += len(rows)
    return positions, count


def _blocks(entries: list[dict]) -> list[tuple[tuple, list[dict]]]:
    """Group DOCX paragraphs under the OZ heading that precedes them.

    A block ends at the next heading or at an entry that is no body paragraph.

    :param entries: attachment entries in document order.
    :returns: match key and entries, heading first, for each heading in document order.
    """
    blocks, current = [], None
    for entry in entries:
        if key := _heading_key(entry["text"].partition(";")[0]):
            current = [entry]
            blocks.append((key, current))
        elif current is not None and entry["id"].startswith("P"):
            current.append(entry)
        else:
            current = None
    return blocks


def compare_attachment(result: dict, attachment: dict) -> dict:
    """Compare unique same-position, same-component fields and retain both citations.

    An ambiguous statement on either side gives no finding: the pair is listed instead.

    :param result: PDF or GAEB review.
    :param attachment: imported DOCX with immutable source IDs.
    :returns: updated review, automatic comparison coverage, the pairs not compared because
        of an ambiguous statement and the number of DOCX headings without an LV position of
        the same OZ and component.
    """
    findings = [dict(f) for f in result["findings"]]
    positions = {_key(p["oz"], p["component"]) for p in result.get("attachment_positions", [])}
    candidates = defaultdict(list)
    unmatched = 0
    for position, block in _blocks(attachment["entries"]):
        unmatched += position not in positions
        header = block[0]
        # The heading names the position; only the text after its first ";" states values.
        texts = [header["text"].partition(";")[2], *(entry["text"] for entry in block[1:])]
        for key, value, first, last in _statements(texts):
            evidence = block[first : last + 1]
            excerpt = [header, *(entry for entry in evidence if entry is not header)]
            source = {
                "docx": evidence[-1]["id"],
                "reference": f"{attachment['name']} · {evidence[-1]['reference']}",
                "excerpt": "\n".join(entry["text"] for entry in excerpt),
            }
            candidates[*position, key].append((value, source))
    grouped = defaultdict(list)
    for field in result.get("attachment_properties", []):
        grouped[*_key(field["oz"], field["component"]), field["key"]].append(field)
    checked, ambiguous = 0, []
    for key, fields in grouped.items():
        matches = candidates[key]
        if matches and "ambiguous" in [f["value"] for f in fields] + [m[0] for m in matches]:
            ambiguous.append(
                {
                    "oz": fields[0]["oz"],
                    "component": fields[0]["component"],
                    "label": _FIELDS[key[-1]][0],
                    "sources": [f["source"] for f in fields] + [m[1] for m in matches],
                }
            )
            continue
        if len(matches) != 1 or len(fields) != 1:
            continue
        field = fields[0]
        value, docx = matches[0]
        if value == "open":
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
            sources=[src, docx],
        )
        if existing is None:
            findings.append(finding)
    return {
        **result,
        "attachment": attachment,
        "findings": findings,
        "attachment_checked": checked,
        "attachment_ambiguous": ambiguous,
        "attachment_unmatched": unmatched,
    }
