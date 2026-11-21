# Hackathon delivery checklist

Track `BidGuard-AI-hackathon-prompt` in its delivery order and the numbered ideas in
`APPROACH.jpg`. See [PDF review](pdf-review-checklist.md) for detailed annotation and Ollama
verification.

## First end-to-end demo

- [x] Import text-layer PDFs with original excerpts and page geometry.
- [x] Import both observed X83 XML namespaces and verify fixture counts and representative positions.
- [x] Detect and annotate source-backed discrepancies in the roof and shaft PDFs.
- [x] Export the annotated PDF and a standalone Markdown findings log.
- [x] Connect optional local Ollama and validate its evidence against source text.
- [x] **Local web flow.** Upload one PDF, display both evidence passages, confirm or dismiss
  a finding, edit its German Bieterfrage, and export a print-ready HTML risk report. Verify with
  the roof LV and the model disabled. Keep the existing annotated PDF and log available.
- [x] Upload either supported X83 edition through the local web flow with no model configured.
  Display normalized positions, import warnings and price-check coverage. Export structural
  findings in the shared HTML risk report. Verified on the 296-item and 50-item X83 fixtures.
- [x] Surface finding category, evidence strength and potential impact as explicit report fields.
- [x] **X83 import and validation.** Extend metadata and warnings, explicitly reject DTDs
  and entities, and finish price-field
  handling including missing versus zero and unit-price basis.
- [x] Add structural checks for duplicate OZ, invalid numeric values and required fields. Verify
  deterministic arithmetic on priced positions with a known price basis. Empty X83 prices are normal.
  The four real X83 samples are unpriced. Arithmetic was verified with explicit fields in synthetic
  XML. Priced GAEB phase adapters remain open.
