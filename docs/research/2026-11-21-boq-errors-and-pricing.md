# BoQ error checks and price sources: research result

Date: 2026-11-21. Topic: Challenge A (risk report for German LVs) and the price questions of the team.
Method: AB-MCTS search tree, 21 web searches, 29 fetched sources (23 used), two SIFT
tournaments with a Bradley-Terry fit. No parliament judges were used.

Status: done. 19 of 26 key claims are checked in their primary text. Section 9 lists the gaps.

> **Warning:** Do not use section 6 as legal advice. Ask a lawyer before you send RFQ emails to
> suppliers that did not agree to receive them.

## 1. Result

1. Build these checks first:
   1. VOB/A rule checks (A2).
   2. Structure and arithmetic checks (A1).
   3. Quantity-change exposure under VOB/B §2 (A6).
   4. A vague-language detector with LLM review (A4).
2. A2, A1 and A6 are in the top four of each leave-one-judge-out fit. Without my own votes,
   cross-item plausibility (A8) takes the fourth place from A4.
3. Get non-public prices with direct price inquiries (RFQ) to suppliers and subcontractors (P5).
   Compare the offers in a Preisspiegel. P5 is first in each leave-one-judge-out fit.
4. Use bidder networks (P6), supplier price files such as DATANORM (P4) and price databases (P2)
   as the next channels. Their order changes between the fits.
5. Get consent before you send RFQ emails. Courts count purchase inquiries as advertising, and
   today's UWG text demands prior express consent for email advertising. A 2008 BGH ruling
   accepted implied consent, but under an older wording. For a phone call to a business,
   presumed consent is enough (section 6).
6. The four sample GAEB XML files do not name RIB iTWO. Their headers name ORCA AVA (two files),
   CaliforniaX and ARCHITEXT Pallas [S22]. The iTWO brochure that I read describes the bidder side:
   estimate, price inquiries and a material Preisspiegel [S9].

## 2. Where the risk check sits

~~~text
 CLIENT SIDE                         BIDDER SIDE (contractor)
 AVA program                         ------------------------------------
 -----------
 LV: GAEB X83 + PDF  --- tender ---> [1] Risk check (this prototype)
                                          | findings: errors, risks
 answers             <--- bidder ---------+
                          questions       | checked LV
                                          v
                                     [2] Estimating system, e.g. RIB iTWO
                                          | price DB, DATANORM files
                                          | RFQ: email or GAEB extract
                                          v
                                     [3] Suppliers, subcontractors (NU)
                                          | offers: GAEB X84, price lists
                                          v
                                     [2] Preisspiegel, chosen prices,
                                          markups, EFB 221/223
 award decision      <--- priced bid -----+
                          (GAEB X84 + forms)
~~~

The RIB brochure names these iTWO functions for the bidder:

- Price inquiries: "Erstellen Sie Preisanfragen direkt aus der Kalkulation heraus." [S9]
  (create price inquiries directly from the estimate).
- Offer comparison: "Wertung der Angebote im Material-Preisspiegel." [S9]
- Interfaces: "Integrationsmöglichkeiten wie Datanorm oder Vergabehandbuch Bund (VHB), GAEB, Dynamische BauDaten" [S9].
- Exchange standard: GAEB XML 3.3 [S9].

The brochure also names "Assistenten und Prüfroutinen" without details [S9]. Thus I do not know
which LV checks iTWO already does. RIB also has an iTWO brochure for AVA and planning. I saw only
its file name in the search results. I did not read it.

## 3. Known methods to find errors and risks

Tournament A asked: which check should the prototype build first? The criterion had four parts:
money at risk, runs on the available data in two days, few false alarms, support in the evidence.

| Rank | Check | What it finds | BT theta | Basis |
|---|---|---|---|---|
| 1 | A2 VOB/A rule checks | provisional items, hourly-wage items, mixed items, risk shifts | 2.19 | [S1] [S2] |
| 2 | A1 Structure and arithmetic | missing quantities or units, duplicate OZ, empty texts, sum errors | 1.69 | [S4] [S5] |
| 3 | A6 Quantity-change exposure | likely quantity errors above 10 %, work with no item | 1.18 | [S3] |
| 4 | A4 Vague-language detector | unclear descriptions | 1.05 | [S5] [S6] |
| 5 | A8 Cross-item plausibility | quantities that do not fit related items | 0.75 | [S5] |
| 6 | A3 ATV Abschnitt 0 checklist | information that a trade needs but the LV does not give | 0.60 | [S1] |
| 7 | A5 Standard-class matching | items with missing parameters or the wrong class | 0.32 | [S7] [S8] |
| 8 | A7 Unbalanced-price analysis | unit prices far above or below cost | 0.21 | [S4] |

