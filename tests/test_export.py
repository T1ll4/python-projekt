import io
import json
import zipfile

import pandas as pd
from openpyxl import load_workbook

from manuscript_formatter.export.excel_export import build_excel
from manuscript_formatter.export.latex_export import latex_escape, render_document, render_table
from manuscript_formatter.export.tables import parse_number
from manuscript_formatter.models import Equation, Table
from manuscript_formatter.pipeline import process_manuscript
from manuscript_formatter.templates import JournalTemplate


def _table():
    df = pd.DataFrame([["A", "1,5", "x_1 & 50%"], ["B", "2.25", "−3"]],
                      columns=["Name", "Value", "Note"])
    return Table(number=1, dataframe=df, caption="Table 1. Example values")


def test_parse_number():
    assert parse_number("3,14") == 3.14
    assert parse_number("1,234.5") == 1234.5
    assert parse_number("1 234") == 1234
    assert parse_number("−4.2") == -4.2
    assert parse_number("42") == 42
    assert parse_number("A-1") == "A-1"
    assert parse_number("1.2.3") == "1.2.3"
    assert parse_number("") == ""


def test_excel_formatting(store):
    tpl = store.get("elsevier")
    data = build_excel([_table()], tpl)
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Summary", "Table 1"]
    ws = wb["Table 1"]
    assert ws["A1"].value == "Table 1. Example values"
    assert ws["A3"].value == "Name" and ws["A3"].font.b
    assert ws["A3"].font.name == tpl.table.font_family
    assert ws["B4"].value == 1.5 and ws["B5"].value == 2.25
    assert ws["A3"].border.top.style == "medium"  # booktabs felső vonal
    assert ws.freeze_panes == "A4"


def test_excel_caption_bottom_and_grid():
    tpl = JournalTemplate.from_dict({"id": "g", "name": "G", "table": {
        "caption_position": "bottom", "border_style": "grid", "decimal_places": 2}})
    wb = load_workbook(io.BytesIO(build_excel([_table()], tpl)))
    ws = wb["Table 1"]
    assert ws["A1"].value == "Name"
    assert ws["A5"].value == "Table 1. Example values"
    assert ws["B2"].number_format == "0.00"
    assert ws["A2"].border.left.style == "thin"


def test_latex_table(store):
    tex = render_table(_table(), store.get("elsevier"))
    assert r"\begin{table}" in tex and r"\toprule" in tex and r"\bottomrule" in tex
    assert r"\caption{Example values}" in tex
    assert r"x\_1 \& 50\%" in tex
    assert r"\begin{tabular}{lrl}" in tex
    assert tex.count("{") == tex.count("}")


def test_latex_grid_and_document():
    tpl = JournalTemplate.from_dict({"id": "g", "name": "G", "table": {
        "border_style": "grid", "latex_environment": "table*", "zebra_striping": True}})
    tex = render_table(_table(), tpl)
    assert r"\begin{table*}" in tex and r"\hline" in tex and "{|l|r|l|}" in tex
    doc = render_document([_table()], [Equation(1, latex=r"\frac{a}{b}")], tpl)
    assert doc.startswith("%") and r"\documentclass" in doc and r"\end{document}" in doc
    assert r"\usepackage[table]{xcolor}" in doc and r"\frac{a}{b}" in doc


def test_latex_escape():
    assert latex_escape("a_b & {c} 100% $") == r"a\_b \& \{c\} 100\% \$"


def test_full_pipeline_zip(samples, store):
    result = process_manuscript(str(samples["docx"]), store.get("elsevier"))
    data = result.zip_bytes()
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert zf.testzip() is None
    names = zf.namelist()
    assert {"figures/Fig1.tif", "figures/Fig2a.tif", "figures/Fig2b.tif"} <= set(names)
    assert "tables/sample_tables.xlsx" in names
    assert "tables/latex/Table1.tex" in names and "tables/latex/main.tex" in names
    assert any(n.startswith("equations/Eq") for n in names)
    assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in zf.infolist())
    report = json.loads(zf.read("report.json"))
    assert report["summary"]["figures"] == 3 and report["summary"]["tables"] == 2
    assert all(f["dpi"] >= 300 for f in report["figures"])
    captions = zf.read("captions.txt").decode()
    assert "Fig2a.tif, Fig2b.tif" in captions


def test_pipeline_pdf_springer_eps(samples, store):
    if "pdf" not in samples:
        return
    result = process_manuscript(str(samples["pdf"]), store.get("springer_nature"))
    assert [f.filename for f in result.figures] == ["Fig1.eps", "Fig2.eps"]
    assert all(f.data.startswith(b"%!PS-Adobe-3.0 EPSF-3.0") for f in result.figures)
    assert result.latex_zip_bytes()


def test_empty_document(tmp_path, store):
    from docx import Document

    path = tmp_path / "empty.docx"
    Document().save(path)
    result = process_manuscript(str(path), store.get("plos_one"))
    assert result.figures == [] and result.extraction.tables == []
    zf = zipfile.ZipFile(io.BytesIO(result.zip_bytes()))
    assert "report.json" in zf.namelist()
    assert load_workbook(io.BytesIO(result.excel_bytes())).sheetnames == ["Summary"]


def test_unconvertible_image_kept_as_original(store):
    from manuscript_formatter.models import ExtractionResult, Figure
    from manuscript_formatter.pipeline import process_extraction

    extraction = ExtractionResult(source_file="x.docx", figures=[
        Figure(number=1, data=b"\x01\x00\x09\x00garbage", source_name="image1.wmf",
               caption="Figure 1. Vector")])
    result = process_extraction(extraction, store.get("elsevier"))
    assert result.figures == [] and len(result.failed_figures) == 1
    names = zipfile.ZipFile(io.BytesIO(result.zip_bytes())).namelist()
    assert "figures_unconverted/Fig1.wmf" in names
    assert any("nem konvertálható" in w for w in result.warnings)
