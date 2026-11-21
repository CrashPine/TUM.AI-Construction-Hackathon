"""Exercise summary hierarchy, tax and carried-total checks on the priced PDFs."""

from dataclasses import replace
from functools import cache
from pathlib import Path

import pymupdf
import pytest

from boqcheck.pdf_extract import Line, extract
from boqcheck.pdf_hierarchy_totals import hierarchy_totals

_RAW = Path(__file__).resolve().parents[1] / "data/raw"
_ABGABE = "Abgabe LV.pdf"
_ANGEBOT = "Angebot AN24-0305.pdf"


@cache
def _extract(name: str) -> tuple[tuple[Line, ...], ...]:
    """Extract a sample PDF once.

    :param name: file name in ``data/raw``.
    :return: immutable cells per page.
    """
    with pymupdf.open(_RAW / name) as document:
        pages, _ = extract(document)
    return tuple(tuple(page) for page in pages)


def _pages(name: str) -> list[list[Line]]:
    """Return a mutable copy of a sample PDF's cells.

    :param name: file name in ``data/raw``.
    :return: cells per page.
    """
    return [list(page) for page in _extract(name)]


def _index(page: list[Line], text: str, below: float = 0) -> int:
    """Find the single cell with a text.

    :param page: cells of one page.
    :param text: exact cell text.
    :param below: smallest top coordinate of the cell.
    :return: index of the cell.
    """
    (i,) = (i for i, cell in enumerate(page) if cell.text == text and cell.quad.rect.y0 >= below)
    return i


@pytest.mark.parametrize(("name", "count"), [(_ABGABE, 12), (_ANGEBOT, 43)])
def test_source_hierarchy_reconciles(name: str, count: int) -> None:
    """Check every stated hierarchy total of both priced PDFs without a finding.

    :param name: sample PDF.
    :param count: stated hierarchy totals in the document.
    """
    assert hierarchy_totals(_pages(name)) == ([], count, count)


@pytest.mark.parametrize(
    ("name", "page", "old", "new", "count"),
    [
        (_ABGABE, 90, "71.085,91", "71.085,90", 2),
        (_ABGABE, 90, "835.804,22", "835.804,23", 2),
        (_ABGABE, 90, "158.802,80", "158.802,81", 2),
        (_ANGEBOT, 10, "270.210,89", "270.210,88", 2),
        (_ANGEBOT, 10, "207.275,50", "207.275,51", 2),
        (_ANGEBOT, 26, "503.276,00", "503.276,01", 2),
        (_ANGEBOT, 26, "988.913,89", "988.913,90", 2),
        (_ANGEBOT, 26, "187.893,64", "187.893,65", 2),
        (_ANGEBOT, 1, "92.497,50", "92.497,51", 1),
    ],
)
def test_changed_total(name: str, page: int, old: str, new: str, count: int) -> None:
    """Report each stated total that no longer matches its stated operands.

    :param name: sample PDF.
    :param page: page index of the changed amount.
    :param old: source amount.
    :param new: amount written in memory.
    :param count: checks that use the changed amount and now differ.
    """
    pages = _pages(name)
    i = _index(pages[page], old)
    pages[page][i] = changed = replace(pages[page][i], text=new)
    findings, checked, stated = hierarchy_totals(pages)
    assert len(findings) == count and checked == stated
    assert all(f.kind == "hierarchy_total" and f.status == "conflict" for f in findings)
    assert all(any(changed in passage for passage in f.passages) for f in findings)
    assert any(new.replace(".", "").replace(",", ".") in f.explanation for f in findings)


@pytest.mark.parametrize(
    ("name", "page", "texts", "checked", "stated", "below"),
    [
        (_ANGEBOT, 10, ("166,00",), 41, 43, 400),
        (_ANGEBOT, 26, ("19,00 %",), 42, 43, 0),
        (_ANGEBOT, 10, ("Summe Abschnitt 2.4. Prüfungen", "2.887,50"), 41, 42, 0),
        (_ANGEBOT, 1, ("Übertrag:", "92.497,50"), 42, 43, 0),
        (_ABGABE, 90, ("1.3", "4.353,60"), 11, 12, 0),
    ],
)
def test_incomplete_evidence(
    name: str, page: int, texts: tuple[str, ...], checked: int, stated: int, below: float
) -> None:
    """Abstain when a wrapped amount, tax rate, member row or carried counterpart is missing.

    :param name: sample PDF.
    :param page: page index of the removed cells.
    :param texts: removed cell texts.
    :param checked: completed checks after the removal.
    :param stated: stated totals after the removal.
    :param below: smallest top coordinate of the removed cells.
    """
    pages = _pages(name)
    for text in texts:
        del pages[page][_index(pages[page], text, below)]
    assert hierarchy_totals(pages) == ([], checked, stated)


def test_carried_total_needs_next_page() -> None:
    """Pair carried totals by page number, not by position in the page list."""
    pages = _pages(_ANGEBOT)
    del pages[4]
    assert hierarchy_totals(pages) == ([], 41, 42)


def test_ambiguous_carried_total() -> None:
    """Abstain when a page states two incoming carried totals."""
    pages = _pages(_ANGEBOT)
    pages[1].append(pages[1][_index(pages[1], "Übertrag:")])
    assert hierarchy_totals(pages) == ([], 42, 43)