### A2: VOB/A rule checks

VOB/A §7 sets the rules for an LV in a public tender. Each rule gives a check:

- Clear text: "Die Leistung ist eindeutig und so erschöpfend zu beschreiben, dass alle Unternehmen die Beschreibung im gleichen Sinne verstehen müssen" [S1].
  All bidders must understand the text in the same way.
- Facts for the price: the client must find "alle sie beeinflussenden Umstände festzustellen und in den Vergabeunterlagen anzugeben" [S1].
  All facts that affect the price must be in the tender documents.
- Risk: "Dem Auftragnehmer darf kein ungewöhnliches Wagnis aufgebürdet werden" [S1].
  Flag texts that move an unusual risk to the contractor.
- Provisional items: "Bedarfspositionen sind grundsätzlich nicht in die Leistungsbeschreibung aufzunehmen" [S1].
  In GAEB XML, such items have a Provis element (inferred from the sample files, see AGENTS.md).
- Mixed items: "Ungleichartige Leistungen sollen unter einer Ordnungszahl (Sammelposition) nur zusammengefasst" werden
  in a narrow case [S2]. Flag items that combine different kinds of work.
- Product names: §7(2) permits a product name only in special cases, with the addition *oder gleichwertig* [S1].
  Flag product names without this addition.

For the bidder, each violation is a price risk and a reason for a bidder question.
One AVA vendor announced the same kind of check: "Leistungspositionen werden automatisch mit
geltenden VOB-Anforderungen und einschlägigen DIN-Normen abgeglichen" [S12] (vendor claim in trade press).

### A1: Structure and arithmetic

- A BoQ error list names "Omissions or double-counting of items" and "Omissions and discrepancies between the BoQ and the drawings or specifications" [S5].
- The FHWA bid review checks the quantities first: "Where substantial differences exist, the estimated quantities should be checked." [S4]
- Checks: missing or zero quantity, missing unit, unit that does not fit the text, duplicate OZ,
  empty long text. On priced files: quantity × unit price = total, and the section sums.
- GAEB 90 numbers have implied decimal places. Check the scale before you trust a sum (AGENTS.md).

### A6: Quantity-change exposure (Nachtrag potential)

- VOB/B §2(3): "Für die über 10 v. H. hinausgehende Überschreitung des Mengenansatzes ist auf Verlangen ein neuer Preis unter Berücksichtigung der Mehr- oder Minderkosten zu vereinbaren." [S3]
  If the real quantity is more than 10 % above the LV quantity, a new price is agreed on request.
- VOB/B §2(6): "Wird eine im Vertrag nicht vorgesehene Leistung gefordert, so hat der Auftragnehmer Anspruch auf besondere Vergütung." [S3]
  Work that the contract does not contain gives a right to extra pay.
- Heuristics (my proposal, not from a source): round or placeholder quantities, lump sums with a
  large scope, related items that disagree, work in a long text that has no item of its own.

### A4: Vague-language detector

- A BoQ error list names "Insufficient information given in the descriptions." [S5]
- The SREE tool shows the method: "SREE is a lexical analyser, searching for instances for only specific words in SREE’s database" [S6].
- Result: "SREE is designed to have 100% recall for potential ambiguities in SREE’s scope" [S6], but
  "SREE’s less than 100% precision was calculated" [S6]. A word list finds each listed term but gives false alarms.
- An LLM review of each hit can remove false alarms. This is my proposal; I did not measure it.
- Start list (my proposal): ca., ggf., etc., usw., o. ä., nach Erfordernis, nach Angabe der
  Bauleitung, bauseits without details. Placeholders such as [FIRMA_096] are not vague terms.

### Lower ranks: A8, A3, A5, A7

- A8: the error list names "Inaccurate measurement of quantities." [S5]. No source gave ratio tables
  between related items, for example formwork area and concrete volume.
- A3: VOB/A says that the notes "in Abschnitt 0 der Allgemeinen Technischen Vertragsbedingungen für Bauleistungen, DIN 18299 ff., sind zu beachten" [S1].
  The DIN texts are not free, and I did not read them. An LLM can invent items of such a list.
