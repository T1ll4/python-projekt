"""Mintakéziratok generálása (DOCX és PDF) a program kipróbálásához és a tesztekhez.

Használat:  python examples/make_sample.py [kimeneti_könyvtár]
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
from docx import Document
from docx.shared import Cm
from lxml import etree
from PIL import Image, ImageDraw

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# E = mc^2 és a másodfokú egyenlet megoldóképlete OMML-ben
OMML_EQUATIONS = [
    f"""<m:oMathPara xmlns:m="{M_NS}"><m:oMath>
      <m:r><m:t>E=m</m:t></m:r>
      <m:sSup><m:e><m:r><m:t>c</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>
    </m:oMath></m:oMathPara>""",
    f"""<m:oMathPara xmlns:m="{M_NS}"><m:oMath>
      <m:r><m:t>x=</m:t></m:r>
      <m:f><m:num><m:r><m:t>−b±</m:t></m:r>
        <m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>
          <m:sSup><m:e><m:r><m:t>b</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>
          <m:r><m:t>−4ac</m:t></m:r></m:e></m:rad></m:num>
        <m:den><m:r><m:t>2a</m:t></m:r></m:den></m:f>
    </m:oMath></m:oMathPara>""",
    f"""<m:oMathPara xmlns:m="{M_NS}"><m:oMath>
      <m:nary><m:naryPr><m:chr m:val="∑"/></m:naryPr>
        <m:sub><m:r><m:t>i=1</m:t></m:r></m:sub><m:sup><m:r><m:t>n</m:t></m:r></m:sup>
        <m:e><m:sSub><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:e>
      </m:nary><m:r><m:t>=α</m:t></m:r>
    </m:oMath></m:oMathPara>""",
]


def photo_image(width: int = 900, height: int = 600) -> Image.Image:
    """Színes, fotószerű (folytonos tónusú) kép, beágyazott 96 dpi-vel."""
    y, x = np.mgrid[0:height, 0:width]
    r = (127 + 127 * np.sin(x / 60.0)).astype(np.uint8)
    g = (127 + 127 * np.cos(y / 45.0)).astype(np.uint8)
    b = ((x + y) % 256).astype(np.uint8)
    img = Image.fromarray(np.dstack([r, g, b]))
    canvas = Image.new("RGB", (width + 120, height + 120), "white")  # fehér margó a vágáshoz
    canvas.paste(img, (60, 60))
    return canvas


def line_art_image(width: int = 1600, height: int = 700) -> Image.Image:
    """Fekete-fehér vonalas ábra (széles → kéthasábos méretezés)."""
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    draw.line((80, height - 80, width - 40, height - 80), fill=0, width=4)
    draw.line((80, 40, 80, height - 80), fill=0, width=4)
    points = [(80 + i * 30, height - 80 - int(250 + 200 * np.sin(i / 6.0))) for i in range(50)]
    draw.line(points, fill=0, width=5)
    for px, py in points[::5]:
        draw.ellipse((px - 8, py - 8, px + 8, py + 8), outline=0, width=3)
    return img


def chart_image() -> Image.Image:
    """Matplotlib diagram RGBA PNG-ként (átlátszó háttérrel)."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    fig = Figure(figsize=(4, 3))
    ax = fig.add_subplot()
    ax.bar(["A", "B", "C", "D"], [3, 7, 5, 9], color=["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"])
    ax.set_ylabel("Value")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, transparent=True)
    buf.seek(0)
    return Image.open(buf).copy()


def _png(img: Image.Image, dpi: int = 96) -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, "PNG", dpi=(dpi, dpi))
    buf.seek(0)
    return buf


def make_docx(path: Path) -> Path:
    doc = Document()
    doc.add_heading("Sample manuscript", level=1)
    doc.add_paragraph("Figure 1 shows the measured signal. This sentence is not a caption.")

    doc.add_picture(_png(photo_image()), width=Cm(12))
    doc.add_paragraph("Figure 1. Continuous-tone colour image of the sample.", style="Caption")

    doc.add_paragraph("Some text between figures.")
    doc.add_paragraph("Table 1. Measured values of the samples.", style="Caption")
    rows = [("Sample", "Mass (g)", "Temperature (°C)", "Note"),
            ("A-1", "12,5", "21.3", "control"),
            ("A-2", "13.75", "22.0", "100% humidity"),
            ("B-1", "1,234.5", "−4.2", "x_1 & y")]
    table = doc.add_table(rows=len(rows), cols=4)
    for r, values in enumerate(rows):
        for c, value in enumerate(values):
            table.cell(r, c).text = value

    doc.add_paragraph("The energy is given by the following relation:")
    for xml in OMML_EQUATIONS:
        p = doc.add_paragraph()
        p._p.append(etree.fromstring(xml))

    doc.add_picture(_png(line_art_image(), dpi=300), width=Cm(16))
    doc.add_picture(_png(chart_image(), dpi=150), width=Cm(8))
    doc.add_paragraph("Fig. 2: Line drawing (a) and bar chart (b) of the results.")

    doc.add_paragraph("2. táblázat: Összesítés")
    t2 = doc.add_table(rows=3, cols=2)
    for r, values in enumerate([("Paraméter", "Érték"), ("n", "42"), ("p", "0.003")]):
        for c, value in enumerate(values):
            t2.cell(r, c).text = value
    doc.add_paragraph(r"A text equation: $$a^2 + b^2 = c^2$$")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


def make_pdf(path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    c.setFont("Helvetica", 11)
    c.drawString(72, height - 72, "Sample manuscript (PDF)")
    c.drawImage(ImageReader(photo_image()), 72, height - 380, width=300, height=220)
    c.drawString(72, height - 400, "Figure 1. Colour image extracted from the PDF.")
    c.setFont("Courier", 10)
    y = height - 450
    c.drawString(72, y, "Table 1. Results of the experiment.")
    for row in (["Group", "Mean", "SD"], ["Control", "10.2", "1.1"], ["Treated", "12.9", "0.8"]):
        y -= 16
        c.drawString(72, y, f"{row[0]:<12}{row[1]:<10}{row[2]}")
    y -= 40
    c.drawString(72, y, "E = m c^2                                   (1)")
    c.showPage()
    c.setFont("Helvetica", 11)
    c.drawImage(ImageReader(line_art_image()), 72, height - 320, width=450, height=200)
    c.drawString(72, height - 340, "Figure 2. Line drawing on page two.")
    c.save()
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "examples/output")
    print("DOCX:", make_docx(out / "sample_manuscript.docx"))
    try:
        print("PDF: ", make_pdf(out / "sample_manuscript.pdf"))
    except ImportError:
        print("PDF minta kihagyva (pip install reportlab)")
