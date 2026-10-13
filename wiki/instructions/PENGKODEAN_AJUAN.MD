# Pengkodean Pengajuan (Non-Dinas & PDLN)

Aturan pembuatan kode pengajuan (`Pengajuan.kode`) untuk perjalanan
**Non-Dinas** dan **Dinas (PDLN)**. Kode dibuat otomatis oleh sistem saat
pengajuan pertama kali disimpan; pengguna tidak mengisinya.

> **Status:** sudah diimplementasikan — Non-Dinas (`PLN…`), PDLN (`PDLN…`), dan
> rotasi nomor urut tahunan. Test: `pengajuan/tests_kode.py`.

## Format

| Jenis | Format lama | Format baru | Contoh |
|---|---|---|---|
| Non-Dinas | `PSP-thn-nourut` | `PLN[Kode Unor]-ddmmyy-NOURUT` | `PLN01-071026-020` |
| Dinas (PDLN) | `PDLN-thn-tipe-nourut` | `PDLN[Kode Unor]-[Tipe]-ddmmyy-NOURUT` | `PDLN01-1-071026-020` |

### Contoh PDLN

Semua contoh: Setjen (Kode Unor `01`), tanggal pengajuan 7 Oktober 2026.

| Tipe PDLN | Kode tipe sistem | `[Tipe]` | Contoh kode |
|---|---|---|---|
| Tipe 1 | `T1` | `1` | `PDLN01-1-071026-020` |
| Tipe 2 — Pendidikan | `T2P` | `2A` | `PDLN01-2A-071026-021` |
| Tipe 2 — Pelatihan | `T2L` | `2B` | `PDLN01-2B-071026-021` |
| Tipe 3 — Penugasan Khusus | `T3` | `3` | `PDLN01-3-071026-021` |

## Komponen

| Bagian | Aturan |
|---|---|
| `PLN` / `PDLN` | Prefix statis: `PLN` untuk Non-Dinas, `PDLN` untuk Dinas. |
| `[Kode Unor]` | Kode unit organisasi pegawai pemohon (`UnitOrganisasi.code`, 2 karakter, mis. `01`), diambil dari `PegawaiProfile.unit_organisasi` pegawai yang membuat pengajuan. Jika profil pegawai belum punya unit organisasi, dipakai `User.unit_organisasi`; jika keduanya kosong dipakai `00`. |
| `[Tipe]` | Khusus PDLN — kode tipe sesuai tabel di atas (`1`, `2A`, `2B`, `3`). Tidak ada pada kode Non-Dinas. |
| `ddmmyy` | Tanggal pengajuan dibuat (hari ini, zona waktu aplikasi): 2 digit hari, 2 digit bulan, 2 digit tahun. |
| `NOURUT` | Nomor urut pengajuan dalam **satu tahun**, default **3 angka**. Kurang dari 3 angka wajib ditambah `0` di depan: `001`, `010`, `100`, `999`. Jika lebih dari 999 dalam setahun, otomatis menjadi 4 angka (`1000`) — tidak dipotong. |

## Nomor urut & rotasi tahunan

`NOURUT` **berlanjut sepanjang tahun** (tidak reset harian) dan kembali ke
`001` setiap **pergantian tahun** (1 Januari). Tanggal `ddmmyy` pada kode tetap
tanggal pengajuan dibuat, tetapi hanya bagian tahunnya (`yy`) yang menentukan
urutan.

Urutan dihitung per **kelompok penghitung**:

| Jenis | Kelompok penghitung | Pola kode yang dihitung (tahun 2026) |
|---|---|---|
| Non-Dinas | Kode Unor + tahun | `PLN[Kode Unor]-dddd26-NNN` |
| PDLN | Kode Unor + tipe + tahun | `PDLN[Kode Unor]-[Tipe]-dddd26-NNN` |

(`dddd` = tanggal & bulan apa pun, `NNN` = nomor urut.)

Nomor berikutnya = nomor tertinggi dalam kelompok tersebut ditambah 1, atau
`001` bila belum ada. Artinya urutan **terpisah per jenis, per tipe PDLN, per
Kode Unor, dan per tahun**. Karena tahun sudah menjadi bagian kode, rotasi
terjadi dengan sendirinya tanpa job terjadwal dan tanpa kolom/tabel tambahan.

Contoh Unor `01`:

| Tanggal | Pengajuan | Kode |
|---|---|---|
| 7 Okt 2026 | Non-Dinas ke-20 tahun 2026 | `PLN01-071026-020` |
| 7 Okt 2026 | Non-Dinas ke-21 tahun 2026 | `PLN01-071026-021` |
| 8 Okt 2026 | Non-Dinas berikutnya — **tidak** reset walau berganti hari | `PLN01-081026-022` |
| 8 Okt 2026 | PDLN Tipe 1 ke-20 tahun 2026 — urutan PDLN terpisah dari Non-Dinas | `PDLN01-1-081026-020` |
| 8 Okt 2026 | PDLN Tipe 2 Pendidikan ke-21 — urutan tiap tipe terpisah | `PDLN01-2A-081026-021` |
| 31 Des 2026 | Non-Dinas terakhir tahun 2026 | `PLN01-311226-148` |
| 2 Jan 2027 | Non-Dinas pertama tahun 2027 — **rotasi tahunan** | `PLN01-020127-001` |

