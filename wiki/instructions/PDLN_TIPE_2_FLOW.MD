# Alur Bisnis PDLN Tipe 2 — Pendidikan (T2P)

> **Tujuan dokumen:** memotret alur pemrosesan PDLN Tipe 2 Pendidikan
> (tugas belajar Master/Doctoral) **sebagaimana sudah diimplementasikan**
> di kode saat ini, sebagai titik awal sebelum perubahan flow.
> Rancangan umum seluruh tipe ada di [BISNIS_PROSES_PDLN.MD](BISNIS_PROSES_PDLN.MD).
>
> **Versi:**
> - **v1 — Saat ini** (§1–§7): sudah berjalan di kode.
> - **v2 — Lanjutan: Admin BKO** ([§8](#8-versi-lanjutan-v2--sk-tubel-oleh-admin-bko)): **sudah diimplementasikan**
>   (rencana: [PDLN_T2_PENDIDIKAN_V2_IMPLEMENTATION_PLAN.MD](PDLN_T2_PENDIDIKAN_V2_IMPLEMENTATION_PLAN.MD)).
>   §1–§7 kini catatan historis v1; bila berbeda, §8 yang berlaku.
>
> **Sumber kebenaran di kode:**
> - Urutan tahap: `pengajuan/alur.py` (`ALUR["T2P"]`)
> - Dokumen per tahap: `pengajuan/persyaratan.py` (`PERSYARATAN[("T2P", <tahap>)]`)
> - Aksi per aktor: `pengajuan/views_pegawai.py`, `views_unor.py`, `views_bpsdm.py`, `views_pakln.py`
> - Model dokumen: `DokumenPegawai`, `DokumenUnor`, `DokumenBpsdm`, `DokumenPakln`, `LaporanPdln` (`pengajuan/models.py`)

---

## 1. Ringkasan

| Item | Nilai |
|---|---|
| Jenis perjalanan | `pdln` |
| Kode tipe | `T2P` — "PDLN Tipe 2 — Pendidikan" |
| Kategori | Master, Doctoral |
| Aktor | Pegawai → Admin Unor → **Admin BPSDM** → Admin Biro PAKLN |
| Urutan status | `belum` → `proses` → `proses_bpsdm` → `proses_pakln` → `selesai` |
| Tahap akhir (tuntas) | `selesai` **dan** Laporan PDLN **disetujui** Admin Biro PAKLN |
| Status final alternatif | `dibatalkan` (lewat permohonan pembatalan, dari status mana pun) |

Perbedaan utama dengan PDLN Tipe 1/3: ada tahap **BPSDM** yang disisipkan
di antara Unor dan Biro PAKLN, dan pengembalian dari Biro PAKLN jatuh ke
**Admin BPSDM** (bukan Admin Unor).

---

## 2. Diagram Alur

```
                Pegawai                Admin Unor              Admin BPSDM             Admin Biro PAKLN
               ─────────              ────────────            ─────────────           ──────────────────
 [belum] ──Kirim──► [proses] ──Teruskan──► [proses_bpsdm] ──Teruskan──► [proses_pakln] ──Selesai──► [selesai]
    ▲                   │  ▲                    │  ▲                         │                          │
    └──Kembalikan───────┘  └────Kembalikan──────┘  └───────Kembalikan────────┘                          │
     (catatan_unor)           (catatan_bpsdm)             (catatan_pakln)                               │
                                                                                                        ▼
                                                              Pegawai unggah Laporan PDLN ──► Admin Biro PAKLN verifikasi
                                                                    ▲                                   │
                                                                    └──────── Dikembalikan ─────────────┤
                                                                                                        ▼
                                                                                              Disetujui → TUNTAS
```

Pengembalian **selalu** ke tahap tepat sebelumnya (`alur.tahap_sebelumnya`)
dan **wajib** disertai catatan. Pihak yang menerima pengembalian **wajib**
mengisi catatan balasan saat mengirim/meneruskan ulang.

---

## 3. Langkah per Tahap

### Tahap 1 — Pegawai: Formulir & Unggah Dokumen (`belum`)

**Halaman:** `pegawai:formulir_pengajuan` → `pegawai:upload_dokumen`

1. Pegawai memilih jenis **PDLN** → tipe **Tipe 2 Pendidikan**.
   Syarat: tidak ada pengajuan lain yang belum tuntas (`alur.pengajuan_belum_tuntas`).
2. Mengisi **Formulir Detail Tugas Belajar** (data pegawai otomatis dari profil, read-only):

   | Field | Wajib | Disimpan di |
   |---|:-:|---|
   | Kategori (Master / Doctoral) | ✅ | `Pengajuan.kategori` |
   | Nama Beasiswa — droplist dari **Platform BPSDM** (pencalonan berstatus selesai, jenis `pendidikan`) | ✅ | `DetailPdln.beasiswa_pintar_id`, `beasiswa_nama` |
   | Perguruan Tinggi | ✅ | `DetailPdln.perguruan_tinggi` |
   | Negara tujuan | ✅ | `Pengajuan.tujuan_negara` |
   | Kota tujuan | ✅ | `DetailPdln.kota_tujuan` |
   | Tgl keberangkatan / kepulangan | ✅ | `Pengajuan.tgl_berangkat`, `tgl_kembali` |
   | Tgl mulai / selesai perkuliahan (di dalam periode perjalanan) | ✅ | `DetailPdln.tgl_mulai_kegiatan`, `tgl_selesai_kegiatan` |
   | Sumber pembiayaan | ✅ | `Pengajuan.sumber_pembiayaan` |
   | Pernyataan kebenaran data | ✅ | `DetailPdln.pernyataan_benar` |
   | Jumlah hari kerja | otomatis | `Pengajuan.jumlah_hari_kerja` (snapshot, tidak memotong cuti) |

3. Mengunggah dokumen wajib (lihat [§4.1](#41-diunggah-pegawai--dokumenpegawai)).
4. Centang pernyataan kelengkapan → **Kirim ke Admin Unor**.
   - Status `belum → proses`, `tgl_pengajuan` diisi, `unit_organisasi` di-snapshot dari profil.
   - Riwayat `dikirim` (atau `dikirim_ulang` + catatan balasan bila sebelumnya dikembalikan Unor).
   - Notifikasi ke Admin Unor.

### Tahap 2 — Admin Unor: Pratinjau & Administrasi Unor (`proses`)

**Halaman:** `unor:preview` → `unor:upload_dokumen`. Cakupan: pengajuan di unit organisasinya.

1. **Pratinjau** formulir dan berkas Pegawai, lalu:
   - **Lanjutkan** → `preview_unor_agree = True`, masuk ke unggah dokumen; atau
   - **Kembalikan ke Pegawai** (catatan wajib) → status `proses → belum`,
     `catatan_unor` diisi, riwayat `dikembalikan_unor`.
2. Mengunggah dokumen administrasi Unor (lihat [§4.2](#42-diunggah-admin-unor--dokumenunor)).
3. Centang pernyataan → **Teruskan ke Admin BPSDM**.
   - Status `proses → proses_bpsdm`, `tgl_masuk_bpsdm` diisi.
   - Riwayat `diteruskan_bpsdm` (atau `diteruskan_ulang_bpsdm` + catatan balasan bila sebelumnya dikembalikan BPSDM).
   - Notifikasi ke Admin BPSDM (Pegawai menerima info).

### Tahap 3 — Admin BPSDM: Pratinjau & Administrasi BPSDM (`proses_bpsdm`)

**Halaman:** `bpsdm:preview` → `bpsdm:upload_dokumen`. Cakupan: **seluruh** T2P/T2L lintas unor.

1. **Pratinjau** berkas Pegawai + Unor, lalu:
   - **Lanjutkan** → `preview_bpsdm_agree = True`; atau
   - **Kembalikan ke Admin Unor** (catatan wajib) → status `proses_bpsdm → proses`,
     `preview_unor_agree` & `preview_bpsdm_agree` di-reset, `catatan_bpsdm` diisi,
     riwayat `dikembalikan_bpsdm`.
2. Mengunggah dokumen administrasi BPSDM (lihat [§4.3](#43-diunggah-admin-bpsdm--dokumenbpsdm)).
3. Centang pernyataan → **Teruskan ke Biro PAKLN**.
   - Status `proses_bpsdm → proses_pakln`, `tgl_masuk_pakln` diisi.
   - Riwayat `diteruskan_pakln` (atau `diteruskan_ulang` + catatan balasan bila sebelumnya dikembalikan PAKLN).
   - Notifikasi ke Admin Biro PAKLN.

### Tahap 4 — Admin Biro PAKLN: Pratinjau & Administrasi PAKLN (`proses_pakln`)

**Halaman:** `pakln:preview` → `pakln:upload_dokumen`.

1. **Pratinjau** berkas Pegawai + Unor + BPSDM, lalu:
   - **Lanjutkan** → `preview_pakln_agree = True`; atau
   - **Kembalikan ke Admin BPSDM** (catatan wajib) → status `proses_pakln → proses_bpsdm`,
     `preview_bpsdm_agree` & `preview_pakln_agree` di-reset, `catatan_pakln` diisi,
     riwayat `dikembalikan_pakln`, notifikasi ke Admin BPSDM.
2. Mengunggah dokumen administrasi PAKLN (lihat [§4.4](#44-diunggah-admin-biro-pakln--dokumenpakln)).
3. Centang pernyataan → **Selesaikan Proses**.
   - Status `proses_pakln → selesai`, `tgl_selesai` diisi. **Tidak** memotong sisa cuti (PDLN = penugasan dinas).
   - Riwayat `selesai`, notifikasi ke Pegawai.

### Tahap 5 — Selesai: Unduh Hasil & Laporan PDLN (`selesai`)

**Halaman Pegawai:** `pegawai:monitor_progres`, `pegawai:pelaporan`. **Halaman PAKLN:** `pakln:pelaporan`.

1. Pegawai dapat **mengunduh** dokumen hasil: SP Setneg, Exit Permit,
   Rekomendasi Visa, SK Tugas Belajar, ND Karo PAKLN ke Sekretaris Unor
   (`_UNDUH_HASIL_PDLN`). **Paspor Dinas tidak** dapat diunduh pegawai.
2. Setelah perjalanan, Pegawai **mengunggah Laporan PDLN** → `LaporanPdln.status = menunggu`.
3. Admin Biro PAKLN **memverifikasi**:
   - **Setujui** → `disetujui`, pengajuan **tuntas** (pegawai boleh mengajukan baru).
   - **Kembalikan** (catatan wajib) → `dikembalikan`; pegawai mengunggah ulang dengan catatan balasan.

Pengajuan T2P berstatus `selesai` tetapi laporannya belum disetujui masih
dihitung "belum tuntas" — pegawai belum bisa membuat pengajuan baru.

---

## 4. Dokumen per Tahap & Pengunggahnya

Keterangan: **TS** = saat unggah diminta *Tanggal Surat*;
**F** = format tersedia di Manajemen Template (bila disediakan);
**G** = ditandai "generate" di registri, **namun generate otomatis belum
diimplementasikan** — saat ini tetap diunggah manual.

Semua dokumen di bawah **wajib** kecuali Rekomendasi Visa (kondisional).
Tombol Kirim/Teruskan/Selesai ditolak bila ada dokumen wajib yang belum
diunggah (`persyaratan.dokumen_kurang`).

### 4.1 Diunggah Pegawai — `DokumenPegawai`

| # | Kode jenis | Dokumen | Catatan |
|:-:|---|---|---|
| 1 | `loa` | Letter of Acceptance (LoA) | |
| 2 | `log` | Letter of Guarantee (LoG) | |
| 3 | `surat_pernyataan` | Surat Pernyataan sesuai ketentuan Kemensetneg | |
| 4 | `drh` | Daftar Riwayat Hidup (DRH) | |
| 5 | `ikatan_dinas` | Perjanjian Ikatan Dinas | versi pegawai (belum ttd lengkap) |
| 6 | `notadinas` | Nota Dinas Pimpinan Unit Kerja ke Sekretaris Unor | TS |

### 4.2 Diunggah Admin Unor — `DokumenUnor`

| # | Kode jenis | Dokumen | Catatan |
|:-:|---|---|---|
| 1 | `nd_sek_bpsdm` | Nota Dinas Sekretaris Unor ke Sekretaris BPSDM | TS, F |
| 2 | `surat_tugas` | Surat Tugas Pimpinan Unor | TS, F |
| 3 | `drh_ttd` | DRH ttd Pimpinan Unor | |

Dokumen Pendukung Unor (`DokumenUnorPendukung`) **tidak** dipakai untuk PDLN.

### 4.3 Diunggah Admin BPSDM — `DokumenBpsdm`

| # | Kode jenis | Dokumen | Catatan |
|:-:|---|---|---|
| 1 | `izin_prinsip` | Izin Prinsip Menteri | |
| 2 | `ikatan_dinas_ttd` | Perjanjian Ikatan Dinas ttd full / SK Tugas Belajar | G (manual) |
| 3 | `nd_kabiro_pakln` | Nota Dinas Sekretaris BPSDM ke Kepala Biro PAKLN | TS, F |

### 4.4 Diunggah Admin Biro PAKLN — `DokumenPakln`

| # | Kode jenis | Dokumen | Wajib | Catatan | Dapat diunduh Pegawai |
|:-:|---|---|:-:|---|:-:|
| 1 | `sp_setneg` | SP Setneg | ✅ | G (manual) | ✅ |
| 2 | `paspor_dinas` | Paspor Dinas | ✅ | | — |
| 3 | `exit_permit` | Exit Permit | ✅ | | ✅ |
| 4 | `visa` | Rekomendasi Visa | ◐ | Wajib bila salah satu negara tujuan `perlu_visa`; opsional bila tidak | ✅ |
| 5 | `sk_tubel` | SK Tugas Belajar | ✅ | G (manual) — **khusus T2P** | ✅ |
| 6 | `nd_karo_unor` | Nota Dinas Karo PAKLN ke Sekretaris Unor hal Penyampaian Dokumen PDLN | ✅ | TS, G (manual) | ✅ |

Dokumen Pendukung PAKLN (`DokumenPaklnPendukung`) **tidak** dipakai untuk PDLN.

### 4.5 Diunggah Pegawai setelah Selesai — `LaporanPdln`

| Dokumen | Diunggah | Diverifikasi | Catatan |
|---|---|---|---|
| Laporan PDLN (satu berkas) | Pegawai | Admin Biro PAKLN | Unggah ulang setelah dikembalikan wajib disertai catatan balasan |

### 4.6 Rekap: siapa mengunggah apa

| Aktor | Jumlah dokumen | Dokumen |
|---|:-:|---|
| Pegawai (sebelum kirim) | 6 | LoA, LoG, Surat Pernyataan, DRH, Perjanjian Ikatan Dinas, ND Pimpinan Unit Kerja |
| Admin Unor | 3 | ND Sekretaris Unor ke Sekretaris BPSDM, Surat Tugas Pimpinan Unor, DRH ttd Pimpinan Unor |
| Admin BPSDM | 3 | Izin Prinsip Menteri, Perjanjian Ikatan Dinas ttd full / SK Tubel, ND Sekretaris BPSDM ke Kabiro PAKLN |
| Admin Biro PAKLN | 5–6 | SP Setneg, Paspor Dinas, Exit Permit, (Rekomendasi Visa), SK Tugas Belajar, ND Karo PAKLN ke Sekretaris Unor |
| Pegawai (setelah selesai) | 1 | Laporan PDLN |

Dokumen tiap tahap dapat dilihat (read-only) oleh tahap berikutnya lewat
"Direktori Unggahan" di halaman Pratinjau (`persyaratan.direktori`).
Dokumen hanya bisa diunggah/dihapus selama pengajuan berada di status
tahap pemiliknya.

---

## 5. Pengembalian & Catatan

| Jalur | Aksi kembali | Status | Field penanda | Aksi kirim ulang (catatan balasan wajib) |
|---|---|---|---|---|
| Admin Unor → Pegawai | `dikembalikan_unor` | `proses → belum` | `catatan_unor` | `dikirim_ulang` |
| Admin BPSDM → Admin Unor | `dikembalikan_bpsdm` | `proses_bpsdm → proses` | `catatan_bpsdm` | `diteruskan_ulang_bpsdm` |
| Admin Biro PAKLN → Admin BPSDM | `dikembalikan_pakln` | `proses_pakln → proses_bpsdm` | `catatan_pakln` | `diteruskan_ulang` |
| Admin Biro PAKLN → Pegawai (laporan) | `laporan_dikembalikan` | (tetap `selesai`) | `LaporanPdln.catatan_pakln` | `laporan_diunggah` |

- Field penanda dikosongkan kembali saat pengajuan dikirim/diteruskan ulang.
- Dokumen yang sudah diunggah **tidak** dihapus saat dikembalikan; pihak
  penerima cukup mengganti berkas yang perlu diperbaiki.
- Pengembalian dari PAKLN pada T2P **tidak** bisa langsung ke Admin Unor
  atau Pegawai — harus berjenjang lewat BPSDM.

---

## 6. Pembatalan

- Diajukan oleh **Pegawai** atau **Admin Unor** selama pengajuan belum tuntas
  (untuk PDLN yang sudah `selesai`: selama Laporan PDLN belum disetujui).
  Draft yang belum pernah dikirim dibatalkan langsung oleh Pegawai tanpa
  persetujuan.
- Persetujuan berjenjang: **Admin Unor** (jenjang 1) → **Admin Biro PAKLN** (final).
- **Admin BPSDM bukan jenjang persetujuan** — hanya melihat daftar pembatalan
  (read-only) dan menerima notifikasi bila pengajuan sudah/sedang di tahap BPSDM.
- Selama permohonan pembatalan terbuka, semua aksi alur utama (kirim,
  teruskan, kembalikan, selesai, verifikasi laporan) **dibekukan**
  (`alur.alasan_dibekukan`).
- Bila disetujui: status → `dibatalkan`, `tgl_dibatalkan` diisi.

---

## 7. Catatan untuk Perubahan Flow

Hal-hal di implementasi saat ini yang perlu diperhatikan saat merancang flow baru:

1. **Tombol Generate belum ada.** `ikatan_dinas_ttd`, `sp_setneg`, `sk_tubel`,
   `nd_karo_unor` ditandai `aksi="generate"` tetapi UI hanya menampilkan
   "Generate otomatis menyusul" dan meminta unggah manual.
2. **SK Tugas Belajar muncul dua kali secara makna:** label `ikatan_dinas_ttd`
   di tahap BPSDM adalah "Perjanjian Ikatan Dinas ttd full / SK Tugas Belajar",
   sementara tahap PAKLN juga mewajibkan `sk_tubel`. Perlu dipastikan siapa
   penerbit SK Tubel yang sebenarnya. → Dijawab di v2: SK Tubel diunggah
   **Admin BKO** ([§8](#8-versi-lanjutan-v2--sk-tubel-oleh-admin-bko)).
3. **T2P dan T2L berbagi alur status** (`ALUR` sama) dan halaman BPSDM yang sama;
   yang berbeda hanya registri dokumen. Mengubah urutan tahap T2P berarti
   memisahkan `ALUR["T2P"]` dari `ALUR["T2L"]`.
4. Titik yang perlu ikut diubah bila urutan/aktor berubah: `alur.ALUR` & `_DESKRIPSI`
   (timeline), `persyaratan.PERSYARATAN`, view tahap terkait, `RiwayatPengajuan.Aksi`,
   `notifications/services.py`, cakupan `report.queryset_untuk`, serta test
   `pengajuan/tests_pdln.py` (`AlurTipe2Tests`).

---

## 8. Versi Lanjutan (v2) — SK Tubel oleh Admin BKO

> **Status: sudah diimplementasikan** (`pengajuan/bko.py`, `views_bko.py`, migrasi
> `pengajuan` 0020–0022). Berlaku **hanya untuk T2P**
> (Pendidikan). T2L (Pelatihan) tetap mengikuti alur v1.

### 8.1 Ringkasan perubahan

| Aspek | v1 (saat ini) | v2 (lanjutan) |
|---|---|---|
| Pengunggah SK Tugas Belajar | Admin Biro PAKLN | **Admin BKO** *(role baru)* |
| Setelah BPSDM meneruskan | Hanya ke Biro PAKLN | **Paralel** ke Biro PAKLN **dan** Admin BKO |
| Biro PAKLN memproses | Langsung | Langsung — **tidak** perlu menunggu BKO |
| Syarat PAKLN menekan **Selesai** | Semua dokumen PAKLN lengkap (termasuk `sk_tubel`) | Dokumen PAKLN lengkap **+ SK Tubel sudah diunggah Admin BKO** |
| Bila SK Tubel tidak dapat diterbitkan | — | Admin BKO **menutup pemrosesan di sisi BKO** dengan catatan alasan (terlihat semua pihak, bisa **dibuka kembali**). Admin PAKLN memilih **Lanjutkan tanpa SK Tubel** atau **Hentikan** (pembatalan) |
| Dokumen BPSDM `ikatan_dinas_ttd` | "Perjanjian Ikatan Dinas ttd full / SK Tugas Belajar" | "Perjanjian Ikatan Dinas ttd full" (SK Tubel tidak lagi di sini) |

### 8.2 Role baru: Admin BKO

| Item | Nilai |
|---|---|
| Kode role | `admin_bko` ("Admin BKO") |
| Kanal | Web |
| Cakupan data | Seluruh pengajuan **T2P** lintas unor yang sudah diteruskan BPSDM (`tgl_masuk_bko` terisi) |
| Tugas | Mengecek informasi pegawai dan data pengajuan, lalu **salah satu**: (a) mengunggah **SK Tugas Belajar**, atau (b) **menutup pemrosesan di sisi BKO** dengan catatan alasan bila SK Tubel tidak dapat diterbitkan |
| Tidak berwenang | Mengembalikan, meneruskan, atau menyelesaikan pengajuan; mengajukan/menyetujui pembatalan; mengelola master data |
| Menu | Dasbor (antrean SK Tubel), Pratinjau (read-only) + Unggah SK Tubel / Tutup Pemrosesan, Pembatalan (read-only) |

**Status track BKO** (`Pengajuan.status_bko`, terpisah dari `Pengajuan.status`):

| Nilai | Arti | Dicapai oleh |
|---|---|---|
| *(kosong)* | Track belum dibuka (belum pernah diteruskan BPSDM) | — |
| `menunggu` | Menunggu SK Tubel dari Admin BKO | BPSDM meneruskan ke PAKLN + BKO |
| `diunggah` | SK Tubel sudah diunggah | Admin BKO unggah SK Tubel |
| `ditutup` | Admin BKO menutup pemrosesan — SK Tubel tidak dapat diterbitkan; alasan di `catatan_bko` | Admin BKO **Tutup Pemrosesan** |

Transisi: `menunggu → diunggah` (unggah), `diunggah → menunggu` (hapus SK
Tubel), `menunggu → ditutup` (Tutup Pemrosesan), `ditutup → menunggu`
(**Buka Kembali**). Semua transisi hanya bisa dilakukan selama pengajuan
belum `selesai`/`dibatalkan` dan tidak sedang dalam permohonan pembatalan.

### 8.3 Diagram alur v2

```
                                                         ┌──► [Track BKO] menunggu ──unggah──► diunggah ─────┐
                                                         │                  │  ▲                              │
                                                         │      Tutup (alasan)  Buka Kembali                  │
                                                         │                  ▼  │                              │
                                                         │                 ditutup ─────────────┐             │
                                                         │                                      │             │
 [belum] ──► [proses] ──► [proses_bpsdm] ──Teruskan──────┤                                      ▼             ▼
  Pegawai    Admin Unor    Admin BPSDM     (paralel)     └──► [proses_pakln] ───────────► Admin PAKLN memilih:
                                                               Admin Biro PAKLN            • diunggah → Selesai ─────────────► [selesai]
                                                               (pratinjau & unggah         • ditutup  → Lanjutkan tanpa SK Tubel ► [selesai]
                                                                dokumen PAKLN)             • ditutup  → Hentikan (pembatalan) ──► [dibatalkan]
                                                                                           • menunggu → Selesai terkunci
```

Track BKO **bukan status pengajuan baru**. `Pengajuan.status` tetap satu
nilai (`proses_pakln`); kemajuan track BKO disimpan terpisah di
`status_bko` (lihat [§8.2](#82-role-baru-admin-bko)). Dengan begitu urutan `ALUR["T2P"]`, timeline utama, dan pengembalian
berjenjang v1 tidak berubah.

### 8.4 Langkah yang berubah

**Tahap 3 — Admin BPSDM: Teruskan (berubah)**

- Status `proses_bpsdm → proses_pakln`, `tgl_masuk_pakln` diisi (sama seperti v1).
- **Tambahan:** `tgl_masuk_bko` diisi (hanya saat pertama kali) dan
  `status_bko = menunggu`, sehingga track BKO terbuka. Notifikasi ke Admin
  Biro PAKLN **dan** Admin BKO.
- Riwayat: `diteruskan_pakln` / `diteruskan_ulang` (seperti v1), ditambah
  `diteruskan_bko` saat track BKO pertama kali dibuka.

**Tahap 4a — Admin BKO: Unggah SK Tubel (baru, paralel)**

**Halaman:** `bko:dashboard` → `bko:upload_dokumen`.

1. Dasbor menampilkan antrean T2P dengan filter *Menunggu* / *Diunggah* / *Ditutup*.
2. **Pratinjau** (read-only) informasi pegawai, data pengajuan, serta berkas
   Pegawai, Unor, dan BPSDM sebagai acuan penerbitan SK Tubel.
3. Admin BKO memilih salah satu:
   - **Unggah SK Tugas Belajar** (dengan *Tanggal Surat*) →
     `status_bko = diunggah`. Tidak ada tombol "Teruskan" — **unggahan itu
     sendiri** menyelesaikan tugas BKO. Riwayat `sk_tubel_diunggah` (status
     pengajuan tetap), notifikasi ke Admin Biro PAKLN.
   - **Tutup Pemrosesan** (catatan alasan **wajib**) bila SK Tubel tidak
     dapat diterbitkan → `status_bko = ditutup`, `catatan_bko` diisi,
     `tgl_bko_ditutup` diisi. Riwayat `ditutup_bko` beserta catatan,
     notifikasi ke **Pegawai, Admin Unor, Admin BPSDM, dan Admin Biro PAKLN**.
     Admin BKO **tidak** mengembalikan dokumen/pengajuan.
4. Selama `status_bko = diunggah` dan pengajuan belum `selesai`, Admin BKO
   masih boleh **mengganti/menghapus** SK Tubel (hapus → kembali `menunggu`).
   Setelah `selesai`, SK Tubel terkunci.
5. **Buka Kembali** (catatan wajib): bila penyebab penutupan sudah teratasi,
   Admin BKO **atau Admin Biro PAKLN** dapat membuka lagi track yang `ditutup` → `status_bko = menunggu`,
   `catatan_bko` & `tgl_bko_ditutup` dikosongkan (alasan lama tetap ada di
   riwayat). Riwayat `dibuka_ulang_bko` (aktor BKO atau PAKLN), notifikasi ke
   Pegawai, Admin Unor, Admin BPSDM, serta Admin BKO/Admin PAKLN (pihak yang
   bukan pembuka). Hanya bisa selama pengajuan belum `selesai`/`dibatalkan`.
6. Admin BKO dapat bertindak kapan pun selama track terbuka, **termasuk saat
   pengajuan sedang dikembalikan** ke BPSDM/Unor/Pegawai.

**Tahap 4b — Admin Biro PAKLN (berubah)**

1. Pratinjau, Lanjutkan, dan unggah dokumen PAKLN dapat dilakukan **tanpa
   menunggu** Admin BKO.
2. Daftar dokumen PAKLN untuk T2P **tidak lagi** memuat `sk_tubel`:
   SP Setneg, Paspor Dinas, Exit Permit, Rekomendasi Visa (◐), ND Karo PAKLN ke Sekretaris Unor.
3. Halaman unggah PAKLN menampilkan status track BKO
   (*Menunggu Admin BKO* / *Sudah diunggah — tanggal* + pratinjau /
   *Ditutup Admin BKO — alasan*).
4. Aksi penyelesaian bergantung `status_bko`:

   | `status_bko` | Pilihan Admin PAKLN |
   |---|---|
   | `menunggu` | **Selesaikan Proses** terkunci — pesan "Menunggu SK Tugas Belajar dari Admin BKO". |
   | `diunggah` | **Selesaikan Proses** seperti biasa. |
   | `ditutup` | Banner "Pemrosesan ditutup Admin BKO: <alasan>" dengan tiga pilihan:<br>• **Buka Kembali** track BKO (catatan wajib, terlihat semua pihak) → `status_bko = menunggu`, Admin BKO diminta memproses lagi SK Tubel.<br>• **Lanjutkan tanpa SK Tubel** — konfirmasi + catatan wajib → `proses_pakln → selesai`; riwayat `selesai_tanpa_sk_tubel` beserta catatan. Catatan ini **hanya terlihat oleh Admin Biro PAKLN** (tidak oleh Pegawai, Admin Unor, Admin BPSDM, maupun Admin BKO, dan tidak dimuat di notifikasi). Pegawai tidak mendapat SK Tubel di daftar unduhan.<br>• **Hentikan Pengajuan** — memakai mekanisme pembatalan yang sudah ada (lihat [§8.6](#86-pengembalian--pembatalan-pada-v2)) → `dibatalkan`. |

   Selama `ditutup`, PAKLN juga boleh menunggu (tidak memilih), mis. karena
   Admin BKO sedang menunggu perbaikan berkas lalu akan membuka kembali sendiri.
5. **Kembalikan ke Admin BPSDM** tetap tersedia seperti v1 (lihat [§8.6](#86-pengembalian--pembatalan-pada-v2)).

### 8.5 Dokumen v2 per aktor

| Aktor | Dokumen | Perubahan dari v1 |
|---|---|---|
| Pegawai | LoA, LoG, Surat Pernyataan, DRH, Perjanjian Ikatan Dinas, ND Pimpinan Unit Kerja | — |
| Admin Unor | ND Sekretaris Unor ke Sekretaris BPSDM, Surat Tugas Pimpinan Unor, DRH ttd Pimpinan Unor | — |
| Admin BPSDM | Izin Prinsip Menteri, **Perjanjian Ikatan Dinas ttd full**, ND Sekretaris BPSDM ke Kabiro PAKLN | Label `ikatan_dinas_ttd` tanpa "/ SK Tugas Belajar" |
| **Admin BKO** *(baru)* | **SK Tugas Belajar** (`sk_tubel`, TS) | Pindah dari Admin Biro PAKLN |
| Admin Biro PAKLN | SP Setneg, Paspor Dinas, Exit Permit, (Rekomendasi Visa), ND Karo PAKLN ke Sekretaris Unor | `sk_tubel` dihapus dari daftar PAKLN |
| Pegawai (setelah selesai) | Laporan PDLN | — |

Pegawai tetap dapat **mengunduh** SK Tugas Belajar saat pengajuan `selesai`
(sumbernya kini dokumen tahap BKO).

### 8.6 Pengembalian & Pembatalan pada v2

| Kejadian | Perilaku track BKO |
|---|---|
| PAKLN mengembalikan ke BPSDM (`proses_pakln → proses_bpsdm`) | SK Tubel yang sudah diunggah **tetap disimpan**. Bila masih `menunggu`, Admin BKO **tetap boleh** mengunggah atau menutup (track BKO tidak ikut mundur). |
| BPSDM mengembalikan ke Unor / Unor ke Pegawai | Sama — track BKO tidak berubah, SK Tubel tidak dihapus. |
| BPSDM meneruskan ulang ke PAKLN | Track `menunggu`/`diunggah` tidak berubah (`tgl_masuk_bko` tetap); Admin BKO hanya menerima notifikasi info. |
| Admin BKO tidak dapat menerbitkan SK Tubel | Admin BKO **Tutup Pemrosesan** dengan alasan (`status_bko = ditutup`). Admin PAKLN memilih Lanjutkan tanpa SK Tubel atau Hentikan. |
| Penyebab penutupan teratasi (mis. berkas diperbaiki lewat pengembalian) | Admin BKO atau Admin PAKLN **Buka Kembali** (`ditutup → menunggu`), lalu Admin BKO unggah SK Tubel seperti biasa. |
| Pembatalan | Admin BKO **bukan** jenjang persetujuan; hanya read-only + notifikasi bila track BKO sudah dibuka. Selama pembatalan terbuka, unggah/tutup di BKO ikut **dibekukan**. |

**Catatan penutupan BKO terlihat oleh semua pihak terlibat.** Berbeda dari
aturan visibilitas v1 (Pegawai hanya melihat catatan jalur Pegawai ↔ Unor),
`catatan_bko` dan riwayat `ditutup_bko` ditampilkan kepada **Pegawai, Admin
Unor, Admin BPSDM, dan Admin Biro PAKLN** — di halaman Pratinjau/Unggah
masing-masing, di Monitor Progres pegawai, dan di isi notifikasi.

**Tindak lanjut setelah track `ditutup`** (keputusan #7 dan #8, [§8.9](#89-keputusan--pertanyaan-terbuka-v2)):
fleksibel, diputuskan Admin Biro PAKLN —

1. **Lanjutkan tanpa SK Tubel** → pengajuan `selesai` (lihat Tahap 4b);
   catatannya internal Admin Biro PAKLN.
2. **Hentikan Pengajuan** dengan mekanisme pembatalan yang sudah ada.
   Karena di v1 hanya Pegawai/Admin Unor yang dapat mengajukan pembatalan
   dan Admin PAKLN adalah pemutus akhir, diputuskan (#9): tombol ini hanya
   muncul saat `status_bko = ditutup`, membuat `PermohonanPembatalan` dengan
   `diajukan_role = admin_pakln`, alasan terisi dari `catatan_bko` (boleh
   ditambah), dan **langsung disetujui** (`dibatalkan`, `tgl_dibatalkan`) tanpa
   jenjang Admin Unor. Pegawai/Admin Unor tetap boleh mengajukan pembatalan
   lewat jalur biasa.
3. **Buka Kembali** track BKO sendiri, atau **menunggu** Admin BKO membukanya,
   setelah penyebab penutupan teratasi.

Track BKO **tidak** dibuka ulang otomatis — termasuk bila pengajuan
dikembalikan lalu diteruskan ulang; pembukaan selalu lewat aksi **Buka
Kembali** oleh Admin BKO atau Admin Biro PAKLN.

### 8.7 Timeline Proses

Lima tahap utama v1 tetap. Pada tahap **Dalam Proses Biro PAKLN**
ditambahkan sub-keterangan track paralel:

- "SK Tugas Belajar (Admin BKO): Menunggu",
- "SK Tugas Belajar (Admin BKO): Diunggah dd Mmm yyyy", atau
- "Pemrosesan ditutup Admin BKO (dd Mmm yyyy): <alasan>" — ditampilkan
  dengan penanda peringatan, terlihat juga oleh Pegawai.

Pada tahap **Selesai**, bila diselesaikan tanpa SK Tubel, ditampilkan
keterangan "Diselesaikan tanpa SK Tugas Belajar" (tanpa catatan — catatan
Admin PAKLN hanya tampil bagi Admin Biro PAKLN).

### 8.8 Dampak ke kode (perkiraan)

| Area | Perubahan |
|---|---|
| `accounts.User.Role` | Tambah `admin_bko`; helper `is_admin_bko()`; seed demo user. |
| `pengajuan/models.py` | `Pengajuan`: `tgl_masuk_bko` (DateField, null), `status_bko` (CharField choices `menunggu`/`diunggah`/`ditutup`, blank), `catatan_bko` (TextField, blank), `tgl_bko_ditutup` (DateField, null). Model `DokumenBko` (pola sama dengan `DokumenBpsdm`, jenis `sk_tubel`). Aksi riwayat `diteruskan_bko`, `sk_tubel_diunggah`, `ditutup_bko`, `dibuka_ulang_bko`, `selesai_tanpa_sk_tubel`. Label `DokumenBpsdm.IKATAN_DINAS_TTD`. Hapus `DokumenPakln.Jenis.SK_TUBEL`. |
| Migrasi data | Sistem belum rilis (data QC) → **semua** T2P memakai pola v2. Data migration: pindahkan `DokumenPakln(jenis="sk_tubel")` ke `DokumenBko`; untuk T2P yang sudah pernah diteruskan BPSDM (`tgl_masuk_pakln` terisi) isi `tgl_masuk_bko` dan `status_bko` (`diunggah` bila SK Tubel ada, selain itu `menunggu`). |
| `pengajuan/riwayat.py` | Pengecualian visibilitas: (1) catatan `ditutup_bko` & `dibuka_ulang_bko` terlihat Pegawai; (2) catatan `selesai_tanpa_sk_tubel` **hanya** terlihat `admin_pakln` (entri riwayatnya tetap tampil bagi pihak lain, tanpa catatan). Tambah label peran `admin_bko`. |
| `pengajuan/pembatalan.py` | Jalur **Hentikan Pengajuan** oleh Admin PAKLN (hanya saat `status_bko = ditutup`): buat permohonan `diajukan_role = admin_pakln` yang langsung `disetujui`. |
| `pengajuan/persyaratan.py` | Tahap baru `"bko"` di `TAHAP_MODEL/RELATED/LABEL`; `("T2P","bko"): [Syarat("sk_tubel", tanggal_surat=True)]`; hapus `sk_tubel` dari `("T2P","pakln")`; `direktori` menampilkan dokumen BKO. |
| `pengajuan/views_bpsdm.py` `_teruskan` | Saat pertama kali: isi `tgl_masuk_bko`, `status_bko = menunggu`, catat riwayat, kirim notifikasi ke BKO. |
| `pengajuan/views_bko.py` + `urls_bko.py` *(baru)* | Dasbor, pratinjau read-only, unggah/hapus SK Tubel (sinkron `status_bko`), **Tutup Pemrosesan** & **Buka Kembali** dengan catatan wajib, pembatalan read-only. |
| `pengajuan/views_pakln.py` | `_selesaikan` T2P: tolak bila `menunggu`; izinkan bila `diunggah`; bila `ditutup` hanya lewat aksi **Lanjutkan tanpa SK Tubel** (catatan wajib). Aksi baru **Hentikan Pengajuan** dan **Buka Kembali** track BKO (catatan wajib). Logika buka kembali dipakai bersama dengan `views_bko`. Tampilkan status track BKO di halaman unggah. |
| Halaman Pratinjau/Unggah Unor, BPSDM, PAKLN + Monitor Progres Pegawai | Tampilkan banner "Pemrosesan ditutup Admin BKO" + `catatan_bko` bila `status_bko = ditutup`. |
| `pengajuan/views_pegawai.py` | `unduh_hasil` SK Tubel diambil dari `DokumenBko`. |
| `pengajuan/report.py` | `queryset_untuk` untuk role `admin_bko`; kolom export "Tgl Masuk BKO", "Tgl SK Tubel". |
| `pengajuan/alur.py` | Sub-keterangan track BKO di `timeline`; `alasan_dibekukan` juga dipakai unggah BKO. |
| `notifications/services.py` | Event baru: diteruskan ke BKO; SK Tubel diunggah (ke PAKLN); **pemrosesan ditutup** oleh BKO & **dibuka kembali** oleh BKO/PAKLN (ke Pegawai, Admin Unor, Admin BPSDM, Admin PAKLN, dengan catatan); info pembatalan ke BKO. |
| `pengajuan/tests_pdln.py` | Test: PAKLN bisa lanjut tanpa SK Tubel; Selesai ditolak saat `menunggu`; saat `ditutup` hanya bisa lewat Lanjutkan tanpa SK Tubel (catatan wajib) atau Hentikan; tutup/buka kembali tanpa catatan ditolak; catatan tutup terlihat Pegawai; catatan Lanjutkan tanpa SK Tubel hanya terlihat Admin PAKLN; buka kembali bisa oleh BKO dan PAKLN, ditolak untuk role lain dan setelah `selesai`/`dibatalkan`; BKO tidak bisa mengakses T2L; pengembalian tidak menghapus SK Tubel; BKO bisa unggah saat pengajuan dikembalikan. |

### 8.9 Keputusan & pertanyaan terbuka v2

**Keputusan (dijawab pemilik proses, 9 Okt 2026):**

| # | Pertanyaan | Keputusan |
|:-:|---|---|
| 1 | Apakah Admin BKO dibatasi per unit organisasi? | **Tidak** — satu cakupan untuk semua unor. |
| 2 | Apakah Admin BKO bisa mengembalikan pengajuan bila berkas tidak memadai? | **Tidak mengembalikan.** Admin BKO hanya mengecek informasi pegawai & data pengajuan lalu mengunggah SK Tubel. Bila SK Tubel tidak dapat diterbitkan, Admin BKO **menutup pemrosesan di sisi BKO** dengan catatan alasan yang terlihat oleh Pegawai, Admin Unor, Admin BPSDM, dan Admin PAKLN. |
| 3 | Apakah SK Tubel boleh diunggah saat pengajuan sedang dikembalikan ke BPSDM/Unor? | **Boleh.** |
| 4 | Apakah ada dokumen PAKLN lain (selain tombol Selesai) yang harus menunggu SK Tubel? | **Tidak ada.** |
| 5 | Apakah T2L (Pelatihan) juga memakai Admin BKO? | **Tidak.** |
| 6 | Pengajuan T2P yang sedang berjalan saat v2 dirilis ikut pola mana? | **Pola baru (v2)** — sistem belum rilis, data masih data QC. SK Tubel diunggah Admin BKO. |
| 7 | Setelah Admin BKO menutup pemrosesan, apa yang terjadi pada pengajuan? | **Fleksibel — dipilih Admin PAKLN:** tetap melanjutkan (selesai tanpa SK Tubel) atau menghentikan dengan mekanisme pembatalan yang sudah ada. |
| 8 | Bolehkah track BKO dibuka lagi setelah ditutup? | **Boleh.** |
| 9 | Bagaimana Admin PAKLN **menghentikan** pengajuan setelah track BKO ditutup? | **Admin PAKLN mengajukan sekaligus memutus:** permohonan pembatalan `diajukan_role = admin_pakln` langsung disetujui (tanpa jenjang Admin Unor), hanya tersedia saat `status_bko = ditutup`. Pegawai/Admin Unor tetap dapat mengajukan pembatalan lewat jalur biasa. |
| 10 | Siapa yang boleh **membuka kembali** track BKO? | **Admin BKO dan Admin Biro PAKLN**, dengan catatan wajib. |
| 11 | Siapa yang melihat catatan **Lanjutkan tanpa SK Tubel**? | **Hanya Admin Biro PAKLN.** Catatan tetap wajib diisi sebagai jejak internal. |

Tidak ada pertanyaan terbuka tersisa untuk v2.