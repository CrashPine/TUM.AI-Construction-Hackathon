"""Verify PDF and GAEB uploads through the local web workflow without a model."""

import json
import re
from collections.abc import Callable
from contextlib import closing
from io import BytesIO
from pathlib import Path
from sqlite3 import connect
from urllib.error import URLError
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults
from zipfile import ZipFile

import pymupdf
import pytest
from openpyxl import Workbook

from boqcheck import semantic
from boqcheck.docx_context import read_context
from boqcheck.history import initialize, promote, replay
from boqcheck.web import make_app
from boqcheck.web_gaeb import review_legacy

_ROOF = Path(__file__).resolve().parents[1] / "data" / "raw" / "LV_09_Porenbetondach.pdf"
_INCOMPLETE = (
    "2101010010 NNN         00000001000St",
    "2101010020 NNN         00000001000St",
    "2301010020  00000001000 000000000100",
    "320101      000000000200",
    "99000000000200",
)


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


def _legacy(phase: str, *rows: str, prefix: tuple[str, ...] = ()) -> bytes:
    r"""Build synthetic fixed-width GAEB 90 records.

    :param phase: exchange phase in the header.
    :param \*rows: records following the header.
    :param prefix: records before the header.
    :returns: 80-column records separated by CRLF.
    """
    header = f"00        {phase}L".ljust(62) + "1122PPPPI90"
    records = (*prefix, header, *rows)
    text = "\r\n".join(f"{row:<74.74}{n:06d}" for n, row in enumerate(records, 1)) + "\r\n"
    return text.encode()


def _duplicate_priced_d84() -> tuple[bytes, list[int], list[int]]:
    """Duplicate the second position's OZ and increase only its total by one cent.

    :returns: modified file bytes and the zero-based 21 and 23 line indexes.
    """
    rows = _ROOF.with_name("Angebot AN24-0305.D84").read_bytes().splitlines()
    positions = [i for i, row in enumerate(rows) if row.startswith(b"21")][:2]
    prices = [i for i, row in enumerate(rows) if row.startswith(b"23")][:2]
    assert positions[0] < prices[0] < positions[1] < prices[1]
    for first, second in (positions, prices):
        rows[second] = rows[second][:2] + rows[first][2:11] + rows[second][11:]
    second_price = rows[prices[1]]
    total = int(second_price[24:36]) + 1
    rows[prices[1]] = second_price[:24] + f"{total:012d}".encode() + second_price[36:]
    return b"\r\n".join(rows) + b"\r\n", positions, prices


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


@pytest.mark.parametrize(
    ("name", "count", "checked"),
    [
        ("Angebot AN24-0305.D84", 274, 274),
        ("StBALV23040.D84", 249, 0),
        ("8209.003_Leistungsverzeichnis_leer.D83", 159, 0),
        ("StBALV23040.D86", 249, 249),
        ("[ORT_024] LV24069.D86", 197, 197),
    ],
)
def test_legacy_upload(tmp_path: Path, name: str, count: int, checked: int) -> None:
    """Upload each real legacy fixture, open source records and export the review.

    :param tmp_path: isolated web storage.
    :param name: fixture name.
    :param count: expected positions.
    :param checked: comparable line amounts.
    """
    app = make_app(tmp_path)
    data = _ROOF.with_name(name).read_bytes()
    status, headers, _ = _request(
        app, "/upload?" + urlencode({"name": name.lower()}), data, "application/octet-stream"
    )
    assert status.startswith("303")
    run = headers["Location"]
    page = _request(app, run)[2].decode()
    assert f"GAEB 90 · Phase {name[-2:]} · {count} Positionen" in page
    assert f"Preisprüfung: {checked} Gesamtbeträge geprüft" in page and 'id="record-' in page
    report = _request(app, run + "/report?download=1")[2].decode()
    for rendered in (page, report):
        assert "Experimentell" in rendered and "genau eine Mengeneinheit" in rendered
        assert "Positionsarten und Preisbasen" in rendered
    if name.endswith("D83"):
        assert "Für D83 ist das zulässig" in report and "Keine aktiven Befunde" in report
    if name == "StBALV23040.D84":
        assert "249 übersprungen" in report


