"""Tests for PDF German typo detection in ``boqcheck.typos``."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from boqcheck.pdf_extract import Line, extract
from boqcheck.typos import TypoFinding, find_typos

_RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def _line(text: str, *, page: int = 0, oz: str | None = None) -> Line:
    """Create a synthetic PDF line for unit tests.

    :param text: extracted line text.
    :param page: zero-based PDF page index.
    :param oz: optional item Ordnungszahl.
    :returns: synthetic ``Line`` instance.
    """
    return Line(page=page, label=None, oz=oz, text=text, quad=pymupdf.Quad())


def test_offline_heuristics_detect_triples_case_flips_and_digits() -> None:
    """Flag tripled letters, internal case flips, and word-plus-digit errors in order."""
    pages = [
        [
            _line("Verlegen von Bettteppich im Flur", page=0, oz="1.1.10"),
            _line("Prüfung dasaufdenvonIhmbenutzten Geräts", page=0, oz="1.1.20"),
        ],
        [
            _line("Mischen von Beton3 nach Vorgabe", page=2, oz="2.1.10"),
        ],
    ]
    findings = find_typos(pages)
    assert [(f.word, f.page, f.oz, f.suggestion) for f in findings] == [
        ("Bettteppich", 0, "1.1.10", None),
        ("dasaufdenvonIhmbenutzten", 0, "1.1.20", None),
        ("Beton3", 2, "2.1.10", "beton"),
    ]
    assert findings[0].context == "Verlegen von Bettteppich im Flur"


def test_valid_triples_uppercase_codes_and_units_are_not_flagged() -> None:
    """Ignore whitelisted compounds, all-caps codes, units, and words containing ß."""
    text = (
        "Schifffahrt ballle nummern III GGG Maßstab Schweißstelle "
        "50 m2 10 m3 C20 DN100 Q2 NAB3 kN dB BaustellV"
    )
    assert find_typos([[_line(text)]]) == []


def test_placeholders_are_ignored_in_offline_and_llm_modes() -> None:
    """Strip anonymization placeholders before heuristic and LLM inspection."""
    line = _line("[FIRMA_102] [ORT_026] [PERSON_167] liefern")
    assert find_typos([[line]]) == []

    seen_texts: list[str] = []

    def llm_check(text: str) -> list[str]:
        """Record cleaned line text and propose a placeholder token.

        :param text: cleaned line text passed to the LLM callback.
        :returns: suspect list including a placeholder word.
        """
        seen_texts.append(text)
        return ["FIRMA_102", "ORT_026"]

    assert find_typos([[line]], llm_check=llm_check) == []
    assert seen_texts == ["liefern"]


@pytest.mark.parametrize(
    "word",
    [
        "Baumaßnahme",
        "Passstücke",
        "Maueranschlussschiene",
        "Bleche",
        "Steinen",
        "elastischer",
        "Bleches",
        "elastischem",
        "Platten",
        "Betons",
    ],
)
def test_dictionary_and_inflected_stems_suppress_suspects(word: str) -> None:
    """Skip words present in ``GERMAN_WORDS`` directly or via standard suffixes.

    :param word: valid German word or inflected form proposed by the LLM.
    """
    findings = find_typos([[_line(word)]], llm_check=lambda _: [word])
    assert findings == []


def test_llm_proposes_suspects_and_offers_edit_distance_one_suggestions() -> None:
    """Call LLM once per line, ignore hallucinations, and suggest single-edit corrections."""
    calls: list[str] = []

    def llm_check(text: str) -> list[str]:
        """Propose one real typo, one valid dictionary word, one triple typo, and noise.

        :param text: cleaned line text.
        :returns: proposed suspect words.
        """
        calls.append(text)
        return ["Malerarbeite", "Wandfliese", "Massse", "Halluzination"]

    line = _line("Malerarbeite an Wandfliese mit Massse", page=3, oz="3.4.5")
    findings = find_typos([[line]], llm_check=llm_check)
    assert calls == ["Malerarbeite an Wandfliese mit Massse"]
    assert findings == [
        TypoFinding("Malerarbeite", 3, "3.4.5", line.text, "malerarbeiten"),
        TypoFinding("Massse", 3, "3.4.5", line.text, "masse"),
    ]


def test_web_check_learns_valid_words_and_reuses_cache() -> None:
    """Cache accepted and rejected web results so each unique word is queried once."""
    calls: list[str] = []
    cache: dict[str, bool] = {}

    def web_check(word: str) -> bool:
        """Accept ``Dämmmaterial`` and reject ``Bettteppich``.

        :param word: suspect token to verify.
        :returns: True if the token is accepted as valid.
        """
        calls.append(word)
        return word.lower() == "dämmmaterial"

    pages = [
        [
            _line("Dämmmaterial und Bettteppich", page=0, oz="1.1"),
            _line("dämmmaterial und bettteppich erneut", page=1, oz="1.2"),
        ]
    ]
    findings = find_typos(pages, web_check=web_check, cache=cache)
    assert calls == ["Dämmmaterial", "Bettteppich"]
    assert cache == {"dämmmaterial": True, "bettteppich": False}
    assert [(f.word, f.page, f.oz) for f in findings] == [
        ("Bettteppich", 0, "1.1"),
        ("bettteppich", 1, "1.2"),
    ]

    # A subsequent offline run reuses the learned valid entry from cache.
    offline_after_learn = find_typos(pages, cache=cache)
    assert [f.word for f in offline_after_learn] == ["Bettteppich", "bettteppich"]


def test_real_sample_pdfs_detect_suspects_and_learn_via_web_check() -> None:
    """Run offline detection and cached web validation on real sample LVs."""
    with pymupdf.open(_RAW / "LV_09_Porenbetondach.pdf") as doc:
        roof_pages, _ = extract(doc)
    roof_findings = find_typos(roof_pages)
    assert [(f.word, f.page, f.oz) for f in roof_findings] == [
        ("Passschnitte", 1, "9.2.9"),
        ("Passschnitte", 1, "9.2.9"),
    ]

    web_calls: list[str] = []
    cache: dict[str, bool] = {}

    def accept_known_compounds(word: str) -> bool:
        """Record lookups and validate known German triple-letter compounds.

        :param word: suspect token.
        :returns: True for valid German compounds in the sample PDFs.
        """
        web_calls.append(word)
        return word.lower() in {"passschnitte", "dämmmaterial"}

    assert find_typos(roof_pages, web_check=accept_known_compounds, cache=cache) == []
    assert web_calls == ["Passschnitte"]

    with pymupdf.open(_RAW / "LV_03_Malerarbeiten.pdf") as doc:
        painter_pages, _ = extract(doc)
    painter_findings = find_typos(painter_pages)
    assert [(f.word, f.page, f.oz) for f in painter_findings] == [
        ("Dämmmaterial", 1, "15.1.10"),
    ]
    assert find_typos(painter_pages, web_check=accept_known_compounds, cache=cache) == []
    assert cache == {"passschnitte": True, "dämmmaterial": True}
