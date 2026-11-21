"""Server-rendered German views for the local review workflow."""

from html import escape

from .history import RULES
from .model import Item

STATUSES = {"open": "Offen", "confirmed": "Bestätigt", "dismissed": "Verworfen"}
_HISTORY_STATUS = {
    "checked": "Geprüft",
    "inapplicable": "Nicht anwendbar",
    "inconclusive": "Offen",
    "deferred": "Zurückgestellt",
}
_RULE_NAMES = {
    "scope_reference": "Zeichnungsumfang",
    "aggregate_limit": "Körnungsgrenze",
}
_HISTORY_REASONS = {
    "format": "Regel gilt nur für PDF",
    "trade": "anderes Gewerk",
    "partial_text": "PDF-Text nur teilweise verfügbar",
    "scope": "keine passenden Positionsmerkmale",
    "unsupported_rule": "Regel nicht verfügbar",
    "model_disabled": "Modell für diesen Lauf nicht aktiviert",
    "model_incomplete": "Modell nicht verfügbar oder Quellenauswahl unvollständig",
    "budget": "Vergleichsbudget ausgeschöpft",
}
_HISTORY_FIELDS = """
<fieldset><legend>Für das Speichern in der Historie</legend>
<label for="reviewer">Prüferkürzel</label><input id="reviewer" name="reviewer" maxlength="120">
<label for="trade">Gewerk (optional)</label>
<input id="trade" name="trade" maxlength="120" value="<!--current-trade-->">
<label for="severity">Priorität</label><select id="severity" name="severity">
<option value="low">Niedrig</option><option value="medium" selected>Mittel</option>
<option value="high">Hoch</option></select></fieldset>
"""

_STYLE = """
:root{font:16px/1.55 system-ui,sans-serif;color:#202620;background:#f4f6f3}
body{margin:0}main{max-width:54rem;padding:2rem 1.25rem;margin:auto}
h1,h2,h3{line-height:1.2} h1{margin-top:.4rem} header{margin-bottom:2rem}
a{color:#215438} nav{display:flex;flex-wrap:wrap;gap:.6rem 1rem}
article{background:white;border:1px solid #d5ddd5;border-radius:.55rem;padding:1rem 1.25rem;
margin:1rem 0}blockquote{margin:.3rem 0 1rem;padding:.4rem .85rem;border-left:4px solid #d5a62e;
background:#fbf7eb}label{display:block;font-weight:600;margin:.7rem 0 .25rem}
textarea{width:100%;box-sizing:border-box}button,select,textarea,input{font:inherit}
button{cursor:pointer;background:#215438;color:white;border:0;border-radius:.3rem;
padding:.5rem .9rem}button:disabled{opacity:.6;cursor:wait}
.badge{font-size:.9rem;color:#465347}.actions{margin-top:1rem}.question{white-space:pre-wrap}
.table{overflow:auto}table{border-collapse:collapse;width:100%}
td,th{padding:.55rem;text-align:left;border-bottom:1px solid #d5ddd5}td{vertical-align:top}
tr:target{background:#fbf2cf}details p{white-space:pre-wrap}
@page{size:A4;margin:16mm}
@media print{nav{display:none} :root,article{background:white;color:black}
main{padding:0;max-width:none}article{break-inside:avoid}}
"""

_UPLOAD = """
<form id="upload">
  <label for="lv">Leistungsverzeichnis als PDF oder GAEB X83</label>
  <input id="lv" type="file" accept=".pdf,.x83,application/pdf" required>
  <p class="badge">GAEB 90, DOCX und XLSX werden derzeit nicht unterstützt.</p>
  <!--model-option-->
  <!--history-option-->
  <div class="actions"><button>Datei prüfen</button></div>
  <p id="progress" role="status"></p>
</form>
<script>
const form = document.querySelector('#upload');
const input = document.querySelector('#lv');
const model = document.querySelector('#semantic');
input.addEventListener('change', () => {
  if (model) model.disabled = !input.files[0]?.name.toLowerCase().endsWith('.pdf');
});
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = input.files[0];
  const type = file.name.toLowerCase().endsWith('.x83') ? 'application/xml' : 'application/pdf';
  const status = document.querySelector('#progress');
  const button = form.querySelector('button');
  button.disabled = true;
  status.textContent = 'Datei wird geprüft …';
  try {
    const query = new URLSearchParams({name: file.name});
    const trade = document.querySelector('#history-trade')?.value.trim();
    if (trade) query.set('trade', trade);
    if (model?.checked && !model.disabled) query.set('semantic', '1');
    const response = await fetch('/upload?' + query, {
      method: 'POST', headers: {'Content-Type': type}, body: file
    });
    if (!response.ok) throw new Error(await response.text());
    location.assign(response.url);
  } catch (error) {
    status.textContent = 'Prüfung fehlgeschlagen. ' + error.message;
    button.disabled = false;
  }
});
</script>
"""


