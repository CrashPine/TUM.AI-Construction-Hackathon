"""Exercise semantic evidence validation and PDF export without a model server."""

from pathlib import Path

import pymupdf
import pytest

from boqcheck import semantic
from boqcheck.pdf_extract import extract
from boqcheck.review_pdf import review_pdf

_CONFIG = semantic.SemanticConfig("http://127.0.0.1:18081/v1/chat/completions", "test")


def _pdf() -> bytes:
    """Return a two-clause PDF with conflicting requirements.

    :returns: synthetic source bytes.
    """
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "The main switch must remain ON during inspection.")
        page.insert_text((72, 102), "The main switch must remain OFF during inspection.")
        return document.tobytes()


def test_semantic_review_exports_grounded_model_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only accept quotations belonging to the referenced source lines.

    :param tmp_path: artifact directory parent.
    :param monkeypatch: fixture for replacing the inference call.
    """
    grounded = {
        "status": "conflict",
        "left_id": "L1",
        "right_id": "L2",
        "left_quote": "remain ON",
        "right_quote": "remain OFF",
        "explanation": "The same switch has incompatible required states during inspection.",
        "question": "What state is required?",
    }

    def model_response(config: semantic.SemanticConfig, payload: dict) -> list[dict]:
        """Return both grounded and hallucinated evidence records.

        :param config: requested model connection.
        :param payload: candidate source lines sent for analysis.
        :returns: simulated model records.
        """
        assert config == _CONFIG
        assert len(payload["left"]) == 2
        return [grounded, grounded | {"right_quote": "never open"}, grounded | {"right_id": "L9"}]

    monkeypatch.setattr(semantic, "_request", model_response)
    result = review_pdf("source.pdf", _pdf(), tmp_path / "review", semantic=_CONFIG)

    assert result["candidates"] == 1
    assert result["status"] == "partial"
    assert result["semantic_coverage"].startswith("1/1")
    assert any("verworfen: 2" in warning for warning in result["warnings"])
    log = Path(result["findings_log"]).read_text(encoding="utf-8")
    assert "Widerspruchskandidat" in log
    assert "**Erkennung:** Semantische Modellprüfung" in log
    assert "**Modell:** test" in log
    assert "remain ON" in log and "remain OFF" in log
    with pymupdf.open(result["annotated_pdf"]) as document:
        highlights = [
            annot.info["content"]
            for annot in document[0].annots(types=[pymupdf.PDF_ANNOT_HIGHLIGHT])
        ]
        assert len(highlights) == 2
        assert any("remain ON" in comment for comment in highlights)
        assert any("remain OFF" in comment for comment in highlights)


def test_semantic_failure_keeps_export(tmp_path: Path) -> None:
    """An invalid model endpoint leaves a partial result with explicit coverage.

    :param tmp_path: artifact directory parent.
    """
    config = semantic.SemanticConfig("http://192.0.2.1/v1/chat/completions", "test")
    result = review_pdf("source.pdf", _pdf(), tmp_path / "review", semantic=config)

    assert result["status"] == "partial"
    assert result["semantic_coverage"].startswith("0/1")
    assert Path(result["annotated_pdf"]).is_file()
    assert Path(result["findings_log"]).is_file()


def test_limited_budget_spans_the_document(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check the first and last windows and report exact page coverage.

    :param monkeypatch: fixture for replacing window boundaries and the inference call.
    """
    with pymupdf.open() as document:
        for number in range(5):
            page = document.new_page()
            if number != 2:
                page.insert_text((72, 72), f"First requirement on page {number + 1}")
                page.insert_text((72, 96), f"Second requirement on page {number + 1}")
        pages, _ = extract(document)

    windows = [["L1", "L2", "L3"], ["L4", "L5", "L6"], ["L7", "L8"]]
    monkeypatch.setattr(semantic, "_windows", lambda _: windows)
    calls = []

    def model_response(config: semantic.SemanticConfig, payload: dict) -> list:
        """Record the model requests and return no candidates.

        :param config: requested model configuration.
        :param payload: input lines sent for analysis.
        :returns: empty model findings.
        """
        assert config.model == "test"
        calls.append([line["id"] for line in payload["left"]])
        return []

    monkeypatch.setattr(semantic, "_request", model_response)
    config = semantic.SemanticConfig(_CONFIG.endpoint, "test", max_requests=2)
    findings, warnings, coverage = semantic.semantic_review(pages, config)
    assert calls == [windows[0], windows[-1]]
    assert not findings
    assert warnings
    assert coverage.startswith("2/6")
    assert "1 (alle Textzeilen übermittelt), 2 (teilweise abgedeckt)" in coverage
    assert "3 (ohne extrahierbaren Text), 4 (nicht abgedeckt)" in coverage
    assert "5 (alle Textzeilen übermittelt)" in coverage
