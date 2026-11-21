"""Review an LV PDF and publish its annotated copy and separate findings log."""

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

from .contradictions import find_contradictions
from .pdf_annotate import annotate
from .pdf_extract import Line, extract
from .semantic import SemanticConfig, semantic_review


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


def review_pdf(
    filename: str, pdf_bytes: bytes, output: Path, *, semantic: SemanticConfig | None = None
) -> dict:
    """Create and verify the annotated PDF and contradiction log.

    :param filename: input name used to label the artifacts.
    :param pdf_bytes: complete PDF contents.
    :param output: path to a new run directory.
    :param semantic: optional semantic checker connection and comparison budget.
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
        findings = find_contradictions(pages)
        warnings = [f"PDF-Seite {page}: kein extrahierbarer Text (keine OCR)." for page in skipped]
        coverage = "nicht ausgeführt (kein Modell konfiguriert)"
        if semantic is not None:
            candidates, semantic_warnings, coverage = semantic_review(pages, semantic)
            warnings.extend(semantic_warnings)
            for candidate in candidates:
                left, right = candidate.passages
                if not any(
                    left[0] in a and right[0] in b or right[0] in a and left[0] in b
                    for a, b in (finding.passages for finding in findings)
                ):
                    findings.append(candidate)
        details = []
        records = []
        expected: Counter[tuple[int, str, str, str]] = Counter()
        for number, finding in enumerate(findings, 1):
            identifier = f"BG-{number:03d}"
            assessment = (
                "Widerspruchskandidat" if finding.status == "conflict" else "Klärungsbedarf"
            )
            method = "Semantische Modellprüfung" if finding.kind == "semantic" else "Regelprüfung"
            category, impact = {
                "scope_reference": (
                    "Leistungsumfang",
                    "Zeichnungen für das falsche Bauteil könnten in die Kalkulation eingehen.",
                ),
                "aggregate_limit": (
                    "Materialanforderung",
                    "Die geforderte Körnung wirkt sich auf die Materialkalkulation aus.",
                ),
            }.get(finding.kind, ("Widerspruch", "Siehe Begründung des Modellvorschlags."))
            records.append(
                {
                    "id": identifier,
                    "assessment": assessment,
                    "method": method,
                    "category": category,
                    "evidence": "Zwei Textstellen; Anwendbarkeit offen"
                    if finding.status != "conflict"
                    else "Zwei Textstellen belegt",
                    "impact": impact,
                    "explanation": finding.explanation,
                    "question": finding.question,
                    "sources": [
                        {
                            "page": passage[0].page + 1,
                            "reference": _reference(passage),
                            "excerpt": _excerpt(passage),
                        }
                        for passage in finding.passages
                    ],
                }
            )
            section = [
                f"## {identifier} · {assessment}",
                "",
                f"**Erkennung:** {method}",
                "",
                finding.explanation,
                "",
            ]
            for passage, other in (finding.passages, finding.passages[::-1]):
                comment = (
                    f"{identifier} · {assessment}\n"
                    f"Gegenstelle: {_reference(other)}\n"
                    f"„{_excerpt(other)}“\n\n{finding.explanation}"
                )
                page = passage[0].page
                count = annotate(document[page], passage, identifier, comment)
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
            details.extend(section)

        stem = re.sub(r"[^\w.-]+", "_", Path(filename).stem).strip("._") or "review"
        pdf_name = f"{stem}.annotated.pdf"
        log_name = f"{stem}.contradictions.md"
        summary = [
            "# Widerspruchsprüfung des Leistungsverzeichnisses",
            "",
            f"**PDF-Seiten mit Text:** {len(pages) - len(skipped)}/{len(pages)}",
            f"**Kandidaten:** {len(findings)}",
            "**Prüfungen:** Verweise in Zeichnungspositionen und Körnungsgrenzen "
            f"für Schachtvierungen. **Semantische Modellprüfung:** {coverage}.",
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

    return {
        "status": "partial" if warnings else "complete",
        "annotated_pdf": str(output / pdf_name),
        "findings_log": str(output / log_name),
        "candidates": len(findings),
        "findings": records,
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
    args = parser.parse_args()
    if bool(args.endpoint) != bool(args.model) or args.max_requests < 1 or not args.timeout > 0:
        parser.error("provide --endpoint and --model together and positive comparison limits")
    semantic = (
        SemanticConfig(args.endpoint, args.model, args.max_requests, args.timeout)
        if args.endpoint
        else None
    )
    try:
        result = review_pdf(args.pdf.name, args.pdf.read_bytes(), args.output, semantic=semantic)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(2, json.dumps({"status": "error", "message": str(error)}) + "\n")
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
