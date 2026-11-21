# PDF contradiction review checklist

- [x] Accept a single text-layer PDF through the agent function and CLI.
- [x] Retain physical page numbers, printed labels where available, OZ and excerpt geometry.
- [x] Export a copy of the PDF with yellow highlights on both source passages.
- [x] Attach reciprocal comments. Place comment markers in free space and use the PDF comments panel when a marker would cover content.
- [x] Export a standalone Markdown log with both excerpts, finding status, detection method, annotation outcome and coverage.
- [x] Connect local Ollama and validate model citations against the source before exporting.
- [x] Verify a real four-page roof LV with Ollama running all six comparisons. The facade-versus-roof candidate came from the built-in rule.
- [x] Verify that the live model detects a synthetic contradiction across two pages and produces highlights and comments on both pages.
- [x] Review the shaft LV excerpt from file pages 2 and 5 (printed 53 and 56). Ollama completed all three comparisons. The exported candidate retained the built-in rule's 8 mm versus 15 mm finding, with reciprocal comments on both pages.
- [x] Run a live negative control where opposite states apply to two different switches. Ollama completed the comparison and the review returned zero findings.
- [ ] Verify on a broader set of real PDFs whether the model identifies contradictions beyond the built-in rules. Report missed expected findings and false positives.
- [ ] Improve review of long PDFs under a request budget. The current log reports any comparisons skipped.
- [ ] Add OCR for scanned PDFs if scanned documents are in scope. The current tool reports textless pages as skipped.
