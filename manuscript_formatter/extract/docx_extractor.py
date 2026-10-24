"""Ábrák, táblázatok, képaláírások és egyenletek kinyerése Word (.docx) fájlból (python-docx)."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from typing import BinaryIO, Optional, Union

import pandas as pd
from docx import Document
from docx.oxml.ns import qn

from ..models import Equation, ExtractionResult, Figure, Table
from .captions import caption_kind, find_latex_equations
from .omml import M_NS, omml_to_latex, omml_to_text

R_EMBED = qn("r:embed")
R_LINK = qn("r:link")
R_ID = qn("r:id")
V_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
OMATH = f"{{{M_NS}}}oMath"
OMATH_PARA = f"{{{M_NS}}}oMathPara"


@dataclass
class _Item:
    kind: str  # image | caption | table | equation
    payload: object = None
    caption_kind: Optional[str] = None
    text: str = ""


def _paragraph_text(p_el) -> str:
    """Bekezdés szövege (egyenletek nélkül)."""
    parts = []
    for node in p_el.iter(qn("w:t")):
        # az egyenleten belüli w:t ne kerüljön a szövegbe
        parent = node.getparent()
        inside_math = False
        while parent is not None and parent is not p_el:
            if parent.tag in (OMATH, OMATH_PARA):
                inside_math = True
                break
            parent = parent.getparent()
        if not inside_math:
            parts.append(node.text or "")
    return "".join(parts).strip()


def _style_name(p_el, doc) -> str:
    p_pr = p_el.find(qn("w:pPr"))
    if p_pr is None:
        return ""
    style = p_pr.find(qn("w:pStyle"))
    if style is None:
        return ""
    style_id = style.get(qn("w:val"), "")
    try:
        for s in doc.styles:
            if s.style_id == style_id:
                return (s.name or style_id).lower()
    except Exception:  # sérült stílustábla
        pass
    return style_id.lower()


def _images_in(element, doc, warnings: list[str]) -> list[tuple[str, bytes]]:
    """Az elemben található beágyazott képek (fájlnév, bájtok)."""
    images = []
    rel_ids = []
    for blip in element.iter(qn("a:blip")):
        rid = blip.get(R_EMBED)
        if rid:
            rel_ids.append(rid)
        elif blip.get(R_LINK):
            warnings.append("Külső hivatkozású (nem beágyazott) kép kihagyva.")
    for imagedata in element.iter(V_IMAGEDATA):  # régi (VML) képek
        rid = imagedata.get(R_ID)
        if rid:
            rel_ids.append(rid)
    for rid in rel_ids:
        try:
            part = doc.part.related_parts[rid]
        except KeyError:
            warnings.append(f"Hiányzó képhivatkozás: {rid}")
            continue
        name = os.path.basename(str(part.partname))
        images.append((name, part.blob))
    return images


def _table_to_dataframe(tbl_el, doc) -> pd.DataFrame:
    from docx.table import Table as DocxTable

    table = DocxTable(tbl_el, doc.part)
    rows: list[list[str]] = []
    for row in table.rows:
        cells = []
        previous = None
        for cell in row.cells:
            # vízszintesen egyesített cellák ismétlődnek a python-docx-ben → csak egyszer
            if previous is not None and cell._tc is previous:
                cells.append("")
                continue
            previous = cell._tc
            cells.append(" ".join(p.text.strip() for p in cell.paragraphs if p.text.strip()))
        rows.append(cells)
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return pd.DataFrame()
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = _unique_header(rows[0])
    return pd.DataFrame(rows[1:], columns=header)


def _unique_header(values: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    header = []
    for i, value in enumerate(values):
        name = value.strip() or f"Column {i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 0
        header.append(name)
    return header


def _display_equations(p_el) -> list[tuple[str, str]]:
    """Kiemelt (önálló) egyenletek a bekezdésben: (latex, szöveg) párok.

    Önálló egyenlet: ``m:oMathPara``, vagy olyan bekezdés, amelyben az ``m:oMath``
    mellett legfeljebb egy egyenletszám („(1)”) szerepel.
    """
    result = []
    paras = list(p_el.iter(OMATH_PARA))
    for para in paras:
        result.append((omml_to_latex(para), omml_to_text(para)))
    if paras:
        return result
    maths = [m for m in p_el.iter(OMATH)]
    if not maths:
        return result
    other_text = _paragraph_text(p_el)
    stripped = other_text.replace("(", "").replace(")", "").replace(".", "").strip()
    if len(stripped) <= 4:  # csak egyenletszám vagy semmi
        for math in maths:
            result.append((omml_to_latex(math), omml_to_text(math)))
    return result


def extract_docx(source: Union[str, os.PathLike, bytes, BinaryIO],
                 source_name: str = "") -> ExtractionResult:
    if isinstance(source, (bytes, bytearray)):
        stream: Union[str, BinaryIO] = io.BytesIO(source)
    else:
        stream = source  # type: ignore[assignment]
    doc = Document(stream)
    name = source_name or (str(source) if isinstance(source, (str, os.PathLike)) else "manuscript.docx")
    result = ExtractionResult(source_file=os.path.basename(name))

    items: list[_Item] = []
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            _collect_paragraph(child, doc, items, result.warnings)
        elif child.tag == qn("w:tbl"):
            images = _images_in(child, doc, result.warnings)
            if images:
                # képrács-táblázat (pl. több panelű ábra) → ábrák, a cellák aláírásaival
                for p_el in child.iter(qn("w:p")):
                    _collect_paragraph(p_el, doc, items, result.warnings)
                continue
            df = _table_to_dataframe(child, doc)
            if not df.empty or len(df.columns) > 0:
                items.append(_Item("table", df))
        elif child.tag == qn("w:sdt"):  # tartalomvezérlők (pl. tartalomjegyzék) szövege
            for p_el in child.iter(qn("w:p")):
                _collect_paragraph(p_el, doc, items, result.warnings)

    _assemble(items, result)
    return result


def _collect_paragraph(p_el, doc, items: list[_Item], warnings: list[str]) -> None:
    for name, blob in _images_in(p_el, doc, warnings):
        items.append(_Item("image", (name, blob)))
    for latex, text in _display_equations(p_el):
        items.append(_Item("equation", (latex, text)))
    text = _paragraph_text(p_el)
    if not text:
        return
    style = _style_name(p_el, doc)
    is_caption_style = "caption" in style or "képaláírás" in style or "felirat" in style
    kind = caption_kind(text, strict=not is_caption_style)
    if kind is None and is_caption_style:
        kind = "table" if text.lower().startswith(("table", "táblázat", "tab.")) else "figure"
    if kind:
        items.append(_Item("caption", caption_kind=kind, text=text))
        return
    equations = find_latex_equations(text)
    for latex in equations:
        items.append(_Item("equation", (latex, latex)))
    if not equations:
        items.append(_Item("text", text=text))


def _assemble(items: list[_Item], result: ExtractionResult) -> None:
    """Képek és táblázatok párosítása a hozzájuk tartozó képaláírással.

    Kezeli az aláírás-az-ábra-alatt és aláírás-az-ábra-felett elrendezést, valamint
    a több képből álló (panel) ábrákat: az egy aláírás előtti képek egy ábrát alkotnak.
    """
    figure_groups: list[tuple[list[tuple[str, bytes]], str]] = []
    unassigned: list[tuple[str, bytes]] = []
    pending_fig_caption: Optional[str] = None

    tables: list[list] = []  # [df, caption]
    pending_table_caption: Optional[str] = None
    last_kind: Optional[str] = None

    eq_counter = 0
    for index, item in enumerate(items):
        next_kind = items[index + 1].kind if index + 1 < len(items) else None
        if item.kind == "image":
            if pending_fig_caption is not None and not unassigned:
                figure_groups.append(([item.payload], pending_fig_caption))  # type: ignore[list-item]
                pending_fig_caption = None
            else:
                unassigned.append(item.payload)  # type: ignore[arg-type]
        elif item.kind == "caption" and item.caption_kind == "figure":
            if unassigned and (last_kind == "image" or next_kind != "image"):
                figure_groups.append((unassigned, item.text))
                unassigned = []
            else:
                if unassigned:  # a korábbi képek aláírás nélkül maradnak
                    figure_groups.extend(([image], "") for image in unassigned)
                    result.warnings.append(f"{len(unassigned)} képhez nem található képaláírás.")
                    unassigned = []
                pending_fig_caption = item.text
        elif item.kind == "caption" and item.caption_kind == "table":
            if last_kind == "table" and tables and not tables[-1][1] and next_kind != "table":
                tables[-1][1] = item.text
            else:
                pending_table_caption = item.text
        elif item.kind == "table":
            tables.append([item.payload, pending_table_caption or ""])
            pending_table_caption = None
        elif item.kind == "equation":
            latex, text = item.payload  # type: ignore[misc]
            eq_counter += 1
            result.equations.append(Equation(number=eq_counter, latex=latex, text=text))
        last_kind = item.kind

    if unassigned:  # aláírás nélküli képek: mindegyik külön ábra
        for image in unassigned:
            figure_groups.append(([image], ""))
        result.warnings.append(f"{len(unassigned)} képhez nem található képaláírás.")
    if pending_fig_caption:
        result.warnings.append(f"Képaláírás kép nélkül (vektoros/beágyazott objektum?): "
                               f"„{pending_fig_caption[:60]}”")

    for number, (images, caption) in enumerate(figure_groups, start=1):
        multi = len(images) > 1
        for index, (name, blob) in enumerate(images):
            panel = chr(ord("a") + index) if multi and index < 26 else ""
            result.figures.append(
                Figure(number=number, data=blob, source_name=name, caption=caption, panel=panel)
            )
    for number, (df, caption) in enumerate(tables, start=1):
        if not caption:
            result.warnings.append(f"A(z) {number}. táblázathoz nem található felirat.")
        result.tables.append(Table(number=number, dataframe=df, caption=caption))
