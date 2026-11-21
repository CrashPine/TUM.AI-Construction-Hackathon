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
- [ ] Extend scope review to ambiguous free text and supporting documents once those are imported.
- [x] Check proposed German PDF typos against the local dictionary and project lexicon.
  Validate the exact source token, retain the original, and export reviewer edits in the report.
- [ ] Add optional token-only online attestation and provenance caching for unresolved words.
- [x] Evaluate model-proposed PDF line-price formulas for adjacent labelled quantity, explicit
  unit-price basis and stated total in one OZ. Ground operands in source lines, round to cents
  and report checked versus unresolved labelled totals.
- [x] Recalculate aligned EUR EP/GP table rows without a model. Verified 274 rows in the priced D84 companion PDF and detected a one-cent change in memory.
- [x] Recalculate the second priced PDF layout with a separate unit column and carry-over positions. Verified all 248 recognised items in Abgabe LV.pdf and a one-cent change across a page break.
- [ ] Extend PDF arithmetic to other table layouts, numerical token roles beyond labelled price fields,
  unit conversions and subtotal membership including optional items.
- [x] Import GAEB 90 D84, D83 and D86 through the parser. Fixture tests cover counts, prices and OZs.
- [ ] Connect GAEB 90 to the web review and add supporting DOCX and mapped XLSX imports with evidence.
- [ ] Accept a supporting DOCX in the same LV review after its source anchors are verified.
- [x] Label unsupported upload formats in the UI until their adapters pass fixture checks.
- [ ] Check historical quantity and unit-price anomalies using comparable records and explicit units.
- [ ] Add the separate legal retrieval demo after the core workflow.
