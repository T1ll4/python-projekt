"""Ábrák kiadói formátumra konvertálása (Pillow + OpenCV).

Lépések: betöltés és módnormalizálás → vonalas ábra felismerése → automatikus
margóvágás (OpenCV) → célméret (oszlopszélesség, mm) és célfelbontás (DPI)
alapján átméretezés → opcionális ábracímke a sablon betűtípusával →
színmód-konverzió (RGB / CMYK / szürkeárnyalat / 1 bites) → mentés
TIFF / EPS / PNG / JPEG / PDF formátumba a DPI metaadattal.
"""

from __future__ import annotations

import io
import re
from dataclasses import replace
from functools import lru_cache
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .models import ProcessedImage
from .templates import FigureRules

try:  # OpenCV opcionális: ha nincs telepítve, Pillow-alapú tartalék fut
    import cv2  # type: ignore

    HAS_CV2 = True
except ImportError:  # pragma: no cover - környezetfüggő
    cv2 = None
    HAS_CV2 = False

Image.MAX_IMAGE_PIXELS = 400_000_000  # nagy felbontású (pl. 1200 dpi) ábrák engedélyezése

MM_PER_INCH = 25.4
EXTENSIONS = {"TIFF": "tif", "EPS": "eps", "PNG": "png", "JPEG": "jpg", "PDF": "pdf"}

# Az egyes kimeneti formátumok által támogatott színmódok (Pillow módnév)
_FORMAT_MODES = {
    "TIFF": {"RGB", "CMYK", "L", "1"},
    "EPS": {"RGB", "CMYK", "L", "1"},
    "PNG": {"RGB", "L", "1"},
    "JPEG": {"RGB", "CMYK", "L"},
    "PDF": {"RGB", "CMYK", "L", "1"},
}


class ImageProcessingError(Exception):
    """A kép nem olvasható vagy nem konvertálható."""


# ---------------------------------------------------------------------- #
# Betöltés, normalizálás
# ---------------------------------------------------------------------- #
def load_image(data: bytes) -> tuple[Image.Image, Optional[float]]:
    """Kép betöltése bájtokból; visszaadja a képet és a forrás DPI-t (ha ismert)."""
    try:
        img = Image.open(io.BytesIO(data))
        img.seek(0)
        img.load()
    except Exception as exc:  # Pillow sokféle kivételt dobhat
        raise ImageProcessingError(f"A kép nem olvasható: {exc}") from None
    dpi = None
    raw_dpi = img.info.get("dpi")
    if isinstance(raw_dpi, (tuple, list)) and raw_dpi:
        try:
            value = float(raw_dpi[0])
            if 10 <= value <= 10000:
                dpi = value
        except (TypeError, ValueError):
            dpi = None
    img = ImageOps.exif_transpose(img) or img
    return normalize_mode(img), dpi


def normalize_mode(img: Image.Image) -> Image.Image:
    """Bármilyen bemeneti módot RGB, L vagy CMYK módra hoz (átlátszóság fehér háttérre)."""
    mode = img.mode
    if mode in ("RGB", "L", "CMYK"):
        return img.copy()
    if mode == "1":
        return img.convert("L")
    if mode.startswith("I") or mode == "F":
        arr = np.asarray(img, dtype=np.float64)
        lo, hi = float(arr.min()), float(arr.max())
        scaled = np.zeros_like(arr) if hi <= lo else (arr - lo) / (hi - lo) * 255.0
        return Image.fromarray(scaled.round().astype(np.uint8))
    if mode == "P":
        img = img.convert("RGBA") if "transparency" in img.info else img.convert("RGB")
        mode = img.mode
        if mode == "RGB":
            return img
    if mode in ("RGBA", "LA", "PA", "RGBa", "La"):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return img.convert("RGB")


def _to_gray_array(img: Image.Image) -> np.ndarray:
    if img.mode == "CMYK":
        img = img.convert("RGB")
    return np.asarray(img.convert("L"), dtype=np.uint8)


