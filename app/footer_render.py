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


@lru_cache(maxsize=1)
def _pill_top():
    p = _layer("pill.png").copy()
    p.paste((0, 0, 0, 0), (0, 960, W, H))     # nothing below the bar (cut where the bar covers it)
    return p


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
        # without a bottom label only the top half of the pill shows (as on the stream)
        img.alpha_composite(_layer("pill.png") if bottom else _pill_top())
    img.alpha_composite(_layer("bar.png"))
    d = ImageDraw.Draw(img)
    if kind == "pill":
        _text(d, PILL_TOP_BASELINE, top, PILL_FONT, PILL_SMALL_SIZE, PILL_MAX_W_SMALL)
        # top-only pill: the main text is as big as on a bar (11 Okt 2026 stream)
        _text(d, PILL_MAIN_BASELINE, main, PILL_FONT, PILL_MAIN_SIZE if bottom else BAR_SIZE, PILL_MAX_W_MAIN)
        _text(d, PILL_BOTTOM_BASELINE, bottom, PILL_FONT, PILL_SMALL_SIZE, PILL_MAX_W_SMALL)
    else:
        _text(d, BAR_BASELINE, main, BAR_FONT, BAR_SIZE, BAR_MAX_W)
    return img


def preview(kind, main, top="", bottom="", width=960):
    """Bottom strip only, on a dark background, for the web page.
    A dialog / lyrics box gives one strip per image, stacked."""
    imgs = render_boxes(main) if kind == "box" else [render(kind, main, top, bottom)]
    if not imgs:
        imgs = [render_box([])]
    y0 = BOX[1] - 12 if kind == "box" else 830
    strips = [im.crop((0, y0, W, H)) for im in imgs]
    sh = strips[0].height
    bg = Image.new("RGBA", (W, sh * len(strips) + 8 * (len(strips) - 1)), (38, 41, 46, 255))
    for i, s in enumerate(strips):
        bg.alpha_composite(s, (0, i * (sh + 8)))
    h = round(bg.height * width / W)
    return bg.convert("RGB").resize((width, h), Image.LANCZOS)


# ---------- dialog / lyrics box (PF / U responses, songs without a number) ----------
# measured on the 15 Nov 2026 stream (Pengutusan & Berkat)
BOX = (75, 829, 1845, 1070)          # x0, y0, x1, y1
BOX_RADIUS = 40
BOX_TOP_GREY, BOX_BOTTOM_GREY = 242, 231
BOX_TEXT_X, BOX_SIZE, BOX_LEAD = 108, 38, 63
BOX_TEXT_CENTER = 950                # middle of the text block (cap top to last baseline)
BOX_MAX_LINES = 3
BOX_TEXT_W = BOX[2] - BOX_TEXT_X - 40
SPEAKER_RE = re.compile(r"^((?:PF|PP|U|MJ\s*\d*|Prd\s*\d*|Imam|Pnt\.?|L|P|J)\s*:\s*)")


@lru_cache(maxsize=1)
def _box_layer():
    x0, y0, x1, y1 = BOX
    s = 4
    mask = Image.new("L", ((x1 - x0) * s, (y1 - y0) * s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), BOX_RADIUS * s, fill=255)
    mask = mask.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    grad = Image.linear_gradient("L").resize((x1 - x0, y1 - y0))      # 0 at top -> 255 at bottom
    grey = grad.point(lambda v: round(BOX_TOP_GREY + (BOX_BOTTOM_GREY - BOX_TOP_GREY) * v / 255))
    box = Image.merge("RGBA", (grey, grey, grey, mask))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.alpha_composite(box, (x0, y0))
    return layer


def _wrap_line(line, font, max_w):
    words, rows, cur = line.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if cur and font.getlength(test) > max_w:
            rows.append(cur)
            cur = w
        else:
            cur = test
    return rows + ([cur] if cur else [])


def box_pages(text, max_lines=BOX_MAX_LINES):
    """Split the text into boxes of at most max_lines rows.
    A blank line always starts a new box; a long line is wrapped; lines are kept
    together in one box where possible. When one speaker's text runs over into the
    next box, that box starts with the speaker again ("PF : ...")."""
    font = _font(PILL_FONT, BOX_SIZE)
    pages = []
    for para in re.split(r"\n\s*\n", (text or "").replace("\r", "").strip()):
        lines = [l.strip() for l in para.split("\n") if l.strip()]
        if not lines:
            continue
        speaker = ""
        m = SPEAKER_RE.match(lines[0])
        cur, cur_speaker = [], ""
        for line in lines:
            m = SPEAKER_RE.match(line)
            if m:
                speaker = m.group(1)
            rows = _wrap_line(line, font, BOX_TEXT_W)
            if cur and len(cur) + len(rows) > max_lines:
                pages.append(cur)
                cur = []
            if not cur and not m and speaker and line[:1].isupper():   # same speaker, new sentence
                rows = _wrap_line(speaker + line, font, BOX_TEXT_W)
            while len(rows) > max_lines:              # one very long line
                pages.append(rows[:max_lines])
                rows = rows[max_lines:]
            cur += rows
        if cur:
            pages.append(cur)
    return pages


def render_box(rows):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.alpha_composite(_layer("bar.png"))
    img.alpha_composite(_box_layer())
    if rows:
        d = ImageDraw.Draw(img)
        font = _font(PILL_FONT, BOX_SIZE)
        cap = font.getbbox("H", anchor="ls")[1] * -1
        first = round(BOX_TEXT_CENTER - ((len(rows) - 1) * BOX_LEAD - cap) / 2)
        for i, row in enumerate(rows):
            d.text((BOX_TEXT_X, first + i * BOX_LEAD), row, font=font, fill=(17, 17, 17, 255), anchor="ls")
    return img


def render_boxes(text):
    return [render_box(rows) for rows in box_pages(text)]


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|]+', " ", s)
    return re.sub(r"\s+", " ", s).strip()[:80].strip() or "footer"
