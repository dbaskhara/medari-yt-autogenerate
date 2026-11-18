"""Medari Live Kit - local web app.

Start with "Buat Aset Live.bat" (it opens http://127.0.0.1:5055 in the browser).
"""
import io
import os
import re
import sys
import shutil
import tempfile
import threading
import uuid
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

sys.path.insert(0, str(Path(__file__).parent))
import countdown  # noqa: E402
import footer_render  # noqa: E402
import liturgy_parser  # noqa: E402
import photos  # noqa: E402
import sheet_render  # noqa: E402
import songs  # noqa: E402
import thumb_render  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
PORT = int(os.environ.get("MEDARI_PORT", "5055"))

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024


@app.get("/")
def index():
    return send_from_directory(Path(__file__).parent / "web", "index.html")


@app.post("/api/parse")
def api_parse():
    f = request.files.get("pdf")
    if not f or not f.filename.lower().endswith(".pdf"):
        return jsonify(error="Pilih file PDF Tata Ibadah."), 400
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.pdf"
        f.save(path)
        try:
            svc = liturgy_parser.parse(path)
        except Exception as e:  # show the reason on the page instead of a crash
            return jsonify(error=f"PDF ini tidak bisa dibaca: {e}"), 400
    data = svc.to_dict()
    data["filename"] = f.filename
    data["thumb"] = thumb_render.default_texts(data)
    return jsonify(data)


# ---------- thumbnail ----------
THUMB_FIELDS = ("date_line", "theme", "readings", "preacher", "time_lang")


def _thumb_image(t):
    photo = None
    if t.get("photo"):
        try:
            photo = Image.open(photos.path_of(t["photo"]))
        except Exception as e:
            raise ValueError(f"Foto tidak bisa dimuat: {e}")
    return thumb_render.render(*[(t.get(k) or "").strip() if k != "theme" else (t.get(k) or "") for k in THUMB_FIELDS],
                               photo=photo, zoom=float(t.get("zoom") or 1), dx=int(t.get("dx") or 0),
                               dy=int(t.get("dy") or 0))


@app.get("/api/photos")
def api_photos():
    try:
        return jsonify(photos=photos.find(request.args.get("name", "")))
    except Exception as e:
        return jsonify(photos=[], error=f"Folder foto tidak bisa dibuka: {e}")


@app.post("/api/photo-upload")
def api_photo_upload():
    f = request.files.get("image")
    if not f:
        return jsonify(error="Pilih file gambar."), 400
    try:
        return jsonify(key=photos.save_upload(f))
    except Exception as e:
        return jsonify(error=f"Gambar ini tidak bisa dipakai: {e}"), 400


@app.post("/api/thumb-preview")
def api_thumb_preview():
    try:
        return _jpeg(_thumb_image(request.get_json(force=True)), 960)
    except ValueError as e:
        return str(e), 400


@app.post("/api/preview")
def api_preview():
    d = request.get_json(force=True)
    kind = d.get("kind", "bar")
    img = footer_render.preview(kind, d.get("main", ""), d.get("top", ""), d.get("bottom", ""),
                                width=int(d.get("width") or 960), full=bool(d.get("full")))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    buf.seek(0)
    resp = send_file(buf, mimetype="image/jpeg")
    resp.headers["X-Images"] = str(len(footer_render.box_pages(d.get("main", ""))) if kind == "box" else 1)
    return resp


def _folder_name(date_text):
    try:
        months = {m: i for i, m in enumerate(
            ["januari", "februari", "maret", "april", "mei", "juni", "juli", "agustus",
             "september", "oktober", "november", "desember"], 1)}
        dd, mm, yy = date_text.split()
        return f"{int(yy):04d}-{months[mm.lower()]:02d}-{int(dd):02d}"
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def _jpeg(img, width):
    h = round(img.height * width / img.width)
    buf = io.BytesIO()
    img.convert("RGB").resize((width, h), Image.LANCZOS).save(buf, "JPEG", quality=82)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


@app.post("/api/song")
def api_song():
    d = request.get_json(force=True)
    code, num = (d.get("code") or "").strip(), (d.get("num") or "").strip()
    if not re.fullmatch(r"[A-Za-z]{1,6}", code) or not re.fullmatch(r"\d{1,4}[a-z]?", num):
        return jsonify(error="Nomor lagu sepertinya salah (contoh: KJ 413)."), 400
    try:
        return jsonify(songs.prepare(code, num, d.get("verses", "")))
    except songs.SongError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"{code} {num} tidak bisa diambil: {e}"), 400


@app.get("/api/slide/<key>/<int:index>")
def api_slide(key, index):
    try:
        img = Image.open(songs.slide_file(key, index))
    except songs.SongError as e:
        return str(e), 404
    return _jpeg(img, min(int(request.args.get("w", 320)), 1440))