- A5: models reach "above 90% F1 score on average, on 32 ICMS categories" [S7], and NER models reach
  "F1 scores ranging from 0.81 to 0.97" [S8]. They need labelled data or a licensed text library.
- A7: FHWA says: "A mathematically unbalanced bid is one containing a bid item(s) which do not reflect reasonable actual costs" [S4].
  It needs priced files and a reference price. Few sample files have prices. Use it later on
  subcontractor offers in the Preisspiegel (my proposal).

### Rejected: Benford's law

Benford's law needs numbers that span several orders of magnitude and that people do not set.
LV quantities are often rounded estimates. The condition fails (analogy grade C). Do not use it.

## 4. Price channels

Tournament B asked: which channel gives reliable, current unit prices or resource costs for a bid
in Germany? The criterion: close to the market at bid time, available in a short bid period,
legal and practical, support in the evidence.

| Rank | Channel | Gives | Limits | BT theta | Basis |
|---|---|---|---|---|---|
| 1 | P5 Direct RFQ and Preisspiegel | quotes for this bid | needs replies in time | 2.27 | [S9] [S19] [S20] [S21] |
| 2 | P6 Bidder networks | many companies fast | reach figures are vendor claims | 1.16 | [S10] [S11] |
| 3 | P4 Supplier price files (DATANORM, PRICAT) | current list prices | materials only, price before discount | 1.09 | [S17] [S18] |
| 4 | P2 Commercial price databases | regional prices for standard work | past award prices, paid access | 0.96 | [S9] [S13] |
| 5 | P7 Bottom-up calculation (EFB 221/223) | clear prices for own labour | needs input prices | 0.66 | [S15] [S21] |
| 6 | P1 Own price history and ML | company-specific prices | not in the sample data | 0.55 | [S16] |
| 7 | P3 Official price indices | update of old prices | coarse, includes VAT | 0.32 | [S14] |

My own votes put P1 second. Both independent judges put P1 low, because the sample data has no
price history. For a bidder with years of own data, P1 can be more useful (assumption).
Without the Nemotron votes, P1 moves to the fourth place. P5 stays first in each fit.

### How the channels work together (my synthesis)

- Materials: import DATANORM files for list prices (P4). Send an RFQ for the project price (P5).
- Subcontractor work: send an RFQ (P5 or P6), compare in the Preisspiegel, add a markup.
- Own labour and equipment: calculate bottom-up from Mittellohn, markups and equipment rates (P7).
- Check: compare with a price database (P2). Update old prices with the Destatis index (P3).

### Evidence per channel

- P5: "Der Bieter kann Preise der Nachunternehmer unmittelbar für sein Angebot übernehmen und mit einem Zuschlag als Aufschlag versehen." [S21]
  The usual markup: "Branchenüblich ist durchaus ein Zuschlag von 10 % in der Spanne von 8 bis 13 %" [S21].
- P5: under VHB-Bund 2017, the bidder must give EFB 223 for subcontractor work [S21], if
  "die voraussichtliche Angebotssumme des Angebots mehr als 50.000 € umfasst" [S21].
- P6: "Mehr als 100.000 Bieter sind auf iTWO tender aktiv." [S10] (RIB figure).
- P6: RIB TenderConnect "bietet Zugriff auf rund 180.000 registrierte Bieterunternehmen der RIB-Plattform" [S11].
  "Eingehende Angebote werden digital erfasst und automatisch in den Preisspiegel übernommen" [S11] (vendor statement in trade press).
- P4: "Generally DATANORM version 4 is still the most common and can be processed by 99% of the programs used." [S17]
  This supplier says: "We update the item data every 3 months." [S17]
- P4: Heinze publishes a PRICAT guideline: "Artikelstammdaten im Fachhandel der Baubranche Version 1.2" [S18].
- P2: "Das Portal baupreislexikon.de wird derzeit von rund 120.000 Nutzern genutzt" [S13]. It gives prices
  "Genau für die gesuchte Bauleistung und die eingestellte Region." [S13]
- P2: estimators often use past award prices: "dienen oft Vergabepreise vergangener Bauvorhaben als Hilfsmittel" [S13].
- P7: the ZDB guide covers the "Stundenverrechnungssatz für ein Unternehmen auf Basis des Mittellohns" [S15],
  the "Kalkulation mit vorbestimmten Zuschlägen und Formblatt 221" [S15], the "Aufgliederung der Einheitspreise im Formblatt 223" [S15]
  and the "Ermittlung von Verrechnungssätzen für Geräte" [S15].
