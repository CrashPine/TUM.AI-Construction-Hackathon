"""Verify PDF and GAEB uploads through the local web workflow without a model."""

from collections.abc import Callable
from contextlib import closing
from io import BytesIO
from pathlib import Path
from sqlite3 import connect
from urllib.error import URLError
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import pymupdf
import pytest

from boqcheck import semantic
from boqcheck.history import initialize, promote, replay
from boqcheck.web import make_app

_ROOF = Path(__file__).resolve().parents[1] / "data" / "raw" / "LV_09_Porenbetondach.pdf"


def _request(
    app: Callable, path: str, data: bytes | None = None, content_type: str = ""
) -> tuple[str, dict[str, str], bytes]:
    """Send a request to the WSGI app using an in-memory body.

    :param app: WSGI application.
    :param path: request path with optional query string.
    :param data: POST body or None for GET.
    :param content_type: request body media type.
    :returns: response status, headers and body.
    """
    environ: dict = {}
    setup_testing_defaults(environ)
    route, _, query = path.partition("?")
    environ.update(PATH_INFO=route, QUERY_STRING=query)
    if data is not None:
        environ.update(
            REQUEST_METHOD="POST", CONTENT_LENGTH=str(len(data)), CONTENT_TYPE=content_type
        )
        environ["wsgi.input"] = BytesIO(data)
    response: list = []
    body = b"".join(app(environ, lambda status, headers: response.extend((status, dict(headers)))))
    return response[0], response[1], body


def test_upload_review_and_report(tmp_path: Path) -> None:
    """Upload the roof, edit its question and verify both exports.

    :param tmp_path: isolated application artifact directory.
    """
    app = make_app(tmp_path)
    home = _request(app, "/")[2]
    assert b"PDF oder GAEB X83" in home
    status, headers, _ = _request(
        app, f"/upload?name={_ROOF.name}", _ROOF.read_bytes(), "application/pdf"
    )
    assert status.startswith("303")
    run = headers["Location"]
    page = _request(app, run)[2].decode()
    assert "OZ 9.2.3" in page and "OZ 9.2.4" in page
    assert "Porenbetonfassade" in page and "Porenbeton-Dachplatten" in page
    assert "Kategorie: Leistungsumfang" in page and "Beleglage:" in page
    assert page.count("#page=1") == 2 and "kein Modell konfiguriert" in page

    question = "Sind Dach <und> Fassade im Preis enthalten?"
    for state in ("confirmed", "dismissed"):
        data = urlencode({"status-BG-001": state, "question-BG-001": question}).encode()
        assert _request(app, run, data, "application/x-www-form-urlencoded")[0].startswith("303")
        status, headers, report = _request(app, run + "/report?download=1")
        assert status.startswith("200") and "attachment" in headers["Content-Disposition"]
        if state == "confirmed":
            assert b"Sind Dach &lt;und&gt; Fassade" in report
            assert "Bestätigt" in report.decode()
        else:
            assert b"BG-001" not in report and b"Sind Dach" not in report
            assert b"Sind Dach &lt;und&gt; Fassade" in _request(app, run)[2]
    pdf = _request(app, run + "/pdf")[2]
    with pymupdf.open(stream=pdf) as document:
        page_one = document[0]
        assert sum(a.type[1] == "Highlight" for a in page_one.annots()) == 2
    assert b"BG-001" in _request(app, run + "/log")[2]


