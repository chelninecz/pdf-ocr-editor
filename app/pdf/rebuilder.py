"""Rebuild a new PDF by patching ONLY the words the user changed.

Philosophy: the output must be the **original drawing, untouched**, except where
the user actually edited or deleted text. So we open the original PDF and, per
page, only:

* **edited** line  -> cover the old word with its background colour, draw the new
  text on top (real, selectable vector text with an embedded CJK font);
* **deleted** line (``enabled == False`` or text cleared) -> cover the old word,
  draw nothing;
* **unchanged** line -> do nothing at all — the original pixels/vectors stay.

This means correctly-printed original text (e.g. Russian energy-label text that an
OCR model can't read well) is preserved exactly, and only deliberate edits appear.
The original file is never modified — output goes to ``<name>_edited.pdf``.
"""

from __future__ import annotations

import os
from typing import List, Optional

import fitz  # PyMuPDF

from ..model.document import Document, Page, TextLine

# Built-in PyMuPDF CJK font (Droid Sans Fallback): full Simplified-Chinese + Latin
# coverage, embedded automatically. Set CJK_FONT_FILE to a Noto Sans CJK .otf for
# nicer glyphs without other changes.
CJK_FONT_NAME = "china-s"
CJK_FONT_FILE: Optional[str] = os.path.join(os.path.dirname(__file__), "..", "fonts", "NotoSansCJKsc-Regular.otf")

# How far (in points) to grow each cover rectangle so it swallows anti-aliasing
# fringe around the original glyphs.
COVER_PAD_PT = 1.2


def _load_font() -> "fitz.Font":
    if CJK_FONT_FILE and os.path.exists(CJK_FONT_FILE):
        return fitz.Font(fontfile=CJK_FONT_FILE)
    return fitz.Font(CJK_FONT_NAME)


def _norm(rgb) -> tuple:
    return tuple(max(0.0, min(1.0, c / 255.0)) for c in rgb)


def change_kind(line: TextLine) -> str:
    """Classify a line as 'edit', 'erase' or 'none' for the patch step."""
    if not line.enabled:
        return "erase"
    new = line.edited_text.strip()
    old = line.text.strip()
    if not new and old:
        return "erase"   # user cleared the text
    if new and new != old:
        return "edit"
    return "none"


def _fit_fontsize(font: "fitz.Font", text: str, box_w_pt: float, box_h_pt: float) -> float:
    """Largest font size whose text fits the box in both height and width."""
    fs = max(2.0, box_h_pt * 0.80)
    if not text:
        return fs
    length = font.text_length(text, fontsize=fs)
    if length > box_w_pt and length > 0:
        fs *= box_w_pt / length
    return max(2.0, fs)


def _line_rect(line: TextLine, scale: float, page_rect: "fitz.Rect") -> "fitz.Rect":
    """Map a line's pixel bbox to a padded PDF-point rect, clipped to the page."""
    x0, y0, x1, y1 = line.bbox
    rect = fitz.Rect(x0 / scale, y0 / scale, x1 / scale, y1 / scale)
    rect = fitz.Rect(
        rect.x0 - COVER_PAD_PT, rect.y0 - COVER_PAD_PT,
        rect.x1 + COVER_PAD_PT, rect.y1 + COVER_PAD_PT,
    )
    return rect & page_rect


def _cover_fill(line: TextLine) -> tuple:
    """Fill colour used to hide the old word: clean white if the line is marked
    erasable (white background), otherwise the sampled background colour."""
    return (1.0, 1.0, 1.0) if line.erasable else _norm(line.bg_color)


def patch_page(page: "fitz.Page", page_model: Page, font: "fitz.Font") -> int:
    """Apply cover/redraw patches to one already-open original page (in place).

    Returns the number of lines changed (edited or erased).
    """
    scale = page_model.scale
    writer = fitz.TextWriter(page.rect)
    n_changed = 0
    n_text = 0
    for line in page_model.lines:
        kind = change_kind(line)
        if kind == "none":
            continue
        n_changed += 1
        rect = _line_rect(line, scale, page.rect)
        # Cover the original word.
        page.draw_rect(rect, color=None, fill=_cover_fill(line))
        if kind == "edit":
            text = line.edited_text.strip()
            fs = _fit_fontsize(font, text, rect.width, rect.height)
            baseline = fitz.Point(rect.x0 + COVER_PAD_PT, rect.y1 - rect.height * 0.18)
            writer.append(baseline, text, font=font, fontsize=fs)
            n_text += 1
    if n_text:
        # Black is the right default for engineering text; original colour is kept
        # for everything we did not touch.
        writer.write_text(page, color=(0, 0, 0))
    return n_changed


def rebuild_document(doc: Document, out_path: Optional[str] = None) -> str:
    """Patch the original PDF with the user's edits and return the output path."""
    if out_path is None:
        base, _ = os.path.splitext(doc.source_path)
        out_path = base + "_edited.pdf"

    font = _load_font()
    src = fitz.open(doc.source_path)
    try:
        for page_model in doc.pages:
            patch_page(src[page_model.index], page_model, font)
        src.save(out_path, deflate=True, garbage=3)
    finally:
        src.close()
    return out_path


def render_preview(doc: Document, page_index: int, dpi: int = 150) -> bytes:
    """Render a single patched page to PNG bytes (for the in-app preview)."""
    font = _load_font()
    src = fitz.open(doc.source_path)
    try:
        page = src[page_index]
        patch_page(page, doc.pages[page_index], font)
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return pix.tobytes("png")
    finally:
        src.close()