- P1: a public procurement project used "approximately 3 million items over 10 years of public procurement" [S16].
  "XGBoost ensemble method appeared to perform best with the predictors for the dataset consisting only of goods (median RMSE at $3)" [S16].
- P3: "Die Preise für den Neubau konventionell gefertigter Wohngebäude in Deutschland sind im August 2026 gegenüber August 2025 um 5,5 % gestiegen" [S14].
  "Alle Preisangaben beziehen sich auf Bauleistungen am Bauwerk einschließlich Mehrwertsteuer." [S14] Remove the VAT before you use the index.

## 5. How to get non-public prices: the RFQ workflow

1. Split the checked LV into packages: one package for each subcontracted trade, one material list for each supplier group.
2. Select suppliers for each package from your supplier list or a bidder network.
   Ask three or more suppliers (my assumption, not from a source).
3. Check consent. Send RFQ emails only to suppliers that agreed to receive them (section 6).
   If a supplier is new, call first and ask.
4. Send the RFQ from the estimating system or by email. Attach the package as a GAEB file and as a PDF.
5. Set the reply date before your own bid deadline. Leave time for the Preisspiegel and for bidder questions.
6. Import the offers: GAEB X84 files from subcontractors, price lists or DATANORM files from suppliers.
7. Make the offers comparable: net prices, the same units, discounts, freight, surcharges, validity.
8. Check each offer for missing items, conditions (Vorbehalte) and unbalanced prices.
9. Put the chosen prices into the estimate. Add the subcontractor markup.
10. If VHB-Bund applies and a subcontractor does the work, fill in EFB 223 [S21].
    The sample PDFs use VHB Bayern forms. I did not check the VHB Bayern rules.

### Email template (German, my draft, not from a source)

Send it only to suppliers that agreed to receive RFQ emails (section 6). The placeholders use
angle brackets. They are different from the [FIRMA_xxx] placeholders in the data.

~~~text
Betreff: Preisanfrage <Gewerk oder Material> – Bauvorhaben <Bezeichnung> – Antwort bis <Datum>

Sehr geehrte Damen und Herren,

wir bereiten ein Angebot für das Bauvorhaben <Bezeichnung> in <Ort> vor.
Ausführung voraussichtlich: <Zeitraum>.

Bitte senden Sie uns Ihr Angebot für die Leistungen im beigefügten Leistungsverzeichnis
(GAEB-Datei und PDF, Positionen <OZ von> bis <OZ bis>).

Bitte beachten Sie:
- Einheitspreise netto je Position, Mengen laut Leistungsverzeichnis
- Lieferung frei Baustelle <PLZ Ort>, oder Fracht getrennt ausweisen
- Bindefrist des Angebots bis <Datum>
- Lieferzeit, Zahlungsbedingungen, Rabatt und Skonto
- Abweichungen, Alternativen und Vorbehalte bitte getrennt kennzeichnen
- Rückgabe bitte als GAEB-Datei (DA 84) oder als Tabelle mit Ordnungszahlen

Bitte antworten Sie bis <Datum, Uhrzeit> an <E-Mail>.
Fragen zum Leistungsverzeichnis beantwortet <Name>, Telefon <Nummer>.

Diese Anfrage ist unverbindlich und kein Auftrag. Wenn Sie keine Preisanfragen
per E-Mail von uns wünschen, teilen Sie uns das bitte kurz mit.

Mit freundlichen Grüßen
<Name>
<Firma, Anschrift>
~~~

## 6. Legal notes (not legal advice)

> **Warning:** Get express consent before you send RFQ emails to a supplier. Without consent, an
> RFQ email can be an unfair nuisance under UWG §7.

What the sources say:

1. Today's text, UWG §7(2) Nr. 2: email advertising is always a nuisance "bei Werbung unter Verwendung einer automatischen Anrufmaschine, eines Faxgerätes oder elektronischer Post, ohne dass eine vorherige ausdrückliche Einwilligung des Adressaten" vorliegt [S19].
2. A purchase inquiry is advertising: "Als Werbung erfasst § 7 Abs. 2 Nr. 3 UWG grundsätzlich auch Nachfragehandlungen." [S20]
   This includes inquiries to businesses: "Der Begriff der Werbung in § 7 Abs. 2 UWG erfasst auch Nachfragehandlungen, die sich an Gewerbetreibende oder Freiberufler richten." [S20]
