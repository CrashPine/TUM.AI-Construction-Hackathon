# AGENTS.md

Instructions for coding agents (Codex, Claude Code, Cursor, Copilot and others) in this repository.
[README.md](README.md) explains the challenge and the German BoQ terms. [data/README.md](data/README.md)
describes every data file.

## Project

Prototype for Challenge A of the TUM.AI Construction Hackathon: an assistant that reads German bills
of quantities (BoQs, German *Leistungsverzeichnis*, LV), finds errors and risks and shows them in a
risk report. Demo: upload a BoQ, get a risk report.

Order of work, from the brief:

1. Parse BoQs into structured data. The brief prefers GAEB; the data also has many PDFs.
2. **Error detection, the main priority:** missing items, unclear descriptions, contradictions, typos.
3. Risk scoring: imprecise scope descriptions, unusual quantities, change-order (Nachtrag) potential.
4. Optional: unit price suggestions from historical data, what-if analyses.

## Status: no stack yet

There is no code, no build system and no test command. The team has not chosen the language or the
framework: do not assume one. The pull request that adds the first code must also update this file
with the commands to set up, run, test and lint the project, and with the new folders.

## Repository map

| Path | Content |
|---|---|
| `data/raw/` | the organizers' 44 sample files, unchanged; read-only |
| `data/README.md` | inventory: formats, phases, counts, files that hold the same BoQ |
| `README.md` | challenge, data overview, glossary |

## Data rules

- Never edit, rename, move or re-encode files in `data/raw/`. `.gitattributes` keeps them byte-exact.
  Write derived data (parsed JSON, extracts, caches) to another folder.
- File names contain spaces and brackets, for example `data/raw/[ORT_024] LV24069.D86`. Quote paths.
- The data is anonymized with placeholders such as `[FIRMA_096]`, `[ORT_024]` and `[PERSON_167]`.
  Keep them as they are. Do not try to recover the real values.
- Placeholders also replace words inside item texts, for example `[PERSON_167] WL liefern und verlegen`.
  A placeholder alone is not a typo or an unclear description: do not report it as an error.
- The anonymization is not complete: some place and organization names are still in the texts.
  Do not put raw documents or long extracts into issues, pull requests, slides or demo videos.
- Tests can read files from `data/raw/`. Do not copy whole data files into code or test folders.

## File formats

Facts below come from scripts that read the files. Meanings marked "inferred" need a check against
the GAEB specification. All texts are German; PDFs use a decimal comma (`1.234,56`).

**GAEB DA XML** (`.X83`, `.x83`; 4 files)

- The namespace depends on the version: 3.1 uses `http://www.gaeb.de/GAEB_DA_XML/200407`,
  3.2 uses `http://www.gaeb.de/GAEB_DA_XML/DA83/3.2`. Match elements by local name.
- `Award/DP` is the exchange phase: 83 (bid request) in all four files.
- Sections are nested `BoQCtgy` elements. Items are `Item` elements (attribute `RNoPart`) with
  `Qty`, `QU` (unit) and `Description/CompleteText`: `OutlineText` holds the short text,
  `DetailTxt` the long text in `p`/`span` markup.
- Some items have `Provis` or `LumpSumItem` children. `501-24-01_GAEB-XML_sas.x83` also has STLB-Bau
  references (`STLBBauID`).
- No file has `UP` or `IT` (unit price, total) elements: all four are unpriced.

**GAEB 90** (`.D83`, `.D84`, `.D86`; 5 files)

- Fixed-width lines of 80 characters with CRLF line ends. Columns 1-2 hold the record type,
  columns 75-80 a line number.
- The code page differs per file: four files use DOS code page 850, `Angebot AN24-0305.D84` uses
  ISO-8859-1. Detect it per file (the right one gives German umlauts). Never assume UTF-8.
- The header record `00` holds the phase in columns 11-12 (83, 84 or 86).
- Record types, inferred from the content: `11`/`12` section start and label, `21` item (OZ,
  quantity, unit), `23` prices, `25` short text, `26` long text, `T0`/`T1`/`T9` free text,
  `99` end of file. Other types occur too.
- Numbers have implied decimal places, and the layout of `23` records differs between files.
  Check quantity × unit price = total on some items before you trust a scale.
- `StBALV23040.D84` has only price records. Join it to `StBALV23040.D86` by OZ to get the texts.

**PDF** (34 files)

- Every page has a text layer: OCR is not needed.
- Only `Abgabe LV.pdf` and `Angebot AN24-0305.pdf` show prices; the other PDFs have dotted blank
  price fields (inferred from counts, see `data/README.md`).
- `Abgabe LV.pdf` and `HEM2301-2_Gesamt-LV.pdf` start with tender forms (VHB Bayern) before the BoQ.

Some BoQs exist in more than one file and phase; `data/README.md` lists the groups. Use them as
ground truth for parser tests, for example parse a PDF and compare it with its GAEB file.

## Working rules

- Branch from `main` with a prefix: `feature/`, `fix/`, `docs/`, `chore/` or `data/`.
  Do not push to `main`; open a pull request.
- Keep each pull request small enough to review in one sitting: about 400 changed lines.
- Commit each finished functionality with its tests. The message says what changed and why.
- Write the least code that solves the task: no unused options, no swallowed errors, no comments
  that repeat the code. Comments explain why.
- Give every module, class and function a docstring in the standard format of the stack
  (Python: Sphinx reST).
- A test must fail when the behavior it covers breaks; see each new test fail once.
  Do not write tests that only exist to pass.
- The repository is public. Never commit API keys, tokens or `.env` files; `.gitignore` excludes
  `.env`. Read keys from environment variables and list their names in a `.env.example` without values.
- Write code, comments and docs in English. Keep German domain terms (LV, OZ, Kurztext, Nachtrag).
- In each pull request, say how you verified the change and what you did not verify.