# ---------------------------------------------------------------------- #
# Elemzés
# ---------------------------------------------------------------------- #
def is_line_art(img: Image.Image, threshold: float = 0.97) -> bool:
    """Vonalas (fekete-fehér rajz) ábra-e: a pixelek döntő része közel fekete vagy fehér,
    és a kép nem tartalmaz színes tartalmat."""
    small = img.copy()
    small.thumbnail((600, 600))
    if small.mode == "CMYK":
        small = small.convert("RGB")
    if small.mode == "RGB":
        arr = np.asarray(small, dtype=np.int16)
        chroma = arr.max(axis=2) - arr.min(axis=2)
        if float(np.mean(chroma > 30)) > 0.01:
            return False
    gray = _to_gray_array(small)
    extreme = np.logical_or(gray < 40, gray > 215)
    return float(np.mean(extreme)) >= threshold


def content_bbox(img: Image.Image, white_threshold: int = 245) -> Optional[tuple[int, int, int, int]]:
    """A nem fehér tartalom befoglaló téglalapja (left, top, right, bottom) vagy None."""
    gray = _to_gray_array(img)
    if HAS_CV2:
        _, mask = cv2.threshold(gray, white_threshold, 255, cv2.THRESH_BINARY_INV)
        points = cv2.findNonZero(mask)
        if points is None:
            return None
        x, y, w, h = cv2.boundingRect(points)
        return x, y, x + w, y + h
    mask_img = Image.fromarray(((gray <= white_threshold) * 255).astype(np.uint8))
    return mask_img.getbbox()


def auto_trim(img: Image.Image, padding: int = 10) -> Image.Image:
    bbox = content_bbox(img)
    if bbox is None:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(img.width, right + padding)
    bottom = min(img.height, bottom + padding)
    if (right - left) < 2 or (bottom - top) < 2:
        return img
    if (left, top, right, bottom) == (0, 0, img.width, img.height):
        return img
    return img.crop((left, top, right, bottom))


# ---------------------------------------------------------------------- #
# Méretezés
# ---------------------------------------------------------------------- #
def choose_width_mm(width_px: int, height_px: int, source_dpi: Optional[float],
                    rules: FigureRules, sizing: str, target_dpi: int) -> float:
    """A célszélesség (mm) meghatározása a méretezési mód alapján."""
    single = rules.single_column_mm
    one_half = rules.one_half_column_mm if rules.one_half_column_mm > 0 else None
    double = rules.double_column_mm
    aspect = width_px / height_px

    if sizing == "single":
        width = single
    elif sizing == "one_half":
        width = one_half or double
    elif sizing == "double":
        width = double
    elif sizing == "original":
        dpi = source_dpi or target_dpi
        width = min(width_px / dpi * MM_PER_INCH, double)
    else:  # auto
        natural = width_px / source_dpi * MM_PER_INCH if source_dpi else None
        if aspect >= 1.6:
            width = double
        elif natural is not None and natural > single * 1.1:
            candidates = [w for w in (one_half, double) if w and w >= natural]
            width = min(candidates) if candidates else double
        else:
            width = single
    # a maximális magasság betartása
    height = width / aspect
    if height > rules.max_height_mm:
        width = rules.max_height_mm * aspect
    return width


