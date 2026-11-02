"""Bangun User Manual (halaman web + PDF) per peran dari Markdown di wiki/user-manual/.

Sumber  : wiki/user-manual/{README,pegawai,admin-unor}.md + images/
Keluaran:
  - templates/bersama/manual/<peran>_toc.html, <peran>_isi.html   (ditampilkan di halaman /user-manual/)
  - static/images/user-manual/*.png                                (gambar untuk halaman)
  - static/docs/panduan_pegawai.pdf, panduan_admin_unor.pdf        (tombol "Unduh PDF")

Jalankan ulang setiap kali Markdown manual berubah:

    pip install markdown-it-py mdit-py-plugins      # alat bantu pengembangan, bukan dependensi aplikasi
    python scripts/build_user_manual.py

Berkas keluaran dibuat otomatis; jangan diedit manual. Folder wiki/ tidak ikut image Docker
(lihat .dockerignore), karena itu hasilnya disimpan sebagai berkas statis/template di repo.
"""
import html
import re
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "wiki" / "user-manual"
PDF_DIR = ROOT / "static" / "docs"
IMG_DIR = ROOT / "static" / "images" / "user-manual"
TPL_DIR = ROOT / "templates" / "bersama" / "manual"
LOGO = ROOT / "static" / "images" / "logopu.png"

try:
    from markdown_it import MarkdownIt
    from mdit_py_plugins.anchors import anchors_plugin
except ImportError:
    sys.exit("Pasang dulu: pip install markdown-it-py mdit-py-plugins")


def slug(s: str) -> str:
    """Slug ala GitHub (sama dengan anchor yang dipakai di Markdown sumber)."""
    s = re.sub(r"[^\w\s-]", "", s.strip().lower(), flags=re.U)
    return re.sub(r"\s", "-", s)


def baca(nama: str) -> str:
    return (SRC / nama).read_text(encoding="utf-8").replace("\r\n", "\n")


PERAN = {
    "pegawai": {
        "label": "Pegawai",
        "berkas": "pegawai.md",
        "pdf": "panduan_pegawai.pdf",
        "ringkas": "mengajukan perjalanan, mengunggah dokumen, memantau progres, melaporkan PDLN, dan mengajukan pembatalan",
        "beranda": "**Beranda**",
        "buang_gambar": [],
    },
    "admin_unor": {
        "label": "Admin Unor",
        "berkas": "admin-unor.md",
        "pdf": "panduan_admin_unor.pdf",
        "ringkas": "memeriksa pengajuan dan dokumen pegawai di unit organisasinya, lalu meneruskan atau mengembalikannya",
        "beranda": "**Dasbor**",
        # Tangkapan layar bagian umum ini diambil dari akun Pegawai (sidebar/isi khusus Pegawai).
        "buang_gambar": ["umum-03-profil.png", "umum-06-profil-dokumen.png", "pegawai-00-profil-paspor.png"],
    },
}


def bagian_umum(kunci: str) -> str:
    p = PERAN[kunci]
    potongan = baca("README.md").split("\n---\n")
    # 0 judul+daftar isi, 1 pendahuluan, 2 akses/akun/profil, 3 catatan penyusun (dibuang)
    pendahuluan, akses = potongan[1], potongan[2]

    paragraf_awal = pendahuluan.split("Panduan ini bertujuan")[0].rstrip()
    pendahuluan = (
        f"{paragraf_awal}\n\n"
        f"Panduan ini membantu **{p['label']}** menjalankan tugasnya di aplikasi, langkah demi langkah: "
        f"{p['ringkas']}.\n\n"
        f"> **Catatan:** Panduan ini hanya memuat fitur untuk peran **{p['label']}**. "
        f"Peran lain tidak dibahas di sini.\n"
    )

    akses = re.sub(
        r"Anda diarahkan ke halaman utama sesuai peran:.*",
        f"Anda diarahkan ke halaman utama: {p['beranda']}.",
        akses,
    )
    if kunci == "pegawai":
        akses = re.sub(r"\n- \*\*Admin Unor\*\* melihat bagian \*\*Dokumen Penugasan\*\*[^\n]*", "", akses)
    else:
        akses = re.sub(r"\n- \*\*Pegawai\*\* melihat bagian \*\*Dokumen Kepegawaian\*\*[^\n]*", "", akses)
        # Sub-bagian "Data Paspor" hanya untuk Pegawai.
        akses = re.sub(r"#### e\. Mengelola data paspor.*?(?=\n### 2\.4)", "", akses, flags=re.S)
    for gambar in p["buang_gambar"]:
        akses = re.sub(rf"^!\[[^\]]*\]\(images/{re.escape(gambar)}\)\n?", "", akses, flags=re.M)
    akses = re.sub(r"\n{3,}", "\n\n", akses)
    return pendahuluan.strip() + "\n\n" + akses.strip() + "\n"


