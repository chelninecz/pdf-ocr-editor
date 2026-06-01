"""RapidOCR engine — PP-OCRv5 models on ONNXRuntime (CPU, fully offline).

Detection + recognition use the PP-OCRv5 ONNX models in ``app/ocr/models/PP-OCRv5``
(fetched by ``scripts/fetch_models.py``); the angle classifier stays on the
package's built-in v2 model (fully compatible, avoids a shape mismatch).

Recognition language is swappable while detection is shared, because the detector
is language-agnostic. ``ch`` (Simplified/Traditional Chinese + English + digits)
is the default; ``eslav`` adds Russian/East-Slavic Cyrillic; ``latin`` covers
Latin scripts. If the v5 models are not present the engine falls back to the
PP-OCRv3 models bundled inside the ``rapidocr-onnxruntime`` wheel.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..model.document import TextLine
from .engine import OcrEngine

# Friendly recognition-language options (value -> label) for the UI/CLI.
REC_LANGS: Dict[str, str] = {
    "ch": "Chinese + English (PP-OCRv5)",
    "eslav": "Russian / Cyrillic (PP-OCRv5)",
    "latin": "Latin scripts (PP-OCRv5)",
}

_DET_MODEL = "ch_PP-OCRv5_det_mobile.onnx"
_REC_MODEL = {
    "ch": "ch_PP-OCRv5_rec_mobile.onnx",
    "eslav": "eslav_PP-OCRv5_rec_mobile.onnx",
    "latin": "latin_PP-OCRv5_rec_mobile.onnx",
}


def _models_dir() -> Path:
    """Locate the bundled PP-OCRv5 model directory (dev and PyInstaller frozen)."""
    if getattr(sys, "frozen", False):  # PyInstaller onedir: data under _internal
        cand = Path(sys._MEIPASS) / "app" / "ocr" / "models" / "PP-OCRv5"  # type: ignore[attr-defined]
        if cand.exists():
            return cand
    return Path(__file__).resolve().parent / "models" / "PP-OCRv5"


class RapidOcrEngine(OcrEngine):
    name = "rapidocr"

    def __init__(
        self,
        lang: str = "ch",
        models_dir: Optional[str] = None,
        use_angle_cls: bool = True,
        text_score: float = 0.4,
        det_model_path: Optional[str] = None,
        rec_model_path: Optional[str] = None,
    ) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self.lang = lang if lang in _REC_MODEL else "ch"
        md = Path(models_dir) if models_dir else _models_dir()
        det = Path(det_model_path) if det_model_path else md / _DET_MODEL
        rec = Path(rec_model_path) if rec_model_path else md / _REC_MODEL[self.lang]

        kwargs = {"text_score": text_score}
        if det.exists() and rec.exists():
            kwargs["det_model_path"] = str(det)
            kwargs["rec_model_path"] = str(rec)
            self.model_version = f"PP-OCRv5/{self.lang}"
        else:
            # v5 models absent -> use the v3 models shipped inside the wheel.
            self.model_version = "PP-OCRv3 (bundled fallback)"
        self._ocr = RapidOCR(**kwargs)
        self._use_cls = use_angle_cls

    def recognize(self, image: np.ndarray) -> List[TextLine]:
        result, _elapse = self._ocr(
            image, use_det=True, use_cls=self._use_cls, use_rec=True
        )
        lines: List[TextLine] = []
        if not result:
            return lines
        for quad_raw, text, score in result:
            quad = tuple((float(p[0]), float(p[1])) for p in quad_raw)
            lines.append(
                TextLine(quad=quad, text=text or "", score=float(score))  # type: ignore[arg-type]
            )
        return lines