def test_legacy_duplicate_occurrences_are_editable_and_source_backed(tmp_path: Path) -> None:
    """Link both duplicate 21 records and preserve the edited finding in the report.

    :param tmp_path: isolated web storage.
    """
    data, positions, _ = _duplicate_priced_d84()
    result = review_legacy("test.D84", data)
    duplicates = [f for f in result["findings"] if f["assessment"] == "Doppelte OZ"]
    assert len(duplicates) == 1
    duplicate = duplicates[0]
    assert duplicate["category"] == "LV-Struktur"
    assert [s["record"] for s in duplicate["sources"]] == [i + 1 for i in positions]
    assert all(f["assessment"] != "Pflichtfelder fehlen" for f in result["findings"])

    app = make_app(tmp_path)
    status, headers, _ = _request(app, "/upload?name=test.D84", data, "application/octet-stream")
    assert status.startswith("303")
    run = headers["Location"]
    page = _request(app, run)[2].decode()
    article = page.split(f'<article id="{duplicate["id"]}">', 1)[1].split("</article>", 1)[0]
    assert re.findall(r'href="#record-(\d+)"', article) == [str(i + 1) for i in positions]
    form = {f"status-{f['id']}": "open" for f in result["findings"]}
    form[f"status-{duplicate['id']}"] = "confirmed"
    form[f"question-{duplicate['id']}"] = "Welche OZ gilt?"
    assert _request(app, run, urlencode(form).encode(), "application/x-www-form-urlencoded")[
        0
    ].startswith("303")
    report = _request(app, run + "/report?download=1")[2].decode()
    assert "Doppelte OZ" in report and "Welche OZ gilt?" in report and "Bestätigt" in report
    assert all(f"Zeile {i + 1} · Satz 21" in report for i in positions)
    assert 'href="#record-' not in report


def test_legacy_duplicate_price_attribution_uses_the_item_occurrence() -> None:
    """A mismatch cites only the changed occurrence, not both items with the same OZ."""
    data, positions, prices = _duplicate_priced_d84()
    result = review_legacy("test.D84", data)
    line = next(f for f in result["findings"] if f["explanation"].startswith("Position "))
    assert [s["record"] for s in line["sources"]] == [positions[1] + 1, prices[1] + 1]


def test_legacy_duplicate_price_only_occurrences_cite_both_23_records() -> None:
    """A price-only D84 treats each 23 as a distinct position, even for equal OZs."""
    rows = _ROOF.with_name("StBALV23040.D84").read_bytes().splitlines()
    prices = [i for i, row in enumerate(rows) if row.startswith(b"23")][:2]
    assert not any(row.startswith(b"21") for row in rows)
    rows[prices[1]] = rows[prices[1]][:2] + rows[prices[0]][2:11] + rows[prices[1]][11:]
    result = review_legacy("test.D84", b"\r\n".join(rows) + b"\r\n")
    duplicates = [f for f in result["findings"] if f["assessment"] == "Doppelte OZ"]
    assert len(duplicates) == 1
    assert [s["record"] for s in duplicates[0]["sources"]] == [i + 1 for i in prices]
    assert (result["gaeb"]["arithmetic_checked"], result["gaeb"]["arithmetic_skipped"]) == (0, 249)


