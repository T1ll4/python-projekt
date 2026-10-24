"""Dokumentumelemzők: a fájl kiterjesztése alapján a megfelelő kinyerőt választja."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Union

from ..models import ExtractionResult
from .docx_extractor import extract_docx
from .pandoc_extractor import PANDOC_FORMATS, PandocError, extract_with_pandoc, pandoc_available
from .pdf_extractor import extract_pdf

SUPPORTED_EXTENSIONS = (".docx", ".pdf", *PANDOC_FORMATS.keys())


class UnsupportedFormatError(ValueError):
    pass


def extract_document(source: Union[str, os.PathLike, bytes], filename: str = "") -> ExtractionResult:
    """Kézirat elemzése fájlútvonalból vagy bájtokból (utóbbinál a ``filename`` kötelező)."""
    if isinstance(source, (bytes, bytearray)):
        if not filename:
            raise ValueError("Bájtbemenet esetén meg kell adni a fájlnevet.")
        name = filename
    else:
        name = filename or str(source)
    ext = Path(name).suffix.lower()

    if ext == ".docx":
        return extract_docx(source, source_name=Path(name).name)
    if ext == ".pdf":
        return extract_pdf(source, source_name=Path(name).name)
    if ext in PANDOC_FORMATS:
        if isinstance(source, (bytes, bytearray)):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"input{ext}"
                path.write_bytes(source)
                return extract_with_pandoc(path, source_name=Path(name).name)
        return extract_with_pandoc(source, source_name=Path(name).name)
    if ext == ".doc":
        raise UnsupportedFormatError(
            "A régi .doc formátum nem támogatott – mentse el .docx formátumban."
        )
    raise UnsupportedFormatError(
        f"Nem támogatott fájltípus: {ext or '(nincs kiterjesztés)'}. "
        f"Támogatott: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


__all__ = [
    "SUPPORTED_EXTENSIONS", "UnsupportedFormatError", "PandocError", "extract_document",
    "extract_docx", "extract_pdf", "extract_with_pandoc", "pandoc_available",
]
