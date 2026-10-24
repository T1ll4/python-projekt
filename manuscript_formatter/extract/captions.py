"""Képaláírások és szöveges egyenletek felismerése (angol és magyar konvenciók)."""

from __future__ import annotations

import re
from typing import Optional

FIGURE_CAPTION_RE = re.compile(
    r"^\s*(?:"
    r"(?:Figure|Fig\.?|FIGURE|FIG\.?|Abbildung|Abb\.)\s*(?P<n1>\d+)"
    r"|(?:Ábra|ÁBRA)\s*(?P<n2>\d+)"
    r"|(?P<n3>\d+)\.\s*(?:ábra|Ábra|ÁBRA)"
    r")(?P<panel>[a-zA-Z](?![a-zA-Z]))?\s*(?P<sep>[.:|\-–—])?\s*",
)
TABLE_CAPTION_RE = re.compile(
    r"^\s*(?:"
    r"(?:Table|TABLE|Tab\.|Tabelle|Táblázat|TÁBLÁZAT)\s*(?P<n1>\d+|[IVXLC]+)"
    r"|(?P<n3>\d+)\.\s*(?:táblázat|Táblázat|TÁBLÁZAT)"
    r")\s*(?P<sep>[.:|\-–—])?\s*",
)
# szöveges LaTeX egyenlet: $$...$$, \[...\], \begin{equation}...\end{equation}
LATEX_EQ_RE = re.compile(
    r"\$\$(?P<a>.+?)\$\$"
    r"|\\\[(?P<b>.+?)\\\]"
    r"|\\begin\{(?P<env>equation\*?|align\*?|gather\*?|displaymath)\}(?P<c>.+?)\\end\{(?P=env)\}",
    re.DOTALL,
)
# PDF-ből kinyert sor, amely egyenletnek tűnik: tartalmaz '='-t és sorvégi számozást, pl. "E = mc2   (1)"
PDF_EQUATION_RE = re.compile(r"^\s*(?P<body>\S.*?=.*?\S)\s{2,}\((?P<num>\d+[a-z]?)\)\s*$")


def _is_caption_match(match: Optional[re.Match], text: str, strict: bool) -> bool:
    if match is None:
        return False
    if not strict or match.group("sep"):
        return True
    rest = text[match.end():]
    # „Figure 2 shows ...” típusú hivatkozás a folyószövegben nem képaláírás
    return not rest.strip() or rest[0].isupper() or not rest[0].isalpha()


def caption_kind(text: str, strict: bool = True) -> Optional[str]:
    """'figure', 'table' vagy None, attól függően, hogy a szöveg képaláírásnak tűnik-e.

    ``strict=True`` esetén szám után elválasztó (``.``, ``:``, ``-``) vagy nagybetűs
    folytatás szükséges, így a folyószövegbeli hivatkozások nem minősülnek aláírásnak.
    """
    if not text or len(text) > 2000:
        return None
    if _is_caption_match(FIGURE_CAPTION_RE.match(text), text, strict):
        return "figure"
    if _is_caption_match(TABLE_CAPTION_RE.match(text), text, strict):
        return "table"
    return None


def caption_number(text: str) -> Optional[int]:
    for regex in (FIGURE_CAPTION_RE, TABLE_CAPTION_RE):
        match = regex.match(text)
        if match:
            for key in ("n1", "n2", "n3"):
                value = match.groupdict().get(key)
                if value and value.isdigit():
                    return int(value)
    return None


def find_latex_equations(text: str) -> list[str]:
    result = []
    for match in LATEX_EQ_RE.finditer(text or ""):
        body = match.group("a") or match.group("b") or match.group("c") or ""
        body = " ".join(body.split())
        if body:
            result.append(body)
    return result
