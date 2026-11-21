# AI Estimation and Bidding Assistant for Bills of Quantities

Team repository for **Challenge A: AI-Powered Cost Estimation and BoQ Analysis** at the TUM.AI
Construction Hackathon.

We build a prototype that reads long bills of quantities (BoQs; German *Leistungsverzeichnis*, LV),
finds errors and risks in them and gives the estimator a risk report before the bid.

**Status (2026-11-21):** the Python package `boqcheck` reads GAEB DA XML files (`.X83`) into a
BoQ data model. Checks, the risk report and the upload page do not exist yet.
[AGENTS.md](AGENTS.md) has the commands and the rules for coding agents.

## Local PDF contradiction review

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
findings and price-check coverage and exports the shared HTML report. GAEB 90, DOCX and XLSX
are currently unsupported.

Review state and generated files are available for the lifetime of the local server. Download
the report, annotated PDF or log before stopping it.

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
