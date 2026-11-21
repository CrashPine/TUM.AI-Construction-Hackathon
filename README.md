# AI Estimation and Bidding Assistant for Bills of Quantities

Team repository for **Challenge A: AI-Powered Cost Estimation and BoQ Analysis** at the TUM.AI
Construction Hackathon.

We build a prototype that reads long bills of quantities (BoQs; German *Leistungsverzeichnis*, LV),
finds errors and risks in them and gives the estimator a risk report before the bid.

**Status (2026-11-21):** the Python package `boqcheck` reads GAEB DA XML files (`.X83`) into a
BoQ data model. Checks, the risk report and the upload page do not exist yet.
[AGENTS.md](AGENTS.md) has the commands and the rules for coding agents.

## Local PDF contradiction review

The PDF checks also flag explicitly open specifications and compensation terms when the
surrounding LV does not resolve them. Findings include the relevant OZ and a German
Bieterfrage. A missing separate line item does not trigger this check.

Start the web prototype without a model:

```powershell
uv sync --locked
uv run python -m boqcheck.web
```

Open `http://127.0.0.1:8000` and upload `data/raw/LV_09_Porenbetondach.pdf`. The PDF review shows
both excerpts and links to the annotated source. Set the review status, edit the Bieterfrage, and
save the changes before opening the risk report. The report includes a standalone HTML download
and a print action which opens the browser's Save as PDF dialog.

The same upload form accepts GAEB X83 (3.1 or 3.2). It shows normalized positions, structural
findings and price-check coverage and exports the shared HTML report. GAEB 90 uploads
(D83, D84 and D86) use the same review and export. Price findings cite physical lines in
the uploaded file. A price-only D84 displays the supplied prices and reports missing
quantities. An optional DOCX attachment belongs to the uploaded LV. Open its source list,
select a paragraph or table cell for a finding, and save the review to include that excerpt
in the HTML report. For PDFs, an attached DOCX also supports automatic comparison of explicitly labelled fields.
Use the same OZ and component title, followed by a property such as a thickness in the next
paragraph. The web review and HTML export show the matched sources. Other excerpts can be cited manually. XLSX uses exact first-row headers `OZ`, `Kurztext`, `Menge`, `ME`. Optional price columns are
`EP`, `Preisbasis` and `Gesamtbetrag`. Store OZ as text to preserve leading zeros. Use values
in the numeric columns, as formulas are reported as unreadable numeric fields. Unmapped sheets
are reported and skipped. Findings cite the original sheet and row.

To make local Ollama available for PDF uploads, start the server with:

```powershell
uv run python -m boqcheck.web --endpoint http://127.0.0.1:44445/api/chat --model bonsai-2:27b --timeout 180
```

Select the model checkbox on a PDF upload to use it for that run. Without the checkbox the
existing rules run on their own. The report records model coverage or unavailability.
The web server defaults to six model comparisons per upload (override with `--max-requests`).
Add `--spelling` to the web or PDF CLI command to check German spelling within the same model
budget. To recognize additional trade terms and brands, add `--lexicon PATH` with a UTF-8 list
containing one accepted word per line. A proposal appears only if its original token is found in
the cited source and a nearby replacement is supported by the local dictionary or lexicon.
The reviewer can edit the replacement before exporting the risk report. The source PDF text
remains intact.

Review state and generated files are available for the lifetime of the local server. Download
the report, annotated PDF or log before stopping it. To retain a confirmed PDF rule case,
select its history checkbox and enter a reviewer identifier before saving. Confirmed cases
promoted this way persist in `bidguard-history.sqlite3` (override with `--history-db PATH`).
The next upload reports coverage for saved drawing-scope and aggregate-limit rules.
Enter the trade on upload to restrict historical matches to cases tagged with that trade and
untagged cases. With the field blank, all saved rules are considered. Position cues are checked
against extracted PDF text, and the report explains skipped or inconclusive historical rules.
To promote a confirmed model finding, also enter a reusable conflict condition and comma-separated
search phrases. On a new PDF upload with the model enabled, historical conditions use up to half
the comparison budget (rounded up). A replay finding must cite excerpts from the new PDF.
The report shows conditions that were deferred when the budget ran out.
Save any edits and choose **Historische Prüfung fortsetzen** to run the next batch. Deferred
reviews retain the original PDF, completed comparisons, edits and latest exports in SQLite.
Keep the private review URL to reopen it after restarting the server with the same history
database and model. The database contains those documents and should stay local.

