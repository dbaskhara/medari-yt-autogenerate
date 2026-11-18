# Medari Live Kit

Turns the weekly **Tata Ibadah** PDF of GKJ Medari-Sleman into everything OBS needs for the Sunday live stream: footers, music-sheet slides, dialog and lyrics boxes, the YouTube thumbnail and the countdown video. The app's screens are in Bahasa Indonesia.

## Weekly use

1. Double-click **`Buat Aset Live.bat`**. The app opens in your browser.
2. Drop the Tata Ibadah PDF on the page.
3. Read **Ringkasan → Perlu dicek**. It lists only what needs a look: a missing preacher photo, a song not found in the library, a verse choice that is a guess, or lyrics to type. Click **Lihat** to jump there. When it says *Semua siap dibuat*, the week is ready.
4. Optional: in **Urutan Ibadah**, click a row to open it and change its text, its type (*Judul*, *Judul + keterangan*, *Kotak teks*), or its song slides. Click a preview to see it full screen. The chips filter the list (*Perlu dicek*, *Lagu*, *Tidak dipakai*).
5. Click **Buat semua**. A progress bar shows each file. At the end you get a gallery of everything that was made.

**Where the files go**
- `output\Minggu Ini\`: always this week's files. **Point OBS at this folder once.** Its contents are replaced every week, so the OBS sources never need to change. The thumbnail and the video always have the same names (`00 - Thumbnail 1920.png`, `00 - Countdown Loop.mp4`).
- `output\<date> Footer\`: the same files kept per Sunday, plus a ZIP.
- `output\Arsip\`: generating again for the same Sunday never deletes anything. The earlier files are moved here.

**Your edits are saved automatically** in the browser for each PDF. Closing the page or opening the same PDF again brings them back. Use *Mulai lagi dari PDF* to start over.

Keep the black window open while you use the app, and close it when you're done.

**First start on a new PC:** the launcher prepares everything by itself, so it needs internet once and takes 2–5 minutes. After that the app works offline.
- If no Python 3.10+ is found, it downloads Python 3.12 from python.org and installs it for the current Windows user. No admin rights or questions are needed.
- It then installs the app's packages into a private `.venv` folder. A `.venv` copied from another PC is detected and rebuilt.

## What is read from the PDF

| PDF | Footer |
|---|---|
| Blue section header, e.g. `Votum & Salam (PF)` | **Bar**: "Votum & Salam" |
| Song header, e.g. `Pujian Pembuka: KP 7: 1-3 "Terpujilah Allah"` | **Pill**: Pujian Pembuka / KP 7: 1-3 / Terpujilah Allah |
| `Pembacaan Alkitab` → `Bacaan I …`, `Bacaan II …` | **Pill** per reading: Pembacaan Alkitab / III Yohanes 1:1-12 / Bacaan 1 |
| `Khotbah` | **Pill**: Khotbah / preacher name from "dilayankan oleh …" |
| Songs inside the text (e.g. `KJ 472 "Haleluya"`) | Offered as a pill, **unticked** |
| PF / U dialog, e.g. in `Pengutusan & Berkat` | **Box** footers: one image per PF + U pair, as on the stream. Ticked for Pengutusan; other sections with a dialog (Votum, Berita Anugerah) are offered unticked |
| Song without a number, e.g. `nyanyian "Kudaki Daki Gunung …"` | **Box** footers with the lyrics. They are read from the PDF when printed there, and reused when the song is sung again later. If the lyrics aren't in the PDF, the item is unticked and you type them in |

**Lettered steps inside any section** ("a." or "a)"), e.g. *Paladosaning Sakramèn Bujana Suci* (a. Pratélan, b. Kidung Panglarap KPJ 314: 1 …) or *Pelayanan Peletakan dan Peneguhan Penatua dan Diaken* (a) Peletakan, b) Pelepasan Stola …), each become a footer, as on the 11 Okt 2026 stream:
- a step is a pill with the section name small on top and the step big in the bar (only the top half of the pill shows);
- a song step gets its pill and its music sheet, like any other song;
- a song named again without a title (g. KPJ 278:1) takes the title from its first mention.
- a song step whose song is printed as notation ("e) Kidung Berkat" with "KJ 320. SYUKUR KAMI PADAMU") gets that song.

**Javanese services (Basa Jawa)** are read the same way. Role codes like (PP), (Prd1), (Prd3 & PP) and stage directions like (Pasamuwan Jumeneng) are removed. *Pamaosing Pangandika* gives one pill per *Waosan*, and *Panyuraosing Pangandika* gives the preacher pill. The preacher comes from "kaladosaken déning …". When the preacher is the church's own pastor, the thumbnail shows the congregation from the title page, e.g. "(Induk Murangan GKJ Medari-Sléman)". The thumbnail says "Basa Jawa" and joins the readings with ";", as in the Canva pages.

**Kotak teks (box) footers** use the rounded light box from the CorelDRAW template, with the bar behind it. On the page, a box item has a text area:
- an **empty line** starts a new box (a new image);
- longer text is wrapped and split into boxes of 3 lines by itself;
- when one speaker's text runs into the next box, that box starts with "PF : " again.

The preview shows every image the item will make.

## Design files

- `app/assets/bar.png`, `app/assets/pill.png`: footer artwork. It was rebuilt from the 15 Nov 2026 stream (`tools/build_assets.py`), because CorelDRAW could not be run here. To use the exact CorelDRAW artwork, export the bar and pill **without text** as 1920×1080 transparent PNGs with the same names and replace these files.
- `app/assets/fonts/`: Inter is included. The bar text in the template uses **Object Sans**. Put `ObjectSans-Regular.otf` (or `.ttf`) in this folder and the app uses it automatically.
- Text positions and sizes are at the top of `app/footer_render.py`.

## Music-sheet slides

For every song in the Tata Ibadah, the app:

1. finds the song's PowerPoint file in the public library *Lagu-lagu Kidung* on Google Drive (KJ, PKJ, NKB, KP, KPJ, KK, KPK). No login is needed.
2. downloads it once and keeps it in `cache\`, so a song used again is instant.
3. exports the slides with **Microsoft PowerPoint**, which must be installed on the PC.
4. pre-selects the slides for the sung verses. For `KJ 27: 1, 3` it picks the #1 and #3 slides. When verses can't be matched one-to-one, all notation slides are selected.
5. places each slide in **Frame Slide 4:3**, with the section name ("Pujian Pembuka") as the label. The camera area stays transparent for OBS.

On the page, click slide thumbnails to change the choice. Each slide shows which verse it was picked for, and *Kenapa slide ini?* explains the choice (e.g. "Ayat 1 → slide 2, ayat 3 → slide 4"). For **Pujian Pengiring Persembahan** the offering QRIS card is added (*Tampilkan QR persembahan*). Songs not found in the library show a message, and you can add your own images instead.

Output files sit next to the footers in service order: `17 - Pujian Pengiring Persembahan - KJ 450 1-4.png`, then `17a … (1 of 4).png`, `17b …`, and so on.

The QRIS image (`app/assets/qr_persembahan.png`) was rebuilt from the stream. The checksum was verified, and it reads as GKJ MEDARI MURANGAN, Sleman. If the church's QRIS changes, replace this file.

## YouTube thumbnail

The **Thumbnail & Video** panel fills the Canva design "Thumbnail Youtube 2026" from the Tata Ibadah:

- top line: "Ibadah Minggu Biasa, 15 November 2026"
- theme: big and bold. Press Enter in the box to choose where a new line starts.
- readings: Bacaan I and II
- preacher (church) on the left of the bottom bar, "08:00 WIB • Bahasa Indonesia" on the right

**Preacher photo:** the app searches the public photo folder on Google Drive (and its sub-folder *PNG PF NEW*) for the preacher's name, then shows the matching photos to click. If the preacher isn't there, use **+ Foto sendiri**. A cut-out PNG with a transparent background looks best. Use the sliders to change the photo's size and position.

You get two files: `00 - Thumbnail YouTube.jpg` (1280×720, for YouTube) and `00 - Thumbnail 1920.png` (for the slide loop in OBS).

The background is `app/assets/thumb_bg.png`: the Canva page with all text and the photo removed. If the design changes in Canva, download the empty page again as PNG and replace this file. Text positions and sizes are at the top of `app/thumb_render.py`.

## Countdown video (loop before the service)

When **Video countdown** is ticked in the thumbnail panel, *Buat semua* also makes `00 - Countdown Loop.mp4` (1920×1080, 30 fps, no sound). It plays:

thumbnail (5 s) → fade → the *Bahan Ads Mentah* video (QRIS offering + social media) → fade → thumbnail (5 s)

You can change the seconds on the page. It replaces the weekly CapCut step. In OBS, use a Media Source with "Loop" ticked.

The base video is downloaded once from the Drive folder *Bahan Ads Mentah* and kept in `cache\ads\`. If a new .mp4 is put in that folder, the app uses it within a week. To use it at once, delete `cache\ads\` and the `cache\folder_1hkltUbX40lM-OeAmB46oz9yLTZH_raCb.json` file. The video takes about 15 seconds to make.
