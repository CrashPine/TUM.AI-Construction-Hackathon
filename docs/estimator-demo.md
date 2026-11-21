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
