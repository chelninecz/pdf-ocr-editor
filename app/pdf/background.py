"""Background classification and the "clean plate".

For every detected line we ask one question: *can the old text be cleanly erased?*
The answer is yes only when the line sits on a near-white, near-uniform background
(typical for a drawing's title block / notes). On coloured or busy backgrounds we
leave the original pixels untouched (per product decision) — the line is still
editable, but only its searchable text layer is written to the rebuilt PDF.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from ..model.document import TextLine

# Thresholds (tuned for 8-bit RGB). A box is "erasable" when its background is
# both bright and low-saturation, i.e. visually white / very light grey.
WHITE_MIN_LUMA = 200      # background brightness 0-255
WHITE_MAX_CHROMA = 28     # max-min channel spread on the background
BG_UNIFORM_MAX_STD = 26   # background must be fairly uniform


def _clamp_bbox(bbox, w: int, h: int) -> Tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    x0 = max(0, min(int(np.floor(x0)), w - 1))
    y0 = max(0, min(int(np.floor(y0)), h - 1))
    x1 = max(x0 + 1, min(int(np.ceil(x1)), w))
    y1 = max(y0 + 1, min(int(np.ceil(y1)), h))
    return x0, y0, x1, y1


_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _analyze_crop(crop: np.ndarray):
    """Return (bg_color, text_color, is_white) for a line crop.

    Background is the *dominant* colour: text strokes are always a pixel minority,
    so the median of the whole crop is the background — robust whether the text is
    darker (black on white) or lighter (white on a coloured band) than its
    background. Text colour is taken from the pixels furthest from that background.
    """
    pix = crop.reshape(-1, 3).astype(np.float32)
    bg = np.median(pix, axis=0)

    dist = np.linalg.norm(pix - bg, axis=1)
    # Refine background from the half of pixels nearest the median, and measure
    # how uniform that background is (catches gradients / lines under the text).
    near = dist <= np.median(dist)
    bg_pixels = pix[near] if near.any() else pix
    bg = np.median(bg_pixels, axis=0)
    bg_uniform_std = float(bg_pixels.std()) if bg_pixels.size else 0.0

    far = dist >= np.quantile(dist, 0.85)
    fg = np.median(pix[far], axis=0) if far.any() else bg

    bg_luma = float(bg @ _LUMA)
    bg_chroma = float(bg.max() - bg.min())

    is_white = (
        bg_luma >= WHITE_MIN_LUMA
        and bg_chroma <= WHITE_MAX_CHROMA
        and bg_uniform_std <= BG_UNIFORM_MAX_STD
    )
    bg_color = tuple(int(round(c)) for c in bg)
    text_color = tuple(int(round(c)) for c in fg)
    return bg_color, text_color, is_white


def classify_lines(raster: np.ndarray, lines: List[TextLine]) -> None:
    """Populate ``erasable``, ``bg_color`` and ``color`` on each line in place."""
    h, w = raster.shape[:2]
    for ln in lines:
        x0, y0, x1, y1 = _clamp_bbox(ln.bbox, w, h)
        crop = raster[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        bg_color, text_color, is_white = _analyze_crop(crop)
        ln.bg_color = bg_color
        ln.color = text_color
        ln.erasable = is_white
