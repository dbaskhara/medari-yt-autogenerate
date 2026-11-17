"""Preacher photos from the public Drive folder used for the thumbnails.

Folder (public, no login): cut-out PNGs named after the preacher, e.g. "Pdt. Eko Iswanto 1.png",
plus the sub-folder "PNG PF NEW". "FOTO PF ASLI" holds uncut originals and is not used.
"""
import io
import re
import unicodedata
from pathlib import Path

from PIL import Image

from song_library import CACHE, _get, list_folder

PHOTO_FOLDER = "1JJrI2WqzjBJhbzpiHAelCRR0kpr-7TIY"
SUBFOLDERS = ("PNG PF NEW",)
PHOTO_CACHE = CACHE / "photos"
UPLOADS = CACHE / "uploads"
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
# titles and file-name noise that say nothing about who it is
NOISE = {"pdt", "em", "bp", "ibu", "bu", "dkn", "pnt", "sdr", "sdri", "mas", "mbak", "dr", "drs", "s", "pd",
         "si", "th", "sth", "mth", "mpd", "msi", "dmin", "edited", "new", "photoroom", "old", "foto", "png", "jpg"}


def _words(name):
    name = unicodedata.normalize("NFKD", Path(name).stem if Path(name).suffix.lower() in IMAGE_EXT else name)
    name = "".join(c for c in name if not unicodedata.combining(c)).lower()
    name = re.sub(r"\(.*?\)", " ", name)          # "(GKJ Condongcatur)"
    return [w for w in re.split(r"[^a-z]+", name) if w and w not in NOISE and len(w) > 1]


def _all_photos():
    items = list_folder(PHOTO_FOLDER)
    out = [(n, fid) for n, fid, is_folder in items if not is_folder]
    for n, fid, is_folder in items:
        if is_folder and n in SUBFOLDERS:
            out += [(sn, sid) for sn, sid, sf in list_folder(fid) if not sf]
    return out


def find(preacher):
    """Photos that fit the preacher's name, best first: [{name, id}]."""
    want = set(_words(preacher))
    if not want:
        return []
    scored, seen = [], set()
    for name, fid in _all_photos():
        have = set(_words(name))
        common = want & have
        if not common or fid in seen:
            continue
        # every word of the shorter name must appear in the longer one ("Pdt. Agus" ~ "Agus Haryanto")
        if not (have <= want or want <= have):
            continue
        seen.add(fid)
        scored.append((-len(common), "NEW" not in name.upper(), name, fid))
    scored.sort()
    return [{"name": n, "id": fid} for _, _, n, fid in scored[:12]]


def fetch(fid):
    """Local path of a Drive photo (downloaded once)."""
    if not re.fullmatch(r"[\w-]{10,80}", fid):
        raise ValueError("bad photo id")
    PHOTO_CACHE.mkdir(parents=True, exist_ok=True)
    path = PHOTO_CACHE / f"{fid}.png"
    if not path.exists():
        data = _get(f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t", timeout=120)
        img = Image.open(io.BytesIO(data))       # raises if Drive sent a web page
        img.thumbnail((1600, 1600), Image.LANCZOS)
        img.save(path)
    return path


def save_upload(file):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    img = Image.open(file.stream)
    img.load()
    img.thumbnail((1600, 1600), Image.LANCZOS)
    key = f"UPPHOTO_{abs(hash((file.filename, img.size, img.tobytes()[:4096]))) % 10**10}"
    img.save(UPLOADS / f"{key}.png")
    return key


def path_of(key):
    """Photo key is a Drive id or an UPPHOTO_ upload key."""
    if key.startswith("UPPHOTO_"):
        if not re.fullmatch(r"UPPHOTO_\d+", key):
            raise ValueError("bad photo key")
        return UPLOADS / f"{key}.png"
    return fetch(key)


if __name__ == "__main__":
    import sys
    for q in sys.argv[1:]:
        print(q, find(q))
