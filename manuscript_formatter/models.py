"""Adatmodellek a kéziratból kinyert elemekhez és a feldolgozás eredményéhez."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class Figure:
    """Egy kéziratból kinyert ábra (nyers képadat + képaláírás)."""

    number: int
    data: bytes
    source_name: str = ""
    caption: str = ""
    page: Optional[int] = None
    panel: str = ""

    @property
    def label(self) -> str:
        return f"Figure {self.number}{self.panel}"


@dataclass
class Table:
    """Egy kéziratból kinyert táblázat."""

    number: int
    dataframe: pd.DataFrame
    caption: str = ""
    page: Optional[int] = None

    @property
    def label(self) -> str:
        return f"Table {self.number}"


@dataclass
class Equation:
    """Egy kinyert egyenlet. A `latex` mező üres, ha nem sikerült LaTeX-et előállítani."""

    number: int
    latex: str = ""
    text: str = ""
    page: Optional[int] = None

    @property
    def label(self) -> str:
        return f"Equation {self.number}"


@dataclass
class ExtractionResult:
    """A dokumentumelemzés teljes eredménye."""

    source_file: str
    figures: list[Figure] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    equations: list[Equation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ProcessedImage:
    """Egy ábra vagy egyenlet kiadói formátumra konvertált változata."""

    filename: str
    data: bytes
    width_px: int
    height_px: int
    dpi: int
    color_mode: str
    file_format: str
    width_mm: float
    height_mm: float
    original_width_px: int = 0
    original_height_px: int = 0
    effective_input_dpi: float = 0.0
    caption: str = ""
    warnings: list[str] = field(default_factory=list)
    preview_png: bytes = b""  # kis méretű előnézet a felülethez (nem kerül a csomagba)

    def to_report(self) -> dict:
        return {
            "filename": self.filename,
            "caption": self.caption,
            "format": self.file_format,
            "color_mode": self.color_mode,
            "dpi": self.dpi,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "width_mm": round(self.width_mm, 2),
            "height_mm": round(self.height_mm, 2),
            "original_width_px": self.original_width_px,
            "original_height_px": self.original_height_px,
            "effective_input_dpi": round(self.effective_input_dpi, 1),
            "warnings": list(self.warnings),
        }
