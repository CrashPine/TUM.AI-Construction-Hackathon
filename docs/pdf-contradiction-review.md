# PUManager PDF contradiction review

## Scope

A local agent tool reviews one German Leistungsverzeichnis (LV) PDF and returns an annotated copy of the uploaded PDF plus a standalone Markdown findings log. This extends the hackathon prompt's original export scope at the user's request. The print-ready risk report and editable German Bieterfragen remain part of the web demo and can consume the same findings. Reuse the existing Python package and GAEB X83 model.

~~~mermaid
flowchart LR
    A[Agent tool or local upload] --> B[PDF extraction and source index]
    B --> C[Candidate retrieval and checks]
    C --> D[Evidence validation]
    D --> E[Annotated copy of source PDF]
    D --> F[Markdown findings log]
~~~

## Components

Proposed paths under `src/boqcheck/`. These interfaces are design targets.

| Module | Responsibility |
| --- | --- |
| `pdf_extract.py` | Extract text and page geometry together. Preserve item boundaries, OZ, general notes, section headings and page continuations. Keep partial extraction warnings. |
| `evidence.py` | Define source spans, finding records and coverage. Keep PDF provenance alongside the existing `BoQ` and `Item` models. |
| `contradictions.py` | Retrieve comparable clauses and run deterministic rules. Allow an optional local semantic checker to propose additional candidates. |
| `pdf_annotate.py` | Add native yellow highlights and linked comments to a copy of the original PDF. Record per-span annotation outcomes. |
| `findings_log.py` | Export each finding and its evidence to a standalone Markdown document. |
| `review_pdf.py` | Coordinate the pipeline. Keep the entry point usable from the agent and the web upload handler. |

Select a PDF backend that can extract word geometry and write native annotation quads and comments in a consistent coordinate system. Evaluate this with a short spike on the roof LV and a rotated synthetic page before committing to a dependency.

## Agent contract

`review_pdf(filename, pdf_bytes) -> ReviewResult` accepts one PDF and returns a run status, artifact handles for `<stem>.annotated.pdf` and `<stem>.contradictions.md`, finding counts by assessment and coverage warnings. The agent adapter resolves uploads and artifact handles locally. Invalid or encrypted PDFs return a structured input error. Zero findings still produces both artifacts and records the checks that ran. Publish the two artifacts as one run after reopening and validating the exported PDF. Use a unique run directory with sanitized filenames. Leave `data/raw/` read-only and process all excerpts locally.

- **Evidence** — immutable source ID, document ID, zero-based PDF page index, optional printed page label, section path, optional OZ, exact excerpt and line quads where available. A normalized search view maps back to the original spans. User-facing file page numbers are one-based.
- **Finding** — stable run-local ID, category, assessment (`conflict` or `needs_scope_check`), at least two source IDs, affected OZ, explanation and possible pricing or execution impact. A German Bieterfrage can be suggested and edited by the reviewer. Review status (`open`, `confirmed`, `dismissed`) is independent of the assessment.
- **Coverage** — pages read and skipped, applicable checks run, unsupported pages, semantic review status and per-source annotation outcome. Produce a partial result if recoverable extraction or placement failures prevent full coverage.

## Conflict detection

Index the Kurztext, Langtext, general notes and cross-references. Retrieve neighboring positions, explicit OZ references and clauses describing the same component across pages and sections. For long LVs, index the entire document first and send only relevant passages to each check. Compare the subject, trade, location, applicability, condition and normalized property before judging compatibility. Account for exceptions, alternatives, optional items and separately scoped components. For example, thickness values can be compared only after mapping each to the relevant part of the assembly.

Start with deterministic checks for incompatible dimensions or material requirements and for scope mismatches in directly related items. Keep uncertain applicability as a candidate for scope review. Deduplicate findings across retrieval paths using the rule and evidence pair. Validate that both source IDs exist and the quoted spans match the original extract. A reference to work included elsewhere is evidence of inclusion. An absent standalone position does not establish a contradiction.

The optional local LLM receives excerpts as untrusted data and returns typed candidates referencing allowed source IDs. Validate those IDs against the supplied context. Allow abstention and retain deterministic results when the model is absent, times out or returns invalid output. Record whether semantic review ran.

## PDF annotations and log

Apply a yellow highlight to each verified excerpt using line-level quads, including wrapped text. On both sides of a pair, the comment names the counterpart file page and OZ, quotes the relevant words and explains the discrepancy in German. Use a shared finding ID in the PDF and the log.

For visible comment markers, find nearby free space using page bounds, text blocks, graphics and already placed annotations. Place a native comment icon there with the full detail in its popup. Where a page has no safe space, attach the comment to the highlight and expose its text in the PDF viewer's comments panel. When geometry cannot be verified, record the file page, printed label and excerpt in the log, plus the reason the highlight could not be placed. Preserve page order, crop, rotation and existing annotations. Reopen the result to verify annotation type, color, target and contents. Render sample pages and inspect readability and alignment.

The Markdown log contains a coverage summary and one entry per finding. Each entry includes the assessment and review state, both excerpts with page and OZ, the explanation, impact, optional Bieterfrage and the annotation outcome for each excerpt. Generate the log from the same validated records as the annotations. Keep tentative findings visibly labeled in both artifacts.

## Delivery and verification

1. **PDF vertical slice without a model.** Implement extraction, indexed evidence, deterministic candidate generation and dual export. Use the four-page roof LV and verify that 9.2.3 and 9.2.4 on file page 1 are presented as a possible roof versus facade scope mismatch. Verify the two visible highlights and reciprocal comments. Runtime rules operate on document content.
2. **Cross-page evidence and layout.** Verify the shaft example at 8 mm and 15 mm on file pages 2 and 5 (printed 53 and 56) as a candidate for scope review. Test the steel-insert inclusion as a negative control. Exercise repeated text, wrapped lines, rotated pages, crowded margins, missing geometry and a zero-finding document. Verify extraction coverage and measure runtime on the 91-page tender PDF.
3. **Local demo and semantic review.** Wire the same tool into a single local upload flow, open both source references, persist reviewer choices and edited Bieterfragen, and export the risk report with the requested PDF and log available for download. Add the optional local model after the deterministic demo works. Compare coverage and findings on the same cases with and without it. Keep OCR, additional input formats and historical RAG on the expanded prototype roadmap.
