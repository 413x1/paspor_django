# Bisnis Proses PDLN (Perjalanan Dinas Luar Negeri)

> **Status:** rancangan — acuan integrasi alur PDLN ke PASPOR (belum diimplementasikan).
> **Sumber:** mockup `20261005_PASPOR — Tahap 2_ PDLN Tipe 1–3 + PINTAR.html`.
> **Pengguna:** Pegawai, Admin Unor, Admin BPSDM (baru), Admin Biro PAKLN.
> **Terkait:** [RIWAYAT_PEMROSESAN_PENGAJUAN.MD](RIWAYAT_PEMROSESAN_PENGAJUAN.MD),
> [SKENARIO_NOTIFIKASI_SURAT.md](SKENARIO_NOTIFIKASI_SURAT.md),
> [MANAJEMEN_TEMPLATE.MD](MANAJEMEN_TEMPLATE.MD),
> [AUTO_CALCULATE_DAYS.MD](AUTO_CALCULATE_DAYS.MD).

## Daftar Isi

1. [Ringkasan](#1-ringkasan)
2. [Jenis Perjalanan & Tipe PDLN](#2-jenis-perjalanan--tipe-pdln)
3. [Aktor & Hak Akses](#3-aktor--hak-akses)
4. [Alur Proses per Tipe](#4-alur-proses-per-tipe)
5. [Formulir Pengajuan per Tipe](#5-formulir-pengajuan-per-tipe)
6. [Persyaratan Dokumen per Tahap](#6-persyaratan-dokumen-per-tahap)
7. [Pengembalian & Catatan Dua Arah](#7-pengembalian--catatan-dua-arah)
8. [Struktur Data & Database](#8-struktur-data--database)
9. [Halaman & Navigasi](#9-halaman--navigasi)
10. [Halaman Report (Dinas & Non-Dinas)](#10-halaman-report-dinas--non-dinas)
11. [Notifikasi](#11-notifikasi)
12. [Integrasi Eksternal (Aplikasi PINTAR)](#12-integrasi-eksternal-aplikasi-pintar)
13. [Tahapan Implementasi](#13-tahapan-implementasi)
14. [Keputusan & Pertanyaan Terbuka](#14-keputusan--pertanyaan-terbuka)
15. [Bahan Pertimbangan untuk Diskusi Lanjutan](#15-bahan-pertimbangan-untuk-diskusi-lanjutan)

---

## 1. Ringkasan

PASPOR saat ini hanya menangani **Perjalanan Luar Negeri Non-Kedinasan**
(Tahap 1): Pegawai → Admin Unor → Admin Biro PAKLN → Selesai, dengan
model tunggal `Pengajuan` dan status `belum → proses → proses_pakln → selesai`.

Tahap 2 menambahkan **PDLN (Perjalanan Dinas Luar Negeri)** dengan empat
tipe, satu role baru (**Admin BPSDM**), dan menu akun baru (Profil,
Pelaporan PDLN). Prinsip integrasinya:

- **Satu siklus pengajuan untuk semua jenis.** PDLN memakai model
  `Pengajuan` yang sama (status, riwayat, notifikasi, dasbor, export),
  dibedakan oleh field `jenis_perjalanan` dan `tipe_pdln`. Detail khusus
  PDLN disimpan di tabel pendamping `DetailPdln` (1:1).
- **Alur ditentukan oleh tipe.** Tipe 1, Tipe 3, dan Non-Dinas melewati
  Unor → PAKLN; Tipe 2 (Pendidikan & Pelatihan) menyisipkan tahap
  **BPSDM** di antara Unor dan PAKLN.
- **Persyaratan dokumen berbasis registri.** Daftar dokumen wajib per
  (tipe, tahap) didefinisikan di satu tempat di kode, bukan tersebar di
  view/template.
- **Report menyatukan Dinas & Non-Dinas** dengan filter jenis/tipe, dan
  dibatasi cakupan masing-masing role.
- **Pembatalan berjenjang untuk semua jenis.** Pegawai atau Admin Unor
  dapat meminta pembatalan dengan alasan wajib; berlaku setelah disetujui
  Admin Unor lalu Admin Biro PAKLN ([§4.5](#45-pembatalan-perjalanan-mekanisme-sementara)).

---

## 2. Jenis Perjalanan & Tipe PDLN

| Jenis | Tipe | Kode tipe | Contoh kegiatan | Melibatkan BPSDM | Prefiks kode pengajuan |
|---|---|---|---|---|---|
| Non-Dinas | — | — | Ibadah, wisata, keperluan pribadi | Tidak | `PSP-<tahun>-NNNN` (tetap) |
| PDLN | Tipe 1 | `T1` | Pertemuan bilateral/regional/multilateral, pameran/expo, advis teknis, pendampingan | Tidak | `PDLN-<tahun>-T1-NNNN` |
| PDLN | Tipe 2 — Pendidikan | `T2P` | Tugas belajar Master/Doctoral | **Ya** | `PDLN-<tahun>-T2P-NNNN` |
| PDLN | Tipe 2 — Pelatihan | `T2L` | Short course, seminar/lokakarya, workshop, simposium/konferensi | **Ya** | `PDLN-<tahun>-T2L-NNNN` |
| PDLN | Tipe 3 — Penugasan Khusus | `T3` | Penugasan atas disposisi Menteri | Tidak | `PDLN-<tahun>-T3-NNNN` |

- Nomor urut `NNNN` dihitung **per prefiks per tahun** (perluasan
  `Pengajuan._generate_kode`).
- Tipe 3 **diajukan oleh Pegawai** dan mengikuti alur yang **sama persis**
  dengan Tipe 1; perbedaannya hanya pada label dokumen Unor ("Izin
  Prinsip/Disposisi Menteri").
- Pemilihan jenis di UI dua langkah (modal "Tambah Usulan Baru"):
  1. Pilih **PDLN** atau **Perjalanan Luar Negeri Non-Kedinasan**.
  2. Jika PDLN → pilih **Tipe 1 / Tipe 2 Pendidikan / Tipe 2 Pelatihan / Tipe 3**.

### 2.1 Aturan satu pengajuan aktif

Pegawai hanya boleh memiliki **satu pengajuan perjalanan luar negeri
aktif** pada satu waktu — **lintas jenis dan tipe** (PDLN maupun
Non-Dinas). Pengajuan baru baru bisa dibuat setelah pengajuan sebelumnya
mencapai **tahap akhir**:

| Jenis | Tahap akhir (pengajuan dianggap tuntas) |
|---|---|
| Non-Dinas | Pengajuan disetujui Admin Biro PAKLN (`status = selesai`). |
| PDLN (semua tipe) | `status = selesai` **dan** Laporan PDLN telah **disetujui** Admin Biro PAKLN ([§4.4](#44-pelaporan-pdln)). |
| Semua | `status = dibatalkan` — permohonan pembatalan telah disetujui Admin Biro PAKLN ([§4.5](#45-pembatalan-perjalanan-mekanisme-sementara)). |

Implementasi: ganti `_active_pengajuan` di
[views_pegawai.py](../../pengajuan/views_pegawai.py) dengan satu helper
`pengajuan_belum_tuntas(pegawai)` yang dipakai Beranda (tombol "Tambah
Usulan Baru" dinonaktifkan dengan keterangan alasannya) **dan**
divalidasi ulang di server saat formulir baru disimpan:

```python
def pengajuan_belum_tuntas(pegawai):
    """Pengajuan terbaru pegawai yang belum mencapai tahap akhir, atau None."""
    qs = Pengajuan.objects.filter(pegawai=pegawai).exclude(status="dibatalkan")
    nondinas = qs.filter(jenis_perjalanan="nondinas").exclude(status="selesai")
    pdln = qs.filter(jenis_perjalanan="pdln").exclude(
        status="selesai", laporan_pdln__status="disetujui",
    )
    return (nondinas | pdln).order_by("-created_at").first()
```

Draft (`status = belum`) juga dihitung aktif — pegawai melanjutkan draft
tersebut alih-alih membuat yang baru (perilaku yang sama dengan sekarang).

---

## 3. Aktor & Hak Akses

| Role | Kode role | Kanal | Cakupan data | Tanggung jawab |
|---|---|---|---|---|
| Pegawai | `pegawai` | Mobile (Satu Bravo) & Web | Pengajuan miliknya | Isi formulir, unggah dokumen, kirim/kirim ulang, pantau progres, unggah (ulang) Laporan PDLN, **ajukan/tarik permohonan pembatalan**, kelola Profil & data paspor |
| Admin Unor | `admin_unor` | Web | Pengajuan pegawai di **unit organisasinya** (`views_unor._scoped`) — semua jenis & tipe | Pratinjau, administrasi Unor, teruskan ke BPSDM (T2) / PAKLN (T1, T3, Non-Dinas), kembalikan ke pegawai; **ajukan pembatalan & persetujuan pembatalan jenjang 1** |
| Admin BPSDM *(baru)* | `admin_bpsdm` | Web | **Seluruh** pengajuan **Tipe 2** (T2P, T2L), lintas unor | Pratinjau, administrasi BPSDM (Izin Prinsip Menteri, Ikatan Dinas/SK Tubel), teruskan ke PAKLN, kembalikan ke Unor |
| Admin Biro PAKLN | `admin_pakln` | Web | Seluruh pengajuan, semua jenis | Pratinjau, administrasi akhir (SP Setneg, Paspor Dinas, Exit Permit, Visa, ND Karo), selesaikan, kembalikan ke tahap sebelumnya; **verifikasi (setujui/kembalikan) Laporan PDLN**; **persetujuan pembatalan jenjang akhir**; kelola master data (termasuk penanda negara wajib visa) |

Catatan:

- Admin BPSDM **tidak** mengelola master data dan **tidak** punya menu
  Pelaporan PDLN maupun Export pada mockup; tetap disarankan diberi Export
  terbatas Tipe 2 (lihat [§10](#10-halaman-report-dinas--non-dinas)).
- Semua admin mendapat menu **Profil** (data e-HRM + unggah SK Penugasan)
  dan placeholder **Ralat/Perubahan** ("akan dikembangkan"). Menu
  **Pembatalan** diisi mekanisme sementara [§4.5](#45-pembatalan-perjalanan-mekanisme-sementara);
  Admin BPSDM hanya menerima informasi (bukan jenjang persetujuan).

---

## 4. Alur Proses per Tipe

### 4.1 Status

`Pengajuan.Status` ditambah dua nilai:

| Status | Label | Dipakai oleh |
|---|---|---|
| `belum` | Belum Diajukan | Semua |
| `proses` | Dalam Proses Unor | Semua |
| `proses_bpsdm` *(baru)* | Dalam Proses BPSDM | T2P, T2L |
| `proses_pakln` | Dalam Proses Biro PAKLN | Semua |
| `selesai` | Selesai | Semua |
| `dibatalkan` *(baru)* | Dibatalkan | Semua — status final, bisa dicapai dari status mana pun lewat [§4.5](#45-pembatalan-perjalanan-mekanisme-sementara); **tidak** termasuk urutan `ALUR` |

Urutan tahap **per tipe** (sumber tunggal, mis. `pengajuan/alur.py`):

```python
ALUR = {
    "nondinas": ["belum", "proses", "proses_pakln", "selesai"],
    "T1":       ["belum", "proses", "proses_pakln", "selesai"],
    "T3":       ["belum", "proses", "proses_pakln", "selesai"],
    "T2P":      ["belum", "proses", "proses_bpsdm", "proses_pakln", "selesai"],
    "T2L":      ["belum", "proses", "proses_bpsdm", "proses_pakln", "selesai"],
}
```

`Pengajuan.timeline` dan `riwayat.timeline_dengan_riwayat` (saat ini
memakai daftar 4 tahap tetap) harus membaca urutan dari `ALUR`, sehingga
Timeline Proses Tipe 2 otomatis menampilkan 5 tahap.

### 4.2 Diagram alur

**Non-Dinas, PDLN Tipe 1, PDLN Tipe 3**

```
            ┌──── DIKEMBALIKAN_UNOR (catatan → Pegawai) ────┐
            ▼                                               │
 [belum] ──DIKIRIM / DIKIRIM_ULANG──► [proses] ──DITERUSKAN_PAKLN / DITERUSKAN_ULANG──► [proses_pakln] ──SELESAI──► [selesai]
  Pegawai                               Admin Unor  ▲                                       │ Admin PAKLN
                                                    └── DIKEMBALIKAN_PAKLN (catatan → Unor) ┘
```

**PDLN Tipe 2 (Pendidikan & Pelatihan)**

```
 [belum] ──DIKIRIM──► [proses] ──DITERUSKAN_BPSDM──► [proses_bpsdm] ──DITERUSKAN_PAKLN──► [proses_pakln] ──SELESAI──► [selesai]
  Pegawai     ▲        Admin Unor     ▲                Admin BPSDM          ▲                 Admin PAKLN
              │                       │                                     │
              └─ DIKEMBALIKAN_UNOR ───┘◄── DIKEMBALIKAN_BPSDM ──────────────┘◄── DIKEMBALIKAN_PAKLN (ke BPSDM)
```

Aturan umum: **pengembalian selalu ke tahap tepat sebelumnya**
(PAKLN → BPSDM pada Tipe 2, PAKLN → Unor pada tipe lain, BPSDM → Unor,
Unor → Pegawai).

### 4.3 Langkah per tahap

| # | Tahap | Aktor | Langkah | Hasil / transisi |
|---|---|---|---|---|
| 1 | Formulir | Pegawai | Pilih jenis & tipe → isi formulir ([§5](#5-formulir-pengajuan-per-tipe)) → centang "data dan formulir yang diisi telah benar" → Simpan | `form_saved = True` |
| 2 | Unggah Dokumen | Pegawai | Unggah seluruh dokumen wajib tahap Pegawai → centang pernyataan kelengkapan → **Kirim ke Admin Unor** (kirim ulang wajib catatan) | `belum → proses`, `tgl_pengajuan` |
| 3 | Pratinjau Unor | Admin Unor | Tinjau formulir & berkas → centang "ditinjau dan sesuai" **atau** Kembalikan ke Pegawai (catatan wajib) | `preview_unor_agree` / `proses → belum` |
| 4 | Administrasi Unor | Admin Unor | Unggah dokumen wajib tahap Unor → centang pernyataan → **Teruskan** ke BPSDM (T2) atau PAKLN (lainnya) | `proses → proses_bpsdm` (`tgl_masuk_bpsdm`) / `proses → proses_pakln` (`tgl_masuk_pakln`) |
| 5 | Pratinjau BPSDM *(T2)* | Admin BPSDM | Tinjau berkas Pegawai & Unor → centang **atau** Kembalikan ke Unor | `preview_bpsdm_agree` / `proses_bpsdm → proses` |
| 6 | Administrasi BPSDM *(T2)* | Admin BPSDM | Unggah Izin Prinsip Menteri, (T2P) Perjanjian Ikatan Dinas/SK Tubel, ND Sekretaris BPSDM → **Teruskan ke PAKLN** | `proses_bpsdm → proses_pakln` (`tgl_masuk_pakln`) |
| 7 | Pratinjau PAKLN | Admin PAKLN | Tinjau seluruh berkas → centang **atau** Kembalikan ke tahap sebelumnya | `preview_pakln_agree` / mundur 1 tahap |
| 8 | Administrasi PAKLN | Admin PAKLN | Unggah/generate SP Setneg, Paspor Dinas, Exit Permit, Rekomendasi Visa, ND Karo (T2P: + SK Tugas Belajar) → **Selesai** | `proses_pakln → selesai`, `tgl_selesai` |
| 9 | Pelaporan *(PDLN)* | Pegawai | Setelah `selesai`, unggah **Laporan PDLN**; unggah ulang (dengan catatan balasan) bila dikembalikan | `LaporanPdln.status = menunggu` |
| 10 | Verifikasi Laporan *(PDLN)* | Admin PAKLN | Tinjau laporan → **Setujui** atau **Kembalikan** (catatan wajib) | `disetujui` → pengajuan **tuntas** ([§2.1](#21-aturan-satu-pengajuan-aktif)) / `dikembalikan` |

Setiap transisi dicatat lewat `riwayat.catat(...)` di dalam
`transaction.atomic()` yang sama dengan `pengajuan.save()`, sesuai pola
[RIWAYAT_PEMROSESAN_PENGAJUAN.MD §5](RIWAYAT_PEMROSESAN_PENGAJUAN.MD#5-pencatatan-riwayat).

### 4.4 Pelaporan PDLN

Untuk PDLN, `status = selesai` belum berarti tuntas: pegawai wajib
melaporkan perjalanannya dan laporan itu harus **disetujui Admin Biro
PAKLN**. Siklus laporan berjalan di dalam status `selesai` (status
`Pengajuan` tidak berubah):

```
 (belum ada) ──UNGGAH──► [menunggu] ──SETUJUI──► [disetujui]   ← tahap akhir PDLN
                            │   ▲
                 KEMBALIKAN │   │ UNGGAH ULANG (catatan balasan wajib)
                            ▼   │
                        [dikembalikan]
```

- Unggah hanya bisa dilakukan bila pengajuan `selesai` (disarankan juga
  setelah `tgl_kembali`, lihat [§14](#14-keputusan--pertanyaan-terbuka)).
- Kembalikan wajib catatan; unggah ulang wajib catatan balasan — pola
  catatan dua arah yang sama dengan [§7](#7-pengembalian--catatan-dua-arah).
- Setiap aksi dicatat di `RiwayatPengajuan` dengan
  `status_dari = status_ke = selesai` (aksi `laporan_diunggah`,
  `laporan_dikembalikan`, `laporan_disetujui`), sehingga tampil di tahap
  **Selesai** pada Timeline Proses.
- Timeline Proses PDLN menampilkan sub-status laporan pada tahap Selesai
  ("Menunggu Laporan", "Menunggu Verifikasi", "Laporan Dikembalikan", "Tuntas").

### 4.5 Pembatalan Perjalanan (mekanisme sementara)

> Mekanisme pembatalan final belum dirumuskan. Bagian ini adalah aturan
> **interim** yang berlaku untuk **Non-Dinas dan semua tipe PDLN**, dan
> akan diganti bila ketentuan resmi sudah ada. Implementasikan secara
> terpisah dari alur utama (model & view sendiri) agar mudah diganti.

**Aturan dasar**

| Aspek | Aturan |
|---|---|
| Yang dapat mengajukan | **Pegawai** (pengajuan miliknya) atau **Admin Unor** (pengajuan di unit organisasinya). Admin BPSDM & Admin PAKLN tidak mengajukan. |
| Alasan | **Wajib** diisi saat mengajukan (teks, tidak boleh kosong). |
| Jenjang persetujuan | **Admin Unor → Admin Biro PAKLN**. Bila diajukan oleh Admin Unor, pengajuannya sekaligus dihitung sebagai persetujuan jenjang Unor, sehingga langsung menunggu Admin PAKLN. |
| Keputusan | Setuju: catatan opsional. **Tolak: catatan wajib.** |
| Kapan boleh diajukan | Setelah pengajuan **pernah dikirim** (`tgl_pengajuan` terisi) dan selama belum tuntas/batal — termasuk saat `belum` karena dikembalikan, `proses`, `proses_bpsdm`, `proses_pakln`, dan `selesai` (lihat [§14](#14-keputusan--pertanyaan-terbuka) untuk batas waktu). |
| Draft yang belum pernah dikirim | Pegawai dapat **membatalkan langsung** tanpa persetujuan (alasan tetap wajib, tercatat di riwayat). |
| Permohonan terbuka | Maksimal **satu** per pengajuan. Setelah ditolak/ditarik, boleh mengajukan lagi. |
| Menarik permohonan | Pengaju dapat menarik permohonannya selama belum diputus Admin PAKLN. |
| Selama permohonan berjalan | Pengajuan **dibekukan**: aksi alur utama (kirim, teruskan, kembalikan, selesai, unggah/verifikasi laporan) nonaktif bagi semua aktor; tampil banner "Permohonan pembatalan sedang diproses". |
| Hasil disetujui | `Pengajuan.status = dibatalkan`, `tgl_dibatalkan` terisi; pengajuan dianggap **tuntas** ([§2.1](#21-aturan-satu-pengajuan-aktif)) sehingga pegawai dapat mengajukan perjalanan baru; Laporan PDLN tidak diperlukan; seluruh dokumen tetap tersimpan sebagai arsip. |
| Hasil ditolak/ditarik | Permohonan ditutup; pengajuan **melanjutkan alur dari status semula** (status tidak pernah berubah selama permohonan). |
| Visibilitas | Alasan dan catatan keputusan terlihat oleh **semua pihak** yang berhak mengakses pengajuan, termasuk Pegawai (berbeda dengan catatan Unor↔PAKLN pada [§7](#7-pengembalian--catatan-dua-arah)). |
| Admin BPSDM | Bukan jenjang persetujuan; menerima notifikasi bila pengajuan Tipe 2 yang dimintakan pembatalan sedang/sudah melewati BPSDM. |

**Siklus permohonan**

```
 Diajukan Pegawai:
   AJUKAN ──► [menunggu_unor] ──SETUJU (Admin Unor)──► [menunggu_pakln] ──SETUJU (Admin PAKLN)──► [disetujui] ⇒ Pengajuan.status = dibatalkan

 Diajukan Admin Unor (jenjang Unor dianggap terpenuhi):
   AJUKAN ─────────────────────────────────────────► [menunggu_pakln] ──SETUJU (Admin PAKLN)──► [disetujui] ⇒ Pengajuan.status = dibatalkan

 Dari [menunggu_unor] / [menunggu_pakln]:
   TOLAK (catatan wajib)  ──► [ditolak]   ⇒ alur utama berlanjut dari status semula
   TARIK (oleh pengaju)   ──► [ditarik]   ⇒ alur utama berlanjut dari status semula
```

**Pencatatan riwayat** — setiap langkah dicatat di `RiwayatPengajuan`
dengan `status_dari = status_ke = <status pengajuan saat itu>`, kecuali
persetujuan akhir yang `status_ke = dibatalkan`. Aksi baru:
`pembatalan_diajukan`, `pembatalan_ditarik`, `pembatalan_disetujui_unor`,
`pembatalan_ditolak_unor`, `pembatalan_ditolak_pakln`, `dibatalkan`.
Alasan/catatan disimpan di kolom `catatan`; `boleh_lihat_pesan` membuka
aksi-aksi pembatalan untuk semua role.

**Timeline Proses** — pengajuan `dibatalkan` menampilkan tahap-tahap
yang sudah dilalui seperti biasa, lalu penanda akhir **"Dibatalkan"**
(tanggal + alasan) menggantikan tahap yang belum dilalui. Permohonan yang
sedang berjalan/ditolak tampil sebagai entri riwayat pada tahap saat
permohonan diajukan.

---

## 5. Formulir Pengajuan per Tipe

Data pegawai (Nama, NIP, Jabatan, Pangkat, Unit Kerja, Unit Organisasi)
**otomatis** dari `PegawaiProfile`, read-only, sama seperti Non-Dinas.

| Field | Non-Dinas | T1 / T3 | T2 Pendidikan | T2 Pelatihan | Disimpan di |
|---|---|---|---|---|---|
| Kategori perjalanan | Ibadah, Keperluan Pribadi, Wisata, Lainnya | Pertemuan Bilateral/Regional/Multilateral, Pameran/Expo, Pemberian Advis Teknis, Pendampingan | Master, Doctoral | Short Course-Training, Seminar/Lokakarya, Workshop, Simposium/Konferensi Internasional | `Pengajuan.kategori` (FK master) |
| Maksud perjalanan | ✅ | — | — | — | `Pengajuan.maksud` |
| Nama beasiswa (Aplikasi PINTAR) | — | — | ✅ droplist | ✅ droplist | `DetailPdln.beasiswa_*` |
| Penyelenggara | — | ✅ | — | ✅ | `DetailPdln.penyelenggara` |
| Perguruan tinggi | — | — | ✅ | — | `DetailPdln.perguruan_tinggi` |
| Negara tujuan | ✅ (M2M) | ✅ | ✅ | ✅ | `Pengajuan.tujuan_negara` |
| Kota tujuan | — | ✅ | ✅ | ✅ | `DetailPdln.kota_tujuan` |
| Tgl keberangkatan / kepulangan | ✅ | ✅ | ✅ | ✅ | `Pengajuan.tgl_berangkat/tgl_kembali` |
| Tgl mulai / selesai kegiatan | — | Agenda (sesuai undangan) | Perkuliahan | Pelatihan | `DetailPdln.tgl_mulai_kegiatan/tgl_selesai_kegiatan` |
| Sumber pembiayaan | Pribadi, Sponsor/Pihak Ketiga, Lainnya | DIPA Kementerian PU, DIPA K/L Lain, Donor Penyelenggara | DIPA Kementerian PU, DIPA K/L Lain, Beasiswa LPDP, Beasiswa/Donor LN, Beasiswa Lainnya | DIPA Kementerian PU, DIPA K/L Lain, Beasiswa/Donor LN, Beasiswa Lainnya | `Pengajuan.sumber_pembiayaan` (FK master) |
| Jumlah hari kerja / kalender | ✅ otomatis | otomatis (informasi, untuk report) | otomatis | otomatis | `Pengajuan.jumlah_hari_kerja` |
| Cek sisa cuti | ✅ (tolak bila melebihi) | — (dinas, bukan cuti) | — | — | — |
| Pernyataan kebenaran data | — | ✅ wajib | ✅ wajib | ✅ wajib | `DetailPdln.pernyataan_benar` |

Validasi tambahan (server-side):

- `tgl_kembali ≥ tgl_berangkat`; `tgl_selesai_kegiatan ≥ tgl_mulai_kegiatan`.
- Periode kegiatan **berada di dalam** periode perjalanan
  (`tgl_berangkat ≤ tgl_mulai_kegiatan` dan `tgl_selesai_kegiatan ≤ tgl_kembali`).
- Pilihan kategori & sumber pembiayaan difilter sesuai tipe ([§8.4](#84-master-data)).
- Beasiswa wajib untuk T2P **dan** T2L (mockup hanya memvalidasi T2L — lihat [§14](#14-keputusan--pertanyaan-terbuka)).

---

## 6. Persyaratan Dokumen per Tahap

Tanda **G** = tersedia tombol *Generate* (dokumen dibuat sistem),
**F** = tombol *Unduh Format* (template dari Manajemen Template),
**TS** = disarankan meminta *Tanggal Surat* (pola `JENIS_PERLU_TANGGAL_SURAT`).

### 6.1 Tahap Pegawai

| Kode jenis | Dokumen | T1 | T3 | T2P | T2L |
|---|---|:-:|:-:|:-:|:-:|
| `undangan` | Undangan/Surat Permohonan dari Penyelenggara | ✅ | ✅ | | |
| `kak` | Kerangka Acuan Kerja (KAK) | ✅ | ✅ | | ✅ |
| `rab` | RAB Pembiayaan | ✅ | ✅ | | |
| `itinerary` | Jadwal Kegiatan/Itinerary | ✅ | ✅ | | |
| `loa` | Letter of Acceptance (LoA) | | | ✅ | ✅ |
| `log` | Letter of Guarantee (LoG) | | | ✅ | |
| `surat_pernyataan` | Surat Pernyataan sesuai ketentuan Kemensetneg | | | ✅ | ✅ |
| `drh` | Daftar Riwayat Hidup (DRH) | | | ✅ | |
| `ikatan_dinas` | Perjanjian Ikatan Dinas | | | ✅ | |
| `notadinas` | Nota Dinas Pimpinan Unit Kerja ke Sekretaris Unor (TS) | ✅ | ✅ | ✅ | ✅ |

Non-Dinas tetap: `cuti`, `iln`, `notadinas`, `pendukung` (tidak berubah).

### 6.2 Tahap Admin Unor

| Kode jenis | Dokumen | T1 | T3 | T2P | T2L |
|---|---|:-:|:-:|:-:|:-:|
| `izin_prinsip` | Izin Prinsip Menteri (T3: "Izin Prinsip/Disposisi Menteri") | ✅ | ✅ | | |
| `surat_tugas` | Surat Tugas / Surat Tugas Pimpinan Unor (F, TS) | ✅ | ✅ | ✅ | ✅ |
| `nd_kabiro_pakln` | Nota Dinas Sekretaris Unor ke Kepala Biro PAKLN (F, TS) | ✅ | ✅ | | |
| `nd_sek_bpsdm` | Nota Dinas Sekretaris Unor ke Sekretaris BPSDM (F, TS) | | | ✅ | ✅ |
| `drh_ttd` | DRH ttd Pimpinan Unor | | | ✅ | |

Non-Dinas tetap: `disposisi`, `iln_pimpinan`, `nd_biropakln` + `DokumenUnorPendukung`.

### 6.3 Tahap Admin BPSDM *(Tipe 2)*

| Kode jenis | Dokumen | T2P | T2L |
|---|---|:-:|:-:|
| `izin_prinsip` | Izin Prinsip Menteri | ✅ | ✅ |
| `ikatan_dinas_ttd` | Perjanjian Ikatan Dinas ttd full / SK Tugas Belajar (G) | ✅ | |
| `nd_kabiro_pakln` | Nota Dinas Sekretaris BPSDM ke Kepala Biro PAKLN (F, TS) | ✅ | ✅ |

### 6.4 Tahap Admin Biro PAKLN

| Kode jenis | Dokumen | T1 | T3 | T2P | T2L |
|---|---|:-:|:-:|:-:|:-:|
| `sp_setneg` | SP Setneg (G) | ✅ | ✅ | ✅ | ✅ |
| `paspor_dinas` | Paspor Dinas | ✅ | ✅ | ✅ | ✅ |
| `exit_permit` | Exit Permit | ✅ | ✅ | ✅ | ✅ |
| `visa` | Rekomendasi Visa — **wajib** bila salah satu negara tujuan memerlukan visa, **opsional** bila tidak | ◐ | ◐ | ◐ | ◐ |
| `sk_tubel` | SK Tugas Belajar (G) | | | ✅ | |
| `nd_karo_unor` | Nota Dinas Karo PAKLN ke Sekretaris Unor hal Penyampaian Dokumen PDLN (G, TS) | ✅ | ✅ | ✅ | ✅ |

Non-Dinas tetap: `iln_sekjen` + `DokumenPaklnPendukung`.

**Aturan visa:** wajib/opsional ditentukan oleh master `Negara.perlu_visa`
(dikelola Admin PAKLN di Manajemen Negara), bukan diputuskan per pengajuan:

```python
@property
def perlu_visa(self):  # Pengajuan
    return self.tujuan_negara.filter(perlu_visa=True).exists()
```

Dievaluasi saat validasi tombol **Selesai** (tahap PAKLN). Bila `True`,
baris Rekomendasi Visa tampil **wajib** beserta nama negara yang
memerlukan visa; bila `False`, tetap tampil sebagai **opsional** ("negara
tujuan tidak memerlukan visa") dan boleh dikosongkan.

### 6.5 Registri persyaratan (satu sumber kebenaran)

Kelengkapan dokumen saat ini dihitung di view (`len(dokumen_map) >= len(jenis_choices)`)
— tidak lagi cukup karena daftar wajib berbeda per tipe. Definisikan
registri di `pengajuan/persyaratan.py`:

```python
# (tipe, tahap) -> daftar persyaratan; tipe "nondinas" untuk alur lama.
PERSYARATAN = {
    ("T1", "pegawai"): [
        Syarat("undangan", wajib=True),
        Syarat("kak", wajib=True),
        Syarat("rab", wajib=True),
        Syarat("itinerary", wajib=True),
        Syarat("notadinas", wajib=True, tanggal_surat=True),
    ],
    ("T1", "pakln"): [
        Syarat("sp_setneg", wajib=True, aksi="generate"),
        Syarat("visa", wajib=lambda p: p.perlu_visa),  # wajib kondisional
        ...
    ],
    ...
}

def syarat_untuk(pengajuan, tahap): ...
def dokumen_lengkap(pengajuan, tahap) -> bool: ...
```

View, template unggah, pratinjau ("Direktori Unggahan"), dan validasi
tombol Kirim/Teruskan/Selesai **seluruhnya** membaca registri ini.

---

## 7. Pengembalian & Catatan Dua Arah

Mockup Tahap 2 belum menggambarkan pengembalian untuk PDLN; sistem
menerapkan pola yang **sudah berjalan** di Non-Dinas
([RIWAYAT_PEMROSESAN_PENGAJUAN.MD §2–§3](RIWAYAT_PEMROSESAN_PENGAJUAN.MD#2-alur-proses--peristiwa-yang-dicatat))
ke semua tipe:

- Pengembalian **wajib** catatan; penerima pengembalian **wajib** membalas
  dengan catatan saat mengirim/meneruskan lagi.
- Jalur catatan per pasangan tahap:

| Jalur | Pengembalian | Balasan | Field penanda di `Pengajuan` |
|---|---|---|---|
| Pegawai ↔ Admin Unor | `dikembalikan_unor` | `dikirim_ulang` | `catatan_unor` (ada) |
| Admin Unor ↔ Admin BPSDM | `dikembalikan_bpsdm` *(baru)* | `diteruskan_ulang_bpsdm` *(baru)* | `catatan_bpsdm` *(baru)* |
| Admin Unor ↔ Admin PAKLN (T1, T3, Non-Dinas) | `dikembalikan_pakln` | `diteruskan_ulang` | `catatan_pakln` (ada) |
| Admin BPSDM ↔ Admin PAKLN (T2) | `dikembalikan_pakln` | `diteruskan_ulang` | `catatan_pakln` (ada) |

- Aksi riwayat baru: `diteruskan_bpsdm` ("Diteruskan ke Admin BPSDM"),
  `diteruskan_ulang_bpsdm`, `dikembalikan_bpsdm` ("Dikembalikan BPSDM ke Admin Unor").
- Label `dikembalikan_pakln` dibuat netral ("Dikembalikan Biro PAKLN"),
  dengan tujuan ditampilkan dari `status_ke` (Unor atau BPSDM).
- `diteruskan_pakln` / `diteruskan_ulang` bisa dilakukan Admin Unor
  **atau** Admin BPSDM — aktor dibaca dari `aktor_role`.
- Visibilitas: **Pegawai** hanya melihat catatan jalur Pegawai ↔ Unor;
  **Admin Unor, Admin BPSDM, Admin PAKLN** melihat semua catatan pada
  pengajuan yang boleh mereka akses. Tambahkan `admin_bpsdm` ke
  `boleh_lihat_pesan` dan ke label peran di `pengajuan/riwayat.py`.

---

## 8. Struktur Data & Database

### 8.1 Keputusan desain

| Opsi | Keputusan | Alasan |
|---|---|---|
| Model terpisah `PengajuanPdln` | ❌ | Menggandakan status, riwayat, notifikasi, dasbor & export; report gabungan jadi UNION. |
| **Perluas `Pengajuan` + tabel pendamping `DetailPdln` (1:1)** | ✅ | Siklus & report seragam; kolom khusus PDLN tidak membebani baris Non-Dinas. |
| Satu tabel dokumen generik + master jenis dokumen di DB | ❌ (untuk sekarang) | Perlu migrasi ulang 3 tabel dokumen yang sudah berjalan; aturan per tipe cukup di registri kode. |
| **Perluas `DokumenPegawai/Unor/Pakln` + tabel baru `DokumenBpsdm`** | ✅ | Pola & path upload yang sudah ada tetap; perubahan skema hanya penambahan pilihan `jenis`. |

### 8.2 Perubahan tabel yang ada

**`accounts.User`**

| Field | Perubahan |
|---|---|
| `role` | Tambah `admin_bpsdm` ("Admin BPSDM"); tambah helper `is_admin_bpsdm()`. |

**`pengajuan.Pengajuan`**

| Field | Tipe | Keterangan |
|---|---|---|
| `jenis_perjalanan` *(baru)* | `CharField(20)`, choices `nondinas`/`pdln`, default `nondinas`, index | Backfill semua data lama = `nondinas`. |
| `tipe_pdln` *(baru)* | `CharField(5)`, choices `T1`/`T2P`/`T2L`/`T3`, blank | Wajib bila `jenis_perjalanan = pdln`. |
| `unit_organisasi` *(baru)* | FK `paspor.UnitOrganisasi`, null, PROTECT | **Snapshot** unor pegawai saat dikirim, agar scoping & report tidak bergeser jika pegawai pindah unit. |
| `status` | choices | Tambah `proses_bpsdm` dan `dibatalkan`. |
| `tgl_dibatalkan` *(baru)* | `DateField`, null | Diisi saat permohonan pembatalan disetujui Admin PAKLN. |
| `preview_bpsdm_agree` *(baru)* | `BooleanField` | Pola sama dengan `preview_unor_agree`. |
| `catatan_bpsdm` *(baru)* | `TextField`, blank | Penanda pengembalian BPSDM → Unor ([§7](#7-pengembalian--catatan-dua-arah)). |
| `tgl_masuk_bpsdm` *(baru)* | `DateField`, null | Tanggal diteruskan ke BPSDM. |
| `kode` | — | Generator mengikuti prefiks per tipe ([§2](#2-jenis-perjalanan--tipe-pdln)); panjang 20 cukup (`PDLN-2026-T2P-0001` = 18). |

Index yang disarankan: `(jenis_perjalanan, tipe_pdln, status)`,
`(unit_organisasi, status)`, `(status, tgl_pengajuan)`.

**`pengajuan.DokumenPegawai / DokumenUnor / DokumenPakln`** — tambah
nilai `Jenis` sesuai [§6](#6-persyaratan-dokumen-per-tahap) (`max_length`
dinaikkan ke 30). `unique_together ("pengajuan", "jenis")` tetap.

**`pengajuan.RiwayatPengajuan.Aksi`** — tambah `diteruskan_bpsdm`,
`diteruskan_ulang_bpsdm`, `dikembalikan_bpsdm`, serta aksi laporan
`laporan_diunggah`, `laporan_dikembalikan`, `laporan_disetujui`
([§4.4](#44-pelaporan-pdln)), dan aksi pembatalan `pembatalan_diajukan`,
`pembatalan_ditarik`, `pembatalan_disetujui_unor`,
`pembatalan_ditolak_unor`, `pembatalan_ditolak_pakln`, `dibatalkan`
([§4.5](#45-pembatalan-perjalanan-mekanisme-sementara)).

**`pengajuan.DokumenGenerateLog.Jenis`** — tambah `sp_setneg`,
`nd_karo_unor`, `sk_tubel`, `ikatan_dinas_ttd`.

**`pengajuan.DokumenTemplate`** — tambah `untuk_admin_bpsdm` (bool),
`jenis_perjalanan` / `tipe_pdln` (opsional) dan `jenis_dokumen`
(opsional, untuk tombol *Unduh Format* per baris dokumen).

**`notifications.Notification.Event`** — lihat [§11](#11-notifikasi).

### 8.3 Tabel baru

**`pengajuan.DetailPdln`** (1:1 `Pengajuan`, `related_name="detail_pdln"`)

| Field | Tipe | T1/T3 | T2P | T2L |
|---|---|:-:|:-:|:-:|
| `pengajuan` | OneToOne, CASCADE | ✅ | ✅ | ✅ |
| `penyelenggara` | `CharField(200)` | ✅ | | ✅ |
| `perguruan_tinggi` | `CharField(200)` | | ✅ | |
| `kota_tujuan` | `CharField(150)` | ✅ | ✅ | ✅ |
| `tgl_mulai_kegiatan`, `tgl_selesai_kegiatan` | `DateField` | Agenda | Perkuliahan | Pelatihan |
| `beasiswa_pintar_id` | `CharField(50)`, blank | | ✅ | ✅ |
| `beasiswa_nama` | `CharField(255)`, blank — snapshot nama dari PINTAR | | ✅ | ✅ |
| `pernyataan_benar` | `BooleanField` | ✅ | ✅ | ✅ |

**`pengajuan.DokumenBpsdm`** — pola identik `DokumenPakln`:
`pengajuan` FK, `jenis` choices [§6.3](#63-tahap-admin-bpsdm-tipe-2),
`file` (`pengajuan/<kode>/bpsdm/<jenis>/`), `tanggal_surat`, `uploaded_at`,
`unique_together ("pengajuan", "jenis")`.

**`pengajuan.LaporanPdln`** (menu Pelaporan PDLN)

| Field | Tipe | Keterangan |
|---|---|---|
| `pengajuan` | OneToOne, CASCADE, `related_name="laporan_pdln"` | Hanya PDLN berstatus `selesai`. |
| `file` | FileField (`pengajuan/<kode>/laporan/`) | Diganti saat unggah ulang. |
| `status` | `CharField(20)`, choices `menunggu` / `dikembalikan` / `disetujui`, index | Siklus [§4.4](#44-pelaporan-pdln). |
| `catatan_pakln` | `TextField`, blank | Catatan pengembalian terakhir — penanda unggah ulang wajib catatan balasan. |
| `diunggah_oleh` | FK User, SET_NULL | |
| `uploaded_at` | DateTimeField | Unggahan terakhir. |
| `diverifikasi_oleh` | FK User, SET_NULL, null | Admin PAKLN yang menyetujui/mengembalikan. |
| `tgl_disetujui` | DateTimeField, null | Diisi saat `disetujui`. |

Status pelaporan untuk tampilan & report: *Belum Melapor* (belum ada
baris), *Menunggu Verifikasi*, *Dikembalikan*, *Disetujui*, ditambah
penanda *Terlambat* bila belum ada laporan setelah `tgl_kembali + batas
hari` (lihat [§14](#14-keputusan--pertanyaan-terbuka)).

**`pengajuan.PermohonanPembatalan`** (menu Pembatalan, [§4.5](#45-pembatalan-perjalanan-mekanisme-sementara))

| Field | Tipe | Keterangan |
|---|---|---|
| `pengajuan` | FK `Pengajuan`, CASCADE, `related_name="permohonan_pembatalan"` | Bisa lebih dari satu (riwayat permohonan), maksimal satu yang terbuka. |
| `diajukan_oleh` | FK User, SET_NULL | Pegawai atau Admin Unor. |
| `diajukan_role` | `CharField(20)` | Snapshot role pengaju. |
| `alasan` | `TextField` | **Wajib**, divalidasi tidak kosong. |
| `status` | `CharField(20)`, choices `menunggu_unor` / `menunggu_pakln` / `disetujui` / `ditolak` / `ditarik`, index | |
| `status_pengajuan_saat_diajukan` | `CharField(20)` | Untuk report & penempatan di timeline. |
| `unor_oleh`, `unor_waktu`, `unor_catatan` | FK User (SET_NULL), DateTimeField, TextField — null/blank | Keputusan jenjang Unor (atau terisi otomatis bila diajukan Admin Unor). |
| `pakln_oleh`, `pakln_waktu`, `pakln_catatan` | idem | Keputusan jenjang akhir. Catatan wajib bila menolak. |
| `created_at`, `updated_at` | DateTimeField | |

Batasan "maksimal satu permohonan terbuka per pengajuan" ditegakkan di
kode (di dalam `transaction.atomic()` dengan `select_for_update()` pada
`Pengajuan`), karena *conditional unique constraint* tidak didukung
MySQL. Helper `Pengajuan.pembatalan_terbuka` mengembalikan permohonan
berstatus `menunggu_*` (dipakai untuk membekukan aksi alur utama).

**`accounts.PasporPegawai`** (Profil → Data Paspor)

| Field | Tipe |
|---|---|
| `pegawai` | FK User, CASCADE, `related_name="paspor_list"` |
| `nomor` | `CharField(20)` |
| `jenis` | choices: Paspor Biasa / Paspor Dinas / Paspor Diplomatik |
| `tgl_expired` | `DateField` |

**`accounts.DokumenKepegawaian`** (Profil → Dokumen Kepegawaian & SK Penugasan admin)

| Field | Tipe |
|---|---|
| `user` | FK User, CASCADE |
| `jenis` | choices: KTP, KK, Kartu Pegawai/SK PNS, Akta Lahir/Ijazah Terakhir, SK Pangkat Terakhir, Pas Foto 4x6, SK Penugasan Admin |
| `file`, `uploaded_at` | |
| — | `unique_together ("user", "jenis")` |

Field profil tambahan dari e-HRM (Status Kepegawaian, NIK, Jenis
Kelamin, TTL, Alamat, Telepon, Email Dinas/Pribadi, riwayat pendidikan &
pelatihan) ditambahkan ke `PegawaiProfile` **saat integrasi e-HRM** — di
luar cakupan dokumen ini.

### 8.4 Master data

| Master | Perubahan |
|---|---|
| `KategoriPerjalanan` | Sudah punya `jenis_perjalanan` (PDLN/Non-Dinas). Tambah `tipe_pdln` — `JSONField(list)` berisi kode tipe yang berlaku (`["T1","T3"]`, `["T2P"]`, `["T2L"]`); kosong = semua tipe PDLN. |
| `SumberPembiayaan` | Sudah punya `tipe_perjalanan`. Tambah `tipe_pdln` (`JSONField(list)`), aturan sama — mis. *DIPA Kementerian PU* berlaku untuk semua, *Beasiswa LPDP* hanya `["T2P"]`. |
| `Negara` | Tambah `perlu_visa` (bool, default `False`) — penentu wajib/opsionalnya Rekomendasi Visa ([§6.4](#64-tahap-admin-biro-pakln)); dapat diubah di Manajemen Negara. |
| Seed | Data migration untuk kategori & sumber pembiayaan PDLN sesuai [§5](#5-formulir-pengajuan-per-tipe). |

Halaman Manajemen Kategori & Sumber Pembiayaan menambah input
"Berlaku untuk tipe PDLN" (multi-checkbox) bila jenis = PDLN.

### 8.5 Diagram relasi (ringkas)

```
User (role) ─1:1─ PegawaiProfile ── UnitOrganisasi
  │  └─1:N─ PasporPegawai, DokumenKepegawaian
  │
  └─1:N─ Pengajuan (jenis_perjalanan, tipe_pdln, status, unit_organisasi*)
            ├─1:1─ DetailPdln                 (hanya PDLN)
            ├─1:N─ DokumenPegawai             (semua)
            ├─1:N─ DokumenUnor (+ Pendukung)  (semua)
            ├─1:N─ DokumenBpsdm               (hanya T2P/T2L)
            ├─1:N─ DokumenPakln (+ Pendukung) (semua)
            ├─1:1─ LaporanPdln (status)       (hanya PDLN, setelah selesai)
            ├─1:N─ PermohonanPembatalan       (semua; maks. 1 terbuka)
            ├─1:N─ RiwayatPengajuan           (audit trail & catatan)
            ├─1:N─ Notification
            ├─N:M─ Negara (tujuan_negara)
            └─N:1─ KategoriPerjalanan, SumberPembiayaan
```

### 8.6 Migrasi

1. Skema: field & tabel baru di atas (semua nullable/default → aman untuk data lama).
2. Data: `jenis_perjalanan = "nondinas"` untuk semua baris; isi
   `unit_organisasi` dari `pegawai.profile.unit_organisasi` untuk
   pengajuan yang sudah dikirim.
3. Data: seed master kategori & sumber pembiayaan PDLN; tandai
   `Negara.perlu_visa` untuk negara yang memerlukan visa.
4. Ubah scoping Admin Unor (`_scoped`) dari `pegawai__profile__unit_organisasi`
   ke `Pengajuan.unit_organisasi` setelah backfill.

---

## 9. Halaman & Navigasi

### 9.1 Pegawai (Mobile & Web)

| Halaman | Perubahan |
|---|---|
| Beranda | Dua tab: **Riwayat PDLN** (tipe, tujuan, tgl, status, status laporan) dan **Riwayat Non-Dinas** (yang sekarang). Tombol "Tambah Usulan Baru" membuka modal dua langkah ([§2](#2-jenis-perjalanan--tipe-pdln)); **nonaktif** selama ada pengajuan belum tuntas, dengan keterangan alasannya, mis. "Laporan PDLN-2026-T1-0003 belum disetujui" ([§2.1](#21-aturan-satu-pengajuan-aktif)). |
| Formulir | Field dinamis per tipe ([§5](#5-formulir-pengajuan-per-tipe)); satu view dengan form class per tipe. |
| Unggah Dokumen | Daftar dari registri [§6](#6-persyaratan-dokumen-per-tahap); kolom catatan perbaikan saat dikembalikan. |
| Monitor Progres | Timeline Proses dengan jumlah tahap sesuai tipe (5 untuk T2), header kartu menampilkan tipe/kategori/negara/kota. Saat `selesai`: tombol unduh dokumen hasil (Non-Dinas: ILN; PDLN: lihat [§14](#14-keputusan--pertanyaan-terbuka)). |
| Profil *(baru)* | Data personal (read-only), Dokumen Kepegawaian (unggah), Data Paspor (tabel + tambah), Pendidikan/Pelatihan (read-only e-HRM). |
| Pelaporan PDLN *(baru)* | Tabel PDLN milik pegawai: tipe, negara, status perjalanan, status pelaporan, aksi Unggah / Unggah Ulang (dengan catatan balasan) / Lihat Laporan (aktif hanya jika `selesai`); banner catatan Admin PAKLN bila laporan dikembalikan. |
| Pembatalan | Daftar permohonan pembatalan milik pegawai (status, alasan, keputusan per jenjang). Tombol **Ajukan Pembatalan** juga ada di Monitor Progres: modal dengan alasan wajib; tombol **Tarik Permohonan** selama belum diputus. Draft yang belum pernah dikirim: tombol **Batalkan Draft** (alasan wajib, tanpa persetujuan). |
| Ralat/Perubahan | Placeholder "akan dikembangkan". |

### 9.2 Admin Unor / Admin BPSDM / Admin PAKLN

| Halaman | Admin Unor | Admin BPSDM | Admin PAKLN |
|---|---|---|---|
| Dasbor | Tab **Dasbor PDLN** / **Dasbor Non-Kedinasan** | Tipe 2 saja | Tab PDLN / Non-Kedinasan |
| Pratinjau | Per tipe; tombol TL aktif bila `proses` | Aktif bila `proses_bpsdm` | Aktif bila `proses_pakln` |
| Unggah Dok. Administrasi | Dokumen tahap Unor per tipe; tujuan teruskan otomatis (BPSDM/PAKLN) | Dokumen tahap BPSDM | Dokumen tahap PAKLN + generate |
| Export Database | ✅ unornya | ✅ Tipe 2 (disarankan) | ✅ semua |
| Pelaporan PDLN | Monitor laporan pegawai unornya (read-only) | — | **Verifikasi**: antrean *Menunggu Verifikasi*, aksi Setujui / Kembalikan (catatan wajib) |
| Profil | ✅ (+ SK Penugasan) | ✅ | ✅ |
| Generate Dokumen | — | Ikatan Dinas/SK Tubel | ND Kabag/ND Karo (ada) + SP Setneg, ND Karo PDLN, SK Tubel |
| Master data | — | — | ✅ (+ field tipe PDLN) |
| Pembatalan | Antrean *Menunggu Unor* (Setujui / Tolak dengan catatan wajib) + tombol **Ajukan Pembatalan** di Pratinjau/Unggah pengajuan unornya | Read-only (Tipe 2) | Antrean *Menunggu PAKLN* (Setujui / Tolak dengan catatan wajib) |

URL baru mengikuti pola yang ada: `pengajuan/urls_bpsdm.py` dengan
`dashboard`, `dashboard_data`, `<kode>/preview/`, `<kode>/upload/`,
`export/`; dekorator `@role_required("admin_bpsdm")`; queryset dibatasi
`tipe_pdln__in=["T2P","T2L"]`.

---

## 10. Halaman Report (Dinas & Non-Dinas)

Seluruh report membaca tabel `Pengajuan` yang sama, sehingga Dinas &
Non-Dinas tampil dalam satu kerangka. **Filter global** yang tersedia di
setiap report:

- Jenis perjalanan (Semua / PDLN / Non-Dinas), Tipe PDLN (multi),
- Status (multi), Unit Organisasi (khusus BPSDM & PAKLN),
- Periode berdasarkan **tgl pengajuan** atau **tgl berangkat**,
- Negara tujuan, Kategori, Sumber pembiayaan, Kanal (Mobile/Web).

**Cakupan per role** (diterapkan di queryset, bukan di template):

| Role | Cakupan |
|---|---|
| Admin Unor | `unit_organisasi = user.unit_organisasi`, semua jenis |
| Admin BPSDM | `tipe_pdln ∈ {T2P, T2L}`, semua unor |
| Admin PAKLN | Semua |

### 10.1 Dasbor (per role)

- **Kartu ringkasan**: Total masuk, Dalam Proses Unor, Dalam Proses BPSDM
  (bila relevan), Dalam Proses PAKLN, Selesai, **Dibatalkan**; plus
  **Perlu Tindakan Saya** (status = tahap role tersebut, ditambah
  permohonan pembatalan yang menunggu keputusan role tersebut) dan
  **Dikembalikan** (pengajuan yang pernah dikembalikan dan sedang
  menunggu perbaikan).
- Pengajuan dengan permohonan pembatalan terbuka diberi penanda
  "Pembatalan diproses" di kolom Status, dan tombol TL-nya dinonaktifkan.
- **Tabel rincian** server-side DataTables (pola `dashboard_data`):
  Pegawai/NIP, Unor, Jenis, Tipe, Kategori, Negara/Kota, Berangkat,
  Kembali, Tgl Pengajuan/Masuk tahap, Kanal, Status, Aksi (TL/Lihat).
- Tab **PDLN** / **Non-Kedinasan** = preset filter jenis perjalanan.

### 10.2 Export Database

- Menggantikan export CSV yang ada dengan satu export terpadu + filter
  global; format **CSV dan XLSX** (`openpyxl`, sudah dipakai untuk impor
  kalender).
- **Kolom umum**: Kode, Jenis, Tipe, Nama, NIP, Jabatan, Unit
  Organisasi, Kategori, Negara, Sumber Pembiayaan, Tgl Berangkat, Tgl
  Kembali, Jumlah Hari Kerja, Kanal, Status, Tgl Pengajuan, Tgl Masuk
  BPSDM, Tgl Masuk PAKLN, Tgl Selesai, Jumlah Dikembalikan, Tgl
  Dibatalkan, Diajukan Batal Oleh (role), Alasan Pembatalan.
- **Kolom PDLN** (kosong untuk Non-Dinas): Kota, Penyelenggara/Perguruan
  Tinggi, Tgl Mulai/Selesai Kegiatan, Beasiswa, Perlu Visa, Status
  Pelaporan.
- **Kolom Non-Dinas** (kosong untuk PDLN): Maksud Perjalanan.
- XLSX berisi sheet **Data** dan sheet **Ringkasan** (pivot [§10.3](#103-rekapitulasi--pivot)) —
  realisasi tombol "📊 Lihat Pivot" pada mockup.

### 10.3 Rekapitulasi / Pivot

Halaman "Rekap" (Admin PAKLN penuh; Admin Unor & BPSDM sesuai cakupan):

| Rekap | Baris × Kolom | Sumber |
|---|---|---|
| Per status | Jenis/Tipe × Status | `Pengajuan` |
| Per unit organisasi | Unor × Jenis/Tipe (jumlah, selesai) | `Pengajuan.unit_organisasi` |
| Per negara tujuan | Negara × Jenis/Tipe | `tujuan_negara` |
| Per bulan | Bulan (tgl pengajuan/berangkat) × Jenis/Tipe | `Pengajuan` |
| Per kategori & sumber pembiayaan | Kategori/Sumber × Jenis | master FK |
| **Waktu proses (SLA)** | Tahap × rata-rata/median hari | Selisih `created_at` riwayat masuk & keluar tiap status |
| **Pengembalian** | Tahap × jumlah pengembalian, % pengajuan yang pernah dikembalikan | `RiwayatPengajuan.aksi` |
| **Pembatalan** | Jenis/Tipe × (diajukan, disetujui, ditolak, ditarik); per role pengaju; per status saat diajukan; rata-rata waktu keputusan per jenjang | `PermohonanPembatalan` |

Waktu proses dihitung dari `RiwayatPengajuan` (sudah menyimpan
`status_dari`, `status_ke`, `created_at`), bukan dari kolom tanggal —
sehingga bolak-balik pengembalian ikut terhitung. Untuk volume besar,
hitung di query (`Window`/`Lead`) atau tabel ringkasan harian; untuk
volume saat ini cukup agregasi Python per halaman report.

### 10.4 Monitor Pelaporan PDLN

- Admin Unor (unornya, read-only) & Admin PAKLN (semua, dengan aksi
  verifikasi): Pegawai, Tipe, Negara, Tgl Kembali, Status Pelaporan
  (Belum Melapor / Menunggu Verifikasi / Dikembalikan / Disetujui, +
  Terlambat), Tgl Unggah, Tgl Disetujui, tautan berkas.
- Kartu ringkasan: PDLN selesai, belum melapor, menunggu verifikasi,
  dikembalikan, disetujui (tuntas), terlambat.
- Karena laporan yang belum disetujui **menahan pegawai mengajukan
  perjalanan baru** ([§2.1](#21-aturan-satu-pengajuan-aktif)), antrean
  *Menunggu Verifikasi* juga tampil sebagai kartu "Perlu Tindakan Saya"
  di Dasbor Admin PAKLN.
- Masuk ke Export sebagai kolom "Status Pelaporan".

---

## 11. Notifikasi

Tambahan event pada `Notification.Event` dan `notifications/services.py`
(format & pola mengikuti [SKENARIO_NOTIFIKASI_SURAT.md](SKENARIO_NOTIFIKASI_SURAT.md)):

| Event | Pemicu | Penerima |
|---|---|---|
| (pakai ulang) `SUBMIT_UNOR`, `RESUBMIT_UNOR`, `REJECT_UNOR` | Pegawai kirim / kirim ulang; Unor kembalikan | Sama seperti Non-Dinas |
| `FORWARD_BPSDM` *(baru)* | Unor teruskan ke BPSDM (T2) | Admin BPSDM; Pegawai (info, tanpa catatan) |
| `REJECT_BPSDM_UNOR` *(baru)* | BPSDM kembalikan ke Unor | Admin Unor (dengan catatan); Pegawai (info netral) |
| `RESUBMIT_BPSDM` *(baru)* | Unor teruskan ulang ke BPSDM | Admin BPSDM (dengan catatan balasan) |
| `APPROVE_UNOR` (diperluas) | Unor **atau BPSDM** teruskan ke PAKLN | Admin PAKLN (+ catatan balasan bila ulang); Pegawai (info) |
| `REJECT_PKLN_UNOR` (diperluas) | PAKLN kembalikan ke tahap sebelumnya | Admin Unor **atau** Admin BPSDM sesuai tipe; Pegawai (info netral) |
| `COMPLETE_PKLN` | PAKLN selesai | Pegawai, Admin Unor |
| `LAPORAN_PDLN_DIUNGGAH` *(baru)* | Pegawai unggah / unggah ulang laporan | Admin PAKLN (untuk verifikasi, + catatan balasan bila ulang); Admin Unor (info) |
| `LAPORAN_PDLN_DIKEMBALIKAN` *(baru)* | Admin PAKLN kembalikan laporan | Pegawai (dengan catatan) |
| `LAPORAN_PDLN_DISETUJUI` *(baru)* | Admin PAKLN setujui laporan | Pegawai (pengajuan tuntas, boleh mengajukan perjalanan baru) |
| `PENGINGAT_LAPORAN` *(baru, opsional)* | Terjadwal: lewat batas pelaporan | Pegawai |
| `PEMBATALAN_DIAJUKAN` *(baru)* | Permohonan pembatalan dibuat | Diajukan Pegawai → Admin Unor; diajukan Admin Unor → Admin PAKLN **dan** Pegawai (dengan alasan) |
| `PEMBATALAN_MENUNGGU_PAKLN` *(baru)* | Admin Unor menyetujui jenjang 1 | Admin PAKLN; Pegawai (info) |
| `PEMBATALAN_DITOLAK` *(baru)* | Ditolak Admin Unor / Admin PAKLN | Pengaju, Pegawai, dan Admin Unor (dengan catatan) |
| `PEMBATALAN_DISETUJUI` *(baru)* | Admin PAKLN menyetujui → `dibatalkan` | Pegawai, Admin Unor, dan Admin BPSDM bila Tipe 2 sudah/sedang di BPSDM |
| `PEMBATALAN_DITARIK` *(baru)* | Pengaju menarik permohonan | Jenjang yang sedang menunggu keputusan |

Judul/isi notifikasi menyebut jenis & tipe (mis. "PDLN Tipe 2 —
Pendidikan") alih-alih konstanta `JENIS_SURAT` Non-Dinas.

---

## 12. Integrasi Eksternal (Aplikasi PINTAR)

Menu **Informasi Penawaran Beasiswa LN** dan **Pencalonan Beasiswa**
berada di Aplikasi PINTAR (sistem terpisah). PASPOR hanya **membaca**:

- Droplist "Nama Beasiswa Pendidikan/Pelatihan" pada formulir T2P/T2L
  menampilkan **pencalonan atas nama pegawai yang login** dengan status
  **Selesai** (mendapat rekomendasi Admin BPSDM dan Admin Biro PAKLN),
  difilter jenis (pendidikan/pelatihan).
- Antarmuka layanan (`paspor/integrasi/pintar.py`):

```python
def daftar_pencalonan_selesai(nip: str, jenis: Literal["pendidikan", "pelatihan"]) -> list[Pencalonan]:
    """Pencalonan {id, nama_beasiswa, institusi, tgl_rekomendasi} berstatus Selesai."""
```

- Disimpan sebagai `beasiswa_pintar_id` + `beasiswa_nama` (snapshot) agar
  pengajuan tetap terbaca bila data PINTAR berubah/tidak tersedia.
- Sebelum API PINTAR siap: implementasi *stub* (tabel/seed lokal atau
  input teks bebas) di balik antarmuka yang sama; ditandai lewat setting
  `PINTAR_API_URL` kosong.

Data profil pegawai (e-HRM) dan login Satu Bravo tetap di luar cakupan
dokumen ini.

---

## 13. Tahapan Implementasi

| Fase | Isi | Keluaran |
|---|---|---|
| 1. Fondasi data | Field `jenis_perjalanan`, `tipe_pdln`, `unit_organisasi`, `proses_bpsdm`; `DetailPdln`; role `admin_bpsdm`; migrasi & backfill; master kategori/sumber per tipe | Data lama tetap berjalan, test lulus |
| 2. Alur & registri | `pengajuan/alur.py` (`ALUR`, transisi, tahap sebelumnya), `pengajuan/persyaratan.py`; timeline & riwayat dinamis per tipe | Unit test transisi per tipe |
| 2b. Pembatalan | `PermohonanPembatalan`, status `dibatalkan`, pembekuan aksi alur utama, menu Pembatalan per role, notifikasi — **dapat dirilis lebih dulu untuk Non-Dinas** karena tidak bergantung pada PDLN | Pembatalan berjenjang berjalan untuk Non-Dinas, otomatis berlaku untuk PDLN |
| 3. PDLN Tipe 1 & 3 + Pelaporan | Formulir, unggah, pratinjau & administrasi Unor/PAKLN, visa wajib/opsional per negara, pengembalian, notifikasi; `LaporanPdln` + verifikasi PAKLN; aturan satu pengajuan aktif ([§2.1](#21-aturan-satu-pengajuan-aktif)) | End-to-end T1/T3 sampai laporan disetujui |
| 4. PDLN Tipe 2 + BPSDM | `DokumenBpsdm`, `urls_bpsdm`, dasbor BPSDM, jalur Unor↔BPSDM↔PAKLN | End-to-end T2P/T2L |
| 5. Integrasi PINTAR | Antarmuka + stub, lalu API nyata | Droplist beasiswa |
| 6. Generate dokumen PDLN | SP Setneg, ND Karo PDLN, SK Tubel, Ikatan Dinas (pola ND Kabag/Karo) | Tombol Generate aktif |
| 7. Report terpadu | Filter global, export CSV/XLSX + sheet ringkasan, halaman Rekap, SLA & pengembalian | Report Dinas & Non-Dinas |
| 8. Profil | `PasporPegawai`, `DokumenKepegawaian` | Menu Profil lengkap |

**Pelaporan PDLN (`LaporanPdln` + verifikasi PAKLN) wajib dirilis bersama
fase 3**, bukan belakangan: aturan [§2.1](#21-aturan-satu-pengajuan-aktif)
menganggap PDLN belum tuntas sampai laporannya disetujui, sehingga tanpa
fitur ini pegawai yang PDLN-nya selesai tidak akan bisa mengajukan
perjalanan baru.

Setiap fase menambah test di `pengajuan/tests.py` (pola `_AlurMixin`):
alur penuh per tipe, pengembalian per jalur, kelengkapan dokumen per
registri (termasuk visa wajib/opsional per negara), scoping per role,
visibilitas catatan, aturan satu pengajuan aktif (Non-Dinas tuntas
saat `selesai`; PDLN tuntas saat laporan disetujui; `dibatalkan` tuntas),
dan pembatalan (alasan/catatan tolak wajib, jenjang per pengaju,
pembekuan aksi alur utama, maksimal satu permohonan terbuka).

---

## 14. Keputusan & Pertanyaan Terbuka

### Keputusan (sudah diambil di dokumen ini)

| # | Keputusan | Alasan |
|---|---|---|
| 1 | Perluas `Pengajuan` + `DetailPdln`, bukan model terpisah | Satu siklus, riwayat, notifikasi & report ([§8.1](#81-keputusan-desain)) |
| 2 | Status baru hanya `proses_bpsdm`; urutan tahap per tipe di `ALUR` | State machine tetap sederhana dan eksplisit |
| 3 | Pengembalian selalu ke tahap tepat sebelumnya, catatan dua arah wajib | Konsisten dengan alur Non-Dinas yang sudah berjalan |
| 4 | Snapshot `unit_organisasi` di `Pengajuan` | Report & scoping stabil saat pegawai mutasi |
| 5 | Persyaratan dokumen di registri kode | Satu sumber kebenaran untuk view, template, validasi |
| 6 | Kode Non-Dinas tetap `PSP-…`, PDLN memakai prefiks per tipe | Kompatibel dengan data & dokumen lama; mengikuti mockup |
| 7 | **PDLN Tipe 3 diajukan oleh Pegawai**, alur sama dengan Tipe 1 *(dikonfirmasi pemilik proses)* | Menyelesaikan inkonsistensi mockup (sebagian teks menyebut "diajukan oleh Admin Unor") |
| 8 | **Rekomendasi Visa wajib** bila negara tujuan memerlukan visa, **opsional** bila tidak; ditentukan master `Negara.perlu_visa` *(dikonfirmasi)* | [§6.4](#64-tahap-admin-biro-pakln) |
| 9 | **Satu pengajuan aktif lintas jenis**; pengajuan baru hanya setelah tahap akhir — Non-Dinas: disetujui Admin PAKLN (`selesai`); PDLN: Laporan PDLN disetujui Admin PAKLN *(dikonfirmasi)* | [§2.1](#21-aturan-satu-pengajuan-aktif), [§4.4](#44-pelaporan-pdln) |
| 10 | **Pembatalan (interim)**: dapat diajukan Pegawai atau Admin Unor, alasan wajib, persetujuan berjenjang Admin Unor → Admin PAKLN; berlaku untuk Dinas & Non-Dinas; disetujui ⇒ `dibatalkan` dan dianggap tuntas *(dikonfirmasi; rumusan final menyusul)* | [§4.5](#45-pembatalan-perjalanan-mekanisme-sementara) |

### Pertanyaan terbuka (default dipakai sampai dijawab)

| # | Pertanyaan | Default |
|---|---|---|
| 1 | Mockup belum memiliki fitur **kembalikan** untuk PDLN. | Diterapkan sesuai [§7](#7-pengembalian--catatan-dua-arah). |
| 2 | Apakah **beasiswa** wajib untuk T2 Pendidikan (mockup hanya memvalidasi Pelatihan)? | Wajib untuk keduanya. |
| 3 | Dokumen hasil apa yang dapat **diunduh Pegawai** saat PDLN selesai? | SP Setneg, Exit Permit, Rekomendasi Visa, ND Karo, (T2P) SK Tubel; Paspor Dinas tidak. |
| 4 | **Batas waktu Pelaporan PDLN** setelah kepulangan, dan apakah laporan baru boleh diunggah setelah `tgl_kembali`? | 14 hari kalender setelah `tgl_kembali` (konfigurabel); unggah dibuka sejak `selesai`. |
| 5 | Apakah Admin BPSDM perlu **Export & Pelaporan**? | Export Tipe 2: ya; Pelaporan: tidak (mengikuti mockup). |
| 6 | **Batas waktu pembatalan** untuk pengajuan yang sudah `selesai`: sampai kapan boleh diajukan? | Non-Dinas: sampai `tgl_berangkat`; PDLN: selama Laporan PDLN belum disetujui (menampung perjalanan yang ternyata tidak dilaksanakan). |
| 7 | Bila pembatalan **diajukan Admin Unor**, apakah tetap perlu persetujuan Admin Unor (orang lain/atasan)? | Tidak — pengajuan oleh Admin Unor dihitung sebagai persetujuan jenjang Unor. |
| 8 | Apakah **Admin BPSDM** perlu menjadi jenjang persetujuan pembatalan Tipe 2? | Tidak; hanya menerima notifikasi. |
| 9 | Tindak lanjut **dokumen yang sudah terbit** (ILN, Paspor Dinas, Exit Permit, SP Setneg) saat dibatalkan — perlu surat pembatalan resmi / pengembalian paspor dinas? | Di luar sistem untuk saat ini; dokumen tetap diarsipkan, tanpa dokumen pembatalan otomatis. |
| 10 | Format resmi dokumen yang di-*generate* (SP Setneg, SK Tubel, Ikatan Dinas) dan format Laporan PDLN. | Menunggu contoh dokumen dari Biro PAKLN/BPSDM. |

---

## 15. Bahan Pertimbangan untuk Diskusi Lanjutan

Daftar celah perencanaan yang **belum** dibahas di dokumen ini dan perlu
didiskusikan sebelum fase terkait dimulai. Berbeda dengan pertanyaan
terbuka [§14](#14-keputusan--pertanyaan-terbuka) (yang sudah punya
default), butir di sini **belum punya rancangan** dan sebagian dapat
mengubah struktur data.

**Prioritas:** 🔴 menghambat — harus diputuskan sebelum fase terdampak;
🟡 penting — perlu diputuskan selama fase berjalan; 🟢 pelengkap.

### Ringkasan

| # | Topik | Prioritas | Fase terdampak | Pihak diskusi |
|---|---|:-:|---|---|
| D1 | Pengajuan rombongan / delegasi | 🔴 | 3 dan seterusnya | Biro PAKLN, Admin Unor |
| D2 | Validasi alur & dokumen terhadap regulasi dan praktik | 🔴 | 3–4 | Biro PAKLN, BPSDM, Biro Hukum |
| D3 | Mekanisme Ralat/Perubahan | 🟡 | Setelah 3 | Biro PAKLN, Admin Unor |
| D4 | Matriks hak akses berkas per role | 🔴 | 2b, 3 | Biro PAKLN, tim pengembang |
| D5 | Kriteria penerimaan per fase | 🔴 | Semua (mulai fase 1) | Pemilik proses, tim pengembang |
| D6 | Perlindungan data pribadi & masa simpan arsip | 🟡 | 3, 8 | Pusdatin, Biro Hukum |
| D7 | Pemrosesan bersamaan oleh lebih dari satu admin | 🟡 | 2, 2b | Tim pengembang |
| D8 | PDLN pada kanal mobile (Satu Bravo) | 🟡 | 3 | Pengelola Satu Bravo, Pusdatin |
| D9 | Target waktu layanan (SLA) per tahap | 🟢 | 7 | Biro PAKLN, BPSDM |
| D10 | Spesifikasi teks notifikasi PDLN | 🟢 | 3–4 | Biro PAKLN |
| D11 | Estimasi usaha, penanggung jawab & jadwal | 🟡 | Perencanaan proyek | Pemilik proyek, tim pengembang |

### D1. Pengajuan rombongan / delegasi 🔴

- **Situasi:** mockup memodelkan satu pegawai per pengajuan. Dalam praktik,
  PDLN sering berangkat sebagai rombongan dengan satu SP Setneg / Surat
  Tugas untuk beberapa orang. Fitur Generate ND Kabag/Karo yang sudah ada
  pun memproses beberapa pengajuan sekaligus (`DokumenGenerateLog.pengajuan` M2M).
- **Yang perlu diputuskan:**
  - Apakah satu pengajuan PDLN dapat berisi beberapa pegawai, atau tiap
    pegawai mengajukan sendiri lalu dikelompokkan oleh admin?
  - Siapa yang membuat pengajuan rombongan (ketua rombongan, Admin Unor)?
  - Dokumen mana yang per orang (paspor dinas, exit permit, visa) dan mana
    yang per rombongan (SP Setneg, surat tugas, izin prinsip)?
  - Bagaimana bila satu anggota dikembalikan/dibatalkan sementara anggota
    lain lanjut? Bagaimana dengan Laporan PDLN dan aturan satu pengajuan
    aktif ([§2.1](#21-aturan-satu-pengajuan-aktif))?
  - Rombongan lintas unor: unor mana yang memproses?
- **Dampak bila diputuskan belakangan:** perubahan model data inti
  (`Pengajuan`, tabel dokumen, pembatalan, pelaporan) setelah data
  produksi terbentuk.

### D2. Validasi terhadap regulasi dan praktik 🔴

- **Situasi:** seluruh daftar dokumen, tahap, dan peran di dokumen ini
  diturunkan dari mockup, yang dapat menyederhanakan proses nyata.
- **Yang perlu diputuskan / diverifikasi:**
  - Kesesuaian dengan regulasi PDLN yang berlaku (ketentuan Kemensetneg,
    peraturan internal Kementerian PU) — termasuk dokumen wajib per tipe.
  - Apakah ada tahap/pihak lain (mis. Kemenlu, Inspektorat, persetujuan
    Sekjen terpisah) yang belum tergambar.
  - Kapan dokumen "kondisional" berlaku selain visa (mis. LoG hanya untuk
    beasiswa tertentu).
- **Keluaran yang diharapkan:** daftar dokumen per tipe yang
  ditandatangani/disetujui pemilik proses sebagai acuan registri
  [§6.5](#65-registri-persyaratan-satu-sumber-kebenaran).

### D3. Mekanisme Ralat/Perubahan 🟡

- **Situasi:** menu Ralat/Perubahan masih placeholder. Perubahan tanggal,
  kota, atau negara setelah disetujui cukup sering terjadi pada PDLN.
  Tanpa mekanisme ini, satu-satunya jalan adalah membatalkan lalu
  mengajukan ulang.
- **Yang perlu diputuskan:**
  - Field apa saja yang boleh diralat, dan pada status apa.
  - Apakah ralat memerlukan persetujuan berjenjang seperti pembatalan,
    dan apakah dokumen yang sudah terbit harus diterbitkan ulang.
  - Apakah ralat menghitung ulang `jumlah_hari_kerja` dan mempengaruhi
    batas waktu pelaporan.
  - Penyimpanan versi data sebelum/sesudah ralat (audit trail).

### D4. Matriks hak akses berkas per role 🔴

- **Situasi:** dokumen ini mengatur siapa memproses tahap mana, tetapi
  belum mengatur **siapa boleh melihat/mengunduh berkas** mana.
- **Yang perlu diputuskan** (contoh pertanyaan):
  - Apakah Admin BPSDM boleh mengakses dokumen tahap Pegawai dan Unor
    seluruhnya?
  - Apakah Pegawai boleh mengunduh dokumen hasil tahap PAKLN (Paspor
    Dinas, Exit Permit, SP Setneg) — lihat juga [§14](#14-keputusan--pertanyaan-terbuka) #3.
  - Apakah Admin Unor boleh melihat dokumen tahap BPSDM/PAKLN.
  - Dokumen Profil (KTP, KK, dsb.): siapa saja yang boleh melihat.
- **Keluaran yang diharapkan:** tabel role × jenis dokumen × (lihat /
  unduh / unggah / hapus), ditegakkan di view unduh berkas (bukan hanya
  disembunyikan di template).

### D5. Kriteria penerimaan per fase 🔴

- **Situasi:** [§13](#13-tahapan-implementasi) baru menyebut area yang
  perlu diuji, belum skenario konkret yang menyatakan sebuah fase
  "selesai".
- **Yang perlu disusun:** untuk setiap fase, daftar skenario Given/When/Then
  yang disepakati pemilik proses (mis. "Pegawai dengan PDLN `selesai`
  tanpa laporan disetujui tidak dapat menekan Tambah Usulan Baru"),
  minimal untuk fase 1, 2, dan 2b sebelum pengerjaan dimulai.

### D6. Perlindungan data pribadi & masa simpan arsip 🟡

- **Situasi:** sistem akan menyimpan NIK, nomor paspor, KTP, KK, DRH,
  dan dokumen kepegawaian lain.
- **Yang perlu diputuskan:**
  - Kepatuhan UU Pelindungan Data Pribadi: dasar pemrosesan, pembatasan
    akses, pencatatan akses ke dokumen sensitif.
  - Masa simpan berkas pengajuan selesai/dibatalkan dan prosedur
    penghapusan/pengarsipan.
  - Apakah nomor paspor/NIK perlu disamarkan pada tampilan dan export.
  - Kebijakan bucket penyimpanan berkas (lihat
    [S3BUCKET_FILE_UPLOAD.MD](S3BUCKET_FILE_UPLOAD.MD)): enkripsi, URL
    bertanda tangan, masa berlaku tautan.

### D7. Pemrosesan bersamaan oleh lebih dari satu admin 🟡

- **Situasi:** satu unor/biro bisa memiliki beberapa admin. Dua admin
  dapat membuka pengajuan yang sama dan, misalnya, satu meneruskan
  sementara yang lain mengembalikan. Saat ini penguncian baru dibahas
  untuk pembatalan.
- **Yang perlu diputuskan:**
  - Penguncian transisi status (`select_for_update` + cek status sebelum
    transisi) di semua aksi alur.
  - Apakah perlu penanda "sedang ditangani oleh …" / penugasan pengajuan
    ke admin tertentu.

### D8. PDLN pada kanal mobile (Satu Bravo) 🟡

- **Situasi:** mockup menampilkan alur PDLN di Mobile App (Satu Bravo)
  maupun Web, tetapi mekanisme integrasi kanal mobile belum didefinisikan
  di dokumen ini.
- **Yang perlu diputuskan:**
  - Apakah kanal mobile berupa webview halaman yang sama atau API
    terpisah.
  - Fitur PDLN mana yang wajib tersedia di mobile (formulir, unggah
    dokumen berukuran besar, pelaporan, pembatalan).
  - Mekanisme login/SSO dan notifikasi push.

### D9. Target waktu layanan (SLA) per tahap 🟢

- **Situasi:** report [§10.3](#103-rekapitulasi--pivot) menghitung lama
  proses per tahap, tetapi belum ada target pembanding.
- **Yang perlu diputuskan:** target hari kerja per tahap per tipe,
  ambang peringatan (mis. kartu "melewati SLA" di dasbor), dan apakah
  perlu pengingat otomatis ke admin.

### D10. Spesifikasi teks notifikasi PDLN 🟢

- **Situasi:** [§11](#11-notifikasi) baru mendaftar event dan penerima.
- **Yang perlu disusun:** judul, isi, tingkat (info/warning/success),
  dan tautan tujuan untuk setiap event, setara dengan rincian di
  [SKENARIO_NOTIFIKASI_SURAT.md](SKENARIO_NOTIFIKASI_SURAT.md); serta
  apakah notifikasi email ikut dikirim.

### D11. Estimasi usaha, penanggung jawab & jadwal 🟡

- **Situasi:** [§13](#13-tahapan-implementasi) berisi urutan fase tanpa
  estimasi.
- **Yang perlu disusun:** estimasi usaha per fase, penanggung jawab
  (pengembang, penguji, pemilik proses yang memvalidasi), target rilis,
  dan ketergantungan eksternal (contoh dokumen resmi, API PINTAR,
  keputusan D1–D2).
