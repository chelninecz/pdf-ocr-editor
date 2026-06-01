"""Headless command-line interface — handy for testing without the GUI.

    python -m app.cli ocr      drawing.pdf            # force-OCR, print lines
    python -m app.cli rebuild  drawing.pdf            # OCR + write drawing_edited.pdf
    python -m app.cli rebuild  drawing.pdf -o out.pdf --dpi 300
"""

from __future__ import annotations

import argparse
import sys

from .model.project import save_session, session_path_for
from .ocr.engine import get_engine
from .pdf.renderer import DEFAULT_DPI, render_document
from .pdf.rebuilder import rebuild_document


def _progress(cur: int, total: int, msg: str) -> None:
    print(f"[{cur}/{total}] {msg}", file=sys.stderr)


def cmd_ocr(args: argparse.Namespace) -> int:
    engine = get_engine(args.engine, lang=args.lang)
    doc = render_document(args.pdf, engine=engine, dpi=args.dpi, progress=_progress)
    for page in doc.pages:
        print(f"\n=== Page {page.index + 1} "
              f"({len(page.lines)} lines, {page.pixel_size[0]}x{page.pixel_size[1]}px) ===")
        for ln in page.lines:
            flag = "white" if ln.erasable else "COLOR"
            print(f"  [{flag} {ln.score:.2f}] {ln.text}")
    if args.save_session:
        path = save_session(doc, session_path_for(args.pdf))
        print(f"\nSession saved: {path}", file=sys.stderr)
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    engine = get_engine(args.engine, lang=args.lang)
    doc = render_document(args.pdf, engine=engine, dpi=args.dpi, progress=_progress)
    out = rebuild_document(doc, args.output)
    print(f"Wrote: {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app.cli", description="PDF OCR editor (headless)")
    p.add_argument("--engine", default="rapidocr", help="OCR engine (default: rapidocr)")
    p.add_argument("--lang", default="ch", choices=["ch", "eslav", "latin"],
                   help="recognition language: ch=CN+EN (default), eslav=Russian, latin")
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="render DPI")
    sub = p.add_subparsers(dest="command", required=True)

    po = sub.add_parser("ocr", help="force-OCR and print recognized text")
    po.add_argument("pdf")
    po.add_argument("--save-session", action="store_true")
    po.set_defaults(func=cmd_ocr)

    pr = sub.add_parser("rebuild", help="force-OCR and write an edited PDF")
    pr.add_argument("pdf")
    pr.add_argument("-o", "--output", default=None)
    pr.set_defaults(func=cmd_rebuild)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
