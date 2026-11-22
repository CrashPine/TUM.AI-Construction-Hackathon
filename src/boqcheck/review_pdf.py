"""Review an LV PDF and publish its annotated copy and separate findings log."""

import argparse
import json
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

from .attachment_scope import pdf_positions, pdf_properties
from .contradictions import Finding, find_contradictions, rule_scope
from .history import review_model_patterns
from .pdf_annotate import annotate
from .pdf_extract import Line, extract
from .price_table import table_prices
from .scope import find_scope_questions
from .semantic import SemanticConfig, semantic_review
from .spelling import load_lexicon


def _reference(passage: tuple[Line, ...]) -> str:
    """Format a physical PDF page and its source labels.

    :param passage: nonempty excerpt from one page.
    :returns: human-readable German source reference.
    """
    line = passage[0]
    reference = f"PDF-Seite {line.page + 1}"
    if line.label:
        reference += f" (Druckseite {line.label})"
    if line.oz:
        reference += f", OZ {line.oz}"
    return reference


def _excerpt(passage: tuple[Line, ...]) -> str:
    """Join source lines for a compact display.

    :param passage: source lines in reading order.
    :returns: excerpt with line breaks replaced by spaces.
    """
    return " ".join(line.text for line in passage)


def _model_batch(
    pages: list[list[Line]],
    semantic: SemanticConfig | None,
    templates: list[dict],
    checkpoint: dict | None,
    focus: tuple[Finding, ...],
) -> tuple[list[tuple[str, Finding]], dict]:
    """Compute one batch and retain model decisions by source-line index.

    :param pages: extracted lines from the original, unchanged PDF.
    :param semantic: model available for this batch.
    :param templates: ordered snapshot of applicable historical templates.
    :param checkpoint: previous completed batch data, when resuming.
    :param focus: deterministic findings for prioritized model verification.
    :returns: accumulated candidates and a JSON-serializable checkpoint.
    """
    if checkpoint is None:
        state = {
            "candidates": [],
            "outcomes": {},
            "attempts": 0,
            "coverage": "nicht ausgeführt (kein Modell konfiguriert)",
            "warnings": [],
        }
    else:
        state = {**checkpoint, "outcomes": dict(checkpoint["outcomes"])}
        templates = [
            t for t in templates if state["outcomes"].get(t["rule"], ("deferred",))[0] == "deferred"
        ]
    pending, outcomes, used = review_model_patterns(
        pages, semantic, templates, resuming=checkpoint is not None
    )
    state["attempts"] += used
    state["outcomes"].update(outcomes)
    if checkpoint is None and semantic is not None:
        if used < semantic.max_requests:
            config = replace(semantic, max_requests=semantic.max_requests - used)
            general, state["warnings"], state["coverage"] = semantic_review(
                pages, config, focus=focus
            )
            pending.extend(("", finding) for finding in general)
        else:
            state["coverage"] = "allgemeine Prüfung zurückgestellt"

    indices = {id(line): index for page in pages for index, line in enumerate(page)}
    previous = [
        (
            pattern,
            Finding(
                extra[0] if extra else "semantic",
                tuple(
                    tuple(pages[page][index] for page, index in passage) for passage in references
                ),
                explanation,
                question,
                status,
                spelling=tuple(extra[1]) if extra and extra[1] else None,
            ),
        )
        for pattern, references, explanation, question, status, *extra in state["candidates"]
    ]
    state["candidates"] = state["candidates"] + [
        (
            pattern,
            [[(line.page, indices[id(line)]) for line in passage] for passage in finding.passages],
            finding.explanation,
            finding.question,
            finding.status,
            finding.kind,
            finding.spelling,
        )
        for pattern, finding in pending
    ]
    return previous + pending, state


