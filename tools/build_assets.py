"""One-off: rebuild the footer artwork (bar + pill) as clean transparent PNGs
from full-HD frames of the 15 Nov 2026 livestream.

The CorelDRAW template could not be opened on this PC, so the artwork is
reconstructed from frames where the footer is on screen:
  f_330.png  -> section bar ("Pengantar & Panggilan Beribadah")
  f_2450.png -> pill + bar ("Pembacaan Alkitab / III Yohanes 1:1-12 / Bacaan 1")

Run:  python tools/build_assets.py reference/frames app/assets
If you later export blank backgrounds from CorelDRAW (1920x1080 PNG, no text),
just drop them in app/assets as bar.png / pill.png and skip this script.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1920, 1080
BAR_Y0, BAR_Y1 = 898, 984          # bar rows [y0, y1)
PILL_X0, PILL_X1 = 442, 1479       # pill columns [x0, x1)
PILL_Y0, PILL_Y1 = 852, 1038       # pill rows [y0, y1)
PILL_R = 42                        # corner radius
SS = 4                             # supersampling for smooth corners


def load(p):
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)


def build_bar(f_bar):
    """Smooth gradient fitted on text-free columns + the faint logo watermark."""
    clear = np.r_[0:495, 1425:W]
    xs = np.arange(W)
    band = np.zeros((BAR_Y1 - BAR_Y0, W, 3), np.float32)
    for i, y in enumerate(range(BAR_Y0, BAR_Y1)):
        for c in range(3):
            coef = np.polyfit(clear, f_bar[y, clear, c], 3)
            band[i, :, c] = np.polyval(coef, xs)
    # keep the watermark (left side only): add back the residual there
    resid = f_bar[BAR_Y0:BAR_Y1, :, :] - band
    resid_img = Image.fromarray(np.clip(resid + 128, 0, 255).astype(np.uint8))
    resid = np.asarray(resid_img.filter(ImageFilter.GaussianBlur(0.8)), np.float32) - 128
    ramp = np.clip((480 - xs) / 40.0, 0, 1)[None, :, None]   # fade out 440..480
    band = band + resid * ramp
    # make the band neutral grey (video adds a slight colour cast)
    grey = band.mean(axis=2, keepdims=True)
    band = np.repeat(grey, 3, axis=2)
    out = np.zeros((H, W, 4), np.uint8)
    out[BAR_Y0:BAR_Y1, :, :3] = np.clip(band, 0, 255).astype(np.uint8)
    out[BAR_Y0:BAR_Y1, :, 3] = 255
    return Image.fromarray(out, "RGBA")


def build_pill(f_pill):
    """Top and bottom caps of the pill: per-row colour from text-free columns."""
    clear = np.r_[460:720, 1200:1460]
    rows = np.median(f_pill[PILL_Y0:PILL_Y1, clear, :], axis=1).mean(axis=1)  # grey
    rgb = np.zeros((H, W, 3), np.uint8)
    rgb[PILL_Y0:PILL_Y1, PILL_X0:PILL_X1, :] = np.clip(rows, 0, 255).astype(np.uint8)[:, None, None]
    mask = Image.new("L", (W * SS, H * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [PILL_X0 * SS, PILL_Y0 * SS, PILL_X1 * SS - 1, PILL_Y1 * SS - 1], radius=PILL_R * SS, fill=255)
    mask = mask.resize((W, H), Image.LANCZOS)
    img = Image.fromarray(rgb, "RGB").convert("RGBA")
    img.putalpha(mask)
    return img


def main(frames_dir, out_dir):
    frames_dir, out_dir = Path(frames_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    build_bar(load(frames_dir / "f_330.png")).save(out_dir / "bar.png")
    build_pill(load(frames_dir / "f_2450.png")).save(out_dir / "pill.png")
    print("wrote", out_dir / "bar.png", out_dir / "pill.png")


if __name__ == "__main__":
    main(*sys.argv[1:3])
