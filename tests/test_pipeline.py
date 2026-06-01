"""Fast, OCR-free tests for the core pipeline (background + patch export).

Run:  python -m pytest tests/  ·  or  python tests/test_pipeline.py
"""

import os
import sys

import fitz
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.model.document import Document, Page, TextLine  # noqa: E402
from app.pdf.background import classify_lines  # noqa: E402
from app.pdf.rebuilder import change_kind, rebuild_document  # noqa: E402


def _line(x0, y0, x1, y1, text="t", edited=None, enabled=True, erasable=True):
    ln = TextLine(quad=((x0, y0), (x1, y0), (x1, y1), (x0, y1)), text=text, score=0.9)
    if edited is not None:
        ln.edited_text = edited
    ln.enabled = enabled
    ln.erasable = erasable
    return ln


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


def test_change_kind():
    assert change_kind(_line(0, 0, 1, 1, "A", edited="A")) == "none"      # untouched
    assert change_kind(_line(0, 0, 1, 1, "A", edited="B")) == "edit"      # text edited
    assert change_kind(_line(0, 0, 1, 1, "A", enabled=False)) == "erase"  # deleted
    assert change_kind(_line(0, 0, 1, 1, "A", edited="")) == "erase"      # cleared
    assert change_kind(_line(0, 0, 1, 1, "", edited="new")) == "edit"     # added box


def test_patch_only_changes_the_original(tmp_path=None):
    """Edited words change, deleted words are erased, everything else is identical."""
    out_dir = str(tmp_path) if tmp_path else os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(out_dir, "_src.pdf")

    # Original "drawing": three words. dpi=72 below => 1 pixel == 1 point.
    d = fitz.open()
    pg = d.new_page(width=300, height=150)
    pg.insert_text((20, 30), "KEEP", fontsize=18)
    pg.insert_text((20, 70), "OLD", fontsize=18)
    pg.insert_text((20, 110), "GONE", fontsize=18)
    d.save(src)
    d.close()

    page = Page(index=0, width_pt=300, height_pt=150, dpi=72)
    page.lines = [
        _line(18, 14, 120, 36, "KEEP", edited="KEEP"),     # unchanged -> untouched
        _line(18, 54, 120, 76, "OLD", edited="新NEW"),      # edited     -> redrawn
        _line(18, 94, 120, 116, "GONE", enabled=False),    # deleted    -> erased
    ]
    doc = Document(source_path=src, pages=[page])

    out = rebuild_document(doc, os.path.join(out_dir, "_out.pdf"))
    rp = fitz.open(out)
    p = rp[0]
    text = p.get_text()
    assert "KEEP" in text, "unchanged original text must be preserved"
    assert len(p.search_for("新NEW")) == 1, "edited text must be drawn (selectable)"

    # The deleted word's region must be blanked (covered white, nothing drawn).
    pix = p.get_pixmap(dpi=72)
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    erased_region = arr[96:114, 22:116, :3]
    assert erased_region.mean() > 250, (
        f"erased region should be blank, mean={erased_region.mean():.1f}")

    # The KEEP word's region must be untouched (still has dark ink).
    keep_region = arr[16:34, 22:90, :3]
    assert keep_region.min() < 120, "unchanged word must still be visible"

    rp.close()
    os.remove(out)
    os.remove(src)


if __name__ == "__main__":
    test_classify_white_vs_colored()
    test_change_kind()
    test_patch_only_changes_the_original()
    print("all tests passed")
