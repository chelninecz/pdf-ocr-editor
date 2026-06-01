"""PyInstaller / double-click entry point.

Kept at the repo root so it can be run as a top-level script (absolute imports),
unlike ``app/main.py`` which uses package-relative imports.
"""

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