@app.post("/api/song-upload")
def api_song_upload():
    key = request.form.get("key", "")
    f = request.files.get("image")
    if not f:
        return jsonify(error="Pilih file gambar."), 400
    try:
        return jsonify(index=songs.save_upload(key, f))
    except Exception as e:
        return jsonify(error=f"Gambar ini tidak bisa dipakai: {e}"), 400


@app.post("/api/sheet-preview")
def api_sheet_preview():
    d = request.get_json(force=True)
    try:
        path = songs.slide_file(d["key"], d["index"])
    except (KeyError, songs.SongError) as e:
        return str(e), 404
    return _jpeg(sheet_render.render(path, d.get("label", ""), bool(d.get("qr"))), 640)


# ---------- generate (runs in the background; the page polls /api/job/<id> for progress) ----------
JOBS = {}
LIVE_FOLDER = OUTPUT / "Minggu Ini"      # fixed folder for OBS: always this week's files
# sub-folders, one per OBS scene: footers over the camera, song slides (camera in the frame's hole),
# offering song slides (the hole sits higher, next to the QR card)
LIVE_SUB = {"footer": "Footer", "lagu": "Lagu", "lagu_qr": "Lagu Persembahan"}
ARCHIVE = OUTPUT / "Arsip"


def _plan(d):
    jobs = []   # (footer or None, sheet or None, item)
    for it in d.get("footers", []):
        footer = it if it.get("include") and (it.get("main") or "").strip() else None
        sheet = it.get("sheet") if (it.get("sheet") or {}).get("include") and (it.get("sheet") or {}).get("slides") else None
        if footer or sheet:
            jobs.append((footer, sheet, it))
    thumb = d.get("thumb") if (d.get("thumb") or {}).get("include") else None
    return jobs, thumb


def _count(jobs, thumb):
    n = 0
    for footer, sheet, _ in jobs:
        if footer:
            n += len(footer_render.box_pages(footer["main"])) if footer.get("kind") == "box" else 1
        if sheet:
            n += len(sheet["slides"])
    if thumb:
        n += 2 + (1 if thumb.get("video") else 0)
    return n


def _archive(folder):
    """Move the files of an earlier run to output/Arsip/<folder> <time>; never delete them."""
    old = [p for p in folder.iterdir() if p.is_file()] if folder.exists() else []
    if not old:
        return None
    dest = ARCHIVE / f"{folder.name} {datetime.now().strftime('%Y-%m-%d %H.%M.%S')}"
    dest.mkdir(parents=True, exist_ok=True)
    for p in old:
        p.replace(dest / p.name)
    return dest


def _run(job, d, jobs, thumb):
    try:
        folder = OUTPUT / f"{_folder_name(d.get('date', ''))} Footer"
        job["archived"] = str(_archive(folder) or "")
        folder.mkdir(parents=True, exist_ok=True)
        names, cats = [], {}

        def done(name, what, cat="thumb"):
            names.append(name)
            cats[name] = cat
            job.update(step=len(names), current=what)

        if thumb:
            job["current"] = "Thumbnail"
            thumb_img = _thumb_image(thumb)
            thumb_img.resize((1280, 720), Image.LANCZOS).save(folder / "00 - Thumbnail YouTube.jpg", quality=92)
            done("00 - Thumbnail YouTube.jpg", "Thumbnail")
            thumb_img.save(folder / "00 - Thumbnail 1920.png", optimize=True)
            done("00 - Thumbnail 1920.png", "Thumbnail")
            if thumb.get("video"):
                job["current"] = "Video countdown (sekitar 15 detik)"
                countdown.make(thumb_img, folder / "00 - Countdown Loop.mp4",
                               hold=float(thumb.get("hold") or 5), fade=float(thumb.get("fade") or 1))
                done("00 - Countdown Loop.mp4", "Video countdown")
        for n, (footer, sheet, it) in enumerate(jobs, 1):
            if footer and footer.get("kind") == "box":
                pages = footer_render.render_boxes(footer["main"])
                what = footer.get("bottom") or "box"
                label = footer_render.safe_name(f"{footer.get('top') or 'Box'} - {what}")
                for j, img in enumerate(pages):
                    name = f"{n:02d}{chr(97 + j)} - {label} ({j + 1} of {len(pages)}).png"
                    img.save(folder / name, optimize=True)
                    done(name, label, "footer")
            elif footer:
                img = footer_render.render(footer.get("kind", "bar"), footer["main"].strip(),
                                           (footer.get("top") or "").strip(), (footer.get("bottom") or "").strip())
                label = footer["main"] if footer.get("kind") == "bar" else f"{footer.get('top') or ''} - {footer['main']}"
                name = f"{n:02d} - {footer_render.safe_name(label)}.png"
                img.save(folder / name, optimize=True)
                done(name, footer["main"], "footer")
            if sheet:
                for j, idx in enumerate(sheet["slides"]):
                    try:
                        path = songs.slide_file(sheet["key"], idx)
                    except songs.SongError:
                        continue
                    img = sheet_render.render(path, sheet.get("label", ""), bool(sheet.get("qr")))
                    song_name = footer_render.safe_name(it.get("main") or sheet["key"])
                    name = f"{n:02d}{chr(97 + j)} - Lagu - {song_name} ({j + 1} of {len(sheet['slides'])}).png"
                    img.save(folder / name, optimize=True)
                    done(name, f"Lagu {song_name}", "lagu_qr" if sheet.get("qr") else "lagu")
        job["current"] = "ZIP dan folder OBS"
        zbuf = folder.with_suffix(".zip")
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            for name in names:
                z.write(folder / name, name)
        job["locked"] = _fill_live(folder, names, cats)
        job.update(done=True, folder=str(folder), live=str(LIVE_FOLDER), zip=zbuf.name, files=names,
                   rel=folder.name, current="")
    except Exception as e:
        job.update(done=True, error=str(e) or e.__class__.__name__)