@pytest.mark.parametrize(
    ("finding_index", "expected"),
    [(0, {3, 5}), (1, {5, 7, 11}), (2, {5, 7, 9, 13})],
)
def test_legacy_calculations_cite_only_effective_records(
    tmp_path: Path, finding_index: int, expected: set[int]
) -> None:
    """Repeated 23, 32 and 99 records cite the last values and exactly the relevant items.

    :param tmp_path: isolated web storage.
    :param finding_index: line, section or grand-total finding.
    :param expected: contributing physical record numbers.
    """
    data = _legacy(
        "84",
        "2101010010 NNN         00000001000St",
        "2301010010  00000001000 000000000100",
        "2301010010  00000001000 000000000200",
        "2101010020 NNN         00000001000St",
        "2301010020  00000001000 000000000100",
        "2101100001 NNN         00000001000St",
        "2301100001  00000001000 000000000100",
        "320101      000000000300",
        "320101      000000000400",
        "99000000000400",
        "99000000000500",
        prefix=("T0Free text before the header",),
    )
    result = review_legacy("test.D84", data)
    assert len(result["findings"]) == 3
    assert {s["record"] for s in result["findings"][finding_index]["sources"]} == expected
    numbers = [number for number, _, _ in result["records"]]
    assert len(numbers) == len(set(numbers))
    app = make_app(tmp_path)
    _, headers, _ = _request(app, "/upload?name=test.D84", data, "application/octet-stream")
    page = _request(app, headers["Location"])[2].decode()
    assert all(page.count(f'id="record-{number}"') == 1 for number in numbers)


def test_legacy_real_section_sums_include_all_item_sources(tmp_path: Path) -> None:
    """Keep complete source evidence for both discrepant sections of the real D86.

    :param tmp_path: isolated web storage.
    """
    path = _ROOF.with_name("StBALV23040.D86")
    data = path.read_bytes()
    findings = review_legacy(path.name, data)["findings"]
    assert [len(f["sources"]) for f in findings] == [32, 24]
    for finding in findings:
        assert finding["sources"][0]["excerpt"].startswith("32")
        assert all(source["excerpt"].startswith("23") for source in finding["sources"][1:])

    app = make_app(tmp_path)
    _, headers, _ = _request(
        app, f"/upload?{urlencode({'name': path.name})}", data, "application/octet-stream"
    )
    run = headers["Location"]
    page = _request(app, run)[2].decode()
    report = _request(app, run + "/report?download=1")[2].decode()
    for finding in findings:
        article = page.split(f'<article id="{finding["id"]}">', 1)[1].split("</article>", 1)[0]
        assert set(re.findall(r'href="#record-(\d+)"', article)) == {
            str(source["record"]) for source in finding["sources"]
        }
        assert all(source["reference"] in report for source in finding["sources"])


@pytest.mark.parametrize("phase", ("84", "83"))
def test_legacy_unpriced_items_count_as_skipped_except_for_unpriced_d83(phase: str) -> None:
    """Report absent price records in priced files without changing unpriced D83 coverage.

    :param phase: exchange phase of a partially priced file.
    """
    result = review_legacy(f"test.D{phase}", _legacy(phase, *_INCOMPLETE))
    assert (result["gaeb"]["arithmetic_checked"], result["gaeb"]["arithmetic_skipped"]) == (1, 1)
    unpriced = review_legacy("test.D83", _legacy("83", *_INCOMPLETE[:2]))
    assert (unpriced["gaeb"]["arithmetic_checked"], unpriced["gaeb"]["arithmetic_skipped"]) == (
        0,
        0,
    )


def test_legacy_wholly_unpriced_d84_items_are_skipped() -> None:
    """Count even a wholly unpriced D84 as uncheckable rather than intentionally unpriced."""
    result = review_legacy("test.D84", _legacy("84", *_INCOMPLETE[:2]))
    assert (result["gaeb"]["arithmetic_checked"], result["gaeb"]["arithmetic_skipped"]) == (0, 2)


def test_legacy_inconclusive_sums_are_neutral_and_source_backed(tmp_path: Path) -> None:
    """Explain missing operands with the 21 record in the review and standalone report.

    :param tmp_path: isolated web storage.
    """
    data = _legacy("84", *_INCOMPLETE)
    result = review_legacy("test.D84", data)
    assert len(result["findings"]) == 2
    section, total = result["findings"]
    assert {f["assessment"] for f in (section, total)} == {"Summe nicht prüfbar"}
    assert {f["category"] for f in (section, total)} == {"Prüfumfang"}
    assert {s["record"] for s in section["sources"]} == {2, 4, 5}
    assert {s["record"] for s in total["sources"]} == {2, 4, 6}
    app = make_app(tmp_path)
    _, headers, _ = _request(app, "/upload?name=test.D84", data, "application/octet-stream")
    run = headers["Location"]
    page = _request(app, run)[2].decode()
    form = {f"status-{f['id']}": "open" for f in result["findings"]}
    form[f"question-{section['id']}"] = "Welcher Betrag fehlt?"
    assert _request(app, run, urlencode(form).encode(), "application/x-www-form-urlencoded")[
        0
    ].startswith("303")
    report = _request(app, run + "/report?download=1")[2].decode()
    for number in (2, 4, 5, 6):
        assert f'href="#record-{number}"' in page
        assert f"Zeile {number} · Satz" in report
    assert "Summe nicht prüfbar" in report and "Rechenabweichung" not in report
    assert "Welcher Betrag fehlt?" in report


