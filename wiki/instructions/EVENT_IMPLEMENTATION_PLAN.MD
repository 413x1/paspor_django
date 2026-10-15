# Rencana Implementasi — Objek Kegiatan PDLN

> **Status:** diimplementasikan (Fase 1–8) — penyesuaian terhadap rancangan dicatat di [§15](#15-catatan-implementasi).
> **Cakupan:** semua tipe PDLN (T1, T2P, T2L, T3). Non-Kedinasan tidak berubah.
> **Terkait:** [BISNIS_PROSES_PDLN.MD](BISNIS_PROSES_PDLN.MD) §5 (formulir) & §8 (data),
> [PDLN_TIPE_2_FLOW.MD](PDLN_TIPE_2_FLOW.MD), [PASPOR_DESIGN_GUIDE.MD](PASPOR_DESIGN_GUIDE.MD).

---

## Daftar Isi

1. [Latar Belakang](#1-latar-belakang)
2. [Kondisi Saat Ini](#2-kondisi-saat-ini)
3. [Konsep & Istilah](#3-konsep--istilah)
4. [Aturan Bisnis](#4-aturan-bisnis)
5. [Proses Bisnis](#5-proses-bisnis)
6. [Rancangan Flow](#6-rancangan-flow)
7. [Perancangan Data](#7-perancangan-data)
8. [Rancangan Halaman](#8-rancangan-halaman)
9. [Notifikasi & Log](#9-notifikasi--log)
10. [Report & Export](#10-report--export)
11. [Migrasi Data](#11-migrasi-data)
12. [Rencana Implementasi per Fase](#12-rencana-implementasi-per-fase)
13. [Test](#13-test)
14. [Keputusan & Pertanyaan Terbuka](#14-keputusan--pertanyaan-terbuka)
15. [Catatan Implementasi](#15-catatan-implementasi)

---

## 1. Latar Belakang

Setiap PDLN selalu memiliki **kegiatan** yang menjadi tujuannya (agenda, program,
pertemuan, perkuliahan, pelatihan). Saat ini kegiatan tidak menjadi objek
sendiri: pegawai mengetik penyelenggara, kota, dan tanggal kegiatan di formulir,
dan khusus Tipe 2 kegiatan diwakili droplist **Nama Beasiswa (Platform BPSDM)**.
Droplist itu **diganti sepenuhnya** oleh Kegiatan; ke depan data kegiatan juga
akan **dikonsumsi dari Platform BPSDM** (lihat [§7.5](#75-kesiapan-integrasi-aplikasi-pintar)).

Akibatnya:

- Kegiatan yang sama diketik berulang oleh banyak pegawai dengan ejaan berbeda.
- Tidak bisa melihat "siapa saja yang berangkat ke kegiatan X".
- Kategori perjalanan dan sumber pembiayaan tidak tervalidasi terhadap kegiatannya.
- Tidak tercatat **dasar** keberadaan kegiatan (surat undangan, tautan resmi, data PINTAR).

Rencana ini memperkenalkan **objek Kegiatan** yang dikelola Admin Biro PAKLN,
dipilih pegawai di formulir PDLN, dan dapat **diusulkan** bila belum ada — oleh
pegawai (semua kategori) atau oleh **Admin BPSDM** (kategori pendidikan &
pelatihan) — berlaku setelah disetujui Admin Biro PAKLN.

---

## 2. Kondisi Saat Ini

| Data | Lokasi sekarang | Diisi oleh | Berlaku tipe |
|---|---|---|---|
| Penyelenggara | `DetailPdln.penyelenggara` (teks bebas) | Pegawai | T1, T3, T2L |
| Perguruan tinggi | `DetailPdln.perguruan_tinggi` (teks bebas) | Pegawai | T2P |
| Kota tujuan | `DetailPdln.kota_tujuan` (teks bebas) | Pegawai | semua |
| Tgl mulai / selesai kegiatan | `DetailPdln.tgl_mulai_kegiatan` / `tgl_selesai_kegiatan` | Pegawai | semua |
| Nama beasiswa | `DetailPdln.beasiswa_pintar_id` + `beasiswa_nama` (dari Platform BPSDM) | Pegawai (droplist) | T2P, T2L |
| Negara tujuan | `Pengajuan.tujuan_negara` (M2M `Negara`) | Pegawai | semua |
| Kategori perjalanan | `Pengajuan.kategori` (FK `KategoriPerjalanan`, disaring per tipe) | Pegawai | semua |
| Sumber pembiayaan | `Pengajuan.sumber_pembiayaan` (FK `SumberPembiayaan`, disaring per tipe) | Pegawai | semua |

Master kategori PDLN saat ini (`paspor/migrations/0007_seed_master_pdln.py`):

| Kategori | Tipe |
|---|---|
| Pertemuan Bilateral/Regional/Multilateral, Pameran/Expo, Pemberian Advis Teknis, Pendampingan | T1, T3 |
| Master, Doctoral (= **pendidikan**) | T2P |
| Short Course-Training, Seminar/Lokakarya, Workshop, Simposium/Konferensi Internasional (= **pelatihan**) | T2L |

---

## 3. Konsep & Istilah

| Istilah | Arti |
|---|---|
| **Kegiatan** | Acara/program di luar negeri yang menjadi tujuan PDLN — mis. "ASEAN Ministerial Meeting on Infrastructure 2027", "Master of Water Management — IHE Delft 2027". Satu kegiatan dapat diikuti banyak pegawai dan berlangsung di satu negara atau lebih (jarang). |
| **Kategori kegiatan** | Kategori perjalanan (`KategoriPerjalanan`) tempat kegiatan berlaku. Satu kegiatan boleh punya beberapa kategori, kecuali kegiatan **pendidikan**. |
| **Skema pendanaan** | Sumber pembiayaan (`SumberPembiayaan`) yang dapat dipakai untuk kegiatan itu. |
| **Dasar kegiatan** | Bukti/rujukan resmi keberadaan kegiatan: surat (nomor surat undangan/penugasan, opsional berkas PDF), tautan (situs resmi penyelenggara/universitas), data Platform BPSDM, atau lainnya. Setiap kegiatan wajib punya minimal satu dasar. |
| **Usulan kegiatan** | Kegiatan baru yang diajukan pegawai atau Admin BPSDM; berstatus *Menunggu Persetujuan* sampai diputus Admin Biro PAKLN. |
| **Kegiatan pendidikan** | Kegiatan yang memuat kategori berlaku `T2P` (Master/Doctoral). Penyelenggara = **universitas**. |
| **Kegiatan pelatihan** | Kegiatan yang kategorinya berlaku `T2L` (Short Course, Seminar, Workshop, Simposium). |

---

## 4. Aturan Bisnis

| # | Aturan |
|:-:|---|
| B1 | Setiap pengajuan PDLN (semua tipe) **wajib memilih satu Kegiatan**. |
| B2 | Hanya kegiatan berstatus **Disetujui** dan **aktif** yang dapat dipilih pegawai. |
| B3 | Satu kegiatan dapat dipilih oleh **lebih dari satu pegawai** (tidak ada batas peserta). |
| B4 | Satu kegiatan dapat berada di **lebih dari satu kategori perjalanan**, **kecuali** kegiatan pendidikan: kegiatan yang memuat kategori pendidikan hanya boleh memiliki **tepat satu** kategori. |
| B5 | Kategori kegiatan harus dari jenis PDLN. Kategori pengajuan wajib **salah satu kategori kegiatan** yang dipilih. |
| B6 | Skema pendanaan kegiatan = satu atau lebih `SumberPembiayaan` PDLN. Sumber pembiayaan pengajuan wajib **salah satu skema kegiatan** (dan tetap berlaku untuk tipe pengajuan). |
| B7 | Kegiatan memiliki **satu atau lebih negara** (umumnya satu). Semua negara kegiatan wajib termasuk dalam **negara tujuan** pengajuan (otomatis ditambahkan, tidak bisa dihapus selama kegiatan itu dipilih); pegawai tetap boleh menambah negara lain. |
| B8 | Periode kegiatan (`tgl_mulai`–`tgl_selesai`) **berbeda** dari periode perjalanan dan harus berada **di dalam** periode perjalanan (aturan validasi yang sudah ada, kini memakai tanggal kegiatan). |
| B9 | `tahun_pelaksanaan` = tahun `tgl_mulai` (diisi otomatis, dapat dikoreksi Admin Biro PAKLN). |
| B10 | Pegawai dapat **mengusulkan** kegiatan baru bila kegiatan belum ada. Usulan **tidak dapat dipilih** (termasuk oleh pengusulnya) sebelum disetujui Admin Biro PAKLN. |
| B10a | **Admin BPSDM** dapat membuat kegiatan **khusus kategori pendidikan (T2P) dan pelatihan (T2L)** — semua kategorinya wajib berlaku T2P atau T2L (pendidikan tetap tepat satu kategori, B4). Kegiatan buatan Admin BPSDM masuk sebagai **usulan** berstatus Menunggu Persetujuan dan baru dapat dipilih setelah **disetujui Admin Biro PAKLN**. |
| B11 | Admin Biro PAKLN dapat **menyetujui** (boleh menyunting isian dulu), atau **menolak** dengan catatan wajib (mis. "gunakan kegiatan *X* yang sudah ada"). |
| B12 | Kegiatan yang sudah dipakai pengajuan **tidak dapat dihapus**, hanya **dinonaktifkan** (tidak ditawarkan lagi, pengajuan lama tetap terbaca). |
| B13 | Data kegiatan **di-snapshot** ke pengajuan saat pengajuan dikirim ke Admin Unor, sehingga perubahan kegiatan berikutnya tidak mengubah pengajuan yang sudah berjalan. |
| B14 | Kegiatan yang sudah lewat (`tgl_selesai` < hari ini) tidak ditawarkan untuk pengajuan baru. |
| B15 | Setiap kegiatan wajib memiliki **minimal satu dasar kegiatan** (surat, tautan, PINTAR, atau lainnya), baik dibuat PAKLN, diusulkan pegawai, maupun hasil sinkron PINTAR. Satu kegiatan boleh memiliki beberapa dasar. |

---

## 5. Proses Bisnis

### 5.1 Aktor & hak akses

| Aktor | Kegiatan |
|---|---|
| **Admin Biro PAKLN** | Membuat, menyunting, menonaktifkan kegiatan; memutus usulan (setujui/tolak); melihat peserta per kegiatan |
| **Pegawai** | Memilih kegiatan di formulir PDLN; mengusulkan kegiatan baru; melihat status usulannya |
| **Admin BPSDM** | Membuat kegiatan pendidikan & pelatihan (sebagai usulan, B10a); menyunting usulannya selama menunggu; melihat daftar kegiatan pendidikan & pelatihan (read-only) dan status usulannya |
| Admin Unor, Admin BKO | Melihat kegiatan (read-only) pada pratinjau pengajuan & report sesuai cakupannya |

### 5.2 Proses A — Admin Biro PAKLN mengelola kegiatan

1. Buka **Master Data → Kegiatan**.
2. **Tambah Kegiatan**: isi nama, deskripsi, negara (≥1), kota, penyelenggara, tanggal
   mulai/selesai, (tahun terisi otomatis), kategori (≥1; pendidikan = tepat 1),
   skema pendanaan (≥1), dan **dasar kegiatan** (≥1, B15). Status langsung **Disetujui**.
3. **Sunting** kapan pun. Pengajuan yang sudah dikirim memakai snapshot (B13).
4. **Nonaktifkan / aktifkan** — kegiatan nonaktif tidak ditawarkan ke pegawai.
5. Lihat **peserta**: daftar pengajuan yang memilih kegiatan tersebut.

### 5.3 Proses B — Pegawai memilih kegiatan

1. Pegawai memilih **Tipe PDLN** → **Kategori Perjalanan**.
2. Field **Kegiatan** menampilkan kegiatan yang disetujui, aktif, belum lewat,
   dan memuat kategori terpilih. Dapat dicari (nama, penyelenggara, kota, negara).
3. Setelah kegiatan dipilih, isian berikut **terisi otomatis dan read-only**:
   penyelenggara/universitas, negara (semua ditambahkan ke negara tujuan), kota,
   tanggal mulai & selesai kegiatan. Pilihan **sumber pembiayaan** disaring ke
   skema kegiatan.
4. Pegawai melengkapi tanggal keberangkatan/kepulangan dan field lain, lalu menyimpan.

### 5.4 Proses C — Pegawai mengusulkan kegiatan baru

1. Di field Kegiatan, pegawai menekan **"Kegiatan belum ada? Usulkan kegiatan baru"**.
2. Modal formulir usulan (atribut yang sama dengan Proses A, termasuk **dasar
   kegiatan** wajib — mis. nomor surat undangan atau tautan resmi). Sistem
   menampilkan **kegiatan mirip** (nama/penyelenggara/tahun) untuk mencegah duplikat.
3. Kirim → usulan berstatus **Menunggu Persetujuan**; notifikasi ke Admin Biro PAKLN.
4. Pegawai **belum bisa memilih** usulan itu (B10). Pegawai dapat menyimpan draft
   formulir tanpa kegiatan; tombol **Lanjut/Kirim** menunggu kegiatan terpilih.
5. Usulan dapat dilihat di **Beranda → Usulan Kegiatan Saya** (status + catatan).

### 5.5 Proses C2 — Admin BPSDM membuat kegiatan pendidikan/pelatihan

1. Buka menu **Kegiatan** (sidebar Admin BPSDM).
2. **Tambah Kegiatan**: atribut sama dengan Proses A termasuk dasar kegiatan;
   pilihan kategori hanya kategori T2P/T2L (B10a). Sistem menampilkan kegiatan mirip.
3. Simpan → status **Menunggu Persetujuan** (`sumber_data = usulan_bpsdm`);
   notifikasi ke Admin Biro PAKLN.
4. Selama menunggu, Admin BPSDM boleh menyunting usulannya; setelah diputus,
   read-only (yang menyunting selanjutnya hanya PAKLN).
5. Status & catatan keputusan terlihat di tab **Usulan Saya**.

### 5.6 Proses D — Admin Biro PAKLN memutus usulan

1. Antrean **Kegiatan → Menunggu Persetujuan** (badge jumlah di sidebar) berisi
   usulan pegawai dan Admin BPSDM; kolom **Diusulkan oleh** menampilkan nama + peran.
2. Admin meninjau isian dan **dasar kegiatan** (membuka tautan/berkas), boleh
   **menyunting** isian (mis. merapikan nama, menambah dasar).
3. **Setujui** → status Disetujui; notifikasi ke pengusul: "kegiatan sudah dapat dipilih".
4. **Tolak** (catatan wajib) → status Ditolak; notifikasi ke pengusul beserta
   catatan (mis. rujukan ke kegiatan yang sudah ada).

---

## 6. Rancangan Flow

### 6.1 Siklus status Kegiatan

```
                                         Admin Biro PAKLN membuat /
                                         sinkron PINTAR
                                                 │
                                                 ▼
Pegawai (semua kategori) ──┐
                           ├─usulkan─► [menunggu] ──setujui──► [disetujui] ◄──aktifkan───┐
Admin BPSDM (T2P/T2L) ─────┘               │                       │                     │
                                           │                       └──nonaktifkan──► (is_active = False)
                                           └──tolak (catatan wajib)──► [ditolak]
```

- `status`: `menunggu` → `disetujui` | `ditolak` (final; pengusul dapat mengusulkan ulang).
- `is_active` terpisah dari `status`: hanya `disetujui` + `is_active` yang dapat dipilih.

### 6.2 Formulir PDLN dengan Kegiatan

```
[Pilih Tipe PDLN] → [Kategori Perjalanan] → [Kegiatan] ──ada──► isian otomatis (read-only)
                                                │                   penyelenggara/universitas, negara,
                                                │                   kota, tgl mulai/selesai kegiatan
                                                │                   + saring sumber pembiayaan
                                              tidak ada
                                                │
                                                ▼
                                   [Usulkan Kegiatan Baru] ──► menunggu persetujuan PAKLN
                                                                (draft boleh disimpan tanpa kegiatan)
```

### 6.3 Posisi dalam alur pengajuan

Kegiatan dipilih pada tahap **Formulir** (status `belum`). Tidak ada tahap
persetujuan baru di alur pengajuan; persetujuan usulan kegiatan berjalan
**terpisah** dan hanya menahan pegawai di tahap formulir. Saat **Kirim ke Admin
Unor**, data kegiatan di-snapshot (B13).

---

## 7. Perancangan Data

### 7.1 Model baru `paspor.Kegiatan`

Diletakkan di app `paspor` bersama master data lain (`Negara`, `KategoriPerjalanan`,
`SumberPembiayaan`).

| Field | Tipe | Wajib | Keterangan |
|---|---|:-:|---|
| `nama` | `CharField(255)` | ✅ | Nama kegiatan/program |
| `deskripsi` | `TextField` | — | Uraian singkat agenda/program |
| `negara` | `M2M Negara` | ✅ ≥1 | Negara pelaksanaan; umumnya satu, boleh lebih (B7) |
| `kota` | `CharField(255)` | ✅ | Kota pelaksanaan; bila multi-negara ditulis berurutan, mis. "Tokyo, Seoul" |
| `penyelenggara` | `CharField(200)` | ✅ | Penyelenggara; untuk pendidikan = **universitas** (label menyesuaikan) |
| `tgl_mulai` | `DateField` | ✅ | Tanggal mulai kegiatan (≠ keberangkatan) |
| `tgl_selesai` | `DateField` | ✅ | Tanggal selesai kegiatan (≠ kepulangan); ≥ `tgl_mulai` |
| `tahun_pelaksanaan` | `PositiveSmallIntegerField` | ✅ | Default `tgl_mulai.year` |
| `kategori` | `M2M KategoriPerjalanan` | ✅ ≥1 | Hanya jenis PDLN; aturan B4 |
| `skema_pendanaan` | `M2M SumberPembiayaan` | ✅ ≥1 | Hanya tipe PDLN |
| `status` | `CharField` choices `menunggu`/`disetujui`/`ditolak` | ✅ | Default `disetujui` bila dibuat PAKLN, `menunggu` bila diusulkan pegawai |
| `is_active` | `BooleanField` | ✅ | Default `True` |
| `diusulkan_oleh` | `FK User` (`SET_NULL`, null) | — | Pengusul (pegawai atau Admin BPSDM); kosong bila dibuat PAKLN/sinkron |
| `diputus_oleh` | `FK User` (`SET_NULL`, null) | — | Admin Biro PAKLN yang memutus usulan |
| `tgl_diputus` | `DateTimeField` null | — | Waktu keputusan |
| `catatan_keputusan` | `TextField` | — | Wajib saat ditolak |
| `sumber_data` | `CharField` choices `manual`/`usulan_pegawai`/`usulan_bpsdm`/`pintar` | ✅ | Asal data: dibuat PAKLN, usulan pegawai, usulan Admin BPSDM, atau sinkron PINTAR (§7.5); disimpan agar tidak bergantung pada peran pengusul yang bisa berubah |
| `kode_pintar` | `CharField(50)` null, unique | — | ID kegiatan/beasiswa di Platform BPSDM; kosong untuk data manual |
| `created_at`, `updated_at` | `DateTimeField` | ✅ | |

Properti/metode:

- `is_pendidikan` — memuat kategori yang `tipe_pdln` berisi `T2P`.
- `tipe_berlaku` — gabungan `tipe_pdln` dari kategorinya (untuk menyaring per tipe pengajuan).
- `dapat_dipilih` — `status == disetujui and is_active and tgl_selesai >= today`, serta memiliki kategori & skema (relevan untuk data sinkron PINTAR, §7.5).
- Manager `Kegiatan.objects.dapat_dipilih(tipe=None, kategori=None)`.

Validasi (`clean()` di form, karena M2M):

- `tgl_selesai >= tgl_mulai`.
- Kategori semua jenis PDLN; bila ada kategori pendidikan → jumlah kategori = 1 (B4).
- Skema semua `SumberPembiayaan.tipe_perjalanan = PDLN`.
- Minimal satu `DasarKegiatan` (formset, B15).
- Bila pengusul Admin BPSDM: semua kategori berlaku `T2P` atau `T2L` (B10a); queryset
  kategori di form juga sudah disaring.

Index & batasan:

- `Index(status, is_active)`, `Index(tahun_pelaksanaan)`.
- Peringatan duplikat (bukan unique constraint): nama mirip + penyelenggara + tahun + negara.
- `kode_pintar` unique bila terisi (kunci sinkron PINTAR).

#### Model `paspor.DasarKegiatan` (1 kegiatan : N dasar)

| Field | Tipe | Wajib | Keterangan |
|---|---|:-:|---|
| `kegiatan` | `FK Kegiatan` (`CASCADE`, `related_name="dasar_list"`) | ✅ | |
| `jenis` | `CharField` choices `surat`/`tautan`/`pintar`/`lainnya` | ✅ | Jenis dasar |
| `nomor_surat` | `CharField(100)` | jenis `surat` | Nomor surat undangan/penugasan/LoA |
| `tgl_surat` | `DateField` null | — | Tanggal surat |
| `tautan` | `URLField(500)` | jenis `tautan` | Halaman resmi kegiatan/program |
| `kode_pintar` | `CharField(50)` | jenis `pintar` | ID di Platform BPSDM (sama dengan `Kegiatan.kode_pintar` bila hasil sinkron) |
| `berkas` | `FileField` (PDF, maks 2 MB, `validate_pdf`) | — | Salinan surat/dokumen pendukung; disimpan di storage S3 seperti dokumen lain |
| `keterangan` | `CharField(255)` | jenis `lainnya` | Uraian dasar, mis. "Nota dinas Kepala Biro No. …" |
| `ditambahkan_oleh` | `FK User` (`SET_NULL`, null) | — | |
| `created_at` | `DateTimeField` | ✅ | |

Validasi `DasarKegiatan.clean()`: field kunci sesuai `jenis` wajib terisi
(`surat` → `nomor_surat`, `tautan` → `tautan`, `pintar` → `kode_pintar`,
`lainnya` → `keterangan`); `berkas` opsional untuk semua jenis.
Dasar yang ditambahkan PAKLN maupun pegawai (saat mengusulkan) tetap tersimpan
apa adanya; penghapusan dasar terakhir ditolak (B15).

### 7.2 Perubahan model yang ada

| Model | Perubahan |
|---|---|
| `Pengajuan` | `kegiatan = FK paspor.Kegiatan (PROTECT, null, blank, related_name="pengajuan_list")` — wajib untuk PDLN di level form/validasi Kirim (B1); null untuk Non-Kedinasan & data lama. |
| `DetailPdln` | Field yang ada menjadi **snapshot** kegiatan saat Kirim (B13): `penyelenggara` (juga untuk universitas T2P), `kota_tujuan`, `tgl_mulai_kegiatan`, `tgl_selesai_kegiatan`. Tambah `kegiatan_nama` (`CharField 255`) dan `kegiatan_tahun` (`PositiveSmallIntegerField null`). `perguruan_tinggi` tidak lagi diisi baru (data lama tetap dibaca; tampil sebagai penyelenggara). `beasiswa_pintar_id` / `beasiswa_nama` tidak lagi diisi baru — hanya untuk data lama; nilainya dipakai backfill (§11). |

### 7.3 Diagram relasi

```
KategoriPerjalanan ◄──M2M── Kegiatan ──M2M──► SumberPembiayaan
                              │  │
                   M2M Negara ◄┘  └─ FK User (diusulkan_oleh, diputus_oleh)
                              │
                              ├──1:N── DasarKegiatan (surat / tautan / pintar / lainnya)
                              ▲
                              │ FK (PROTECT)
                          Pengajuan ──1:1── DetailPdln (snapshot kegiatan)
                              │
                              ├── FK KategoriPerjalanan  (∈ kegiatan.kategori)
                              ├── FK SumberPembiayaan    (∈ kegiatan.skema_pendanaan)
                              └── M2M Negara             (⊇ kegiatan.negara)
```

### 7.4 Snapshot saat Kirim

Di `views_pegawai._kirim` (di dalam transaksi yang sama), salin ke `DetailPdln`:
`kegiatan_nama ← nama`, `kegiatan_tahun ← tahun_pelaksanaan`,
`penyelenggara ← penyelenggara`, `kota_tujuan ← kota`,
`tgl_mulai_kegiatan ← tgl_mulai`, `tgl_selesai_kegiatan ← tgl_selesai`.
Saat masih draft (status `belum`, termasuk saat dikembalikan Unor), tampilan
membaca langsung dari `Kegiatan` sehingga koreksi PAKLN ikut terbawa.

### 7.5 Kesiapan integrasi Platform BPSDM

Data kegiatan nantinya juga diambil dari Platform BPSDM. Integrasinya **di luar
cakupan** rencana ini, tetapi model disiapkan agar tidak perlu diubah lagi:

- Kegiatan dari PINTAR disimpan dengan `sumber_data = pintar` dan `kode_pintar`
  terisi; sinkron berikutnya melakukan *upsert* berdasarkan `kode_pintar`.
- Sinkron otomatis membuat `DasarKegiatan` berjenis `pintar` (B15), sehingga
  sumber data kegiatan selalu tercatat.
- Kegiatan hasil sinkron langsung berstatus **Disetujui** (sudah tervalidasi di
  PINTAR); Admin Biro PAKLN tetap dapat menyunting dan menonaktifkan.
- Field yang tidak tersedia di PINTAR (mis. kategori/skema) dilengkapi PAKLN;
  selama belum lengkap kegiatan tidak dapat dipilih (`dapat_dipilih` juga
  memeriksa kategori ≥1 dan skema ≥1).
- Kegiatan manual yang ternyata sama dengan data PINTAR dapat ditautkan dengan
  mengisi `kode_pintar` (tanpa membuat kegiatan baru).

---

## 8. Rancangan Halaman

Mengikuti [PASPOR_DESIGN_GUIDE.MD](PASPOR_DESIGN_GUIDE.MD) (pola dasbor/daftar, DataTables standar, tombol & modal).

### 8.1 Admin Biro PAKLN — Master Data → Kegiatan

| Elemen | Isi |
|---|---|
| URL | `pakln:kelola_kegiatan`, `pakln:kegiatan_data`, `pakln:edit_kegiatan`, `pakln:toggle_kegiatan`, `pakln:putuskan_kegiatan`, `pakln:peserta_kegiatan` |
| Tab | **Semua** · **Menunggu Persetujuan** (badge) · **Ditolak** |
| Tabel | Nama (+ penyelenggara `.cell-muted`) · Negara/Kota · Periode · Tahun · Kategori · Skema · Status (`.tag`) · Peserta (jumlah pengajuan) · Aksi |
| Form tambah/sunting | Semua atribut [§7.1](#71-model-baru-pasporkegiatan) + bagian **Dasar Kegiatan** (baris dinamis: pilih jenis → field sesuai jenis, berkas opsional memakai `_input_berkas.html`); negara, kategori & skema memakai `.multiselect`; label "Penyelenggara" berubah menjadi "Universitas" bila kategori pendidikan dipilih |
| Detail kegiatan | Menampilkan daftar dasar: nomor surat (+ tombol pratinjau berkas), tautan (buka di tab baru, `rel="noopener"`), kode PINTAR, keterangan |
| Putus usulan | Halaman sunting + panel **Setujui** (`is-success`) / **Tolak** (`is-danger`, catatan wajib, `data-confirm`) |
| Peserta | Daftar pengajuan yang memilih kegiatan (kode, pegawai, unor, status) |
| Sidebar | Grup **Master Data**: tambah menu **Kegiatan** (badge jumlah menunggu) |

### 8.2 Pegawai — Formulir PDLN

| Elemen | Perubahan |
|---|---|
| Field **Kegiatan** | Select dengan pencarian, disaring tipe + kategori; menampilkan "Nama — Penyelenggara, Kota (dd Mmm yyyy – dd Mmm yyyy)" |
| Isian otomatis | Penyelenggara/Universitas, Negara (semua negara kegiatan dikunci di negara tujuan), Kota, Tgl mulai/selesai kegiatan — read-only |
| Sumber pembiayaan | Disaring ke skema kegiatan |
| Tautan usulan | "Kegiatan belum ada? **Usulkan kegiatan baru**" → modal `.paspor-modal` (termasuk minimal satu dasar kegiatan) |
| Field dihapus | `penyelenggara`, `perguruan_tinggi`, `kota_tujuan`, `tgl_mulai_kegiatan`, `tgl_selesai_kegiatan` (input bebas), dan droplist `beasiswa` (Platform BPSDM) |

Endpoint pendukung: `pegawai:kegiatan_opsi` (JSON opsi per tipe/kategori, untuk
pencarian & isian otomatis), `pegawai:usulkan_kegiatan` (POST modal).

### 8.3 Pegawai — Beranda

Kartu **Usulan Kegiatan Saya**: nama, tanggal usul, status (Menunggu/Disetujui/
Ditolak + catatan). Disembunyikan bila belum pernah mengusulkan.

### 8.4 Admin BPSDM — Kegiatan

| Elemen | Isi |
|---|---|
| URL | `bpsdm:kegiatan`, `bpsdm:kegiatan_data`, `bpsdm:tambah_kegiatan`, `bpsdm:edit_kegiatan` (hanya usulan sendiri berstatus menunggu) |
| Tab | **Kegiatan Pendidikan & Pelatihan** (disetujui, read-only) · **Usulan Saya** (semua status + catatan keputusan) |
| Form | Sama dengan form PAKLN (komponen bersama), kategori disaring T2P/T2L, tanpa panel putus |
| Sidebar | Menu **Kegiatan** di grup Admin BPSDM |

### 8.5 Halaman lain

- `partials/_ringkasan_pengajuan.html`: tampilkan **Kegiatan** (nama + tahun),
  data snapshot (penyelenggara/universitas, kota, periode kegiatan), dan
  **dasar kegiatan** (agar verifikator Unor/BPSDM/PAKLN dapat merujuknya).
- Monitor progres pegawai & formulir laporan PDLN: tampilkan nama kegiatan.

---

## 9. Notifikasi & Log

| Kode | Pemicu | Penerima |
|---|---|---|
| `NOTIF_08A_KEGIATAN_DIUSULKAN` | Pegawai atau Admin BPSDM mengusulkan kegiatan | Admin Biro PAKLN |
| `NOTIF_08B_KEGIATAN_DISETUJUI` | PAKLN menyetujui usulan | Pengusul (pegawai/Admin BPSDM) |
| `NOTIF_08C_KEGIATAN_DITOLAK` | PAKLN menolak usulan (dengan catatan) | Pengusul (pegawai/Admin BPSDM) |

Log Sistem (`logs.utils.record_activity`, `target_type="kegiatan"`): tambah,
sunting, aktifkan/nonaktifkan, usulkan, setujui, tolak, tambah/hapus dasar.

---

## 10. Report & Export

- Export Database: kolom **Kegiatan**, **Tahun Kegiatan**, **Penyelenggara** (dari snapshot,
  fallback ke `Kegiatan` untuk draft).
- Rekap: tab baru **Per Kegiatan** — jumlah pengajuan per kegiatan, per status.
- Filter global: **Kegiatan** (select dengan pencarian) dan **Tahun Kegiatan**.

---

## 11. Migrasi Data

Sistem belum rilis (data QC), sehingga data lama dimigrasikan agar konsisten:

| Migrasi | Isi |
|---|---|
| `paspor/00xx_kegiatan` | Model `Kegiatan` + M2M + `DasarKegiatan` |
| `pengajuan/00xx_pengajuan_kegiatan` | `Pengajuan.kegiatan`, `DetailPdln.kegiatan_nama`, `kegiatan_tahun` |
| `pengajuan/00xx_backfill_kegiatan` | Untuk setiap pengajuan PDLN yang punya `DetailPdln`: kelompokkan berdasarkan (nama, penyelenggara/perguruan tinggi, kota, tgl mulai, tgl selesai, himpunan negara tujuan); buat satu `Kegiatan` **disetujui** per kelompok dengan `nama` = `beasiswa_nama` atau "Kegiatan {penyelenggara} {tahun}", `negara` = negara tujuan pengajuan, `kode_pintar` = `beasiswa_pintar_id` bila ada (`sumber_data = pintar`, selain itu `manual`), dasar = `pintar` (bila ada `beasiswa_pintar_id`) atau `lainnya` dengan keterangan "Migrasi data pengajuan {kode}", `kategori` = kategori pengajuan, `skema_pendanaan` = sumber pembiayaan pengajuan; tautkan pengajuan & isi snapshot |

Pengajuan Non-Kedinasan tidak disentuh. Reverse: kosongkan tautan & hapus kegiatan hasil backfill.

---

## 12. Rencana Implementasi per Fase

| Fase | Pekerjaan | File utama |
|:-:|---|---|
| 1 | Model `Kegiatan` (termasuk `sumber_data`, `kode_pintar`) & `DasarKegiatan` + manager `dapat_dipilih`, admin Django, migrasi | `paspor/models.py`, `paspor/admin.py`, `paspor/migrations/` |
| 2 | `Pengajuan.kegiatan`, snapshot `DetailPdln`, migrasi + backfill | `pengajuan/models.py`, `pengajuan/migrations/` |
| 3 | Manajemen Kegiatan PAKLN: form + formset dasar (validasi B4/B6/B15), daftar DataTables, sunting, aktif/nonaktif, peserta, sidebar & breadcrumb | `pengajuan/forms.py` (`KegiatanForm`), `pengajuan/views_pakln.py`, `pengajuan/urls_pakln.py`, `templates/pakln/kegiatan*.html`, `partials/_sidebar.html`, `pengajuan/breadcrumbs.py` |
| 4 | Usulan & persetujuan: modal usulan pegawai (cek kemiripan), menu Kegiatan Admin BPSDM (B10a), antrean & putus PAKLN, kartu "Usulan Kegiatan Saya", notifikasi 08A–08C | `pengajuan/kegiatan.py` (layanan: `usulkan`, `setujui`, `tolak`), `views_pegawai.py`, `views_bpsdm.py`, `urls_bpsdm.py`, `templates/bpsdm/kegiatan*.html`, `views_pakln.py`, `notifications/models.py`, `notifications/services.py` |
| 5 | Formulir PDLN: field Kegiatan (select berpencarian, endpoint opsi), isian otomatis, saring sumber pembiayaan, negara terkunci, validasi B5–B8, hapus field bebas & droplist beasiswa | `pengajuan/forms.py` (`PdlnForm`), `templates/pegawai/formulir_pdln.html`, `views_pegawai.py` |
| 6 | Snapshot saat Kirim + tampilan kegiatan di ringkasan, monitor, laporan | `views_pegawai._kirim`, `partials/_ringkasan_pengajuan.html`, `pegawai/monitor.html`, `pegawai/laporan_form.html` |
| 7 | Report: kolom export, tab rekap per kegiatan, filter | `pengajuan/report.py`, `views_report.py`, `templates/report/*` |
| 8 | Test, dokumentasi (`BISNIS_PROSES_PDLN.MD` §5 & §8, design guide bila ada komponen baru) | `pengajuan/tests_kegiatan.py`, `wiki/instructions/*` |

Perkiraan urutan rilis: Fase 1–3 (PAKLN dapat mulai mengisi master kegiatan) →
Fase 4–6 (pegawai memakai kegiatan) → Fase 7–8.

**Lanjutan (di luar cakupan):** sinkron kegiatan dari Platform BPSDM
(`pengajuan/kegiatan.py: sinkron_pintar`, perintah manajemen terjadwal) sesuai
§7.5, setelah spesifikasi API PINTAR tersedia.

---

## 13. Test

| # | Skenario | Harapan |
|:-:|---|---|
| 1 | PAKLN membuat kegiatan dengan 2 kategori non-pendidikan | Tersimpan, status disetujui |
| 2 | Kegiatan dengan kategori Master + Pameran | Ditolak (B4) |
| 3 | Kegiatan dengan kategori Non-Kedinasan / skema Non-Dinas | Ditolak |
| 4 | `tgl_selesai < tgl_mulai` | Ditolak |
| 5 | Pegawai mengusulkan kegiatan | Status menunggu, notifikasi ke PAKLN, tidak muncul di opsi pegawai (termasuk pengusul) |
| 6 | PAKLN menyetujui usulan | Muncul di opsi; notifikasi ke pengusul |
| 7 | PAKLN menolak tanpa catatan / dengan catatan | Ditolak / status ditolak + notifikasi berisi catatan |
| 8 | Opsi kegiatan disaring tipe & kategori, kegiatan nonaktif & lewat tidak muncul | Sesuai B2, B14 |
| 9 | Formulir: kategori pengajuan bukan kategori kegiatan | Ditolak (B5) |
| 10 | Formulir: sumber pembiayaan di luar skema kegiatan | Ditolak (B6) |
| 11 | Formulir: memilih kegiatan dengan 2 negara | `tujuan_negara` memuat kedua negara kegiatan; negara tambahan pegawai tetap tersimpan (B7) |
| 12 | Periode kegiatan di luar periode perjalanan | Ditolak (B8) |
| 13 | Dua pegawai memilih kegiatan yang sama | Keduanya tersimpan (B3); peserta = 2 |
| 14 | PAKLN mengubah tanggal kegiatan setelah pengajuan dikirim | Snapshot pengajuan tidak berubah (B13) |
| 15 | Hapus kegiatan yang sudah dipakai | Ditolak (`PROTECT`); hanya bisa dinonaktifkan (B12) |
| 16 | Backfill migrasi | Pengajuan PDLN lama tertaut ke kegiatan; kelompok sama → satu kegiatan |
| 17 | Kirim pengajuan PDLN tanpa kegiatan | Ditolak (B1) |
| 18 | Kegiatan disetujui tetapi tanpa kategori/skema (data PINTAR belum lengkap) | Tidak muncul di opsi pegawai |
| 19 | Dua kegiatan dengan `kode_pintar` sama | Ditolak (unique) |
| 20 | Simpan kegiatan / usulan tanpa dasar kegiatan | Ditolak (B15) |
| 24 | Admin BPSDM membuat kegiatan kategori Workshop + Seminar | Tersimpan berstatus menunggu, `sumber_data = usulan_bpsdm`, notifikasi ke PAKLN; belum muncul di opsi pegawai |
| 25 | Admin BPSDM membuat kegiatan kategori Pertemuan Bilateral (T1/T3) | Ditolak (B10a) |
| 26 | PAKLN menyetujui usulan Admin BPSDM | Muncul di opsi pegawai T2; notifikasi ke Admin BPSDM pengusul |
| 27 | Admin BPSDM menyunting usulan yang sudah diputus / usulan milik Admin BPSDM lain | Ditolak (403) |
| 21 | Dasar jenis `surat` tanpa nomor surat, `tautan` dengan URL tidak valid | Ditolak |
| 22 | Berkas dasar > 2 MB atau bukan PDF | Ditolak |
| 23 | Hapus dasar terakhir sebuah kegiatan | Ditolak (B15) |

---

## 14. Keputusan & Pertanyaan Terbuka

### 14.1 Sudah diputuskan

| # | Pertanyaan | Keputusan |
|:-:|---|---|
| 1 | **Platform BPSDM**: droplist Nama Beasiswa diganti oleh Kegiatan? | **Diganti.** Field `beasiswa_*` hanya untuk data lama. Ke depan data kegiatan juga dikonsumsi dari PINTAR; model disiapkan dengan `sumber_data` & `kode_pintar` (§7.5), integrasi menyusul. |
| 2 | **Daftar kategori**: disatukan menjadi *pendidikan* / *pelatihan* atau tetap? | **Tetap** seperti master sekarang; "kategori pendidikan" = kategori yang berlaku `T2P` (Master/Doctoral). Ditinjau ulang bila perlu. |
| 3 | Satu kegiatan di **lebih dari satu negara**? | **Boleh**, meski jarang. `Kegiatan.negara` menjadi M2M (≥1); semua negara kegiatan masuk negara tujuan (B7). Kota tetap satu field teks. |
| 4 | Apakah kegiatan perlu **sumber/dasar**? | **Ya, wajib** (B15): minimal satu dasar berupa nomor surat, tautan, data PINTAR, atau lainnya; boleh lebih dari satu, berkas PDF opsional (model `DasarKegiatan`). |
| 5 | Siapa saja yang boleh **mengusulkan/membuat** kegiatan? | Admin Biro PAKLN membuat langsung (disetujui). **Pegawai** mengusulkan (semua kategori). **Admin BPSDM** membuat kegiatan **pendidikan & pelatihan** yang perlu disetujui Admin Biro PAKLN (B10a), dengan menu Kegiatan sendiri (§8.4). |

### 14.2 Masih memakai default

Default di bawah dipakai dalam rancangan ini sampai dijawab.

| # | Pertanyaan | Default rancangan |
|:-:|---|---|
| 6 | Skema pendanaan **satu atau banyak** per kegiatan? | Banyak (M2M); pengajuan memilih salah satunya. |
| 7 | Selama usulan menunggu, apakah pegawai boleh **menyimpan draft** formulir? | Boleh, tanpa kegiatan; Lanjut/Kirim menunggu kegiatan terpilih. |
| 8 | Bolehkah PAKLN **menggabungkan** usulan duplikat ke kegiatan yang sudah ada secara otomatis (memindahkan pengajuan)? | Tidak di versi pertama — tolak dengan catatan rujukan; pengusul memilih kegiatan yang ada. |
| 9 | Kegiatan **multi-tahun** (pendidikan 2–4 tahun): `tahun_pelaksanaan` = tahun mulai? | Ya, tahun mulai. |
| 10 | Apakah **Admin Unor** perlu menu daftar kegiatan sendiri? | Tidak — cukup tampil di pratinjau pengajuan & report. |
| 11 | **Sinkron PINTAR**: bila PAKLN menyunting kegiatan hasil sinkron, apakah sinkron berikutnya menimpa suntingan itu? | Tidak — suntingan PAKLN dipertahankan; detailnya diputuskan saat integrasi. |
| 12 | Usulan **Admin BPSDM**: boleh disunting/ditarik selama menunggu? Apakah usulan BPSDM terlihat oleh semua Admin BPSDM atau hanya pembuatnya? | Boleh disunting (tidak ditarik) selama menunggu, hanya oleh pembuatnya; tab Usulan Saya hanya menampilkan usulan sendiri. |

---

## 15. Catatan Implementasi

Penyesuaian terhadap rancangan di atas saat implementasi:

| Bagian | Rancangan | Implementasi |
|---|---|---|
| §5.4 / §8.2 Usulan pegawai | Modal `.paspor-modal` | **Halaman** `pegawai:usulkan_kegiatan` (tautan "Usulkan kegiatan baru" di Formulir PDLN) — form + formset dasar + unggah berkas melebihi lebar modal 400px. Setelah dikirim, kembali ke formulir. |
| §8.2 Endpoint opsi | `pegawai:kegiatan_opsi` (JSON) | Opsi kegiatan disematkan di halaman formulir (`json_script`, `PdlnForm.opsi_kegiatan`) — penyaringan per kategori, pencarian, isian otomatis, dan penyaringan sumber pembiayaan berjalan di browser; server memvalidasi ulang. |
| §8.1 Menu PAKLN | Grup Master Data | Menu utama **Kegiatan** di sidebar (badge jumlah usulan menunggu); peserta tampil di halaman detail kegiatan (tanpa URL terpisah). |
| §7.4 Snapshot | Saat Kirim; draft membaca langsung dari `Kegiatan` | Snapshot ditulis saat formulir disimpan **dan diperbarui saat Kirim** (`pengajuan.kegiatan.snapshot`) — hasilnya sama: koreksi PAKLN selama draft ikut terbawa, setelah dikirim beku. T2P: universitas disimpan di `perguruan_tinggi`, tipe lain di `penyelenggara`, agar tampilan & export lama tetap terbaca. |
| §8.1 Hapus | — | Kegiatan yang **belum** dipakai pengajuan boleh dihapus (beserta berkas dasarnya); yang sudah dipakai hanya dapat dinonaktifkan (B12). |
| §5.3 Kegiatan T1/T3 | — | Master kategori T1 dan T3 sama (`["T1","T3"]`), sehingga kegiatan T1 juga tampil untuk T3 dan sebaliknya. |

Kode utama:

| Lapisan | Berkas |
|---|---|
| Model & migrasi | `paspor/models.py` (`Kegiatan`, `DasarKegiatan`, `KegiatanQuerySet.dapat_dipilih`), `paspor/migrations/0008_kegiatan.py`, `pengajuan/migrations/0026_pengajuan_kegiatan.py`, `0027_backfill_kegiatan.py`, `notifications/migrations/0007_event_kegiatan.py` |
| Layanan | `pengajuan/kegiatan.py` (`simpan`, `usulkan`, `setujui`, `tolak`, `snapshot`, `mirip`) |
| Form | `pengajuan/forms.py` (`KegiatanForm`, `DasarKegiatanForm`, `dasar_formset`, `KeputusanKegiatanForm`, `PdlnForm`) |
| View & URL | `pengajuan/views_kegiatan.py`; `pakln:kelola_kegiatan`, `kegiatan_data`, `tambah_kegiatan`, `edit_kegiatan`, `putuskan_kegiatan`, `toggle_kegiatan`, `hapus_kegiatan`; `bpsdm:kegiatan`, `kegiatan_data`, `tambah_kegiatan`, `edit_kegiatan`; `pegawai:usulkan_kegiatan` |
| Template | `templates/kegiatan/` (`daftar.html`, `form.html`, `_field.html`, `_dasar_row.html`), `pegawai/formulir_pdln.html`, `pegawai/beranda.html`, `partials/_ringkasan_pengajuan.html` |
| Notifikasi | `notifications/services.py` (`notify_kegiatan_diusulkan/disetujui/ditolak`) |
| Report | `pengajuan/report.py` (kolom Kegiatan & Tahun Kegiatan, filter `kegiatan`/`tahun_kegiatan`, rekap per kegiatan) |
| Seed | `python manage.py seed_kegiatan` — 5 kegiatan per tipe (T1, T2P, T2L, T3) + usulan menunggu dari `andra.wibisono` & `admin.bpsdm`; dipanggil otomatis oleh `seed_demo_data` |
| Test | `pengajuan/tests_kegiatan.py` |

