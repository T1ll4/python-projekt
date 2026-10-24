"""LaTeX táblázatok és egyenletek generálása Jinja2 sablonokkal."""

from __future__ import annotations

from pathlib import Path

import jinja2

from ..models import Equation, Table
from ..templates import JournalTemplate
from .tables import format_number, numeric_columns, typed_dataframe

TEMPLATE_DIR = Path(__file__).parent / "latex_templates"

_LATEX_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    "<": r"\textless{}", ">": r"\textgreater{}", "−": "--", "±": r"$\pm$", "×": r"$\times$",
    "°": r"\textdegree{}", "µ": r"$\mu$", "μ": r"$\mu$", "≤": r"$\leq$", "≥": r"$\geq$",
}

# a jinja2 alapértelmezett {{ }} / {% %} jelölése ütközik a LaTeX kapcsos zárójeleivel
_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
    block_start_string=r"\BLOCK{", block_end_string="}",
    variable_start_string=r"\VAR{", variable_end_string="}",
    comment_start_string=r"\#{", comment_end_string="}",
    trim_blocks=True, lstrip_blocks=True, autoescape=False,
    undefined=jinja2.StrictUndefined, keep_trailing_newline=True,
)


def latex_escape(value) -> str:
    text = "" if value is None else str(value)
    return "".join(_LATEX_SPECIAL.get(ch, ch) for ch in text)


def strip_caption_label(caption: str) -> str:
    """„Table 1. Valami” → „Valami” (a LaTeX \\caption maga számoz)."""
    from ..extract.captions import FIGURE_CAPTION_RE, TABLE_CAPTION_RE

    for regex in (TABLE_CAPTION_RE, FIGURE_CAPTION_RE):
        match = regex.match(caption or "")
        if match:
            return caption[match.end():].strip()
    return (caption or "").strip()


def _font_package(font_family: str) -> str:
    low = font_family.lower()
    if "times" in low:
        return r"\usepackage{newtxtext,newtxmath}"
    if "arial" in low or "helvetica" in low:
        return "\\usepackage{helvet}\n\\renewcommand{\\familydefault}{\\sfdefault}"
    return ""


def table_context(table: Table, template: JournalTemplate) -> dict:
    rules = template.table
    df = typed_dataframe(table.dataframe)
    numeric = numeric_columns(df)
    n_cols = max(1, df.shape[1])
    if rules.border_style == "grid":
        colspec = "|" + "|".join("r" if numeric[i] else "l" for i in range(n_cols)) + "|"
    else:
        colspec = "".join("r" if (i < len(numeric) and numeric[i]) else "l" for i in range(n_cols))
    header = [latex_escape(c) for c in df.columns]
    if rules.header_bold:
        header = [r"\textbf{" + h + "}" for h in header]
    rows = [[latex_escape(format_number(v, rules.decimal_places)) for v in row]
            for row in df.itertuples(index=False)]
    return {
        "number": table.number,
        "caption": latex_escape(strip_caption_label(table.caption)) or f"Table {table.number}",
        "label": f"tab:{table.number}",
        "colspec": colspec,
        "header": header,
        "rows": rows,
        "border": rules.border_style,
        "environment": rules.latex_environment,
        "caption_top": rules.caption_position == "top",
        "font_size": rules.latex_font_size,
        "zebra": rules.zebra_striping,
    }


def render_table(table: Table, template: JournalTemplate) -> str:
    return _ENV.get_template("table.tex.j2").render(t=table_context(table, template))


def render_document(tables: list[Table], equations: list[Equation],
                    template: JournalTemplate) -> str:
    """Önállóan lefordítható LaTeX dokumentum az összes táblázattal és egyenlettel."""
    return _ENV.get_template("document.tex.j2").render(
        template=template,
        font_package=_font_package(template.table.font_family),
        tables=[render_table(t, template) for t in tables],
        equations=[e for e in equations if e.latex],
        needs_xcolor=template.table.zebra_striping,
    )


def render_equations(equations: list[Equation]) -> str:
    return _ENV.get_template("equations.tex.j2").render(
        equations=[e for e in equations if e.latex]
    )
