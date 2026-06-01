"""Domain model: a document is a list of pages, each holding OCR text lines.

Coordinates convention
----------------------
All geometry (``quad``, ``bbox``) is stored in **pixels of the rendered raster**
for the page, at the page's ``dpi``. Conversion to PDF points happens only at
export time (``points = pixels * 72 / dpi``); keeping pixels here means the GUI,
which displays that same raster, can use the numbers directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Point = Tuple[float, float]
Quad = Tuple[Point, Point, Point, Point]


@dataclass
class TextLine:
    """One detected line of text plus its editable state.

    ``quad`` is the detector's (possibly rotated) 4-point polygon. ``text`` is the
    raw OCR output; ``edited_text`` is what the user sees and what gets written to
    the rebuilt PDF. ``erasable`` is decided by background classification; only
    erasable lines get their pixels whited-out on the clean plate.
    """

    quad: Quad
    text: str
    score: float = 0.0
    edited_text: str = ""
    erasable: bool = False
    enabled: bool = True
    # Estimated original text colour (r, g, b) 0-255, used when redrawing.
    color: Tuple[int, int, int] = (0, 0, 0)
    # Estimated background colour (r, g, b); used to fill the box on the clean plate.
    bg_color: Tuple[int, int, int] = (255, 255, 255)

    def __post_init__(self) -> None:
        if not self.edited_text:
            self.edited_text = self.text

    # -- geometry helpers -------------------------------------------------
    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        """Axis-aligned bounding box (x0, y0, x1, y1) in raster pixels."""
        xs = [p[0] for p in self.quad]
        ys = [p[1] for p in self.quad]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def width(self) -> float:
        x0, _, x1, _ = self.bbox
        return x1 - x0

    @property
    def height(self) -> float:
        _, y0, _, y1 = self.bbox
        return y1 - y0

    # -- (de)serialization ------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "quad": [list(p) for p in self.quad],
            "text": self.text,
            "score": self.score,
            "edited_text": self.edited_text,
            "erasable": self.erasable,
            "enabled": self.enabled,
            "color": list(self.color),
            "bg_color": list(self.bg_color),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TextLine":
        quad = tuple(tuple(p) for p in d["quad"])  # type: ignore[assignment]
        return cls(
            quad=quad,  # type: ignore[arg-type]
            text=d["text"],
            score=d.get("score", 0.0),
            edited_text=d.get("edited_text", d["text"]),
            erasable=d.get("erasable", False),
            enabled=d.get("enabled", True),
            color=tuple(d.get("color", [0, 0, 0])),  # type: ignore[arg-type]
            bg_color=tuple(d.get("bg_color", [255, 255, 255])),  # type: ignore[arg-type]
        )


@dataclass
class Page:
    """A single PDF page, its render parameters and its OCR lines."""

    index: int
    width_pt: float       # original page size in PDF points
    height_pt: float
    dpi: int
    lines: List[TextLine] = field(default_factory=list)
    # Raster is held only in memory (not serialized); re-rendered from the PDF.
    raster: Optional["object"] = None  # numpy.ndarray (H, W, 3) uint8

    @property
    def scale(self) -> float:
        """Pixels-per-point for this page's raster."""
        return self.dpi / 72.0

    @property
    def pixel_size(self) -> Tuple[int, int]:
        return (round(self.width_pt * self.scale), round(self.height_pt * self.scale))

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
            "dpi": self.dpi,
            "lines": [ln.to_dict() for ln in self.lines],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Page":
        return cls(
            index=d["index"],
            width_pt=d["width_pt"],
            height_pt=d["height_pt"],
            dpi=d["dpi"],
            lines=[TextLine.from_dict(x) for x in d.get("lines", [])],
        )


@dataclass
class Document:
    """A loaded PDF and the edit session over it."""

    source_path: str
    pages: List[Page] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "pages": [p.to_dict() for p in self.pages],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Document":
        return cls(
            source_path=d["source_path"],
            pages=[Page.from_dict(x) for x in d.get("pages", [])],
        )
