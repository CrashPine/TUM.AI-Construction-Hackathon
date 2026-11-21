"""Serve local PDF and X83 uploads, review state and printable reports."""

import argparse
import re
import sqlite3
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs
from uuid import uuid4
from wsgiref.simple_server import make_server

from .history import RULES, SEVERITIES, initialize, promote, replay
from .review_pdf import review_pdf
from .semantic import SemanticConfig
from .web_gaeb import review_x83
from .web_views import STATUSES, review_view, upload_view

_RUN = re.compile(r"/review/([a-f0-9]{32})(?:/(pdf|log|report))?")
_MAX_UPLOAD = 32 * 1024 * 1024


def _read_body(env: dict, limit: int, *, media_type: str) -> bytes:
    """Read a bounded request body.

    :param env: WSGI request environment.
    :param limit: maximum permitted body length in bytes.
    :param media_type: expected media type.
    :returns: request body.
    :raises ValueError: if the body length or media type is invalid.
    """
    length = int(env.get("CONTENT_LENGTH") or 0)
    if env.get("CONTENT_TYPE", "").split(";", 1)[0] != media_type:
        raise ValueError("Ungültiges Dateiformat oder Formular.")
    if not 0 < length <= limit:
        raise ValueError("Ungültige Uploadgröße.")
    return env["wsgi.input"].read(length)


def _update(
    result: dict, fields: dict[str, list[str]], history_db: Path | None, source: str
) -> None:
    """Validate a complete review form before updating the session.

    :param result: existing review result.
    :param fields: submitted form fields.
    :param history_db: configured history database, if enabled.
    :param source: original upload filename.
    :raises ValueError: if a status or question is invalid.
    """
    changes = []
    cases = []
    for finding in result["findings"]:
        identifier = finding["id"]
        status = fields.get(f"status-{identifier}", [""])[0]
        question = fields.get(f"question-{identifier}", [""])[0]
        if status not in STATUSES or len(question) > 2000:
            raise ValueError("Ungültige Prüfdaten.")
        changes.append((finding, status, question))
        if f"promote-{identifier}" in fields:
            if history_db is None or status != "confirmed" or finding.get("rule") not in RULES:
                raise ValueError("Nur bestätigte Befunde mit wiederverwendbarer Regel speichern.")
            cases.append((finding, question))
    if cases:
        reviewer = fields.get("reviewer", [""])[0].strip()
        trade = fields.get("trade", [""])[0].strip()
        severity = SEVERITIES.get(fields.get("severity", ["medium"])[0])
        if not reviewer or len(reviewer) > 120 or len(trade) > 120 or severity is None:
            raise ValueError("Bitte Prüfer und gültige Priorität für die Historie angeben.")
        promote(history_db, source, result["document_hash"], reviewer, trade, severity, cases)
    for finding, status, question in changes:
        finding.update(review_status=status, question=question)


def _analyse(env: dict, name: str, output: Path, semantic: SemanticConfig | None) -> dict:
    """Dispatch the upload to its analyzer using the original filename.

    :param env: WSGI request environment.
    :param name: uploaded filename.
    :param output: path for PDF output files.
    :param semantic: optional model configuration for this upload.
    :returns: structured review result.
    :raises ValueError: if the suffix is unsupported.
    """
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        data = _read_body(env, _MAX_UPLOAD, media_type="application/pdf")
        result = review_pdf(name, data, output, semantic=semantic)
        if semantic is not None:
            result["semantic_model"] = semantic.model
        result["document_hash"] = sha256(data).hexdigest()
        return result
    if suffix == ".x83":
        return review_x83(name, _read_body(env, _MAX_UPLOAD, media_type="application/xml"))
    raise ValueError("Unterstützt werden PDF und GAEB X83.")