def test_legacy_price_evidence(tmp_path: Path) -> None:
    """Check that an altered D84 price leads to the original record and editable report.

    :param tmp_path: isolated web storage.
    """
    app = make_app(tmp_path)
    name = "Angebot AN24-0305.D84"
    rows = _ROOF.with_name(name).read_bytes().splitlines()
    index = next(i for i, row in enumerate(rows) if row.startswith(b"23"))
    rows[index] = rows[index][:24] + b"000007200001" + rows[index][36:]
    data = b"\r\n".join(rows) + b"\r\n"
    status, headers, _ = _request(app, "/upload?name=test.D84", data, "application/octet-stream")
    assert status.startswith("303")
    run = headers["Location"]
    page = _request(app, run)[2].decode()
    assert f'href="#record-{index + 1}"' in page
    assert "Mögliche Rechenabweichung" in page
    assert "Positionsarten und Preisbasen sind nicht vollständig erkannt" in page
    form = dict.fromkeys(re.findall(r'name="(status-BG-\d+)"', page), "open")
    form.update({"status-BG-001": "confirmed", "question-BG-001": "Bitte Preis klären."})
    fields = urlencode(form)
    assert _request(app, run, fields.encode(), "application/x-www-form-urlencoded")[0].startswith(
        "303"
    )
    report = _request(app, run + "/report?download=1")[2].decode()
    assert "72000.01" in report and "Bitte Preis klären." in report
    assert "Mögliche Rechenabweichung" in report
    assert "Positionsarten und Preisbasen sind nicht vollständig erkannt" in report
    assert rows[index].decode("ascii") in report
    assert _request(app, "/upload?name=test.D83", data, "application/octet-stream")[0].startswith(
        "400"
    )


def test_docx_attachment(tmp_path: Path) -> None:
    """Attach a real DOCX, cite a source and keep independent runs isolated.

    :param tmp_path: temporary review storage.
    """
    app = make_app(tmp_path)
    pdf = _ROOF.read_bytes()
    upload = "/upload?name=roof.pdf"
    run = _request(app, upload, pdf, "application/pdf")[1]["Location"]
    other = _request(app, upload, pdf, "application/pdf")[1]["Location"]
    data = _ROOF.with_name("LV-Positionen.docx").read_bytes()
    target = run + "/attachment?name=LV-Positionen.docx"
    assert _request(app, target, b"invalid", "application/octet-stream")[0].startswith("400")
    for _ in range(2):
        assert _request(app, target, data, "application/octet-stream")[0].startswith("303")
    page = _request(app, run)[2].decode()
    assert "53 Textstellen" in page and "P2 · Absatz 2" in page
    assert "docx-P2" not in _request(app, other)[2].decode()
    fields = {
        "status-BG-001": "confirmed",
        "question-BG-001": "Welche Leistung gilt?",
        "citation-BG-001": "P2",
    }
    assert _request(app, run, urlencode(fields).encode(), "application/x-www-form-urlencoded")[
        0
    ].startswith("303")
    report = _request(app, run + "/report?download=1")[2].decode()
    assert "LV-Positionen.docx · Absatz 2" in report and "Baustelleneinrichtung [psch]" in report
    assert "Welche Leistung gilt?" in report


