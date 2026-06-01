"""Download PP-OCRv5 ONNX models into app/ocr/models/PP-OCRv5/ (with SHA256 check).

Run once during setup/build (needs internet); the resulting files are then bundled
so the app stays fully offline at runtime.

    python scripts/fetch_models.py            # detection + Chinese rec + dict + cls
    python scripts/fetch_models.py --all      # also Russian (eslav) and latin rec
"""

import argparse
import hashlib
import os
import sys
import urllib.request

MS = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0"
DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "app", "ocr", "models", "PP-OCRv5")

# (local_name, url, sha256)
CORE = [
    ("ch_PP-OCRv5_det_mobile.onnx",
     f"{MS}/onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx",
     "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae"),
    ("ch_PP-OCRv5_rec_mobile.onnx",
     f"{MS}/onnx/PP-OCRv5/rec/ch_PP-OCRv5_rec_mobile.onnx",
     "5825fc7ebf84ae7a412be049820b4d86d77620f204a041697b0494669b1742c5"),
    ("ppocrv5_dict.txt",
     f"{MS}/paddle/PP-OCRv5/rec/ch_PP-OCRv5_rec_mobile/ppocrv5_dict.txt",
     None),
    ("ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
     f"{MS}/onnx/PP-OCRv5/cls/ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
     "54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7"),
]

EXTRA = [
    ("eslav_PP-OCRv5_rec_mobile.onnx",
     f"{MS}/onnx/PP-OCRv5/rec/eslav_PP-OCRv5_rec_mobile.onnx",
     "08705d6721849b1347d26187f15a5e362c431963a2a62bfff4feac578c489aab"),
    ("ppocrv5_eslav_dict.txt",
     f"{MS}/paddle/PP-OCRv5/rec/eslav_PP-OCRv5_rec_mobile/ppocrv5_eslav_dict.txt",
     None),
    ("latin_PP-OCRv5_rec_mobile.onnx",
     f"{MS}/onnx/PP-OCRv5/rec/latin_PP-OCRv5_rec_mobile.onnx",
     "b20bd37c168a570f583afbc8cd7925603890efbcdc000a59e22c269d160b5f5a"),
    ("ppocrv5_latin_dict.txt",
     f"{MS}/paddle/PP-OCRv5/rec/latin_PP-OCRv5_rec_mobile/ppocrv5_latin_dict.txt",
     None),
]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name: str, url: str, sha: str) -> None:
    out = os.path.join(DEST, name)
    if os.path.exists(out) and (sha is None or _sha256(out) == sha):
        print(f"  ok (cached)  {name}")
        return
    print(f"  downloading  {name} …", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as fh:
        fh.write(r.read())
    if sha is not None:
        got = _sha256(out)
        if got != sha:
            raise SystemExit(f"SHA256 mismatch for {name}: {got} != {sha}")
    print(f"  done         {name}  ({os.path.getsize(out)/1e6:.1f} MB)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="also fetch Russian/latin rec")
    args = ap.parse_args()
    os.makedirs(DEST, exist_ok=True)
    items = CORE + (EXTRA if args.all else [])
    print(f"Fetching {len(items)} files -> {DEST}")
    for name, url, sha in items:
        fetch(name, url, sha)
    print("All models present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
