"""Read a GKJ Medari-Sleman "Tata Ibadah" PDF and list the live-stream footers.

Each section of the service is a row on a light-blue band in the PDF. Every
band becomes one footer:
  * a song   ("Pujian Pembuka: KP 7: 1-3 "Terpujilah Allah"")  -> pill
  * Pembacaan Alkitab -> one pill per reading (Bacaan I, Bacaan II)
  * Khotbah           -> pill with the preacher's name
  * anything else     -> plain bar with the section name
Songs that appear inside the text (not on a band) are offered too, unticked.
"""
import re
from dataclasses import dataclass, asdict, field

import pymupdf

SONG_BOOKS = r"(?:KJ|PKJ|KPJ|KP|NKB|NNBT|GB|KMM|MKJ|Kid\.?\s*Jemaat)"
SONG_RE = re.compile(
    rf"^(?P<label>.*?)[\s:]*\b(?P<book>{SONG_BOOKS})\s*(?P<num>\d+[a-z]?)"
    rf"(?:\s*:\s*(?P<verses>[\d\s,\-–]+?))?\s*[\"“”](?P<title>[^\"“”]+)[\"“”]",
    re.IGNORECASE,
)
INLINE_SONG_RE = re.compile(
    rf"\b(?P<book>{SONG_BOOKS})\s*(?P<num>\d+[a-z]?)(?:\s*:\s*(?P<verses>[\d\s,\-–]+?))?\s*[\"“”](?P<title>[^\"“”]+)[\"“”]"
)
ROLE_RE = re.compile(r"\s*\((?:MJ\s*\d*|PF|Imam|Pnt\.?|Dkn\.?|Liturgos|[A-Z]{1,4}\d?(?:\s*&\s*[A-Z]{1,4}\d?)*)\)\s*$")
STAGE_RE = re.compile(r"\((?:Jemaat|Umat)[^)]*\)", re.IGNORECASE)
READING_RE = re.compile(r"Bacaan\s+(?P<n>I{1,3}|IV|\d)\s+(?P<ref>.+?)\s*(?:\((?:MJ\s*\d*|PF)[^)]*\)|$)")
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


@dataclass
class Footer:
    kind: str                 # "bar" or "pill"
    main: str
    top: str = ""
    bottom: str = ""
    include: bool = True
    source: str = ""          # the PDF text it came from, shown as a hint
    song: dict = None         # {"code": "KJ", "num": "413", "verses": "1, 2"} for songs


@dataclass
class Service:
    title: str = ""
    date: str = ""
    time: str = ""
    theme: str = ""
    preacher: str = ""
    preacher_church: str = ""
    footers: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        return d


def _clean(s):
    s = s.replace(" ", " ").replace("�", '"')
    return re.sub(r"\s+", " ", s).strip()


def _is_header_fill(fill):
    if not fill:
        return False
    r, g, b = fill[:3]
    return b > 0.7 and r < 0.85 and b - r > 0.08


