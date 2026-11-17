"""Prepare a song for the music-sheet slides: fetch the .ppt, export slides, pick the verses."""
import json
import re
import subprocess
import threading
from pathlib import Path

import numpy as np
from PIL import Image

import song_library

APP = Path(__file__).resolve().parent
SLIDES = song_library.CACHE / "slides"
UPLOADS = song_library.CACHE / "uploads"
_ppt_lock = threading.Lock()          # PowerPoint handles one file at a time


class SongError(Exception):
    pass


def parse_verses(text):
    """'1-3' -> [1,2,3]; '1, 3' -> [1,3]; '' -> []"""
    out = []
    for part in re.split(r"[,;]", text or ""):
        part = part.strip()
        m = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
        if m:
            out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def export_slides(ppt_path, out_dir):
    """PowerPoint -> slideN.png + slides.json (cached)."""
    out_dir = Path(out_dir)
    if (out_dir / "slides.json").exists():
        return
    with _ppt_lock:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(APP / "ppt_export.ps1"),
             "-Path", str(ppt_path), "-OutDir", str(out_dir)],
            capture_output=True, text=True, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0 or not (out_dir / "slides.json").exists():
        msg = (r.stderr or r.stdout or "").strip().splitlines()
        hint = " Is Microsoft PowerPoint installed on this PC?" if "PowerPoint" in (r.stderr or "") or "COM" in (r.stderr or "") else ""
        raise SongError(f"Could not open the slides with PowerPoint.{hint} {msg[-1] if msg else ''}".strip())


def _ink(path):
    a = np.asarray(Image.open(path).convert("L").resize((360, 270)))
    return float((a < 100).mean()) * 100


def analyse(key, verses_text):
    """Return slide list + default selection for a prepared song."""
    folder = SLIDES / key
    info = json.loads((folder / "slides.json").read_text(encoding="utf-8-sig"))["slides"]
    if isinstance(info, dict):
        info = [info]
    slides = []
    lyrics_at = None
    for s in info:
        idx = int(s["index"])
        ink = _ink(folder / f"slide{idx}.png")
        text_len = len(s.get("text") or "")
        if lyrics_at is None and idx > 1 and text_len >= 150:
            lyrics_at = idx
        slides.append({"index": idx, "ink": round(ink, 1)})
    end = lyrics_at or (max(s["index"] for s in slides) + 1)
    notation = [s["index"] for s in slides if 1 < s["index"] < end and s["ink"] >= 3.0]
    verses = parse_verses(verses_text)
    if verses and notation and max(verses) <= len(notation):
        selected = [notation[v - 1] for v in verses]
        note = ""
    else:
        selected = list(notation)
        note = "Verses could not be matched one-to-one; all notation slides are selected - please check." if verses else ""
    for s in slides:
        s["kind"] = "lyrics" if s["index"] == lyrics_at else ("notation" if s["index"] in notation else "other")
    return {"slides": slides, "selected": selected, "note": note}


def prepare(code, num, verses_text):
    key = f"{code.upper()}_{num}"
    path, name = song_library.fetch_song(code, num)
    if path is None:
        raise SongError(name)
    export_slides(path, SLIDES / key)
    result = analyse(key, verses_text)
    result.update(key=key, name=Path(name).stem.strip(" ."))
    return result


def slide_file(key, index):
    if not re.fullmatch(r"[\w-]+", key):
        raise SongError("bad key")
    base = UPLOADS if key.startswith("UP_") else SLIDES
    p = base / key / f"slide{int(index)}.png"
    if not p.exists():
        raise SongError("slide not found")
    return p


def save_upload(key, file_storage):
    """A user-supplied image (for songs not in the library). Returns its slide index."""
    if not re.fullmatch(r"UP_[\w-]+", key):
        raise SongError("bad key")
    folder = UPLOADS / key
    folder.mkdir(parents=True, exist_ok=True)
    idx = len(list(folder.glob("slide*.png"))) + 1
    img = Image.open(file_storage.stream).convert("RGB")
    img.save(folder / f"slide{idx}.png")
    return idx
