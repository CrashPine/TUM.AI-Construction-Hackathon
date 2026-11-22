"""Ask the local model to compare an LV position with the DOCX block for the same OZ."""

import re
from hashlib import sha256
from urllib.error import URLError

from . import semantic
from .attachment_scope import _HEADING, _key

# Template wording makes a difference legitimate, so the code, not the model, caps the status.
_ALTERNATIVE = re.compile(
    r"alternativ|wahlweise|bedarfsposition|eventualposition|oder\s+gleichwertig", re.I
)


def _blocks(entries: list[dict]) -> dict[tuple, list[dict]]:
    """Group DOCX paragraphs under the OZ heading that precedes them.

    :param entries: attachment entries in document order.
    :returns: heading entry and following paragraphs, keyed like the LV positions.
    """
    blocks, current = {}, None
    for entry in entries:
        heading = _HEADING.fullmatch(entry["text"].partition(";")[0].strip())
        if heading:
            current = blocks.setdefault(_key(heading[1], heading[2]), [])
            current.append(entry)
        elif current is not None and entry["id"].startswith("P"):
            current.append(entry)
        else:
            current = None
    return blocks


def review_attachment(result: dict, config: semantic.SemanticConfig | None) -> dict:
    """Add model-proposed contradictions between LV positions and their DOCX blocks.

    Each OZ and component pair present in both documents costs one request. The budget
    ``config.max_requests`` applies again here, separately from the PDF review.

    :param result: review after the deterministic attachment comparison.
    :param config: model selected for the review, or None.
    :returns: a new review with grounded findings and an ``attachment_review`` summary.
    """
    if config is None:
        summary = "Modellabgleich LV / DOCX nicht ausgeführt: kein Modell gewählt."
        return {**result, "attachment_review": {"summary": summary, "warnings": []}}
    attachment = result["attachment"]
    blocks = _blocks(attachment["entries"])
    pairs = [
        (position, blocks[key])
        for position in result.get("attachment_positions", [])
        if (key := _key(position["oz"], position["component"])) in blocks
    ]
    findings = [dict(f) for f in result["findings"]]
    warnings, completed, rejected, proposed = [], 0, 0, 0
    for index, (position, block) in enumerate(pairs):
        if index == config.max_requests:
            warnings.append(
                f"Budget erschöpft: {len(pairs) - index} Positionen nicht mit Modell verglichen."
            )
            break
        left = {line["id"]: line for line in position["lines"]}
        right = {entry["id"]: entry for entry in block}
        payload = {
            "left": [{**line, "oz": position["oz"]} for line in position["lines"]],
            "right": [{"id": entry["id"], "text": entry["text"]} for entry in block],
        }
        try:
            records = semantic._request(config, payload)
        except (URLError, OSError, ValueError, KeyError, IndexError, TypeError):
            warnings.append(f"Modellabgleich LV / DOCX ab Position {index + 1} nicht verfügbar.")
            break
        completed += 1
        for record in records:
            proposed += 1
            fields = [
                record.get(name) if isinstance(record, dict) else None
                for name in ("left_id", "right_id", "left_quote", "right_quote", "status")
            ] + [record.get("explanation") if isinstance(record, dict) else None]
            a, b, aq, bq, status, explanation = fields
            if (
                not all(isinstance(value, str) and value.strip() for value in fields)
                or status not in ("conflict", "needs_scope_check")
                or a not in left
                or b not in right
                or aq not in left[a]["text"]
                or bq not in right[b]["text"]
            ):
                rejected += 1
                continue
            line, entry = left[a], right[b]
            if _ALTERNATIVE.search(line["text"] + "\n" + entry["text"]):
                status = "needs_scope_check"
            # A GAEB position is one row of the review; a PDF position can span pages.
            anchor = (
                {"position": position["position"], "reference": position["reference"]}
                if "position" in position
                else {
                    "page": line["page"],
                    "reference": f"PDF-Seite {line['page']}, OZ {position['oz']} · "
                    f"{position['component']}",
                }
            )
            question = record.get("question")
            findings.append(
                {
                    "id": "AS-"
                    + sha256("|".join((position["oz"], a, b)).encode()).hexdigest()[:12],
                    "assessment": "Widerspruch zwischen LV und Anlage"
                    if status == "conflict"
                    else "Anwendbarkeit zwischen LV und Anlage prüfen",
                    "rule": "attachment_semantic",
                    "category": "Leistungsumfang",
                    "method": "Modellabgleich LV / DOCX",
                    "evidence": "Zwei Textstellen belegt"
                    if status == "conflict"
                    else "Zwei Textstellen; Anwendbarkeit offen",
                    "impact": "Siehe Begründung des Modellvorschlags.",
                    "explanation": explanation,
                    "question": question if isinstance(question, str) else "",
                    "review_status": "open",
                    "history_match": False,
                    "sources": [
                        {"oz": position["oz"], **anchor, "excerpt": line["text"]},
                        {
                            "docx": b,
                            "reference": f"{attachment['name']} · {entry['reference']}",
                            "excerpt": entry["text"],
                        },
                    ],
                }
            )
    accepted = proposed - rejected
    if rejected:
        warnings.append(f"Modellvorschläge ohne gültigen Quellenbeleg verworfen: {rejected}.")
    if not pairs:
        summary = "Modellabgleich LV / DOCX: keine Position mit gleicher OZ und Bauteil."
    else:
        summary = (
            f"Modellabgleich LV / DOCX: {completed}/{len(pairs)} zugeordnete Positionen "
            f"verglichen, {accepted} Vorschläge mit Quellenbeleg."
        )
        if completed and not proposed:
            summary += " Das Modell hat keinen Widerspruch gemeldet; das ist kein Nachweis."
    return {
        **result,
        "findings": findings,
        "attachment_review": {"summary": summary, "warnings": warnings},
    }
