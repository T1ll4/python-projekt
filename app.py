"""Streamlit webes felület.

Indítás:  streamlit run app.py
"""

from __future__ import annotations

import dataclasses
import os

import streamlit as st

from manuscript_formatter import __version__
from manuscript_formatter.extract import SUPPORTED_EXTENSIONS, PandocError, UnsupportedFormatError
from manuscript_formatter.extract.pandoc_extractor import pandoc_available
from manuscript_formatter.export.latex_export import render_table
from manuscript_formatter.pipeline import ProcessResult, process_manuscript
from manuscript_formatter.templates import (
    CAPTION_POSITIONS, COLOR_MODES, FIGURE_FORMATS, LATEX_ENVS, SIZING_MODES, TABLE_BORDERS,
    TIFF_COMPRESSIONS, EquationRules, FigureRules, JournalTemplate, TableRules, TemplateError,
    TemplateStore,
)

st.set_page_config(page_title="Journal Figure Formatter", page_icon="📐", layout="wide")

# --------------------------------------------------------------------------- #
# Mezőfeliratok és választólisták a sablonszerkesztőhöz
# --------------------------------------------------------------------------- #
LABELS = {
    "figure": {
        "dpi": "Felbontás – fotó / színes (DPI)",
        "line_art_dpi": "Felbontás – vonalas ábra (DPI)",
        "color_mode": "Színmód",
        "file_format": "Fájlformátum",
        "tiff_compression": "TIFF tömörítés",
        "jpeg_quality": "JPEG minőség (1–100)",
        "single_column_mm": "Egyhasábos szélesség (mm)",
        "one_half_column_mm": "Másfél hasábos szélesség (mm, 0 = nincs)",
        "double_column_mm": "Kéthasábos szélesség (mm)",
        "max_height_mm": "Maximális magasság (mm)",
        "sizing": "Méretezési mód",
        "allow_upscale": "Felskálázás engedélyezése",
        "auto_trim": "Fehér margók automatikus levágása",
        "trim_padding_px": "Margó vágás után (px)",
        "detect_line_art": "Vonalas ábrák felismerése (1 bites kimenet)",
        "font_family": "Betűtípus (címkékhez)",
        "font_size_pt": "Betűméret (pt)",
        "min_font_size_pt": "Minimális betűméret (pt)",
        "add_label": "Ábracímke („Fig. 1”, „(a)”) ráírása",
        "filename_pattern": "Fájlnév minta ({number} kötelező)",
    },
    "table": {
        "font_family": "Betűtípus",
        "font_size_pt": "Betűméret (pt)",
        "header_bold": "Félkövér fejléc",
        "header_fill": "Fejléc háttérszín (hex, pl. D9D9D9)",
        "border_style": "Szegélyezés",
        "zebra_striping": "Váltakozó sorszínezés",
        "caption_position": "Felirat helye",
        "latex_environment": "LaTeX környezet",
        "latex_font_size": "LaTeX betűméret parancs (pl. \\small)",
        "decimal_places": "Tizedesjegyek (-1 = eredeti)",
        "filename_pattern": "Fájlnév minta ({number} kötelező)",
    },
    "equation": {
        "render_images": "Egyenletek képként is",
        "dpi": "Felbontás (DPI)",
        "file_format": "Fájlformátum",
        "font_size_pt": "Betűméret (pt)",
        "font_family": "Betűtípus",
        "filename_pattern": "Fájlnév minta ({number} kötelező)",
    },
}
CHOICES = {
    ("figure", "color_mode"): COLOR_MODES,
    ("figure", "file_format"): FIGURE_FORMATS,
    ("figure", "tiff_compression"): TIFF_COMPRESSIONS,
    ("figure", "sizing"): SIZING_MODES,
    ("table", "border_style"): TABLE_BORDERS,
    ("table", "caption_position"): CAPTION_POSITIONS,
    ("table", "latex_environment"): LATEX_ENVS,
    ("equation", "file_format"): FIGURE_FORMATS,
}
SIZING_LABELS = {
    "auto": "automatikus (képarány / eredeti méret alapján)",
    "single": "egyhasábos", "one_half": "másfél hasábos", "double": "kéthasábos",
    "original": "eredeti fizikai méret",
}
SECTION_CLASSES = {"figure": FigureRules, "table": TableRules, "equation": EquationRules}


store = TemplateStore()  # könnyű objektum: minden futáskor a lemezről olvas