### Command-line review

```powershell
uv sync --locked
uv run python -m boqcheck.review_pdf "data/raw/LV_09_Porenbetondach.pdf" "runs/roof-review"
```

Use a new output directory for each run. The command prints a JSON manifest with the status,
candidate count, coverage warnings and paths to the annotated source PDF and Markdown log.
Agent integrations can call `boqcheck.review_pdf.review_pdf(filename, pdf_bytes, output)` directly.

The baseline checks forward references in drawing positions and differing maximum aggregate
sizes for Schachtvierungen. Review the resulting candidates before using the proposed
Bieterfragen. Textless pages are reported as skipped. See the
[PDF review architecture](docs/pdf-contradiction-review.md) for the data flow and the
[PDF review checklist](docs/pdf-review-checklist.md) for completed checks and open work.


### Semantic review with Ollama

```powershell
uv run python -m boqcheck.review_pdf "input.pdf" "runs/model-review" `
  --endpoint http://127.0.0.1:44445/api/chat --model "bonsai-2:27b" --timeout 180
```

Agent callers can pass `semantic=SemanticConfig(endpoint, model)` to `review_pdf`.
The tool submits text excerpts to the configured loopback model. The native Ollama endpoint
uses JSON output with thinking disabled. Existing OpenAI-compatible loopback chat URLs are also
supported.

The comparison budget defaults to 24 requests and can be adjusted with `--max-requests`.
When related windows share uncommon terms, an OZ or an explicit reference to an OZ, the tool
reserves up to half the requests for those pairs. It spreads the remaining local checks across
the document when the budget cannot cover every window.
The log reports completed comparisons and which physical PDF pages supplied all, some, or none
of their extracted lines. It preserves deterministic findings when the model is unavailable.

## GAEB X83 validation

```powershell
uv run python -m boqcheck.gaeb_checks "data/raw/GAEB-[PROJEKT_004].X83"
```

The JSON report lists importer warnings and position findings with their OZ and item number.
An X83 without prices is valid for this check. If a file explicitly supplies `UP`, `PriceBasis`
and `IT` as item extensions, the checker compares the rounded total for standard unit-priced
items with a known quantity and unit. It skips totals with missing operands or explicit discounts.
The official X83 and X84 schemas are available from
[GAEB](https://www.gaeb.de/de/service/downloads/gaeb-datenaustausch/).

## Challenge

**Problem.** Bills of quantities often contain thousands of line items, multiple cost groups and
cross-trade dependencies. Companies lack the time and staff to review them in detail, identify risks
and learn from past projects. Typos, calculation errors and overlooked change-order potential can
have major financial consequences.

**Objective.** A prototype for intelligent BoQ analysis:

- Import and parse long BoQs (PDF, GAEB, Excel).
- **Error detection (priority):** missing items, unclear descriptions, contradictions, typos.
- Risk assessment: flag imprecise scope descriptions and unusual quantities.
- Detect change-order potential and likely disputes during execution.
- Optional: suggest unit prices or markups from historical project data.

**Milestones:**

1. BoQ parsing and structured data extraction
2. Error detection and plausibility checks
3. Risk scoring and change-order detection
4. Integration of historical project data (optional)
5. What-if analyses (material prices, alternatives)

**Deliverables:**

- A demo of a web app or assistant tool with upload and risk report.
- A pitch from an estimator's perspective: how does the prototype change the bidding process?

## Data

[`data/raw/`](data/raw/) holds the 44 files that the organizers shared (25 MB, German, anonymized),
unchanged. [`data/README.md`](data/README.md) describes each file and which files hold the same BoQ.

| Format | Files | Content |
|---|---:|---|
| GAEB DA XML (`.X83`) | 4 | bid requests (phase 83): sections, items, quantities, units, short and long texts; no prices |
| GAEB 90 (`.D83`, `.D84`, `.D86`) | 5 | fixed-width BoQ files: 1 bid request (83), 2 bids (84), 2 contract awards (86); the 84 and 86 files have prices |
| PDF | 34 | 27 trade BoQs of one building project (`LV_00` to `LV_23`), 2 BoQs with prices, 5 other BoQs and tender packages without prices |
| DOCX | 1 | 40 BoQ positions grouped by work package |

The brief also names Excel BoQs, historical project data (planned vs. actual costs, change orders),
unit price catalogs and real examples of faulty BoQ items. On 2026-11-21 the shared folder had none
of these as separate files.

## Repository layout

| Path | Content |
|---|---|
| `AGENTS.md` | instructions for coding agents: rules and notes on the file formats |
| `README.md` | this overview |
| `data/README.md` | data inventory |
| `data/raw/` | the organizers' files, read-only |
| `src/boqcheck/` | Python package: BoQ data model and parsers |
| `tests/` | pytest tests |
| `docs/research/` | research reports: [BoQ error checks and price sources](docs/research/2026-11-21-boq-errors-and-pricing.md) |
| `pyproject.toml`, `uv.lock` | project settings and locked dev tool versions |

## How we work

- Branch from `main` (`feature/`, `fix/`, `docs/`, `chore/`, `data/`) and open a pull request.
- Keep pull requests small (about 400 changed lines). Commit each finished functionality with its tests.
- The repository is public. Never commit API keys, tokens or `.env` files.

[AGENTS.md](AGENTS.md) has the full rules.

## Glossary

Short explanations from general domain knowledge, not checked against a source. Check a term
before you build an error rule on it. Only the phase meanings were compared with the data.

| German term | Meaning |
|---|---|
| LV, Leistungsverzeichnis | bill of quantities (BoQ) |
| OZ, Ordnungszahl | item number, hierarchical (for example `01.02.0030`) |
| Los, Titel, Bereich | levels of the BoQ structure; a Los (lot) can be awarded on its own |
| Position | line item |
| Kurztext, Langtext | short description, full description |
| Menge, ME (Mengeneinheit) | quantity, unit: `m`, `m²`, `m³`, `St` (piece), `psch` (lump sum), `Mt` (month) |
| EP (Einheitspreis), GP (Gesamtpreis, Gesamtbetrag) | unit price, line total: GP = Menge × EP |
| Pauschal (psch) | lump sum |
| Bedarfsposition, Eventualposition | provisional item: paid only if the client orders it |
| Wahlposition, Alternativposition | alternative item: priced instead of a base item (Grundposition) |
| Zulage | surcharge item on top of another item |
| Vorbemerkungen | preliminary notes that apply to many items |
| Nachtrag | change order: extra payment for changed or additional work |
| Aufmaß | measurement of the work done |
| Anfrage, Angebot, Auftrag | request for bids, bid, contract award |
| VOB/A, VOB/B, VOB/C | German construction rules: award procedure, contract terms, technical standards (ATV, DIN 18299 ff.) |
| VHB Bayern | standard tender forms of Bavarian public construction; forms 211 and 214.H appear in two PDFs |
| STLB-Bau | standard text library for BoQ items |
| GAEB | German standard for BoQ data exchange; formats include GAEB 90 (fixed-width text) and GAEB DA XML |
| Phase 83, 84, 86 | GAEB exchange phase: bid request, bid, contract award |

## Historical comparison demo

Run `uv run python -m boqcheck.web --historical-dataset history.json` and upload
the XLSX named in the dataset. The JSON has `filename`, `sha256` (of the exact
XLSX bytes), `synthetic`, `current` (object keyed by OZ), and `peers` (array).
Each observation requires `project`, `source`, `trade`, `scope`, and `unit`.
Pass `scale` and `scale_unit` for quantity comparisons, and `currency`,
`price_type`, `market`, and `price_period` for price comparisons. Peer rows
also supply `quantity`, `price` and `price_basis` as applicable. The current
quantity, price and price basis come from the XLSX. The web report requires
three distinct comparable projects for a reference range. See
`test_historical_comparison_export` in `tests/test_web.py` for a synthetic example.