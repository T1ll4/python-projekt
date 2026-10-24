"""Egyéb formátumok (ODT, RTF, Markdown, LaTeX, HTML, EPUB, RST) feldolgozása pandoc-kal.

A pandoc a bemenetet .docx formátumra alakítja (az egyenleteket OMML-ként,
a képeket beágyazva), majd a .docx kinyerő dolgozza fel.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..models import ExtractionResult
from .docx_extractor import extract_docx

PANDOC_FORMATS = {
    ".odt": "odt", ".rtf": "rtf", ".md": "markdown", ".markdown": "markdown",
    ".tex": "latex", ".latex": "latex", ".html": "html", ".htm": "html",
    ".epub": "epub", ".rst": "rst",
}


class PandocError(RuntimeError):
    pass


def pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


def convert_with_pandoc(path: str | os.PathLike, target: str | os.PathLike,
                        timeout: int = 120) -> None:
    path = Path(path)
    if not pandoc_available():
        raise PandocError("A pandoc nincs telepítve (https://pandoc.org/installing.html).")
    reader = PANDOC_FORMATS.get(path.suffix.lower())
    if reader is None:
        raise PandocError(f"A pandoc ezt a formátumot nem kezeli: {path.suffix}")
    cmd = ["pandoc", str(path), "-f", reader, "-t", "docx", "-o", str(target),
           f"--resource-path={path.parent}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise PandocError("A pandoc konverzió időtúllépés miatt megszakadt.") from None
    if proc.returncode != 0:
        raise PandocError(f"Pandoc hiba: {proc.stderr.strip()[:500]}")


def extract_with_pandoc(path: str | os.PathLike, source_name: str = "") -> ExtractionResult:
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "converted.docx"
        convert_with_pandoc(path, target)
        result = extract_docx(str(target), source_name=source_name or path.name)
    result.source_file = source_name or path.name
    return result
