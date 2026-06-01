"""Helpers to bridge numpy rasters and Qt images."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap


def ndarray_to_qpixmap(arr: np.ndarray) -> QPixmap:
    """Convert an (H, W, 3) uint8 RGB array to a QPixmap (copy, so it owns data)."""
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    h, w = arr.shape[:2]
    img = QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img.copy())
