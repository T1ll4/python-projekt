"""Egyenletek képpé renderelése (matplotlib mathtext) a sablon betűtípusával és felbontásával."""

from __future__ import annotations

import io

from .templates import EquationRules

_SERIF = ("times", "times new roman", "georgia", "garamond", "palatino", "cambria", "serif")
_SANS = ("arial", "helvetica", "calibri", "verdana", "sans", "sans-serif", "liberation sans")

# a mathtext által nem ismert, de ártalmatlanul elhagyható / helyettesíthető parancsok
_REPLACEMENTS = {
    r"\left.": "", r"\right.": "", r"\begin{aligned}": "", r"\end{aligned}": "",
    r"\begin{matrix}": "", r"\end{matrix}": "", r"\displaystyle": "", r"\text{": r"\mathrm{",
    r"\operatorname{": r"\mathrm{", r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\lvert": "|",
    r"\rvert": "|", r"\coloneqq": ":=", r"\iint": r"\int\int", r"\iiint": r"\int\int\int",
    r"\nonumber": "", "&": "", r"\\": r"\quad ",
}


class EquationRenderError(Exception):
    pass


def mathtext_fontset(font_family: str) -> str:
    low = font_family.strip().lower()
    if any(name in low for name in _SANS):
        return "stixsans"
    if any(name in low for name in _SERIF):
        return "stix"
    return "cm"


def prepare_for_mathtext(latex: str) -> str:
    text = latex.strip().strip("$").strip()
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    return " ".join(text.split())


def render_equation_png(latex: str, rules: EquationRules) -> bytes:
    """LaTeX egyenlet → PNG bájtok a megadott DPI-vel. Hiba esetén EquationRenderError."""
    if not latex.strip():
        raise EquationRenderError("Üres egyenlet.")
    try:
        import matplotlib

        matplotlib.use("Agg", force=False)
        from matplotlib import rc_context
        from matplotlib.figure import Figure
    except ImportError:  # pragma: no cover
        raise EquationRenderError("A matplotlib nincs telepítve.") from None

    expression = f"${prepare_for_mathtext(latex)}$"
    with rc_context({"mathtext.fontset": mathtext_fontset(rules.font_family)}):
        fig = Figure(figsize=(0.01, 0.01))
        fig.text(0, 0, expression, fontsize=rules.font_size_pt)
        buf = io.BytesIO()
        try:
            fig.savefig(buf, format="png", dpi=rules.dpi, bbox_inches="tight",
                        pad_inches=0.02, facecolor="white")
        except Exception as exc:  # mathtext ParseException, ValueError, ...
            message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            raise EquationRenderError(f"Nem renderelhető: {message}") from None
    return buf.getvalue()