def make_app(
    directory: Path, *, history_db: Path | None = None, semantic: SemanticConfig | None = None
) -> Callable:
    """Build the single-process WSGI application.

    :param directory: temporary root for generated artifacts.
    :param history_db: SQLite database that persists beyond the server lifetime.
    :param semantic: optional local model available for PDF uploads.
    :returns: WSGI application with per-run in-memory state.
    """
    runs: dict[str, tuple[str, dict]] = {}
    if history_db is not None:
        initialize(history_db)

    def app(env: dict, start_response: Callable) -> list[bytes]:
        """Dispatch one local HTTP request.

        :param env: WSGI request environment.
        :param start_response: WSGI response callback.
        :returns: encoded response body.
        """
        method = env["REQUEST_METHOD"]
        path = env["PATH_INFO"]
        query = parse_qs(env.get("QUERY_STRING", ""))
        content_type = "text/html; charset=utf-8"
        status = "200 OK"
        headers = [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")]
        body: str | bytes = ""

        try:
            if method == "GET" and path == "/":
                body = upload_view(
                    semantic.model if semantic else None, history=history_db is not None
                )
            elif method == "POST" and path == "/upload":
                name = query.get("name", ["upload.pdf"])[0][:200]
                identifier = uuid4().hex
                selected = semantic if query.get("semantic") == ["1"] else None
                result = _analyse(env, name, directory / identifier, selected)
                if history_db is not None:
                    trade = query.get("trade", [""])[0].strip()[:120]
                    result["history_trade"] = trade
                    result["history"] = replay(history_db, result, trade=trade)
                    matched = {
                        identifier
                        for pattern in result["history"]
                        for identifier in pattern["matches"]
                    }
                    for finding in result["findings"]:
                        finding["history_match"] = finding["id"] in matched
                for finding in result["findings"]:
                    finding["review_status"] = "open"
                runs[identifier] = (name, result)
                status = "303 See Other"
                headers.append(("Location", f"/review/{identifier}"))
            elif (match := _RUN.fullmatch(path)) and match[1] in runs:
                name, result = runs[match[1]]
                subpage = match[2]
                base = f"/review/{match[1]}"
                if method == "POST" and subpage is None:
                    data = _read_body(
                        env, 512 * 1024, media_type="application/x-www-form-urlencoded"
                    )
                    fields = parse_qs(data.decode("utf-8"), keep_blank_values=True)
                    _update(result, fields, history_db, name)
                    status = "303 See Other"
                    headers.append(("Location", base))
                elif method == "GET" and subpage in ("pdf", "log"):
                    if "annotated_pdf" not in result:
                        status, body = "404 Not Found", "Datei nicht gefunden."
                    elif subpage == "pdf":
                        content_type = "application/pdf"
                        body = Path(result["annotated_pdf"]).read_bytes()
                        headers.append(("Content-Disposition", 'inline; filename="annotated.pdf"'))
                    else:
                        content_type = "text/markdown; charset=utf-8"
                        body = Path(result["findings_log"]).read_bytes()
                        headers.append(
                            ("Content-Disposition", 'attachment; filename="findings.md"')
                        )
                elif method == "GET":
                    report = subpage == "report"
                    download = report and query.get("download") == ["1"]
                    body = review_view(base, name, result, report=report, download=download)
                    if download:
                        headers.append(
                            ("Content-Disposition", 'attachment; filename="risikobericht.html"')
                        )
                else:
                    status, body = "405 Method Not Allowed", "Methode nicht erlaubt."
            else:
                status, body = "404 Not Found", "Seite nicht gefunden."
        except ValueError as error:
            status, content_type, body = "400 Bad Request", "text/plain; charset=utf-8", str(error)
        except (OSError, RuntimeError, sqlite3.Error):
            status = "500 Internal Server Error"
            content_type, body = (
                "text/plain; charset=utf-8",
                "Die Prüfung konnte nicht gespeichert werden.",
            )

        data = body.encode("utf-8") if isinstance(body, str) else body
        headers.extend([("Content-Type", content_type), ("Content-Length", str(len(data)))])
        start_response(status, headers)
        return [data]

    return app


def main() -> None:
    """Start the local review server on a loopback port."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--history-db", type=Path, default=Path("bidguard-history.sqlite3"))
    parser.add_argument("--model", help="optional local model name")
    parser.add_argument("--endpoint", help="loopback Ollama or chat completions URL")
    parser.add_argument("--max-requests", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=90, help="seconds per model comparison")
    args = parser.parse_args()
    if bool(args.endpoint) != bool(args.model) or args.max_requests < 1 or not args.timeout > 0:
        parser.error("provide --endpoint and --model together and positive comparison limits")
    semantic = (
        SemanticConfig(args.endpoint, args.model, args.max_requests, args.timeout)
        if args.endpoint
        else None
    )
    with TemporaryDirectory(prefix="bidguard-") as temporary:
        application = make_app(Path(temporary), history_db=args.history_db, semantic=semantic)
        with make_server("127.0.0.1", args.port, application) as server:
            print(f"BidGuard AI · http://127.0.0.1:{server.server_port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
