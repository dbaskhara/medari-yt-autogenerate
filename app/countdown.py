"""Pre-service loop video: thumbnail -> fade -> base ad video -> fade -> thumbnail.

The base video ("Bahan Ads Mentah (Persembahan & Sosmed).mp4": QRIS offering + social media)
is taken from the public Drive folder "Bahan Ads Mentah" and kept in cache/ads.
If the multimedia team puts a new .mp4 in that folder, it is picked up within a week
(or at once with "refresh").
"""
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

from song_library import CACHE, _get, list_folder

ADS_FOLDER = "1hkltUbX40lM-OeAmB46oz9yLTZH_raCb"
ADS_CACHE = CACHE / "ads"
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv")
FPS = 30


class VideoError(Exception):
    pass


def base_video(refresh=False):
    """(local path, name) of the newest base video in the Drive folder."""
    if refresh:
        f = CACHE / f"folder_{ADS_FOLDER}.json"
        if f.exists():
            f.unlink()
    try:
        vids = [(n, fid) for n, fid, is_folder in list_folder(ADS_FOLDER)
                if not is_folder and n.lower().endswith(VIDEO_EXT)]
    except Exception:
        vids = []
    ADS_CACHE.mkdir(parents=True, exist_ok=True)
    if not vids:   # offline: use what we have
        have = sorted(ADS_CACHE.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if have:
            return have[0], have[0].name
        raise VideoError("Video dasar tidak ditemukan di folder Drive 'Bahan Ads Mentah'.")
    name, fid = vids[0]
    path = ADS_CACHE / f"{fid}{Path(name).suffix.lower()}"
    if not path.exists():
        data = _get(f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t", timeout=600)
        if data[4:8] != b"ftyp" and not data.startswith(b"\x1a\x45\xdf\xa3"):
            raise VideoError(f"Gagal mengunduh {name} (Drive mengirim halaman web, bukan video).")
        path.write_bytes(data)
    return path, name


def _duration(path):
    out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True, errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise VideoError("Durasi video dasar tidak bisa dibaca.")


def make(thumb_img, out_path, hold=5.0, fade=1.0):
    """Write the loop video (1920x1080, 30 fps, H.264, no sound) to out_path."""
    base, _ = base_video()
    dur = _duration(base)
    hold = max(float(hold), fade + 0.5)
    with tempfile.TemporaryDirectory() as tmp:
        still = Path(tmp) / "thumb.png"
        thumb_img.convert("RGB").save(still)
        norm = f"scale=1920:1080:flags=lanczos,fps={FPS},format=yuv420p,setsar=1,settb=AVTB"
        graph = (f"[0:v]{norm}[a];[1:v]{norm}[b];[2:v]{norm}[c];"
                 f"[a][b]xfade=transition=fade:duration={fade}:offset={hold - fade}[ab];"
                 f"[ab][c]xfade=transition=fade:duration={fade}:offset={hold + dur - 2 * fade}[v]")
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
               "-loop", "1", "-framerate", str(FPS), "-t", str(hold), "-i", str(still),
               "-i", str(base),
               "-loop", "1", "-framerate", str(FPS), "-t", str(hold), "-i", str(still),
               "-filter_complex", graph, "-map", "[v]", "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(out_path)]
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise VideoError("Video gagal dibuat: " + (r.stderr.strip().splitlines() or ["ffmpeg error"])[-1])
    return out_path
