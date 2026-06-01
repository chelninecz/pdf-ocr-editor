"""Fast, OCR-free tests for the core pipeline (background + rebuild).

Run:  python -m pytest tests/  ·  or  python tests/test_pipeline.py
"""

import os
import sys

import fitz
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.model.document import Document, Page, TextLine  # noqa: E402
from app.pdf.background import build_clean_plate, classify_lines  # noqa: E402
from app.pdf.rebuilder import rebuild_document  # noqa: E402


def _line(x0, y0, x1, y1, text="t"):
    return TextLine(quad=((x0, y0), (x1, y0), (x1, y1), (x0, y1)), text=text, score=0.9)


def test_classify_white_vs_colored():
    raster = np.full((200, 400, 3), 255, np.uint8)        # white page
    raster[32:48, 30:170] = 0                              # black text stripe on white
    raster[120:170, 20:380] = (70, 130, 200)              # blue band
    raster[134:156, 30:300] = 255                          # white text stripe on blue

    white = _line(20, 20, 200, 60)
    colored = _line(20, 120, 380, 170)
    classify_lines(raster, [white, colored])

    assert white.erasable is True, "black-on-white must be erasable"
    assert colored.erasable is False, "white-on-blue must NOT be erasable"


def test_clean_plate_erases_only_white_boxes():
    raster = np.full((100, 200, 3), 255, np.uint8)
    raster[10:30, 10:90] = 0          # ink to be erased
    raster[60:80, 10:90] = (200, 50, 50)  # coloured content, must survive

    ln_white = _line(10, 10, 90, 30)
    ln_white.erasable = True
    ln_color = _line(10, 60, 90, 80)
    ln_color.erasable = False
    ln_color.bg_color = (200, 50, 50)

    plate = build_clean_plate(raster, [ln_white, ln_color])
    assert (plate[15:25, 15:85] == 255).all(), "white-bg box should be wiped to bg"
    assert (plate[65:75, 15:85] != 255).any(), "coloured box must be left intact"


def test_rebuild_emits_searchable_cjk(tmp_path=None):
    out_dir = tmp_path or os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(out_dir, "_synthetic.pdf")
    fitz.open().new_page(width=300, height=150)  # noqa: just to ensure fitz works
    # Build a minimal Document with one white page and two lines.
    raster = np.full((300, 600, 3), 255, np.uint8)
    page = Page(index=0, width_pt=300, height_pt=150, dpi=144)
    page.raster = raster
    w = _line(20, 20, 300, 70, "Bracket")
    w.edited_text = "Bracket 支架"
    w.erasable = True
    c = _line(20, 120, 400, 170, "note")
    c.edited_text = "Deburr 去毛刺"
    c.erasable = False
    page.lines = [w, c]
    doc = Document(source_path=src, pages=[page])

    out = rebuild_document(doc, os.path.join(out_dir, "_rebuilt.pdf"))
    pdf = fitz.open(out)
    pg = pdf[0]
    text = pg.get_text()
    assert "支架" in text and "Bracket" in text
    # Coloured line is invisible but still searchable.
    assert len(pg.search_for("去毛刺")) == 1
    assert len(pg.search_for("支架")) == 1
    pdf.close()
    os.remove(out)


if __name__ == "__main__":
    test_classify_white_vs_colored()
    test_clean_plate_erases_only_white_boxes()
    test_rebuild_emits_searchable_cjk()
    print("all tests passed")
