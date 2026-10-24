"""A teljes feldolgozási folyamat: elemzés → konverzió → kimeneti csomagok."""

from __future__ import annotations

import datetime as _dt
import io
import json
import os
import zipfile
from dataclasses import dataclass, field
from typing import Optional, Union

from . import __version__
from .equations import EquationRenderError, render_equation_png
from .export.excel_export import build_excel
from .export.latex_export import render_document, render_equations, render_table
from .extract import extract_document
from .imaging import ImageProcessingError, process_image, rules_for_equations, safe_stem
from .models import ExtractionResult, ProcessedImage
from .templates import JournalTemplate


@dataclass
class ProcessResult:
    template: JournalTemplate
    extraction: ExtractionResult
    figures: list[ProcessedImage] = field(default_factory=list)
    equation_images: list[ProcessedImage] = field(default_factory=list)
    failed_figures: list[tuple[str, bytes, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # -- kimenetek ------------------------------------------------------
    def report(self) -> dict:
        ex = self.extraction
        return {
            "generator": f"journal-figure-formatter {__version__}",
            "created": _dt.datetime.now().isoformat(timespec="seconds"),
            "source_file": ex.source_file,
            "template": {"id": self.template.id, "name": self.template.name},
            "summary": {
                "figures": len(self.figures),
                "figures_failed": len(self.failed_figures),
                "tables": len(ex.tables),
                "equations": len(ex.equations),
                "equation_images": len(self.equation_images),
            },
            "figures": [f.to_report() for f in self.figures],
            "failed_figures": [{"source": n, "error": e} for n, _, e in self.failed_figures],
            "tables": [{"number": t.number, "caption": t.caption, "rows": int(t.dataframe.shape[0]),
                        "columns": int(t.dataframe.shape[1])} for t in ex.tables],
            "equations": [{"number": e.number, "latex": e.latex, "text": e.text}
                          for e in ex.equations],
            "warnings": list(self.warnings),
        }

    def excel_bytes(self) -> bytes:
        return build_excel(self.extraction.tables, self.template,
                           [f.to_report() for f in self.figures])

    def latex_files(self) -> dict[str, str]:
        """Különálló .tex fájlok: táblázatonként egy, egyenletek, és egy fordítható fődokumentum."""
        rules = self.template.table
        files = {}
        for table in self.extraction.tables:
            name = safe_stem(rules.filename_pattern.format(number=table.number))
            files[f"{name}.tex"] = render_table(table, self.template)
        if any(e.latex for e in self.extraction.equations):
            files["equations.tex"] = render_equations(self.extraction.equations)
        files["main.tex"] = render_document(self.extraction.tables, self.extraction.equations,
                                            self.template)
        return files

    def latex_zip_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for name, content in self.latex_files().items():
                zf.writestr(name, content)
        return buf.getvalue()

    def zip_bytes(self) -> bytes:
        """A teljes, kiadónak leadható csomag."""
        stem = safe_stem(os.path.splitext(self.extraction.source_file)[0]) or "manuscript"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for fig in self.figures:
                zf.writestr(f"figures/{fig.filename}", fig.data)
            for name, data, _ in self.failed_figures:
                zf.writestr(f"figures_unconverted/{name}", data)
            for eq in self.equation_images:
                zf.writestr(f"equations/{eq.filename}", eq.data)
            if self.extraction.tables:
                zf.writestr(f"tables/{stem}_tables.xlsx", self.excel_bytes())
            for name, content in self.latex_files().items():
                zf.writestr(f"tables/latex/{name}", content)
            zf.writestr("captions.txt", self.captions_text())
            zf.writestr("report.json", json.dumps(self.report(), indent=2, ensure_ascii=False))
            zf.writestr("template.json", json.dumps(self.template.to_dict(), indent=2,
                                                    ensure_ascii=False))
        return buf.getvalue()

    def captions_text(self) -> str:
        lines = ["FIGURE CAPTIONS", "=" * 15]
        groups: dict[str, list[str]] = {}
        for fig in self.figures:  # a több panelből álló ábrák egy aláírás alatt
            groups.setdefault(fig.caption or f"\0{fig.filename}", []).append(fig.filename)
        for caption, names in groups.items():
            text = "(nincs képaláírás)" if caption.startswith("\0") else caption
            lines.append(f"{', '.join(names)}: {text}")
        lines += ["", "TABLE CAPTIONS", "=" * 14]
        for table in self.extraction.tables:
            lines.append(f"{table.label}: {table.caption or '(nincs felirat)'}")
        return "\n".join(lines) + "\n"


def process_extraction(extraction: ExtractionResult, template: JournalTemplate,
                       sizing: Optional[str] = None) -> ProcessResult:
    result = ProcessResult(template=template, extraction=extraction,
                           warnings=list(extraction.warnings))
    rules = template.figure
    used_names: set[str] = set()

    for fig in extraction.figures:
        stem = rules.filename_pattern.format(number=fig.number) + fig.panel
        label = None
        if rules.add_label:
            label = f"({fig.panel})" if fig.panel else f"Fig. {fig.number}"
        try:
            processed = process_image(fig.data, rules, stem, caption=fig.caption,
                                      label_text=label, sizing=sizing)
        except ImageProcessingError as exc:
            name = safe_stem(stem) + os.path.splitext(fig.source_name)[1].lower()
            result.failed_figures.append((name, fig.data, str(exc)))
            result.warnings.append(f"{fig.label} ({fig.source_name}) nem konvertálható: {exc} "
                                   "– az eredeti fájl a figures_unconverted mappába került.")
            continue
        processed.filename = _unique(processed.filename, used_names)
        result.figures.append(processed)
        for warning in processed.warnings:
            result.warnings.append(f"{fig.label}: {warning}")

    eq_rules = template.equation
    if eq_rules.render_images:
        image_rules = rules_for_equations(rules, eq_rules.file_format, rules.color_mode)
        for eq in extraction.equations:
            if not eq.latex:
                continue
            stem = eq_rules.filename_pattern.format(number=eq.number)
            try:
                png = render_equation_png(eq.latex, eq_rules)
                processed = process_image(png, image_rules, stem, caption=eq.latex,
                                          dpi_override=eq_rules.dpi)
            except (EquationRenderError, ImageProcessingError) as exc:
                result.warnings.append(f"{eq.label}: {exc} (a LaTeX forrás a .tex fájlban megvan)")
                continue
            processed.filename = _unique(processed.filename, used_names)
            result.equation_images.append(processed)
    return result


def _unique(filename: str, used: set[str]) -> str:
    base, ext = os.path.splitext(filename)
    candidate, n = filename, 2
    while candidate.lower() in used:
        candidate = f"{base}_{n}{ext}"
        n += 1
    used.add(candidate.lower())
    return candidate


def process_manuscript(source: Union[str, os.PathLike, bytes], template: JournalTemplate,
                       filename: str = "", sizing: Optional[str] = None) -> ProcessResult:
    """Kézirat elemzése és minden elem konvertálása a megadott sablon szerint."""
    extraction = extract_document(source, filename=filename)
    return process_extraction(extraction, template, sizing=sizing)
