"""A movable / resizable box over one OCR line, drawn on the page canvas.

Colour code:
    green  — erasable (white background): old pixels will be replaced
    orange — coloured background: original kept, text added as searchable layer
    grey   — disabled (excluded from the rebuilt PDF)
A red dashed inset marks low-confidence lines that deserve a human look.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from ..model.document import TextLine

LOW_CONF = 0.6
HANDLE = 9.0  # handle hit size in scene px

_COL_ERASABLE = QColor(40, 170, 70)
_COL_COLORED = QColor(230, 140, 30)
_COL_DISABLED = QColor(140, 140, 140)
_COL_LOWCONF = QColor(220, 40, 40)


class TextBoxItem(QGraphicsRectItem):
    def __init__(self, line: TextLine):
        x0, y0, x1, y1 = line.bbox
        super().__init__(0, 0, x1 - x0, y1 - y0)
        self.setPos(x0, y0)
        self.line = line
        self._resize_handle: Optional[str] = None
        self._press_rect: Optional[QRectF] = None
        self._press_pos: Optional[QPointF] = None
        self._press_scene: Optional[QPointF] = None
        self._moved = False

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        # Callbacks wired up by the canvas.
        self.on_geometry_changed: Callable[[TextLine], None] = lambda ln: None
        self.on_activated: Callable[[TextLine], None] = lambda ln: None
        self.on_edit_began: Callable[[], None] = lambda: None

    # -- model sync -------------------------------------------------------
    def scene_rect(self) -> QRectF:
        return QRectF(self.pos(), self.rect().size())

    def commit_geometry(self) -> None:
        r = self.scene_rect()
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
        self.line.quad = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        self.on_geometry_changed(self.line)

    def refresh_style(self) -> None:
        self.update()

    # -- painting ---------------------------------------------------------
    def _base_color(self) -> QColor:
        if not self.line.enabled:
            return _COL_DISABLED
        return _COL_ERASABLE if self.line.erasable else _COL_COLORED

    def paint(self, painter, option, widget=None):
        color = self._base_color()
        r = self.rect()

        fill = QColor(color)
        fill.setAlpha(60 if self.isSelected() else 28)
        painter.setBrush(QBrush(fill))
        pen = QPen(color, 2.0 if self.isSelected() else 1.4)
        if not self.line.enabled:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(r)

        if self.line.enabled and self.line.score < LOW_CONF:
            lp = QPen(_COL_LOWCONF, 1.0, Qt.PenStyle.DashLine)
            painter.setPen(lp)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r.adjusted(2, 2, -2, -2))

        if self.isSelected():
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            for pt in self._handle_points().values():
                painter.drawRect(QRectF(pt.x() - 3, pt.y() - 3, 6, 6))

    # -- handles / resize -------------------------------------------------
    def _handle_points(self) -> dict:
        r = self.rect()
        return {
            "tl": r.topLeft(), "tr": r.topRight(),
            "bl": r.bottomLeft(), "br": r.bottomRight(),
            "t": QPointF(r.center().x(), r.top()),
            "b": QPointF(r.center().x(), r.bottom()),
            "l": QPointF(r.left(), r.center().y()),
            "r": QPointF(r.right(), r.center().y()),
        }

    def _handle_at(self, pos: QPointF) -> Optional[str]:
        for name, pt in self._handle_points().items():
            if (abs(pos.x() - pt.x()) <= HANDLE) and (abs(pos.y() - pt.y()) <= HANDLE):
                return name
        return None

    def hoverMoveEvent(self, event):
        handle = self._handle_at(event.pos()) if self.isSelected() else None
        cursors = {
            "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
            "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
            "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
        }
        self.setCursor(cursors.get(handle, Qt.CursorShape.SizeAllCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self._moved = False
        self._resize_handle = self._handle_at(event.pos()) if self.isSelected() else None
        if self._resize_handle:
            self._press_rect = QRectF(self.rect())
            self._press_pos = QPointF(self.pos())
            self._press_scene = event.scenePos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._moved:
            # First actual drag of this gesture -> let the window snapshot for undo.
            self._moved = True
            self.on_edit_began()
        if not self._resize_handle:
            super().mouseMoveEvent(event)
            return
        d = event.scenePos() - self._press_scene
        r = QRectF(self._press_rect)
        h = self._resize_handle
        if "l" in h:
            r.setLeft(r.left() + d.x())
        if "r" in h:
            r.setRight(r.right() + d.x())
        if "t" in h:
            r.setTop(r.top() + d.y())
        if "b" in h:
            r.setBottom(r.bottom() + d.y())
        r = r.normalized()
        if r.width() < 4 or r.height() < 4:
            return
        # Keep pos fixed; rect carries the new geometry in local coords.
        self.prepareGeometryChange()
        self.setRect(r)

    def mouseReleaseEvent(self, event):
        was_resizing = bool(self._resize_handle)
        self._resize_handle = None
        super().mouseReleaseEvent(event)
        # Normalize: fold any pos offset from moving back into a clean rect.
        self.commit_geometry()
        if was_resizing:
            event.accept()

    def mouseDoubleClickEvent(self, event):
        self.on_activated(self.line)
        super().mouseDoubleClickEvent(event)
