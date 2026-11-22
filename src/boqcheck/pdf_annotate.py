"""Write native yellow highlights and nearby PDF comment markers."""

import pymupdf

from .pdf_extract import Line


def annotate(page: pymupdf.Page, passage: tuple[Line, ...], identifier: str, comment: str) -> int:
    """Highlight the passage and place an optional comment marker in free space.

    :param page: source page of the passage.
    :param passage: extracted source geometry and text.
    :param identifier: finding identifier shared with the log.
    :param comment: explanation and counterpart reference.
    :returns: number of annotations written.
    """
    bounds = page.rect * page.derotation_matrix
    quads = [line.quad for line in passage]
    if any(quad.is_empty or not bounds.contains(quad.rect) for quad in quads):
        return 0

    obstacles = [pymupdf.Rect(word[:4]) for word in page.get_text("words")]
    obstacles.extend(pymupdf.Rect(image["bbox"]) for image in page.get_image_info())
    obstacles.extend(
        drawing["rect"]
        for drawing in page.get_drawings()
        if not (
            drawing["type"] == "f"
            and drawing["fill"] == (1, 1, 1)
            and drawing["rect"].get_area() >= 0.95 * bounds.get_area()
        )
    )
    obstacles.extend(annot.rect for annot in page.annots())
    obstacles.extend(widget.rect for widget in page.widgets())
    obstacles.extend(link["from"] for link in page.get_links())

    highlight = page.add_highlight_annot(quads)
    highlight.set_colors(stroke=(1, 1, 0))
    highlight.set_info(title="PUManager", subject=identifier, content=comment)
    highlight.update()
    obstacles.extend(quad.rect for quad in quads)

    anchor = quads[0].rect
    for x in (anchor.x1 + 8, anchor.x0 - 28, bounds.x1 - 26, bounds.x0 + 6):
        marker = pymupdf.Rect(x, anchor.y0, x + 20, anchor.y0 + 20)
        if bounds.contains(marker) and not any(marker.intersects(box) for box in obstacles):
            note = page.add_text_annot(marker.tl, comment, icon="Comment")
            if not bounds.contains(note.rect) or any(
                note.rect.intersects(box) for box in obstacles
            ):
                page.delete_annot(note)
                continue
            note.set_info(title="PUManager", subject=identifier)
            note.update()
            return 2
    return 1
