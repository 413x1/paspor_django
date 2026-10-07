# Pengkodean Pengajuan (Non-Dinas)

Aturan pembuatan kode pengajuan (`Pengajuan.kode`) untuk alur Perjalanan Luar
Negeri **Non-Dinas**. Kode dibuat otomatis oleh sistem saat pengajuan pertama
kali disimpan; pengguna tidak mengisinya.

## Format

| | Format | Contoh |
|---|---|---|
| Lama | `PSP-thn-nourut` | `PSP-2026-0142` |
| **Baru** | `PLN[Kode Unor]-ddmmyy-NOURUT` | `PLN01-071026-020` |

Contoh di atas: Kode Unor = `01`, tanggal pengajuan = 7 Oktober 2026,
nomor urut = 20.

## Komponen

| Bagian | Aturan |
|---|---|
| `PLN` | Prefix statis. |
| `[Kode Unor]` | Kode unit organisasi pegawai pemohon (`UnitOrganisasi.code`, 2 karakter, mis. `01`), diambil dari `PegawaiProfile.unit_organisasi` pegawai yang membuat pengajuan. Jika profil pegawai belum punya unit organisasi, dipakai `User.unit_organisasi`; jika keduanya kosong dipakai `00`. |
| `ddmmyy` | Tanggal pengajuan dibuat (hari ini, zona waktu aplikasi): 2 digit hari, 2 digit bulan, 2 digit tahun. |
| `NOURUT` | Nomor urut pengajuan, default **3 angka**. Kurang dari 3 angka wajib ditambah `0` di depan (mis. `001`, `010`, `020`). Jika lebih dari 999 dalam sehari, otomatis menjadi 4 angka (`1000`) — tidak dipotong. |

## Reset harian

`NOURUT` kembali ke `001` setiap berganti hari. Penghitungannya **per Kode Unor
per hari**: nomor berikutnya = nomor tertinggi pada kode berawalan
`PLN[Kode Unor]-ddmmyy-` ditambah 1, atau `001` bila belum ada. Karena tanggal
sudah menjadi bagian prefix, reset terjadi dengan sendirinya tanpa job
terjadwal dan tanpa kolom/tabel tambahan.

Contoh pada 7 Okt 2026:

- Pengajuan pertama Unor `01` → `PLN01-071026-001`
- Pengajuan kedua Unor `01` → `PLN01-071026-002`
- Pengajuan pertama Unor `04` → `PLN04-071026-001` (urutan tiap Unor terpisah)
- Pengajuan pertama Unor `01` pada 8 Okt 2026 → `PLN01-081026-001`

## Catatan teknis

- Implementasi: `Pengajuan._generate_kode()` di `pengajuan/models.py`, dipanggil
  dari `Pengajuan.save()` hanya saat `kode` masih kosong.
- Tidak ada perubahan skema database dan tidak perlu migrasi. `kode` tetap
  `CharField(max_length=20, unique=True)`; kode terpanjang format baru 17
  karakter.
- Pengajuan lama berkode `PSP-thn-nourut` **tidak diubah** dan tetap valid.
  Format lama dan baru berdampingan di tabel yang sama.
- Pencarian nomor tertinggi memakai perbandingan angka (bukan urutan teks), agar
  `1000` tidak dianggap lebih kecil dari `999`.
- Dua pengajuan yang tersimpan tepat bersamaan untuk Unor yang sama berpotensi
  mendapat nomor yang sama; batasan `unique=True` pada `kode` akan menolak yang
  kedua dengan `IntegrityError` (perilaku yang sama dengan format lama). Untuk
  volume saat ini (satu pengajuan aktif per pegawai) risikonya sangat kecil.
