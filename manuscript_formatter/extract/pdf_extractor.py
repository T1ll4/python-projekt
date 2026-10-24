"""Ábrák, táblázatok, képaláírások és egyenletek kinyerése PDF-ből (pypdf).

A PDF nem tárol szerkezeti információt, ezért heurisztikák működnek:

* ábrák: az oldalakon beágyazott raszterképek (``page.images``), a túl kicsi
  (ikon, logó) képek kiszűrésével; az aláírásokat oldalanként, sorrendben
  rendeli a képekhez;
* táblázatok: a „Table N” aláírást követő, legalább két, nagy szóközzel
  elválasztott oszlopot tartalmazó sorok (layout módú szövegkinyerés);
* egyenletek: ``=`` jelet és sorvégi „(N)” számozást tartalmazó sorok.
"""

from __future__ import annotations

import io
import os
import re
from typing import BinaryIO, Union

import pandas as pd
from PIL import Image
from pypdf import PdfReader

from ..models import Equation, ExtractionResult, Figure, Table
from .captions import PDF_EQUATION_RE, caption_kind
from .docx_extractor import _unique_header
from .omml import convert_text

MIN_IMAGE_SIDE = 32
_COL_SPLIT = re.compile(r"\s{2,}|\t+")


def _page_text(page) -> str:
    try:
        return page.extract_text(extraction_mode="layout") or ""
    except Exception:
        try:
            return page.extract_text() or ""
        except Exception:
            return ""


def _image_bytes(image_file) -> bytes | None:
    """A pypdf képobjektumából Pillow által olvasható bájtsorozat."""
    data = getattr(image_file, "data", None)
    if data:
        try:
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
            return data
        except Exception:
            pass
    try:
        pil = image_file.image
    except Exception:
        return None
    if pil is None:
        return None
    buf = io.BytesIO()
    pil.save(buf, "TIFF" if pil.mode == "CMYK" else "PNG")
    return buf.getvalue()


def _collect_caption(lines: list[str], start: int) -> str:
    """Az aláírás a kezdősortól az első üres sorig / következő aláírásig tart (max. 5 sor)."""
    parts = [lines[start].strip()]
    for line in lines[start + 1:start + 5]:
        stripped = line.strip()
        if not stripped or caption_kind(stripped) or len(_COL_SPLIT.split(stripped)) > 2:
            break
        parts.append(stripped)
    return " ".join(" ".join(parts).split())


def _parse_table(lines: list[str], start: int) -> pd.DataFrame | None:
    """A felirat után következő oszlopos sorok táblázattá alakítása."""
    rows: list[list[str]] = []
    blanks = 0
    index = start
    # a felirat esetleg több soros: a nem oszlopos sorokat átlépjük, amíg táblázat nem jön
    while index < len(lines) and index < start + 6:
        cells = [c for c in _COL_SPLIT.split(lines[index].strip()) if c]
        if len(cells) >= 2:
            break
        index += 1
    for line in lines[index:]:
        stripped = line.strip()
        if not stripped:
            blanks += 1
            if rows and blanks > 1:
                break
            continue
        blanks = 0
        if caption_kind(stripped):
            break
        cells = [c.strip() for c in _COL_SPLIT.split(stripped) if c.strip()]
        if len(cells) < 2:
            if rows:
                break
            continue
        rows.append(cells)
    if len(rows) < 2:
        return None
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    return pd.DataFrame(rows[1:], columns=_unique_header(rows[0]))


def extract_pdf(source: Union[str, os.PathLike, bytes, BinaryIO],
                source_name: str = "") -> ExtractionResult:
    if isinstance(source, (bytes, bytearray)):
        stream: Union[str, os.PathLike, BinaryIO] = io.BytesIO(source)
    else:
        stream = source
    reader = PdfReader(stream)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            raise ValueError("A PDF jelszóval védett, nem dolgozható fel.") from None
    name = source_name or (str(source) if isinstance(source, (str, os.PathLike)) else "manuscript.pdf")
    result = ExtractionResult(source_file=os.path.basename(name))

    figure_no = table_no = equation_no = 0
    seen_hashes: set[int] = set()
    for page_index, page in enumerate(reader.pages, start=1):
        lines = _page_text(page).splitlines()

        # -- képek ------------------------------------------------------
        images: list[tuple[str, bytes]] = []
        try:
            page_images = list(page.images)
        except Exception as exc:
            result.warnings.append(f"{page_index}. oldal képei nem olvashatók: {exc}")
            page_images = []
        for image_file in page_images:
            data = _image_bytes(image_file)
            if not data:
                continue
            try:
                with Image.open(io.BytesIO(data)) as probe:
                    w, h = probe.size
            except Exception:
                continue
            if min(w, h) < MIN_IMAGE_SIDE:
                continue
            digest = hash(data)
            if digest in seen_hashes:  # ugyanaz a kép többször (pl. fejléc logó)
                continue
            seen_hashes.add(digest)
            images.append((getattr(image_file, "name", f"p{page_index}.png"), data))

        # -- aláírások, táblázatok, egyenletek --------------------------
        fig_captions: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            kind = caption_kind(stripped)
            if kind == "figure":
                fig_captions.append(_collect_caption(lines, i))
            elif kind == "table":
                caption = _collect_caption(lines, i)
                df = _parse_table(lines, i + 1)
                if df is not None:
                    table_no += 1
                    result.tables.append(Table(number=table_no, dataframe=df,
                                               caption=caption, page=page_index))
                else:
                    result.warnings.append(
                        f"{page_index}. oldal: a(z) „{caption[:40]}” táblázat sorai nem ismerhetők fel."
                    )
            else:
                match = PDF_EQUATION_RE.match(line)
                if match:
                    body = " ".join(match.group("body").split())
                    equation_no += 1
                    result.equations.append(Equation(number=equation_no, latex=convert_text(body),
                                                     text=body, page=page_index))

        for i, (img_name, data) in enumerate(images):
            figure_no += 1
            caption = fig_captions[i] if i < len(fig_captions) else ""
            result.figures.append(Figure(number=figure_no, data=data, source_name=img_name,
                                         caption=caption, page=page_index))
        if len(fig_captions) > len(images):
            result.warnings.append(
                f"{page_index}. oldal: {len(fig_captions) - len(images)} ábra-aláíráshoz nincs "
                "raszterkép (valószínűleg vektoros ábra – kérje a forrásfájlt)."
            )
        elif len(images) > len(fig_captions):
            result.warnings.append(
                f"{page_index}. oldal: {len(images) - len(fig_captions)} képhez nincs aláírás."
            )
    return result