def bagian_peran(kunci: str) -> str:
    p = PERAN[kunci]
    pecah = re.split(r"^## 1\. ", baca(p["berkas"]), maxsplit=1, flags=re.M)
    kepala, isi = pecah[0], "## 1. " + pecah[1]
    intro = [b for b in kepala.split("\n\n") if b.strip() and not b.startswith("#") and "Daftar Isi" not in b][0]
    intro = intro.replace(
        "[Akses, Akun, dan Profil](README.md#2-akses-akun-dan-profil)",
        "[Bagian 2: Akses, Akun, dan Profil](#2-akses-akun-dan-profil)",
    )

    # Penomoran lanjutan dari README (Bab 3). Urutan penting: sub-judul dulu, baru judul bab.
    isi = re.sub(r"^### (\d)\.(\d) (.*)$", r"#### 3.\1.\2 \3", isi, flags=re.M)  # 4.1 -> 3.4.1 (Admin Unor)
    isi = re.sub(r"^## (\d+)\. (.*)$", r"### 3.\1 \2", isi, flags=re.M)
    isi = re.sub(r"^### (Langkah .*)$", r"#### \1", isi, flags=re.M)
    isi = isi.replace("[Bagian 2 pada README](README.md#2-akses-akun-dan-profil)", "[Bagian 2](#2-akses-akun-dan-profil)")
    isi = isi.replace("[Bagian 4](#4-mengusulkan-kegiatan-baru)", "[Bagian 3.4](#34-mengusulkan-kegiatan-baru)")
    isi = re.sub(r"\n---\n", "\n", isi)
    return f"## 3. Panduan Pengguna: {p['label']}\n\n{intro}\n\n{isi.strip()}\n"


def md_ke_html(kunci: str) -> str:
    """Markdown gabungan (bagian umum + bagian peran) -> HTML, gambar masih relatif `images/...`."""
    md_teks = bagian_umum(kunci) + "\n" + bagian_peran(kunci)
    md = MarkdownIt("commonmark", {"html": False, "breaks": False}).enable("table")
    md.use(anchors_plugin, min_level=2, max_level=4, slug_func=slug, permalink=False)
    isi = md.render(md_teks)

    def jadi_figure(m):
        src, alt = m.group(1), html.unescape(m.group(2))
        return f'<figure><img src="{src}" alt="{html.escape(alt)}"><figcaption>{html.escape(alt)}</figcaption></figure>'

    isi = re.sub(r'<p><img src="([^"]+)" alt="([^"]*)"\s*/?></p>', jadi_figure, isi)

    def kelas_bq(m):
        kelas = {"catatan": "catatan", "penting": "penting", "peringatan": "peringatan"}.get(m.group(2).lower().rstrip(":"), "")
        return f'<blockquote class="{kelas}">{m.group(1)}<strong>{m.group(2)}'

    return re.sub(r"<blockquote>(\s*<p>)<strong>([^<]+)", kelas_bq, isi)


def daftar_isi(isi: str) -> list[tuple[int, str, str]]:
    """[(tingkat, id, judul)] untuk H2-H3 dan H4 yang berupa langkah/nomor bab 3."""
    hasil = []
    for m in re.finditer(r'<h([234])([^>]*)id="([^"]+)"([^>]*)>(.*?)</h\1>', isi, flags=re.S):
        tingkat, ident, judul = int(m.group(1)), m.group(3), re.sub(r"<[^>]+>", "", m.group(5)).strip()
        if tingkat == 4 and not re.match(r"^(Langkah|3\.)", judul):
            continue
        hasil.append((tingkat, ident, judul))
    return hasil


