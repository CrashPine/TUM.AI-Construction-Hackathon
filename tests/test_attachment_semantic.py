"""Tests for the model comparison of LV positions with their DOCX blocks."""

from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from zipfile import ZipFile

import pymupdf
import pytest
from test_web import _request

from boqcheck import semantic
from boqcheck.attachment_semantic import review_attachment
from boqcheck.web import make_app

_CONFIG = semantic.SemanticConfig("http://127.0.0.1:18081/v1/chat/completions", "test")
_RECORD = {
    "left_id": "L1",
    "right_id": "P2",
    "left_quote": "10 mm",
    "right_quote": "20 mm",
    "status": "conflict",
    "explanation": "Die Dicke weicht ab.",
    "question": "Welche Dicke gilt?",
}


def _result(component: str = "Dachplatte", lv: str = "Dicke: 10 mm") -> dict:
    """Build a review with one LV position and one DOCX block.

    :param component: DOCX heading component.
    :param lv: second LV line.
    :returns: review after the deterministic comparison.
    """
    return {
        "findings": [],
        "attachment_positions": [
            {
                "oz": "01.01.0010",
                "component": "Dachplatte",
                "lines": [
                    {"id": "L0", "page": 1, "text": "01.01.0010. Dachplatte"},
                    {"id": "L1", "page": 1, "text": lv},
                ],
            }
        ],
        "attachment": {
            "name": "Details.docx",
            "entries": [
                {"id": "P1", "reference": "Absatz 1", "text": f"OZ 01.01.0010 {component}"},
                {"id": "P2", "reference": "Absatz 2", "text": "Dicke: 20 mm"},
            ],
        },
    }


def _answer(monkeypatch: pytest.MonkeyPatch, records: list | Exception) -> list[dict]:
    """Replace the model with a fixed answer and record the payloads.

    :param monkeypatch: pytest fixture.
    :param records: answer, or an exception to raise.
    :returns: payloads sent to the model.
    """
    sent = []

    def fake(config: semantic.SemanticConfig, payload: dict) -> list:
        """Return the fixed answer.

        :param config: ignored model settings.
        :param payload: request content.
        :returns: the fixed records.
        :raises records: the configured failure.
        """
        sent.append(payload)
        if isinstance(records, Exception):
            raise records
        return records

    monkeypatch.setattr(semantic, "_request", fake)
    return sent


def test_grounded_conflict_cites_both_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a valid proposal becomes one finding with a PDF and a DOCX source.

    :param monkeypatch: pytest fixture.
    """
    sent = _answer(monkeypatch, [_RECORD])
    reviewed = review_attachment(_result(), _CONFIG)
    [finding] = reviewed["findings"]
    assert [entry["id"] for entry in sent[0]["right"]] == ["P1", "P2"]
    assert finding["assessment"] == "Widerspruch zwischen LV und Anlage"
    assert finding["sources"][0]["excerpt"] == "Dicke: 10 mm"
    assert finding["sources"][1]["reference"] == "Details.docx · Absatz 2"
    assert "1 Vorschläge mit Quellenbeleg" in reviewed["attachment_review"]["summary"]


def test_other_component_is_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify a DOCX block for another component causes no request.

    :param monkeypatch: pytest fixture.
    """
    sent = _answer(monkeypatch, [_RECORD])
    reviewed = review_attachment(_result(component="Fassade"), _CONFIG)
    assert not sent and not reviewed["findings"]
    assert "keine Position" in reviewed["attachment_review"]["summary"]


def test_alternative_wording_caps_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify template alternatives turn a conflict into a scope check.

    :param monkeypatch: pytest fixture.
    """
    _answer(monkeypatch, [{**_RECORD, "left_quote": "10 mm"}])
    reviewed = review_attachment(_result(lv="Dicke: 10 mm oder gleichwertig"), _CONFIG)
    assert reviewed["findings"][0]["assessment"] == "Anwendbarkeit zwischen LV und Anlage prüfen"


@pytest.mark.parametrize(
    "change",
    [{"left_id": "P2"}, {"right_id": "L1"}, {"right_quote": "30 mm"}, {"status": "maybe"}],
)
def test_ungrounded_proposals_are_rejected(monkeypatch: pytest.MonkeyPatch, change: dict) -> None:
    """Verify wrong IDs, invented quotes and unknown statuses are dropped and counted.

    :param monkeypatch: pytest fixture.
    :param change: field that breaks the grounding.
    """
    _answer(monkeypatch, [{**_RECORD, **change}])
    reviewed = review_attachment(_result(), _CONFIG)
    assert not reviewed["findings"]
    assert reviewed["attachment_review"]["warnings"] == [
        "Modellvorschläge ohne gültigen Quellenbeleg verworfen: 1."
    ]


@pytest.mark.parametrize(
    ("answer", "text"),
    [
        ([], "kein Nachweis"),
        (URLError("down"), "ab Position 1 nicht verfügbar"),
    ],
)
def test_empty_or_failed_model_is_reported(
    monkeypatch: pytest.MonkeyPatch, answer: list | Exception, text: str
) -> None:
    """Verify abstention and endpoint failure are visible, not silent.

    :param monkeypatch: pytest fixture.
    :param answer: model answer or failure.
    :param text: expected message part.
    """
    _answer(monkeypatch, answer)
    review = review_attachment(_result(), _CONFIG)["attachment_review"]
    assert text in review["summary"] + " ".join(review["warnings"])


def test_without_model_nothing_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify no request is made when no model was selected.

    :param monkeypatch: pytest fixture.
    """
    sent = _answer(monkeypatch, [_RECORD])
    review = review_attachment(_result(), None)["attachment_review"]
    assert not sent and "kein Modell gewählt" in review["summary"]


def test_web_attachment_uses_selected_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify upload, attachment and report carry the model finding and its sources.

    :param tmp_path: isolated review storage.
    :param monkeypatch: pytest fixture.
    """
    _answer(monkeypatch, [])
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((50, 50), "01.01.0010. Dachplatte\nDicke: 10 mm")
        source = pdf.tobytes()
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>OZ 01.01.0010 Dachplatte</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>Dicke: 20 mm</w:t></w:r></w:p></w:body></w:document>",
        )
    app = make_app(tmp_path, semantic=_CONFIG)
    run = _request(app, "/upload?name=LV.pdf&semantic=1", source, "application/pdf")[1]["Location"]
    sent = _answer(monkeypatch, [_RECORD])
    _request(
        app, run + "/attachment?name=Details.docx", data.getvalue(), "application/octet-stream"
    )
    report = _request(app, run + "/report?download=1")[2].decode()
    assert len(sent) == 1
    assert "Widerspruch zwischen LV und Anlage" in report and "Welche Dicke gilt?" in report
    assert "1/1 zugeordnete Positionen" in report