def test_invalid_upload_returns_error(tmp_path: Path) -> None:
    """Surface an invalid PDF without publishing review artifacts.

    :param tmp_path: isolated application artifact directory.
    """
    app = make_app(tmp_path)
    assert _request(app, "/upload", b"invalid", "application/pdf")[0].startswith("400")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("name", "version", "count", "oz"),
    [
        ("501-24-01_GAEB-XML_sas.x83", "3.1", 296, "01.01.0001"),
        ("GAEB-[PROJEKT_004].X83", "3.2", 50, "01.0001"),
    ],
)
def test_real_x83_upload(tmp_path: Path, name: str, version: str, count: int, oz: str) -> None:
    """Import real unpriced X83 files via the browser endpoint.

    :param tmp_path: isolated application artifact directory.
    :param name: fixture filename.
    :param version: GAEB version declared by the fixture.
    :param count: expected number of imported positions.
    :param oz: representative normalized position number.
    """
    app = make_app(tmp_path)
    data = _ROOF.with_name(name).read_bytes()
    status, headers, _ = _request(
        app, f"/upload?{urlencode({'name': name})}", data, "application/xml"
    )
    assert status.startswith("303")
    run = headers["Location"]
    page = _request(app, run)[2].decode()
    assert f"GAEB {version} · Phase 83 · {count} Positionen" in page
    assert page.count('<tr id="position-') == count
    assert oz in page and "Langtext" in page
    assert "Keine Preisangaben. Für X83 ist das zulässig." in page
    assert "Keine aktiven Befunde." in page and "Annotiertes PDF" not in page
    assert _request(app, run + "/pdf")[0].startswith("404")
    assert "0 Gesamtbeträge geprüft" in _request(app, run + "/report")[2].decode()


def test_x83_finding_links_to_both_positions(tmp_path: Path) -> None:
    """Link a duplicate OZ finding to both source rows and include it in the report.

    :param tmp_path: isolated application artifact directory.
    """
    data = b"""<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA83/3.2">
    <Award><DP>83</DP><BoQ><BoQInfo>
    <BoQBkdn><Type>Item</Type><Length>4</Length></BoQBkdn>
    </BoQInfo><BoQBody><Itemlist>
    <Item RNoPart="1"><Qty>1</Qty><QU>m</QU></Item>
    <Item RNoPart="0001"><Qty>2</Qty><QU>m</QU></Item>
    </Itemlist></BoQBody></BoQ></Award></GAEB>"""
    app = make_app(tmp_path)
    status, headers, _ = _request(app, "/upload?name=items.x83", data, "application/xml")
    assert status.startswith("303")
    run = headers["Location"]
    page = _request(app, run)[2].decode()
    assert "Doppelte OZ" in page
    assert "Kategorie: LV-Struktur" in page and "Auswirkung:" in page
    assert 'href="#position-1"' in page and 'href="#position-2"' in page
    assert "Doppelte OZ" in _request(app, run + "/report")[2].decode()


