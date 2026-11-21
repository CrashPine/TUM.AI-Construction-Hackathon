"""Server-rendered German views for the local PDF review workflow."""

from html import escape

STATUSES = {"open": "Offen", "confirmed": "Bestätigt", "dismissed": "Verworfen"}

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
@page{size:A4;margin:16mm}
@media print{nav{display:none} :root,article{background:white;color:black}
main{padding:0;max-width:none}article{break-inside:avoid}}
"""

_UPLOAD = """
<form id="upload">
  <label for="pdf">Leistungsverzeichnis als PDF</label>
  <input id="pdf" type="file" accept=".pdf,application/pdf" required>
  <div class="actions"><button>PDF prüfen</button></div>
  <p id="progress" role="status"></p>
</form>
<script>
const form = document.querySelector('#upload');
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = document.querySelector('#pdf').files[0];
  const status = document.querySelector('#progress');
  const button = form.querySelector('button');
  button.disabled = true;
  status.textContent = 'PDF wird geprüft …';
  try {
    const response = await fetch('/upload?name=' + encodeURIComponent(file.name), {
      method: 'POST', headers: {'Content-Type': 'application/pdf'}, body: file
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


def upload_view() -> str:
    """Render the single-PDF upload page.

    :returns: complete upload view.
    """
    return _page("LV prüfen", _UPLOAD)


def _finding(base: str, finding: dict, report: bool) -> str:
    """Render one finding and its evidence links.

    :param base: internally generated run URL.
    :param finding: finding with reviewer status and question.
    :param report: whether the rendering is for export.
    :returns: rendered finding.
    """
    identifier = finding["id"]
    status = finding["review_status"]
    pieces = [
        f'<article id="{identifier}"><h2>{identifier} · {escape(finding["assessment"])}</h2>',
        f'<p class="badge">{escape(finding["method"])} · {STATUSES[status]}</p>',
        f"<p>{escape(finding['explanation'])}</p>",
    ]
    for source in finding["sources"]:
        ref = escape(source["reference"])
        if not report:
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
    pieces.append("</article>")
    return "".join(pieces)


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
        content.append(
            f'<nav><a href="/">Neue Prüfung</a><a href="{base}/pdf">Annotiertes PDF</a>'
            f'<a href="{base}/log">Befundprotokoll</a>'
            f'<a href="{base}/report">Risikobericht</a></nav>'
        )

    content.append(f'<p class="badge">Modellprüfung: {escape(result["semantic_coverage"])}</p>')
    if result["warnings"]:
        content.append(
            "<ul>" + "".join(f"<li>{escape(w)}</li>" for w in result["warnings"]) + "</ul>"
        )
    if not findings:
        content.append("<p>Keine aktiven Befunde.</p>")
    if findings and not report:
        content.append(f'<form method="post" action="{base}">')
    content.extend(_finding(base, finding, report) for finding in findings)
    if findings and not report:
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
    return _page("Risikobericht" if report else "Befunde prüfen", "".join(content))
