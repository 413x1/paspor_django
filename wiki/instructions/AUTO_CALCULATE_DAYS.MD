# Auto Calculate Jumlah Hari Kalender & Hari Kerja

> **Status:** sudah diimplementasikan.
> **Pengguna:** Pegawai (Formulir Pengajuan) dan Admin Biro PAKLN (menu Setting Kalender).

## Daftar Isi

1. [Ringkasan](#1-ringkasan)
2. [Aturan Perhitungan](#2-aturan-perhitungan)
3. [Alur Pegawai](#3-alur-pegawai--formulir-pengajuan)
4. [Alur Admin Biro PAKLN](#4-alur-admin-biro-pakln--setting-kalender)
5. [Struktur Data](#5-struktur-data)
6. [Seed Data Hari Libur](#6-seed-data-hari-libur)
7. [Peta Kode](#7-peta-kode)
8. [Pengujian](#8-pengujian)
9. [Keputusan](#9-keputusan)

---

## 1. Ringkasan

### Masalah

Formulir Pengajuan Perjalanan Non-Kedinasan punya dua kolom:

- **Jumlah Hari Kalender** — mudah, cukup selisih tanggal.
- **Jumlah Hari Kerja** — dulu diketik manual oleh pegawai, sehingga rawan
  salah (lupa mengecualikan Sabtu/Minggu atau tanggal merah).

Padahal Jumlah Hari Kerja dipakai untuk validasi sisa cuti dan dicetak pada
ND Karo. Tanggal merah juga berubah setiap tahun (SKB 3 Menteri), jadi
tidak bisa dihitung hanya dari tanggal.

### Solusi

- Admin Biro PAKLN mengelola daftar **tanggal merah** (libur nasional &
  cuti bersama) lewat menu **Setting Kalender**.
- Sabtu & Minggu **otomatis** bukan hari kerja — tidak perlu diinput.
- Sistem menghitung kedua kolom secara otomatis; pegawai tidak lagi
  mengetik angka.

### Hasil yang dicapai

| # | Kriteria | Status |
|---|---|---|
| 1 | Menu Setting Kalender: tambah, edit, nonaktifkan, hapus tanggal libur | ✅ |
| 2 | Sabtu & Minggu selalu bukan hari kerja | ✅ |
| 3 | Kolom Hari Kalender & Hari Kerja terisi otomatis tanpa reload | ✅ |
| 4 | Hari kerja dihitung ulang di server saat disimpan (nilai browser diabaikan) | ✅ |
| 5 | Validasi "hari kerja ≤ sisa cuti" memakai hasil hitung server | ✅ |
| 6 | Pengajuan yang sudah dikirim tidak berubah walau kalender diubah | ✅ |
| 7 | Peringatan bila kalender tahun terkait belum diatur | ✅ |

**Di luar cakupan:** libur daerah per unit, hari kerja non-standar
(mis. unit yang masuk Sabtu), sinkronisasi dari API kalender eksternal.

---

## 2. Aturan Perhitungan

| Istilah | Arti |
|---|---|
| **Hari Kalender** | Semua tanggal dari berangkat s.d. kembali, **termasuk** kedua ujung. |
| **Akhir Pekan** | Sabtu & Minggu. Ditetapkan di kode, bukan data. |
| **Hari Libur** | Tanggal aktif di tabel `HariLibur` (libur nasional / cuti bersama). |
| **Hari Kerja** | Hari Kalender − Akhir Pekan − Hari Libur yang jatuh Senin–Jumat. |

Aturan tambahan:

- Berangkat & kembali di tanggal yang sama = **1 hari**.
- Tanggal kembali sebelum tanggal berangkat → tidak dihitung (formulir menolak).
- Libur yang jatuh di Sabtu/Minggu **tidak dikurangi dua kali**.
- Libur yang **dinonaktifkan** tidak dihitung.
- Hari kerja boleh **0** (mis. perjalanan Sabtu–Minggu saja).

### Contoh

| Berangkat | Kembali | Kalender | Akhir pekan | Libur | **Hari Kerja** |
|---|---|---|---|---|---|
| Jum, 14 Agu 2026 | Rab, 19 Agu 2026 | 6 | 2 | 1 (17 Agu) | **3** |
| Sab, 15 Agu 2026 | Min, 16 Agu 2026 | 2 | 2 | 0 | **0** |
| Sen, 16 Mar 2026 | Jum, 27 Mar 2026 | 12 | 2 | 5 (Nyepi & Idulfitri) | **5** |

---

## 3. Alur Pegawai — Formulir Pengajuan

```
Isi Tanggal Keberangkatan & Tanggal Kembali
        │
        ▼
Browser memanggil  GET /pegawai/hitung-hari/?berangkat=...&kembali=...
        │
        ▼
Kolom terisi otomatis (read-only):
  • Jumlah Hari Kalender
  • Jumlah Hari Kerja
  • Rincian: "6 hari kalender, 2 hari akhir pekan, 1 hari libur (17 Agu: Proklamasi Kemerdekaan)."
  • ⚠ bila kalender tahun tsb. belum diatur admin
  • ⚠ bila hari kerja melebihi sisa cuti
        │
        ▼
Klik "Simpan & Lanjutkan"
        │
        ▼
Server menghitung ulang hari kerja ──► melebihi sisa cuti? ──► tampilkan error
        │
        ▼
Tersimpan ke Pengajuan.jumlah_hari_kerja
```

Hal penting:

- Angka di browser **hanya pratinjau**. Nilai yang disimpan selalu hasil
  hitung server.
- Setelah pengajuan **dikirim**, angkanya **dibekukan** (snapshot). Perubahan
  kalender oleh admin sesudahnya tidak memengaruhi pengajuan tersebut.
- Peringatan "kalender belum diatur" **tidak memblokir** — pengajuan tetap
  bisa disimpan, dengan hari kerja yang baru mengecualikan Sabtu & Minggu.

---

## 4. Alur Admin Biro PAKLN — Setting Kalender

**Menu:** navbar → dropdown master data → **Setting Kalender**
(`/admin-biropakln/kalender/`).

```
┌──────────────────────────────────────────────────────────────┐
│ Setting Kalender — Hari Libur Nasional                       │
├──────────────────────────────────────────────────────────────┤
│ Tambah Hari Libur                                            │
│  Tanggal Mulai [____]   Tanggal Selesai [____] (opsional)    │
│  Keterangan [______________]   Jenis [Libur Nasional ▾]      │
│  ☑ Lewati Sabtu & Minggu dalam rentang       [Simpan]        │
├──────────────────────────────────────────────────────────────┤
│ Daftar Hari Libur Tahun 2026 (25)                  [2026 ▾]  │
│  Tanggal | Hari | Keterangan | Jenis | Status | Aksi         │
│                              [Edit] [Nonaktifkan] [Hapus]    │
└──────────────────────────────────────────────────────────────┘
```

| Aksi | Perilaku |
|---|---|
| **Tambah satu tanggal** | Isi Tanggal Mulai saja. |
| **Tambah rentang** | Isi juga Tanggal Selesai (maks. 31 hari) → satu baris per tanggal. Sabtu/Minggu dilewati bila dicentang. |
| **Tanggal sudah ada** | Dilewati, bukan error. Contoh pesan: *"3 tanggal libur ditambahkan. 1 dilewati karena sudah ada (17-08-2026)."* |
| **Tanggal jatuh di akhir pekan** | Tetap disimpan, dengan info bahwa tanggal itu tidak mengubah hari kerja. |
| **Filter tahun** | Menampilkan tahun yang punya data + tahun berjalan + tahun depan. |
| **Edit** | Ubah tanggal, keterangan, jenis, status. |
| **Nonaktifkan / Aktifkan** | Untuk revisi SKB tanpa menghapus data. |
| **Hapus** | Permanen, dengan konfirmasi. |
| **Import Excel** | Unggah banyak tanggal sekaligus — lihat di bawah. |

### Import dari Excel

1. Klik **Unduh Template Excel** — berisi header, 2 baris contoh, dropdown
   kolom *jenis*, dan sheet *Petunjuk*.
2. Isi satu baris per tanggal:

   | tanggal | keterangan | jenis |
   |---|---|---|
   | 2026-08-17 | Proklamasi Kemerdekaan | Libur Nasional |
   | 2026-12-24 | Cuti Bersama Kelahiran Yesus Kristus | Cuti Bersama |

3. Unggah berkas (.xlsx, atau .csv; maks. 2 MB), lalu klik **Import Excel**.

Aturan impor:

| Hal | Aturan |
|---|---|
| Header | Wajib ada kolom `tanggal`, `keterangan`, `jenis`. Urutan bebas, huruf besar/kecil diabaikan. |
| Tanggal | Sel tanggal Excel, atau teks `YYYY-MM-DD`, `DD-MM-YYYY`, `DD/MM/YYYY`. |
| Jenis | `Libur Nasional` / `Cuti Bersama` (juga menerima `libur_nasional`, `cuti_bersama`, `libur`, `cuti`). Kosong = Libur Nasional. |
| Baris kosong | Diabaikan. Maks. 1.000 baris per berkas. |
| Ada baris salah | **Tidak ada yang disimpan.** Semua kesalahan ditampilkan per nomor baris (tanggal tidak valid, tanggal ganda, keterangan kosong, jenis tidak dikenal), maks. 10 pesan. |
| Tanggal sudah ada | Dilewati. Jika **"Timpa keterangan & jenis"** dicentang, keterangan & jenisnya diperbarui (status aktif tidak diubah). |
| Hasil | Contoh: *"Impor selesai: 2 ditambahkan, 0 diperbarui, 1 dilewati (sudah ada)."* Tabel langsung beralih ke tahun yang paling banyak diimpor. |

**Dampak perubahan kalender:**

| Pengajuan | Efek |
|---|---|
| Draft (belum dikirim) | Ikut angka baru saat pegawai membuka & menyimpan ulang formulir. |
| Sudah dikirim | **Tidak berubah.** |

Untuk menghitung ulang semua draft sekaligus:
`python manage.py hitung_ulang_hari_kerja [--dry-run]`.

**Generate ND Karo:** saat admin mengubah tanggal di form, Jumlah Hari Kerja
diisi ulang otomatis dari kalender, tetapi tetap bisa disunting manual
(hanya memengaruhi dokumen, bukan data pengajuan).

---

## 5. Struktur Data

### Tabel baru `HariLibur` (app `paspor`)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `tanggal` | Date, **unik** | Satu baris = satu tanggal. |
| `keterangan` | Char(150) | cth. "Proklamasi Kemerdekaan". |
| `jenis` | Choice | `libur_nasional` atau `cuti_bersama`. |
| `is_active` | Boolean | Hanya yang aktif dihitung. |
| `dibuat_oleh` | FK User, nullable | Admin yang menambah (kosong bila dari seed). |
| `created_at`, `updated_at` | DateTime | Otomatis. |

Libur beberapa hari berturut-turut disimpan sebagai beberapa baris. Tahun
tidak disimpan terpisah — cukup difilter lewat `tanggal__year`.

### Perubahan tabel `Pengajuan`

Tidak ada perubahan skema. Hanya maknanya yang berubah:

| Field | Sebelum | Sekarang |
|---|---|---|
| `jumlah_hari_kerja` | Diketik pegawai | Snapshot hasil hitung sistem |
| `jumlah_hari_kalender` | Property | Tetap property, memakai rumus dari `paspor.kalender` |

Method baru: `Pengajuan.hitung_ulang_hari()` — mengisi ulang
`jumlah_hari_kerja` dari kalender saat ini (khusus draft).

---

## 6. Seed Data Hari Libur

Sumber: **SKB 3 Menteri tentang Hari Libur Nasional dan Cuti Bersama**.
Data disimpan per tahun di `scripts/data/hari_libur_<tahun>.csv`
(kolom `tanggal,keterangan,jenis`).

```powershell
python manage.py seed_hari_libur                  # muat semua CSV (2026 & 2027)
python manage.py seed_hari_libur --tahun 2027     # hanya satu tahun
python manage.py seed_hari_libur --file path.xlsx # berkas lain (.csv / .xlsx)
python manage.py seed_hari_libur --timpa          # perbarui keterangan & jenis yang sudah ada
```

Perintah ini aman dijalankan berulang — tanggal yang sudah ada dilewati
(kecuali `--timpa`). Aturan validasinya sama dengan fitur Import Excel. **Menambah tahun baru:** buat `hari_libur_<tahun>.csv`
dengan format yang sama, lalu jalankan ulang perintah di atas.

### 2026

**Libur Nasional (17 hari)**

| No | Tanggal | Hari | Keterangan |
|--:|---|---|---|
| 1 | 1 Januari | Kamis | Tahun Baru 2026 Masehi |
| 2 | 16 Januari | Jumat | Isra Mikraj Nabi Muhammad SAW |
| 3 | 17 Februari | Selasa | Tahun Baru Imlek 2577 Kongzili |
| 4 | 19 Maret | Kamis | Hari Suci Nyepi, Tahun Baru Saka 1948 |
| 5 | 21 Maret | Sabtu | Hari Raya Idulfitri 1447 H |
| 6 | 22 Maret | Minggu | Hari Raya Idulfitri 1447 H |
| 7 | 3 April | Jumat | Wafat Yesus Kristus |
| 8 | 5 April | Minggu | Hari Kebangkitan Yesus Kristus (Paskah) |
| 9 | 1 Mei | Jumat | Hari Buruh Internasional |
| 10 | 14 Mei | Kamis | Kenaikan Yesus Kristus |
| 11 | 27 Mei | Rabu | Hari Raya Iduladha 1447 H |
| 12 | 31 Mei | Minggu | Hari Raya Waisak 2570 BE |
| 13 | 1 Juni | Senin | Hari Lahir Pancasila |
| 14 | 16 Juni | Selasa | 1 Muharam Tahun Baru Islam 1448 H |
| 15 | 17 Agustus | Senin | Proklamasi Kemerdekaan |
| 16 | 25 Agustus | Selasa | Maulid Nabi Muhammad SAW |
| 17 | 25 Desember | Jumat | Kelahiran Yesus Kristus |

**Cuti Bersama (8 hari)**

| No | Tanggal | Hari | Keterangan |
|--:|---|---|---|
| 1 | 16 Februari | Senin | Tahun Baru Imlek 2577 Kongzili |
| 2 | 18 Maret | Rabu | Hari Suci Nyepi, Tahun Baru Saka 1948 |
| 3 | 20 Maret | Jumat | Hari Raya Idulfitri 1447 H |
| 4 | 23 Maret | Senin | Hari Raya Idulfitri 1447 H |
| 5 | 24 Maret | Selasa | Hari Raya Idulfitri 1447 H |
| 6 | 15 Mei | Jumat | Kenaikan Yesus Kristus |
| 7 | 28 Mei | Kamis | Hari Raya Iduladha 1447 H |
| 8 | 24 Desember | Kamis | Kelahiran Yesus Kristus |

### 2027

**Libur Nasional (18 hari)**

| No | Tanggal | Hari | Keterangan |
|--:|---|---|---|
| 1 | 1 Januari | Jumat | Tahun Baru 2027 Masehi |
| 2 | 5 Januari | Selasa | Isra Mikraj Nabi Muhammad SAW |
| 3 | 6 Februari | Sabtu | Tahun Baru Imlek 2578 Kongzili |
| 4 | 8 Maret | Senin | Hari Suci Nyepi, Tahun Baru Saka 1949 |
| 5 | 10 Maret | Rabu | Hari Raya Idulfitri 1448 H |
| 6 | 11 Maret | Kamis | Hari Raya Idulfitri 1448 H |
| 7 | 26 Maret | Jumat | Wafat Yesus Kristus |
| 8 | 28 Maret | Minggu | Hari Kebangkitan Yesus Kristus (Paskah) |
| 9 | 1 Mei | Sabtu | Hari Buruh Internasional |
| 10 | 6 Mei | Kamis | Kenaikan Yesus Kristus |
| 11 | 17 Mei | Senin | Hari Raya Iduladha 1448 H |
| 12 | 20 Mei | Kamis | Hari Raya Waisak 2571 BE |
| 13 | 1 Juni | Selasa | Hari Lahir Pancasila |
| 14 | 6 Juni | Minggu | 1 Muharam Tahun Baru Islam 1449 H |
| 15 | 15 Agustus | Minggu | Maulid Nabi Muhammad SAW |
| 16 | 17 Agustus | Selasa | Proklamasi Kemerdekaan |
| 17 | 25 Desember | Sabtu | Kelahiran Yesus Kristus (Natal) |
| 18 | 26 Desember | Minggu | Isra Mikraj Nabi Muhammad SAW |

> Isra Mikraj muncul dua kali di 2027 (5 Januari & 26 Desember) karena
> tahun Hijriah lebih pendek dari tahun Masehi.

**Cuti Bersama (8 hari)**

| No | Tanggal | Hari | Keterangan |
|--:|---|---|---|
| 1 | 5 Februari | Jumat | Tahun Baru Imlek 2578 Kongzili |
| 2 | 9 Maret | Selasa | Hari Raya Idulfitri 1448 H |
| 3 | 12 Maret | Jumat | Hari Raya Idulfitri 1448 H |
| 4 | 15 Maret | Senin | Hari Raya Idulfitri 1448 H |
| 5 | 25 Maret | Kamis | Wafat Yesus Kristus |
| 6 | 18 Mei | Selasa | Hari Raya Iduladha 1448 H |
| 7 | 19 Mei | Rabu | Hari Raya Waisak 2571 BE |
| 8 | 24 Desember | Jumat | Kelahiran Yesus Kristus (Natal) |

---

## 7. Peta Kode

| Bagian | Lokasi |
|---|---|
| Model `HariLibur` | [paspor/models.py](../../paspor/models.py), admin di [paspor/admin.py](../../paspor/admin.py) |
| **Rumus hitung hari** (satu-satunya tempat) | [paspor/kalender.py](../../paspor/kalender.py) — `hitung_hari_kalender`, `hitung_hari_kerja`, `rincian_hari` |
| Validasi & simpan hari kerja | `PengajuanForm.clean()` di [pengajuan/forms.py](../../pengajuan/forms.py) |
| Form Setting Kalender | `TambahHariLiburForm`, `HariLiburForm` di [pengajuan/forms.py](../../pengajuan/forms.py) |
| Endpoint JSON `pegawai:hitung_hari` | `hitung_hari` di [pengajuan/views_pegawai.py](../../pengajuan/views_pegawai.py) |
| Views Setting Kalender | `kelola_kalender`, `kalender_data`, `edit_hari_libur`, `toggle_hari_libur`, `hapus_hari_libur`, `impor_kalender`, `template_kalender` di [pengajuan/views_pakln.py](../../pengajuan/views_pakln.py) |
| Baca & simpan Excel/CSV, template Excel | [paspor/impor_libur.py](../../paspor/impor_libur.py) — dipakai menu Import Excel **dan** `seed_hari_libur` (library `openpyxl`) |
| Template formulir pegawai | [templates/pegawai/formulir.html](../../templates/pegawai/formulir.html) |
| Template Setting Kalender | [templates/pakln/kalender.html](../../templates/pakln/kalender.html), [templates/pakln/edit_hari_libur.html](../../templates/pakln/edit_hari_libur.html) |
| Generate ND Karo | [templates/pakln/generate_nd_karo.html](../../templates/pakln/generate_nd_karo.html) |
| Seed & perintah | [paspor/management/commands/](../../paspor/management/commands/) — `seed_hari_libur`, `hitung_ulang_hari_kerja` |
| Data seed | [scripts/data/](../../scripts/data/) — `hari_libur_2026.csv`, `hari_libur_2027.csv` |

Aturan untuk pengembangan berikutnya: semua perhitungan hari (termasuk API
kanal mobile nanti) **wajib** memanggil `paspor.kalender`, dan tidak boleh
mempercayai angka hari kerja kiriman klien.

---

## 8. Pengujian

```powershell
python manage.py test paspor
```

Test di [paspor/tests.py](../../paspor/tests.py) mencakup:

- **Perhitungan:** satu hari, rentang dengan/tanpa libur, hanya akhir pekan,
  libur di hari Minggu, libur nonaktif, lintas tahun, rentang tidak valid,
  deteksi tahun yang belum diatur.
- **Formulir:** nilai hari kerja palsu dari klien diabaikan, melebihi sisa
  cuti ditolak, snapshot tidak berubah setelah kalender diubah.
- **Endpoint:** respons JSON, input tidak valid (400), wajib login.
- **Setting Kalender:** tambah rentang (akhir pekan & duplikat dilewati),
  toggle, hapus, akses ditolak untuk selain Admin Biro PAKLN.
- **Seed:** CSV 2026 & 2027 termuat lengkap dan aman dijalankan ulang.
- **Import Excel:** berkas valid, opsi timpa, satu baris salah → tidak ada
  yang disimpan, kolom hilang, berkas rusak, impor CSV, template yang
  diunduh bisa langsung diimpor ulang, akses ditolak untuk non-admin.
- **Potong cuti:** menyelesaikan proses memotong sisa cuti sebesar hari
  kerja, bukan hari kalender.

**Uji manual:** login sebagai pegawai → Formulir Pengajuan → pilih
16–27 Maret 2026 → Hari Kalender **12**, Hari Kerja **5**, dan rincian
libur muncul tanpa reload.

---

## 9. Keputusan

| # | Pertanyaan | Keputusan |
|---|---|---|
| 1 | Sisa cuti dipotong berapa hari saat Admin Biro PAKLN menyelesaikan proses? | **Jumlah hari kerja** (snapshot pengajuan) — sama dengan dasar validasi sisa cuti di formulir. Sebelumnya dipotong hari kalender. |
| 2 | Apakah cuti bersama dihitung bukan hari kerja? | **Ya** — semua `HariLibur` aktif (libur nasional & cuti bersama) dikecualikan. |
| 3 | Bolehkah admin mengubah hari kerja? | Hanya di form Generate ND Karo (memengaruhi dokumen saja), tidak di data pengajuan. |
