"""Medari Live Footer Generator - local web app.

Start with "Generate Footer.bat" (it opens http://127.0.0.1:5055 in the browser).
"""
import io
import os
import re
import sys
import tempfile
import threading
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
        return jsonify(error="Please choose a PDF file (Tata Ibadah / Warta Jemaat)."), 400
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.pdf"
        f.save(path)
        try:
            svc = liturgy_parser.parse(path)
        except Exception as e:  # show the reason on the page instead of a crash
            return jsonify(error=f"Could not read this PDF: {e}"), 400
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
            raise ValueError(f"Could not load the photo: {e}")
    return thumb_render.render(*[(t.get(k) or "").strip() if k != "theme" else (t.get(k) or "") for k in THUMB_FIELDS],
                               photo=photo, zoom=float(t.get("zoom") or 1), dx=int(t.get("dx") or 0),
                               dy=int(t.get("dy") or 0))


@app.get("/api/photos")
def api_photos():
    try:
        return jsonify(photos=photos.find(request.args.get("name", "")))
    except Exception as e:
        return jsonify(photos=[], error=f"Photo folder could not be read: {e}")


@app.post("/api/photo-upload")
def api_photo_upload():
    f = request.files.get("image")
    if not f:
        return jsonify(error="Choose an image file."), 400
    try:
        return jsonify(key=photos.save_upload(f))
    except Exception as e:
        return jsonify(error=f"Could not use this image: {e}"), 400


@app.post("/api/thumb-preview")
def api_thumb_preview():
    try:
        return _jpeg(_thumb_image(request.get_json(force=True)), 960)
    except ValueError as e:
        return str(e), 400


@app.post("/api/preview")
def api_preview():
    d = request.get_json(force=True)
    img = footer_render.preview(d.get("kind", "bar"), d.get("main", ""), d.get("top", ""), d.get("bottom", ""))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg")


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
        return jsonify(error="Song number looks wrong (example: KJ 413)."), 400
    try:
        return jsonify(songs.prepare(code, num, d.get("verses", "")))
    except songs.SongError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"Could not get {code} {num}: {e}"), 400


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
        return jsonify(error="Choose an image file."), 400
    try:
        return jsonify(index=songs.save_upload(key, f))
    except Exception as e:
        return jsonify(error=f"Could not use this image: {e}"), 400


@app.post("/api/sheet-preview")
def api_sheet_preview():
    d = request.get_json(force=True)
    try:
        path = songs.slide_file(d["key"], d["index"])
    except (KeyError, songs.SongError) as e:
        return str(e), 404
    return _jpeg(sheet_render.render(path, d.get("label", ""), bool(d.get("qr"))), 640)


@app.post("/api/generate")
def api_generate():
    d = request.get_json(force=True)
    jobs = []   # (footer or None, sheet or None)
    for it in d.get("footers", []):
        footer = it if it.get("include") and (it.get("main") or "").strip() else None
        sheet = it.get("sheet") if (it.get("sheet") or {}).get("include") and (it.get("sheet") or {}).get("slides") else None
        if footer or sheet:
            jobs.append((footer, sheet, it))
    thumb = d.get("thumb") if (d.get("thumb") or {}).get("include") else None
    if not jobs and not thumb:
        return jsonify(error="Nothing to generate - tick at least one footer, song or the thumbnail."), 400
    try:
        thumb_img = _thumb_image(thumb) if thumb else None
    except ValueError as e:
        return jsonify(error=str(e)), 400
    folder = OUTPUT / f"{_folder_name(d.get('date', ''))} Footer"
    folder.mkdir(parents=True, exist_ok=True)
    for old in list(folder.glob("*.png")) + list(folder.glob("*.jpg")) + list(folder.glob("*.mp4")):
        old.unlink()
    names = []
    if thumb_img:
        thumb_img.resize((1280, 720), Image.LANCZOS).save(folder / "00 - Thumbnail YouTube.jpg", quality=92)
        thumb_img.save(folder / "00 - Thumbnail 1920.png", optimize=True)
        names += ["00 - Thumbnail YouTube.jpg", "00 - Thumbnail 1920.png"]
        if thumb.get("video"):
            try:
                countdown.make(thumb_img, folder / "00 - Countdown Loop.mp4",
                               hold=float(thumb.get("hold") or 5), fade=float(thumb.get("fade") or 1))
                names.append("00 - Countdown Loop.mp4")
            except Exception as e:
                return jsonify(error=f"{e}"), 400
    for n, (footer, sheet, it) in enumerate(jobs, 1):
        if footer:
            img = footer_render.render(footer.get("kind", "bar"), footer["main"].strip(),
                                       (footer.get("top") or "").strip(), (footer.get("bottom") or "").strip())
            label = footer["main"] if footer.get("kind") == "bar" else f"{footer.get('top') or ''} - {footer['main']}"
            name = f"{n:02d} - {footer_render.safe_name(label)}.png"
            img.save(folder / name, optimize=True)
            names.append(name)
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
                names.append(name)
    zbuf = folder.with_suffix(".zip")
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.write(folder / name, name)
    return jsonify(folder=str(folder), zip=zbuf.name, files=names)


@app.get("/api/download/<path:name>")
def api_download(name):
    if not re.fullmatch(r"[\w\- ]+\.zip", name):
        return "bad name", 400
    return send_from_directory(OUTPUT, name, as_attachment=True)


@app.post("/api/open-folder")
def api_open_folder():
    folder = Path(request.get_json(force=True).get("folder", ""))
    if folder.resolve().parent == OUTPUT.resolve() and folder.exists():
        os.startfile(folder)  # Windows Explorer
        return jsonify(ok=True)
    return jsonify(error="folder not found"), 400


if __name__ == "__main__":
    import logging
    import flask.cli
    logging.getLogger("werkzeug").setLevel(logging.ERROR)   # keep the console window quiet
    flask.cli.show_server_banner = lambda *a, **k: None
    OUTPUT.mkdir(exist_ok=True)
    url = f"http://127.0.0.1:{PORT}"
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"\n  Medari Footer Generator is running at {url}\n  Keep this window open. Close it to stop the app.\n")
    app.run(host="127.0.0.1", port=PORT, debug=False)
