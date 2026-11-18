"""YouTube thumbnail: Canva background + weekly text + preacher photo.

Layout measured from the 15 Nov 2026 thumbnail (made in Canva, 1280x720) and scaled to 1920x1080.
The background (assets/thumb_bg.png) is the Canva page with all text and the photo removed.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent / "assets"
FONTS = ASSETS / "fonts"
W, H = 1920, 1080

RIGHT = 1862                 # right edge of the text column
DATE = (214, 41)             # baseline, size  (Inter Regular)
THEME_LAST_BASELINE = 728    # theme grows upwards from here (Inter Bold)
THEME_SIZE, THEME_LEAD = 100, 1.05
THEME_MAX_W, THEME_MAX_LINES = 1060, 3
READINGS = (865, 50)         # baseline, size
BAR_BASELINE, BAR_SIZE = 994, 37
BAR_LEFT, BAR_RIGHT = 108, 1868
INK = (17, 17, 17)

PHOTO_TOP, PHOTO_CX, PHOTO_MIN_W, PHOTO_MAX_W = 300, 285, 560, 760
EDGE_X0, EDGE_SLOPE = 727.3, -0.2682   # diagonal edge of the grey panel, measured on thumb_bg.png


def _font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


@lru_cache(maxsize=1)
def _background():
    bg = Image.open(ASSETS / "thumb_bg.png").convert("RGB")
    if bg.size != (W, H):
        bg = bg.resize((W, H), Image.LANCZOS)
    return bg


@lru_cache(maxsize=1)
def _bar_rows():
    """Rows of the grey name bar; it is drawn again over the photo, like in Canva."""
    a = np.asarray(_background().convert("L"))[:, 1000].astype(int)
    rows = [y for y in range(860, H) if a[y] < 248]
    return (rows[0], rows[-1] + 1) if rows else (950, 1024)


def _fit(text, name, size, max_w, min_size=18):
    f = _font(name, size)
    while f.getlength(text) > max_w and size > min_size:
        size -= 1
        f = _font(name, size)
    return f


def _wrap(text, font, max_w):
    lines = []
    for para in text.replace("\r", "").split("\n"):
        words, cur = para.split(), ""
        for w in words:
            test = f"{cur} {w}".strip()
            if cur and font.getlength(test) > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = test
        if cur:
            lines.append(cur)
    return lines


def _theme_lines(theme):
    size = THEME_SIZE
    while True:
        f = _font("Inter-Bold.ttf", size)
        lines = _wrap(theme, f, THEME_MAX_W)
        if (len(lines) <= THEME_MAX_LINES and all(f.getlength(l) <= THEME_MAX_W for l in lines)) or size <= 50:
            return f, lines
        size -= 4


def _place_photo(img, photo, zoom=1.0, dx=0, dy=0):
    p = photo.convert("RGBA")
    box = p.getchannel("A").getbbox()
    if box:
        p = p.crop(box)
    # head at PHOTO_TOP; a full-body photo is made wide enough that it is cut off at the bottom,
    # like the half-body photos in the Canva thumbnails
    scale = max((H - PHOTO_TOP) / p.height, PHOTO_MIN_W / p.width)
    scale = min(scale, PHOTO_MAX_W / p.width) * zoom
    p = p.resize((max(1, round(p.width * scale)), max(1, round(p.height * scale))), Image.LANCZOS)
    x = round(PHOTO_CX - p.width / 2 + dx)
    y = round(max(PHOTO_TOP, H - p.height) + dy)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(p, (x, y), p)
    # the white side is in front: keep the photo inside the grey panel only
    alpha = ImageChops.multiply(layer.getchannel("A"), _panel_mask())
    img.paste(layer, (0, 0), alpha)


@lru_cache(maxsize=1)
def _panel_mask():
    """Grey left panel up to its diagonal edge (x = EDGE_X0 + EDGE_SLOPE * y), anti-aliased."""
    s = 4
    m = Image.new("L", (W * s, H * s), 0)
    ImageDraw.Draw(m).polygon([(0, 0), (EDGE_X0 * s, 0), ((EDGE_X0 + EDGE_SLOPE * H) * s, H * s), (0, H * s)],
                              fill=255)
    return m.resize((W, H), Image.LANCZOS)


def render(date_line, theme, readings, preacher, time_lang, photo=None, zoom=1.0, dx=0, dy=0):
    """1920x1080 RGB thumbnail."""
    img = _background().copy()
    if photo is not None:
        _place_photo(img, photo, zoom, dx, dy)
        y0, y1 = _bar_rows()
        img.paste(_background().crop((0, y0, W, y1)), (0, y0))
    d = ImageDraw.Draw(img)
    if date_line:
        d.text((RIGHT, DATE[0]), date_line, font=_fit(date_line, "Inter-Regular.ttf", DATE[1], 1100),
               fill=INK, anchor="rs")
    if theme.strip():
        f, lines = _theme_lines(theme)
        lead = round(f.size * THEME_LEAD)
        for i, line in enumerate(reversed(lines)):
            d.text((RIGHT, THEME_LAST_BASELINE - i * lead), line, font=f, fill=INK, anchor="rs")
    if readings:
        d.text((RIGHT, READINGS[0]), readings, font=_fit(readings, "Inter-Regular.ttf", READINGS[1], 1100),
               fill=INK, anchor="rs")
    right_f = _fit(time_lang, "Inter-Regular.ttf", BAR_SIZE, 760)
    right_w = right_f.getlength(time_lang) if time_lang else 0
    if preacher:
        d.text((BAR_LEFT, BAR_BASELINE), preacher,
               font=_fit(preacher, "Inter-Regular.ttf", BAR_SIZE, BAR_RIGHT - BAR_LEFT - right_w - 60),
               fill=INK, anchor="ls")
    if time_lang:
        d.text((BAR_RIGHT, BAR_BASELINE), time_lang, font=right_f, fill=INK, anchor="rs")
    return img


def default_texts(svc_dict):
    """Thumbnail texts from the parsed Tata Ibadah."""
    title = (svc_dict.get("title") or "Ibadah Minggu").strip()
    for prefix in ("Tata ", "Tatacara "):
        if title.lower().startswith(prefix.lower()):
            title = title[len(prefix):]
    title = title[:1].upper() + title[1:]
    javanese = any(w in (svc_dict.get("title") or "").lower() for w in ("pangibadah", "pangabekti", "jawi"))
    lang = "Basa Jawa" if javanese else "Bahasa Indonesia"
    readings = [f["main"] for f in svc_dict.get("footers", [])
                if f.get("top") == "Pembacaan Alkitab" and (f.get("bottom") or "").startswith("Bacaan")]
    preacher = svc_dict.get("preacher") or ""
    church = svc_dict.get("preacher_church") or ""
    time = (svc_dict.get("time") or "08:00 WIB").strip()
    return {
        "date_line": f"{title}, {svc_dict.get('date', '')}".strip(", "),
        "theme": svc_dict.get("theme") or "",
        "readings": ", ".join(readings),
        "preacher": f"{preacher} ({church})" if church else preacher,
        "time_lang": f"{time}   •   {lang}",
    }
