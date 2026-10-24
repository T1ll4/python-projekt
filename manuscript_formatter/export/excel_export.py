"""Formázott Excel munkafüzet készítése (openpyxl) a kinyert táblázatokból."""

from __future__ import annotations

import io
import re
from typing import Iterable, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..models import Table
from ..templates import JournalTemplate
from .tables import numeric_columns, typed_dataframe

_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
# az Excel által tiltott vezérlőkarakterek
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(value):
    if isinstance(value, str):
        return _ILLEGAL_XML.sub("", value)
    return value


def _sheet_title(base: str, existing: Iterable[str]) -> str:
    title = _INVALID_SHEET_CHARS.sub("_", base).strip("'")[:31] or "Sheet"
    candidate, n = title, 2
    lowered = {e.lower() for e in existing}
    while candidate.lower() in lowered:
        suffix = f" ({n})"
        candidate = title[: 31 - len(suffix)] + suffix
        n += 1
    return candidate


def _number_format(decimal_places: int) -> Optional[str]:
    if decimal_places < 0:
        return None
    return "0" if decimal_places == 0 else "0." + "0" * decimal_places


def build_excel(tables: list[Table], template: JournalTemplate,
                figure_report: Optional[list[dict]] = None) -> bytes:
    """Minden táblázat külön munkalapra kerül a sablon betűtípusával, fejlécstílusával,
    szegélyeivel; opcionálisan egy „Figures” összesítő lap is készül."""
    rules = template.table
    wb = Workbook()
    wb.remove(wb.active)

    base_font = Font(name=rules.font_family, size=rules.font_size_pt)
    header_font = Font(name=rules.font_family, size=rules.font_size_pt, bold=rules.header_bold)
    caption_font = Font(name=rules.font_family, size=rules.font_size_pt, bold=True)
    header_fill = PatternFill("solid", fgColor=rules.header_fill.upper())
    zebra_fill = PatternFill("solid", fgColor="F2F2F2")
    thin = Side(style="thin", color="000000")
    medium = Side(style="medium", color="000000")
    number_format = _number_format(rules.decimal_places)

    for table in tables:
        ws = wb.create_sheet(_sheet_title(table.label, wb.sheetnames))
        df = typed_dataframe(table.dataframe)
        n_cols = max(1, df.shape[1])
        numeric = numeric_columns(df)
        row = 1

        def write_caption(at_row: int) -> None:
            cell = ws.cell(row=at_row, column=1, value=_clean(table.caption or table.label))
            cell.font = caption_font
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if n_cols > 1:
                ws.merge_cells(start_row=at_row, start_column=1, end_row=at_row, end_column=n_cols)
            lines = max(1, len(cell.value) // max(20, n_cols * 14) + 1)
            ws.row_dimensions[at_row].height = rules.font_size_pt * 1.4 * lines

        if rules.caption_position == "top":
            write_caption(row)
            row += 2

        header_row = row
        for col, name in enumerate(df.columns, start=1):
            cell = ws.cell(row=row, column=col, value=_clean(str(name)))
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        row += 1
        first_data = row
        for r_index, values in enumerate(df.itertuples(index=False)):
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=_clean(value))
                cell.font = base_font
                is_num = isinstance(value, (int, float)) and not isinstance(value, bool)
                cell.alignment = Alignment(horizontal="right" if is_num else "left",
                                           vertical="top", wrap_text=not is_num)
                if is_num and number_format and isinstance(value, float):
                    cell.number_format = number_format
                if rules.zebra_striping and r_index % 2 == 1:
                    cell.fill = zebra_fill
            row += 1
        last_row = row - 1

        _apply_borders(ws, rules.border_style, header_row, first_data, last_row, n_cols,
                       thin, medium)

        if rules.caption_position == "bottom":
            write_caption(row + 1)

        for col in range(1, n_cols + 1):
            letter = get_column_letter(col)
            lengths = [len(str(ws.cell(row=r, column=col).value or ""))
                       for r in range(header_row, last_row + 1)]
            width = min(60, max(8, max(lengths, default=8) + 2))
            if col <= len(numeric) and numeric[col - 1]:
                width = min(width, 18)
            ws.column_dimensions[letter].width = width
        ws.freeze_panes = ws.cell(row=first_data, column=1)
        ws.sheet_view.showGridLines = rules.border_style == "none"

    _summary_sheet(wb, template, tables, figure_report, base_font, header_font, header_fill)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _apply_borders(ws, style: str, header_row: int, first_data: int, last_row: int,
                   n_cols: int, thin: Side, medium: Side) -> None:
    if style == "none":
        return
    for r in range(header_row, last_row + 1):
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=r, column=c)
            if style == "grid":
                cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            else:  # booktabs: vastag felső/alsó vonal, vékony a fejléc alatt
                top = medium if r == header_row else None
                bottom = None
                if r == header_row:
                    bottom = thin
                if r == last_row:
                    bottom = medium
                cell.border = Border(top=top, bottom=bottom)


def _summary_sheet(wb: Workbook, template: JournalTemplate, tables: list[Table],
                   figure_report: Optional[list[dict]], base_font: Font, header_font: Font,
                   header_fill: PatternFill) -> None:
    ws = wb.create_sheet("Summary", 0)
    ws["A1"] = "Sablon"
    ws["B1"] = f"{template.name} ({template.id})"
    ws["A2"] = "Táblázatok száma"
    ws["B2"] = len(tables)
    ws["A3"] = "Ábrák száma"
    ws["B3"] = len(figure_report or [])
    for r in range(1, 4):
        ws.cell(row=r, column=1).font = header_font
        ws.cell(row=r, column=2).font = base_font
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 40

    if figure_report:
        headers = ["Fájl", "Formátum", "Színmód", "DPI", "Szélesség (mm)", "Magasság (mm)",
                   "Pixel (sz×m)", "Eredeti eff. DPI", "Képaláírás", "Figyelmeztetések"]
        start = 5
        for col, name in enumerate(headers, start=1):
            cell = ws.cell(row=start, column=col, value=name)
            cell.font = header_font
            cell.fill = header_fill
        for i, rep in enumerate(figure_report, start=start + 1):
            values = [rep["filename"], rep["format"], rep["color_mode"], rep["dpi"],
                      rep["width_mm"], rep["height_mm"], f'{rep["width_px"]}×{rep["height_px"]}',
                      rep["effective_input_dpi"], rep["caption"], "; ".join(rep["warnings"])]
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=i, column=col, value=_clean(value))
                cell.font = base_font
        for col, width in enumerate([18, 10, 10, 8, 14, 14, 14, 14, 50, 60], start=1):
            ws.column_dimensions[get_column_letter(col)].width = max(
                width, ws.column_dimensions[get_column_letter(col)].width or 0)