def review_pdf(
    filename: str,
    pdf_bytes: bytes,
    output: Path,
    *,
    semantic: SemanticConfig | None = None,
    templates: list[dict] | None = None,
    checkpoint: dict | None = None,
) -> dict:
    """Create and verify the annotated PDF and contradiction log.

    :param filename: input name used to label the artifacts.
    :param pdf_bytes: complete PDF contents.
    :param output: path to a new run directory.
    :param semantic: optional semantic checker connection and comparison budget.
    :param templates: confirmed, prioritized model conditions for historical review.
    :param checkpoint: completed model batches for this original PDF.
    :returns: run status, artifact paths, structured findings and coverage warnings.
    :raises ValueError: if the input is not a readable, unencrypted PDF.
    :raises FileExistsError: if the output directory already exists.
    :raises RuntimeError: if the output fails verification.
    """
    try:
        document = pymupdf.open(stream=pdf_bytes)
    except (pymupdf.FileDataError, ValueError) as error:
        raise ValueError("Input must be a readable PDF.") from error

    with document:
        if not document.is_pdf or document.is_encrypted or document.needs_pass or not len(document):
            raise ValueError("Input must be a nonempty, unencrypted PDF.")
        pages, skipped = extract(document)
        findings = find_contradictions(pages) + find_scope_questions(pages)
        warnings = [f"PDF-Seite {page}: kein extrahierbarer Text (keine OCR)." for page in skipped]
        table_findings, table_coverage = table_prices(pages)
        findings.extend(table_findings)
        pending, state = _model_batch(pages, semantic, templates or [], checkpoint, tuple(findings))
        model_history = state["outcomes"]
        warnings.extend(state["warnings"])
        coverage = state["coverage"] + ". " + table_coverage
        if state["attempts"]:
            coverage += f"; {state['attempts']} historische Vergleiche versucht"
        if any(status in ("inconclusive", "deferred") for status, _ in model_history.values()):
            warnings.append("Historische Modellprüfung teilweise offen; siehe Regelstatus.")
        origins: dict[int, list[str]] = {}
        model_matches: set[int] = set()
        for pattern, candidate in pending:
            if candidate.spelling or candidate.kind == "calculation":
                findings.append(candidate)
                continue
            left, right = candidate.passages
            existing = next(
                (
                    finding
                    for finding in findings
                    if len(finding.passages) == 2
                    and (
                        (left[0] in finding.passages[0] and right[0] in finding.passages[1])
                        or (right[0] in finding.passages[0] and left[0] in finding.passages[1])
                    )
                ),
                None,
            )
            if existing is None:
                existing = candidate
                findings.append(candidate)
            elif not pattern and existing.kind != "semantic":
                model_matches.add(id(existing))
            if pattern:
                origins.setdefault(id(existing), []).append(pattern)
        details = []
        records = []
        expected: Counter[tuple[int, str, str, str]] = Counter()
        for number, finding in enumerate(findings, 1):
            identifier = f"BG-{number:03d}"
            assessment = (
                "Widerspruchskandidat" if finding.status == "conflict" else "Klärungsbedarf"
            )
            method = "Semantische Modellprüfung" if finding.kind == "semantic" else "Regelprüfung"
            if id(finding) in model_matches:
                method += " · Modellbefund an denselben Quellen"
            if finding.spelling:
                assessment = "Möglicher Schreibfehler"
                method = "Modellvorschlag mit lokalem Wortabgleich"
            if finding.kind == "calculation":
                assessment = "Rechenabweichung"
                method = "Modellformel mit lokaler Decimal-Prüfung"
            if finding.kind in ("table_price", "section_total", "hierarchy_total"):
                assessment = "Rechenabweichung"
            if id(finding) in origins:
                method += " · Historischer Modell-Treffer"
            category, impact = {
                "scope_reference": (
                    "Leistungsumfang",
                    "Zeichnungen für das falsche Bauteil könnten in die Kalkulation eingehen.",
                ),
                "aggregate_limit": (
                    "Materialanforderung",
                    "Die geforderte Körnung wirkt sich auf die Materialkalkulation aus.",
                ),
                "open_scope": (
                    "Unklare Leistungsbeschreibung",
                    "Der Aufwand für Material oder Ausführung bleibt offen.",
                ),
                "open_pricing": (
                    "Offene Vergütung",
                    "Erforderlicher Aufwand könnte im Angebot unberücksichtigt bleiben.",
                ),
                "spelling": (
                    "Rechtschreibung",
                    "Die Leistungsbeschreibung könnte missverständlich sein.",
                ),
                "table_price": ("Positionsbetrag", "Die Abweichung kann die Angebotssumme ändern."),
                "section_total": (
                    "Abschnittssumme",
                    "Die Abweichung kann die Angebotssumme ändern.",
                ),
                "hierarchy_total": (
                    "Summenhierarchie",
                    "Die Abweichung kann die Angebotssumme ändern.",
                ),
                "calculation": ("Positionsbetrag", "Die Abweichung kann die Angebotssumme ändern."),
            }.get(finding.kind, ("Widerspruch", "Siehe Begründung des Modellvorschlags."))
            records.append(
                {
                    "id": identifier,
                    "rule": finding.kind,
                    "history_rules": origins.get(id(finding), []),
                    "assessment": assessment,
                    "method": method,
                    "category": category,
                    "evidence": (
                        "Ausdrücklich offene Angabe belegt"
                        if len(finding.passages) == 1
                        else (
                            "Zwei Textstellen; Anwendbarkeit offen"
                            if finding.status != "conflict"
                            else "Zwei Textstellen belegt"
                        )
                    ),
                    "impact": impact,
                    "explanation": finding.explanation,
                    "question": finding.question,
                    "sources": [
                        {
                            "page": passage[0].page + 1,
                            "oz": passage[0].oz,
                            "reference": _reference(passage),
                            "excerpt": _excerpt(passage),
                        }
                        for passage in finding.passages
                    ],
                }
            )
            if finding.kind in ("table_price", "calculation"):
                records[-1]["evidence"] = "Menge, Preisbasis, Einheitspreis und Gesamtbetrag belegt"
            if finding.kind == "section_total":
                records[-1]["evidence"] = (
                    "Ausgewiesene Abschnittssumme und zugehörige Positionsbeträge"
                )
            if finding.kind == "hierarchy_total":
                records[-1]["evidence"] = "Ausgewiesene Summe und ausgewiesene Teilsummen"
            if finding.spelling:
                token, correction, start, end = finding.spelling
                records[-1].update(
                    original_word=token,
                    correction=correction,
                    span_start=start,
                    span_end=end,
                    evidence="Exaktes Originalwort und lokal bestätigter Korrekturvorschlag",
                )
            section = [
                f"## {identifier} · {assessment}",
                "",
                f"**Erkennung:** {method}",
                "",
                finding.explanation,
                "",
            ]
            for index, passage in enumerate(finding.passages):
                comment = f"{identifier} · {assessment}\n"
                if len(finding.passages) == 2:
                    other = finding.passages[1 - index]
                    comment += f"Gegenstelle: {_reference(other)}\n„{_excerpt(other)}“\n\n"
                comment += finding.explanation
                if len(finding.passages) == 1 and finding.question:
                    comment += f"\n\nBieterfrage: {finding.question}"
                page = passage[0].page
                geometry = passage
                if finding.spelling:
                    token, correction, _, _ = finding.spelling
                    comment += f"\n\nVorschlag: {token} → {correction}"
                    word = document[page].search_for(token, clip=passage[0].quad.rect, quads=True)
                    if len(word) == 1:
                        geometry = (replace(passage[0], quad=word[0]),)
                count = annotate(document[page], geometry, identifier, comment)
                for subtype in ("Highlight", "Text")[:count]:
                    expected[page, identifier, comment, subtype] += 1
                outcome = {
                    0: "Markierung nicht möglich (Seitengeometrie)",
                    1: "Markierung mit Kommentar im Kommentarbereich",
                    2: "Markierung mit Kommentarsymbol",
                }[count]
                if count == 0:
                    warnings.append(f"{identifier}, {_reference(passage)}: {outcome}.")
                section.extend(
                    [f"**{_reference(passage)}**", "", f"> {_excerpt(passage)}", "", outcome, ""]
                )
            if finding.question:
                section.extend([f"**Bieterfrage:** {finding.question}", ""])
            if finding.spelling:
                section.extend([f"**Vorschlag:** {token} → {correction}", ""])
            details.extend(section)

        stem = re.sub(r"[^\w.-]+", "_", Path(filename).stem).strip("._") or "review"
        pdf_name = f"{stem}.annotated.pdf"
        log_name = f"{stem}.contradictions.md"
        summary = [
            "# Widerspruchsprüfung des Leistungsverzeichnisses",
            "",
            f"**PDF-Seiten mit Text:** {len(pages) - len(skipped)}/{len(pages)}",
            f"**Kandidaten:** {len(findings)}",
            "**Prüfungen:** Zeichnungsverweise, Körnungsgrenzen für Schachtvierungen "
            f"und ausdrücklich offene Angaben. **Semantische Modellprüfung:** {coverage}.",
            "",
        ]
        if semantic is not None:
            summary.extend([f"**Modell:** {semantic.model}", ""])
        summary.extend(f"- {warning}" for warning in warnings)
        summary.append("")
        if not findings:
            summary.extend(["Die ausgeführten Prüfungen haben keine Kandidaten gefunden.", ""])

        if output.exists():
            raise FileExistsError(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=output.parent) as staging:
            artifacts = Path(staging) / "artifacts"
            artifacts.mkdir()
            pdf = artifacts / pdf_name
            document.save(pdf)
            with pymupdf.open(pdf) as reopened:
                actual: Counter[tuple[int, str, str, str]] = Counter()
                for page in reopened:
                    for annot in page.annots():
                        info = annot.info
                        key = page.number, info["subject"], info["content"], annot.type[1]
                        if key in expected:
                            actual[key] += 1
                            if annot.type[1] == "Highlight" and tuple(annot.colors["stroke"]) != (
                                1,
                                1,
                                0,
                            ):
                                raise RuntimeError("Exported highlight is not yellow.")
                if len(reopened) != len(document) or actual != expected:
                    raise RuntimeError("Exported PDF failed annotation verification.")
            (artifacts / log_name).write_text("\n".join(summary + details), encoding="utf-8")
            artifacts.rename(output)

    positions, position_count = pdf_positions(pages)
    return {
        "status": "partial" if warnings else "complete",
        "annotated_pdf": str(output / pdf_name),
        "findings_log": str(output / log_name),
        "candidates": len(findings),
        "page_count": len(pages),
        "text_pages": len(pages) - len(skipped),
        "rule_scope": rule_scope(pages),
        "attachment_properties": pdf_properties(pages),
        "attachment_positions": positions,
        "position_count": position_count,
        "findings": records,
        "model_history": model_history,
        **({"checkpoint": state} if templates else {}),
        "semantic_coverage": coverage,
        "warnings": warnings,
    }


