"""Main application window: page navigator, canvas, line table and edit panel."""

from __future__ import annotations

import copy
import os
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..model.document import Document, Page, TextLine
from ..model.project import load_session, save_session, session_path_for
from ..ocr.rapidocr_engine import REC_LANGS
from ..pdf.rebuilder import change_kind, rebuild_document, render_preview
from ..pdf.renderer import DEFAULT_DPI, render_document
from .ocr_worker import OcrWorker
from .page_canvas import PageCanvas
from .preview_dialog import PreviewDialog
from .text_box_item import LOW_CONF


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF OCR Editor")
        self.resize(1400, 900)

        self.doc: Optional[Document] = None
        self.page_index = 0
        self.dpi = DEFAULT_DPI
        self.lang = "ch"
        self._worker: Optional[OcrWorker] = None
        self._preview: Optional[PreviewDialog] = None
        self._syncing = False

        # Undo/redo: stacks of (page_index, deep-copied line list) snapshots.
        self._undo: List[Tuple[int, List[TextLine]]] = []
        self._redo: List[Tuple[int, List[TextLine]]] = []
        self._text_edit_recorded = False  # coalesce a typing burst into one step
        self._undo_limit = 100

        self.canvas = PageCanvas(self)
        self.setCentralWidget(self.canvas)
        self.canvas.lineSelected.connect(self._on_line_selected)
        self.canvas.lineActivated.connect(lambda ln: self.text_edit.setFocus())
        self.canvas.geometryChanged.connect(lambda ln: None)
        self.canvas.boxAdded.connect(self._on_box_added)
        self.canvas.editBegan.connect(self._record_undo)

        self._build_docks()
        self._build_toolbar()
        self._build_statusbar()
        self._update_actions_enabled()

    # ------------------------------------------------------------------ UI
    def _build_docks(self) -> None:
        # Left: page navigator
        self.page_list = QListWidget()
        self.page_list.currentRowChanged.connect(self._on_page_changed)
        left = QDockWidget("Pages", self)
        left.setWidget(self.page_list)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, left)

        # Right: line table + edit panel
        self.line_table = QTableWidget(0, 3)
        self.line_table.setHorizontalHeaderLabels(["Conf", "Type", "Text"])
        self.line_table.horizontalHeader().setStretchLastSection(True)
        self.line_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.line_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.line_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.line_table.itemSelectionChanged.connect(self._on_table_selection)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("Select a box to edit its text…")
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.info_label = QLabel("—")
        self.info_label.setWordWrap(True)
        self.cb_erasable = QCheckBox("White background (clean erase)")
        self.cb_erasable.setToolTip("If set, the old word is covered with white; "
                                    "otherwise with the sampled background colour.")
        self.cb_erasable.toggled.connect(self._on_erasable_toggled)
        self.cb_enabled = QCheckBox("Keep word in output (uncheck = erase)")
        self.cb_enabled.toggled.connect(self._on_enabled_toggled)
        self.btn_delete = QPushButton("Delete word (erase from drawing)")
        self.btn_delete.clicked.connect(self._delete_current_line)

        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.addWidget(QLabel("Recognized text:"))
        lay.addWidget(self.text_edit, 1)
        lay.addWidget(self.info_label)
        lay.addWidget(self.cb_erasable)
        lay.addWidget(self.cb_enabled)
        lay.addWidget(self.btn_delete)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.addWidget(self.line_table, 1)
        rlay.addWidget(panel, 1)
        rdock = QDockWidget("Lines & Editing", self)
        rdock.setWidget(right)
        rdock.setMinimumWidth(360)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, rdock)

    def _act(self, text, slot, shortcut=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        return a

    def _build_toolbar(self) -> None:
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        self.act_open = self._act("Open PDF", self.open_pdf, "Ctrl+O")
        self.act_ocr = self._act("Run OCR", self.run_ocr, "F5")
        self.act_undo = self._act("Undo", self.undo, "Ctrl+Z")
        self.act_redo = self._act("Redo", self.redo, "Ctrl+Y")
        self.act_redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.act_add = self._act("Add box", lambda: self.canvas.set_add_mode(True), "Ctrl+B")
        self.act_preview = self._act("Preview", self.show_preview, "Ctrl+P")
        self.act_export = self._act("Export PDF", self.export_pdf, "Ctrl+E")
        self.act_save = self._act("Save session", self.save_session, "Ctrl+S")
        self.act_load = self._act("Open session", self.open_session, None)
        tb.addAction(self.act_open)
        tb.addAction(self.act_ocr)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self.act_add)
        tb.addAction(self.act_preview)
        tb.addAction(self.act_export)
        tb.addSeparator()
        tb.addAction(self.act_save)
        tb.addAction(self.act_load)
        tb.addSeparator()

        tb.addWidget(QLabel(" DPI "))
        self.dpi_combo = QComboBox()
        for v in (200, 300, 400):
            self.dpi_combo.addItem(str(v), v)
        self.dpi_combo.setCurrentText(str(self.dpi))
        self.dpi_combo.currentIndexChanged.connect(
            lambda: setattr(self, "dpi", self.dpi_combo.currentData())
        )
        tb.addWidget(self.dpi_combo)

        tb.addWidget(QLabel("  Lang "))
        self.lang_combo = QComboBox()
        for value, label in REC_LANGS.items():
            self.lang_combo.addItem(label, value)
        self.lang_combo.setToolTip("Recognition language (detection is shared). "
                                   "Switch to Russian for Cyrillic labels, then re-run OCR.")
        self.lang_combo.currentIndexChanged.connect(
            lambda: setattr(self, "lang", self.lang_combo.currentData())
        )
        tb.addWidget(self.lang_combo)
        tb.addSeparator()
        tb.addAction(self._act("Zoom +", lambda: self.canvas.zoom(1.25), "Ctrl++"))
        tb.addAction(self._act("Zoom −", lambda: self.canvas.zoom(0.8), "Ctrl+-"))
        tb.addAction(self._act("Fit", self.canvas.fit, "Ctrl+0"))

    def _build_statusbar(self) -> None:
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress)

    def _update_actions_enabled(self) -> None:
        has_doc = self.doc is not None
        busy = self._worker is not None and self._worker.isRunning()
        for a in (self.act_ocr, self.act_add, self.act_preview, self.act_export, self.act_save):
            a.setEnabled(has_doc and not busy)
        self.act_open.setEnabled(not busy)
        self.act_load.setEnabled(not busy)
        self._update_undo_actions()

    # ---------------------------------------------------------------- undo
    def _snapshot(self, page_index: int, lines: List[TextLine]) -> Tuple[int, List[TextLine]]:
        return (page_index, copy.deepcopy(lines))

    def _record_undo(self, pre_lines: Optional[List[TextLine]] = None) -> None:
        """Push the page's pre-change state so the next mutation can be undone.

        ``pre_lines`` lets a caller supply a reconstructed prior state (used by
        'add box', where the mutation has already happened on the live list).
        """
        page = self.current_page
        if page is None:
            return
        lines = pre_lines if pre_lines is not None else page.lines
        self._undo.append(self._snapshot(self.page_index, lines))
        if len(self._undo) > self._undo_limit:
            self._undo.pop(0)
        self._redo.clear()
        self._update_undo_actions()

    def undo(self) -> None:
        if not self._undo or self.doc is None:
            return
        idx, lines = self._undo.pop()
        self._redo.append(self._snapshot(self.page_index, self.current_page.lines))
        self._restore(idx, lines)

    def redo(self) -> None:
        if not self._redo or self.doc is None:
            return
        idx, lines = self._redo.pop()
        self._undo.append(self._snapshot(self.page_index, self.current_page.lines))
        self._restore(idx, lines)

    def _restore(self, idx: int, lines: List[TextLine]) -> None:
        self.doc.pages[idx].lines = lines
        if idx != self.page_index:
            self._syncing = True
            self.page_list.setCurrentRow(idx)
            self._syncing = False
            self.page_index = idx
            self.canvas.set_page(self.doc.pages[idx])          # different page: fit
        else:
            self.canvas.set_page(self.doc.pages[idx], keep_view=True)  # keep zoom
        self._rebuild_line_table()
        self._load_editor(None)
        self._text_edit_recorded = False
        self._update_page_count(idx)
        self._update_undo_actions()

    def _clear_history(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._text_edit_recorded = False
        self._update_undo_actions()

    def _update_undo_actions(self) -> None:
        busy = self._worker is not None and self._worker.isRunning()
        self.act_undo.setEnabled(bool(self._undo) and not busy)
        self.act_redo.setEnabled(bool(self._redo) and not busy)

    def _update_page_count(self, idx: int) -> None:
        if self.doc and 0 <= idx < self.page_list.count():
            self.page_list.item(idx).setText(
                f"Page {idx + 1}  ({len(self.doc.pages[idx].lines)} lines)"
            )

    # -------------------------------------------------------------- actions
    def open_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF files (*.pdf)")
        if not path:
            return
        try:
            # Quick preview: rasters only, no OCR yet.
            self.doc = render_document(path, engine=None, dpi=self.dpi)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))
            return
        self._reload_ui()
        self.statusBar().showMessage(
            f"Loaded {len(self.doc.pages)} page(s). Press Run OCR (F5).", 8000
        )

    def run_ocr(self) -> None:
        if self.doc is None:
            return
        self._worker = OcrWorker(self.doc.source_path, self.dpi, lang=self.lang)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_doc.connect(self._on_ocr_done)
        self._worker.failed.connect(self._on_ocr_failed)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._update_actions_enabled()
        self._worker.start()

    def _on_progress(self, cur: int, total: int, msg: str) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(cur)
        self.statusBar().showMessage(msg)

    def _on_ocr_done(self, doc: Document) -> None:
        self.doc = doc
        self.progress.setVisible(False)
        self._worker = None
        self._reload_ui()
        self._update_actions_enabled()
        self.statusBar().showMessage("OCR complete.", 6000)

    def _on_ocr_failed(self, msg: str) -> None:
        self.progress.setVisible(False)
        self._worker = None
        self._update_actions_enabled()
        QMessageBox.critical(self, "OCR failed", msg)

    def show_preview(self) -> None:
        if self.doc is None:
            return
        if self._preview is None:
            self._preview = PreviewDialog(self)
            self._preview.btn_refresh.clicked.connect(self._refresh_preview)
        self._preview.show()
        self._preview.raise_()
        self._preview.activateWindow()
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._preview is None or self.doc is None or self.current_page is None:
            return
        try:
            self.setCursor(Qt.CursorShape.WaitCursor)
            png = render_preview(self.doc, self.page_index, dpi=150)
        except Exception as exc:
            self._preview.set_message(f"Preview failed:\n{exc}")
            return
        finally:
            self.unsetCursor()
        changed = sum(1 for ln in self.current_page.lines if change_kind(ln) != "none")
        self._preview.set_image(
            png, f"Page {self.page_index + 1} — {changed} change(s) patched; "
                 f"everything else is the original."
        )

    def export_pdf(self) -> None:
        if self.doc is None:
            return
        base, _ = os.path.splitext(self.doc.source_path)
        default = base + "_edited.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Export edited PDF", default, "PDF files (*.pdf)")
        if not path:
            return
        try:
            self.setCursor(Qt.CursorShape.WaitCursor)
            out = rebuild_document(self.doc, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        finally:
            self.unsetCursor()
        QMessageBox.information(self, "Exported", f"Wrote:\n{out}")

    def save_session(self) -> None:
        if self.doc is None:
            return
        path = save_session(self.doc, session_path_for(self.doc.source_path))
        self.statusBar().showMessage(f"Session saved: {path}", 6000)

    def open_session(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open session", "", "Session files (*.json)"
        )
        if not path:
            return
        try:
            self.doc = load_session(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open session failed", str(exc))
            return
        self._reload_ui()
        self.statusBar().showMessage("Session loaded.", 6000)

    # ----------------------------------------------------------- UI refresh
    def _reload_ui(self) -> None:
        self._clear_history()
        self._syncing = True
        self.page_list.clear()
        if self.doc:
            for p in self.doc.pages:
                self.page_list.addItem(f"Page {p.index + 1}  ({len(p.lines)} lines)")
        self._syncing = False
        self.page_index = 0
        if self.doc and self.doc.pages:
            self.page_list.setCurrentRow(0)
        else:
            self.canvas.set_page(None)
        self._update_actions_enabled()

    @property
    def current_page(self) -> Optional[Page]:
        if self.doc and 0 <= self.page_index < len(self.doc.pages):
            return self.doc.pages[self.page_index]
        return None

    def _on_page_changed(self, row: int) -> None:
        if self._syncing or self.doc is None or row < 0:
            return
        self.page_index = row
        self.canvas.set_page(self.current_page)
        self._rebuild_line_table()
        self._load_editor(None)
        if self._preview is not None and self._preview.isVisible():
            self._refresh_preview()

    def _rebuild_line_table(self) -> None:
        self._syncing = True
        page = self.current_page
        self.line_table.setRowCount(0)
        if page:
            self.line_table.setRowCount(len(page.lines))
            for r, ln in enumerate(page.lines):
                self._fill_table_row(r, ln)
        self._syncing = False

    def _fill_table_row(self, r: int, ln: TextLine) -> None:
        conf = QTableWidgetItem(f"{ln.score:.2f}")
        kind = QTableWidgetItem(
            "erase" if not ln.enabled else ("white" if ln.erasable else "color")
        )
        text = QTableWidgetItem(ln.edited_text)
        conf.setData(Qt.ItemDataRole.UserRole, ln)
        if ln.enabled and ln.score < LOW_CONF:
            for it in (conf, kind, text):
                it.setForeground(QColor(200, 30, 30))
        if not ln.enabled:
            for it in (conf, kind, text):
                it.setForeground(QColor(140, 140, 140))
        self.line_table.setItem(r, 0, conf)
        self.line_table.setItem(r, 1, kind)
        self.line_table.setItem(r, 2, text)

    def _row_for_line(self, line: TextLine) -> int:
        for r in range(self.line_table.rowCount()):
            it = self.line_table.item(r, 0)
            if it and it.data(Qt.ItemDataRole.UserRole) is line:
                return r
        return -1

    # ---------------------------------------------------------- selection
    def _on_table_selection(self) -> None:
        if self._syncing:
            return
        items = self.line_table.selectedItems()
        if not items:
            return
        line = self.line_table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        self.canvas.select_line(line)

    def _on_line_selected(self, line: Optional[TextLine]) -> None:
        if self._syncing:
            return
        self._syncing = True
        row = self._row_for_line(line) if line else -1
        if row >= 0:
            self.line_table.selectRow(row)
        else:
            self.line_table.clearSelection()
        self._syncing = False
        self._load_editor(line)

    def _on_box_added(self, line: TextLine) -> None:
        # The box is already in page.lines; record the prior state (without it).
        pre = [ln for ln in self.current_page.lines if ln is not line]
        self._record_undo(pre_lines=pre)
        self._update_page_count(self.page_index)
        self._rebuild_line_table()
        self._on_line_selected(line)
        self.text_edit.setFocus()

    # ------------------------------------------------------------- editor
    def _load_editor(self, line: Optional[TextLine]) -> None:
        self._current_line = line
        self._text_edit_recorded = False  # new selection starts a fresh undo step
        self._syncing = True
        if line is None:
            self.text_edit.setPlainText("")
            self.text_edit.setEnabled(False)
            self.info_label.setText("—")
            self.cb_erasable.setEnabled(False)
            self.cb_enabled.setEnabled(False)
            self.btn_delete.setEnabled(False)
        else:
            self.text_edit.setEnabled(True)
            self.text_edit.setPlainText(line.edited_text)
            kind = "white bg (erasable)" if line.erasable else "coloured bg (kept)"
            self.info_label.setText(
                f"confidence {line.score:.2f} · {kind}\noriginal OCR: {line.text!r}"
            )
            self.cb_erasable.setEnabled(True)
            self.cb_enabled.setEnabled(True)
            self.btn_delete.setEnabled(True)
            self.cb_erasable.setChecked(line.erasable)
            self.cb_enabled.setChecked(line.enabled)
        self._syncing = False

    def _on_text_changed(self) -> None:
        if self._syncing or getattr(self, "_current_line", None) is None:
            return
        if not self._text_edit_recorded:
            self._record_undo()  # snapshot pre-edit text once per typing burst
            self._text_edit_recorded = True
        self._current_line.edited_text = self.text_edit.toPlainText()
        row = self._row_for_line(self._current_line)
        if row >= 0:
            self._syncing = True
            self.line_table.item(row, 2).setText(self._current_line.edited_text)
            self._syncing = False

    def _on_erasable_toggled(self, on: bool) -> None:
        if self._syncing or getattr(self, "_current_line", None) is None:
            return
        self._record_undo()
        self._current_line.erasable = on
        self._refresh_current_line_style()

    def _on_enabled_toggled(self, on: bool) -> None:
        if self._syncing or getattr(self, "_current_line", None) is None:
            return
        self._record_undo()
        self._current_line.enabled = on
        self._refresh_current_line_style()

    def _refresh_current_line_style(self) -> None:
        self.canvas.refresh_styles()
        row = self._row_for_line(self._current_line)
        if row >= 0:
            self._syncing = True
            self._fill_table_row(row, self._current_line)
            self._syncing = False

    def _delete_current_line(self) -> None:
        """Mark the word as deleted: it stays in the model (so its region can be
        erased on export and the action can be undone), but is excluded/erased."""
        line = getattr(self, "_current_line", None)
        if line is None:
            return
        self._record_undo()  # snapshot so an accidental delete is one Ctrl+Z away
        line.enabled = False
        self._refresh_current_line_style()
        self._load_editor(line)  # refresh the panel (checkbox now unchecked)
