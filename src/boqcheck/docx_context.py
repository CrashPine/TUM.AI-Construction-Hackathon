"""Read Word body text as supporting evidence in document order."""

import re
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class _BodyBuilder(ET.TreeBuilder):
    """Parse OOXML without document type declarations."""

    def doctype(self, name: str, pubid: str, system: str) -> None:
        """Reject DTDs before expanding their content.

        :param name: document type.
        :param pubid: public identifier.
        :param system: system identifier.
        :raises ValueError: whenever a document type is declared.
        """
        raise ValueError("DTD in DOCX nicht unterstützt.")


def _text(p: ET.Element) -> str:
    """Read visible text runs with Word tab and break boundaries.

    :param p: source paragraph.
    :returns: plain text.
    """
    return "".join(
        (node.text or "") if node.tag == _W + "t" else " "
        for node in p.iter()
        if node.tag in (_W + "t", _W + "br", _W + "tab")
    ).strip()


def _has_text(block: ET.Element) -> bool:
    """Tell whether a skipped block holds visible text or embedded content.

    :param block: body or cell element the reader does not extract.
    :returns: whether skipping it hides content from the comparison.
    """
    return any(
        node.tag == _W + "altChunk" or (node.tag == _W + "t" and (node.text or "").strip())
        for node in block.iter()
    )


def read_context(data: bytes) -> tuple[list[dict], int]:
    """Extract body paragraphs and top-level table cells with stable source references.

    Content controls, nested tables and embedded chunks are not extracted; they are counted
    so that the comparison can say which parts it did not assess.

    :param data: complete DOCX bytes.
    :returns: nonempty excerpts in body order and the number of skipped blocks with content.
    :raises ValueError: if the document cannot be imported or has no supported text.
    """
    try:
        with ZipFile(BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 8_000_000:
                raise ValueError("DOCX-Dokumenttext zu groß.")
            root = ET.fromstring(archive.read(info), parser=ET.XMLParser(target=_BodyBuilder()))
    except (BadZipFile, KeyError, ET.ParseError, RuntimeError, OSError) as error:
        raise ValueError("DOCX-Dokumenttext nicht lesbar.") from error
    body = root.find(_W + "body")
    if body is None:
        raise ValueError("DOCX ohne Dokumentkörper.")
    entries = []
    paragraph = table = unread = 0
    for block in body:
        if block.tag == _W + "p":
            paragraph += 1
            text = _text(block)
            if text:
                style = block.find(f"{_W}pPr/{_W}pStyle")
                title = style.get(_W + "val", "") if style is not None else ""
                label = (
                    "Überschrift"
                    if re.fullmatch(r"(Heading|Überschrift)\s*[1-9]", title, re.I)
                    else "Absatz"
                )
                entries.append(
                    {"id": f"P{paragraph}", "reference": f"{label} {paragraph}", "text": text}
                )
        elif block.tag == _W + "tbl":
            table += 1
            for row, tr in enumerate(block.findall(_W + "tr"), 1):
                unread += sum(_has_text(child) for child in tr if child.tag != _W + "tc")
                for col, tc in enumerate(tr.findall(_W + "tc"), 1):
                    unread += sum(_has_text(child) for child in tc if child.tag != _W + "p")
                    text = "\n".join(filter(None, map(_text, tc.findall(_W + "p"))))
                    if text:
                        entries.append(
                            {
                                "id": f"T{table}R{row}C{col}",
                                "reference": f"Tabelle {table}, Zeile {row}, Zelle {col}",
                                "text": text,
                            }
                        )
        else:
            unread += _has_text(block)
    if not entries:
        raise ValueError("Keine lesbaren Absätze oder Tabellenzellen im DOCX.")
    return entries, unread
