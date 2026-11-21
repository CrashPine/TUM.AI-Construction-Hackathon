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
- [x] Run and manually review the two waterproofing LVs with Ollama. Both outputs preserved the source pages. Neither the model nor the rules returned a candidate.
- [x] Run a model-only control on both shaft LV pages with the known 8 mm versus 15 mm discrepancy. Both clauses were in the first comparison. Ollama completed 3/3 comparisons and returned zero candidates. Keep deterministic checks enabled for the hackathon demo.
- [ ] Verify on a broader set of real PDFs whether the model identifies contradictions beyond the built-in rules. Report missed expected findings and false positives.
- [x] Spread a small model budget across the document and log coverage by physical PDF page. Verified on the 91-page `Abgabe LV.pdf`: three requests covered excerpts near the start, middle and end of the file.
- [x] Prioritize likely cross-page conflicts under a limited budget using shared OZ, explicit references and uncommon terms. In a live two-request run, Ollama found the conflict spanning pages 1 and 7 of the synthetic PDF and exported both annotated passages.
- [ ] Add OCR for scanned PDFs if scanned documents are in scope. The current tool reports textless pages as skipped.

## Waterproofing sample review

Local model: `bonsai-2:27b`. Each run covered both pages and completed every planned comparison.

| Sample | Comparisons | Manual review |
| --- | ---: | --- |
| `LV_15_Abdichtung_Aussenwaende.pdf` | 1/1 | OZ 1.1.20 specifies 14 cm and 140 mm consistently. Client-supplied insulation and contractor installation can both apply. No definite contradiction identified. |
| `LV_15a_Abdichtung_Bodenplatte_Buero.pdf` | 3/3 | OZ 1.1.10 separates drain work into another item. OZ 1.1.15 mentions both drains and PVC pipes. The scope could use clarification, but the component descriptions may apply together. No definite contradiction identified. |

These two runs exercise the zero-findings path on real PDFs. A real-document positive case
detected independently by the model remains open.
