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

## Stack and commands

Python 3.12 or newer with [uv](https://docs.astral.sh/uv/). The package `boqcheck` in `src/` has no
runtime dependencies. Dev tools: pytest, ruff (lint and format) and pydoclint (Sphinx docstrings).
`pyproject.toml` holds their settings.

| Task | Command |
|---|---|
| Set up `.venv/` | `uv sync` |
| Test | `uv run pytest -q` |
| Lint | `uv run ruff check`, `uv run ruff format --check`, `uv run pydoclint src tests` |
| Format | `uv run ruff format` |

Run the test and lint commands in the repository root before you open a pull request. pydoclint
reads `pyproject.toml` from the current folder; in another folder it uses other defaults.
CI (`.github/workflows/ci.yml`) runs the same commands on each pull request and each push to
`main`; its `uv sync --locked` fails if `uv.lock` does not match `pyproject.toml`.

Use the parser from Python:

```python
from pathlib import Path

from boqcheck import parse

path = Path("data/raw/GAEB-[PROJEKT_004].X83")
boq = parse(path.name, path.read_bytes())  # sections and items in document order
```

`parse()` selects the parser by the file suffix, in any letter case. It reads `.x83` (GAEB DA XML)
and `.d83`, `.d84`, `.d86` (GAEB 90). It raises `ValueError` for other suffixes, for data that is not well-formed XML and for XML without
a GAEB `Award/BoQ` element. It also raises `ValueError` if a `BoQBkdn` element has no `Length`,
or if no `BoQBkdn` element has the type `Item`. Other faults can raise other exceptions, for
example a `Qty` that is not a number. The GAEB 90 parser raises `ValueError` for data without a
`00` record or OZ mask, for a `23` record that does not follow the `21` record of its OZ, and for
files without `21` records (`StBALV23040.D84`). All parsers return the model in `src/boqcheck/model.py`
(`BoQ`, `Section`, `Item`) with these rules:

- An OZ joins its levels with `.` and pads them with zeros to the widths of the BoQ breakdown, for
  example `01.02.0030`. A lot (Los, `Lot` in the breakdown) is the top level. An index letter
  follows the item number without a separator, for example `01.02.0030A`.
- Parts marked as not applicable (Entfällt) are left out, with everything below them.
- The long text of an item ends with its sub-descriptions (Unterbeschreibungen). Each one starts
  with the line `Unterbeschreibung <n>:`, followed by its short text and its long text.
- Units stay as the file writes them (`m3`, `m³`, `Stk.`).
- Prices are `Decimal` or `None`: `Item.unit_price`, `Item.total`, `Section.total` and `BoQ.total`
  (net grand total). Only GAEB 90 files fill them; a blank or zero grand total gives `None`.

## Repository map

| Path | Content |
|---|---|
| `src/boqcheck/` | the package: data model (`model.py`), GAEB DA XML parser (`gaeb_xml.py`), GAEB 90 parser (`gaeb90.py`), `parse()` in `__init__.py` |
| `tests/` | pytest tests; they read the sample files in `data/raw/` |
| `pyproject.toml`, `uv.lock`, `.python-version` | project, dev tools and their settings; locked versions |
| `data/raw/` | the organizers' 44 sample files, unchanged; read-only |
| `data/README.md` | inventory: formats, phases, counts, files that hold the same BoQ |
| `README.md` | challenge, data overview, glossary |
| `docs/research/` | research reports: known BoQ checks, price sources, supplier RFQ workflow |

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
- `DetailTxt` can hold several `Text` elements with `TextComplement` elements between them (text of
  the client, blanks for the bidder). The parser keeps both in document order.
- Section titles are in `BoQCtgy/LblTx`. The markup is `p`/`span`, or `span`/`br` without `p`
  (`[NUMMER_001]_leer.X83`). `501-24-01_GAEB-XML_sas.x83` is indented inside the text markup.
- `RNoPart` values are not always padded: `8209.003_Leistungsverzeichnis_leer.X83` and
  `[NUMMER_001]_leer.X83` write `1` where `BoQBkdn` gives 2 or 4 digits. `StBALV23040.D86` writes
  the OZs of the same BoQ with zeros (`01.01.0001`).
- The parser skips `Remark` (notes) and `PerfDescr` elements, and item children such as
  `RefDescr` and `RefRNo` in `[NUMMER_001]_leer.X83`.
- `[NUMMER_001]_leer.X83` has 16 `SubDescr` elements (sub-descriptions) in 13 items, numbered by
  `SubDNo` from 1 in each item. Each has a short and a long text. `Leistungsverzeichnis_leer.pdf`
  prints each one as `Unterbeschreibung <n>:`, then its short text and its long text. The parser
  writes them the same way.
- Item texts have lists (`ul`/`li`) only in `8209.003_Leistungsverzeichnis_leer.X83`. Each `li`
  holds a `p`, so each list item gets its own line. Tables (`table`/`tr`/`td`) occur only in
  `Award/AddText` of `501-24-01_GAEB-XML_sas.x83`, and the parser does not read `AddText`.
- No file has a `Lot` breakdown entry, an `RNoIndex` attribute, `NotAppl`, or `NotApplBoQ` `Yes`
  (`501-24-01_GAEB-XML_sas.x83` has `NotApplBoQ` `No` in all 25 sections). Tests cover them
  with synthetic XML.
- Some items have `Provis` or `LumpSumItem` children. `501-24-01_GAEB-XML_sas.x83` also has STLB-Bau
  references (`STLBBauID`).
- No file has `UP` or `IT` (unit price, total) elements: all four are unpriced.

**GAEB 90** (`.D83`, `.D84`, `.D86`; 5 files)

- Fixed-width lines of 80 characters with CRLF line ends. Columns 1-2 hold the record type,
  columns 75-80 a line number.
- The code page differs per file: four files use DOS code page 850, `Angebot AN24-0305.D84` uses
  ISO-8859-1. Detect it per file (the right one gives German umlauts). Never assume UTF-8.
- The header record `00` is not always the first line. It holds the phase in columns 11-12
  (83, 84 or 86) and the OZ mask in columns 63-71 (digits 1-4 for the levels, `P` for the item
  number, `I` for the index).
- Record types, inferred from the content: `11`/`12` section start and label, `21` item (OZ,
  quantity, unit), `23` prices, `25` short text, `26` long text, `T0`/`T1`/`T9` free text,
  `32` section total, `99` end of file with the net grand total. Other types occur too.
- Field columns used by `gaeb90.py` (1-based): OZ 3-11 in all records; `21` quantity 24-34
  (3 decimals) and unit 35-38; column 43 holds an `X` in 28 D83 items, meaning unknown, not read.
  `23` unit price 13-23 (2 decimals if column 23 is blank, else 3) and total 25-36 (2 decimals);
  `32` total 13-24; `99` net total 3-14. Quantity × unit price = total holds on all priced items.
- Files without `11`/`12` records (`Angebot AN24-0305.D84`) get their sections from `32` records.
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
