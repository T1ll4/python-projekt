import io
import shutil
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

from manuscript_formatter.imaging import (
    ImageProcessingError, auto_trim, is_line_art, normalize_mode, process_image, rgb_to_cmyk,
)
from manuscript_formatter.templates import FigureRules


def _png(img, dpi=None):
    buf = io.BytesIO()
    img.save(buf, "PNG", **({"dpi": (dpi, dpi)} if dpi else {}))
    return buf.getvalue()


def _photo(w=400, h=300):
    rng = np.random.default_rng(0)
    return Image.fromarray(rng.integers(0, 255, (h, w, 3), dtype=np.uint8))


def test_tiff_dpi_size_and_mode():
    rules = FigureRules(dpi=300, single_column_mm=85, sizing="single", file_format="TIFF",
                        color_mode="RGB", auto_trim=False)
    out = process_image(_png(_photo()), rules, "Fig1")
    img = Image.open(io.BytesIO(out.data))
    assert out.filename == "Fig1.tif"
    assert img.format == "TIFF" and img.mode == "RGB"
    assert round(img.info["dpi"][0]) == 300
    assert img.width == round(85 / 25.4 * 300)
    assert abs(out.width_mm - 85) < 0.2
    assert any("felskálázva" in w for w in out.warnings)  # 400 px < 1004 px


def test_cmyk_output_has_black_channel():
    rules = FigureRules(color_mode="CMYK", file_format="TIFF", auto_trim=False, sizing="single")
    img = Image.new("RGB", (200, 100), (0, 0, 0))
    img.paste((255, 0, 0), (100, 0, 200, 100))
    out = process_image(_png(img), rules, "c")
    result = Image.open(io.BytesIO(out.data))
    assert result.mode == "CMYK"
    c, m, y, k = result.getpixel((5, 5))
    assert k > 250 and c < 5  # tiszta fekete K csatornán
    c, m, y, k = result.getpixel((result.width - 5, 5))
    assert m > 250 and y > 250 and k < 5


def test_rgb_to_cmyk_white():
    out = rgb_to_cmyk(Image.new("RGB", (2, 2), "white"))
    assert out.getpixel((0, 0)) == (0, 0, 0, 0)


@pytest.mark.parametrize("fmt,mode", [("TIFF", "Grayscale"), ("PNG", "RGB"), ("JPEG", "CMYK"),
                                      ("PDF", "RGB"), ("EPS", "CMYK"), ("TIFF", "Bilevel"),
                                      ("EPS", "Bilevel")])
def test_all_formats(fmt, mode):
    rules = FigureRules(file_format=fmt, color_mode=mode, detect_line_art=False, dpi=150,
                        line_art_dpi=150, single_column_mm=40, sizing="single")
    out = process_image(_png(_photo()), rules, "x")
    assert out.data
    assert out.filename.endswith({"TIFF": ".tif", "PNG": ".png", "JPEG": ".jpg", "PDF": ".pdf",
                                  "EPS": ".eps"}[fmt])
    if fmt == "EPS":
        head = out.data[:400].decode("latin-1")
        assert "%%BoundingBox: 0 0 114 " in head  # 40 mm = 113.4 pt
    elif fmt != "PDF":
        assert Image.open(io.BytesIO(out.data)).mode == {"Grayscale": "L", "RGB": "RGB",
                                                         "CMYK": "CMYK", "Bilevel": "1"}[mode]


@pytest.mark.skipif(shutil.which("gs") is None, reason="ghostscript nincs telepítve")
def test_eps_readable_by_ghostscript():
    for mode in ("RGB", "Bilevel"):
        rules = FigureRules(file_format="EPS", color_mode=mode, dpi=100, line_art_dpi=100,
                            single_column_mm=30, sizing="single", detect_line_art=False)
        out = process_image(_png(_photo(120, 80)), rules, "x")
        img = Image.open(io.BytesIO(out.data))
        img.load()
        assert img.size[0] > 0


def test_auto_trim_removes_white_margin():
    img = Image.new("RGB", (300, 200), "white")
    img.paste((0, 0, 0), (100, 50, 200, 150))
    trimmed = auto_trim(img, padding=5)
    assert trimmed.size == (110, 110)


def test_line_art_detection_and_bilevel():
    img = Image.new("L", (400, 300), 255)
    img.paste(0, (50, 50, 350, 60))
    assert is_line_art(img)
    assert not is_line_art(_photo())
    rules = FigureRules(file_format="TIFF", color_mode="RGB", dpi=300, line_art_dpi=1000,
                        sizing="single", single_column_mm=50)
    out = process_image(_png(img), rules, "l")
    assert out.dpi == 1000 and out.color_mode == "Bilevel"
    assert Image.open(io.BytesIO(out.data)).mode == "1"


def test_transparent_png_flattened_on_white():
    img = Image.new("RGBA", (50, 50), (255, 0, 0, 0))
    flat = normalize_mode(img)
    assert flat.mode == "RGB" and flat.getpixel((0, 0)) == (255, 255, 255)


def test_16bit_and_palette_inputs():
    arr = (np.arange(100 * 100, dtype=np.uint16).reshape(100, 100) * 6)
    assert normalize_mode(Image.fromarray(arr)).mode == "L"
    assert normalize_mode(_photo().convert("P")).mode == "RGB"


def test_max_height_respected():
    tall = Image.new("RGB", (100, 1000), (10, 120, 200))
    rules = FigureRules(sizing="double", double_column_mm=170, max_height_mm=200, auto_trim=False,
                        detect_line_art=False)
    out = process_image(_png(tall), rules, "t")
    assert out.height_mm <= 200.5


def test_auto_sizing_wide_goes_double():
    wide = _photo(1000, 300)
    rules = FigureRules(sizing="auto", auto_trim=False, detect_line_art=False)
    assert abs(process_image(_png(wide), rules, "w").width_mm - rules.double_column_mm) < 0.3
    square = _photo(300, 300)
    assert abs(process_image(_png(square), rules, "s").width_mm - rules.single_column_mm) < 0.3


def test_no_upscale_keeps_pixels():
    rules = FigureRules(allow_upscale=False, sizing="double", auto_trim=False,
                        detect_line_art=False)
    out = process_image(_png(_photo(200, 100)), rules, "n")
    assert out.width_px == 200 and out.dpi == rules.dpi


def test_label_added():
    rules = replace(FigureRules(), add_label=True, auto_trim=False, detect_line_art=False,
                    color_mode="Grayscale", sizing="single")
    blank = Image.new("RGB", (400, 300), "white")
    out = process_image(_png(blank), rules, "lab", label_text="Fig. 1")
    img = Image.open(io.BytesIO(out.data))
    assert np.asarray(img.crop((0, 0, 200, 60))).min() < 50  # van sötét szöveg a sarokban


def test_invalid_image_raises():
    with pytest.raises(ImageProcessingError):
        process_image(b"not an image", FigureRules(), "bad")
