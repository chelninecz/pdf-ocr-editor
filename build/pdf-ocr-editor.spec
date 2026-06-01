# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — portable, onedir, no admin needed.

Build from the repo root:
    python -m PyInstaller build/pdf-ocr-editor.spec --noconfirm

Output: dist/PDF-OCR-Editor/  (copy the whole folder; run PDF-OCR-Editor.exe).
The bundle includes the RapidOCR ONNX models and ONNXRuntime libs, so first run
needs no network. PyMuPDF's hook bundles the embedded CJK font ("china-s").
"""

import os

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# SPECPATH is injected by PyInstaller and points at this spec's directory
# (repo/build); the repo root is one level up. Robust regardless of cwd.
ROOT = os.path.dirname(SPECPATH)

datas = []
binaries = []
hiddenimports = []

# RapidOCR ships its v3 ONNX models, the YAML config and the character
# dictionaries as package data — collect them (used as offline fallback).
datas += collect_data_files("rapidocr_onnxruntime")
hiddenimports += collect_submodules("rapidocr_onnxruntime")

# PP-OCRv5 models (det + ch/eslav/latin rec, cls) fetched into app/ocr/models.
_v5 = os.path.join(ROOT, "app", "ocr", "models", "PP-OCRv5")
if os.path.isdir(_v5):
    for fn in os.listdir(_v5):
        datas.append((os.path.join(_v5, fn), "app/ocr/models/PP-OCRv5"))

# Native libraries.
binaries += collect_dynamic_libs("onnxruntime")
binaries += collect_dynamic_libs("shapely")
hiddenimports += ["onnxruntime", "shapely", "pyclipper", "cv2"]

# Optional drop-in CJK font (app/fonts/*.otf). Bundled if present.
_fonts = os.path.join(ROOT, "app", "fonts")
if os.path.isdir(_fonts):
    for fn in os.listdir(_fonts):
        datas.append((os.path.join(_fonts, fn), "app/fonts"))

a = Analysis(
    [os.path.join(ROOT, "run_app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDF-OCR-Editor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app, no console window
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PDF-OCR-Editor",
)