def test_only_confirmed_cases_are_promoted_and_replayed_after_restart(tmp_path: Path) -> None:
    """Persist source-backed history and keep retries idempotent across runs.

    :param tmp_path: isolated database and artifact directory.
    """
    history = tmp_path / "history.sqlite3"
    app = make_app(tmp_path, history_db=history)
    upload = f"/upload?name={_ROOF.name}"
    body = _ROOF.read_bytes()
    run = _request(app, upload, body, "application/pdf")[1]["Location"]
    assert "Keine historischen Regeln gespeichert" in _request(app, run)[2].decode()
    form = {
        "status-BG-001": "open",
        "question-BG-001": "Dach oder Fassade?",
        "promote-BG-001": "on",
        "reviewer": "QA",
        "trade": "Dach",
        "severity": "high",
    }
    form_type = "application/x-www-form-urlencoded"
    assert _request(app, run, urlencode(form).encode(), form_type)[0].startswith("400")
    with closing(connect(history)) as db:
        assert db.execute("SELECT COUNT(*) FROM confirmed_cases").fetchone() == (0,)
    form["status-BG-001"] = "confirmed"
    for _ in range(2):
        assert _request(app, run, urlencode(form).encode(), form_type)[0].startswith("303")

    restarted = make_app(tmp_path, history_db=history)
    second = _request(restarted, upload, body, "application/pdf")[1]["Location"]
    page = _request(restarted, second)[2].decode()
    assert "Historischer Regel-Treffer" in page and "Zeichnungsumfang · Geprüft" in page
    assert _request(restarted, second, urlencode(form).encode(), form_type)[0].startswith("303")
    with closing(connect(history)) as db:
        assert db.execute("SELECT COUNT(*) FROM patterns").fetchone() == (1,)
        (case,) = db.execute("SELECT reviewer, trade, severity, evidence FROM confirmed_cases")
        assert case[:3] == ("QA", "Dach", 3)
        assert "9.2.3" in case[3] and "9.2.4" in case[3]

    matching_upload = upload + "&" + urlencode({"trade": " DACH  "})
    matching = _request(restarted, matching_upload, body, "application/pdf")[1]["Location"]
    assert "Historischer Regel-Treffer" in _request(restarted, matching)[2].decode()

    different_upload = upload + "&trade=Elektro"
    different = _request(restarted, different_upload, body, "application/pdf")[1]["Location"]
    page = _request(restarted, different)[2].decode()
    assert "Nicht anwendbar (anderes Gewerk)" in page
    assert "Historischer Regel-Treffer" not in page
    assert "OZ 9.2.3" in page and "OZ 9.2.4" in page

    with pymupdf.open() as unrelated:
        unrelated.new_page().insert_text((72, 72), "Fassadenfarbe der Nebenanlage")
        clean = _request(restarted, matching_upload, unrelated.tobytes(), "application/pdf")
    page = _request(restarted, clean[1]["Location"])[2].decode()
    assert "Nicht anwendbar (keine passenden Positionsmerkmale)" in page


def test_history_priority_and_coverage(tmp_path: Path) -> None:
    """Prioritize severity first and report non-PDF or unreadable coverage.

    :param tmp_path: isolated database directory.
    """
    db = tmp_path / "history.sqlite3"
    initialize(db)
    for rule, priority in (("scope_reference", 1), ("aggregate_limit", 3)):
        finding = {"rule": rule, "sources": [{"reference": "PDF-Seite 1"}]}
        promote(db, "synthetic.pdf", rule, "QA", "Test", priority, [(finding, "")])
    coverage = replay(db, {"findings": [], "text_pages": 0, "page_count": 1})
    assert [entry["rule"] for entry in coverage] == ["aggregate_limit", "scope_reference"]
    assert {entry["status"] for entry in coverage} == {"inconclusive"}
    assert {entry["reason"] for entry in coverage} == {"partial_text"}
    assert {entry["status"] for entry in replay(db, {"findings": [], "gaeb": {}})} == {
        "inapplicable"
    }