# --------------------------------------------------------------------------- #
# Feldolgozás fül
# --------------------------------------------------------------------------- #
def page_process() -> None:
    templates = store.list_all()
    if not templates:
        st.error("Nincs elérhető sablon.")
        return
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        uploaded = st.file_uploader(
            "Kézirat feltöltése",
            type=[e.lstrip(".") for e in SUPPORTED_EXTENSIONS],
            help="DOCX és PDF közvetlenül; ODT, RTF, Markdown, LaTeX, HTML, EPUB, RST pandoc-kal.",
        )
    with col2:
        template_id = st.selectbox(
            "Folyóirat-sablon", [t.id for t in templates],
            format_func=lambda i: next(t.name for t in templates if t.id == i),
        )
        template = store.get(template_id)
        st.caption(template.description or "")
    with col3:
        sizing = st.selectbox("Méretezés", ["(sablon szerint)", *SIZING_MODES],
                              format_func=lambda s: SIZING_LABELS.get(s, s))
        f = template.figure
        st.caption(f"{f.file_format} · {f.color_mode} · {f.dpi}/{f.line_art_dpi} dpi · "
                   f"{f.single_column_mm:g}/{f.double_column_mm:g} mm · {f.font_family}")

    if not pandoc_available():
        st.info("A pandoc nincs telepítve: csak DOCX és PDF dolgozható fel.")

    if st.button("▶ Feldolgozás", type="primary", disabled=uploaded is None):
        with st.spinner("Elemzés és konvertálás…"):
            try:
                result = process_manuscript(
                    uploaded.getvalue(), template, filename=uploaded.name,
                    sizing=None if sizing.startswith("(") else sizing,
                )
            except (UnsupportedFormatError, PandocError, ValueError) as exc:
                st.error(f"Hiba: {exc}")
                return
            except Exception as exc:  # sérült fájl stb.
                st.error(f"A dokumentum nem dolgozható fel: {type(exc).__name__}: {exc}")
                return
            st.session_state["result"] = result
            st.session_state["downloads"] = {
                "zip": result.zip_bytes(),
                "xlsx": result.excel_bytes() if result.extraction.tables else None,
                "latex": result.latex_zip_bytes(),
            }

    result: ProcessResult | None = st.session_state.get("result")
    if result is not None:
        show_result(result)


def show_result(result: ProcessResult) -> None:
    ex = result.extraction
    downloads = st.session_state["downloads"]
    stem = os.path.splitext(ex.source_file)[0] or "manuscript"
    st.divider()
    st.subheader(f"Eredmény – {ex.source_file} · {result.template.name}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ábrák", len(result.figures))
    m2.metric("Táblázatok", len(ex.tables))
    m3.metric("Egyenletek", len(ex.equations))
    m4.metric("Figyelmeztetések", len(result.warnings))

    d1, d2, d3 = st.columns(3)
    d1.download_button("⬇ Teljes ZIP csomag", downloads["zip"],
                       file_name=f"{stem}_{result.template.id}.zip", mime="application/zip",
                       type="primary")
    if downloads["xlsx"]:
        d2.download_button("⬇ Excel táblázatok", downloads["xlsx"], file_name=f"{stem}_tables.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d3.download_button("⬇ LaTeX fájlok (ZIP)", downloads["latex"],
                       file_name=f"{stem}_latex.zip", mime="application/zip")

    if result.warnings:
        with st.expander(f"⚠ Figyelmeztetések ({len(result.warnings)})", expanded=False):
            for warning in result.warnings:
                st.warning(warning)

    tab_fig, tab_tab, tab_eq = st.tabs(["Ábrák", "Táblázatok", "Egyenletek"])
    with tab_fig:
        if not result.figures and not result.failed_figures:
            st.info("Nem található ábra.")
        cols = st.columns(3)
        for i, fig in enumerate(result.figures):
            with cols[i % 3]:
                st.image(fig.preview_png, width="stretch")
                st.markdown(f"**{fig.filename}** – {fig.width_mm:.1f} × {fig.height_mm:.1f} mm, "
                            f"{fig.dpi} dpi, {fig.color_mode}")
                st.caption(f"{fig.width_px} × {fig.height_px} px (eredeti: "
                           f"{fig.original_width_px} × {fig.original_height_px} px, "
                           f"eff. {fig.effective_input_dpi:.0f} dpi)")
                if fig.caption:
                    st.caption(fig.caption)
        for name, _, error in result.failed_figures:
            st.error(f"{name}: {error}")
    with tab_tab:
        if not ex.tables:
            st.info("Nem található táblázat.")
        for table in ex.tables:
            st.markdown(f"**{table.label}** – {table.caption or '(nincs felirat)'}")
            st.dataframe(table.dataframe, width="stretch", hide_index=True)
            with st.expander("LaTeX kód"):
                st.code(render_table(table, result.template), language="latex")
    with tab_eq:
        if not ex.equations:
            st.info("Nem található egyenlet.")
        images = {img.caption: img for img in result.equation_images}
        for eq in ex.equations:
            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown(f"**{eq.label}**")
                if eq.latex:
                    try:
                        st.latex(eq.latex)
                    except Exception:
                        pass
                    st.code(eq.latex, language="latex")
                else:
                    st.text(eq.text)
            with c2:
                img = images.get(eq.latex)
                if img is not None:
                    st.image(img.preview_png)
                    st.caption(f"{img.filename} – {img.dpi} dpi")


# --------------------------------------------------------------------------- #
# Sablonok fül
# --------------------------------------------------------------------------- #
def _widget(section: str, name: str, value, key: str):
    label = LABELS[section].get(name, name)
    choices = CHOICES.get((section, name))
    if choices:
        index = choices.index(value) if value in choices else 0
        return st.selectbox(label, choices, index=index, key=key,
                            format_func=lambda s: SIZING_LABELS.get(s, s) if name == "sizing" else s)
    if isinstance(value, bool):
        return st.checkbox(label, value=value, key=key)
    if isinstance(value, int):
        return int(st.number_input(label, value=value, step=1, key=key))
    if isinstance(value, float):
        return float(st.number_input(label, value=value, step=0.5, format="%.2f", key=key))
    return st.text_input(label, value=str(value), key=key)


