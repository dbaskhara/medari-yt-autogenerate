"""Music-sheet slides for OBS: a song slide placed in Frame Slide 4_3.

Layout measured from the 15 Nov 2026 stream:
  * left white box  (24,129)-(1118,950)  -> the song slide (4:3)
  * right hole      (1167,335)-(1895,744) -> transparent, OBS shows the camera there
  * top-right label, Inter Bold 37, right edge x=1870 -> section name ("Pujian Pembuka")
Offering variant ("Pujian Pengiring Persembahan"): the camera hole moves up to
(1167,167)-(1896,578) and the QRIS card is drawn below it.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"
FONTS = ASSETS / "fonts"
W, H = 1920, 1080

SHEET_BOX = (24, 129, 1119, 951)
LABEL_RIGHT, LABEL_BASELINE, LABEL_SIZE = 1870, 108, 37
HOLE = (1167, 335, 1896, 745)
QR_HOLE = (1167, 167, 1897, 579)
CARD = (1214, 627, 1548, 922)          # grey gradient card with the caption
PANEL = (1548, 627, W, 922)            # white panel behind the QR
QR_BORDER = (1604, 644, 1865, 905)     # rounded black frame around the QR
ARROW_C, ARROW_R = (1556, 775), 21
CAPTION = ["QR Code/Kode QR", "Persembahan", "Minggu"]
CAPTION_RIGHT, CAPTION_BASELINES, CAPTION_SIZE = 1529, (668, 694, 719), 25
SS = 4                                  # supersampling for smooth rounded shapes


@lru_cache(maxsize=16)
def _font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


@lru_cache(maxsize=2)
def _frame(with_qr):
    frame = Image.open(ASSETS / "frame_4_3.png").convert("RGBA")
    if not with_qr:
        return frame
    a = np.asarray(frame).astype(np.float32)
    # 1. close the normal camera hole with the backdrop (blend rows above/below it)
    x0, y0, x1, y1 = HOLE
    top, bot = a[y0 - 2, x0:x1], a[y1 + 1, x0:x1]
    t = np.linspace(0, 1, y1 - y0)[:, None, None]
    a[y0:y1, x0:x1] = top[None] * (1 - t) + bot[None] * t
    a[y0 - 1:y1 + 1, x0:x1, 3] = 255
    # 2. open the higher camera hole
    x0, y0, x1, y1 = QR_HOLE
    a[y0:y1, x0:x1] = 0
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    _draw_qr_card(img)
    return img


def _rounded(size, box, radius, corners=None):
    """Anti-aliased rounded-rectangle mask, full frame size."""
    m = Image.new("L", (size[0] * SS, size[1] * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle([v * SS for v in box], radius=radius * SS, fill=255, corners=corners)
    return m.resize(size, Image.LANCZOS)


def _draw_qr_card(img):
    # grey card: light top-left -> darker bottom-right, rounded on the left
    x0, y0, x1, y1 = CARD
    yy, xx = np.mgrid[0:y1 - y0, 0:x1 - x0]
    shade = 241 - 45 * (xx / (x1 - x0)) * 0.6 - 45 * (yy / (y1 - y0)) * 0.9
    card = np.zeros((H, W, 4), np.uint8)
    card[y0:y1, x0:x1, :3] = np.clip(shade, 0, 255).astype(np.uint8)[..., None]
    card_img = Image.fromarray(card, "RGBA")
    card_img.putalpha(_rounded((W, H), (x0, y0, x1 + 40, y1), 42, corners=(True, False, False, True)))
    img.alpha_composite(card_img)
    # white panel for the QR
    d = ImageDraw.Draw(img)
    d.rectangle(PANEL, fill=(255, 255, 255, 255))
    # caption, right-aligned
    f = _font("Inter-Regular.ttf", CAPTION_SIZE)
    for line, base in zip(CAPTION, CAPTION_BASELINES):
        d.text((CAPTION_RIGHT, base), line, font=f, fill=(0, 0, 0, 255), anchor="rs")
    # small arrow button between card and panel
    cx, cy = ARROW_C
    circle = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(circle).ellipse((cx - ARROW_R, cy - ARROW_R, cx + ARROW_R, cy + ARROW_R), fill=(214, 214, 214, 255))
    circle.putalpha(_rounded((W, H), (cx - ARROW_R, cy - ARROW_R, cx + ARROW_R, cy + ARROW_R), ARROW_R))
    img.alpha_composite(circle)
    d.polygon([(cx - 6, cy - 11), (cx - 6, cy + 11), (cx + 9, cy)], fill=(0, 0, 0, 255))
    # rounded black frame + QR code
    bx0, by0, bx1, by1 = QR_BORDER
    border = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    border.putalpha(_rounded((W, H), QR_BORDER, 30))
    img.alpha_composite(border)
    inner = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    inner.putalpha(_rounded((W, H), (bx0 + 6, by0 + 6, bx1 - 6, by1 - 6), 25))
    img.alpha_composite(inner)
    qr_path = ASSETS / "qr_persembahan.png"
    if qr_path.exists():
        side = (bx1 - bx0) - 2 * 20
        qr = Image.open(qr_path).convert("RGBA").resize((side, side), Image.NEAREST)
        img.alpha_composite(qr, (bx0 + 20, by0 + 20))


def render(slide_path, label="", with_qr=False):
    img = _frame(with_qr).copy()
    x0, y0, x1, y1 = SHEET_BOX
    bw, bh = x1 - x0, y1 - y0
    slide = Image.open(slide_path).convert("RGBA")
    # fit inside the 4:3 box without stretching (song slides are already 4:3)
    scale = min(bw / slide.width, bh / slide.height)
    slide = slide.resize((max(1, round(slide.width * scale)), max(1, round(slide.height * scale))), Image.LANCZOS)
    img.alpha_composite(slide, (x0 + (bw - slide.width) // 2, y0 + (bh - slide.height) // 2))
    if label:
        f = _font("Inter-Bold.ttf", LABEL_SIZE)
        while f.getlength(label) > 780 and f.size > 20:
            f = _font("Inter-Bold.ttf", f.size - 1)
        ImageDraw.Draw(img).text((LABEL_RIGHT, LABEL_BASELINE), label, font=f, fill=(0, 0, 0, 255), anchor="rs")
    return img


def is_offering(label):
    return "persembahan" in (label or "").lower()
