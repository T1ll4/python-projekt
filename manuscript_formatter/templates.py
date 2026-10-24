"""Kiadói (folyóirat-specifikus) formázási sablonok kezelése.

A sablonok JSON fájlokban tárolódnak. A beépített sablonok a csomag
``builtin_templates`` könyvtárában vannak (csak olvashatók), a felhasználó
által a felületen létrehozott / módosított sablonok pedig a felhasználói
sablonkönyvtárba kerülnek (alapértelmezés: ``./user_templates``, felülírható a
``MF_TEMPLATE_DIR`` környezeti változóval). Azonos azonosító esetén a
felhasználói sablon felülírja a beépítettet.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

BUILTIN_DIR = Path(__file__).parent / "builtin_templates"

COLOR_MODES = ("RGB", "CMYK", "Grayscale", "Bilevel")
FIGURE_FORMATS = ("TIFF", "EPS", "PNG", "JPEG", "PDF")
TIFF_COMPRESSIONS = ("none", "tiff_lzw", "tiff_deflate")
SIZING_MODES = ("auto", "single", "one_half", "double", "original")
TABLE_BORDERS = ("booktabs", "grid", "none")
CAPTION_POSITIONS = ("top", "bottom")
LATEX_ENVS = ("table", "table*")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


class TemplateError(ValueError):
    """Érvénytelen sablon vagy sablonművelet."""


@dataclass
class FigureRules:
    dpi: int = 300
    line_art_dpi: int = 600
    color_mode: str = "RGB"
    file_format: str = "TIFF"
    tiff_compression: str = "tiff_lzw"
    jpeg_quality: int = 95
    single_column_mm: float = 85.0
    one_half_column_mm: float = 0.0
    double_column_mm: float = 175.0
    max_height_mm: float = 230.0
    sizing: str = "auto"
    allow_upscale: bool = True
    auto_trim: bool = True
    trim_padding_px: int = 10
    detect_line_art: bool = True
    font_family: str = "Arial"
    font_size_pt: float = 8.0
    min_font_size_pt: float = 6.0
    add_label: bool = False
    filename_pattern: str = "Fig{number}"


@dataclass
class TableRules:
    font_family: str = "Times New Roman"
    font_size_pt: float = 9.0
    header_bold: bool = True
    header_fill: str = "D9D9D9"
    border_style: str = "booktabs"
    zebra_striping: bool = False
    caption_position: str = "top"
    latex_environment: str = "table"
    latex_font_size: str = "\\small"
    decimal_places: int = -1
    filename_pattern: str = "Table{number}"


@dataclass
class EquationRules:
    render_images: bool = True
    dpi: int = 600
    file_format: str = "PNG"
    font_size_pt: float = 10.0
    font_family: str = "Times New Roman"
    filename_pattern: str = "Eq{number}"


@dataclass
class JournalTemplate:
    id: str
    name: str
    description: str = ""
    publisher: str = ""
    figure: FigureRules = field(default_factory=FigureRules)
    table: TableRules = field(default_factory=TableRules)
    equation: EquationRules = field(default_factory=EquationRules)
    builtin: bool = False

    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("builtin", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], builtin: bool = False) -> "JournalTemplate":
        if not isinstance(data, dict):
            raise TemplateError("A sablonnak JSON objektumnak kell lennie.")
        tpl = cls(
            id=str(data.get("id", "")).strip(),
            name=str(data.get("name", "")).strip(),
            description=str(data.get("description", "")),
            publisher=str(data.get("publisher", "")),
            figure=_section_from_dict(FigureRules, data.get("figure", {}), "figure"),
            table=_section_from_dict(TableRules, data.get("table", {}), "table"),
            equation=_section_from_dict(EquationRules, data.get("equation", {}), "equation"),
            builtin=builtin,
        )
        tpl.validate()
        return tpl

    def validate(self) -> None:
        errors: list[str] = []
        if not _ID_RE.match(self.id):
            errors.append(
                "Az azonosító csak kisbetűt, számot, '-' és '_' karaktert tartalmazhat (max. 64)."
            )
        if not self.name:
            errors.append("A sablon neve nem lehet üres.")
        f, t, e = self.figure, self.table, self.equation
        _check_choice(errors, "figure.color_mode", f.color_mode, COLOR_MODES)
        _check_choice(errors, "figure.file_format", f.file_format, FIGURE_FORMATS)
        _check_choice(errors, "figure.tiff_compression", f.tiff_compression, TIFF_COMPRESSIONS)
        _check_choice(errors, "figure.sizing", f.sizing, SIZING_MODES)
        _check_range(errors, "figure.dpi", f.dpi, 72, 2400)
        _check_range(errors, "figure.line_art_dpi", f.line_art_dpi, 72, 2400)
        _check_range(errors, "figure.jpeg_quality", f.jpeg_quality, 1, 100)
        _check_range(errors, "figure.single_column_mm", f.single_column_mm, 10, 500)
        _check_range(errors, "figure.one_half_column_mm", f.one_half_column_mm, 0, 500)
        _check_range(errors, "figure.double_column_mm", f.double_column_mm, 10, 500)
        _check_range(errors, "figure.max_height_mm", f.max_height_mm, 10, 1000)
        _check_range(errors, "figure.trim_padding_px", f.trim_padding_px, 0, 500)
        _check_range(errors, "figure.font_size_pt", f.font_size_pt, 4, 72)
        _check_range(errors, "figure.min_font_size_pt", f.min_font_size_pt, 2, 72)
        if f.double_column_mm < f.single_column_mm:
            errors.append("figure.double_column_mm nem lehet kisebb, mint single_column_mm.")
        if f.file_format == "JPEG" and f.color_mode == "Bilevel":
            errors.append("JPEG formátum nem támogatja a Bilevel (1 bites) színmódot.")
        if f.file_format == "PNG" and f.color_mode == "CMYK":
            errors.append("PNG formátum nem támogatja a CMYK színmódot (válasszon TIFF/EPS/JPEG/PDF-et).")
        _check_pattern(errors, "figure.filename_pattern", f.filename_pattern)

        _check_choice(errors, "table.border_style", t.border_style, TABLE_BORDERS)
        _check_choice(errors, "table.caption_position", t.caption_position, CAPTION_POSITIONS)
        _check_choice(errors, "table.latex_environment", t.latex_environment, LATEX_ENVS)
        _check_range(errors, "table.font_size_pt", t.font_size_pt, 4, 72)
        _check_range(errors, "table.decimal_places", t.decimal_places, -1, 10)
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", t.header_fill or ""):
            errors.append("table.header_fill 6 jegyű hexa színkód kell legyen (pl. D9D9D9).")
        _check_pattern(errors, "table.filename_pattern", t.filename_pattern)

        _check_choice(errors, "equation.file_format", e.file_format, FIGURE_FORMATS)
        _check_range(errors, "equation.dpi", e.dpi, 72, 2400)
        _check_range(errors, "equation.font_size_pt", e.font_size_pt, 4, 72)
        _check_pattern(errors, "equation.filename_pattern", e.filename_pattern)
        if errors:
            raise TemplateError("; ".join(errors))


# ---------------------------------------------------------------------- #
def _section_from_dict(cls, data: Any, section: str):
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise TemplateError(f"A '{section}' szekciónak objektumnak kell lennie.")
    known = {f.name: f for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise TemplateError(f"Ismeretlen mező(k) a '{section}' szekcióban: {', '.join(sorted(unknown))}")
    defaults = cls()
    kwargs = {}
    for name, value in data.items():
        expected = type(getattr(defaults, name))
        kwargs[name] = _coerce(value, expected, f"{section}.{name}")
    return cls(**kwargs)


def _coerce(value: Any, expected: type, name: str) -> Any:
    try:
        if expected is bool:
            if isinstance(value, str):
                low = value.strip().lower()
                if low in ("true", "1", "yes", "igen"):
                    return True
                if low in ("false", "0", "no", "nem"):
                    return False
                raise ValueError
            return bool(value)
        if expected is int:
            if isinstance(value, float) and not value.is_integer():
                raise ValueError
            return int(value)
        if expected is float:
            return float(value)
        return str(value)
    except (TypeError, ValueError):
        raise TemplateError(f"Érvénytelen érték a '{name}' mezőben: {value!r}") from None


def _check_choice(errors: list[str], name: str, value: Any, choices: tuple) -> None:
    if value not in choices:
        errors.append(f"{name} értéke csak {', '.join(choices)} lehet (kapott: {value!r}).")


def _check_range(errors: list[str], name: str, value: float, lo: float, hi: float) -> None:
    if not lo <= value <= hi:
        errors.append(f"{name} értéke {lo} és {hi} között kell legyen (kapott: {value}).")


def _check_pattern(errors: list[str], name: str, pattern: str) -> None:
    if "{number}" not in pattern:
        errors.append(f"{name} tartalmazza a {{number}} helyőrzőt.")
        return
    try:
        result = pattern.format(number=1)
    except (KeyError, IndexError, ValueError):
        errors.append(f"{name} csak a {{number}} helyőrzőt használhatja.")
        return
    if re.search(r'[\\/:*?"<>|]', result):
        errors.append(f"{name} nem tartalmazhat fájlnévben tiltott karaktert.")


# ---------------------------------------------------------------------- #
class TemplateStore:
    """Beépített + felhasználói sablonok betöltése, mentése, törlése."""

    def __init__(self, user_dir: str | os.PathLike | None = None,
                 builtin_dir: str | os.PathLike | None = None) -> None:
        self.builtin_dir = Path(builtin_dir) if builtin_dir else BUILTIN_DIR
        self.user_dir = Path(user_dir or os.environ.get("MF_TEMPLATE_DIR", "user_templates"))

    # -- olvasás ---------------------------------------------------------
    def _load_dir(self, directory: Path, builtin: bool) -> dict[str, JournalTemplate]:
        result: dict[str, JournalTemplate] = {}
        if not directory.is_dir():
            return result
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                tpl = JournalTemplate.from_dict(data, builtin=builtin)
            except (OSError, json.JSONDecodeError, TemplateError):
                continue  # sérült fájl ne akassza meg a felületet
            result[tpl.id] = tpl
        return result

    def list_all(self) -> list[JournalTemplate]:
        merged = self._load_dir(self.builtin_dir, builtin=True)
        merged.update(self._load_dir(self.user_dir, builtin=False))
        return sorted(merged.values(), key=lambda t: t.name.lower())

    def ids(self) -> list[str]:
        return [t.id for t in self.list_all()]

    def get(self, template_id: str) -> JournalTemplate:
        for tpl in self.list_all():
            if tpl.id == template_id:
                return tpl
        raise TemplateError(f"Nincs ilyen sablon: {template_id!r}")

    def is_builtin_only(self, template_id: str) -> bool:
        return (self.builtin_dir / f"{template_id}.json").is_file() and not (
            self.user_dir / f"{template_id}.json"
        ).is_file()

    # -- írás ------------------------------------------------------------
    def save(self, template: JournalTemplate) -> Path:
        template.validate()
        self.user_dir.mkdir(parents=True, exist_ok=True)
        path = self.user_dir / f"{template.id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(template.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return path

    def delete(self, template_id: str) -> None:
        path = self.user_dir / f"{template_id}.json"
        if not _ID_RE.match(template_id) or not path.is_file():
            raise TemplateError(
                f"A(z) {template_id!r} sablon nem törölhető (beépített vagy nem létezik)."
            )
        path.unlink()

    def import_json(self, text: str | bytes) -> JournalTemplate:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TemplateError(f"Hibás JSON: {exc}") from None
        tpl = JournalTemplate.from_dict(data)
        self.save(tpl)
        return tpl

    @staticmethod
    def export_json(template: JournalTemplate) -> str:
        return json.dumps(template.to_dict(), indent=2, ensure_ascii=False)