def page_templates() -> None:
    templates = store.list_all()
    left, right = st.columns([1, 2])
    with left:
        st.markdown("#### Sablonok")
        options = ["__new__", *[t.id for t in templates]]
        selected = st.radio(
            "Szerkesztendő sablon", options,
            format_func=lambda i: "➕ Új sablon" if i == "__new__" else
            next(f"{t.name} ({'beépített' if t.builtin else 'egyéni'})" for t in templates if t.id == i),
        )
        st.markdown("#### Importálás")
        upload = st.file_uploader("Sablon JSON", type=["json"], key="tpl_import")
        if upload is not None and st.button("Importálás"):
            try:
                tpl = store.import_json(upload.getvalue())
                st.success(f"Importálva: {tpl.name}")
                st.rerun()
            except TemplateError as exc:
                st.error(str(exc))

    with right:
        if selected == "__new__":
            base = JournalTemplate(id="uj_folyoirat", name="Új folyóirat")
            st.markdown("#### Új sablon")
        else:
            base = store.get(selected)
            st.markdown(f"#### {base.name}")
            if base.builtin:
                st.info("Beépített sablon: mentéskor felhasználói példány készül azonos "
                        "azonosítóval (felülírja a beépítettet), vagy adjon meg új azonosítót.")
            st.download_button("⬇ Exportálás JSON-ként", store.export_json(base),
                               file_name=f"{base.id}.json", mime="application/json")
        prefix = f"tpl_{selected}"
        with st.form(key=f"form_{selected}"):
            c1, c2 = st.columns(2)
            new_id = c1.text_input("Azonosító (kisbetű, szám, -, _)", value=base.id, key=f"{prefix}_id")
            new_name = c2.text_input("Megjelenített név", value=base.name, key=f"{prefix}_name")
            publisher = c1.text_input("Kiadó", value=base.publisher, key=f"{prefix}_pub")
            description = st.text_area("Leírás", value=base.description, key=f"{prefix}_desc")
            values: dict[str, dict] = {}
            for section, title in (("figure", "Ábrák"), ("table", "Táblázatok"),
                                   ("equation", "Egyenletek")):
                st.markdown(f"##### {title}")
                current = getattr(base, section)
                cols = st.columns(3)
                values[section] = {}
                for i, fld in enumerate(dataclasses.fields(SECTION_CLASSES[section])):
                    with cols[i % 3]:
                        values[section][fld.name] = _widget(
                            section, fld.name, getattr(current, fld.name),
                            key=f"{prefix}_{section}_{fld.name}",
                        )
            submitted = st.form_submit_button("💾 Mentés", type="primary")
        if submitted:
            data = {"id": new_id.strip(), "name": new_name.strip(), "publisher": publisher,
                    "description": description, **values}
            try:
                tpl = JournalTemplate.from_dict(data)
                store.save(tpl)
                st.success(f"Sablon mentve: {tpl.name} ({tpl.id})")
            except TemplateError as exc:
                st.error(f"A sablon nem menthető: {exc}")

        if selected != "__new__" and not base.builtin:
            if st.button("🗑 Sablon törlése"):
                try:
                    store.delete(base.id)
                    st.success("Törölve.")
                    st.rerun()
                except TemplateError as exc:
                    st.error(str(exc))


# --------------------------------------------------------------------------- #
def page_help() -> None:
    st.markdown(f"""
**Journal Figure Formatter {__version__}**

1. **Feldolgozás** fül: töltse fel a kéziratot (DOCX, PDF, illetve pandoc-kal ODT, RTF,
   Markdown, LaTeX, HTML, EPUB, RST), válassza ki a folyóirat-sablont, majd indítsa a
   feldolgozást.
2. A program kinyeri az ábrákat, képaláírásokat, táblázatokat és egyenleteket, majd
   a sablon szerint konvertálja őket (DPI, színmód, oszlopszélesség, formátum, betűtípus).
3. Letölthető: a teljes **ZIP csomag** (ábrák, egyenletképek, Excel, LaTeX, képaláírások,
   megfelelőségi jelentés), külön az **Excel** és a **LaTeX** táblázatok.
4. A **Sablonok** fülön új kiadói szabályrendszer hozható létre, a meglévő módosítható,
   importálható / exportálható (JSON).

Sablonok tárolási helye: `{store.user_dir.resolve()}`
""")


st.title("📐 Journal Figure Formatter")
st.caption("Tudományos kéziratok ábráinak, táblázatainak és egyenleteinek kiadói formázása")
tab1, tab2, tab3 = st.tabs(["📄 Feldolgozás", "🧩 Sablonok", "ℹ Súgó"])
with tab1:
    page_process()
with tab2:
    page_templates()
with tab3:
    page_help()
