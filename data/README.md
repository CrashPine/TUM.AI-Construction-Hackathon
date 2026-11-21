# Data inventory

`raw/` is an unchanged copy of the dataset that the challenge organizers shared with the teams on
Google Drive: 44 files, 25 MB, downloaded on 2026-11-21, original file names.

All texts are German. The data is anonymized: names, companies, places, addresses, phone numbers,
e-mail addresses and similar values are replaced by placeholders such as `[FIRMA_096]`, `[ORT_024]`,
`[PERSON_167]` or `[PROJEKT_004]`. GAEB 90 files pad the placeholders with zeros to keep the column
width, for example `[PROJEKT_000000000000000000000000000000000002]`.

The numbers below come from scripts that read the files.

## GAEB DA XML (4 files)

| File | XML version | Phase | Items | Sections | Date |
|---|---|---|---:|---:|---|
| `501-24-01_GAEB-XML_sas.x83` | 3.1 | 83 | 296 | 25 | 2025-06-27 |
| `8209.003_Leistungsverzeichnis_leer.X83` | 3.2 | 83 | 159 | 28 | 2024-02-27 |
| `GAEB-[PROJEKT_004].X83` | 3.2 | 83 | 50 | 4 | 2025-05-16 |
| `[NUMMER_001]_leer.X83` | 3.2 | 83 | 248 | 32 | 2023-03-10 |

Items: `Item` elements. Sections: `BoQCtgy` elements on all levels. Date: the first `Date` element.
No file has price elements (`UP`, `IT`). `[NUMMER_001]_leer.X83` gives the currency as `EURO`,
the others as `EUR`.

## GAEB 90 (5 files)

| File | Phase | Item records (`21`) | Price records (`23`) | Code page |
|---|---|---:|---:|---|
| `8209.003_Leistungsverzeichnis_leer.D83` | 83 | 159 | 0 | cp850 |
| `Angebot AN24-0305.D84` | 84 | 274 | 274 | ISO-8859-1 |
| `StBALV23040.D84` | 84 | 0 | 249 | cp850 |
| `StBALV23040.D86` | 86 | 249 | 249 | cp850 |
| `[ORT_024] LV24069.D86` | 86 | 197 | 197 | cp850 |

Phase: columns 11-12 of the header record `00`. Code page: the decoding that gives German umlauts.
`StBALV23040.D84` has no item texts, only price records; `parse()` rejects it.
In `StBALV23040.D86` the stated totals of sections `08.01` and `08` exceed the sums of their
items by 982.20, and OZ `08.01.0003` is missing.

## PDF (34 files)

Every page of every PDF has a text layer. The columns "Amounts" (amounts of 1.000,00 or more) and
"Dotted" (runs of 6 or more dots, the blank price fields of a print) are counts over the whole text.
Only `Abgabe LV.pdf` and `Angebot AN24-0305.pdf` show such amounts, so the other PDFs are most
likely unpriced.

| File | Pages | Amounts | Dotted | Content |
|---|---:|---:|---:|---|
| `Abgabe LV.pdf` | 91 | 145 | 0 | tender forms (VHB Bayern, from form 214.H), then a priced BoQ |
| `Angebot AN24-0305.pdf` | 27 | 173 | 1 | a contractor's bid (Angebot) |
| `HEM2301-2_Gesamt-LV.pdf` | 136 | 0 | 690 | invitation to bid (VHB Bayern form 211) and other forms, then the BoQ |
| `LV-Ausdruck-[PROJEKT_004].pdf` | 22 | 0 | 157 | BoQ print |
| `LV-Schachtbauwerk.pdf` | 14 | 0 | 72 | BoQ print (shaft structure) |
| `Leistungsverzeichnis.pdf` | 71 | 0 | 618 | BoQ print |
| `Leistungsverzeichnis_leer.pdf` | 78 | 0 | 8 | BoQ print |

The 27 files `LV_00` to `LV_23` (397 pages) belong to one building project. Each file is the
BoQ of one trade and is headed "Anfrage" (request for bids). None shows amounts of 1.000,00 or more;
all show dotted price fields. There is no `LV_16`.

