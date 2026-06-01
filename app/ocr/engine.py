"""OCR engine abstraction.

The rest of the app talks to :class:`OcrEngine` only, so the concrete engine
(RapidOCR / PP-OCRv5 today, Tesseract or EasyOCR tomorrow) can be swapped without
touching the renderer, the rebuilder or the UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

import numpy as np

from ..model.document import TextLine


class OcrEngine(ABC):
    """Recognize text lines in a raster image.

    Implementations must be **offline** and run on CPU. ``recognize`` takes an
    ``(H, W, 3)`` uint8 RGB array and returns one :class:`TextLine` per detected
    line, with ``quad`` in pixel coordinates of the input image.
    """

    name: str = "abstract"

    @abstractmethod
    def recognize(self, image: np.ndarray) -> List[TextLine]:
        ...


def get_engine(name: str = "rapidocr", lang: str = "ch", **kwargs) -> OcrEngine:
    """Factory for the configured engine. Defaults to RapidOCR (PP-OCRv5 ONNX).

    ``lang`` selects the recognition model: ``ch`` (Chinese+English, default),
    ``eslav`` (Russian/Cyrillic) or ``latin``.
    """
    name = (name or "rapidocr").lower()
    if name in ("rapidocr", "ppocr", "paddle", "default"):
        from .rapidocr_engine import RapidOcrEngine

        return RapidOcrEngine(lang=lang, **kwargs)
    raise ValueError(f"Unknown OCR engine: {name!r}")