def _lines(page):
    """All text lines on a page as (y_center, x0, text, bbox)."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"])
            if not text.strip():
                continue
            x0, y0, x1, y1 = line["bbox"]
            out.append(((y0 + y1) / 2, x0, _clean(text), (x0, y0, x1, y1)))
    out.sort(key=lambda t: (round(t[0]), t[1]))
    # merge pieces that sit on the same visual row (e.g. "Bacaan I" + "III Yohanes 1:1-12")
    rows = []
    for item in out:
        if rows and abs(rows[-1][0] - item[0]) <= 3:
            y, x0, text, bb = rows[-1]
            parts = sorted([(x0, text), (item[1], item[2])])
            rows[-1] = (y, parts[0][0], parts[0][1] + "  " + parts[1][1],
                        (min(bb[0], item[3][0]), min(bb[1], item[3][1]), max(bb[2], item[3][2]), max(bb[3], item[3][3])))
        else:
            rows.append(item)
    return rows


def _header_bands(page):
    rects = [d["rect"] for d in page.get_drawings()
             if _is_header_fill(d.get("fill")) and d["rect"].height > 8 and d["rect"].width > 200]
    rects.sort(key=lambda r: r.y0)
    return rects


def _song_main(book, num, verses):
    main = f"{book.upper() if len(book) <= 4 else book} {num}"
    if verses:
        v = re.sub(r"\s*,\s*", ", ", verses.strip().replace("–", "-"))
        v = re.sub(r"\s*-\s*", "-", v)
        main += f": {v}"
    return main


def _song_ref(m):
    book = re.sub(r"\s+", "", m.group("book")).upper()
    verses = (m.group("verses") or "").strip().replace("–", "-")
    return {"code": book, "num": m.group("num"), "verses": verses}


def _classify(header, body_after):
    """Turn one blue-band header into zero or more footers."""
    text = _clean(STAGE_RE.sub("", header))
    if not text or text.isupper():
        return []
    m = SONG_RE.search(text)
    if m:
        label = ROLE_RE.sub("", m.group("label")).strip(" :")
        return [Footer("pill", _song_main(m.group("book"), m.group("num"), m.group("verses")),
                       top=label, bottom=_clean(m.group("title")), source=header, song=_song_ref(m))]
    name = ROLE_RE.sub("", text).strip(" :")
    if re.fullmatch(r"Pembacaan Alkitab", name, re.IGNORECASE):
        readings = []
        for line in body_after:
            r = READING_RE.search(line)
            if r:
                n = ROMAN.get(r.group("n"), r.group("n"))
                readings.append(Footer("pill", _clean(r.group("ref")), top="Pembacaan Alkitab",
                                       bottom=f"Bacaan {n}", source=line))
        return readings or [Footer("bar", name, source=header)]
    if re.fullmatch(r"Khotbah", name, re.IGNORECASE):
        return [Footer("pill", "{preacher}", top="Khotbah", source=header)]
    return [Footer("bar", name, source=header)]


def parse(pdf_path):
    doc = pymupdf.open(pdf_path)
    svc = Service()

    # ---- whole-document facts ------------------------------------------------
    full = _clean(" ".join(p.get_text() for p in doc))
    first = [l[2] for l in _lines(doc[0])]
    for i, line in enumerate(first[:8]):
        m = re.search(r"(\d{1,2}\s+\w+\s+\d{4})\s*,\s*(\d{1,2}[.:]\d{2})\s*WIB", line)
        if m:
            svc.date, svc.time = m.group(1), m.group(2).replace(".", ":") + " WIB"
            svc.title = first[0] if not first[0].isdigit() else (first[1] if len(first) > 1 else "")
            if i + 1 < len(first):
                svc.theme = first[i + 1].strip(' "“”')
            break
    m = re.search(r"dilayankan oleh\s+(?:Bp\.|Ibu|Sdr\.|Sdri\.)?\s*(Pdt\.[^,]+?|Vik\.[^,]+?|Pnt\.[^,]+?)\s+dari\s+(.+?)(?:,|\s+dalam rangka|\.\s)", full)
    if m:
        svc.preacher = _clean(m.group(1))
        church = _clean(m.group(2))
        abbr = re.search(r"\(([A-Z]{2,})\)\s*(.*)", church)
        svc.preacher_church = f"{abbr.group(1)} {abbr.group(2)}".strip() if abbr else church

    # ---- footers, in page order ----------------------------------------------
    header_texts = set()
    entries = []   # (page, y, kind, payload)
    for pno, page in enumerate(doc):
        lines = _lines(page)
        bands = _header_bands(page)
        used = set()
        groups = []
        for band in bands:
            idx = [i for i, l in enumerate(lines) if i not in used and band.y0 - 1 <= l[0] <= band.y1 + 1]
            if not idx:
                continue
            used.update(idx)
            groups.append((band.y0, idx))
        for y, idx in groups:
            header = _clean(" ".join(lines[i][2] for i in idx))
            body_after = [l[2] for i, l in enumerate(lines) if i > max(idx)][:12]
            header_texts.add(header)
            entries.append((pno, y, "header", (header, body_after)))
        for i, l in enumerate(lines):
            if i in used:
                continue
            for m in INLINE_SONG_RE.finditer(l[2]):
                entries.append((pno, l[0], "inline", (l[2], m)))

    entries.sort(key=lambda e: (e[0], e[1]))
    seen_songs = set()   # "KJ 413" style keys, so a song is only offered once
    for _, _, kind, payload in entries:
        if kind == "header":
            new = _classify(*payload)
            for f in new:
                k = re.match(rf"({SONG_BOOKS})\s*(\d+[a-z]?)", f.main, re.IGNORECASE)
                if k:
                    seen_songs.add(f"{k.group(1).upper()} {k.group(2)}")
            svc.footers.extend(new)
        else:
            line, m = payload
            main = _song_main(m.group("book"), m.group("num"), m.group("verses"))
            key = f"{m.group('book').upper()} {m.group('num')}"
            if key in seen_songs:
                continue
            seen_songs.add(key)
            svc.footers.append(Footer("pill", main, top="Pujian", bottom=_clean(m.group("title")),
                                      include=False, source=line, song=_song_ref(m)))

    for f in svc.footers:
        if f.main == "{preacher}":
            f.main = svc.preacher or "Pdt. ..."
    return svc


if __name__ == "__main__":
    import json, sys
    print(json.dumps(parse(sys.argv[1]).to_dict(), ensure_ascii=False, indent=1))
