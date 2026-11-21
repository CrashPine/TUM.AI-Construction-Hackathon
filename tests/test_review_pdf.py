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
                if annotation.info["title"] != "BidGuard AI":
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
