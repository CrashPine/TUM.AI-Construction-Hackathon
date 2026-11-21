# Roof tender review in 90 seconds

Run `uv run python -m boqcheck.web` and open `http://127.0.0.1:8000`. Have
`data/raw/LV_09_Porenbetondach.pdf` ready in the file picker. This demo runs locally
with the built-in rules. For a public recording, crop the screen to the finding
and the two relevant phrases.

| Time | On screen | What to say |
| --- | --- | --- |
| 0–15 s | Upload the four-page roof LV. | “Before I price the roof, I need to know which building elements the client expects me to include.” |
| 15–40 s | Open the scope finding, then its page link. On PDF page 1, show the yellow passages at OZ 9.2.3 and 9.2.4. Open the annotation comment. | “One passage says *Porenbetonfassade*. The other specifies *Porenbeton-Dachplatten*. These are different elements. I can see the source wording and decide whether it needs clarification.” |
| 40–65 s | Return to the review, select **Bestätigt**, edit the Bieterfrage and click **Änderungen speichern**. | “I would ask the client: *Ist die Porenbetonfassade zusätzlich zu den Dachplatten anzubieten? Falls ja, unter welcher Position ist sie zu kalkulieren?*” |
| 65–90 s | Open **Risikobericht**, show the saved question and **Drucken / Als PDF speichern**. Return to the review to show **Annotiertes PDF** and **Befundprotokoll**. | “The estimator has a question ready to send before bidding. A colleague can review the marked original alongside the findings log.” |

For rehearsal, the web tests exercise the actual roof upload, question edit and
report export. The X83 and scope tests cover two controls: an unpriced request can
legitimately have empty prices, and explicitly included work should not trigger
a missing-scope finding.

## Acceptance walk-through

`test_acceptance_walkthrough` in `tests/test_web.py` replays the demo for each supported
format with no model configured: upload, confirm the first finding, write its Bieterfrage,
save, reload the review and open the report. The confirmed status and the question must
appear on the reloaded review and in the report, and the source links must point to the
expected PDF page, position or GAEB 90 record.

| Upload | What the test checks |
| --- | --- |
| Roof PDF + DOCX attachment | The text-layer badge, page links within the page count, the attached `LV-Positionen.docx` with paragraph references, the confirmed status kept after the attachment and the findings log. |
| `GAEB-[PROJEKT_004].X83` | Positions are listed and the report shows **Keine aktiven Befunde.** |
| `StBALV23040.D86` | Price findings link to their GAEB 90 records. |
| Synthetic XLSX (labelled synthetic, built in the test) | A total mismatch with its sheet and row reference. |

`test_long_pdf_reports_text_layer_and_price_coverage` uploads the 91-page `Abgabe LV.pdf`
and checks the text-layer badge and the price-check coverage.

Limitations:

- No language model runs in this walk-through; model findings are covered separately.
- The four X83 samples are unpriced bid requests, so the X83 case has no findings.
- There is no sample XLSX; the XLSX case uses a synthetic workbook.
- The annotated PDF and the Markdown findings log are written at review time and do not
  include later reviewer edits; the HTML report does.
- The 91-page PDF review took about 1.3 s on one development machine; other machines differ.
