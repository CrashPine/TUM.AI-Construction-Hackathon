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
- [ ] Prepare the 90-second estimator demo after the web flow works.

## Additional analysis and formats

- [ ] Expose optional local model configuration on the web workflow; retain the no-model baseline.
- [x] Persist explicitly promoted, confirmed PDF rule cases in SQLite with source evidence and
  reviewer provenance. Deduplicate patterns and repeated promotions. Show empty-history coverage
  and match saved PDF rules against new uploads in stable priority order.
- [ ] Complete historical replay with applicability based on trade and position attributes,
  reusable patterns for model findings, and resumable batches with deferred coverage.
- [ ] Detect ambiguous or potentially unpriced scope with evidence and a German Bieterfrage.
- [ ] Check German spelling with a dictionary and trade lexicon.
- [ ] Evaluate model-proposed formulas through typed expressions and Decimal.
- [ ] Add GAEB 90 D84, D83 and D86, then supporting DOCX and mapped XLSX imports with evidence.
- [ ] Accept a supporting DOCX in the same LV review after its source anchors are verified.
- [x] Label unsupported upload formats in the UI until their adapters pass fixture checks.
- [ ] Check historical quantity and unit-price anomalies using comparable records and explicit units.
- [ ] Add the separate legal retrieval demo after the core workflow.
