# Perancangan Fitur PDLN & Penyempurnaan Alur PASPOR

> **Status:** rancangan — turunan dari [BISNIS_PROSES_PDLN.MD](../instructions/BISNIS_PROSES_PDLN.MD).
> Bila ada perbedaan, dokumen bisnis proses yang menjadi acuan; perbarui
> diagram di sini mengikuti perubahan di sana.

Folder ini berisi desain visual untuk integrasi **PDLN (Perjalanan Dinas
Luar Negeri)** ke PASPOR, sekaligus penyesuaian alur **Non-Dinas** yang
sudah berjalan (pembatalan, aturan satu pengajuan aktif, report terpadu).

## Isi

| No | Dokumen | Isi |
|---|---|---|
| 01 | [Use Case](01_USE_CASE.md) | Aktor, use case per role, hubungan include/extend |
| 02 | [Flowchart / Activity](02_FLOWCHART.md) | Alur pengajuan per tipe, pengembalian, pelaporan, pembatalan, aturan satu pengajuan aktif |
| 03 | [State Diagram](03_STATE_DIAGRAM.md) | Siklus status `Pengajuan`, `LaporanPdln`, `PermohonanPembatalan` |
| 04 | [Sequence Diagram](04_SEQUENCE_DIAGRAM.md) | Interaksi user–view–service–database untuk aksi utama |
| 05 | [Class Diagram & ERD](05_CLASS_ERD.md) | Model data Django dan relasi tabel |
| 06 | [Desain Menu & Layout](06_DESAIN_MENU_LAYOUT.md) | Peta menu per role dan wireframe halaman kunci |

## Notasi

- Diagram ditulis dalam **[Mermaid](https://mermaid.js.org/)**. Tampil
  otomatis di GitHub/GitLab; di VS Code gunakan ekstensi *Markdown
  Preview Mermaid Support* (`bierner.markdown-mermaid`).
- Wireframe layout ditulis sebagai blok teks (ASCII) — menggambarkan
  susunan dan isi, **bukan** desain visual final. Gaya visual mengikuti
  `static/css/style.css` (tema navy/gold) dan mockup Tahap 2.
- Istilah, kode status, dan kode tipe sama dengan dokumen bisnis proses:

| Kode | Arti |
|---|---|
| `nondinas` | Perjalanan Luar Negeri Non-Kedinasan |
| `T1` / `T3` | PDLN Tipe 1 / Tipe 3 (Penugasan Khusus) — alur Unor → PAKLN |
| `T2P` / `T2L` | PDLN Tipe 2 Pendidikan / Pelatihan — alur Unor → BPSDM → PAKLN |
| `belum`, `proses`, `proses_bpsdm`, `proses_pakln`, `selesai`, `dibatalkan` | Status `Pengajuan` |

## Cakupan & batasan

- Butir yang masih dibahas di
  [BISNIS_PROSES_PDLN.MD §15](../instructions/BISNIS_PROSES_PDLN.MD#15-bahan-pertimbangan-untuk-diskusi-lanjutan)
  (terutama **D1 rombongan/delegasi** dan **D3 Ralat/Perubahan**) **belum**
  digambarkan; diagram mengasumsikan satu pegawai per pengajuan.
- Pembatalan memakai **mekanisme interim** (BISNIS_PROSES_PDLN.MD §4.5).