3. In 2008, the BGH accepted implied consent for one case. A company that publishes an email address accepts "Anfragen potentieller Kunden zu dem üblichen Waren- und Dienstleistungsangebot des Unternehmens" [S20].
   A practice article reports a BGH judgment of the same day (I ZR 75/06). It accepted a purchase inquiry by fax from one car dealer to another on this basis [S24].
4. Condition: the BGH applied the wording of 2008. Then, email advertising needed only "ein ausdrückliches oder konkludentes Einverständnis" [S20]. Implied (konkludent) consent was enough.
5. Today's wording demands express consent. A 2023 judgment uses the GDPR definition: an "unmissverständlich abgegebene Willensbekundung in Form einer Erklärung oder einer sonstigen eindeutigen bestätigenden Handlung" [S23].
6. I found no later judgment that applies the 2008 rule to today's wording. Thus I cannot confirm that a published address is enough today.
7. For a phone call to a business, presumed consent is enough. UWG §7(2) Nr. 1 names calls "gegenüber einem sonstigen Marktteilnehmer ohne dessen zumindest mutmaßliche Einwilligung" [S19].
   Presumed consent needs a concrete interest: "Es muss auf Grund konkreter Umstände ein sachliches Interesse des Anzurufenden vom Anrufer vermutet werden können." [S23]
   An objection ends it: "Ein ausdrücklicher Widerspruch schließt die Annahme einer mutmaßlichen Einwilligung aus" [S23].
8. Numbering (inferred): in 2008, Nr. 2 was the phone rule and Nr. 3 the email rule [S20]. Today, they are Nr. 1 and Nr. 2 [S19].

Safe practice (my reading, not legal advice):

1. Existing suppliers: get express consent once, for example in the supplier registration or the framework agreement. Keep a record.
2. New suppliers: call the sales department first. Ask for consent to send the RFQ by email, and record it.
   A supplier has a concrete interest in an inquiry about its usual products (my reading).
3. Or use the supplier's own inquiry form, or a bidder platform where the supplier registered for inquiries. I did not check the platform terms.
4. Ask only for products or work that the supplier offers.
5. If a supplier objects, stop at once.

Not researched: GDPR (DSGVO) rules for named contact persons, and the terms of bidder platforms.

## 7. Prototype scope for the hackathon (proposal)

The README says: no historical data, no price catalogs, few priced files. Thus:

1. Parse GAEB DA XML first, then PDF, then GAEB 90.
2. Build A2 and A1 as rules. They need no model.
3. Add the A6 heuristics and the A4 word list with LLM review.
4. Show the risk report: one row for each finding, with OZ, check, severity, reason and a draft bidder question.
5. Optional: an RFQ generator. It groups the items by trade and fills in the email template.
6. Do not promise unit price suggestions from history. The sample data has no price history.

## 8. Method trace

### AB-MCTS tree

| Node | Origin | Visits | Q |
|---|---|---|---|
| B1_lv_text_checks | root | 9 | 0.53 |
| B2_numbers_risk | root | 6 | 0.54 |
| B3_price_estimation | root | 10 | 0.55 |
| B4_supplier_prices | root | 11 | 0.64 |
| B5_itwo_fit | STRUCTURAL mutation of B3 and B4 | 4 | pruned |
| X13_stlb_matching | CROSSOVER of B1 and B3 | 4 | 0.69 |
| B4m_quote_extraction | PARAMETER mutation of B4 | 2 | 0.375 |
| B2m_quantity_errors | PARAMETER mutation of B2 | 2 | 0.50 |

- Visits: 48. The budget was 30. The overrun of 18 visits comes from the deep reading wave (26 fetches)
  and one legal check.
- Searches: 21, all in standard mode. Fetch attempts: 30 for 29 sources. Failed fetches: 5. Leaks: 1.
- abmcts-audit: FAIL, with batched=28, off_chosen=20 and no_new_choose=30. All flags are in the two
  named parallel waves (t=1 to 4 and t=22 to 47). The audit expects one choose for each visit.
- The legal check (t=48) used a logged override: choose --override with a reason. It added no flag.
- The CLI accepted one visit on the pruned node B5 (t=47). This visit records the RIB tender brochure.
- Evidence packs: 24 lines (A) and 34 lines (B). quote-check result: CITED=58, MISSING=0.

### SIFT tournaments

