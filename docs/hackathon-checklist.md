# Hackathon delivery checklist

Track the full BidGuard AI implementation prompt here. See [PDF review](pdf-review-checklist.md)
for detailed annotation and Ollama verification.

## First end-to-end demo

- [x] Import text-layer PDFs with original excerpts and page geometry.
- [x] Import both observed X83 XML namespaces and verify fixture counts and representative positions.
- [x] Detect and annotate source-backed discrepancies in the roof and shaft PDFs.
- [x] Export the annotated PDF and a standalone Markdown findings log.
- [x] Connect optional local Ollama and validate its evidence against source text.
- [ ] **Next: Local web flow.** Upload one PDF, display both evidence passages, confirm or dismiss
  a finding, edit its German Bieterfrage, and export a print-ready HTML risk report. Verify with
  the roof LV and the model disabled. Keep the existing annotated PDF and log available.
- [ ] Extend X83 metadata and warnings, explicitly reject DTDs and entities, and finish price-field
  handling including missing versus zero and unit-price basis.
- [ ] Add structural checks for duplicate OZ, invalid numeric values and required fields. Verify
  deterministic arithmetic on priced positions with a known price basis. Empty X83 prices are normal.
- [ ] Prepare the 90-second estimator demo after the web flow works.

## Additional analysis and formats

- [ ] Detect ambiguous or potentially unpriced scope with evidence and a German Bieterfrage.
- [ ] Persist confirmed issues in SQLite and replay deduplicated historical patterns with coverage.
- [ ] Check German spelling with a dictionary and trade lexicon.
- [ ] Evaluate model-proposed formulas through typed expressions and Decimal.
- [ ] Add GAEB 90 D84, D83 and D86, then supporting DOCX and mapped XLSX imports with evidence.
- [ ] Check historical quantity and unit-price anomalies using comparable records and explicit units.
- [ ] Add the separate legal retrieval demo after the core workflow.
