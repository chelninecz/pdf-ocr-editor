"""Modeless preview of the patched (export-ready) current page.

Shows exactly what ``rebuild_document`` would write: the original drawing with
only the user's edits/erasures applied. Refreshes on demand and on page change.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class PreviewDialog(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Export preview — patched result")
        self.resize(950, 720)

        self._pix: Optional[QPixmap] = None
        self._label = QLabel("Press Refresh to render the current page.")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._label)
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_refresh = QPushButton("Refresh")
        self.info = QLabel("")
        top = QHBoxLayout()
        top.addWidget(self.btn_refresh)
        top.addWidget(self.info, 1)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self._scroll, 1)

    def set_image(self, png_bytes: bytes, caption: str = "") -> None:
        pm = QPixmap()
        pm.loadFromData(png_bytes, "PNG")
        self._pix = pm
        self.info.setText(caption)
        self._apply_scale()

    def set_message(self, text: str) -> None:
        self._pix = None
        self._label.setPixmap(QPixmap())
        self._label.setText(text)

    def _apply_scale(self) -> None:
        if self._pix is None:
            return
        # Fit to the viewport width, keep aspect ratio, allow vertical scroll.
        w = max(200, self._scroll.viewport().width() - 4)
        scaled = self._pix.scaledToWidth(
            min(w, self._pix.width() * 3), Qt.TransformationMode.SmoothTransformation
        )
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_scale()