| Item | A (checks) | B (price channels) |
|---|---|---|
| Candidates, pairs | 8, 28 | 7, 21 |
| Match records | 139 | 105 |
| Valid judge records | GPT 28+28, Nemotron 28+27 | GPT 21+21, Nemotron 21+21 |
| Same winner after side swap | GPT 28/28, Nemotron 24/27 | GPT 21/21, Nemotron 18/21 |
| Agreement GPT and Nemotron | 0.84 | 0.889 |
| Agreement own and GPT, own and Nemotron | 0.821, 0.80 | 0.571, 0.50 |
| Converged (iterations) | yes (64) | yes (61) |
| Twin warning | no | no |
| Leave-one-judge-out, first place | A2, A2, A1 | P5, P5, P5 |

- Judges: my own votes, bench-gpt-6.2-sol #1 and #2, bench-nemotron-3-ultra-free #1 and #2.
  Run #2 of each model swaps the sides of every pair.
- The standing judge rule names parliament. You asked for no parliament in this task, so I used
  two other model families. Gemini was the plan. It failed with HTTP 429 on three Gemini models
  and on one retry after 60 s. Nemotron replaced it.
- To reverse this decision, run sift-judge again with parliament labels and refit.

### Fitness inputs

The definitions come from the research policy file (policy.json).

- Yield = useful sources / deep-fetched sources = 23 / 29 = 0.793.
- LeakRate = sources that failed a gate after the fetch / deep-fetched sources = 1 / 29 = 0.034.
  If the four access failures (HTTP 403, HTTP 404, failed fetch) count as leaks: 5 / 29 = 0.172.
- Entropy = normalized Shannon entropy of the source domains = 0.955 (18 domains, 58 evidence lines).
- Fitness = 0.793 × 0.966 × 0.955 = 0.731. With the access failures as leaks: 0.627.
- My reading: I computed the entropy over the evidence lines. The final candidates are methods, not sources.

### Analogies (quick mode)

| Source | Target | Conditions | Grade | What transfers |
|---|---|---|---|---|
| Owner-side bid review (FHWA) | bidder-side LV check | quantities first: holds; engineer's estimate exists: fails before pricing | B | the order of steps, not the result |
| Ambiguity detection in requirements (SREE) | LV texts | word list fits the language: approx; recall only inside the list: holds | B | the method |
| Should-cost calculation | EFB 221/223 (P7) | resource inputs are known: approx | B | the method |
| Benford's law | LV quantities | several orders of magnitude, numbers not set by people: fails | C | nothing |

## 9. Not verified

- Seven of 26 key claims are not checked in a primary text. S5, S11, S12, S13, S21 and S24 are
  secondary sources. The UWG numbering change is inferred.
- Whether a published email address still gives consent to purchase inquiries under today's UWG
  wording: I found no later judgment.
- RM Baupreise (Rudolf Müller): the fetch was blocked (HTTP 403).
- BKI, Heinze Baupreisinfo, STLB-BauZ, Procore and Autodesk: not fetched.
- ATV Abschnitt 0 contents: the DIN texts are not free. I did not read them.
- OLG Celle judgment 14 U 191/13: the PDF gave HTTP 404.
- Polat study on unbalanced bids: the fetch failed.
- One secondary source says that iTWO has no prominent AI functions. I saw only a search snippet.
- Vendor figures: 100,000 bidders [S10], 180,000 bidder companies [S11], 120,000 users [S13],
  Phase0 functions [S12].
- GDPR (DSGVO) rules for named contact persons, and the terms of bidder platforms: not researched.
- The criteria and the hard-constraint ranks of the tournaments are mine. Other criteria can change
  the order.

## Sources

