"""Rebuild a new PDF from edited text lines.

Each output page is: a *clean-plate* raster of the original drawing (old text on
white backgrounds erased, the part geometry and any coloured text untouched) with
a **real, selectable, searchable** text layer drawn on top using an embedded CJK
font. Erasable lines get visible vector text in place of the old pixels; coloured
lines keep their original pixels and receive an invisible text layer so the
corrected text is still selectable and searchable.

The original file is never modified — output goes to ``<name>_edited.pdf``.
"""

from __future__ import annotations

import os
from typing import Optional

import fitz  # PyMuPDF
import numpy as np

from ..model.document import Document, Page, TextLine
from .background import build_clean_plate

# Built-in PyMuPDF font: Droid Sans Fallback, full Simplified-Chinese + Latin
# coverage, embedded automatically. Swap to a Noto Sans CJK .otf via CJK_FONT_FILE
# for nicer glyphs without changing anything else here.
CJK_FONT_NAME = "china-s"
CJK_FONT_FILE: Optional[str] = None

# How to treat lines on coloured / non-erasable backgrounds.
#   "invisible" — keep original pixels, add a hidden searchable text layer (default)
#   "visible"   — draw the text on top of the original pixels
#   "skip"      — don't emit any text for these lines
COLORED_TEXT_MODE = "invisible"

_RENDER_INVISIBLE = 3  # PDF text render mode: no fill, no stroke


def _load_font() -> "fitz.Font":
    if CJK_FONT_FILE and os.path.exists(CJK_FONT_FILE):
        return fitz.Font(fontfile=CJK_FONT_FILE)
    return fitz.Font(CJK_FONT_NAME)


def _pixmap_from_array(arr: np.ndarray) -> "fitz.Pixmap":
    h, w = arr.shape[:2]
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    return fitz.Pixmap(fitz.csRGB, w, h, arr.tobytes(), False)


def _fit_fontsize(font: "fitz.Font", text: str, box_w_pt: float, box_h_pt: float) -> float:
    """Largest font size whose text fits the box in both height and width."""
    fs = max(2.0, box_h_pt * 0.80)
    if not text:
        return fs
    length = font.text_length(text, fontsize=fs)
    if length > box_w_pt and length > 0:
        fs *= box_w_pt / length
    return max(2.0, fs)


def _place_line(
    visible_tw: "fitz.TextWriter",
    hidden_tw: "fitz.TextWriter",
    font: "fitz.Font",
    line: TextLine,
    scale: float,
) -> str:
    """Append one line's text to the visible or hidden TextWriter.

    Returns which writer received text: "visible", "hidden", or "" (nothing).
    """
    text = line.edited_text.strip()
    if not text:
        return ""
    if not line.erasable and COLORED_TEXT_MODE == "skip":
        return ""

    x0, y0, x1, y1 = (c / scale for c in line.bbox)  # px -> pt
    box_w_pt = x1 - x0
    box_h_pt = y1 - y0
    fs = _fit_fontsize(font, text, box_w_pt, box_h_pt)
    # Baseline near the bottom of the box, leaving room for descenders.
    baseline = fitz.Point(x0, y1 - box_h_pt * 0.18)

    if line.erasable or COLORED_TEXT_MODE == "visible":
        visible_tw.append(baseline, text, font=font, fontsize=fs)
        return "visible"
    # invisible searchable layer over coloured background
    hidden_tw.append(baseline, text, font=font, fontsize=fs)
    return "hidden"


def _norm_color(rgb) -> tuple:
    return tuple(max(0.0, min(1.0, c / 255.0)) for c in rgb)


def rebuild_page(out_pdf: "fitz.Document", page: Page, font: "fitz.Font") -> None:
    if page.raster is None:
        raise ValueError(f"Page {page.index} has no raster; re-render before rebuild.")

    plate = build_clean_plate(page.raster, page.lines)
    new_page = out_pdf.new_page(width=page.width_pt, height=page.height_pt)
    rect = fitz.Rect(0, 0, page.width_pt, page.height_pt)
    new_page.insert_image(rect, pixmap=_pixmap_from_array(plate))

    visible_tw = fitz.TextWriter(rect)
    hidden_tw = fitz.TextWriter(rect)
    # Track a representative colour for the visible layer (most lines are black).
    visible_color = (0, 0, 0)
    n_visible = n_hidden = 0
    for line in page.lines:
        if not line.enabled:
            continue
        if line.erasable:
            visible_color = line.color
        where = _place_line(visible_tw, hidden_tw, font, line, page.scale)
        n_visible += where == "visible"
        n_hidden += where == "hidden"

    # write_text raises on an empty writer, so only flush ones that got text.
    if n_visible:
        visible_tw.write_text(new_page, color=_norm_color(visible_color))
    if n_hidden:
        hidden_tw.write_text(new_page, render_mode=_RENDER_INVISIBLE)


def rebuild_document(doc: Document, out_path: Optional[str] = None) -> str:
    """Build the edited PDF and return its path."""
    if out_path is None:
        base, _ = os.path.splitext(doc.source_path)
        out_path = base + "_edited.pdf"

    font = _load_font()
    out_pdf = fitz.open()
    try:
        for page in doc.pages:
            rebuild_page(out_pdf, page, font)
        out_pdf.save(out_path, deflate=True, garbage=3)
    finally:
        out_pdf.close()
    return out_path
