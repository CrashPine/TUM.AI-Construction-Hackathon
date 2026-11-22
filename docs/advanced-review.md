# Advanced PUManager review

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

`tests/test_baseline.py` freezes the rule findings for all 43 supported sample files and checks
that an unavailable or malformed model keeps them and the export. To rerun the roof and shaft
cases with a real local model, set `BOQCHECK_BASELINE_ENDPOINT` and `BOQCHECK_BASELINE_MODEL`,
then run `uv run pytest -s tests/test_baseline.py -k local_model`. That tier prints the model
findings for comparison; it does not score them.


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

## Historical comparison demo

Run `uv run python -m boqcheck.web --historical-dataset history.json` and upload
the XLSX named in the dataset. The JSON has `filename`, `sha256` (of the exact
XLSX bytes), `synthetic`, `current` (object keyed by OZ), and `peers` (array).
Each observation requires `project`, `source`, `trade`, `scope`, and `unit`.
Pass `scale` and `scale_unit` for quantity comparisons, and `currency`,
`price_type`, `market`, and `price_period` for price comparisons. Peer rows
also supply `quantity`, `price` and `price_basis` as applicable. The current
quantity, price and price basis come from the XLSX. Quantities are compared
per `scale` and `scale_unit`, prices per `price_basis`. Prices are compared only
with peers of the same trade, scope, unit, currency, `price_type`, market and
`price_period`; they are never indexed or adjusted to another date, and the report
says that the reference is not a market quote. Without a current price or price
basis the price comparison is unavailable. A reference range needs
at least `min_projects` distinct comparable projects (integer of at least 2,
default 3); with fewer the report shows insufficient evidence. A value is
flagged as unusual when it lies outside the peer range and deviates from the
median by at least `deviation_threshold` (positive number, default 0.30). The
report states both settings, the deviation and the peer sources. Embedding
similarity only selects peers; it never decides an anomaly. `price_type` must be
`net` or `gross`. A dataset with `synthetic` false needs a nonempty top-level
`authorization` naming its usage basis; the report shows it as declared, not
verified. Identical rows for the same project and source load once; differing
rows are rejected. For each comparison the report lists missing current fields
and how many peers were excluded as the same project, duplicates, without
metadata or on another basis. See
`test_historical_comparison_export` in `tests/test_web.py` for a synthetic example.
For semantic peer selection, add a top-level `embedding_model` naming an installed
Ollama embedding model and a `description` for each peer. Set `embedding_port`
(default 11434) and `similarity` (default 0.75) if needed. Requests stay on loopback.
Only peers with the same trade, scope and unit enter the similarity search;
the report counts the ones it gated out. Embeddings are computed per report, with
no stored index. Each comparison states its retrieval provenance: model, threshold,
selected/candidate counts, or why retrieval was unavailable (model not installed,
HTTP error, service unreachable, invalid answer). Without `embedding_model` it says
that peers were chosen by metadata only.
Instead of entering peer numbers in JSON, add a top-level `projects` array.
Each entry contains `project` (independent project ID), `workbook` (relative XLSX
path inside the manifest directory), and `positions` (object keyed by historical OZ).
Use `defaults` for common metadata and per-position objects for overrides. Numbers,
units and descriptions come from the workbook. Reports cite the workbook, sheet
and physical row. Inline `peers` may still be supplied independently.
For a project-level shortlist before position matching, set `current_profile`
to a project summary and `project_profiles` to an object mapping historical
project IDs to their summaries. This requires `embedding_model`. Only projects
with a supplied profile can enter the shortlist. The report shows coverage of
both search stages, including how many projects had no profile.