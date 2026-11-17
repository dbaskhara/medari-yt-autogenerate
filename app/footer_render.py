"""Draw footer PNGs (1920x1080, transparent) for OBS.

Two layouts, measured from the live stream of 15 Nov 2026:
  bar  - full-width grey bar, one centred line   (e.g. "Votum & Salam")
  pill - bar + rounded pill behind it: small label on top, big text in the
         bar, small label below            (e.g. Pembacaan Alkitab / III Yohanes 1:1-12 / Bacaan 1)
"""
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"
FONTS = ASSETS / "fonts"
W, H = 1920, 1080
TEXT_COLOR = (0, 0, 0, 255)

# Baselines (y) and sizes measured on the video frames
BAR_BASELINE, BAR_SIZE, BAR_MAX_W = 962, 58, 1820
PILL_TOP_BASELINE, PILL_SMALL_SIZE = 886, 28
PILL_MAIN_BASELINE, PILL_MAIN_SIZE = 968, 56
PILL_BOTTOM_BASELINE = 1025
PILL_MAX_W_SMALL, PILL_MAX_W_MAIN = 980, 1800


def _font_file(*names):
    for n in names:
        for ext in (".otf", ".ttf"):
            p = FONTS / f"{n}{ext}"
            if p.exists():
                return p
    return FONTS / "Inter-Regular.ttf"


# Bar text is set in Object Sans in the CorelDRAW template; Inter is used until
# ObjectSans-Regular.otf/.ttf is put in app/assets/fonts.
BAR_FONT = _font_file("ObjectSans-Regular", "Object Sans Regular", "Inter-Regular")
PILL_FONT = _font_file("Inter-Regular")


@lru_cache(maxsize=64)
def _font(path, size):
    return ImageFont.truetype(str(path), size)


@lru_cache(maxsize=4)
def _layer(name):
    return Image.open(ASSETS / name).convert("RGBA")


def _fit(path, size, text, max_w):
    """Largest size <= size so that text fits in max_w."""
    while size > 14:
        f = _font(path, size)
        if f.getlength(text) <= max_w:
            return f
        size -= 1
    return _font(path, size)


def _text(draw, y, text, path, size, max_w):
    if text:
        draw.text((W / 2, y), text, font=_fit(path, size, text, max_w), fill=TEXT_COLOR, anchor="ms")


def render(kind, main, top="", bottom=""):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if kind == "pill":
        img.alpha_composite(_layer("pill.png"))
    img.alpha_composite(_layer("bar.png"))
    d = ImageDraw.Draw(img)
    if kind == "pill":
        _text(d, PILL_TOP_BASELINE, top, PILL_FONT, PILL_SMALL_SIZE, PILL_MAX_W_SMALL)
        _text(d, PILL_MAIN_BASELINE, main, PILL_FONT, PILL_MAIN_SIZE, PILL_MAX_W_MAIN)
        _text(d, PILL_BOTTOM_BASELINE, bottom, PILL_FONT, PILL_SMALL_SIZE, PILL_MAX_W_SMALL)
    else:
        _text(d, BAR_BASELINE, main, BAR_FONT, BAR_SIZE, BAR_MAX_W)
    return img


def preview(kind, main, top="", bottom="", width=960):
    """Bottom strip only, on a dark checker-free background, for the web page."""
    img = render(kind, main, top, bottom).crop((0, 830, W, H))
    bg = Image.new("RGBA", img.size, (38, 41, 46, 255))
    bg.alpha_composite(img)
    h = round(bg.height * width / W)
    return bg.convert("RGB").resize((width, h), Image.LANCZOS)


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|]+', " ", s)
    return re.sub(r"\s+", " ", s).strip()[:80] or "footer"
