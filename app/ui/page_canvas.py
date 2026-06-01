"""Zoomable canvas showing a page raster with editable text boxes on top."""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QRubberBand,
)

from ..model.document import Page, TextLine
from .qimage_utils import ndarray_to_qpixmap
from .text_box_item import TextBoxItem


class PageCanvas(QGraphicsView):
    lineSelected = Signal(object)      # TextLine or None
    lineActivated = Signal(object)     # double-clicked TextLine
    geometryChanged = Signal(object)   # TextLine whose box moved/resized
    boxAdded = Signal(object)          # newly created TextLine
    editBegan = Signal()               # a move/resize gesture started (for undo)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._items: Dict[int, TextBoxItem] = {}  # id(line) -> item
        self._page: Optional[Page] = None

        self._add_mode = False
        self._rubber: Optional[QRubberBand] = None
        self._rubber_origin = None
        self._pending_fit = False

        self._scene.selectionChanged.connect(self._on_selection_changed)

    # -- page loading -----------------------------------------------------
    def set_page(self, page: Optional[Page], keep_view: bool = False) -> None:
        """Show ``page``. ``keep_view`` preserves the current zoom/scroll (used by
        undo/redo so an accidental delete doesn't also reset the viewport)."""
        self._scene.clear()
        self._items.clear()
        self._pixmap_item = None
        self._page = page
        if page is None or page.raster is None:
            return
        pm = ndarray_to_qpixmap(page.raster)
        self._pixmap_item = self._scene.addPixmap(pm)
        self._pixmap_item.setZValue(-1)
        self._scene.setSceneRect(QRectF(pm.rect()))
        for line in page.lines:
            self._add_item(line)
        if keep_view:
            return  # same-size page; the existing view transform stays valid
        if self.isVisible():
            self.fit()
        else:
            self._pending_fit = True  # view not sized yet; fit on first show

    def _add_item(self, line: TextLine) -> TextBoxItem:
        item = TextBoxItem(line)
        item.on_geometry_changed = self.geometryChanged.emit
        item.on_activated = self.lineActivated.emit
        item.on_edit_began = self.editBegan.emit
        self._scene.addItem(item)
        self._items[id(line)] = item
        return item

    def refresh_styles(self) -> None:
        for item in self._items.values():
            item.refresh_style()

    def select_line(self, line: Optional[TextLine]) -> None:
        self._scene.blockSignals(True)
        for item in self._items.values():
            item.setSelected(False)
        if line is not None and id(line) in self._items:
            item = self._items[id(line)]
            item.setSelected(True)
            self.ensureVisible(item)
        self._scene.blockSignals(False)
        self.lineSelected.emit(line)

    # -- zoom -------------------------------------------------------------
    def fit(self) -> None:
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_fit:
            self._pending_fit = False
            self.fit()

    def zoom(self, factor: float) -> None:
        self.scale(factor, factor)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
            event.accept()
        else:
            super().wheelEvent(event)

    # -- add-box mode -----------------------------------------------------
    def set_add_mode(self, on: bool) -> None:
        self._add_mode = on
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag if on else QGraphicsView.DragMode.ScrollHandDrag
        )
        self.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        if self._add_mode and event.button() == Qt.MouseButton.LeftButton:
            self._rubber_origin = event.position().toPoint()
            self._rubber = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
            self._rubber.setGeometry(QRectF(self._rubber_origin, self._rubber_origin).toRect())
            self._rubber.show()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._add_mode and self._rubber is not None:
            rect = QRectF(self._rubber_origin, event.position().toPoint()).normalized().toRect()
            self._rubber.setGeometry(rect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._add_mode and self._rubber is not None:
            view_rect = self._rubber.geometry()
            self._rubber.hide()
            self._rubber = None
            scene_rect = self.mapToScene(view_rect).boundingRect()
            self._create_box(scene_rect)
            self.set_add_mode(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _create_box(self, r: QRectF) -> None:
        if self._page is None or r.width() < 4 or r.height() < 4:
            return
        x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
        line = TextLine(
            quad=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
            text="",
            score=1.0,
            erasable=True,
        )
        self._page.lines.append(line)
        self._add_item(line)
        self.boxAdded.emit(line)
        self.select_line(line)

    # -- selection --------------------------------------------------------
    def _on_selection_changed(self) -> None:
        items = self._scene.selectedItems()
        line = None
        for it in items:
            if isinstance(it, TextBoxItem):
                line = it.line
                break
        self.lineSelected.emit(line)