| File | Pages |
|---|---:|
| `LV_00_Roh_und_Erdauarbeiten.pdf` | 68 |
| `LV_01_Fertigteiltreppen.pdf` | 3 |
| `LV_02_PVC_Fussbodenbelag.pdf` | 10 |
| `LV_03_Malerarbeiten.pdf` | 17 |
| `LV_04_Porenbetonfassade.pdf` | 5 |
| `LV_05_[FIRMA_096].pdf` | 1 |
| `LV_06_Kautschukboden.pdf` | 5 |
| `LV_07_Teppichboden.pdf` | 5 |
| `LV_08_Fliesen_und_Natursteinarbeiten.pdf` | 14 |
| `LV_09_Porenbetondach.pdf` | 4 |
| `LV_10_Stahlbetonfertigeile_Stuetzen_Binder.pdf` | 6 |
| `LV_11_Stahlbetonfertigeile_Sandwichsockel.pdf` | 4 |
| `LV_12_Dachabdichtung.pdf` | 11 |
| `LV_13_ELT.pdf` | 58 |
| `LV_14_Sanitaeranlage.pdf` | 62 |
| `LV_14a_Betonkernaktivierung.pdf` | 16 |
| `LV_14b_Dachentwaesserung.pdf` | 14 |
| `LV_14c_Industriebodenheizung.pdf` | 7 |
| `LV_15_Abdichtung_Aussenwaende.pdf` | 2 |
| `LV_15a_Abdichtung_Bodenplatte_Buero.pdf` | 2 |
| `LV_17_Trockenbau.pdf` | 16 |
| `LV_18_Estrich.pdf` | 14 |
| `LV_19_Sektionaltore_Stahltueren.pdf` | 8 |
| `LV_20_Bodenbelagsarbeiten.pdf` | 13 |
| `LV_21_Natursteinarbeiten.pdf` | 11 |
| `LV_22_Schreinerarbeiten.pdf` | 16 |
| `LV_23_Sanitaertrennwaende.pdf` | 5 |

## DOCX (1 file)

`LV-Positionen.docx` lists 40 positions as "OZ – short text [unit]" in groups such as Asphalt,
Baugrube (excavation), Rohrleitungsmaterial DN 250 GGG (ductile iron pipe), Kabelleerrohr (cable duct)
and Kabelschacht (cable shaft). Some groups are joined by "oder" (or) and "mit" (with). The same terms
occur in `Angebot AN24-0305.pdf` and `Leistungsverzeichnis.pdf`; the source BoQ is not confirmed.

## Files that hold the same BoQ

These groups are conclusions from the evidence in the table, not information from the organizers.
"Short texts occur" means exact matches of item short texts after whitespace normalization.

| Group | Files | Evidence |
|---|---|---|
| 1 | `8209.003_Leistungsverzeichnis_leer.X83` (83), `8209.003_Leistungsverzeichnis_leer.D83` (83), `[ORT_024] LV24069.D86` (86) | project number `8209.003` in all three; 111 of 158 XML short texts occur in each GAEB 90 file; 158 of 196 D86 short texts occur in the D83. The D86 has 197 items, the D83 has 159. |
| 2 | `[NUMMER_001]_leer.X83` (83), `Leistungsverzeichnis_leer.pdf`, `StBALV23040.D84` (84), `StBALV23040.D86` (86) | 227 of 246 XML short texts occur in the PDF and 160 of 246 in the D86; XML and PDF have the same BoQ date (10.03.2023); D84 and D86 have the same header id `23A0051`. |
| 3, likely | `Angebot AN24-0305.D84`, `Angebot AN24-0305.pdf` | same bid number and date (25.11.2024). Texts not compared: the D84 has no short-text records. |
| 4, not confirmed | `GAEB-[PROJEKT_004].X83`, `LV-Ausdruck-[PROJEKT_004].pdf` | same placeholder in the file names, but only 9 of 48 XML short texts occur in the PDF. |

`501-24-01_GAEB-XML_sas.x83` matches neither `HEM2301-2_Gesamt-LV.pdf` nor `Abgabe LV.pdf`
(1 of 295 short texts).

Groups give ground truth for parser tests (parse the PDF, compare it with the GAEB file) and allow
comparisons between bid request, bid and contract award (phases 83, 84 and 86).
