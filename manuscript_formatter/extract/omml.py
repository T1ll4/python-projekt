"""Office Math Markup Language (OMML, Word-egyenletek) → LaTeX konverzió.

A Word dokumentumokban az egyenletek ``m:oMath`` XML elemekként tárolódnak.
Ez a modul a leggyakoribb szerkezeteket (tört, kitevő, index, gyök, szumma /
integrál, zárójelek, függvények, ékezetek, mátrixok, egyenletrendszerek)
LaTeX-re fordítja. Ismeretlen elemnél a gyermekelemek tartalmát fűzi össze,
így szöveg sosem vész el.
"""

from __future__ import annotations

from lxml import etree

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _m(tag: str) -> str:
    return f"{{{M_NS}}}{tag}"


SYMBOLS = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\epsilon",
    "ϵ": r"\epsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "ϑ": r"\vartheta",
    "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu", "ξ": r"\xi",
    "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "ς": r"\varsigma", "τ": r"\tau",
    "υ": r"\upsilon", "φ": r"\phi", "ϕ": r"\phi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda", "Ξ": r"\Xi",
    "Π": r"\Pi", "Σ": r"\Sigma", "Υ": r"\Upsilon", "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
    "×": r"\times", "·": r"\cdot", "⋅": r"\cdot", "÷": r"\div", "±": r"\pm", "∓": r"\mp",
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx", "≡": r"\equiv", "∼": r"\sim",
    "∝": r"\propto", "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla", "∈": r"\in",
    "∉": r"\notin", "⊂": r"\subset", "⊆": r"\subseteq", "∪": r"\cup", "∩": r"\cap",
    "∀": r"\forall", "∃": r"\exists", "→": r"\rightarrow", "←": r"\leftarrow",
    "⇒": r"\Rightarrow", "⇔": r"\Leftrightarrow", "↔": r"\leftrightarrow", "…": r"\ldots",
    "⋯": r"\cdots", "°": r"^{\circ}", "′": "'", "″": "''", "−": "-", "∗": "*", "ℏ": r"\hbar",
    "ℓ": r"\ell", "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∬": r"\iint", "∭": r"\iiint",
    "∮": r"\oint", "√": r"\surd", "⟨": r"\langle", "⟩": r"\rangle", "‖": r"\|",
    "⁡": "", "​": "", "⁢": "", "⁣": "",
}
ESCAPES = {"%": r"\%", "#": r"\#", "&": r"\&", "$": r"\$", "_": r"\_"}
FUNCTIONS = {"sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "sinh",
             "cosh", "tanh", "log", "ln", "lg", "exp", "lim", "max", "min", "sup", "inf",
             "det", "dim", "ker", "deg", "arg", "gcd", "Pr"}
ACCENTS = {"̂": r"\hat", "^": r"\hat", "̃": r"\tilde", "~": r"\tilde",
           "̄": r"\bar", "¯": r"\bar", "̅": r"\overline", "̇": r"\dot",
           "̈": r"\ddot", "⃗": r"\vec", "→": r"\vec", "̌": r"\check"}
BRACKETS = {"(": "(", ")": ")", "[": "[", "]": "]", "{": r"\{", "}": r"\}", "|": "|",
            "‖": r"\|", "⟨": r"\langle", "⟩": r"\rangle", "⌊": r"\lfloor", "⌋": r"\rfloor",
            "⌈": r"\lceil", "⌉": r"\rceil", "": "."}


def _val(element, path: str, default: str | None = None) -> str | None:
    """Egy tulajdonság-elem ``m:val`` attribútuma (pl. ``m:naryPr/m:chr``)."""
    if element is None:
        return default
    node = element.find(path, {"m": M_NS})
    if node is None:
        return default
    return node.get(_m("val"), default)


def convert_text(text: str) -> str:
    out = []
    for ch in text:
        if ch in SYMBOLS:
            sym = SYMBOLS[ch]
            out.append(sym + (" " if sym.startswith("\\") and sym[-1].isalpha() else ""))
        elif ch in ESCAPES:
            out.append(ESCAPES[ch])
        elif ch in "{}":
            out.append("\\" + ch)
        else:
            out.append(ch)
    result = "".join(out)
    stripped = result.strip()
    if stripped in FUNCTIONS:
        return "\\" + stripped + " "
    return result


def _child(element, tag: str):
    return element.find(_m(tag))


def _conv(element) -> str:
    """Egy elem gyermekeinek konvertálása."""
    if element is None:
        return ""
    return "".join(convert_node(child) for child in element)


def _group(element) -> str:
    return "{" + _conv(element).strip() + "}"