def _page(title: str, content: str) -> str:
    """Wrap a rendered view in a single HTML document.

    :param title: visible title and browser tab label.
    :param content: already safely rendered HTML.
    :returns: complete UTF-8 HTML document.
    """
    return (
        f'<!doctype html><html lang="de"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)} | BidGuard AI</title><style>{_STYLE}</style></head>"
        f'<body><main><header><div class="badge">BidGuard AI</div>'
        f"<h1>{escape(title)}</h1></header>{content}</main></body></html>"
    )


def upload_view(model: str | None = None, *, history: bool = False) -> str:
    """Render the single-file upload page.

    :param model: local model name, when available.
    :param history: whether optional trade metadata is used for historical checks.
    :returns: complete upload view.
    """
    option = (
        f'<label><input type="checkbox" id="semantic" disabled> '
        f"Lokales Modell für PDF verwenden ({escape(model)})</label>"
        if model
        else ""
    )
    trade = (
        '<label for="history-trade">Gewerk für historische Regeln (optional)</label>'
        '<input id="history-trade" maxlength="120">'
        if history
        else ""
    )
    body = _UPLOAD.replace("<!--model-option-->", option).replace("<!--history-option-->", trade)
    return _page("LV prüfen", body)


def _finding(base: str, finding: dict, report: bool, history: bool) -> str:
    """Render one finding and its evidence links.

    :param base: internally generated run URL.
    :param finding: finding with reviewer status and question.
    :param report: whether the rendering is for export.
    :param history: whether history controls and labels are available.
    :returns: rendered finding.
    """
    identifier = finding["id"]
    status = finding["review_status"]
    pieces = [
        f'<article id="{identifier}"><h2>{identifier} · {escape(finding["assessment"])}</h2>',
        f'<p class="badge">{escape(finding["method"])} · {STATUSES[status]}</p>',
        f'<p class="badge">Kategorie: {escape(finding["category"])} · '
        f"Beleglage: {escape(finding['evidence'])}</p>",
        f"<p>{escape(finding['explanation'])}</p>",
        f"<p><strong>Mögliche Auswirkung:</strong> {escape(finding['impact'])}</p>",
    ]
    if history:
        origin = "Historischer Regel-Treffer" if finding["history_match"] else "Aktuelle Prüfung"
        pieces.append(f'<p class="badge">{origin}</p>')
    for source in finding["sources"]:
        ref = escape(source["reference"])
        if not report and "position" in source:
            ref = f'<a href="#position-{source["position"]}">{ref}</a>'
        elif not report:
            ref = (
                f'<a href="{base}/pdf#page={source["page"]}" target="_blank" rel="noopener">'
                f"{ref}</a>"
            )
        pieces.append(f"<div>{ref}<blockquote>{escape(source['excerpt'])}</blockquote></div>")
    if not report:
        options = "".join(
            f'<option value="{value}"{" selected" if value == status else ""}>{label}</option>'
            for value, label in STATUSES.items()
        )
        pieces.extend(
            [
                f'<label for="status-{identifier}">Prüfstatus</label>',
                f'<select id="status-{identifier}" name="status-{identifier}">{options}</select>',
                f'<label for="question-{identifier}">Bieterfrage</label>',
                f'<textarea id="question-{identifier}" name="question-{identifier}" rows="3" '
                f'maxlength="2000">{escape(finding["question"])}</textarea>',
            ]
        )
        if history and finding.get("rule") in RULES | {"semantic"}:
            pieces.append(
                f'<label><input type="checkbox" name="promote-{identifier}"> '
                "Bestätigten Befund in die Historie aufnehmen</label>"
            )
            if finding["rule"] == "semantic":
                pieces.append(
                    f'<label for="condition-{identifier}">Konfliktbedingung</label>'
                    f'<textarea id="condition-{identifier}" name="condition-{identifier}" '
                    'rows="2" maxlength="500"></textarea>'
                    f'<label for="terms-{identifier}">Suchbegriffe, durch Kommas getrennt</label>'
                    f'<input id="terms-{identifier}" name="terms-{identifier}" maxlength="500">'
                )
    pieces.append("</article>")
    return "".join(pieces)


