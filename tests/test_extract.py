import pytest
from lxml import etree

from manuscript_formatter.extract import UnsupportedFormatError, extract_document, pandoc_available
from manuscript_formatter.extract.captions import caption_kind, caption_number, find_latex_equations
from manuscript_formatter.extract.omml import omml_to_latex


@pytest.mark.parametrize("text,kind", [
    ("Figure 1. Results", "figure"), ("Fig. 2 Overview", "figure"), ("1. ábra: Mérés", "figure"),
    ("Table 3: Stats", "table"), ("2. táblázat. Adatok", "table"), ("TABLE II. Values", "table"),
    ("Figure 2 shows the data", None), ("Figures are nice", None), ("Tablet 3. x", None),
])
def test_caption_detection(text, kind):
    assert caption_kind(text) == kind


def test_caption_number_and_latex_text():
    assert caption_number("Fig. 12: x") == 12
    assert find_latex_equations(r"a $$x^2$$ b \begin{equation}y=1\end{equation}") == ["x^2", "y=1"]


M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _omml(body):
    return etree.fromstring(f'<m:oMath xmlns:m="{M}">{body}</m:oMath>')


def test_omml_fraction_sup_greek():
    xml = _omml('<m:f><m:num><m:r><m:t>α</m:t></m:r></m:num><m:den><m:sSup><m:e><m:r><m:t>x'
                '</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:den></m:f>')
    assert omml_to_latex(xml) == r"\frac{\alpha}{{x}^{2}}"


def test_omml_delimiter_func_nary():
    xml = _omml('<m:d><m:e><m:r><m:t>a</m:t></m:r></m:e><m:e><m:r><m:t>b</m:t></m:r></m:e></m:d>'
                '<m:func><m:fName><m:r><m:t>sin</m:t></m:r></m:fName><m:e><m:r><m:t>x</m:t></m:r>'
                '</m:e></m:func>'
                '<m:nary><m:naryPr><m:chr m:val="∑"/></m:naryPr><m:sub><m:r><m:t>i</m:t></m:r>'
                '</m:sub><m:sup/><m:e><m:r><m:t>i</m:t></m:r></m:e></m:nary>')
    latex = omml_to_latex(xml)
    assert r"\left(a \mid b\right)" in latex
    assert r"\sin {x}" in latex
    assert r"\sum_{i} {i}" in latex


def test_docx_extraction(samples):
    res = extract_document(str(samples["docx"]))
    # 1. ábra + 2. ábra két panellel
    assert [(f.number, f.panel) for f in res.figures] == [(1, ""), (2, "a"), (2, "b")]
    assert res.figures[0].caption.startswith("Figure 1.")
    assert res.figures[1].caption == res.figures[2].caption
    assert len(res.tables) == 2
    t1 = res.tables[0]
    assert t1.caption.startswith("Table 1.")
    assert list(t1.dataframe.columns) == ["Sample", "Mass (g)", "Temperature (°C)", "Note"]
    assert t1.dataframe.shape == (3, 4)
    assert res.tables[1].caption.startswith("2. táblázat")
    latex = [e.latex for e in res.equations]
    assert latex[0] == "E=m{c}^{2}"
    assert r"\frac" in latex[1] and r"\sqrt" in latex[1]
    assert r"\sum_{i=1}^{n}" in latex[2]
    assert latex[3] == "a^2 + b^2 = c^2"


def test_docx_from_bytes(samples):
    data = samples["docx"].read_bytes()
    res = extract_document(data, filename="upload.docx")
    assert res.source_file == "upload.docx" and len(res.figures) == 3


def test_pdf_extraction(samples):
    if "pdf" not in samples:
        pytest.skip("reportlab nincs telepítve")
    res = extract_document(str(samples["pdf"]))
    assert len(res.figures) == 2
    assert res.figures[0].caption.startswith("Figure 1.") and res.figures[0].page == 1
    assert res.figures[1].page == 2
    assert len(res.tables) == 1
    assert list(res.tables[0].dataframe.columns) == ["Group", "Mean", "SD"]
    assert res.tables[0].dataframe.iloc[1, 1] == "12.9"
    assert len(res.equations) == 1 and "E = m c^2" in res.equations[0].text


@pytest.mark.skipif(not pandoc_available(), reason="pandoc nincs telepítve")
def test_markdown_via_pandoc(tmp_path):
    from PIL import Image

    Image.new("RGB", (120, 80), (200, 30, 30)).save(tmp_path / "img.png")
    md = tmp_path / "paper.md"
    md.write_text("# Title\n\n![Figure 1. A red box.](img.png)\n\n"
                  "$$\\frac{a}{b} = c$$\n\n"
                  "Table: Table 1. Small table.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n",
                  encoding="utf-8")
    res = extract_document(str(md))
    assert len(res.figures) == 1 and res.figures[0].caption.startswith("Figure 1.")
    assert len(res.tables) == 1 and list(res.tables[0].dataframe.columns) == ["A", "B"]
    assert any(r"\frac{a}{b}" in e.latex for e in res.equations)


def test_unsupported_format():
    with pytest.raises(UnsupportedFormatError):
        extract_document(b"x", filename="file.doc")
    with pytest.raises(UnsupportedFormatError):
        extract_document(b"x", filename="file.xyz")