def convert_node(node) -> str:  # noqa: C901 - elágazó, de lineárisan olvasható
    if not isinstance(node.tag, str):
        return ""
    tag = etree.QName(node).localname
    ns = etree.QName(node).namespace

    if tag.endswith("Pr") and ns == M_NS:
        return ""  # tulajdonság-elemek
    if ns == W_NS:
        if tag == "t":
            return convert_text(node.text or "")
        if tag in ("rPr", "pPr"):
            return ""
        return _conv(node)
    if ns != M_NS:
        return _conv(node)

    if tag == "t":
        return convert_text(node.text or "")
    if tag == "r":
        text = "".join(t.text or "" for t in node.iter(_m("t")))
        converted = convert_text(text)
        word = text.strip()
        plain = node.find("m:rPr/m:nor", {"m": M_NS}) is not None or (
            _val(node, "m:rPr/m:sty") == "p" and len(word) > 1 and word.isalpha()
        )
        if plain and word and word not in FUNCTIONS:
            return r"\mathrm{" + converted + "}"
        return converted
    if tag == "f":
        num, den = _group(_child(node, "num")), _group(_child(node, "den"))
        ftype = _val(node, "m:fPr/m:type", "bar")
        if ftype == "lin":
            return f"{num}/{den}"
        if ftype == "noBar":
            return r"\genfrac{}{}{0pt}{}" + num + den
        return r"\frac" + num + den
    if tag == "sSup":
        return _group(_child(node, "e")) + "^" + _group(_child(node, "sup"))
    if tag == "sSub":
        return _group(_child(node, "e")) + "_" + _group(_child(node, "sub"))
    if tag == "sSubSup":
        return (_group(_child(node, "e")) + "_" + _group(_child(node, "sub"))
                + "^" + _group(_child(node, "sup")))
    if tag == "sPre":
        return ("{}_" + _group(_child(node, "sub")) + "^" + _group(_child(node, "sup"))
                + _group(_child(node, "e")))
    if tag == "rad":
        deg = _conv(_child(node, "deg")).strip()
        hide = _val(node, "m:radPr/m:degHide")
        body = _group(_child(node, "e"))
        if deg and hide not in ("1", "on", "true"):
            return r"\sqrt[" + deg + "]" + body
        return r"\sqrt" + body
    if tag == "nary":
        char = _val(node, "m:naryPr/m:chr", "∫")
        op = SYMBOLS.get(char, char)
        result = op
        sub = _conv(_child(node, "sub")).strip()
        sup = _conv(_child(node, "sup")).strip()
        if sub:
            result += "_{" + sub + "}"
        if sup:
            result += "^{" + sup + "}"
        return result + " " + _group(_child(node, "e"))
    if tag == "d":
        beg = _val(node, "m:dPr/m:begChr", "(")
        end = _val(node, "m:dPr/m:endChr", ")")
        sep = _val(node, "m:dPr/m:sepChr", "|")
        parts = [_conv(e).strip() for e in node.findall(_m("e"))]
        sep_tex = r" \mid " if sep == "|" else " " + BRACKETS.get(sep, sep) + " "
        if sep == ",":
            sep_tex = ", "
        inner = sep_tex.join(parts)
        return (r"\left" + BRACKETS.get(beg, beg) + inner
                + r"\right" + BRACKETS.get(end, end))
    if tag == "func":
        name = _conv(_child(node, "fName")).strip()
        if name in FUNCTIONS:
            name = "\\" + name
        return name + " " + _group(_child(node, "e"))
    if tag == "acc":
        char = _val(node, "m:accPr/m:chr", "̂")
        cmd = ACCENTS.get(char, r"\hat")
        return cmd + _group(_child(node, "e"))
    if tag == "bar":
        pos = _val(node, "m:barPr/m:pos", "bot")
        cmd = r"\overline" if pos == "top" else r"\underline"
        return cmd + _group(_child(node, "e"))
    if tag == "limLow":
        return _group(_child(node, "e")) + "_" + _group(_child(node, "lim"))
    if tag == "limUpp":
        return _group(_child(node, "e")) + "^" + _group(_child(node, "lim"))
    if tag == "groupChr":
        pos = _val(node, "m:groupChrPr/m:pos", "bot")
        cmd = r"\overbrace" if pos == "top" else r"\underbrace"
        return cmd + _group(_child(node, "e"))
    if tag == "eqArr":
        rows = [_conv(e).strip() for e in node.findall(_m("e"))]
        return r"\begin{aligned}" + r" \\ ".join(rows) + r"\end{aligned}"
    if tag == "m":
        rows = []
        for mr in node.findall(_m("mr")):
            rows.append(" & ".join(_conv(e).strip() for e in mr.findall(_m("e"))))
        return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"
    if tag == "oMathPara":
        maths = [omml_to_latex(m) for m in node.findall(_m("oMath"))]
        return r" \\ ".join(maths)
    # oMath, e, num, den, box, borderBox, phant, fName, sub, sup, ...
    return _conv(node)


def omml_to_latex(element) -> str:
    """Egy ``m:oMath`` vagy ``m:oMathPara`` elem LaTeX alakja (``$`` nélkül)."""
    latex = convert_node(element)
    return " ".join(latex.split())


def omml_to_text(element) -> str:
    """Az egyenlet egyszerű szöveges (lineáris) alakja."""
    return "".join(t.text or "" for t in element.iter(_m("t")))