def _fill_live(folder, names, cats):
    """Copy this week's files into output/Minggu Ini (and its scene folders) for OBS.
    A file OBS has open (e.g. the countdown video while it plays) cannot be replaced:
    it is listed and everything else is still updated."""
    locked = []
    dirs = [LIVE_FOLDER] + [LIVE_FOLDER / d for d in LIVE_SUB.values()]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        for p in d.iterdir():
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    locked.append(str(p.relative_to(LIVE_FOLDER)))
    for name in names:
        sub = LIVE_SUB.get(cats.get(name))
        dest = (LIVE_FOLDER / sub / name) if sub else (LIVE_FOLDER / name)
        try:
            shutil.copy2(folder / name, dest)
        except OSError:
            rel = str(dest.relative_to(LIVE_FOLDER))
            if rel not in locked:
                locked.append(rel)
    return locked


@app.post("/api/generate")
def api_generate():
    d = request.get_json(force=True)
    jobs, thumb = _plan(d)
    if not jobs and not thumb:
        return jsonify(error="Belum ada yang dipilih untuk dibuat."), 400
    if thumb:
        try:
            _thumb_image(thumb)        # fail early on a broken photo
        except ValueError as e:
            return jsonify(error=str(e)), 400
    job_id = uuid.uuid4().hex[:12]
    job = JOBS[job_id] = {"done": False, "step": 0, "total": _count(jobs, thumb), "current": "", "error": ""}
    threading.Thread(target=_run, args=(job, d, jobs, thumb), daemon=True).start()
    return jsonify(job=job_id, total=job["total"])


@app.get("/api/job/<job_id>")
def api_job(job_id):
    job = JOBS.get(job_id)
    return (jsonify(job), 200) if job else (jsonify(error="tidak ditemukan"), 404)


@app.get("/api/output/<path:rel>")
def api_output(rel):
    """A generated file as a small picture for the gallery on the page."""
    path = (OUTPUT / rel).resolve()
    if OUTPUT.resolve() not in path.parents or not path.is_file() or path.suffix.lower() not in (".png", ".jpg"):
        return "not found", 404
    w = min(int(request.args.get("w", 360)), 1920)
    img = Image.open(path)
    if img.mode == "RGBA":                     # transparent footers: show them over the camera picture
        bg = footer_render.camera_bg().copy()
        bg.alpha_composite(img.convert("RGBA").resize(bg.size))
        img = bg
    return _jpeg(img, w)


@app.get("/api/download/<path:name>")
def api_download(name):
    if not re.fullmatch(r"[\w\- ]+\.zip", name):
        return "bad name", 400
    return send_from_directory(OUTPUT, name, as_attachment=True)


@app.post("/api/open-folder")
def api_open_folder():
    folder = Path(request.get_json(force=True).get("folder", ""))
    if OUTPUT.resolve() in (folder.resolve(), *folder.resolve().parents) and folder.exists():
        os.startfile(folder)  # Windows Explorer
        return jsonify(ok=True)
    return jsonify(error="folder tidak ditemukan"), 400


if __name__ == "__main__":
    import logging
    import flask.cli
    logging.getLogger("werkzeug").setLevel(logging.ERROR)   # keep the console window quiet
    flask.cli.show_server_banner = lambda *a, **k: None
    OUTPUT.mkdir(exist_ok=True)
    url = f"http://127.0.0.1:{PORT}"
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"\n  Medari Live Kit berjalan di {url}\n  Biarkan jendela ini terbuka. Tutup jendela ini untuk menghentikan aplikasi.\n")
    app.run(host="127.0.0.1", port=PORT, debug=False)
