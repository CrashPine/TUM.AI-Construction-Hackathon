"""Tests for the model comparison of LV positions with their DOCX blocks."""

from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from zipfile import ZipFile

import pymupdf
import pytest
from test_web import _ROOF, _request

from boqcheck import parse, semantic
from boqcheck.attachment_scope import compare_attachment
from boqcheck.attachment_semantic import review_attachment
from boqcheck.docx_context import read_context
from boqcheck.review_pdf import review_pdf
from boqcheck.web import make_app
from boqcheck.web_gaeb import review_legacy, review_x83

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


@pytest.mark.parametrize(
    ("name", "review"), [("StBALV23040.D86", review_legacy), ("[NUMMER_001]_leer.X83", review_x83)]
)
def test_gaeb_source_names_the_position(
    monkeypatch: pytest.MonkeyPatch, name: str, review: Callable[[str, bytes], dict]
) -> None:
    """Verify a grounded proposal on a real GAEB position cites the position, not a PDF page.

    :param monkeypatch: pytest fixture.
    :param name: real GAEB sample.
    :param review: web review for the sample format.
    """
    data = _ROOF.with_name(name).read_bytes()
    [(index, item)] = [
        (i, it) for i, it in enumerate(parse(name, data).items, 1) if it.oz == "03.01.0004"
    ]
    result = review(name, data)
    [line] = [
        line
        for position in result["attachment_positions"]
        if position["oz"] == item.oz
        for line in position["lines"]
        if line["text"] == "Dicke: 100 mm"
    ]
    entries = [
        {"id": "P1", "reference": "Absatz 1", "text": f"OZ 3.1.4 {item.short_text}"},
        {"id": "P2", "reference": "Absatz 2", "text": "Dicke: 120 mm"},
    ]
    record = {**_RECORD, "left_id": line["id"], "left_quote": "100 mm", "right_quote": "120 mm"}
    sent = _answer(monkeypatch, [record])
    attachment = {"name": "Synthetisch.docx", "entries": entries, "unread": 0}
    reviewed = review_attachment(compare_attachment(result, attachment), _CONFIG)
    [finding] = [f for f in reviewed["findings"] if f.get("rule") == "attachment_semantic"]
    assert finding["sources"][0] == {
        "oz": "03.01.0004",
        "position": index,
        "reference": f"Position {index} · OZ 03.01.0004 · {item.short_text}",
        "excerpt": "Dicke: 100 mm",
    }
    assert finding["sources"][1]["reference"] == "Synthetisch.docx · Absatz 2"
    assert len(sent) == 1 and all("page" not in line for line in sent[0]["left"])


def test_real_pdf_positions_reach_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Send each real LV position that a real DOCX heading names to the mocked model.

    16 headings of LV-Positionen.docx share OZ and Kurztext with Leistungsverzeichnis.pdf. The
    fixed answer cites one of these positions, so the other 15 requests reject it.

    :param tmp_path: artifact directory parent.
    :param monkeypatch: pytest fixture.
    """
    pdf = _ROOF.with_name("Leistungsverzeichnis.pdf")
    result = review_pdf(pdf.name, pdf.read_bytes(), tmp_path / "review")
    entries, unread = read_context(_ROOF.with_name("LV-Positionen.docx").read_bytes())
    [entry] = [e for e in entries if e["text"].startswith("1.1.20 ")]
    [position] = [p for p in result["attachment_positions"] if p["oz"] == "1.1.20"]
    line = position["lines"][1]
    record = {
        **_RECORD,
        "left_id": line["id"],
        "right_id": entry["id"],
        "left_quote": "vorhalten",
        "right_quote": "[Mt.]",
    }
    sent = _answer(monkeypatch, [record])
    attachment = {"name": "LV-Positionen.docx", "entries": entries, "unread": unread}
    reviewed = review_attachment(compare_attachment(result, attachment), _CONFIG)
    [finding] = [f for f in reviewed["findings"] if f.get("rule") == "attachment_semantic"]
    assert len(sent) == 16
    assert finding["sources"][0] == {
        "oz": "1.1.20",
        "page": line["page"],
        "reference": f"PDF-Seite {line['page']}, OZ 1.1.20 · Baustelleneinrichtung vorhalten",
        "excerpt": "Baustelleneinrichtung vorhalten",
    }
    assert finding["sources"][1]["reference"] == f"LV-Positionen.docx · {entry['reference']}"
    assert reviewed["attachment_review"]["warnings"] == [
        "Modellvorschläge ohne gültigen Quellenbeleg verworfen: 15."
    ]


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
