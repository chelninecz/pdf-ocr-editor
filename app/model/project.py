"""Persist an edit session to JSON next to the PDF, so work can be resumed.

Rasters are intentionally *not* stored — they are re-rendered from the source PDF
on load. This keeps session files tiny and portable.
"""

from __future__ import annotations

import json

from .document import Document

SESSION_SUFFIX = ".ocr-session.json"


def session_path_for(pdf_path: str) -> str:
    return pdf_path + SESSION_SUFFIX


def save_session(doc: Document, path: str | None = None) -> str:
    path = path or session_path_for(doc.source_path)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc.to_dict(), fh, ensure_ascii=False, indent=2)
    return path


def load_session(path: str, reload_rasters: bool = True) -> Document:
    with open(path, "r", encoding="utf-8") as fh:
        doc = Document.from_dict(json.load(fh))
    if reload_rasters:
        from ..pdf.renderer import reload_rasters as _reload

        _reload(doc)
    return doc
