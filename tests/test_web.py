"""Verify the local web workflow with the real roof LV and no configured model."""

from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import pymupdf

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
    assert b"PDF pr" in _request(app, "/")[2]
    status, headers, _ = _request(
        app, f"/upload?name={_ROOF.name}", _ROOF.read_bytes(), "application/pdf"
    )
    assert status.startswith("303")
    run = headers["Location"]
    page = _request(app, run)[2].decode()
    assert "OZ 9.2.3" in page and "OZ 9.2.4" in page
    assert "Porenbetonfassade" in page and "Porenbeton-Dachplatten" in page
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