def _positions(items: tuple[Item, ...]) -> str:
    """Render the normalized GAEB positions with finding anchors.

    :param items: parsed positions in source order.
    :returns: an HTML table with quantities, units and both description fields.
    """
    rows = []
    for number, item in enumerate(items, 1):
        description = escape(item.short_text)
        if item.long_text:
            description += (
                f"<details><summary>Langtext</summary><p>{escape(item.long_text)}</p></details>"
            )
        qty = str(item.quantity) if item.quantity is not None else "–"
        rows.append(
            f'<tr id="position-{number}"><th scope="row">{escape(item.oz) or "–"}</th>'
            f"<td>{description}</td><td>{escape(qty)}</td><td>{escape(item.unit) or '–'}</td></tr>"
        )
    return (
        '<h2 id="positions">Positionen</h2><div class="table"><table><thead>'
        "<tr><th>OZ</th><th>Leistung</th><th>Menge</th><th>ME</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def review_view(
    base: str, name: str, result: dict, *, report: bool = False, download: bool = False
) -> str:
    """Render the editable review or a print-ready snapshot.

    :param base: internally generated run URL.
    :param name: original upload filename.
    :param result: structured findings, review state and coverage.
    :param report: whether to render the print-ready version.
    :param download: whether to omit links requiring an active local session.
    :returns: complete UTF-8 HTML document.
    """
    findings = [f for f in result["findings"] if not report or f["review_status"] != "dismissed"]
    content = [f"<p>{escape(name)}</p>"]
    if report:
        links = ""
        if not download:
            links = (
                f'<a href="{base}/report?download=1" download>HTML herunterladen</a>'
                f'<a href="{base}">Zur Prüfung</a>'
            )
        content.append(
            '<nav><button type="button" onclick="window.print()">Drucken / Als PDF speichern'
            f"</button>{links}</nav>"
        )
    else:
        sources = (
            f'<a href="{base}/pdf">Annotiertes PDF</a><a href="{base}/log">Befundprotokoll</a>'
            if "annotated_pdf" in result
            else '<a href="#positions">Positionen</a>'
        )
        content.append(
            f'<nav><a href="/">Neue Prüfung</a>{sources}'
            f'<a href="{base}/report">Risikobericht</a></nav>'
        )

    if gaeb := result.get("gaeb"):
        version = escape(gaeb["version"] or "unbekannt")
        phase = escape(gaeb["phase"] or "unbekannt")
        content.append(
            f'<p class="badge">GAEB {version} · Phase {phase} · {gaeb["items"]} Positionen</p>'
            f"<p>Preisprüfung: {gaeb['arithmetic_checked']} Gesamtbeträge geprüft, "
            f"{gaeb['arithmetic_skipped']} übersprungen.</p>"
        )
        if gaeb["arithmetic_checked"] == gaeb["arithmetic_skipped"] == 0:
            content.append("<p>Keine Preisangaben. Für X83 ist das zulässig.</p>")
    else:
        if model := result.get("semantic_model"):
            content.append(f'<p class="badge">Lokales Modell: {escape(model)}</p>')
        content.append(f'<p class="badge">Modellprüfung: {escape(result["semantic_coverage"])}</p>')
    if result["warnings"]:
        content.append(
            "<ul>" + "".join(f"<li>{escape(w)}</li>" for w in result["warnings"]) + "</ul>"
        )
    history = "history" in result
    if history:
        content.append("<h2>Historische Regeln</h2>")
        if trade := result["history_trade"]:
            content.append(f"<p>Gewerk: {escape(trade)}</p>")
        if result["history"]:
            entries = []
            for pattern in result["history"]:
                label = escape(
                    pattern["condition"] or _RULE_NAMES.get(pattern["rule"], pattern["rule"])
                )
                status = _HISTORY_STATUS[pattern["status"]]
                reason = _HISTORY_REASONS.get(pattern["reason"])
                detail = f" ({reason})" if reason else ""
                entries.append(
                    f"<li>{label} · {status}{detail} · {pattern['cases']} bestätigte Fälle</li>"
                )
            content.append("<ul>" + "".join(entries) + "</ul>")
        else:
            content.append("<p>Keine historischen Regeln gespeichert.</p>")
        if result.get("can_resume") and not report:
            content.append(
                f'<form method="post" action="{base}/resume">'
                "<p>Änderungen zuerst speichern. Diese Prüfung kann nach einem Neustart über "
                "dieselbe Adresse fortgesetzt werden.</p>"
                "<button>Historische Prüfung fortsetzen</button></form>"
            )
    if not findings:
        content.append("<p>Keine aktiven Befunde.</p>")
    if findings and not report:
        content.append(f'<form method="post" action="{base}">')
    content.extend(_finding(base, finding, report, history) for finding in findings)
    if findings and not report:
        if history and any(f.get("rule") in RULES | {"semantic"} for f in findings):
            content.append(
                _HISTORY_FIELDS.replace("<!--current-trade-->", escape(result["history_trade"]))
            )
        content.append('<div class="actions"><button>Änderungen speichern</button></div></form>')
    if report:
        questions = [
            f"<li><strong>{f['id']}</strong> "
            f'<span class="question">{escape(f["question"])}</span></li>'
            for f in findings
            if f["question"].strip()
        ]
        content.extend(
            [
                "<h2>Bieterfragen</h2>",
                "<ol>" + "".join(questions) + "</ol>"
                if questions
                else "<p>Keine Bieterfragen.</p>",
            ]
        )
    elif gaeb:
        content.append(_positions(result["positions"]))
    return _page("Risikobericht" if report else "Befunde prüfen", "".join(content))
