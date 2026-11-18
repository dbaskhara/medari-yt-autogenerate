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
# role codes after a section name: (PF) (MJ1) (Imam) - Javanese services: (PP) (Prd1) (Prd3 & PP)
_ROLE = r"(?:MJ\s*\d*|PF|PP|Prd\s*\d*|Imam|Pnt\.?|Dkn\.?|Liturgos|[A-Z]{1,4}\d?)"
ROLE_RE = re.compile(rf"\s*\({_ROLE}(?:\s*&\s*{_ROLE})*\)\s*$")
STAGE_RE = re.compile(r"\((?:Jemaat|Umat|Pasamuwan)[^)]*\)", re.IGNORECASE)
READING_RE = re.compile(r"(?P<word>Bacaan|Waosan)\s+(?P<n>I{1,3}|IV|\d)\s*:?\s+(?P<ref>.+?)\s*(?:\((?:MJ\s*\d*|PF|PP|Prd\s*\d*)[^)]*\)|$)")
READING_HEADERS = r"Pembacaan Alkitab|Pamaosing Pangandika|Pamaosing Kitab Suci"
SERMON_HEADERS = r"Khotbah|Panyuraosing Pangandika|Kotbah"
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


@dataclass
class Footer:
    kind: str                 # "bar", "pill" or "box" (dialog / lyrics box; main holds the lines)
    main: str
    top: str = ""
    bottom: str = ""
    include: bool = True
    source: str = ""          # the PDF text it came from, shown as a hint
    song: dict = None         # {"code": "KJ", "num": "413", "verses": "1, 2"} for songs
    layout: str = ""          # "full": music sheet full screen, without camera (e.g. songs during Bujana Suci)


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
    if re.match(rf"(?:PF|PP|Prd\s*\d*|MJ\s*\d*)\s+\S", name):     # "PP Mandhap saking mimbar ..." = stage direction
        return []
    if re.fullmatch(READING_HEADERS, name, re.IGNORECASE):
        readings = []
        for line in body_after:
            r = READING_RE.search(line)
            if r:
                n = ROMAN.get(r.group("n"), r.group("n"))
                readings.append(Footer("pill", _clean(r.group("ref")).strip(" :"), top=name,
                                       bottom=f"{r.group('word')} {n}", source=line))
        return readings or [Footer("bar", name, source=header)]
    if re.fullmatch(SERMON_HEADERS, name, re.IGNORECASE):
        return [Footer("pill", "{preacher}", top=name, source=header)]
    return [Footer("bar", name, source=header)]


SPEAKER_RE = re.compile(r"^(PF|PP|U|MJ\s*\d*|Prd\s*\d*|Imam|Pnt\.?|L|P|J)\s*:\s*(.*)$")
# "disambut dengan nyanyian "..."" / Javanese "kasambut (kanthi pepujèn) "...""
SUNG_RE = re.compile(r"(?:nyanyi\w*|menyanyikan|lagu|pujian|kasambut|pepuj[eè]n|kidung)\s+(?:kanthi\s+pepuj[eè]n\s+)?"
                     r"[\"“”]([^\"“”]{4,80})[\"“”]", re.IGNORECASE)


def _dialog(body):
    """PF / U turns of a section: [(speaker, [lines])]. Stops at stage directions."""
    turns = []
    for line in body:
        line = line.replace("  ", " ").strip()
        m = SPEAKER_RE.match(line)
        if m:
            spk = re.sub(r"\s+", "", m.group(1))
            text = m.group(2).strip()
            if not text or re.match(r"(?:menyanyikan|bernyanyi|ngidungaken|kidung)\b", text, re.IGNORECASE):
                break
            turns.append((spk, [STAGE_RE.sub("", text).strip()]))
        elif turns and line and line[0] not in "(#~*" and not line.isupper():
            prev = turns[-1][1]
            # the PDF broke the sentence (small letter, or the line before has no punctuation): join it again
            if line[0].islower() or prev[-1].endswith("-") or not re.search(r"[.,!?;:”\"]$", prev[-1]):
                prev[-1] += ("" if prev[-1].endswith("-") else " ") + line
            else:
                prev.append(line)
        elif turns:
            break
    clean = []
    for spk, lines in turns:   # drop stage directions in brackets, also over several lines
        # "(langsung disambut ...)" goes, an abbreviation like "(KKH)" stays
        text = re.sub(r"\s*\((?![A-Z0-9 .,]{1,12}\))[^)]*\)", "", "\n".join(lines), flags=re.S)
        text = re.sub(r"\s*\((?![A-Z0-9 .,]{1,12}\)).*", "", text, flags=re.S)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines:
            clean.append((spk, lines))
    return clean


def _lyrics(body, end_line):
    """Lines of a song printed after the instruction that names it; wrap-broken lines
    (starting with a small letter) are joined again."""
    i = end_line
    while i < len(body) and not body[i].rstrip().endswith("."):   # rest of the instruction
        i += 1
    out = []
    for line in body[i + 1:]:
        line = line.strip()
        if not line or line.isdigit() or line.lower().startswith(("http", "www.")):
            continue
        if line[0] in "(#~*" or SPEAKER_RE.match(line) or line.isupper():
            break
        if out and line[0].islower():
            out[-1] += " " + line
        else:
            out.append(line)
    return out


SUBPOINT_RE = re.compile(r"^([a-h])\.\s+(.+)$")
BARE_SONG_RE = re.compile(rf"\b(?P<book>{SONG_BOOKS})\s*(?P<num>\d+[a-z]?)(?:\s*:\s*(?P<verses>\d[\d\s,\-–]*))?", re.IGNORECASE)