- [x] Prepare the [90-second estimator demo](estimator-demo.md) on the real roof LV.
- [x] Walk through the demo for PDF with DOCX attachment, X83, D86 and synthetic XLSX in one
  acceptance test: status and Bieterfrage survive a reload, source links resolve, and the PDF
  shows its text-layer coverage. Verified with no model configured; see the
  [limitations](estimator-demo.md#acceptance-walk-through).

## Additional analysis and formats

- [x] Expose optional local model configuration on the web workflow. PDF uploads opt in per run;
  the report shows coverage and the rule-only result remains available on model failure.
- [x] Persist explicitly promoted, confirmed PDF rule cases in SQLite with source evidence and
  reviewer provenance. Deduplicate patterns and repeated promotions. Show empty-history coverage
  and match saved PDF rules against new uploads in stable priority order.
- [x] Filter existing historical PDF rules by an optional trade and by the position and component
  cues used by each rule. Show why a rule is inapplicable or inconclusive.
- [x] Promote confirmed model findings to reusable conditions with reviewer-supplied search
  terms. Replay applicable templates using grounded evidence in the new PDF and show when the
  model is unavailable or the comparison budget is exhausted. Verified through two independent
  synthetic uploads with a simulated model response.
- [x] Persist completed historical batches and resume deferred templates on the same PDF without
  redoing finished model calls. Verify recovery after restart and preservation of review edits.
- [x] Flag explicitly open PDF specifications and compensation terms with source evidence,
  pricing impact and a German Bieterfrage. Check matching adjacent positions and applicable
  general clauses. Verify that included work does not become a missing-scope finding.
- [x] Compare labelled PDF and DOCX specifications with matching OZ and component title. Verify clarification, discrepancy, equivalent units and a different component in the HTML report.
- [ ] Extend attachment analysis to ambiguous free text, additional layouts and GAEB source positions.
- [x] Check proposed German PDF typos against the local dictionary and project lexicon.
  Validate the exact source token, retain the original, and export reviewer edits in the report.
- [x] Add optional token-only online attestation and provenance caching for unresolved words.
  Off by default. Only approved single words are sent, after unanimous answers from all
  services, and warnings report counts only. The letters-only filter does not guarantee
  confidentiality: the approved word list is the control.
- [x] Evaluate model-proposed PDF line-price formulas for adjacent labelled quantity, explicit
  unit-price basis and stated total in one OZ. Ground operands in source lines, round to cents
  and report checked versus unresolved labelled totals.
- [x] Recalculate aligned EUR EP/GP table rows without a model. Verified 274 rows in the priced D84 companion PDF and detected a one-cent change in memory.
- [x] Recalculate the second priced PDF layout with a separate unit column and carry-over positions. Verified all 248 recognised items in Abgabe LV.pdf and a one-cent change across a page break.
- [x] Reconcile source-backed section subtotals in both priced PDFs (14 explicit section totals and 23 keyed summary rows). Count unresolved optional membership as unchecked. Test explicit inclusion, exclusion and a one-cent error.
- [x] Convert compatible units in labelled PDF price formulas. Verify metres against a price per 100 centimetres and reject incompatible dimensions.
- [x] Give every PDF number a role (input, derived, identifier, specification, unknown) with an exact
  source ID, and accept model price formulas only as allowlisted add/sub/mul/div trees over the group's
  token IDs that are dimensionally consistent and equal quantity × price / basis. Report unchecked values.
- [x] Reconcile the summary hierarchy and tax totals in both priced PDFs (12 checks in Abgabe LV.pdf,
  43 in Angebot AN24-0305.pdf: copies, area and grand totals, net, VAT, gross and carry-overs).
  Abstain on missing or duplicated cells and detect a one-cent change.
- [ ] Extend PDF arithmetic to table and subtotal layouts beyond the two priced samples.
- [x] Import GAEB 90 D84, D83 and D86 through the parser. Fixture tests cover counts, prices and OZs.
- [x] Connect D83, D84 and D86 to the web review and HTML export. Verify all five uploads,
  missing quantities in the price-only D84 and a changed price with original record evidence.
- [x] Link duplicate OZ occurrences and GAEB 90 price calculations to effective physical records;
  show uncheckable sums and skipped positions. Warn that position types and price bases are not
  fully recognized and that price checks assume one quantity unit per unit price.
- [x] Import DOCX body paragraphs and top-level table cells in order with source anchors.
  Checked the supplied 53 nonempty paragraphs; styled headings and cells use a synthetic fixture.
- [x] Attach a DOCX to a specific LV, select a source for a finding and export the excerpt
  with its filename and paragraph or cell reference. Verify upload isolation and retry.
- [x] Add mapped XLSX import with worksheet and row evidence. Verified via synthetic workbook upload and HTML export.
- [x] Label unsupported upload formats in the UI until their adapters pass fixture checks.
- [x] Calculate historical quantity and price anomalies from explicit comparison metadata and sourced peers. Verified both on synthetic data.
- [x] Load a mapped local historical dataset and export quantity and price findings, peer sources and insufficient-evidence coverage. Verified on synthetic XLSX.
- [x] Optionally filter metadata-compatible positions by local Ollama embeddings. Verified with synthetic vectors and an unavailable service.
- [x] Import historical XLSX rows through an explicit local manifest, with workbook, sheet and row evidence.
- [x] Shortlist projects by supplied summaries using local embeddings before matching positions.
- [x] Report retrieval provenance per comparison: model, threshold, counts, metadata-gated
  peers, unprofiled projects and the failure reason. Verified with synthetic vectors and mocked
  HTTP errors only; model quality is not established by these tests.
- [x] Smoke-test both retrieval stages with real GAEB text and local nomic-embed-text:v1.5.
  Project summaries built from up to 1,000 characters of section titles scored 0.969 for two
  editions of the same LV and 0.708/0.712 for two other files. For six X83 queries against the
  first twelve D86 descriptions of the same LV, all six matching positions passed both
  0.75 and 0.90. The thresholds also admitted nine and three additional selections respectively.
- [x] Validate historical records: net/gross price type, declared usage authorization for
  non-synthetic data, one record per project and source, missing-field and exclusion counts in
  the report. Verified on synthetic data.
- [x] Configure the anomaly rule per dataset (`min_projects`, `deviation_threshold`) and show
  the rule, peer count, deviation from the median and peer sources in the report. Verified with
  a labelled synthetic anomaly, a normal control, another scale basis and a missing scale.
- [x] Compare prices only on the same trade, scope, unit, currency, net/gross type, market and
  price period, normalized per price basis, without index or date adjustment. Verified on
  synthetic data: each basis field and the normalization are needed (8 of 8 field-drop mutants
  fail the test; the earlier tests missed 3).
- [ ] Evaluate independent projects with reviewer-labelled comparable positions. Same-LV
  editions validate retrieval only and do not count as independent quantity or price peers.
- [x] Freeze an offline acceptance baseline: exact rule findings for all 43 supported samples,
  partial results for unavailable, invalid or incomplete model output, and an opt-in real-model
  tier. Verified that a changed anchor and a valid fake response fail.
- [ ] Add the separate legal retrieval demo after the core workflow.
  Blocked: no authorized legal corpus.
- [x] Add one explicit, labelled what-if calculation (quantity or unit price) per GAEB or
  XLSX review without changing source data. Verified with the real D84 sample, invalid
  inputs, refusals and rounding; 13 of 13 controlled mutants fail the tests.