def _resize(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    if img.size == size:
        return img
    upscale = size[0] > img.width
    method = Image.Resampling.BICUBIC if upscale else Image.Resampling.LANCZOS
    return img.resize(size, method)


def _otsu_binarize(img: Image.Image) -> Image.Image:
    gray = _to_gray_array(img)
    if HAS_CV2:
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        binary = np.where(gray > 127, 255, 0).astype(np.uint8)
    return Image.fromarray(binary.astype(np.uint8)).convert("1", dither=Image.Dither.NONE)


# ---------------------------------------------------------------------- #
# Betűtípus és címke
# ---------------------------------------------------------------------- #
_FONT_FALLBACKS = {
    "arial": ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"],
    "helvetica": ["Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"],
    "times new roman": ["Times New Roman", "Liberation Serif", "Times", "DejaVu Serif"],
    "times": ["Times", "Times New Roman", "Liberation Serif", "DejaVu Serif"],
    "courier new": ["Courier New", "Liberation Mono", "DejaVu Sans Mono"],
    "symbol": ["Symbol", "DejaVu Sans"],
}


@lru_cache(maxsize=32)
def find_font_file(family: str) -> Optional[str]:
    """A megadott betűcsaládhoz (vagy metrikailag kompatibilis helyettesítőhöz) tartozó fájl."""
    try:
        from matplotlib import font_manager
    except ImportError:  # pragma: no cover
        return None
    candidates = _FONT_FALLBACKS.get(family.strip().lower(), [family, "DejaVu Sans"])
    for name in candidates:
        try:
            path = font_manager.findfont(
                font_manager.FontProperties(family=name), fallback_to_default=False
            )
            if path:
                return path
        except Exception:
            continue
    try:
        return font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans"))
    except Exception:  # pragma: no cover
        return None


def load_font(family: str, size_px: int) -> ImageFont.ImageFont:
    size_px = max(6, int(size_px))
    path = find_font_file(family)
    if path:
        try:
            return ImageFont.truetype(path, size_px)
        except OSError:
            pass
    return ImageFont.load_default(size=size_px)


def add_label(img: Image.Image, text: str, rules: FigureRules, dpi: int) -> Image.Image:
    """Ábracímke (pl. „Fig. 1” vagy „(a)”) elhelyezése a bal felső sarokban."""
    size_px = round(rules.font_size_pt / 72.0 * dpi)
    font = load_font(rules.font_family, size_px)
    work = img.convert("RGB") if img.mode == "CMYK" else img.copy()
    draw = ImageDraw.Draw(work)
    margin = max(2, size_px // 4)
    bbox = draw.textbbox((margin, margin), text, font=font)
    fill_bg = 255 if work.mode == "L" else (255, 255, 255)
    fill_fg = 0 if work.mode == "L" else (0, 0, 0)
    draw.rectangle((bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2), fill=fill_bg)
    draw.text((margin, margin), text, font=font, fill=fill_fg)
    return work.convert("CMYK") if img.mode == "CMYK" else work


# ---------------------------------------------------------------------- #
# Színmód
# ---------------------------------------------------------------------- #
def rgb_to_cmyk(img: Image.Image) -> Image.Image:
    """RGB → CMYK konverzió fekete-generálással (GCR).

    A Pillow beépített konverziója K=0 csatornát ad, ami nyomdai szempontból
    rossz (pl. a fekete szöveg négy színből áll össze). Itt a K csatorna a
    közös szürke komponensből képződik.
    """
    rgb = np.asarray(img.convert("RGB"), dtype=np.float64) / 255.0
    k = 1.0 - rgb.max(axis=2)
    denom = np.where(k < 1.0, 1.0 - k, 1.0)
    c = (1.0 - rgb[..., 0] - k) / denom
    m = (1.0 - rgb[..., 1] - k) / denom
    y = (1.0 - rgb[..., 2] - k) / denom
    cmyk = np.stack([c, m, y, k], axis=2)
    cmyk = np.clip(cmyk * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return Image.frombytes("CMYK", img.size, cmyk.tobytes())


def convert_color(img: Image.Image, color_mode: str) -> Image.Image:
    if color_mode == "RGB":
        return img.convert("RGB")
    if color_mode == "CMYK":
        return img if img.mode == "CMYK" else rgb_to_cmyk(img)
    if color_mode == "Grayscale":
        base = img.convert("RGB") if img.mode == "CMYK" else img
        return base.convert("L")
    if color_mode == "Bilevel":
        return _otsu_binarize(img)
    raise ImageProcessingError(f"Ismeretlen színmód: {color_mode}")


# ---------------------------------------------------------------------- #
# Mentés
# ---------------------------------------------------------------------- #
def _patch_eps_size(data: bytes, width_px: int, height_px: int,
                    width_pt: float, height_pt: float) -> bytes:
    """A Pillow EPS kimenete a pixelméretet pontként írja (72 dpi). A fizikai méret
    helyes megadásához a BoundingBox és a scale értékét pontra javítjuk."""
    text = data.decode("latin-1")
    text = text.replace(
        f"%%BoundingBox: 0 0 {width_px} {height_px}\n",
        f"%%BoundingBox: 0 0 {int(np.ceil(width_pt))} {int(np.ceil(height_pt))}\n"
        f"%%HiResBoundingBox: 0 0 {width_pt:.3f} {height_pt:.3f}\n",
        1,
    )
    text = text.replace(
        f"\n{width_px} {height_px} scale\n", f"\n{width_pt:.3f} {height_pt:.3f} scale\n", 1
    )
    return text.encode("latin-1")


def _bilevel_eps(img: Image.Image, width_pt: float, height_pt: float) -> bytes:
    """1 bites EPS (a Pillow EPS írója ezt a módot nem kezeli). 1 = fehér, 0 = fekete."""
    row_bytes = (img.width + 7) // 8
    raw = img.tobytes("raw", "1")
    header = (
        "%!PS-Adobe-3.0 EPSF-3.0\n"
        "%%Creator: journal-figure-formatter\n"
        f"%%BoundingBox: 0 0 {int(np.ceil(width_pt))} {int(np.ceil(height_pt))}\n"
        f"%%HiResBoundingBox: 0 0 {width_pt:.3f} {height_pt:.3f}\n"
        "%%LanguageLevel: 2\n%%Pages: 1\n%%EndComments\n%%Page: 1 1\n"
        "gsave\n"
        f"/buf {row_bytes} string def\n"
        f"{width_pt:.3f} {height_pt:.3f} scale\n"
        f"{img.width} {img.height} 1\n"
        f"[{img.width} 0 0 -{img.height} 0 {img.height}]\n"
        "{ currentfile buf readhexstring pop } bind\n"
        "image\n"
    )
    hex_data = raw.hex()
    line = 2 * row_bytes
    body = "\n".join(hex_data[i:i + line] for i in range(0, len(hex_data), line))
    return (header + body + "\ngrestore\nshowpage\n%%EOF\n").encode("ascii")


def save_image(img: Image.Image, file_format: str, dpi: int,
               tiff_compression: str = "tiff_lzw", jpeg_quality: int = 95) -> bytes:
    if file_format not in _FORMAT_MODES:
        raise ImageProcessingError(f"Nem támogatott formátum: {file_format}")
    if img.mode not in _FORMAT_MODES[file_format]:
        raise ImageProcessingError(
            f"A(z) {file_format} formátum nem támogatja a(z) {img.mode} színmódot."
        )
    buf = io.BytesIO()
    if file_format == "TIFF":
        compression = None if tiff_compression == "none" else tiff_compression
        if img.mode == "1" and compression is not None:
            compression = "group4"
        kwargs = {"dpi": (dpi, dpi)}
        if compression:
            kwargs["compression"] = compression
        img.save(buf, "TIFF", **kwargs)
    elif file_format == "EPS":
        width_pt = img.width / dpi * 72.0
        height_pt = img.height / dpi * 72.0
        if img.mode == "1":
            return _bilevel_eps(img, width_pt, height_pt)
        img.save(buf, "EPS")
        return _patch_eps_size(buf.getvalue(), img.width, img.height, width_pt, height_pt)
    elif file_format == "PNG":
        img.save(buf, "PNG", dpi=(dpi, dpi), optimize=True)
    elif file_format == "JPEG":
        img.save(buf, "JPEG", dpi=(dpi, dpi), quality=jpeg_quality, subsampling=0)
    elif file_format == "PDF":
        img.save(buf, "PDF", resolution=float(dpi))
    return buf.getvalue()


# ---------------------------------------------------------------------- #
# Fő belépési pont
# ---------------------------------------------------------------------- #
def safe_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_\-]+", "_", name).strip("_")
    return stem or "figure"


def process_image(data: bytes, rules: FigureRules, filename_stem: str, caption: str = "",
                  label_text: Optional[str] = None, sizing: Optional[str] = None,
                  dpi_override: Optional[int] = None) -> ProcessedImage:
    """Egy ábra teljes konverziója a sablon szabályai szerint."""
    img, source_dpi = load_image(data)
    original_w, original_h = img.size
    warnings: list[str] = []

    if img.width < 2 or img.height < 2:
        raise ImageProcessingError("A kép túl kicsi a feldolgozáshoz.")

    line_art = rules.detect_line_art and is_line_art(img)
    if dpi_override:
        dpi = int(dpi_override)
    elif line_art or rules.color_mode == "Bilevel":
        dpi = max(rules.line_art_dpi, rules.dpi)
    else:
        dpi = rules.dpi

    if rules.auto_trim:
        img = auto_trim(img, rules.trim_padding_px)

    sizing = sizing or rules.sizing
    width_mm = choose_width_mm(img.width, img.height, source_dpi, rules, sizing, dpi)
    aspect = img.width / img.height
    target_w = max(1, round(width_mm / MM_PER_INCH * dpi))
    target_h = max(1, round(target_w / aspect))
    effective_dpi = img.width / (width_mm / MM_PER_INCH)

    if target_w > img.width:
        if rules.allow_upscale:
            if effective_dpi < dpi * 0.98:
                warnings.append(
                    f"Az eredeti kép csak {effective_dpi:.0f} dpi felbontású a "
                    f"{width_mm:.1f} mm célszélességen; {dpi} dpi-re felskálázva "
                    "(a részletek nem javulnak, érdemes nagyobb felbontású forrást kérni)."
                )
        else:
            target_w, target_h = img.width, img.height
            width_mm = img.width / dpi * MM_PER_INCH
            warnings.append(
                f"Felskálázás tiltva: az ábra {width_mm:.1f} mm széles lesz "
                f"(a sablon szerinti oszlopszélességnél kisebb)."
            )

    img = _resize(img, (target_w, target_h))

    if rules.add_label and label_text:
        img = add_label(img, label_text, rules, dpi)

    color_mode = rules.color_mode
    if line_art and color_mode in ("RGB", "CMYK", "Grayscale") and rules.file_format != "JPEG":
        # vonalas ábrát 1 bites tiszta élekkel érdemes leadni
        warnings.append("Vonalas ábra felismerve: 1 bites (bilevel) kimenet, "
                        f"{dpi} dpi felbontással.")
        color_mode = "Bilevel"
    img = convert_color(img, color_mode)

    if img.width * 25.4 / dpi < rules.single_column_mm * 0.5:
        warnings.append("Az ábra szélessége kisebb, mint a hasábszélesség fele.")

    ext = EXTENSIONS[rules.file_format]
    preview = img.convert({"CMYK": "RGB", "1": "L"}.get(img.mode, img.mode))
    preview.thumbnail((800, 800))
    preview_buf = io.BytesIO()
    preview.save(preview_buf, "PNG")
    data_out = save_image(img, rules.file_format, dpi, rules.tiff_compression, rules.jpeg_quality)
    return ProcessedImage(
        filename=f"{safe_stem(filename_stem)}.{ext}",
        data=data_out,
        width_px=img.width,
        height_px=img.height,
        dpi=dpi,
        color_mode=color_mode,
        file_format=rules.file_format,
        width_mm=img.width / dpi * MM_PER_INCH,
        height_mm=img.height / dpi * MM_PER_INCH,
        original_width_px=original_w,
        original_height_px=original_h,
        effective_input_dpi=effective_dpi,
        caption=caption,
        warnings=warnings,
        preview_png=preview_buf.getvalue(),
    )


def rules_for_equations(rules: FigureRules, file_format: str, color_mode: str) -> FigureRules:
    """Egyenletképekhez használt szabályok: eredeti fizikai méret, vágás, nincs címke."""
    if color_mode == "CMYK" and file_format == "PNG":
        color_mode = "RGB"
    if color_mode == "Bilevel" and file_format == "JPEG":
        color_mode = "Grayscale"
    return replace(rules, file_format=file_format, color_mode=color_mode, sizing="original",
                   auto_trim=True, trim_padding_px=4, add_label=False, detect_line_art=False,
                   allow_upscale=True)