def cek(dokumen: str, nama: str) -> None:
    ids = set(re.findall(r'\sid="([^"]+)"', dokumen))
    masalah = [f"anchor tidak ditemukan: #{a}" for a in set(re.findall(r'href="#([^"]+)"', dokumen)) if a not in ids]
    for src in set(re.findall(r'<img src="images/([^"]+)"', dokumen)):
        if not (SRC / "images" / src).exists():
            masalah.append(f"gambar tidak ada: {src}")
    masalah += [f"tautan non-anchor tersisa: {s}" for s in re.findall(r'href="([^"#][^"]*)"', dokumen)]
    if masalah:
        sys.exit(f"[{nama}] " + "; ".join(masalah))


# ---------------------------------------------------------------- halaman web
def ukuran_png(path: Path) -> tuple[int, int]:
    """Lebar dan tinggi PNG dari header IHDR (tanpa dependensi tambahan)."""
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit(f"Bukan berkas PNG: {path}")
    return struct.unpack(">II", data[16:24])


def tulis_fragmen(kunci: str) -> set[str]:
    isi = md_ke_html(kunci)
    cek(isi, kunci)
    if re.search(r"\{[{%#]", isi):
        sys.exit(f"[{kunci}] Markdown memuat sintaks template Django ('{{{{' / '{{%'); hindari di manual.")

    gambar = set(re.findall(r'<img src="images/([^"]+)"', isi))

    def ke_static(m):
        nama, alt = m.group(1), m.group(2)
        url = "{% static 'images/user-manual/" + nama + "' %}"
        lebar, tinggi = ukuran_png(SRC / "images" / nama)  # dipesan agar halaman tidak bergeser saat gambar dimuat
        return (f'<figure><a href="{url}" target="_blank" rel="noopener" title="Klik untuk memperbesar">'
                f'<img src="{url}" alt="{alt}" width="{lebar}" height="{tinggi}" loading="lazy"></a><figcaption>')

    isi = re.sub(r'<figure><img src="images/([^"]+)" alt="([^"]*)"><figcaption>', ke_static, isi)
    isi = isi.replace("<table>", '<div class="manual-table"><table>').replace("</table>", "</table></div>")

    toc = "".join(
        f'<li class="l{t}"><a href="#{i}">{j}</a></li>' for t, i, j in daftar_isi(isi)
    )
    TPL_DIR.mkdir(parents=True, exist_ok=True)
    kepala = "{# Dibuat otomatis oleh scripts/build_user_manual.py dari wiki/user-manual/ - jangan diedit manual. #}\n"
    (TPL_DIR / f"{kunci}_isi.html").write_text("{% load static %}\n" + kepala + isi, encoding="utf-8", newline="\n")
    (TPL_DIR / f"{kunci}_toc.html").write_text(kepala + f"<ul>{toc}</ul>\n", encoding="utf-8", newline="\n")
    return gambar


def salin_gambar(nama_gambar: set[str]) -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for nama in sorted(nama_gambar):
        tujuan = IMG_DIR / nama
        if not tujuan.exists() or tujuan.read_bytes() != (SRC / "images" / nama).read_bytes():
            shutil.copy2(SRC / "images" / nama, tujuan)


