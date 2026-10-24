"""Parancssori felület.

Példák::

    python -m manuscript_formatter process kezirat.docx -t elsevier -o leadas.zip
    python -m manuscript_formatter process kezirat.pdf -t ieee --excel t.xlsx --latex tablak/
    python -m manuscript_formatter templates list
    python -m manuscript_formatter templates export elsevier -o sajat.json
    python -m manuscript_formatter templates import sajat.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .extract import SUPPORTED_EXTENSIONS, PandocError, UnsupportedFormatError
from .pipeline import process_manuscript
from .templates import SIZING_MODES, TemplateError, TemplateStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manuscript_formatter",
        description="Tudományos kéziratok ábráinak, táblázatainak és egyenleteinek "
                    "kiadói formázása.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--template-dir", help="felhasználói sablonkönyvtár "
                                               "(alapértelmezés: ./user_templates)")
    sub = parser.add_subparsers(dest="command", required=True)

    proc = sub.add_parser("process", help="kézirat feldolgozása")
    proc.add_argument("input", help=f"bemeneti fájl ({', '.join(SUPPORTED_EXTENSIONS)})")
    proc.add_argument("-t", "--template", required=True, help="sablon azonosító (pl. elsevier)")
    proc.add_argument("-o", "--output", help="kimeneti ZIP (alapértelmezés: <bemenet>_<sablon>.zip)")
    proc.add_argument("--excel", help="a táblázatok Excel fájlja külön is ide kerül")
    proc.add_argument("--latex", help="a LaTeX táblázatok könyvtára (külön .tex fájlok)")
    proc.add_argument("--sizing", choices=SIZING_MODES, help="méretezési mód felülírása")

    tpl = sub.add_parser("templates", help="sablonok kezelése")
    tsub = tpl.add_subparsers(dest="action", required=True)
    tsub.add_parser("list", help="sablonok listázása")
    show = tsub.add_parser("show", help="sablon megjelenítése JSON-ként")
    show.add_argument("id")
    exp = tsub.add_parser("export", help="sablon exportálása JSON fájlba")
    exp.add_argument("id")
    exp.add_argument("-o", "--output", required=True)
    imp = tsub.add_parser("import", help="sablon importálása JSON fájlból")
    imp.add_argument("file")
    delete = tsub.add_parser("delete", help="felhasználói sablon törlése")
    delete.add_argument("id")
    return parser


def _process(args, store: TemplateStore) -> int:
    template = store.get(args.template)
    source = Path(args.input)
    if not source.is_file():
        print(f"Hiba: a fájl nem létezik: {source}", file=sys.stderr)
        return 2
    result = process_manuscript(str(source), template, sizing=args.sizing)
    output = Path(args.output or f"{source.stem}_{template.id}.zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result.zip_bytes())

    ex = result.extraction
    print(f"Sablon:     {template.name}")
    print(f"Ábrák:      {len(result.figures)} konvertálva"
          + (f", {len(result.failed_figures)} sikertelen" if result.failed_figures else ""))
    print(f"Táblázatok: {len(ex.tables)}")
    print(f"Egyenletek: {len(ex.equations)} ({len(result.equation_images)} képként)")
    print(f"ZIP csomag: {output}")
    if args.excel:
        Path(args.excel).write_bytes(result.excel_bytes())
        print(f"Excel:      {args.excel}")
    if args.latex:
        directory = Path(args.latex)
        directory.mkdir(parents=True, exist_ok=True)
        for name, content in result.latex_files().items():
            (directory / name).write_text(content, encoding="utf-8")
        print(f"LaTeX:      {directory}/")
    if result.warnings:
        print("\nFigyelmeztetések:")
        for warning in result.warnings:
            print(f"  - {warning}")
    return 0


def _templates(args, store: TemplateStore) -> int:
    if args.action == "list":
        for tpl in store.list_all():
            kind = "beépített" if tpl.builtin else "egyéni"
            f = tpl.figure
            print(f"{tpl.id:<20} {tpl.name:<30} [{kind}] {f.file_format}, {f.color_mode}, "
                  f"{f.dpi}/{f.line_art_dpi} dpi, {f.single_column_mm}/{f.double_column_mm} mm")
    elif args.action == "show":
        print(store.export_json(store.get(args.id)))
    elif args.action == "export":
        Path(args.output).write_text(store.export_json(store.get(args.id)), encoding="utf-8")
        print(f"Exportálva: {args.output}")
    elif args.action == "import":
        tpl = store.import_json(Path(args.file).read_text(encoding="utf-8"))
        print(f"Importálva: {tpl.id} ({tpl.name})")
    elif args.action == "delete":
        store.delete(args.id)
        print(f"Törölve: {args.id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    store = TemplateStore(user_dir=args.template_dir)
    try:
        if args.command == "process":
            return _process(args, store)
        return _templates(args, store)
    except (TemplateError, UnsupportedFormatError, PandocError, ValueError, OSError) as exc:
        print(f"Hiba: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
