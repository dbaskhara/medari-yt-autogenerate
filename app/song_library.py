"""Find and fetch song slides (.ppt) from the public GKJ Medari Drive library.

Library layout (public, no login needed):
  Lagu-lagu Kidung / <songbook> / <number range folder> / "KJ 413. Tuhan Pimpin AnakMu..ppt"
Files are downloaded once and kept in cache/songs, so a song used again is instant.
"""
import html
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT_FOLDER = "1yFBfo-NSstedSaBYXyqDBjuUr8U8OH8d"
CACHE = Path(__file__).resolve().parent.parent / "cache"
SONG_CACHE = CACHE / "songs"
LIST_TTL = 7 * 24 * 3600          # folder listings are re-read once a week

# songbook code in the Tata Ibadah -> folder name in the library
BOOKS = {
    "KJ": "Kidung Jemaat",
    "PKJ": "Pelengkap Kidung Jemaat",
    "NKB": "Nyanyikanlah Kidung Baru",
    "KP": "Kidung Pujian",
    "KPJ": "Kidung Pasamuwan Jawi",
    "KK": "Kidung Keesaan",
    "KPK": "Kidung Pasamuwan Kristen",
}
SLIDE_EXT = (".ppt", ".pptx", ".pps", ".ppsx")


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (MedariLiveFooter)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def list_folder(folder_id):
    """[(name, id, is_folder)] for a public Drive folder, cached for a week."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f"folder_{folder_id}.json"
    if cache_file.exists() and time.time() - cache_file.stat().st_mtime < LIST_TTL:
        return [tuple(x) for x in json.loads(cache_file.read_text(encoding="utf-8"))]
    page = _get(f"https://drive.google.com/embeddedfolderview?id={folder_id}").decode("utf-8", "replace")
    items = []
    for kind, fid, title in re.findall(
            r'<a href="https://drive\.google\.com/(drive/folders/|file/d/)([\w-]+)[^"]*"[^>]*>.*?'
            r'<div class="flip-entry-title">(.*?)</div>', page, re.S):
        items.append((html.unescape(title).strip(), fid, kind.startswith("drive")))
    cache_file.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return items


def _range_of(name):
    nums = [int(n) for n in re.findall(r"\d+", name)]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], 10 ** 6       # e.g. "PKJ 251_SELESAI"
    return None


def _matches(name, code, num):
    if name.lower().startswith("backup") or not name.lower().endswith(SLIDE_EXT):
        return False
    return re.match(rf"^\s*{re.escape(code)}[\s._\-]*0*{re.escape(num)}(?![0-9a-z])", name, re.IGNORECASE) is not None


def _search(folder_id, code, num, depth=0):
    items = list_folder(folder_id)
    for name, fid, is_folder in items:
        if not is_folder and _matches(name, code, num):
            return name, fid
    if depth >= 3:
        return None
    n = int(re.match(r"\d+", num).group())
    folders = [(name, fid) for name, fid, is_folder in items if is_folder]
    # number-range folders first ("KJ401-450_MPP"), then any other sub-folder
    ranged = [(name, fid) for name, fid in folders if (r := _range_of(name)) and r[0] <= n <= r[1]]
    for name, fid in ranged:
        hit = _search(fid, code, num, depth + 1)
        if hit:
            return hit
    return None


def find_song(code, num):
    """Return (file name, drive id) or None. code like 'KJ', num like '413' or '472b'."""
    code = code.upper()
    root = {name: fid for name, fid, is_folder in list_folder(ROOT_FOLDER) if is_folder}
    order = [BOOKS[code]] if code in BOOKS else []
    order += ["Lagu Tambahan", "Patch"]
    for book in order:
        if book in root:
            hit = _search(root[book], code, num)
            if hit:
                return hit
    return None


def fetch_song(code, num):
    """Download the song file (once). Returns (local path, original name) or (None, reason)."""
    SONG_CACHE.mkdir(parents=True, exist_ok=True)
    key = f"{code.upper()}_{num}"
    for p in SONG_CACHE.glob(f"{key}.*"):
        if p.suffix.lower() in SLIDE_EXT:
            meta = p.with_suffix(".name")
            return p, meta.read_text(encoding="utf-8") if meta.exists() else p.name
    hit = find_song(code, num)
    if not hit:
        return None, f"{code} {num} tidak ada di perpustakaan lagu"
    name, fid = hit
    data = _get(f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t", timeout=120)
    if not data.startswith(b"\xd0\xcf\x11\xe0") and not data.startswith(b"PK"):
        return None, f"Gagal mengunduh {name} (Drive mengirim halaman web)"
    path = SONG_CACHE / f"{key}{Path(name).suffix.lower()}"
    path.write_bytes(data)
    path.with_suffix(".name").write_text(name, encoding="utf-8")
    return path, name


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        c, n = arg.split(":")
        print(arg, fetch_song(c, n))
