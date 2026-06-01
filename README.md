# PDF OCR Editor

Force-OCR scanned **part drawings** (Simplified Chinese + English), correct the
recognized text in a desktop window, and rebuild a new PDF that keeps the part
image but replaces the text with a real, selectable, searchable text layer.

Runs **fully offline on CPU** and installs **without administrator rights**.

## What it does

1. **Force-OCR** — every page is rasterized and OCR'd from the image. Any existing
   (often unreliable) text layer in the source PDF is ignored on purpose.
2. **Edit** — recognized lines are shown as boxes over the drawing. Edit the text,
   move/resize/add/delete boxes, toggle whether a line is erasable or included.
   Every edit is undoable — **Ctrl+Z** / **Ctrl+Y** (multi-step), so an accidental
   delete is one keystroke to recover.
3. **Rebuild** — a new `*_edited.pdf` is written:
   - text on a **white** background is erased and replaced with crisp vector text;
   - text on a **coloured** background is left visually untouched (the part image
     is preserved) but still gets an invisible searchable text layer;
   - the original file is never modified.

OCR engine: **PP-OCRv5 models on ONNXRuntime** via `rapidocr-onnxruntime` — strong
Simplified/Traditional-Chinese + English recognition, CPU, offline. Detection is
language-agnostic and the recognition model is **swappable per run**:
`ch` (Chinese + English, default), `eslav` (Russian / Cyrillic) or `latin`. The
engine sits behind a small `OcrEngine` interface (`app/ocr/engine.py`) so the whole
engine can also be replaced (Tesseract/EasyOCR) without touching the rest of the
app. If the v5 models are absent it falls back to the v3 models in the wheel.

## Install (development)

Python 3.10–3.14, per-user, no admin:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python scripts\fetch_models.py            # PP-OCRv5 det + Chinese rec + cls
python scripts\fetch_models.py --all      # also Russian (eslav) + latin rec
```

`fetch_models.py` downloads the PP-OCRv5 ONNX models once (with SHA256 checks) into
`app/ocr/models/PP-OCRv5/`; they are then bundled, so the app runs fully offline.
Without them the app falls back to the v3 models in the wheel.

## Run

GUI:

```powershell
python -m app.main            # or: python run_app.py drawing.pdf
```

Workflow: **Open PDF** → **Run OCR** (F5) → edit boxes → **Export PDF** (Ctrl+E).
**Save session** (Ctrl+S) writes a small `.json` next to the PDF so you can resume.

Headless CLI (handy for testing / batch):

```powershell
python -m app.cli ocr      drawing.pdf            # print recognized lines
python -m app.cli rebuild  drawing.pdf            # write drawing_edited.pdf
python -m app.cli rebuild  drawing.pdf --dpi 400 -o out.pdf
```

## Build the portable bundle (no admin to run)

```powershell
.venv\Scripts\pip install pyinstaller
python -m PyInstaller build/pdf-ocr-editor.spec --noconfirm
```

Distribute the whole `dist/PDF-OCR-Editor/` folder; users double-click
`PDF-OCR-Editor.exe`. No Python install, no admin, no internet needed — the OCR
models and the embedded CJK font travel inside the bundle.

## Layout

```
app/
  ocr/        OcrEngine interface + RapidOCR (PP-OCR ONNX) implementation
  pdf/        renderer (force-OCR), background (white/colour + erase), rebuilder
  model/      Document/Page/TextLine + session save/load
  ui/         PySide6 window, zoomable canvas, editable boxes, OCR worker thread
  cli.py      headless interface
build/        PyInstaller spec
tests/        fast OCR-free tests for background + rebuild
scripts/      sample-drawing generator for manual testing
```

## Tuning & limits

- **DPI** (toolbar, default 300) trades accuracy vs speed; raise to 400 for dense
  drawings with thin lines.
- **White/colour threshold** lives in `app/pdf/background.py`
  (`WHITE_MIN_LUMA`, `WHITE_MAX_CHROMA`, `BG_UNIFORM_MAX_STD`).
- **Nicer CJK glyphs**: drop a `NotoSansCJKsc-Regular.otf` in `app/fonts/` and set
  `CJK_FONT_FILE` in `app/pdf/rebuilder.py`; otherwise PyMuPDF's built-in
  `china-s` font is used.
- **OCR models / language**: default is **PP-OCRv5 / ch** (Chinese + English).
  Real drawings often carry **Russian** text (e.g. EAC energy labels) — the `ch`
  model can't read Cyrillic, so switch the **Lang** selector (toolbar) or
  `--lang eslav` (CLI) and re-run OCR for those pages; detection is shared, only
  recognition changes. `latin` is available for Latin-only documents.
- Known hard cases (edit manually): vertical/rotated CJK, GD&T / tolerance symbols,
  the ⌀ diameter sign. Exact CAD fonts are not reproduced — the goal is correct,
  legible, searchable text.
- Requires a CPU with AVX (any modern laptop).