@pytest.mark.parametrize(
    ("spec", "component", "checks", "outcome"),
    [
        ("offen", "Dachplatte", 1, "Durch Anlage geklärt"),
        ("10 mm", "Dachplatte", 1, "Abweichung zwischen LV und Anlage"),
        ("2 cm", "Dachplatte", 1, ""),
        ("10 mm", "Fassade", 0, ""),
    ],
)
def test_pdf_attachment_comparison(
    tmp_path: Path, spec: str, component: str, checks: int, outcome: str
) -> None:
    """Verify clarification, conflict, equivalent units and different components via uploads.

    :param tmp_path: isolated review storage.
    :param spec: source PDF thickness.
    :param component: DOCX position title.
    :param checks: number of grounded comparisons.
    :param outcome: expected finding label, or empty for no finding.
    """
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((50, 50), f"01.01.0010. Dachplatte\nDicke: {spec}")
        source = pdf.tobytes()
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(
            "word/document.xml",
            f"""
          <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:p><w:r><w:t>OZ 01.01.0010 {component}</w:t></w:r></w:p>
          <w:p><w:r><w:t>Dicke: 20 mm</w:t></w:r></w:p></w:body></w:document>""",
        )
    app = make_app(tmp_path)
    run = _request(app, "/upload?name=LV.pdf", source, "application/pdf")[1]["Location"]
    assert _request(
        app, run + "/attachment?name=Details.docx", data.getvalue(), "application/octet-stream"
    )[0].startswith("303")
    report = _request(app, run + "/report?download=1")[2].decode()
    assert f"{checks} eindeutig zugeordnete" in report
    if outcome:
        assert outcome in report and f"Dicke: {spec}" in report
        assert "Details.docx · Absatz 2" in report and "Dicke: 20 mm" in report
        if spec == "offen":
            assert "Keine Bieterfragen" in report
    else:
        assert "Keine aktiven Befunde" in report


def test_docx_cell_and_heading_order() -> None:
    """Keep a styled heading, two table cells and the next paragraph in source order."""
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """
          <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
          <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Dach</w:t></w:r></w:p>
          <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Beton</w:t></w:r></w:p></w:tc>
          <w:tc><w:p><w:r><w:t>8 mm</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
          <w:p><w:r><w:t>Ende</w:t></w:r></w:p></w:body></w:document>""",
        )
    entries = read_context(data.getvalue())
    assert [(e["id"], e["text"]) for e in entries] == [
        ("P1", "Dach"),
        ("T1R1C1", "Beton"),
        ("T1R1C2", "8 mm"),
        ("P2", "Ende"),
    ]
    assert entries[0]["reference"] == "Überschrift 1"
    assert entries[2]["reference"] == "Tabelle 1, Zeile 1, Zelle 2"


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

    edited = urlencode(
        {"status-BG-001": "confirmed", "question-BG-001": "Welcher Zustand gilt für Ventil B?"}
    ).encode()
    assert _request(restarted, result, edited, "application/x-www-form-urlencoded")[0].startswith(
        "303"
    )
    assert "Historische Prüfung fortsetzen" in _request(restarted, result)[2].decode()

    original_pdf = _request(restarted, result + "/pdf")[2]
    with closing(connect(db_path)) as database:
        paths = database.execute("SELECT result FROM review_jobs").fetchone()[0]
    temporary_result = json.loads(paths)
    Path(temporary_result["annotated_pdf"]).unlink()
    Path(temporary_result["findings_log"]).unlink()

    recovered = make_app(tmp_path / "after-restart", history_db=db_path, semantic=config)
    assert _request(recovered, result + "/pdf")[2] == original_pdf
    assert (
        "Welcher Zustand gilt für Ventil B?" in _request(recovered, result + "/report")[2].decode()
    )
    assert len(prompts) == 2
    assert _request(recovered, result + "/resume", b"")[0].startswith("303")
    assert len(prompts) == 3
    assert prompts[-1][0] == "The valve inspection requirements specify opposite states."
    page = _request(recovered, result)[2].decode()
    assert "Zurückgestellt (Vergleichsbudget ausgeschöpft)" not in page
    assert "Historische Prüfung fortsetzen" not in page
    assert page.count('<article id="BG-') == 1
    assert "Bestätigt" in page and "Welcher Zustand gilt für Ventil B?" in page
    assert _request(recovered, result + "/resume", b"")[0].startswith("400")
    assert len(prompts) == 3


