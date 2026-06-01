"""Run rendering + OCR off the UI thread so the window stays responsive."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..ocr.engine import get_engine
from ..pdf.renderer import render_document


class OcrWorker(QThread):
    progress = Signal(int, int, str)   # current, total, message
    finished_doc = Signal(object)      # Document
    failed = Signal(str)

    def __init__(self, pdf_path: str, dpi: int, engine_name: str = "rapidocr",
                 lang: str = "ch", parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.dpi = dpi
        self.engine_name = engine_name
        self.lang = lang

    def run(self) -> None:
        try:
            self.progress.emit(0, 0, "Loading OCR engine…")
            engine = get_engine(self.engine_name, lang=self.lang)
            doc = render_document(
                self.pdf_path,
                engine=engine,
                dpi=self.dpi,
                progress=lambda c, t, m: self.progress.emit(c, t, m),
            )
            self.finished_doc.emit(doc)
        except Exception as exc:  # surface to the UI rather than crash the thread
            self.failed.emit(f"{type(exc).__name__}: {exc}")
