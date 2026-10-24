# 📐 Journal Figure Formatter

**Tudományos kéziratok ábráinak, grafikonjainak, egyenleteinek és táblázatainak automatikus
kinyerése, átméretezése és formázása a folyóiratok vizuális és felbontásbeli
(DPI, színmód, betűtípus, oszlopszélesség) követelményei szerint.**

A program egy feltöltött kéziratból (DOCX, PDF, vagy pandoc segítségével ODT, RTF,
Markdown, LaTeX, HTML, EPUB, RST) automatikusan leválasztja az ábrákat a képaláírásokkal, a
táblázatokat és az egyenleteket. Ezután a kiválasztott folyóirat-sablon szerint konvertálja
őket, és a kiadónak leadható, tömörített ZIP csomagot készít. A csomagban vannak a
konvertált ábrák, a formázott Excel munkafüzet, a külön LaTeX táblázatok, a képaláírások listája
és egy megfelelőségi jelentés.

---

## Gyors kezdés – felhasználói útmutató

A programot egy böngészőben futó felületen lehet használni: fájlt kell feltölteni és
gombokra kattintani, programozni nem kell hozzá.

### 1. Egyszeri telepítés

**Python 3.10 vagy újabb kell.** Ellenőrzés a Terminálban: `python3 --version`. Ha a verzió
régebbi, vagy nincs Python, telepítse a <https://www.python.org/downloads/> oldalról
(macOS-en Homebrew-val is lehet: `brew install python`).

A program telepítése a projekt mappájában:

```bash
cd journal-figure-formatter
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

*(Opcionális)* ODT, RTF, Markdown vagy LaTeX kéziratokhoz telepíteni kell a pandocot is
(`brew install pandoc`, Linuxon `sudo apt install pandoc`). DOCX és PDF fájlokhoz erre
nincs szükség.

### 2. Indítás (minden alkalommal)

```bash
cd journal-figure-formatter
source .venv/bin/activate          # Windows: .venv\Scripts\activate
streamlit run app.py
```

A böngészőben magától megnyílik a `http://localhost:8501` cím. Leállítás: a Terminálban
**Ctrl+C**.

### 3. Kézirat feldolgozása – 📄 Feldolgozás fül

1. **Kézirat feltöltése:** húzza be a `.docx` vagy `.pdf` fájlt.
2. **Folyóirat-sablon:** válassza ki a célfolyóiratot (Elsevier, Springer Nature, IEEE,
   PLOS ONE, ACS). Alatta látszanak a sablon előírásai, például
   `TIFF · CMYK · 300/1200 dpi · 82.5/177.8 mm · Arial`.
3. **Méretezés:** maradhat „(sablon szerint)”, vagy kényszeríthető egy- vagy kéthasábos méret.
4. Kattintson a **▶ Feldolgozás** gombra.
5. Az eredmény:
   - számlálók: hány ábrát, táblázatot és egyenletet talált a program;
   - **⚠ Figyelmeztetések:** például ha egy kép felbontása gyenge, vagy egy ábrához
     nincs képaláírás;
   - **Ábrák / Táblázatok / Egyenletek** alfülek előnézettel;
   - letöltőgombok:
     - **Teljes ZIP csomag:** ezt lehet a kiadónak beküldeni;
     - **Excel táblázatok;**
     - **LaTeX fájlok.**

### 4. Saját folyóirat-sablon – 🧩 Sablonok fül

Ha a célfolyóirat nincs a listában, vagy más az előírása:

1. Válassza a **➕ Új sablon** lehetőséget, vagy egy meglévő sablont kiindulásnak.
2. Adja meg az azonosítót és a nevet, majd állítsa be a DPI-t, a színmódot, a
   fájlformátumot, a hasábszélességet (mm), a betűtípust és a táblázatstílust.
3. Kattintson a **💾 Mentés** gombra. Az új sablon ezután megjelenik a Feldolgozás fülön.
4. A sablon JSON-ként exportálható és importálható, így egy kollégának is odaadható.

### 5. Kipróbálás mintakézirattal

Ha nincs kéznél kézirat, generálható egy minta:

```bash
pip install reportlab
python examples/make_sample.py examples/output
```

Ezután töltse fel az `examples/output/sample_manuscript.docx` vagy a
`sample_manuscript.pdf` fájlt a felületen.

---

## Tartalom

