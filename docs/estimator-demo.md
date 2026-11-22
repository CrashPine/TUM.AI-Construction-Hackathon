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
save, attach the real `LV-Positionen.docx`, reload the review and open the report. The
confirmed status and the question must appear on the reloaded review and in the report, and
the source links must point to the expected PDF page, position or GAEB 90 record.

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

## Explicit what-if calculation

A GAEB or XLSX review has a **Was-wäre-wenn-Rechnung** form. Choose a position, the
field (Menge or EP) and a hypothetical value; an empty value removes the assumption.
The review and the report then show the original and the hypothetical quantity, unit price
and amount (Menge × EP, rounded half up to the cent), and the difference. The section is
labelled as a hypothetical assumption with no source data and no market price. The stated
total of the position is shown unchanged. The parsed positions, findings and the annotated
PDF are not changed.

Limitations:

- One assumption per review. It is kept only in memory and is not saved to the history
  database, so it is lost on a restart.
- There is no calculation for lump-sum items (Pauschal), positions with an adjusted total
  or a price basis other than 1; the section says why.
- PDF reviews have no parsed positions and no what-if form.

## DOCX attachment to a GAEB review

A DOCX attached to an X83 or GAEB 90 review is compared with the parsed positions. The
Kurztext of a position is its component. Its Langtext is read with the same statement reader
as the PDF positions (see below). A value is compared only if the DOCX has a heading with the
same OZ and the same Kurztext and each document states the field once. OZ levels are compared
as numbers, so `3.1.4` matches `03.01.0004`; the
PDF comparison uses the same rule. An index letter must be identical, and a two-level OZ needs
the prefix `OZ` (`OZ 2.9`). Case and spacing of the Kurztext do not count. The LV source of a
finding links to the position row. The review and the report show how many values were compared
and how many DOCX headings have no position with the same OZ and Kurztext. The experimental XLSX
review uses the same comparison; its rows have no Langtext, so it compares no values.

The reader looks for the fields Dicke, Schichtdicke, Oberflächengüte, Oberflächenqualität and
Lieferverantwortung in the LV lines of a position and in all paragraphs of a DOCX block: the
heading and the paragraphs after it, up to the next heading or table. A line that ends with a
field label (`Dicke:`) and a next line that starts with the value, also after a qualifier, give
one statement, and the excerpt shows both lines. A line with parts separated by `;`, for
example `Farbe: rot; Dicke: 2 mm`, gives one statement for each part. Each statement is one of
these:

- exact: the label and a supported value only (`Dicke: 20 cm`).
- open: `offen` or a similar word. Open values work as before.
- ambiguous: a qualifier such as `ca.`, `mind.`, `max.`, `bis`, `über` or `>`, `oder`, a range
  (`10 - 15 cm`), words after the value (`über Rohrscheitel`), an unsupported unit, or a field
  named in free text or in a compound label (`Wanddicke`).

If a document has an ambiguous statement for a field that both documents state for a position,
there is no finding. The review and the report count and list the pair as **nicht automatisch
verglichen (mehrdeutige Angabe)**, with all excerpts; in the review, the sources are links. If
the model comparison cites a line with one of these markers, a conflict becomes a scope check.

In the 44 samples, the reader finds 15 exact statements (12 GAEB, 3 PDF), 261 ambiguous
statements (141 GAEB, 120 PDF) and no open value. The old reader found 12 exact values (11 GAEB,
1 PDF) and skipped 3 unsupported GAEB values. 10 fields (7 GAEB, 3 PDF) have one exact
statement in their position and can be compared; before, 11 fields (10 GAEB, 1 PDF) could.

Limitations:

- No fuzzy matching: a heading that shortens or rewords the Kurztext matches no position.
- GAEB 90 keeps no physical record for a Langtext line (Satz 26), so the source names the
  position, not a record line.
- The local model can be selected only for PDF uploads, so a GAEB review shows that the model
  comparison did not run. The model comparison accepts GAEB positions; it is tested with a
  mocked model only.
- An open Langtext value (`Dicke: offen`) that the DOCX fills counts as compared but gives no
  finding, because GAEB reviews have no open-scope finding.
- The tests combine real GAEB samples with small synthetic DOCX files; there is no real DOCX
  for a GAEB sample.
- A free-text mention counts as a statement. In 4 GAEB positions (2 positions of one BoQ in
  2 files), a range in free text stops the comparison of an exact Schichtdicke; the pair is
  listed instead.
- `bis`, `über` and `oder` also occur in text that does not qualify the value. A model
  conflict that cites such a line becomes a scope check.
- A compound label (`Wanddicke: 25 cm`) is only listed, never compared. A statement that
  continues on the next line without a label and colon cites only its first line.

## DOCX attachment to a PDF review

A DOCX attached to a PDF review is compared with the PDF positions whose first row states
the component. Two layouts are read:

- One line `OZ Component`, as in the synthetic test PDFs.
- The OZ in its own cell and the Kurztext in the next cell of the same row, as in the sample
  LV PDFs. The Kurztext is the component.

The match rules are those of the GAEB comparison. In both reviews, a DOCX heading can end
with the unit in brackets, for example `1.1.20 – Baustelleneinrichtung vorhalten [Mt.]`. The
unit is not part of the Kurztext for the match, and excerpts keep the full paragraph. A
placeholder in brackets, such as `[FIRMA_096]`, is not a unit. The PDF review and the report
show how many positions with an OZ have a recognized Kurztext and how many DOCX headings have
no position with the same OZ and Kurztext.

The 25 sample PDFs with OZs have 970 positions; 792 are read. With the real
`LV-Positionen.docx` and `Leistungsverzeichnis.pdf`, 209 of 274 positions are read and 16 of
the 40 headings match. Of the other 24 headings, 16 name a read position with another Kurztext
and 8 name a position that is not read. The DOCX has no labelled values, so no value is
compared or listed. The source BoQ of the DOCX is not confirmed.

Limitations:

- If the cell next to the OZ holds the position type (`*** Bedarfsposition ohne GB` or
  `mit GB`), the position is not read (100 positions in the samples).
- If the line after the OZ cell is on a lower row, the position is not read (78 positions in
  the samples). In 77 of them, the first Kurztext line extracts before the OZ cell, at the end
  of the previous position, as when a Kurztext wraps. The previous position then has one line
  too many, also in the model comparison.
- Only the Kurztext line on the OZ row is read. A Kurztext that continued on the next row
  would be cut there and match no heading.
- The unit is not compared, and there is no fuzzy matching.
- If a Kurztext itself ends with a word in brackets, for example `[PE]`, the DOCX heading
  loses that word and matches no position. No Kurztext in the samples ends so.
- The model comparison of PDF positions is tested with a mocked model only. The statement reader
  is tested with real PDF and GAEB samples, but only with synthetic DOCX files.
