"""Reconcile explicitly opened and closed PDF sections using stated position amounts."""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .contradictions import Finding
from .pdf_calculation import _NUMBER
from .pdf_extract import Line

_OPTION = re.compile(
    r"\b(?:Bedarfsposition|Eventualposition|Wahlposition|Alternativposition|optional)\b", re.I
)
_OUT = re.compile(r"\b(?:ohne (?:Gesamtbetrag|Gesamtpreis|GP)|nur (?:EP|Einheitspreis))\b", re.I)
_IN = re.compile(r"\bmit (?:Gesamtbetrag|Gesamtpreis|GP)\b", re.I)


@dataclass
class SectionTotals:
    """Track a single open section and document-wide coverage."""

    section: str = ""
    current: str = ""
    amounts: dict[str, tuple[Decimal, Line] | None] = field(default_factory=dict)
    optional: set[str] = field(default_factory=set)
    included: set[str] = field(default_factory=set)
    excluded: set[str] = field(default_factory=set)
    markers: dict[str, tuple[Line, ...]] = field(default_factory=dict)
    ambiguous: bool = False
    # Suffix of amounts in explanations; empty for a table whose header names no currency.
    currency: str = " EUR"
    stated: int = 0
    checked: int = 0
    findings: list[Finding] = field(default_factory=list)

    def observe(self, row: list[Line], split: bool, left: float, right: float) -> None:
        """Read section boundaries, item identifiers and explicit inclusion markers.

        :param row: cells in horizontal order.
        :param split: whether the section uses a separate quantity row.
        :param left: left edge of the position column.
        :param right: right edge of the amount column header.
        """
        first = row[0].text
        close = re.fullmatch(r"Summe Abschnitt (\d+(?:\.\d+)+)\.", first)
        if not split and close:
            self.stated += 1
            if (
                self.section
                and (split or close[1] == self.section)
                and len(row) == 2
                and abs(row[-1].quad.rect.x1 - right) < 10
                and re.fullmatch(_NUMBER, row[-1].text)
                and len(row[-1].text) <= 18
            ):
                self.reconcile(row)
            self.section = ""
            return
        if abs(row[0].quad.rect.x0 - left) < 5:
            heading = re.fullmatch(r"(\d+\.\d+)" if split else r"Abschnitt (\d+\.\d+)\.", first)
            if heading:
                self.section = heading[1]
                self.current = ""
                self.amounts.clear()
                self.optional.clear()
                self.included.clear()
                self.excluded.clear()
                self.markers.clear()
                self.ambiguous = False
                return
            if self.section and re.fullmatch(r"\d+(?:\.\d+){2,}[A-Za-z]?", first):
                self.ambiguous |= first in self.amounts or first.rsplit(".", 1)[0] != self.section
                self.current = first
                self.amounts[first] = None
        if self.section:
            text = " ".join(cell.text for cell in row)
            if _OPTION.search(text) or _IN.search(text) or _OUT.search(text):
                self.optional.add(self.current)
                label = _OPTION.sub("", text, count=1).strip(" *():-,")
                if _IN.fullmatch(label):
                    self.included.add(self.current)
                if _OUT.fullmatch(label):
                    self.excluded.add(self.current)
                    self.markers[self.current] = tuple(row)
                if not self.current:
                    self.ambiguous = True

    def reconcile(self, row: list[Line]) -> None:
        """Compare one stated subtotal when all included amounts are known.

        :param row: subtotal label and stated EUR amount.
        """
        if (
            self.ambiguous
            or not self.amounts
            or self.included & self.excluded
            or self.optional - self.included - self.excluded
        ):
            return
        members = []
        for oz, amount in self.amounts.items():
            if oz in self.excluded:
                continue
            if amount is None:
                return
            members.append((oz, *amount))
        expected = sum((value for _, value, _ in members), Decimal(0))
        actual = Decimal(row[-1].text.replace(".", "").replace(",", "."))
        self.checked += 1
        if actual != expected:
            terms = " + ".join(f"{value} ({oz})" for oz, value, _ in members) or "0"
            exclusions = (
                " Ohne Gesamtbetrag: " + ", ".join(sorted(self.excluded)) + "."
                if self.excluded
                else ""
            )
            self.findings.append(
                Finding(
                    "section_total",
                    (tuple(row), *((line,) for _, _, line in members), *self.markers.values()),
                    f"Abschnitt {self.section}: {terms} = {expected}{self.currency}. "
                    f"Ausgewiesen: {actual}{self.currency}.{exclusions}",
                    "Welcher Gesamtbetrag gilt für diesen Abschnitt?",
                    "conflict",
                )
            )
