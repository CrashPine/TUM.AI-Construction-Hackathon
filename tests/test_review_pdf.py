"""Verify the PDF review tool on actual LVs and a synthetic rotated page."""

from pathlib import Path

import pymupdf
import pytest

from boqcheck.review_pdf import review_pdf

_DATA = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.mark.parametrize(
    ("filename", "pages", "references"),
    [
        ("LV_09_Porenbetondach.pdf", (0, 0), ("OZ 9.2.3", "OZ 9.2.4")),
        ("LV-Schachtbauwerk.pdf", (1, 4), ("Druckseite 53", "Druckseite 56")),
    ],
)
def test_review_exports_both_passages(
    tmp_path: Path, filename: str, pages: tuple[int, int], references: tuple[str, str]
) -> None:
    """Check reciprocal comments, yellow highlights and safe marker placement.

    :param tmp_path: isolated directory for generated artifacts.
    :param filename: corpus source filename.
    :param pages: expected physical pages of the two excerpts, zero-based.
    :param references: expected snippets in the two source references.
    """
    original = (_DATA / filename).read_bytes()
    result = review_pdf(filename, original, tmp_path / "run")
    assert result["status"] == "complete"
    assert result["candidates"] == 1
    log = Path(result["findings_log"]).read_text(encoding="utf-8")
    assert "Klärungsbedarf" in log
    assert "**Erkennung:** Regelprüfung" in log
    assert "Bieterfrage" in log
    with pymupdf.open(result["annotated_pdf"]) as reviewed, pymupdf.open(stream=original) as source:
        assert len(reviewed) == len(source)
        highlights = []
        markers = []
        for page in reviewed:
            assert page.get_text() == source[page.number].get_text()
            words = [pymupdf.Rect(word[:4]) for word in page.get_text("words")]
            for annotation in page.annots():
                if annotation.info["title"] != "PUManager":
                    continue
                if annotation.type[1] == "Highlight":
                    assert tuple(annotation.colors["stroke"]) == (1, 1, 0)
                    assert annotation.vertices
                    highlights.append((page.number, annotation.info["content"]))
                if annotation.type[1] == "Text":
                    markers.append(page.number)
                    assert not any(annotation.rect.intersects(word) for word in words)

    assert sorted(markers) == sorted(pages)
    assert sorted(page for page, _ in highlights) == sorted(pages)
    for reference in references:
        assert reference in log
        assert any(reference in comment for _, comment in highlights)


def test_empty_text_page_returns_partial_review(tmp_path: Path) -> None:
    """Report skipped pages and issue both artifacts even without findings.

    :param tmp_path: isolated directory for generated artifacts.
    """
    with pymupdf.open() as document:
        page = document.new_page()
        page.set_rotation(90)
        data = document.tobytes()
    result = review_pdf("blank.pdf", data, tmp_path / "run")
    assert result["status"] == "partial"
    assert result["candidates"] == 0
    assert result["warnings"]
    with pymupdf.open(result["annotated_pdf"]) as reviewed:
        assert reviewed[0].rotation == 90
        assert list(reviewed[0].annots()) == []


def test_invalid_input_does_not_publish(tmp_path: Path) -> None:
    """Reject an invalid PDF without leaving an output directory.

    :param tmp_path: isolated directory for generated artifacts.
    """
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="PDF"):
        review_pdf("bad.pdf", b"not a PDF", output)
    assert not output.exists()


def test_explicit_open_scope_and_pricing_are_annotated(tmp_path: Path) -> None:
    """Export evidence and German questions for open specification and pricing.

    :param tmp_path: isolated artifact directory.
    """
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "1.2.10. Schutzestrich")
        page.insert_text((72, 98), "Schutzestrich herstellen.")
        page.insert_text((72, 124), "Schichtdicke: nach Absprache")
        page.insert_text((72, 150), "Vergütung: noch offen")
        result = review_pdf("open-terms.pdf", document.tobytes(), tmp_path / "run")

    assert {finding["rule"] for finding in result["findings"]} == {"open_scope", "open_pricing"}
    for finding in result["findings"]:
        assert len(finding["sources"]) == 1 and "OZ 1.2.10" in finding["question"]
    with pymupdf.open(result["annotated_pdf"]) as reviewed:
        page = reviewed[0]
        marks = [
            annot.info["content"] for annot in page.annots(types=[pymupdf.PDF_ANNOT_HIGHLIGHT])
        ]
        assert len(marks) == 2
        assert all("Bieterfrage" in comment and "Gegenstelle" not in comment for comment in marks)


