"""Render PDF pages to rasters and drive force-OCR.

"Force-OCR" means we **always** rasterize the page and OCR the image, ignoring
any text layer the source PDF may already contain. That is the whole point: the
existing text layer is assumed unreliable.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import fitz  # PyMuPDF
import numpy as np

from ..model.document import Document, Page
from ..ocr.engine import OcrEngine

DEFAULT_DPI = 300

ProgressCb = Callable[[int, int, str], None]  # (current, total, message)


def render_page_raster(page: "fitz.Page", dpi: int = DEFAULT_DPI) -> np.ndarray:
    """Rasterize one PyMuPDF page to an ``(H, W, 3)`` uint8 RGB array."""
    pix = page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
    arr = np.frombuffer(pix.samples, dtype=np.uint8)
    arr = arr.reshape(pix.height, pix.width, 3)
    return np.ascontiguousarray(arr)


def render_document(
    pdf_path: str,
    engine: Optional[OcrEngine] = None,
    dpi: int = DEFAULT_DPI,
    classify_background: bool = True,
    progress: Optional[ProgressCb] = None,
) -> Document:
    """Open a PDF, rasterize every page, force-OCR it and return a Document.

    Each page's raster is kept on the ``Page`` (in memory) for the GUI and the
    rebuild step. If ``engine`` is None the document is returned with rasters but
    no text lines (useful for a quick preview before OCR).
    """
    doc = Document(source_path=pdf_path)
    with fitz.open(pdf_path) as pdf:
        total = pdf.page_count
        for i, fp in enumerate(pdf):
            if progress:
                progress(i, total, f"Page {i + 1}/{total}: rendering")
            rect = fp.rect
            page = Page(
                index=i,
                width_pt=rect.width,
                height_pt=rect.height,
                dpi=dpi,
            )
            page.raster = render_page_raster(fp, dpi=dpi)
            if engine is not None:
                if progress:
                    progress(i, total, f"Page {i + 1}/{total}: OCR")
                page.lines = engine.recognize(page.raster)
                if classify_background:
                    from .background import classify_lines

                    classify_lines(page.raster, page.lines)
            doc.pages.append(page)
        if progress:
            progress(total, total, "Done")
    return doc


def reload_rasters(doc: Document, dpi_override: Optional[int] = None) -> None:
    """Re-render rasters for a Document loaded from a saved session (.json)."""
    with fitz.open(doc.source_path) as pdf:
        for page in doc.pages:
            fp = pdf[page.index]
            page.raster = render_page_raster(fp, dpi=dpi_override or page.dpi)
