"""GUI entry point. Run with:  python -m app.main"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def _selftest(result_path: str) -> int:
    """Prove the frozen bundle can load the OCR engine + models + Qt, then exit.

    Writes a result line to ``result_path`` (works even in a windowed/no-console
    build) so an external check can confirm success without a visible window.
    """
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import numpy as np

    from .ocr.engine import get_engine

    engine = get_engine()
    lines = engine.recognize(np.full((64, 256, 3), 255, np.uint8))
    version = getattr(engine, "model_version", "?")
    app = QApplication.instance() or QApplication([])
    _ = MainWindow()  # constructs every widget -> proves Qt plugins are bundled
    with open(result_path, "w", encoding="utf-8") as fh:
        fh.write(f"OK ocr_ok=1 model={version} lines={len(lines)} qt={app is not None}\n")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        idx = sys.argv.index("--selftest")
        out = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "selftest_result.txt"
        return _selftest(out)

    app = QApplication(sys.argv)
    app.setApplicationName("PDF OCR Editor")
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        from .pdf.renderer import render_document
        try:
            win.doc = render_document(sys.argv[1], engine=None, dpi=win.dpi)
            win._reload_ui()
        except Exception:
            pass
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