def main() -> None:
    """Run the local PDF review tool and print a JSON artifact manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="input PDF")
    parser.add_argument("output", type=Path, help="new output directory")
    parser.add_argument("--endpoint", help="loopback Ollama or chat completions URL")
    parser.add_argument("--model", help="model ID exposed by the endpoint")
    parser.add_argument("--max-requests", type=int, default=24, help="semantic comparison budget")
    parser.add_argument("--timeout", type=float, default=90, help="seconds per model comparison")
    parser.add_argument(
        "--spelling", action="store_true", help="check German spelling with the model"
    )
    parser.add_argument("--lexicon", type=Path, help="local project terms, one per line")
    args = parser.parse_args()
    if bool(args.endpoint) != bool(args.model) or args.max_requests < 1 or not args.timeout > 0:
        parser.error("provide --endpoint and --model together and positive comparison limits")
    if (args.spelling or args.lexicon) and not args.endpoint:
        parser.error("spelling and lexicon require a configured local model")
    try:
        lexicon = load_lexicon(args.lexicon) if args.lexicon else frozenset()
        semantic = (
            SemanticConfig(
                args.endpoint,
                args.model,
                args.max_requests,
                args.timeout,
                spelling=args.spelling or bool(args.lexicon),
                lexicon=lexicon,
            )
            if args.endpoint
            else None
        )
        result = review_pdf(args.pdf.name, args.pdf.read_bytes(), args.output, semantic=semantic)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(2, json.dumps({"status": "error", "message": str(error)}) + "\n")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