def test_optional_web_model_keeps_roof_rule_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only call the model for opted-in uploads and preserve the rule on a network error.

    :param tmp_path: isolated artifact directory.
    :param monkeypatch: fixture for replacing the inference transport.
    """
    config = semantic.SemanticConfig("http://127.0.0.1:44445/api/chat", "bonsai-2:27b")
    calls = []

    def unavailable(selected: semantic.SemanticConfig, payload: dict) -> list:
        """Record an attempted comparison and simulate an unavailable local model.

        :param selected: requested model configuration.
        :param payload: source passages that would go to the model.
        :returns: no result, because the local model is unavailable.
        :raises URLError: always, to exercise web fallback.
        """
        assert payload["left"]
        calls.append(selected)
        raise URLError("offline")

    monkeypatch.setattr(semantic, "_request", unavailable)
    app = make_app(tmp_path, semantic=config)
    assert b'id="semantic"' in _request(app, "/")[2]
    upload = f"/upload?name={_ROOF.name}"
    data = _ROOF.read_bytes()
    _request(app, upload, data, "application/pdf")
    assert not calls
    status, headers, _ = _request(app, upload + "&semantic=1", data, "application/pdf")
    assert status.startswith("303") and calls == [config]
    run = headers["Location"]
    for path in (run, run + "/report"):
        page = _request(app, path)[2].decode()
        assert "Lokales Modell: bonsai-2:27b" in page and "nicht verfügbar" in page
        assert "OZ 9.2.3" in page and "OZ 9.2.4" in page
    assert _request(app, run + "/pdf")[2].startswith(b"%PDF")


def test_model_pattern_is_promoted_and_grounded_in_a_new_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replay a confirmed model pattern on independent source pages.

    :param tmp_path: isolated database and PDF artifacts directory.
    :param monkeypatch: fixture for replacing model inference.
    """
    db_path = tmp_path / "history.sqlite3"
    config = semantic.SemanticConfig("http://127.0.0.1:44445/api/chat", "test", max_requests=1)
    condition = "During inspection the same valve cannot be both open and closed."
    prompts = []

    def infer(selected: semantic.SemanticConfig, payload: dict) -> list[dict]:
        """Simulate source-backed inference and record only the current clauses.

        :param selected: configured test model.
        :param payload: selected current-document excerpts and optional condition.
        :returns: one validated-shape model proposal.
        """
        assert selected.model == "test"
        clauses = [line["text"] for line in payload["left"]]
        prompts.append((payload.get("historical_condition"), clauses))
        left, right = payload["left"]
        return [
            {
                "left_id": left["id"],
                "right_id": right["id"],
                "left_quote": "remain open",
                "right_quote": "remain closed",
                "status": "conflict",
                "explanation": "The same valve has incompatible inspection requirements.",
            }
        ]

    monkeypatch.setattr(semantic, "_request", infer)
    app = make_app(tmp_path, history_db=db_path, semantic=config)
    documents = []
    for valve in ("Valve A", "Valve B"):
        with pymupdf.open() as source:
            for state in ("open", "closed"):
                source.new_page().insert_text(
                    (72, 72), f"{valve} must remain {state} during inspection."
                )
            documents.append(source.tobytes())
    first, second = documents
    initial = _request(app, "/upload?name=first.pdf&semantic=1", first, "application/pdf")
    run = initial[1]["Location"]
    form = {
        "status-BG-001": "confirmed",
        "promote-BG-001": "on",
        "condition-BG-001": condition,
        "terms-BG-001": "Inspection, Valve",
        "reviewer": "QA",
    }
    for terms in ("Inspection, Valve", "valve, inspection, valve"):
        form["terms-BG-001"] = terms
        response = _request(app, run, urlencode(form).encode(), "application/x-www-form-urlencoded")
        assert response[0].startswith("303")
    with closing(connect(db_path)) as database:
        assert database.execute("SELECT COUNT(*) FROM semantic_patterns").fetchone() == (1,)
        assert database.execute("SELECT COUNT(*) FROM confirmed_cases").fetchone() == (1,)
    form["condition-BG-001"] = "The valve inspection requirements specify opposite states."
    form["severity"] = "low"
    response = _request(app, run, urlencode(form).encode(), "application/x-www-form-urlencoded")
    assert response[0].startswith("303")

    restarted = make_app(tmp_path, history_db=db_path, semantic=config)
    offline = _request(restarted, "/upload?name=second.pdf", second, "application/pdf")
    assert (
        "Modell für diesen Lauf nicht aktiviert"
        in _request(restarted, offline[1]["Location"])[2].decode()
    )
    assert len(prompts) == 1
    reviewed = _request(restarted, "/upload?name=second.pdf&semantic=1", second, "application/pdf")
    result = reviewed[1]["Location"]
    assert prompts[-1][0] == condition and len(prompts) == 2
    assert all("Valve B" in clause for clause in prompts[-1][1])
    report = _request(restarted, result + "/report")[2].decode()
    assert "Historischer Modell-Treffer" in report and "Valve B" in report
    assert "Zurückgestellt (Vergleichsbudget ausgeschöpft)" in report
    assert "Valve A" not in report
    with pymupdf.open(stream=_request(restarted, result + "/pdf")[2]) as output:
        assert [page.first_annot.type[1] for page in output] == ["Highlight", "Highlight"]