def test_german_spelling_is_grounded_and_editable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Require dictionary evidence and preserve the original token through review.

    :param tmp_path: temporary PDF artifacts directory.
    :param monkeypatch: fixture for replacing model inference.
    """
    config = semantic.SemanticConfig(
        "http://127.0.0.1:44445/api/chat",
        "test",
        max_requests=1,
        spelling=True,
        lexicon=frozenset({"montagge"}),
    )

    def suggest(selected: semantic.SemanticConfig, payload: dict) -> list[dict]:
        """Return a typo, an accepted project word and unsupported proposals.

        :param selected: model review configuration.
        :param payload: excerpts from the current uploaded PDF.
        :returns: simulated spelling proposals.
        """
        assert selected.spelling and payload["check_spelling"] is True
        source = payload["left"][0]["id"]
        return [
            {
                "kind": "spelling",
                "source_id": identifier,
                "token": token,
                "correction": replacement,
                "explanation": "Der Satz verlangt ein Verb.",
            }
            for identifier, token, replacement in (
                (source, "ausführren", "ausführen"),
                (source, "Montagge", "Montage"),
                (source, "Montage", "Montagge"),
                (source, "BETTON", "Beton"),
                (source, "Vorbereittung", "Vorbereitung"),
                ("L999", "ausführren", "ausführen"),
            )
        ]

    monkeypatch.setattr(semantic, "_request", suggest)
    app = make_app(tmp_path, semantic=config)
    with pymupdf.open() as document:
        document.new_page().insert_text(
            (72, 72), "Die Montagge fachgerecht ausführren. BETTON Vorbereittung-"
        )
        response = _request(
            app, "/upload?name=lv.pdf&semantic=1", document.tobytes(), "application/pdf"
        )
    run = response[1]["Location"]
    page = _request(app, run)[2].decode()
    assert page.count('<article id="BG-') == 1
    assert "Originalwort: <strong>ausführren" in page
    assert 'value="ausführen"' in page
    with pymupdf.open(stream=_request(app, run + "/pdf")[2]) as output:
        source = output[0]
        assert "ausführren" in source.get_text()
        assert "ausführren → ausführen" in source.first_annot.info["content"]
    edited = urlencode({"status-BG-001": "confirmed", "correction-BG-001": "durchführen"}).encode()
    assert _request(app, run, edited, "application/x-www-form-urlencoded")[0].startswith("303")
    report = _request(app, run + "/report")[2].decode()
    assert "Originalwort: <strong>ausführren" in report
    assert "Korrekturvorschlag: <strong>durchführen" in report


def test_xlsx_sheet_row_report(tmp_path: Path) -> None:
    """Trace arithmetic and formula findings to the physical spreadsheet rows.

    :param tmp_path: isolated web review storage.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Dach"
    sheet.append(["OZ", "Kurztext", "Menge", "ME", "EP", "Preisbasis", "Gesamtbetrag"])
    sheet.append(["01.01.0010", "Dachplatte", "1.000,0", "m", 2, 100, 19.99])
    sheet.append([])
    sheet.append(["01.01.0020", "Rohr", "=1+1", "m"])
    workbook.create_sheet("Hinweise").append(["Text"])
    data = BytesIO()
    workbook.save(data)
    app = make_app(tmp_path)
    status, headers, _ = _request(
        app, "/upload?name=sample.XLSX", data.getvalue(), "application/octet-stream"
    )
    assert status.startswith("303")
    run = headers["Location"]
    review = _request(app, run)[2].decode()
    assert 'href="#position-1"' in review and 'id="position-1"' in review
    report = _request(app, run + "/report?download=1")[2].decode()
    assert "XLSX · 2 Positionen" in report
    assert "Blatt Dach · Zeile 2" in report and "Blatt Dach · Zeile 4" in report
    assert "20.00" in report and "19.99" in report and "=1+1" in report
    assert "Blatt Hinweise" in report