def test_scope_questions_use_adjacent_and_general_conditions(tmp_path: Path) -> None:
    """Suppress questions already answered in applicable source context.

    :param tmp_path: isolated artifact directory.
    """
    lines = (
        "Für die OZ 1.2.10: Lieferverantwortung: Auftragnehmer",
        "1.2.10. Schutzestrich",
        "Schutzestrich herstellen, Verankerungen liefern.",
        "Schichtdicke: nach Absprache",
        "Lieferverantwortung: noch offen",
        "Vergütung: offen",
        "Verankerungen sind im Einheitspreis enthalten.",
        "1.2.20. Schutzestrich",
        "Schichtdicke: 45 mm",
        "1.2.30. Geländer",
        "Geländer montieren, Schrauben und Dübel einschliesslich.",
    )
    with pymupdf.open() as document:
        page = document.new_page()
        for index, line in enumerate(lines):
            page.insert_text((72, 72 + index * 27), line)
        result = review_pdf("included-scope.pdf", document.tobytes(), tmp_path / "run")
    assert result["findings"] == []


def test_shaft_model_receives_both_sources_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Send both shaft citations within one request and report the matched finding.

    :param tmp_path: isolated artifact location.
    :param monkeypatch: substitute the embedding-free chat transport.
    """
    from boqcheck import semantic

    def reply(config: semantic.SemanticConfig, payload: dict) -> list:
        """Return a candidate using the two exact source quotes.

        :param config: local comparison budget.
        :param payload: emitted source groups.
        :returns: a grounded semantic response.
        """
        assert config.max_requests == 1
        left = next(line for line in payload["left"] if "8 mm" in line["text"])
        right = next(line for line in payload["left"] if "15 mm" in line["text"])
        assert (left["page"], right["page"]) == (2, 5)
        return [
            {
                "left_id": left["id"],
                "right_id": right["id"],
                "left_quote": "8 mm",
                "right_quote": "15 mm",
                "status": "needs_scope_check",
                "explanation": "Körnung klären.",
            }
        ]

    monkeypatch.setattr(semantic, "_request", reply)
    path = Path(__file__).resolve().parents[1] / "data/raw/LV-Schachtbauwerk.pdf"
    result = review_pdf(
        path.name,
        path.read_bytes(),
        tmp_path / "shaft",
        semantic=semantic.SemanticConfig("", "test", 1),
    )
    (finding,) = result["findings"]
    assert "Modellbefund an denselben Quellen" in finding["method"]


@pytest.mark.parametrize(
    ("other", "label", "expected"),
    [
        ("200 mm", "", True),
        ("10 cm", "", False),
        ("200 mm", "Wahlweise\n", False),
    ],
)
def test_explicit_specification_values(
    tmp_path: Path, other: str, label: str, expected: bool
) -> None:
    """Compare complete labelled values and leave declared alternatives alone.

    :param tmp_path: isolated artifact directory.
    :param other: second thickness.
    :param label: optional marker defining alternatives.
    :param expected: whether the two citations require review.
    """
    with pymupdf.open() as doc:
        doc.new_page().insert_text(
            (72, 72), f"01.01.0010. Dachplatte\nDicke: 100 mm\n{label}Dicke: {other}"
        )
        data = doc.tobytes()
    result = review_pdf("spec.pdf", data, tmp_path / "result")
    findings = result["findings"]
    assert bool(findings) is expected
    if expected:
        assert [source["excerpt"] for source in findings[0]["sources"]] == [
            "Dicke: 100 mm",
            f"Dicke: {other}",
        ]