- [S1] VOB/A 2019 §7 (text mirror): https://lxgesetze.de/vob-a-2019/7
- [S2] VOB/A 2019 §7b (text mirror): https://lxgesetze.de/vob-a-2019/7b
- [S3] VOB/B 2016 §2 (text mirror): https://lxgesetze.de/vob-b-2016/2
- [S4] FHWA memorandum on bid review and unbalanced bids, 1 Dec 1988: https://www.fhwa.dot.gov/construction/contracts/881201.cfm
- [S5] Designing Buildings Wiki, Common mistakes in bill of quantities (secondary): https://www.designingbuildings.co.uk/wiki/Common_mistakes_in_bill_of_quantities
- [S6] Tjong, Avoiding Ambiguity in Requirements Specifications (thesis): https://cs.uwaterloo.ca/~dberry/FTP_SITE/students.theses/TjongThesis.pdf
- [S7] Deza, Ihshaish, Mahdjoubi, classifying construction cost documents into ICMS, arXiv 2211.07705: https://arxiv.org/abs/2211.07705
- [S8] Ontology development using language model-based NER, Journal of Civil Engineering and Management: https://journals.vilniustech.lt/index.php/JCEM/article/download/26519/13445
- [S9] RIB iTWO brochure, Kalkulation und Baumanagement: https://www.rib-software.com/pdf/de/rib-itwo-broschuere-kalkulation-baumanagement.pdf
- [S10] RIB iTWO tender and ava-sign brochure: https://www.rib-software.com/pdf/de/rib-itwo-tender-ava-sign-2-2022.pdf
- [S11] Baulinks, RIB TenderConnect (trade press, secondary): https://www.baulinks.de/webplugin/2026/1077.php4
- [S12] Baulinks, Phase0 AI functions (trade press, secondary): https://www.baulinks.de/webplugin/2026/0768.php4
- [S13] Bauprofessor news, Baupreislexikon (secondary): https://www.bauprofessor.de/news/baupreislexikon-ab-sofort-baupreise-in-echtzeit/
- [S14] Destatis, Baupreise: https://www.destatis.de/DE/Themen/Wirtschaft/Preise/Baupreise-Immobilienpreisindex/_inhalt.html
- [S15] ZDB, Ermittlung lohnbasierter Kalkulationsansätze im Bauunternehmen (2018): https://www.zdb.de/fileadmin/user_upload/2018_Kalkulationsansaetze_Einstieg_fuer_WebShop.pdf
- [S16] DSSG, DNCP unit price project, conclusions: https://dssgxuk.github.io/dncp/conclusions.html
- [S17] TBS, FAQ on interfaces (DATANORM): https://tbs-online.de/de/en/Service/Frequently-asked-questions/Interfaces.html
- [S18] Heinze PRICAT guideline 1.2 (hosted by a dealer): https://www.stark-deutschland.de/fileadmin/Lieferanten/Stammdaten_Preise/HeinzePricat1_2.pdf
- [S19] UWG §7: https://www.gesetze-im-internet.de/uwg_2004/__7.html
- [S20] BGH, 17.07.2008, I ZR 197/05 (text mirror): https://lexetius.com/2008,2034
- [S21] Bauprofessor, Preisangaben zu Nachunternehmer (secondary): https://www.bauprofessor.de/preisangaben-zu-nachunternehmer/
- [S22] Local: the ProgName element in the headers of the four X83 files in data/raw.
- [S23] LG Nürnberg-Fürth, judgment of 29.09.2023, 19 O 1485/23 (Bavarian court database): https://www.gesetze-bayern.de/Content/Pdf/Y-300-Z-GRURRS-B-2023-N-36137?all=True
- [S24] IWW, Gewerbliche Nachfrage per Telefax und E-Mail zulässig, 29.08.2008 (practice article, secondary): https://www.iww.de/asr/archiv/wettbewerbsrecht-gewerbliche-nachfrage-per-telefax-und-e-mail-zulaessig-f20314

Fetched but not usable:

- OLG Celle PDF (HTTP 404): https://www.heuking.de/fileadmin/DATA/Dokumente/Aktuelles/OLG_Celle_20.11.19_14_U_191-13_1068.pdf
- Polat record (fetch failed): https://bvbvf1.bib-bvb.de/vufind/PrimoRecord/cdi_proquest_miscellaneous_1864558604
- RM Baupreise press PDF (HTTP 403): https://www.presseservice.rudolf-mueller.de/pressreleases/baupreise-online-3427510.pdf
- Knauf Insulation article data (HTTP 403): https://knauf.com/de-DE/services/artikelstammdaten/knauf-insulation
- arXiv 2206.14553 (the abstract does not hold the claim from the search): https://arxiv.org/abs/2206.14553
- Gatto et al., NLP framework for cost estimation, EC3 2023 (read, not used): https://re.public.polimi.it/bitstream/11311/1256883/1/DEVELOPMENT%20OF%20A%20FRAMEWORK%20FOR%20PROCESSING%20UNSTRUCTURED%20TEXT%20DATASET%20THROUGH%20NLP%20IN%20COST%20ESTIMATION%20AEC%20SECTOR.pdf
