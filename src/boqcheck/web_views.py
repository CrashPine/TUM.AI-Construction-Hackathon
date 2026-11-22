"""Server-rendered German views for the local review workflow."""

from html import escape

from . import what_if
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
  <label for="lv">Leistungsverzeichnis als PDF oder GAEB X83, D83, D84, D86 oder XLSX</label>
  <input id="lv" type="file" accept=".pdf,.x83,.d83,.d84,.d86,.xlsx,application/pdf" required>
  <label for="attachment">Anlage zum LV (DOCX, optional)</label>
  <input id="attachment" type="file" accept=".docx">
  <p class="badge">XLSX-Kopfzeile: OZ, Kurztext, Menge, ME.</p>
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
  const suffix = file.name.split('.').pop().toLowerCase();
  const types = {pdf: 'application/pdf', x83: 'application/xml'};
  const type = types[suffix] || 'application/octet-stream';
  const status = document.querySelector('#progress');
  const button = form.querySelector('button');
  button.disabled = true;
  const started = Date.now();
  let stage = model?.checked && !model.disabled
    ? 'Datei und lokales Modell werden geprüft'
    : 'Datei wird geprüft';
  const updateStatus = () => {
    status.textContent = stage + ' … ' + Math.floor((Date.now() - started) / 1000) + ' s';
  };
  updateStatus();
  const timer = setInterval(updateStatus, 1000);
  try {
    const query = new URLSearchParams({name: file.name});
    const trade = document.querySelector('#history-trade')?.value.trim();
    if (trade) query.set('trade', trade);
    if (model?.checked && !model.disabled) query.set('semantic', '1');
    const response = await fetch('/upload?' + query, {
      method: 'POST', headers: {'Content-Type': type}, body: file
    });
    if (!response.ok) throw new Error(await response.text());
    const attachment = document.querySelector('#attachment').files[0];
    if (attachment) {
      stage = 'Anlage wird geprüft';
      updateStatus();
      const params = new URLSearchParams({name: attachment.name});
      const added = await fetch(response.url + '/attachment?' + params, {
        method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: attachment
      });
      if (!added.ok) {
        status.textContent = 'Anlage: ' + await added.text() + ' ';
        const link = document.createElement('a');
        link.href = response.url;
        link.textContent = 'LV-Prüfung öffnen';
        status.append(link);
        button.disabled = false;
        return;
      }
    }
    location.assign(response.url);
  } catch (error) {
    status.textContent = 'Prüfung fehlgeschlagen. ' + error.message;
    button.disabled = false;
  } finally {
    clearInterval(timer);
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
        '<p class="badge">Die Modellprüfung kann mehrere Minuten dauern. Der Bericht '
        "zeigt, welche Vergleiche abgeschlossen wurden.</p>"
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
        elif not report and "record" in source:
            ref = f'<a href="#record-{source["record"]}">{ref}</a>'
        elif not report and "docx" in source:
            ref = f'<a href="#docx-{escape(source["docx"])}">{ref}</a>'
        elif not report:
            ref = (
                f'<a href="{base}/pdf#page={source["page"]}" target="_blank" rel="noopener">'
                f"{ref}</a>"
            )
        pieces.append(f"<div>{ref}<blockquote>{escape(source['excerpt'])}</blockquote></div>")
    if "original_word" in finding:
        original = escape(finding["original_word"])
        correction = escape(finding["correction"])
        pieces.append(f"<p>Originalwort: <strong>{original}</strong></p>")
        if report:
            pieces.append(f"<p>Korrekturvorschlag: <strong>{correction}</strong></p>")
        else:
            pieces.append(
                f'<label for="correction-{identifier}">Korrekturvorschlag</label>'
                f'<input id="correction-{identifier}" name="correction-{identifier}" '
                f'value="{correction}" maxlength="120" required>'
            )
    if not report:
        options = "".join(
            f'<option value="{value}"{" selected" if value == status else ""}>{label}</option>'
            for value, label in STATUSES.items()
        )
        pieces.extend(
            [
                f'<label for="status-{identifier}">Prüfstatus</label>',
                f'<select id="status-{identifier}" name="status-{identifier}">{options}</select>',
            ]
        )
        if "original_word" not in finding:
            pieces.append(
                f'<label for="question-{identifier}">Bieterfrage</label>'
                f'<textarea id="question-{identifier}" name="question-{identifier}" rows="3" '
                f'maxlength="2000">{escape(finding["question"])}</textarea>'
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


def _positions(
    items: tuple[Item, ...], legacy: bool = False, references: list[str] | None = None
) -> str:
    """Render the normalized GAEB positions with finding anchors.

    :param items: parsed positions in source order.
    :param legacy: include the two price columns.
    :param references: optional sheet and row labels.
    :returns: an HTML table with quantities, units and both description fields.
    """
    rows = []
    for number, item in enumerate(items, 1):
        description = escape(item.short_text)
        if references:
            description += f"<p>{escape(references[number - 1])}</p>"
        if item.long_text:
            description += (
                f"<details><summary>Langtext</summary><p>{escape(item.long_text)}</p></details>"
            )
        qty = str(item.quantity) if item.quantity is not None else "–"
        prices = (
            "".join(
                f"<td>{v if v is not None else '–'}</td>" for v in (item.unit_price, item.total)
            )
            if legacy
            else ""
        )
        rows.append(
            f'<tr id="position-{number}"><th scope="row">{escape(item.oz) or "–"}</th>'
            f"<td>{description}</td><td>{escape(qty)}</td>"
            f"<td>{escape(item.unit) or '–'}</td>{prices}</tr>"
        )
    return (
        '<h2 id="positions">Positionen</h2><div class="table"><table><thead>'
        "<tr><th>OZ</th><th>Leistung</th><th>Menge</th><th>ME</th>"
        + ("<th>EP</th><th>Gesamtbetrag</th>" if legacy else "")
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


_FIELDS = {
    "quantity": "Menge",
    "scale": "Bezugsgröße",
    "scale_unit": "Bezugseinheit",
    "price": "Einheitspreis",
    "price_basis": "Preisbasis",
    "currency": "Währung",
    "price_type": "Netto/Brutto",
    "market": "Markt",
    "price_period": "Preisstand",
    "project": "Projekt",
    "source": "Quelle",
    "trade": "Gewerk",
    "scope": "Leistungsumfang",
    "unit": "Einheit",
}
_EXCLUSIONS = {
    "current_project": "gleiches Projekt",
    "duplicate": "doppelt",
    "missing_metadata": "ohne Metadaten",
    "different_basis": "andere Vergleichsbasis",
}


def _history_comparison(result: dict, report: bool) -> str:
    """Render historical comparison coverage and evidence.

    :param result: structured review with historical comparisons.
    :param report: whether to omit links to the live position grid.
    :returns: historical comparison HTML.
    """
    if "historical_comparisons" not in result:
        return ""
    parts = ["<h2>Historischer Mengen- und Preisvergleich</h2>"]
    if result["synthetic_history"]:
        parts.append("<p>Synthetische Beispieldaten. Keine Marktpreise.</p>")
    parts.append(
        "<p>Preise nur bei gleicher Währung, Netto/Brutto-Angabe, Markt und Preisstand "
        "verglichen; keine Index- oder Datumsanpassung. Kein Marktpreisangebot.</p>"
    )
    if result.get("history_authorization"):
        parts.append(
            "<p>Nutzungsfreigabe laut Datensatz, nicht geprüft: "
            f"{escape(result['history_authorization'])}</p>"
        )
    if not result["historical_comparisons"]:
        parts.append("<p>Keine eindeutig zugeordneten Positionen.</p>")
    statuses = {
        "anomaly": "Auffällig",
        "within_reference": "Im Referenzbereich",
        "unavailable": "Nicht verfügbar",
        "insufficient_evidence": "Zu wenige Vergleichsprojekte",
    }
    for entry in result["historical_comparisons"]:
        label = f"OZ {escape(entry['oz'])}"
        if not report:
            label = f'<a href="#position-{entry["position"]}">{label}</a>'
        parts.append(f"<h3>{label}</h3>")
        if entry["retrieval"]:
            parts.append(f"<p>{escape(entry['retrieval'])}</p>")
        for key, label in (("quantity", "Menge"), ("unit_price", "Einheitspreis")):
            comparison = entry["results"][key]
            parts.append(f"<p><b>{label}:</b> {statuses[comparison['status']]}</p>")
            if comparison.get("missing"):
                fields = ", ".join(_FIELDS[name] for name in comparison["missing"])
                parts.append(f"<p>Fehlende Angaben: {fields}</p>")
            if comparison.get("excluded"):
                counts = ", ".join(
                    f"{comparison['excluded'][key]} {text}"
                    for key, text in _EXCLUSIONS.items()
                    if key in comparison["excluded"]
                )
                parts.append(f"<p>Ausgeschlossen (Vergleichsstufe): {counts}</p>")
            if "value" not in comparison:
                continue
            basis = escape(" / ".join(comparison["basis"]))
            parts.append(f"<p>Ist: {comparison['value']:.4g} · Vergleichsbasis: {basis}</p>")
            percent = format((comparison["threshold"] * 100).normalize(), "f")
            parts.append(
                f"<p>Vergleichsprojekte: {len(comparison['peers'])} "
                f"(mindestens {comparison['min_projects']}) · Regel: auffällig außerhalb der "
                f"Spanne und ab {percent} % Abweichung vom Median</p>"
            )
            if "median" in comparison:
                parts.append(
                    f"<p>Median: {comparison['median']:.4g} · "
                    f"Spanne: {comparison['low']:.4g}–{comparison['high']:.4g} · "
                    f"Abweichung vom Median: {comparison['deviation']:+.1%}</p>"
                )
            for peer in comparison["peers"]:
                sources = ", ".join(
                    f"{escape(ref)} ({value:.4g})" for ref, value in peer["sources"]
                )
                parts.append(f"<p>{escape(peer['project'])} · {sources}</p>")
    return "".join(parts)


def _number(value: object, row: tuple) -> str:
    """Render one number of a what-if row.

    :param value: the number, or None.
    :param row: quantity, unit price and amount of the row.
    :returns: the number, or which inputs are missing.
    """
    if value is not None:
        return escape(str(value))
    missing = [
        label
        for label, number in zip(what_if.FIELDS.values(), row[:2], strict=True)
        if number is None
    ]
    return "nicht berechenbar: " + escape(", ".join(missing) or "–") + " fehlt"


def what_if_section(
    base: str, positions: tuple[Item, ...], assumption: dict | None, *, form: bool
) -> str:
    """Render one labelled hypothetical calculation and, on the review, its form.

    :param base: internally generated run URL.
    :param positions: parsed positions; they are not changed.
    :param assumption: the current assumption, if any.
    :param form: whether to add the input form.
    :returns: an HTML section.
    """
    parts = ["<section>"]
    if assumption:
        parts.append("<h2>Hypothetische Annahme – keine Quelldaten, kein Marktpreis</h2>")
        number = assumption["position"]
        item = positions[number - 1]
        label = what_if.FIELDS[assumption["field"]]
        parts.append(
            f"<p>Position {number} · {escape(item.oz) or '–'} · {escape(item.short_text)} · "
            f"{escape(item.unit) or '–'} · geändert: {label} = {escape(assumption['value'])}</p>"
        )
        result = what_if.evaluate(item, assumption)
        if "refused" in result:
            parts.append(f"<p>Keine hypothetische Rechnung: {escape(result['refused'])}</p>")
        else:
            original, changed = result["original"], result["hypothetical"]
            rows = "".join(
                f"<tr><th>{title}</th><td>{_number(original[i], original)}</td>"
                f"<td>{_number(changed[i], changed)}</td></tr>"
                for i, title in enumerate(("Menge", "EP", "Betrag (berechnet)"))
            )
            delta = result["delta"]
            stated = "–" if item.total is None else escape(str(item.total))
            parts.append(
                "<p>Rechnung: Menge × EP, kaufmännisch auf Cent gerundet.</p>"
                "<table><tr><th></th><th>Original</th><th>Hypothetisch</th></tr>"
                f"{rows}</table><p>Rechendifferenz (hypothetisch): "
                f"{'nicht berechenbar' if delta is None else delta}</p>"
                f"<p>Angegebener Gesamtbetrag unverändert: {stated}</p>"
            )
    if form:
        current = assumption or {}
        options = "".join(
            f'<option value="{n}"{" selected" * (current.get("position") == n)}>'
            f"{n} · {escape(item.oz) or '–'}</option>"
            for n, item in enumerate(positions, 1)
        )
        fields = "".join(
            f'<option value="{key}"{" selected" * (current.get("field") == key)}>{title}</option>'
            for key, title in what_if.FIELDS.items()
        )
        parts.append(
            "<h2>Was-wäre-wenn-Rechnung</h2>"
            f'<form method="post" action="{escape(base)}/whatif">'
            f'<label>Position <select name="position">{options}</select></label>'
            f'<label>Feld <select name="field">{fields}</select></label>'
            "<label>Hypothetischer Wert (leer entfernt die Annahme) "
            f'<input name="value" inputmode="decimal" value="{escape(current.get("value", ""))}">'
            "</label><button>Annahme berechnen</button></form>"
        )
    return "".join(parts) + "</section>"


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
        spreadsheet = bool(result.get("sheet_references"))
        version = escape(gaeb["version"] or "unbekannt")
        phase = escape(gaeb["phase"] or "unbekannt")
        label = "XLSX (experimentell)" if spreadsheet else f"GAEB {version} · Phase {phase}"
        content.append(
            f'<p class="badge">{label} · {gaeb["items"]} Positionen</p>'
            f"<p>Preisprüfung: {gaeb['arithmetic_checked']} Gesamtbeträge geprüft, "
            f"{gaeb['arithmetic_skipped']} übersprungen.</p>"
        )
        if gaeb["arithmetic_checked"] == gaeb["arithmetic_skipped"] == 0:
            if spreadsheet:
                content.append("<p>Keine Preisangaben.</p>")
            elif version != "90" or phase == "83":
                format_name = "D83" if version == "90" else "X83"
                content.append(f"<p>Keine Preisangaben. Für {format_name} ist das zulässig.</p>")
            else:
                content.append("<p>Keine prüfbaren Preisangaben.</p>")
    else:
        content.append(
            f'<p class="badge">Textebene: {result["text_pages"]} von '
            f"{result['page_count']} Seiten</p>"
        )
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
    content.append(_history_comparison(result, report))
    if not findings:
        content.append("<p>Keine aktiven Befunde.</p>")
    if findings and not report:
        content.append(f'<form method="post" action="{base}">')
    attachment = result.get("attachment")
    if attachment and "attachment_checked" in result:
        content.append(
            f"<p>Automatischer Abgleich LV / DOCX: {result['attachment_checked']} "
            "eindeutig zugeordnete Positionsangaben geprüft.</p>"
        )
        if "position_count" in result:
            content.append(
                f"<p>{len(result['attachment_positions'])} von {result['position_count']} "
                "LV-Positionen mit OZ und Kurztext erkannt.</p>"
            )
        if "attachment_unmatched" in result:
            content.append(
                f"<p>{result['attachment_unmatched']} Positionsüberschriften der Anlage ohne "
                "LV-Position mit gleicher OZ und gleichem Kurztext.</p>"
            )
        if unread := attachment.get("unread"):
            content.append(
                f"<p>{unread} Textblöcke der Anlage nicht bewertet (Inhaltssteuerelemente, "
                "verschachtelte Tabellen oder eingebettete Inhalte); kein vollständiger Abgleich."
                "</p>"
            )
    if review := result.get("attachment_review"):
        content.append(f"<p>{escape(review['summary'])}</p>")
        content.extend(f"<p>{escape(warning)}</p>" for warning in review["warnings"])
    entries = {entry["id"]: entry for entry in attachment["entries"]} if attachment else {}
    if attachment and not report:
        content.append(
            f"<details><summary>Anlage: {escape(attachment['name'])} "
            f"({len(entries)} Textstellen)</summary>"
        )
        for key, entry in entries.items():
            content.append(
                f'<p id="docx-{key}"><b>{key} · {escape(entry["reference"])}</b> '
                f"{escape(entry['text'])}</p>"
            )
        content.append("</details><datalist id='docx-sources'>")
        content.extend(
            f'<option value="{key}">{escape(entry["text"][:80])}</option>'
            for key, entry in entries.items()
        )
        content.append("</datalist>")
    for finding in findings:
        content.append(_finding(base, finding, report, history))
        citation = finding.get("citation", "")
        if citation in entries:
            entry = entries[citation]
            content.append(
                f"<p><b>DOCX-Beleg zu {finding['id']} · {escape(attachment['name'])} · "
                f"{escape(entry['reference'])}</b></p><blockquote>"
                f"{escape(entry['text'])}</blockquote>"
            )
        if entries and not report:
            content.append(
                f"<label>DOCX-Beleg zu {finding['id']} (optional)"
                f'<input name="citation-{finding["id"]}" list="docx-sources" '
                f'value="{escape(citation)}"></label>'
            )
    if findings and not report:
        if history and any(f.get("rule") in RULES | {"semantic"} for f in findings):
            content.append(
                _HISTORY_FIELDS.replace("<!--current-trade-->", escape(result["history_trade"]))
            )
        content.append('<div class="actions"><button>Änderungen speichern</button></div></form>')
    if "positions" in result and (not report or result.get("what_if")):
        content.append(
            what_if_section(base, result["positions"], result.get("what_if"), form=not report)
        )
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
        references = result.get("sheet_references")
        content.append(
            _positions(result["positions"], "records" in result or bool(references), references)
        )
        if records := result.get("records"):
            content.append("<h2>Quelldatensätze</h2>")
            content.extend(
                f'<details id="record-{i}"><summary>Zeile {i} · {escape(label)}</summary>'
                f"<pre>{escape(raw)}</pre></details>"
                for i, label, raw in records
            )
    return _page("Risikobericht" if report else "Befunde prüfen", "".join(content))