Unor lain memiliki urutan sendiri: Non-Dinas pertama Unor `04` tahun 2026 →
`PLN04-ddmm26-001`.

## Catatan teknis

- Implementasi: `Pengajuan._generate_kode()` di `pengajuan/models.py`, dipanggil
  dari `Pengajuan.save()` hanya saat `kode` masih kosong.
- **Panjang kode.** Kode PDLN terpanjang dengan `NOURUT` 3 angka adalah 20
  karakter (`PDLN01-2A-071026-020`), tepat sama dengan `kode`
  `CharField(max_length=20)` saat ini. `NOURUT` 4 angka (`1000`, lebih dari 999
  pengajuan setahun dalam satu kelompok) akan menjadi 21 karakter. Dengan
  rotasi tahunan kondisi ini jauh lebih mungkin terjadi (mis. Unor besar),
  sehingga `max_length` **wajib** dinaikkan menjadi **25** (satu migrasi
  `AlterField`).
- **Tipe ditentukan saat kode dibuat.** Kode dibuat pada penyimpanan pertama
  formulir, saat `jenis_perjalanan` dan `tipe_pdln` sudah terisi. Kode tidak
  dibuat ulang bila tipe diubah kemudian (kode bersifat tetap).
- **Kode lama tidak diubah.** Pengajuan berkode `PSP-thn-nourut`,
  `PDLN-thn-tipe-nourut`, maupun PDLN berkode `PLN…` (dibuat sebelum format
  PDLN baru dieksekusi) tetap valid dan berdampingan di tabel yang sama.
- **Pencarian kelompok.** Karena tanggal ada di tengah kode, kelompok tidak
  bisa dicari dengan awalan saja. Kode dicari dengan pola (regex) yang
  mengunci jenis, Kode Unor, tipe, dan tahun, mis. Non-Dinas Unor `01` tahun
  2026: `^PLN01-[0-9]{4}26-[0-9]+$`; PDLN Tipe 2 Pendidikan:
  `^PDLN01-2A-[0-9]{4}26-[0-9]+$`. Pola ini tidak tertukar antar jenis
  (`PLN01-` tidak cocok dengan `PDLN01-`) dan tidak ikut menghitung kode lama
  `PSP-…` / `PDLN-thn-…`.
- Pencarian nomor tertinggi memakai perbandingan angka (bukan urutan teks), agar
  `1000` tidak dianggap lebih kecil dari `999`. Nomor diambil dari bagian
  setelah tanda `-` terakhir, sehingga berlaku untuk kedua format.
- **Peralihan dari reset harian.** Kode `PLN…` 2026 yang sudah terbit dengan
  reset harian ikut dihitung; nomor berikutnya melanjutkan dari nomor
  tertinggi yang pernah terbit di tahun itu. Tidak ada bentrok kode karena
  kode lama dan baru selalu berbeda tanggal atau nomor.
- Dua pengajuan yang tersimpan tepat bersamaan untuk kelompok yang sama berpotensi
  mendapat nomor yang sama; batasan `unique=True` pada `kode` akan menolak yang
  kedua dengan `IntegrityError`. Untuk volume saat ini (satu pengajuan aktif
  per pegawai) risikonya sangat kecil.

## Perubahan kode

Perubahan yang diterapkan untuk format PDLN dan rotasi tahunan:

| # | File | Perubahan |
|:-:|---|---|
| 1 | `pengajuan/models.py` | Tambah peta `KODE_TIPE = {"T1": "1", "T2P": "2A", "T2L": "2B", "T3": "3"}`. `_generate_kode()`: kepala kode `PDLN{unor}-{KODE_TIPE[tipe_pdln]}-` bila `is_pdln` dan `tipe_pdln` terisi, selain itu `PLN{unor}-`; nomor tertinggi dicari dengan `kode__regex` `^{kepala}[0-9]{4}{yy}-[0-9]+$` (rotasi tahunan, menggantikan `kode__startswith` prefix harian); hasil `{kepala}{ddmmyy}-{nourut:03d}`. `kode` `max_length` 20 → 25. |
| 2 | `pengajuan/migrations/0023_pengajuan_kode_max_length_25.py` | Migrasi `AlterField` untuk `Pengajuan.kode` (`max_length=25`). Tanpa migrasi data — kode lama tidak diubah. |
| 3 | `pengajuan/tests_pdln.py`, `pengajuan/tests_kode.py` | Perbarui `test_kode_dan_detail_pdln` (sebelumnya mengharapkan format lama `PDLN-<tahun>-T1-`) dan tambah test: format tiap tipe, padding `001`, nomor **berlanjut** saat berganti hari, kembali `001` saat berganti tahun, urutan terpisah per jenis/tipe/Unor, Non-Dinas tetap `PLN…`. |
| 4 | `wiki/instructions/BISNIS_PROSES_PDLN.MD` | Perbarui kolom "Prefiks kode pengajuan" di §2 dan catatan panjang kode di §8.2 agar merujuk dokumen ini. |
