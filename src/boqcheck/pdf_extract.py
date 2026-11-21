"""Extract LV text with page geometry for evidence-backed PDF findings."""

import re
from dataclasses import dataclass

import pymupdf

_OZ = re.compile(r"^(\d+(?:\.\d+){2,}[A-Za-z]?)\.(?:\s|$)")
_LABEL = re.compile(r"^Seite\s*:\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Line:
    """A source line in PDF reading order.

    :ivar page: zero-based physical page index.
    :ivar label: printed page number, if present.
    :ivar oz: current item, if known.
    :ivar text: original extracted line with outer whitespace removed.
    :ivar quad: geometry in unrotated page coordinates.
    """

    page: int
    label: str | None
    oz: str | None
    text: str
    quad: pymupdf.Quad


def extract(document: pymupdf.Document) -> tuple[list[list[Line]], list[int]]:
    """Read text layers and identify pages without selectable text.

    :param document: source PDF.
    :returns: source lines by page and one-based numbers of pages without text.
    """
    pages = []
    skipped = []
    oz = None
    for page in document:
        entries = []
        for block in page.get_text(
            "dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
        )["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"]).strip()
                if text:
                    baseline = line["spans"][0]["origin"][1]
                    quad = pymupdf.recover_line_quad(line)
                    entries.append((baseline, quad.rect.x0, text, quad))

        entries.sort(key=lambda entry: (round(entry[0], 1), entry[1]))
        label = next((match[1] for _, _, text, _ in entries if (match := _LABEL.match(text))), None)
        lines = []
        for _, _, text, quad in entries:
            if match := _OZ.match(text):
                oz = match[1]
            lines.append(Line(page.number, label, oz, text, quad))
        pages.append(lines)
        if not lines:
            skipped.append(page.number + 1)
    return pages, skipped