def _subpoints(section, body, songs_seen):
    """Lettered steps inside a section, e.g. Paladosaning Sakramèn Bujana Suci:
    a. Pratélan / b. Kidung Panglarap KPJ 314: 1 "..." / c. Paladosaning Roti Pambujanan ...
    Each step is a pill with the section name on top; songs get a full-screen music sheet."""
    out = []
    for line in body:
        m = SUBPOINT_RE.match(line.strip())
        if not m:
            continue
        text = _clean(m.group(2))
        s = INLINE_SONG_RE.search(text) or BARE_SONG_RE.search(text)
        if s:
            book = re.sub(r"\s+", "", s.group("book")).upper()
            key = f"{book} {s.group('num')}"
            label = text[:s.start()].strip(" :–-") or songs_seen.get(key, ("Kidung", ""))[0]
            label = label[:1].upper() + label[1:]
            title = _clean(s.groupdict().get("title") or "") or songs_seen.get(key, ("", ""))[1]
            songs_seen[key] = (label, title)
            verses = (s.group("verses") or "").strip()
            out.append(Footer("pill", _song_main(book, s.group("num"), verses), top=label, bottom=title,
                              source=f"{section}: {m.group(1)}. {text}", layout="full",
                              song={"code": book, "num": s.group("num"), "verses": verses.replace("–", "-")}))
        else:
            name = re.split(r"\s*[➔→]\s*", text)[0].strip(" .")
            out.append(Footer("pill", name, top=section, source=f"{section}: {m.group(1)}. {text}"))
    return out


def _rows(lines):
    """Rough number of rows the lines take in a box (about 85 characters fit in one row)."""
    return sum(max(1, -(-len(l) // 85)) for l in lines)


def _boxes(section, body, known_lyrics):
    """Box footers for a section: the PF/U dialog (if the congregation answers) and
    songs sung without a song number, with their lyrics when the PDF prints them."""
    out = []
    turns = [] if re.fullmatch(READING_HEADERS, section or "", re.IGNORECASE) else _dialog(body)
    if any(s == "U" for s, _ in turns):
        paras, cur = [], []
        for spk, lines in turns:
            text = [f"{spk} : {lines[0]}"] + lines[1:]
            if spk == "U" and cur and _rows(cur) + _rows(text) <= 3:
                cur += text
            else:
                if cur:
                    paras.append(cur)
                cur = text
        if cur:
            paras.append(cur)
        out.append(Footer("box", "\n\n".join("\n".join(p) for p in paras), top=section or "Dialog",
                          bottom="dialog", include=bool(re.search(r"p[ae]ngutusan", section, re.IGNORECASE)),
                          source=f"{section}: PF / U dialog"))
    joined, starts = "", []
    for line in body:
        starts.append(len(joined))
        joined += line + " "
    for m in SUNG_RE.finditer(joined):
        if INLINE_SONG_RE.search(m.group(0)):
            continue
        title = _clean(m.group(1))
        end_line = max(i for i, s in enumerate(starts) if s < m.end())
        lyrics = _lyrics(body, end_line) or known_lyrics.get(title.lower(), [])
        if lyrics:
            known_lyrics[title.lower()] = lyrics
        out.append(Footer("box", "\n".join(lyrics), top=section or "Lagu", bottom=title, include=bool(lyrics),
                          source=f"Song “{title}”" + ("" if lyrics else " - lyrics not in the PDF, type them in")))
    return out


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
    else:   # Javanese: "Pangandikanipun Gusti badhé kaladosaken déning Bp. Pdt. Éko Iswanto."
        m = re.search(r"(?:kaladosaken|dipunladosi|kaladosan|dilayankan oleh)\s+(?:d[eé]ning\s+)?"
                      r"(?:Bp\.|Ibu|Sdr\.|Sdri\.)?\s*((?:Pdt\.|Vik\.|Pnt\.)\s*(?:Em\.\s*)?[^,.;()]+?)"
                      r"(?:,?\s+(?:saking|dari)\s+([^,;]+?))?\s*(?:[.,;](?:\s|$)|$)", full)
        if m:
            svc.preacher = _clean(m.group(1))
            svc.preacher_church = _clean(m.group(2) or "")
    if svc.preacher and not svc.preacher_church:
        # the church's own pastor: use the congregation named under the title, e.g. "Induk Murangan GKJ Medari-Sléman"
        home = next((l for l in first[1:5] if "GKJ" in l and not re.search(r"\d{4}", l)), "")
        svc.preacher_church = home

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
            entries.append((pno, l[0] + 0.01, "text", l[2]))
            for m in INLINE_SONG_RE.finditer(l[2]):
                entries.append((pno, l[0], "inline", (l[2], m)))

    entries.sort(key=lambda e: (e[0], e[1]))
    # the full text of each section (until the next blue band, also across pages)
    bodies, current = {}, None
    for n, (_, _, kind, payload) in enumerate(entries):
        if kind == "header":
            current = n
            bodies[n] = []
        elif kind == "text" and current is not None:
            bodies[current].append(payload)
    seen_songs = set()   # "KJ 413" style keys, so a song is only offered once
    known_lyrics = {}    # song title -> lyrics, for a song sung again later
    subpoint_songs = {}  # "KPJ 278" -> (label, title), for "g. KPJ 278:1" without a title
    for n, (_, _, kind, payload) in enumerate(entries):
        if kind == "text":
            continue
        if kind == "header":
            new = _classify(*payload)
            name = (new[0].main if new[0].kind == "bar" else new[0].top) if new else ""
            new += _boxes(name, bodies.get(n, []), known_lyrics)
            steps = _subpoints(name, bodies.get(n, []), subpoint_songs)
            for f in steps:
                if f.song:
                    seen_songs.add(f"{f.song['code']} {f.song['num']}")
            new += steps
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