# ------------------------------------------------------------------------ PDF
CSS_PDF = """
@page { size: A4; margin: 2cm 1.8cm 2cm 1.8cm;
  @bottom-center { content: "Panduan Pengguna Paspor PU \\2014  {LABEL}  \\00b7  Halaman " counter(page);
                   font: 8pt 'Segoe UI', Arial, sans-serif; color: #6b7280; } }
@page :first { margin: 0; @bottom-center { content: none; } }
html { font: 10pt/1.5 'Segoe UI', Arial, Helvetica, sans-serif; color: #1f2937; }
body { margin: 0; }
.cover { height: 297mm; padding: 55mm 25mm 0 25mm; background: #f4f6fb; border-top: 14mm solid #1d3557;
         box-sizing: border-box; page-break-after: always; }
.cover img { height: 24mm; margin-bottom: 14mm; }
.cover h1 { font-size: 30pt; line-height: 1.15; color: #1d3557; margin: 0 0 6mm 0; }
.cover .peran { display: inline-block; background: #ffb703; color: #1d3557; font-weight: 700; font-size: 15pt;
                padding: 2mm 6mm; border-radius: 2mm; margin-bottom: 10mm; }
.cover p { font-size: 11pt; color: #475569; margin: 0 0 2mm 0; }
.toc { page-break-after: always; }
.toc h2 { font-size: 18pt; color: #1d3557; border-bottom: 2px solid #1d3557; padding-bottom: 2mm; margin-top: 0; }
.toc ul { list-style: none; margin: 0; padding: 0; }
.toc li { margin: 1.2mm 0; }
.toc li.l3 { padding-left: 6mm; font-size: 9.5pt; }
.toc li.l4 { padding-left: 12mm; font-size: 9pt; color: #475569; }
.toc li.l2 { font-weight: 700; margin-top: 3mm; }
.toc a { color: inherit; text-decoration: none; display: block; }
.toc a::after { content: leader('.') target-counter(attr(href), page); }
h2, h3, h4 { color: #1d3557; break-after: avoid; }
h2 { font-size: 16pt; border-bottom: 1.5px solid #cbd5e1; padding-bottom: 1.5mm; margin: 9mm 0 4mm; }
h2.mulai-halaman { break-before: page; margin-top: 0; }
h3 { font-size: 13pt; margin: 6mm 0 2.5mm; }
h4 { font-size: 11pt; margin: 5mm 0 2mm; }
p { margin: 0 0 2.6mm; orphans: 3; widows: 3; }
ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
li { margin: 0.8mm 0; }
a { color: #1d4ed8; text-decoration: none; }
code { font: 9pt Consolas, monospace; background: #eef1f6; padding: 0 1mm; border-radius: 1mm; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 9pt; }
th, td { border: 1px solid #cbd5e1; padding: 1.5mm 2.2mm; text-align: left; vertical-align: top; }
th { background: #e8edf5; color: #1d3557; }
tr { break-inside: avoid; }
blockquote { margin: 3mm 0 4mm; padding: 2.5mm 4mm; background: #f1f5f9; border-left: 1.2mm solid #64748b; break-inside: avoid; }
blockquote p { margin: 0; }
blockquote.penting, blockquote.peringatan { background: #fff4e5; border-left-color: #e08a00; }
blockquote.catatan { background: #eaf3ff; border-left-color: #2563eb; }
figure { margin: 3mm 0 5mm; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 15.5cm; border: 1px solid #cbd5e1; }
figcaption { font-size: 8pt; color: #64748b; margin-top: 1mm; font-style: italic; }
"""


def html_pdf(kunci: str) -> str:
    p = PERAN[kunci]
    isi = md_ke_html(kunci)
    cek(isi, kunci)
    bab3 = f"3-panduan-pengguna-{slug(p['label'])}"
    isi = isi.replace(f'<h2 id="{bab3}">', f'<h2 class="mulai-halaman" id="{bab3}">')
    item = "".join(f'<li class="l{t}"><a href="#{i}">{j}</a></li>' for t, i, j in daftar_isi(isi))
    cover = (
        f'<section class="cover"><img src="{LOGO.as_uri()}" alt="">'
        f"<h1>Buku Panduan Pengguna<br>Paspor PU</h1>"
        f'<div class="peran">Peran: {p["label"]}</div>'
        f"<p>Platform Administrasi Surat Perjalanan Overseas Request</p>"
        f"<p>Kementerian Pekerjaan Umum &middot; Biro Perencanaan Anggaran dan Kerja Sama Luar Negeri</p>"
        f"<p>Oktober 2026</p></section>"
    )
    return (
        f'<!doctype html><html lang="id"><head><meta charset="utf-8">'
        f'<title>Panduan Pengguna Paspor PU - {p["label"]}</title><style>{CSS_PDF.replace("{LABEL}", p["label"])}</style></head>'
        f'<body>{cover}<section class="toc"><h2>Daftar Isi</h2><ul>{item}</ul></section>{isi}</body></html>'
    )


def tulis_pdf(kunci: str) -> Path:
    from weasyprint import HTML

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    tujuan = PDF_DIR / PERAN[kunci]["pdf"]
    HTML(string=html_pdf(kunci), base_url=SRC.as_uri() + "/").write_pdf(tujuan)
    return tujuan


def main() -> None:
    gambar: set[str] = set()
    for kunci in PERAN:
        gambar |= tulis_fragmen(kunci)
        print(f"[{kunci}] halaman web -> {TPL_DIR / (kunci + '_isi.html')}")
    salin_gambar(gambar)
    print(f"{len(gambar)} gambar -> {IMG_DIR}")
    for kunci in PERAN:
        pdf = tulis_pdf(kunci)
        print(f"[{kunci}] PDF -> {pdf} ({pdf.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