- [🚀 Gyors kezdés – felhasználói útmutató](#-gyors-kezdés--felhasználói-útmutató)
- [Fő funkciók](#fő-funkciók)
- [Architektúra](#architektúra)
- [Telepítés](#telepítés)
- [Használat – webes felület](#használat--webes-felület)
- [Használat – parancssor](#használat--parancssor)
- [Használat – Python API](#használat--python-api)
- [A kimeneti ZIP csomag szerkezete](#a-kimeneti-zip-csomag-szerkezete)
- [Folyóirat-sablonok](#folyóirat-sablonok)
- [Működés részletesen](#működés-részletesen)
- [Tesztek](#tesztek)
- [Korlátok](#korlátok)
- [Projektstruktúra](#projektstruktúra)

---

## Fő funkciók

| Követelmény | Megvalósítás |
|---|---|
| **Bemenet és elemzés** | `python-docx` (DOCX), `pypdf` (PDF), `pandoc` (ODT, RTF, MD, TeX, HTML, EPUB, RST → DOCX) |
| Ábrák detektálása | beágyazott képek (DrawingML és régi VML), képrács-táblázatokban lévő képek, PDF raszterképek |
| Képaláírások | „Caption” stílus és mintafelismerés: `Figure 1.`, `Fig. 2:`, `1. ábra`, `Table 1`, `2. táblázat`, `TABLE II` stb.; az aláírás lehet az ábra alatt vagy felett; több panelből álló ábrák (1a, 1b) |
| Táblázatok | Word táblázatok → `pandas.DataFrame` (egyesített cellák kezelése), PDF-ben oszloptávolság-alapú felismerés |
| Egyenletek | Word-egyenletek (OMML) → **LaTeX** saját konverterrel; szöveges `$$…$$`, `\[…\]`, `\begin{equation}`; PDF-ben számozott egyenletsorok |
| **Vizuális konverzió** | `Pillow` + `OpenCV`: TIFF (LZW/Deflate/Group4), EPS (helyes fizikai mérettel), PNG, JPEG, PDF |
| Felbontás | minimum DPI fotóra és külön (magasabb) DPI vonalas ábrára, effektív bemeneti DPI számítása, figyelmeztetés felskálázáskor |
| Színterek | RGB, CMYK (fekete-generálással, GCR), szürkeárnyalat, 1 bites (bilevel, Otsu-küszöböléssel) |
| Méretezés | egy-, másfél- és kéthasábos szélesség (mm), max. magasság, automatikus választás képarány és eredeti méret alapján |
| Betűtípus | a sablon betűtípusa érvényes az ábracímkékre, az egyenletképekre (mathtext), az Excel és a LaTeX táblázatokra |
| **Dinamikus sablonkezelés** | új kiadói szabályok létrehozása, szerkesztése, mentése, törlése, JSON import/export a webes felületen, validációval |
| **Kimenet** | tömörített ZIP; formázott Excel (`openpyxl`); külön LaTeX táblázatok (`pandas` + `jinja2` sablonok); megfelelőségi jelentés (JSON + Excel összesítő lap) |

## Architektúra

```
          ┌──────────────┐   ┌──────────────────────┐   ┌─────────────────────────┐
 kézirat ─▶   extract/   ├──▶│  ExtractionResult    ├──▶│ pipeline.process_...    │
 (docx,   │ docx / pdf / │   │ figures, tables,     │   │  ├ imaging.py (ábrák)   │
  pdf,    │ pandoc       │   │ equations, captions  │   │  ├ equations.py         │
  odt…)   └──────────────┘   └──────────────────────┘   │  └ sablon (templates.py)│
                                                         └───────────┬─────────────┘
                                                                     ▼
                                 ┌──────────────────────────────────────────────────┐
                                 │ export/: ZIP · Excel (openpyxl) · LaTeX (jinja2) │
                                 └──────────────────────────────────────────────────┘
       Felületek:  app.py (Streamlit)  ·  manuscript_formatter/cli.py (parancssor)
```

## Telepítés

Követelmény: **Python 3.10+**. Opcionálisan:
- **pandoc**: ODT/RTF/Markdown/LaTeX/HTML bemenethez,
- **ghostscript**: csak akkor kell, ha EPS fájlt kell *beolvasni* (a kimenethez nem kell).

```bash
git clone <repo-url> journal-figure-formatter
cd journal-figure-formatter
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt     # fejlesztéshez/tesztekhez: requirements-dev.txt
```

Pandoc telepítése: `sudo apt install pandoc` (Linux), `brew install pandoc` (macOS) vagy
<https://pandoc.org/installing.html>.

## Használat – webes felület

```bash
streamlit run app.py
```

Ezután a böngészőben megnyílik a `http://localhost:8501` cím.

1. **📄 Feldolgozás**: töltse fel a kéziratot, válassza ki a folyóirat-sablont és ha kell,
   a méretezési módot, majd kattintson a **▶ Feldolgozás** gombra.
   - Megjelenik az ábrák előnézete a végső méretekkel (mm, px, DPI, színmód), a táblázatok és
     a LaTeX kódjuk, valamint az egyenletek (LaTeX és renderelt kép).
   - Letölthető a **teljes ZIP csomag**, külön az **Excel** és a **LaTeX** fájlok.
   - A figyelmeztetések jelzik például az alacsony eredeti felbontást vagy a hiányzó
     képaláírást.
2. **🧩 Sablonok**: új sablon létrehozása, vagy meglévő szerkesztése az összes paraméterrel.
   Mentéskor a rendszer ellenőrzi a sablont (érvényes értéktartományok, a formátum és a
   színmód összeillése, fájlnévminta). Itt lehet JSON-t importálni és exportálni, és itt
   törölhetők a saját sablonok.
3. **ℹ Súgó**: rövid használati útmutató.

A saját sablonok alapértelmezés szerint a `./user_templates/` mappába kerülnek. Ez a
`MF_TEMPLATE_DIR` környezeti változóval módosítható.

## Használat – parancssor

```bash
# kézirat feldolgozása Elsevier sablonnal → ZIP
python -m manuscript_formatter process kezirat.docx -t elsevier -o leadas.zip

# PDF, IEEE sablon, Excel és LaTeX külön is, kéthasábos méretezés kényszerítése
python -m manuscript_formatter process kezirat.pdf -t ieee \
       --excel tablazatok.xlsx --latex latex/ --sizing double

# sablonok kezelése
python -m manuscript_formatter templates list
python -m manuscript_formatter templates show springer_nature
python -m manuscript_formatter templates export elsevier -o sajat.json
python -m manuscript_formatter templates import sajat.json
python -m manuscript_formatter templates delete sajat_folyoirat
```

`pip install .` után a `manuscript-formatter` parancs is elérhető.

Mintakézirat generálása a kipróbáláshoz:

```bash
python examples/make_sample.py examples/output
python -m manuscript_formatter process examples/output/sample_manuscript.docx -t acs
```

## Használat – Python API

```python
from manuscript_formatter.templates import TemplateStore
from manuscript_formatter.pipeline import process_manuscript

store = TemplateStore()
result = process_manuscript("kezirat.docx", store.get("springer_nature"))

open("leadas.zip", "wb").write(result.zip_bytes())
open("tablazatok.xlsx", "wb").write(result.excel_bytes())
for name, tex in result.latex_files().items():
    open(name, "w", encoding="utf-8").write(tex)
print(result.report()["summary"], result.warnings)
```

## A kimeneti ZIP csomag szerkezete

```
kezirat_elsevier.zip
├── figures/                 # konvertált ábrák (pl. Fig1.tif, Fig2a.tif, Fig2b.tif)
├── figures_unconverted/     # csak ha egy kép nem konvertálható (pl. WMF/EMF) – eredeti fájl
├── equations/               # egyenletek képként (Eq1.tif …) a sablon DPI-jével és betűtípusával
├── tables/
│   ├── kezirat_tables.xlsx  # formázott Excel: táblázatonként egy munkalap + Summary lap
│   └── latex/
│       ├── Table1.tex       # különálló LaTeX táblázatok (\input-tal beemelhetők)
│       ├── Table2.tex
│       ├── equations.tex    # egyenletek equation környezetben
│       └── main.tex         # önállóan lefordítható dokumentum az összes táblázattal
├── captions.txt             # ábra- és táblázatfeliratok listája
├── report.json              # megfelelőségi jelentés (méret, DPI, színmód, figyelmeztetések)
└── template.json            # a használt sablon (reprodukálhatóság)
```

## Folyóirat-sablonok

### Beépített sablonok

| Azonosító | Folyóirat | Formátum | Színmód | DPI (fotó / vonalas) | Szélesség (mm) | Betűtípus |
|---|---|---|---|---|---|---|
| `elsevier` | Elsevier | TIFF | RGB | 300 / 1000 | 90 / 140 / 190 | Arial |
| `springer_nature` | Springer Nature | EPS | RGB | 300 / 1200 | 84 / 129 / 174 | Arial |
| `ieee` | IEEE Transactions | TIFF | RGB | 300 / 600 | 88.9 / 181.9 | Times New Roman |
| `plos_one` | PLOS ONE | TIFF (LZW) | RGB | 300 / 600 | 132 / 190.5 | Arial |
| `acs` | ACS Publications | TIFF | CMYK | 300 / 1200 | 82.5 / 177.8 | Arial |

> A beépített értékek a kiadók nyilvános szerzői útmutatóin alapulnak. Leadás előtt
> érdemes ellenőrizni az adott folyóirat aktuális előírásait, és szükség esetén a felületen
> módosítani a sablont.

### Sablon JSON formátum

```json
{
  "id": "sajat_folyoirat",
  "name": "Saját Folyóirat",
  "publisher": "Kiadó Kft.",
  "description": "Rövid leírás",
  "figure": {
    "dpi": 300, "line_art_dpi": 1000,
    "color_mode": "CMYK", "file_format": "TIFF", "tiff_compression": "tiff_lzw",
    "jpeg_quality": 95,
    "single_column_mm": 85, "one_half_column_mm": 0, "double_column_mm": 175,
    "max_height_mm": 230, "sizing": "auto",
    "allow_upscale": true, "auto_trim": true, "trim_padding_px": 10,
    "detect_line_art": true,
    "font_family": "Arial", "font_size_pt": 8, "min_font_size_pt": 6,
    "add_label": false, "filename_pattern": "Fig{number}"
  },
  "table": {
    "font_family": "Times New Roman", "font_size_pt": 9,
    "header_bold": true, "header_fill": "D9D9D9",
    "border_style": "booktabs", "zebra_striping": false,
    "caption_position": "top", "latex_environment": "table",
    "latex_font_size": "\\small", "decimal_places": -1,
    "filename_pattern": "Table{number}"
  },
  "equation": {
    "render_images": true, "dpi": 600, "file_format": "PNG",
    "font_size_pt": 10, "font_family": "Times New Roman",
    "filename_pattern": "Eq{number}"
  }
}
```

| Mező | Lehetséges értékek / jelentés |
|---|---|
| `figure.color_mode` | `RGB`, `CMYK`, `Grayscale`, `Bilevel` (1 bites) |
| `figure.file_format` | `TIFF`, `EPS`, `PNG`, `JPEG`, `PDF` (PNG + CMYK és JPEG + Bilevel nem engedélyezett) |
| `figure.tiff_compression` | `none`, `tiff_lzw`, `tiff_deflate` (1 bites képnél automatikusan Group4) |
| `figure.sizing` | `auto`, `single`, `one_half`, `double`, `original` |
| `figure.one_half_column_mm` | `0` = a folyóiratnak nincs másfél hasábos mérete |
| `figure.detect_line_art` | vonalas ábránál `line_art_dpi` és 1 bites kimenet |
| `figure.add_label` | „Fig. N” vagy panelbetű „(a)” ráírása a sablon betűtípusával |
| `table.border_style` | `booktabs` (vízszintes vonalak), `grid` (rács), `none` |
| `table.caption_position` | `top`, `bottom` |
| `table.latex_environment` | `table`, `table*` (kéthasábos) |
| `table.decimal_places` | `-1` = eredeti pontosság, `0–10` = kerekítés |
| `*.filename_pattern` | kötelező `{number}` helyőrző, tiltott fájlnév-karakterek nélkül |

Azonos azonosítójú felhasználói sablon felülírja a beépítettet. A felhasználói példány
törlésével a beépített sablon visszaáll.

## Működés részletesen

**Ábrák és képaláírások párosítása (DOCX).** A dokumentum törzsét sorrendben járja be
(bekezdések, táblázatok, tartalomvezérlők). A képaláírás az ábra alatt és felett is lehet.
Ha egy aláírás előtt több kép áll, azok egy több panelből álló ábrát alkotnak (`Fig2a`,
`Fig2b`). A folyószöveg hivatkozásai („Figure 2 shows…”) nem számítanak aláírásnak, mert
„Caption” stílus nélkül a szám után elválasztójel vagy nagybetűs folytatás szükséges.

**Képfeldolgozási lánc** (`imaging.py`):
1. Betöltés, EXIF-forgatás, a módok normalizálása (átlátszóság fehér háttérre, 16 bites és
   palettás képek kezelése).
2. Vonalas ábra felismerése: közel fekete-fehér pixelarány, színtartalom nélkül.
3. A fehér margók levágása OpenCV-vel (`threshold` + `boundingRect`).
4. Célszélesség (mm) a méretezési mód szerint, a max. magasság betartásával. Ebből és a
   cél-DPI-ből jön a pixelméret. Az effektív bemeneti DPI-t is kiszámolja, és ha ez
   alacsony, figyelmeztet.
5. Átméretezés (Lanczos kicsinyítéshez, bikubikus nagyításhoz), opcionálisan ábracímke.
6. Színkonverzió: a CMYK fekete-generálással (GCR) készül, így a fekete szöveg tiszta
   K csatornán van. Az 1 bites kimenet Otsu-küszöböléssel készül.
7. Mentés DPI metaadattal. Az EPS fájl BoundingBox-a a valós fizikai méretet adja pontban
   (a Pillow alapértelmezésben 72 dpi-t feltételezne). 1 bites EPS-hez saját, kompakt
   író készült.

**Egyenletek.** A Word OMML egyenleteit saját konverter fordítja LaTeX-re (törtek, gyökök,
indexek, szummák/integrálok, zárójelek, függvények, ékezetek, mátrixok, görög betűk és
szimbólumok). A képeket a matplotlib mathtext rendereli a sablon betűtípusához illő
fontkészlettel (Times → STIX, Arial → STIX Sans), a sablon DPI-jével.

**Táblázatok.** A számokat felismeri (tizedesvessző, ezres tagolás, unicode mínuszjel), és
Excelben valódi számként, jobbra igazítva tárolja őket. A LaTeX-ben a numerikus oszlopok
`r` igazítást kapnak, a speciális karakterek (`& % $ # _ { } ~ ^ \`) escape-elve vannak.

## Tesztek

```bash
pip install -r requirements-dev.txt
pytest -q
```

A 71 teszt lefedi a sablonvalidációt és -tárolást, minden képformátumot és színmódot (a
DPI-t és a fizikai méretet is ellenőrzi), a DOCX/PDF/Markdown kinyerést, az OMML → LaTeX
konverziót, az Excel- és LaTeX-formázást, a teljes ZIP csomagot, a CLI-t és a Streamlit
felületet (`AppTest`). A tesztek Python 3.10 és 3.13 alatt is hibátlanul lefutnak.

## Korlátok

- **PDF**: a vektoros ábrák (nem raszterképek) nem nyerhetők ki. Ilyenkor a program
  figyelmeztet, és a forrásfájlt érdemes külön bekérni. A PDF-táblázatok felismerése
  heurisztikus (oszlopközök alapján).
- **WMF/EMF** képek Linuxon nem konvertálhatók. Ezek eredeti formában a
  `figures_unconverted/` mappába kerülnek.
- A felskálázás nem pótolja a hiányzó részleteket. A program jelzi, ha az eredeti
  felbontás alacsonyabb a megköveteltnél.
- A CMYK konverzió ICC-profil nélküli (GCR) közelítés. Nyomdai színhű munkához
  profilalapú konverzió ajánlott.
- A raszterképekbe égetett feliratok betűtípusa utólag nem módosítható. A sablon
  betűtípusa a címkékre, az egyenletekre és a táblázatokra vonatkozik.

## Projektstruktúra

```
journal-figure-formatter/
├── app.py                          # Streamlit webes felület
├── manuscript_formatter/
│   ├── __main__.py, cli.py         # parancssori felület
│   ├── models.py                   # adatmodellek (Figure, Table, Equation, ...)
│   ├── templates.py                # sablonok: dataclass-ok, validáció, JSON tároló
│   ├── builtin_templates/*.json    # beépített folyóirat-sablonok
│   ├── imaging.py                  # Pillow + OpenCV képkonverzió
│   ├── equations.py                # egyenlet-renderelés (matplotlib mathtext)
│   ├── pipeline.py                 # teljes folyamat + ZIP csomag
│   ├── extract/
│   │   ├── docx_extractor.py       # python-docx
│   │   ├── pdf_extractor.py        # pypdf
│   │   ├── pandoc_extractor.py     # pandoc
│   │   ├── omml.py                 # Word-egyenlet → LaTeX
│   │   └── captions.py             # képaláírás-felismerés
│   └── export/
│       ├── excel_export.py         # openpyxl
│       ├── latex_export.py         # jinja2
│       ├── tables.py               # számfelismerés, formázás
│       └── latex_templates/*.j2    # LaTeX Jinja2 sablonok
├── examples/make_sample.py         # mintakézirat (DOCX + PDF) generátor
├── tests/                          # pytest tesztek
└── requirements.txt, requirements-dev.txt, pyproject.toml
```

## Licenc

MIT – lásd a [LICENSE](LICENSE) fájlt.
