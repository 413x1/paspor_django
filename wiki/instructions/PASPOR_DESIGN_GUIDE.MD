# PASPOR Design Guide

> **Tujuan:** satu acuan tampilan agar setiap halaman PASPOR terasa sebagai satu
> aplikasi — warna, tipografi, layout, tombol, komponen, ikon, gerak, dan bahasa.
> **Sumber kebenaran:** `static/css/style.css` (lapisan tema di atas Bulma 1.x)
> dan `templates/base.html` + `templates/partials/`. Panduan ini mendokumentasikan
> apa yang **sudah ada**, lalu menetapkan aturan untuk pekerjaan berikutnya.
> **Audiens:** pengembang & perancang yang menambah/mengubah halaman.

---

## Daftar Isi

1. [Prinsip](#1-prinsip)
2. [Fondasi Teknis](#2-fondasi-teknis)
3. [Warna](#3-warna)
4. [Tipografi](#4-tipografi)
5. [Spasi, Radius, Bayangan](#5-spasi-radius-bayangan)
6. [Layout](#6-layout)
7. [Anatomi Halaman](#7-anatomi-halaman)
8. [Tombol](#8-tombol)
9. [Form](#9-form)
10. [Badge & Status](#10-badge--status)
11. [Umpan Balik (Pesan, Dialog, Toast)](#11-umpan-balik-pesan-dialog-toast)
12. [Tabel & DataTables](#12-tabel--datatables)
13. [Komponen Domain](#13-komponen-domain)
14. [Modal & Lapisan (z-index)](#14-modal--lapisan-z-index)
15. [Ikon](#15-ikon)
16. [Gerak (Motion)](#16-gerak-motion)
17. [Aksesibilitas](#17-aksesibilitas)
18. [Bahasa & Penulisan](#18-bahasa--penulisan)
19. [Inkonsistensi Saat Ini & Rencana Perbaikan](#19-inkonsistensi-saat-ini--rencana-perbaikan)
20. [Checklist Sebelum Merge](#20-checklist-sebelum-merge)

---

## 1. Prinsip

1. **Formal, tenang, terpercaya.** Aplikasi pemerintah untuk proses perizinan —
   tampilan bersih, warna hemat, tanpa dekorasi berlebihan.
2. **Status selalu jelas.** Pengguna harus langsung tahu: pengajuan sedang di
   siapa, apa yang kurang, dan apa langkah berikutnya.
3. **Satu pola untuk satu kebutuhan.** Gunakan komponen yang sudah ada sebelum
   membuat yang baru. Komponen baru masuk ke `style.css`, bukan inline.
4. **Token, bukan angka lepas.** Warna, durasi, dan radius memakai variabel CSS.
5. **Aksi berbahaya selalu dikonfirmasi** dan tampil berbeda dari aksi biasa.

---

## 2. Fondasi Teknis

| Lapisan | File | Peran |
|---|---|---|
| Framework | `static/vendors/bulma/css/versions/bulma-no-dark-mode.min.css` (Bulma 1.x, tanpa dark mode) | Struktur: `box`, `button`, `field`, `table`, `modal`, `notification`, `tag`, `columns` |
| Tema | `static/css/style.css` | Token warna/gerak, override variabel Bulma, komponen khas PASPOR |
| Kerangka | `templates/base.html` | Shell aplikasi, modal bersama, dialog, perilaku JS global |
| Partial | `templates/partials/_*.html` | Komponen tampilan yang dipakai ulang |
| Tabel | `static/vendors/datatables/` | DataTables server-side |

Aturan:

- **Selalu naikkan versi cache-busting** saat mengubah `style.css`:
  `{% static 'css/style.css' %}?v=YYYYMMDDx` di `base.html` (dan `registration/login.html`).
- **Tidak ada CSS inline baru** kecuali nilai yang benar-benar unik per elemen.
  Pola berulang → kelas di `style.css` (lihat [§19](#19-inkonsistensi-saat-ini--rencana-perbaikan)).
- **Tidak ada `<style>` per template** kecuali untuk halaman cetak/PDF
  (`pakln/pdf_template_*.html`, `pakln/generate_nd_*.html`).
- Perilaku interaktif memakai atribut deklaratif yang sudah tersedia di `base.html`
  (`data-confirm`, `data-modal-open`, `data-modal-close`, `data-dropdown-toggle`,
  `data-doc-preview`) — jangan menulis ulang JS yang sama per halaman.

---

## 3. Warna

### 3.1 Palet (token di `:root`)

| Token | Nilai | Peran |
|---|---|---|
| `--navy-900` | `#1d3557` | **Warna utama.** Judul, tombol primer, paginasi aktif, teks tegas |
| `--navy-800` | `#27406b` | Hover tombol primer |
| `--navy-700` | `#374774` | Latar sidebar & topbar (`--sidebar-bg`) |
| `--teal` | `#24819b` | Tautan, fokus input, aksen informasi |
| `--gold` | `#ffbd12` | **Aksen aksi.** Tombol "tindak lanjut", badge sidebar, avatar |
| `--gold-600` | `#e8a400` | Hover tombol gold |
| `--gold-dark` | `#8a5a00` | Teks di atas `--gold-bg` |
| `--gold-bg` | `#fff4d6` | Latar peringatan / "sedang diproses" |
| `--green` | `#2f9e64` | Sukses, selesai, dokumen terunggah |
| `--green-bg` | `#e5f6ec` | Latar sukses |
| `--blue-bg` | `#e6f1fb` | Latar informasi, chip, pernyataan (`agree-box`) |
| `--slate-900` | `#1f2430` | Teks isi utama |
| `--slate-600` | `#4a5163` | Teks sekunder, label tombol netral |
| `--slate-400` | `#7a8194` | Teks redup (keterangan, waktu, placeholder) |
| `--line` | `#d7dbe3` | Garis, border kartu & input |
| `--bg` | `#f4f6fb` | Latar halaman, kepala tabel, field readonly |
| `--white` | `#ffffff` | Latar kartu |

### 3.2 Token tambahan

Ditambahkan untuk menggantikan hex yang sebelumnya ditulis langsung
(`#c0392b`, `#dc2626`, `#e0453c`, `#fdecea`, `#5e35b1`, …). Gunakan token ini;
jangan menulis hex baru.

| Token | Nilai | Peran |
|---|---|---|
| `--red` | `#c0392b` | Teks error, status dibatalkan, penanda wajib (`.text-danger`) |
| `--red-strong` | `#dc2626` | Tombol/ikon destruktif, badge notifikasi |
| `--red-hover` | `#b91c1c` | Hover tombol destruktif |
| `--red-bg` | `#fdecea` | Latar error/destruktif |
| `--red-line` | `#f3c6c2` | Border kotak destruktif (`.box.is-danger-soft`) |
| `--purple` | `#5e35b1` | Status "Dalam Proses BPSDM" |
| `--purple-bg` | `#ede7f6` | Latar status BPSDM |
| `--neutral-bg` | `#eceff3` | Latar status "Belum Diajukan", badge opsional |
| `--blue-line` | `#cfe0f2` | Border kotak informasi (`.agree-box`, `.box.is-info-soft`) |
| `--teal-dark` | `#1c6a80` | Hover tombol info |
| `--green-dark` | `#1e6b41` | Teks di atas `--green-bg` |
| `--green-hover` | `#278553` | Hover tombol sukses |

Pengecualian yang disengaja: warna "Keluar" di sidebar (`rgba(239,68,68,.15)` /
`#f87171`) dioptimalkan untuk latar gelap sidebar.

### 3.3 Makna warna (semantik)

| Makna | Latar | Teks/Aksen | Contoh |
|---|---|---|---|
| Primer / navigasi | `--navy-900` | `--white` | Tombol simpan, paginasi aktif |
| Perlu tindakan | `--gold` / `--gold-bg` | `--navy-900` / `--gold-dark` | Tombol "TL →", kartu "Perlu Tindakan Saya" |
| Informasi | `--blue-bg` | `--teal` / `--navy-900` | Badge "Wajib", catatan perbaikan |
| Sukses / selesai | `--green-bg` | `--green` | Dokumen terunggah, status Selesai |
| Bahaya / dibatalkan | `--red-bg` | `--red` | Kembalikan, Hapus, Hentikan, Dibatalkan |
| Netral / nonaktif | `--neutral-bg` | `--slate-600` | Belum Diajukan, opsional |

Aturan:

- **Gold = ajakan bertindak, bukan peringatan bahaya.** Bahaya selalu merah.
- Maksimal **satu** tombol primer (navy) dan **satu** tombol gold per area aksi.
- Teks di atas latar berwarna memakai pasangan dari tabel di atas, bukan hitam.

### 3.4 Warna status pengajuan

Satu status = satu warna di seluruh aplikasi (`.tag.paspor-status.is-<status>`):

| Status | Label | Latar | Teks |
|---|---|---|---|
| `belum` | Belum Diajukan | `--neutral-bg` | `--slate-600` |
| `proses` | Dalam Proses Unor | `--gold-bg` | `--gold-dark` |
| `proses_bpsdm` | Dalam Proses BPSDM | `--purple-bg` | `--purple` |
| `proses_pakln` | Dalam Proses Biro PAKLN | `--blue-bg` | `--teal` |
| `selesai` | Selesai | `--green-bg` | `--green` |
| `dibatalkan` | Dibatalkan | `--red-bg` | `--red` |

Status track Admin BKO (`.tag.bko-status`): `menunggu` biru, `diunggah` hijau, `ditutup` gold.

---

## 4. Tipografi

### 4.1 Font

`-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif` (font sistem,
lewat `--bulma-family-primary`). Tidak memuat web font — cepat dan terbaca di
semua perangkat kantor. Dokumen PDF yang digenerate memakai **Arial** (lihat
template PDF), terpisah dari UI.

### 4.2 Skala

Saat ini ada 15 ukuran berbeda (10–30px). **Gunakan hanya skala berikut** untuk
pekerjaan baru; ukuran lain dibulatkan ke yang terdekat saat disentuh.

| Peran | Ukuran | Berat | Warna | Kelas/elemen yang ada |
|---|---|---|---|---|
| Angka ringkasan | 30px | 800 | `--navy-900` | `.summary-card .num` |
| Judul halaman | 20px | 800 | `--navy-900` | `.page-head h2`, `.login-card h2` |
| Judul bagian | 18px | 800 | `--navy-900` | `.section-title` |
| Sub-judul bagian | 14px | 800 | `--navy-900` | `.section-title` kecil (kini inline `font-size:14px`) |
| Judul item | 14.5px | 700 | `--slate-900` | `.doc-row h4`, `.timeline h4` |
| Isi / input | 14px | 400 | `--slate-900` | `body`, `.input` |
| Isi tabel | 13.5px | 400 | `--slate-900` | `.table.data-table` |
| Label & isi kecil | 13px | 700 / 400 | `--slate-900` / `--slate-600` | `.label`, `.agree-box label` |
| Keterangan | 12.5px | 400 | `--slate-400` | `.doc-row p`, `.timeline p` |
| Bantuan / meta | 12px | 400 | `--slate-400` | `.helptext`, `.cell-muted` |
| Kepala tabel | 11.5px | 700, UPPERCASE, `letter-spacing .03em` | `--slate-600` | `.table.data-table th` |
| Badge | 10–11px | 700 | sesuai badge | `.badge-auto`, `.paspor-role` |

Aturan:

- Berat yang dipakai hanya **400, 500 (menu), 600, 700, 800**.
- Judul memakai `--navy-900`, bukan hitam.
- `UPPERCASE` hanya untuk kepala tabel, label grup sidebar, dan label grup notifikasi.
- Jangan memakai `<h1>`–`<h6>` Bulma (`.title`, `.subtitle`); pakai kelas di atas.
- Angka & tanggal: format Indonesia — `d M Y` (`07 Okt 2026`), jam `H:i`.

---

## 5. Spasi, Radius, Bayangan

### 5.1 Spasi

Skala dasar 4px. Nilai yang dipakai: **4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 28**.

| Konteks | Nilai |
|---|---|
| Padding halaman (`.page-wrap`) | 24px 28px 60px (mobile 20px 16px 48px) |
| Padding kartu (`.box`) | 22px |
| Jarak antar kartu | 20px (`.box` margin-bottom, `gap` grid) |
| Jarak antar field | 16px |
| Jarak tombol dalam grup | 8–10px |
| Jarak judul bagian → isi | 16px |

### 5.2 Radius

| Token / nilai | Dipakai untuk |
|---|---|
| 4px | Item menu sidebar, badge sidebar |
| 8px (`--bulma-radius-small`) | Input, select, tombol kecil DataTables |
| 10px (`--bulma-radius`) | Tombol, pesan, toast |
| 12px | Baris dokumen, opsi pilihan |
| 14px (`--radius`) | Kartu, tabel, dropdown |
| 16–18px | Modal kecil, kartu login |
| 999px | Pill: status, badge, chip |

### 5.3 Bayangan

Hanya satu bayangan: `--shadow` (`0 10px 30px rgba(29,53,87,.12)`) untuk elemen
**mengambang** (dropdown, toast, modal, kartu login). Kartu biasa **tanpa
bayangan** — cukup border `--line`.

---

## 6. Layout

### 6.1 Kerangka aplikasi

```
┌──────────────┬──────────────────────────────────────────────┐
│              │ .app-header (sticky, tinggi 72px, putih)      │
│ .app-sidebar ├──────────────────────────────────────────────┤
│ (fixed,      │ .page-wrap                                    │
│  280px,      │   breadcrumb                                  │
│  navy-700)   │   pesan flash                                 │
│              │   konten (lebar penuh / fluid)                │
└──────────────┴──────────────────────────────────────────────┘
```

| Variabel | Nilai |
|---|---|
| `--sidebar-w` | 280px |
| `--header-h` | 72px |

- Konten **fluid** (mengisi lebar di samping sidebar). Kelas lama `narrow`
  / `medium` pada `wrap_extra_class` tidak lagi membatasi lebar.
- Sidebar dapat diciutkan di desktop (`body.sidebar-collapsed`) dan menjadi
  laci (drawer) di ≤1023px (`body.sidebar-open` + `.sidebar-overlay`).

### 6.2 Breakpoint

| Lebar | Perubahan |
|---|---|
| ≤1100px | `.preview-split` menjadi 1 kolom |
| ≤1023px | Sidebar menjadi drawer; header padding 16px |
| ≤800px | `.summary-grid` 2 kolom |
| ≤700px | `.field-readonly-grid` 1 kolom |
| ≤640px | Teks user di header disembunyikan; toolbar/footer DataTables bertumpuk |
| ≤500px | Dropdown notifikasi & toast selebar layar |

Untuk breakpoint baru, **pakai salah satu nilai di atas**.

### 6.3 Grid yang tersedia

| Kelas | Kolom | Untuk |
|---|---|---|
| `.preview-split` | 2 kolom sama lebar | Pratinjau (data pengajuan ‖ dokumen), aksi ‖ riwayat |
| `.summary-grid` / `.summary-grid.is-wide` | 4 kolom / auto-fit min 150px | Kartu ringkasan dasbor |
| `.field-readonly-grid` | 2 kolom | Data read-only (ringkasan pengajuan) |
| `.columns` / `.column` (Bulma) | bebas | Form multi-kolom |
| `.kv-list` | label ‖ nilai | Daftar kunci–nilai ringkas |

---

## 7. Anatomi Halaman

Setiap halaman memakai `{% extends "base.html" %}` dan mengikuti salah satu pola.

### 7.1 Dasbor / daftar

```
.page-head            → h2 judul + p.sub keterangan    [tombol sekunder kanan]
.section-title        → "Ringkasan Progres"
.summary-grid         → kartu ringkasan (partials/_ringkasan_dasbor.html)
.box                  → .section-title + .table-wrap > table.data-table (DataTables)
```

### 7.2 Pratinjau (tinjau sebelum memproses)

```
banner status (partials/_status_bko.html, catatan pengembalian, pembatalan)
.preview-split
  .box  → .section-title + status tag + partials/_ringkasan_pengajuan.html
  .box  → partials/_direktori_dokumen.html + agree-box + tombol lanjut
.preview-split
  .box.is-danger-soft → aksi kembalikan (form + catatan wajib)
  partials/_riwayat_pengajuan.html
tombol kembali (is-fullwidth)
```

### 7.3 Unggah / administrasi

```
banner (dibekukan, catatan pengembalian)
.box  → template dokumen tersedia (opsional)
.box  → .section-title + partials/_dokumen_tahap.html + agree-box + tombol teruskan
partials/_riwayat_pengajuan.html
baris tombol kembali (2 tombol flex:1)
```

### 7.4 Elemen pembuka

- **`.page-head`** — dipakai di halaman level menu (dasbor, daftar). Judul 20px,
  keterangan `.sub` 13px, tombol di kanan.
- **`.section-title`** — judul di dalam `.box`. Sub-judul di dalamnya:
  `.section-title.is-small` (14px); tambah `.is-spaced` bila perlu jarak bawah 14px.
- **Keterangan di bawah judul** — `<p class="sub is-title-sub">` di bawah
  `.section-title`, `<p class="cell-muted is-title-sub">` di bawah
  `.section-title.is-small`.
- **Baris tombol sama lebar** (mis. "← Kembali ke Pratinjau" + "Kembali ke
  Dasbor") — `<div class="button-row">`.
- Breadcrumb otomatis dari `pengajuan/breadcrumbs.py` — **daftarkan setiap
  halaman baru** di `CRUMBS`.

---

## 8. Tombol

### 8.1 Varian

| Varian | Kelas | Tampilan | Kapan |
|---|---|---|---|
| Primer | `button is-primary` | Navy, teks putih | Aksi utama yang menyimpan/melanjutkan: Simpan, Lanjutkan, Kirim |
| Aksi alur | `button is-warning` | Gold, teks navy | Meneruskan/menyelesaikan proses: Teruskan ke…, Selesaikan Proses, TL → |
| Sekunder | `button` | Putih, border `--line`, teks `--slate-600` | Kembali, Batal, Lihat, Pratinjau, Unduh |
| Bahaya | `button is-danger` | Merah, teks putih | Aksi final/destruktif: Hapus, Kembalikan, Tutup Pemrosesan, Hentikan |
| Bahaya lunak | `button is-danger is-light` | Latar merah muda, teks merah | Aksi negatif yang tidak final: Tolak, Ajukan Pembatalan |
| Sukses | `button is-success` | Hijau, teks putih | Persetujuan/verifikasi: Verifikasi Laporan |
| Info | `button is-info` | Teal, teks putih | Aksi khusus fitur yang perlu dibedakan dari alur utama: Pelaporan PDLN |
| Info lunak | `button is-info is-light` | Latar biru muda, teks teal | Tautan pendukung: Lihat Detail |
| Tab aktif | `button is-active` di `.tab-bar` | Navy | Tab filter (PDLN / Non-Kedinasan) |

Aturan tombol sekunder memakai `:where()` sehingga spesifisitasnya rendah;
varian di atas selalu menang **tanpa `!important`**. Jangan membuat kelas warna
tombol per halaman (seperti `btn-pelaporan-*` yang sudah dihapus).

### 8.2 Ukuran & lebar

| Kelas | Pakai di |
|---|---|
| `is-small` | Dalam tabel, baris dokumen, header kartu, aksi sekunder |
| (default) | Form, kepala halaman |
| `is-fullwidth` | Tombol aksi utama di akhir kartu proses; tombol kembali di bawah halaman |

### 8.3 Aturan

- **Label = kata kerja + objek**, Bahasa Indonesia: "Teruskan ke Admin BPSDM",
  "Kembalikan ke Admin Unor", "Unggah", "Simpan". Hindari "OK", "Submit".
- Arah alur memakai panah teks: maju `→` di akhir ("Lanjutkan →"), kembali `←`
  di awal ("← Kembali ke Dasbor"), kembalikan `↩` di awal.
- Urutan dalam satu baris: sekunder (Batal) di **kiri**, primer di **kanan**
  (`.actions-bar` rata kanan).
- Tombol aksi alur **dinonaktifkan** (`disabled`) bila prasyarat belum
  terpenuhi, disertai `.helptext` yang menyebut apa yang kurang.
- **Aksi destruktif atau tak bisa dibatalkan wajib konfirmasi** deklaratif:

  ```html
  <form method="post"
        data-confirm="Kembalikan pengajuan ini ke Admin Unor beserta catatan?"
        data-confirm-title="Kembalikan Pengajuan"
        data-confirm-ok="Kembalikan"
        data-confirm-type="danger">   <!-- danger | warning (default) | info -->
  ```
- Kelompok tombol sejajar: `.buttons` (Bulma) atau `.table-actions` (dalam sel tabel).

---

## 9. Form

| Elemen | Pola |
|---|---|
| Field | `<div class="field"><label class="label">…</label><div class="control">…</div></div>` |
| Input | `input.input`, `textarea.textarea`, `div.select > select` |
| Bantuan | `p.helptext` di bawah control |
| Error | `.errorlist` / `.help.is-danger` (merah, 13px) |
| Readonly | `input[readonly]` → latar `--bg`, teks `--slate-600` |
| Wajib/opsional | Badge di label: `.badge-auto` "Wajib", `.badge-auto.is-optional` "Opsional" |
| Pernyataan | `.agree-box` (checkbox + label) sebelum tombol kirim/teruskan |
| Pilih banyak | `.multiselect` (chip + panel pencarian), mis. Tujuan Negara |
| Tanggal | `input[type=date]` — ikon kalender di kanan otomatis |
| Unggah berkas (baris dokumen) | `partials/_dokumen_tahap.html`: komponen `.file.is-small` berikon unggah, label "Unggah"/"Ganti"; berkas langsung terunggah saat dipilih; modal Tanggal Surat otomatis bila `data-tanggal-surat="1"` |
| Unggah berkas (field form) | `{% include "partials/_input_berkas.html" with field=form.file %}` — widget `forms.FileInput(attrs={"class": "file-input", ...})` (bukan `ClearableFileInput`, agar tidak muncul teks bawaan "Currently/Clear"); tombol "Pilih berkas" berikon + nama berkas terpilih; tinggi, huruf (14px), dan radius (8px) sama dengan `.input` |

Aturan:

- Label 13px tebal, **di atas** input (bukan di samping).
- Fokus: border `--teal` + cincin `rgba(36,129,155,.25)` — jangan dihilangkan.
- Validasi utama di **server**; tampilkan error di dekat field + pesan ringkas di atas.
- Catatan pengembalian/penutupan: `textarea` 3 baris, `required`, label menyebut
  **siapa yang akan membaca** ("Catatan untuk Admin Unor").
- Unggahan dokumen: **PDF saja**, ukuran **maks. 2 MB**; khusus **Dokumen Laporan
  PDLN maks. 10 MB**. Template Dokumen (PDF/DOCX) dan impor kalender (XLSX/CSV)
  juga maks. 2 MB. Validasi server di `paspor/validators.py` (`validate_pdf`,
  `validate_pdf_laporan`, `validate_ukuran`, `periksa_pdf`); di browser lewat
  atribut `data-max-mb` pada input (`berkasUkuranValid` di `base.html`). Sebutkan
  batasnya di label field, mis. "Berkas PDF (maks. 2 MB)".
- **Jangan menampilkan input berkas native** (tombol "Choose File" bawaan browser):
  selalu pakai komponen `.file` dengan ikon `partials/_ikon_unggah.html`.

---

## 10. Badge & Status

| Komponen | Kelas | Bentuk | Kapan |
|---|---|---|---|
| Status pengajuan | `.tag.paspor-status.is-<status>` + `<span class="dot">` | Pill 12px tebal + titik | Di tabel & kepala pratinjau — [§3.4](#34-warna-status-pengajuan) |
| Status BKO | `.tag.bko-status.is-<status_bko>` (`partials/_status_bko.html` `badge=True`) | Pill 11.5px | Di samping status pengajuan T2P |
| Status kegiatan | `.tag.kegiatan-status.is-menunggu/disetujui/ditolak/nonaktif` | Pill 11.5px | Daftar & detail Kegiatan, usulan kegiatan |
| Wajib / opsional | `.badge-auto` / `.badge-auto.is-optional` | Pill 10px | Di judul dokumen/field |
| Badge menu | `.sidebar-badge` | Kotak gold | Jumlah tindakan di sidebar |
| Peran | `.paspor-role` | Kotak kecil | Label peran user |
| Segera hadir | `.soon-tag` | Kotak abu | Opsi yang belum tersedia |

Jangan membuat warna status baru di template; tambahkan modifier di `style.css`.

---

## 11. Umpan Balik (Pesan, Dialog, Toast)

| Kebutuhan | Komponen | Catatan |
|---|---|---|
| Hasil aksi (sukses) | `messages.success` → otomatis tampil sebagai **dialog sukses** (`data-flash-success`) | Kalimat lengkap: "Pengajuan PLN01-… diteruskan ke Admin BPSDM." |
| Hasil aksi (gagal) | `messages.error` → `.notification.paspor-msg.is-danger` | Sebut apa yang kurang + cara memperbaiki |
| Banner kondisi halaman | `.notification.paspor-msg.is-warning` / `.is-info` / `.is-success` | Catatan pengembalian, dibekukan, pembatalan diproses |
| Konfirmasi / pemberitahuan dari JS | `#pasporDialog` via `data-confirm`, atau `pasporConfirm({title, message, confirmText, cancelText, type})` / `pasporAlert({...})` (keduanya mengembalikan `Promise`) | Ikon & warna tombol mengikuti `type` (`danger`, `warning`, `success`, `info`) |
| Notifikasi sistem | Toast kanan atas + lonceng (Notification Center) | Dikirim dari `notifications/services.py` |

Aturan:

- Banner diawali simbol + teks tebal: `<strong>⚠ Dikembalikan oleh Admin PKLN:</strong> …`.
- Satu jenis informasi = satu banner; jangan menumpuk banner yang sama.
- Warna banner: `is-warning` gold (perlu perhatian), `is-info` biru (informasi
  netral, mis. catatan perbaikan), `is-success` hijau, `is-danger` merah.

---

## 12. Tabel & DataTables

Struktur standar:

```html
<div class="box">
  <div class="section-title">Judul Tabel</div>
  <div class="table-wrap">
    <table id="dashboardTable" class="table data-table is-fullwidth is-hoverable" style="width:100%;">
      <thead><tr><th>…</th></tr></thead><tbody></tbody>
    </table>
  </div>
</div>
```

Konfigurasi DataTables yang seragam:

```js
{
  serverSide: true, processing: true, autoWidth: false,
  pageLength: 10, lengthMenu: [10, 25, 50, 100],
  dom: '<"dt-toolbar"lf>rt<"dt-footer"ip>',
  language: {
    search: '', searchPlaceholder: 'Cari pengajuan...', lengthMenu: 'Tampilkan _MENU_ pengajuan',
    info: 'Menampilkan _START_–_END_ dari _TOTAL_ pengajuan', infoEmpty: 'Belum ada pengajuan',
    infoFiltered: '(disaring dari _MAX_)', zeroRecords: 'Tidak ada pengajuan yang cocok.',
    processing: 'Memuat…', paginate: { previous: '‹ Sebelumnya', next: 'Berikutnya ›' },
  },
}
```

Aturan:

- Kolom pertama: identitas (nama tebal + NIP/kode `.cell-muted` di bawahnya).
- Kolom terakhir: **Action** — satu tombol `is-small` (`is-warning` "TL →" bila
  perlu tindakan, `button` "Lihat" bila tidak) atau teks `.cell-muted`
  ("Menunggu Admin Unor").
- Kolom status: `.tag.paspor-status` (+ badge BKO bila relevan).
- Tanggal di sel: `07 Okt 2026`; nilai kosong `—`.
- HTML dari server dibangun dengan `format_html` (dengan argumen) atau
  `escape`; teks statis tanpa variabel pakai `mark_safe`.
- Filter tambahan di atas tabel: `.filter-bar` (field berjajar, rata bawah).

---

## 13. Komponen Domain

| Komponen | Kelas / partial | Pakai untuk |
|---|---|---|
| Kartu ringkasan | `.summary-card` (`.active` gold, `.is-done` hijau) | Angka di dasbor |
| Baris dokumen | `.doc-row` (`.uploaded` hijau) — `partials/_dokumen_tahap.html` | Satu persyaratan dokumen + aksi unggah/pratinjau/hapus |
| Direktori dokumen | `partials/_direktori_dokumen.html` | Dokumen tahap sebelumnya (read-only) |
| Ringkasan pengajuan | `partials/_ringkasan_pengajuan.html` (`.field-readonly-grid`) | Data pegawai & pengajuan read-only |
| Timeline proses | `.timeline` + `.dot-wrap.done/current/upcoming/cancelled`, `.timeline-sub` | Tahap pengajuan + sub-status BKO |
| Riwayat | `.riwayat-list` + `.riwayat-pesan` — `partials/_riwayat_pengajuan.html` | Kejadian & catatan per tahap |
| Kotak aksi | `.box.is-danger-soft` / `.box.is-warning-soft` / `.box.is-info-soft` | Aksi kembalikan/tutup/hentikan; peringatan; informasi (mis. template dokumen tersedia) |
| Teks merah | `.text-danger` (`.is-strong` untuk tebal) | Penanda wajib `*`, peringatan singkat ("Terlambat") |
| Kartu cuti | `.cuti-card` | Sisa cuti pegawai |
| Opsi pilihan | `.jenis-option` (`.active`, `.disabled`) | Modal pilih jenis perjalanan |
| Tab | `.tab-bar` + `.button.is-small.is-active` | Filter tab |
| Dropdown aksi | `.table-head-actions` + `.table-head-menu` | Aksi batch di kepala tabel |
| Baris dasar kegiatan | `.dasar-row` (formset, `templates/kegiatan/_dasar_row.html`) / `.dasar-list` (read-only) | Dasar kegiatan: surat, tautan, PINTAR, lainnya + berkas opsional |

Sebelum membuat komponen baru, cek tabel ini dan `templates/partials/`.

---

## 14. Modal & Lapisan (z-index)

| Lapisan | z-index |
|---|---|
| Dropdown di konten | 20–30 |
| Header (`.app-header`) | 40 |
| Overlay & dropdown header | 45 |
| Sidebar | 50 |
| Modal (`.modal`) & toast | 60 |
| Dialog konfirmasi (`.paspor-dialog`) | 70 |

Jenis modal:

| Modal | Kelas | Lebar |
|---|---|---|
| Pilihan / form kecil | `.modal.paspor-modal` | maks 400px |
| Pratinjau dokumen (bersama) | `#docPreviewModal` + `.doc-preview-card` — buka dengan `data-doc-preview="URL"` | 960px |
| Konfirmasi / notifikasi | `#pasporDialog` (`.paspor-dialog`) — lewat `data-confirm` | sedang, teks rata tengah |

Aturan: modal selalu menutupi sidebar; tutup dengan tombol ×, "Tutup", klik
latar, atau `Esc`. Jangan membuat modal pratinjau sendiri — pakai yang bersama.

---

## 15. Ikon

Saat ini ada dua sistem: **SVG garis** (sidebar, lonceng, dialog) dan
**emoji/simbol** di konten.

| Konteks | Gunakan |
|---|---|
| Navigasi sidebar, header, dialog | SVG garis 18px, `stroke-width 1.8`, `stroke: currentColor` |
| Tombol pilih/unggah berkas | SVG `partials/_ikon_unggah.html` (`.ikon-unggah`, 16px; 14px pada `.file.is-small`) |
| Label tombol & banner | Simbol baku di bawah, **sebelum** teks, dipisah spasi |

Simbol baku (jangan memakai varian lain untuk makna yang sama):

| Makna | Simbol |
|---|---|
| Unggah / ganti | ⬆ |
| Unduh | ⬇ |
| Pratinjau | 👁 |
| Hapus | 🗑 |
| Template / dokumen | 📄 |
| Tanggal | 📅 |
| Peringatan / dikembalikan | ⚠ |
| Kembalikan | ↩ |
| Perbaikan / buka kembali | ↻ |
| Sukses / selesai | ✓ |
| Batal / pembatalan | ✕ |
| Ditutup | ■ |
| Maju / kembali | → / ← |

Jangka panjang: ganti emoji di tombol dengan SVG dari satu set (mis. Lucide/
Feather, gaya garis sama dengan sidebar) agar tampil sama di semua OS.

---

## 16. Gerak (Motion)

| Token | Nilai | Pakai untuk |
|---|---|---|
| `--duration-instant` | 100ms | Tekan tombol (`scale(.96)`) |
| `--duration-fast` | 150ms | Hover, dropdown, chevron |
| `--duration-base` | 250ms | Modal, toast |
| `--duration-slow` | 350ms | Sidebar buka/tutup |
| `--ease-apple` | `cubic-bezier(.32,.72,0,1)` | Default semua transisi |
| `--ease-apple-in-out` | `cubic-bezier(.65,0,.35,1)` | Perpindahan besar (sidebar) |
| `--ease-spring` | `cubic-bezier(.17,.89,.32,1.28)` | Hanya elemen kecil (switch/checkbox), sangat terbatas |

Aturan: gerak halus tanpa pantulan; selalu sediakan fallback
`@media (prefers-reduced-motion: reduce)` untuk animasi dekoratif.

---

## 17. Aksesibilitas

- **Kontras:** teks isi minimal 4.5:1. `--slate-400` (≈3.9:1 di atas putih) hanya
  untuk teks meta/sekunder; jangan untuk informasi penting atau teks <12px.
- **Fokus terlihat** pada semua elemen interaktif; jangan `outline: none` tanpa pengganti.
- **Ikon-saja wajib berlabel:** `aria-label` (mis. tombol tutup `aria-label="Tutup"`), SVG dekoratif `aria-hidden="true"`.
- **Status tidak hanya lewat warna:** selalu ada teks label (pill status memuat teks).
- Form: setiap input punya `<label for>`; error dikaitkan dekat field.
- Modal dapat ditutup dengan `Esc`; tombol utama dapat dicapai dengan keyboard.

---

## 18. Bahasa & Penulisan

- **Bahasa Indonesia baku**, kalimat aktif, sapaan netral ("Anda" untuk pegawai).
- Istilah konsisten:

| Pakai | Hindari |
|---|---|
| Pengajuan | Usulan (kecuali tombol "Tambah Usulan Baru"), surat |
| Admin Biro PAKLN / Biro PAKLN | PKLN (sisa lama — ganti saat disentuh) |
| Teruskan / Kembalikan | Approve / Reject |
| Unggah / Unduh | Upload / Download |
| Dokumen | File, berkas (boleh "berkas" untuk file fisik) |
| Non-Kedinasan / PDLN | Non Dinas, Dinas LN |

- Judul pakai **Kapital Tiap Kata** ("Unggah Dokumen Administrasi"); kalimat
  bantuan pakai huruf kapital di awal saja.
- Pesan error: **apa yang salah + apa yang harus dilakukan**
  ("Lengkapi dokumen wajib: LoA, DRH.").
- Kode pengajuan selalu ditampilkan utuh (`PDLN01-2A-071026-021`).

---

## 19. Inkonsistensi Saat Ini & Rencana Perbaikan

Temuan audit `style.css` & template (per 13 Okt 2026), urut prioritas.
Kolom **Status** mencatat penerapan di branch `improvement/design-consistency`.

| # | Temuan | Dampak | Perbaikan | Status |
|:-:|---|---|---|---|
| 1 | Aturan tombol sekunder `.button:not(.is-primary):not(.is-warning):not(.is-logout):not(.is-text):not(.is-ghost)` (spesifisitas tinggi) menimpa `is-danger`, `is-success`, `is-info` | Tombol bahaya (Kembalikan, Hapus, Tutup, Hentikan) **tampil putih** seperti tombol biasa | Tambah `:not(.is-danger):not(.is-success):not(.is-info)` dan definisikan `.button.is-danger` (latar `--red-strong`, teks putih, hover lebih gelap) serta `.button.is-success` | ✅ Selesai — `:where()` + varian `is-danger`/`is-success`/`is-info` (+ `is-light`); workaround `btn-pelaporan-*` dengan `!important` di `pelaporan.css` dihapus. Efek samping yang ikut terperbaiki: tab aktif `.tab-bar .button.is-active` kini benar-benar navy. |
| 2 | Merah & ungu ditulis langsung (`#c0392b`, `#dc2626`, `#e0453c`, `#fdecea`, `#5e35b1`) | Sulit diubah serempak, nuansa merah berbeda-beda | Token baru [§3.2](#32-token-tambahan) | ✅ Selesai — tidak ada hex merah/ungu tersisa di `style.css`, `pelaporan.css`, dan template (kecuali template PDF) |
| 3 | `.notification.paspor-msg.is-info` sama dengan `is-warning` (gold) | Informasi netral terlihat seperti peringatan | `is-info` → latar `--blue-bg`, teks `--navy-900` | ✅ Selesai |
| 4 | 189 atribut `style="…"` di template; terbanyak `font-size:14px` (22×), `width:100%` (14×), `font-size:14px;margin-bottom:14px` (13×), `margin:-10px 0 12px` (7×) | Tampilan tidak seragam, sulit dirawat | Kelas baru: `.section-title.is-small` (14px), `.section-sub` (pakai yang sudah ada), `.mt-16`/utilitas Bulma (`mt-4`, `mb-3`), `.is-flex-1`; migrasikan saat halaman disentuh | 🟡 Sebagian — 189 → 127. Pola berulang diganti `.section-title.is-small[.is-spaced]`, `.is-title-sub`, `.button-row`, `.box.is-info-soft`, `.text-danger`; blok `<style>` di `pegawai/laporan_form.html` dipindah ke `pelaporan.css`. Sisanya nilai unik (mis. `width:100%` untuk DataTables) — migrasikan saat halaman disentuh |
| 5 | 15 ukuran font berbeda | Hierarki kabur | Skala [§4.2](#42-skala) | ⏳ Bertahap — terapkan saat halaman disentuh |
| 6 | Emoji sebagai ikon tombol | Tampilan berbeda antar OS, ukuran tidak seragam | Simbol baku [§15](#15-ikon); jangka panjang set SVG | ⏳ Jangka panjang |
| 7 | Sisa istilah "PKLN" di teks & notifikasi | Istilah tidak konsisten | Ganti ke "Biro PAKLN" saat disentuh | ✅ Selesai untuk teks yang terlihat pengguna (template, notifikasi, label model). Kode event `NOTIF_03*_…PKLN` tetap karena tersimpan di database |
| 8 | `registration/login.html` memakai versi CSS sendiri (`?v=20260911a`) | Halaman login bisa memakai CSS usang | Samakan versi dengan `base.html` setiap rilis CSS | ✅ Selesai — kedua file kini `?v=20261013c` |

Sisa pekerjaan (#4–#6) dilakukan bertahap: setiap PR yang menyentuh sebuah
halaman ikut merapikan halaman itu sesuai panduan ini.

---

## 20. Checklist Sebelum Merge

- [ ] Memakai komponen/partial yang ada; komponen baru didefinisikan di `style.css`
- [ ] Warna, radius, durasi memakai token; tidak ada hex baru di template
- [ ] Ukuran font dari skala [§4.2](#42-skala); tidak ada `style="font-size:…"` baru
- [ ] Tombol: varian sesuai [§8.1](#81-varian); aksi destruktif memakai `data-confirm`
- [ ] Status memakai `.tag.paspor-status` / `.tag.bko-status`
- [ ] Tabel memakai `.table-wrap` + `.data-table` + konfigurasi DataTables standar
- [ ] Halaman baru terdaftar di `breadcrumbs.CRUMBS` dan sidebar (bila menu)
- [ ] Teks Bahasa Indonesia sesuai [§18](#18-bahasa--penulisan)
- [ ] Dicek di lebar 1366px, 1024px, dan 390px (mobile)
- [ ] Versi cache-busting `style.css` dinaikkan bila CSS berubah
