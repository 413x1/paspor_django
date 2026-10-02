# Riwayat Pemrosesan Pengajuan

> **Status:** sudah diimplementasikan.
> **Pengguna:** Pegawai, Admin Unor, Admin Biro PAKLN.

## Daftar Isi

1. [Ringkasan](#1-ringkasan)
2. [Alur Proses & Peristiwa yang Dicatat](#2-alur-proses--peristiwa-yang-dicatat)
3. [Aturan Visibilitas Pesan](#3-aturan-visibilitas-pesan)
4. [Struktur Data](#4-struktur-data)
5. [Pencatatan Riwayat](#5-pencatatan-riwayat)
6. [Tampilan (UI)](#6-tampilan-ui)
7. [Migrasi Data Lama](#7-migrasi-data-lama)
8. [Peta Kode](#8-peta-kode)
9. [Pengujian](#9-pengujian)
10. [Keputusan & Pertanyaan Terbuka](#10-keputusan--pertanyaan-terbuka)

---

## 1. Ringkasan

### Masalah

Saat ini pesan pengembalian disimpan di dua kolom saja pada `Pengajuan`:

- `catatan_unor` — catatan Admin Unor ke pegawai, **dikosongkan** saat
  pegawai mengirim ulang ([views_pegawai.py](../../pengajuan/views_pegawai.py) `upload_dokumen`).
- `catatan_pakln` — catatan Admin Biro PAKLN ke Admin Unor, **dikosongkan**
  saat Admin Unor meneruskan ulang ([views_unor.py](../../pengajuan/views_unor.py) `upload_dokumen`).

Akibatnya:

- Hanya pesan **terakhir** yang tersimpan; pengembalian kedua menimpa yang
  pertama, dan setelah dikirim ulang pesan hilang sama sekali.
- Tidak ada catatan **siapa** memproses dan **kapan** (selain 3 tanggal
  `tgl_pengajuan`, `tgl_masuk_pakln`, `tgl_selesai`).
- Timeline Monitor Progres (`Pengajuan.timeline`) hanya menampilkan 4 tahap
  linear; bolak-balik pengembalian tidak terlihat.
- Tabel `Notification` bukan pengganti: satu baris per penerima, bisa
  di-*dismiss*, dan bukan jejak proses.

### Solusi

Tambahkan tabel **`RiwayatPengajuan`** — log *append-only* berisi satu
baris untuk setiap perpindahan status, lengkap dengan aktor, waktu, dan
pesan (jika ada). Riwayat ditampilkan sebagai **Timeline Proses** 4 tahap
(Diajukan Pegawai → Dalam Proses Unor → Dalam Proses Biro PAKLN → Selesai);
di bawah setiap tahap tercantum peristiwa yang terjadi di tahap itu beserta
pesannya, difilter sesuai peran yang melihat (lihat [§3](#3-aturan-visibilitas-pesan)).

### Kriteria penerimaan

| # | Kriteria |
|---|---|
| 1 | Setiap perpindahan status tercatat dengan aktor, waktu, status asal & tujuan |
| 2 | Setiap pesan pengembalian tersimpan permanen, tidak tertimpa oleh pengembalian berikutnya |
| 3 | Pegawai melihat pesan dari Admin Unor (dan pesan perannya sendiri) |
| 4 | Admin Unor melihat pesan dari Admin Biro PAKLN dan pesan yang ditulis Admin Unor sendiri |
| 5 | Admin Biro PAKLN melihat seluruh riwayat dan seluruh pesan |
| 6 | Penyaringan pesan dilakukan di server, bukan disembunyikan di template |
| 7 | Riwayat tidak dapat diubah/dihapus dari UI aplikasi |
| 8 | Perilaku yang ada (banner catatan, notifikasi, deteksi kirim ulang) tidak berubah |

**Di luar cakupan:** riwayat unggah/hapus dokumen per berkas, riwayat
generate ND (sudah ada di `DokumenGenerateLog`), balasan/percakapan
dua arah atas sebuah pesan, fitur "Tolak Permanen".

---

## 2. Alur Proses & Peristiwa yang Dicatat

Status yang ada di `Pengajuan.Status`: `belum` → `proses` → `proses_pakln` → `selesai`.

```
            ┌──────────── DIKEMBALIKAN_UNOR (pesan → pegawai) ─────────┐
            ▼                                                          │
 [belum] ──DIKIRIM / DIKIRIM_ULANG (pesan → Unor)──► [proses] ──DITERUSKAN_PAKLN / DITERUSKAN_ULANG (pesan → PAKLN)──► [proses_pakln] ──SELESAI──► [selesai]
                                        ▲                                  │
                                        └── DIKEMBALIKAN_PAKLN (pesan → Unor) ┘
```

| Kode aksi | Label | Aktor | Status asal → tujuan | Pesan wajib | Titik kode saat ini |
|---|---|---|---|---|---|
| `dikirim` | Diajukan ke Admin Unor | Pegawai | `belum` → `proses` | – | `views_pegawai.upload_dokumen` (`kirim`, bukan resubmit) |
| `dikirim_ulang` | Perbaikan dikirim ke Admin Unor | Pegawai | `belum` → `proses` | ✅ (balasan untuk Unor) | `views_pegawai.upload_dokumen` (`kirim`, `is_resubmit`) |
| `dikembalikan_unor` | Dikembalikan Admin Unor ke Pegawai | Admin Unor | `proses` → `belum` | ✅ | `views_unor.preview` (`kembalikan`) |
| `diteruskan_pakln` | Diteruskan ke Biro PAKLN | Admin Unor | `proses` → `proses_pakln` | – | `views_unor.upload_dokumen` (`teruskan`, bukan penerusan ulang) |
| `diteruskan_ulang` | Perbaikan diteruskan ke Biro PAKLN | Admin Unor | `proses` → `proses_pakln` | ✅ (balasan untuk PAKLN) | `views_unor.upload_dokumen` (`teruskan`, `is_ulang`) |
| `dikembalikan_pakln` | Dikembalikan Biro PAKLN ke Admin Unor | Admin PAKLN | `proses_pakln` → `proses` | ✅ | `views_pakln.preview` (`kembalikan`) |
| `selesai` | Selesai diproses | Admin PAKLN | `proses_pakln` → `selesai` | – | `views_pakln.upload_dokumen` (`selesaikan`) |

Catatan:

- Menyimpan draft formulir (`formulir_pengajuan`) **tidak** dicatat — belum
  ada proses. Opsional: catat `dibuat` saat pengajuan pertama kali disimpan.
- **Catatan dua arah.** Penerima pengembalian wajib membalas dengan
  catatan saat mengirim lagi: pegawai → Admin Unor (`dikirim_ulang`) dan
  Admin Unor → Biro PAKLN (`diteruskan_ulang`). Kolom "Catatan perbaikan"
  hanya muncul (dan hanya divalidasi) bila pengajuan sedang dikembalikan.
- Deteksi pengiriman ulang: `is_resubmit = bool(pengajuan.catatan_unor)`;
  penerusan ulang: `is_ulang = bool(pengajuan.catatan_pakln)` — keduanya
  dibaca sebelum kolom dikosongkan.
- Balasan tampil sebagai banner "↻ Perbaikan dari …" di halaman pratinjau
  pihak yang mengembalikan (`riwayat.catatan_perbaikan`) selama itu
  peristiwa terakhir, dan selalu ada di Timeline Proses. Balasan juga
  dimuat di notifikasi penerima (`notify_resubmit_unor`,
  `notify_approve_unor` — yang terakhir hanya untuk Admin PAKLN, bukan pegawai).
- Setelah `dikembalikan_pakln`, Admin Unor boleh langsung meneruskan lagi
  (`diteruskan_ulang`) **atau** mengembalikan ke pegawai
  (`dikembalikan_unor`). Keduanya sudah didukung view yang ada.

---

## 3. Aturan Visibilitas Pesan

Aturan berlaku pada **pesan** (`catatan`). Baris peristiwa (aksi, waktu,
aktor) tetap tampil untuk semua peran agar timeline utuh; untuk peran yang
tidak berhak, pesan diganti keterangan netral.

| Peristiwa | Pegawai | Admin Unor | Admin Biro PAKLN |
|---|---|---|---|
| `dikembalikan_unor` (pesan Unor → Pegawai) | ✅ lihat pesan | ✅ lihat pesan (pesan sendiri) | ✅ lihat pesan |
| `dikirim_ulang` (balasan Pegawai → Unor) | ✅ lihat pesan (pesan sendiri) | ✅ lihat pesan | ✅ lihat pesan |
| `dikembalikan_pakln` (pesan PAKLN → Unor) | ❌ pesan disembunyikan | ✅ lihat pesan | ✅ lihat pesan |
| `diteruskan_ulang` (balasan Unor → PAKLN) | ❌ pesan disembunyikan | ✅ lihat pesan (pesan sendiri) | ✅ lihat pesan |
| Peristiwa tanpa pesan | ✅ | ✅ | ✅ |

Dirumuskan sebagai aturan:

```
# Pesan berada pada salah satu dari dua jalur:
#   Pegawai <-> Admin Unor        : dikembalikan_unor, dikirim_ulang
#   Admin Unor <-> Admin PAKLN    : dikembalikan_pakln, diteruskan_ulang
boleh_lihat_pesan(user, riwayat) =
    riwayat.aksi in JALUR_PEGAWAI           if user.role == pegawai
    True                                    if user.role in (admin_unor, admin_pakln)
```

Ketentuan tambahan:

- Nama aktor: pegawai melihat label peran ("Admin Unor", "Biro PAKLN"),
  bukan nama pribadi admin. Admin Unor & Admin PAKLN melihat nama lengkap.
- Untuk pegawai, peristiwa `dikembalikan_pakln` ditampilkan dengan label
  netral **"Dikembalikan ke Admin Unor untuk perbaikan"** tanpa pesan.
- Penyaringan **wajib di server**: pesan yang tidak berhak tidak boleh
  ikut terkirim ke template/JSON sama sekali (bukan sekadar `display:none`).
- Akses ke riwayat mengikuti akses ke pengajuannya, yang sudah dibatasi:
  pegawai hanya miliknya (`pegawai=request.user`), Admin Unor hanya unit
  organisasinya (`views_unor._scoped`), Admin PAKLN semua.

---

## 4. Struktur Data

Model baru di [pengajuan/models.py](../../pengajuan/models.py):

```python
class RiwayatPengajuan(models.Model):
    """Log append-only setiap perpindahan status Pengajuan beserta pesan
    pengembalian. Tidak pernah di-update/dihapus dari aplikasi."""

    class Aksi(models.TextChoices):
        DIKIRIM = "dikirim", "Diajukan ke Admin Unor"
        DIKIRIM_ULANG = "dikirim_ulang", "Perbaikan dikirim ke Admin Unor"
        DIKEMBALIKAN_UNOR = "dikembalikan_unor", "Dikembalikan Admin Unor ke Pegawai"
        DITERUSKAN_PAKLN = "diteruskan_pakln", "Diteruskan ke Biro PAKLN"
        DIKEMBALIKAN_PAKLN = "dikembalikan_pakln", "Dikembalikan Biro PAKLN ke Admin Unor"
        SELESAI = "selesai", "Selesai diproses"

    pengajuan = models.ForeignKey(Pengajuan, on_delete=models.CASCADE, related_name="riwayat")
    aksi = models.CharField(max_length=30, choices=Aksi.choices)
    status_dari = models.CharField(max_length=20, choices=Pengajuan.Status.choices)
    status_ke = models.CharField(max_length=20, choices=Pengajuan.Status.choices)

    aktor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="riwayat_pengajuan",
    )
    # Snapshot saat kejadian — tetap benar walau user kemudian dihapus
    # atau perannya diganti. Dasar aturan visibilitas pesan.
    aktor_role = models.CharField(max_length=20)
    aktor_nama = models.CharField(max_length=150)

    catatan = models.TextField(blank=True)
    # default (bukan auto_now_add) agar migrasi backfill bisa mengisi
    # tanggal historis.
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["pengajuan", "created_at"])]
        verbose_name = "Riwayat Pengajuan"
        verbose_name_plural = "Riwayat Pengajuan"
```

Keputusan desain:

- **`aktor_role` & `aktor_nama` di-snapshot**, bukan dibaca dari `aktor`
  saat tampil, karena aturan visibilitas bergantung pada peran *saat pesan
  ditulis*.
- **`catatan_unor` / `catatan_pakln` dipertahankan.** Keduanya tetap dipakai
  untuk banner "⚠ Dikembalikan…" dan deteksi `is_resubmit`. Riwayat adalah
  tambahan, bukan pengganti — mengurangi risiko regresi.
- Migrasi: `0014_riwayatpengajuan.py` (skema) + `0015_backfill_riwayat.py`
  (data, lihat [§7](#7-migrasi-data-lama)).

---

## 5. Pencatatan Riwayat

### Helper

Modul baru `pengajuan/riwayat.py` — satu pintu untuk menulis & membaca:

```python
def catat(pengajuan, aksi, aktor, status_dari, catatan=""):
    """Tambah satu baris riwayat. status_ke diambil dari pengajuan.status
    (panggil SETELAH status diubah)."""

def riwayat_untuk(pengajuan, user):
    """Daftar riwayat yang siap ditampilkan untuk `user`: pesan yang tidak
    berhak sudah dikosongkan, label & nama aktor sudah disesuaikan peran."""

def boleh_lihat_pesan(user, riwayat) -> bool: ...

def timeline_dengan_riwayat(pengajuan, user):
    """4 tahap Pengajuan.timeline, tiap tahap berisi entri riwayat yang
    terjadi di tahap itu (berdasarkan status_dari)."""

def konteks(pengajuan, user):
    """{'timeline': ...} untuk partial timeline/riwayat."""
```

### Pemanggilan di view

Di setiap titik pada tabel [§2](#2-alur-proses--peristiwa-yang-dicatat):

1. Simpan `status_dari = pengajuan.status` **sebelum** status diubah.
2. Ubah status & `save()` seperti sekarang.
3. Panggil `riwayat.catat(...)` **dalam `transaction.atomic()` yang sama**
   dengan `save()`, agar status & riwayat tidak pernah tidak sinkron.
4. Notifikasi (`notify_*`) tetap dipanggil seperti sekarang, setelah blok atomic.

Contoh (`views_unor.preview`, cabang `kembalikan`):

```python
status_dari = pengajuan.status
with transaction.atomic():
    pengajuan.status = Pengajuan.Status.BELUM
    pengajuan.submitted = False
    pengajuan.preview_unor_agree = False
    pengajuan.catatan_unor = catatan
    pengajuan.save()
    riwayat.catat(pengajuan, RiwayatPengajuan.Aksi.DIKEMBALIKAN_UNOR,
                  request.user, status_dari, catatan=catatan)
notify_reject_unor(pengajuan, catatan)
```

`views_pakln.upload_dokumen` (`selesaikan`) sudah memakai
`transaction.atomic()` — cukup tambahkan `riwayat.catat` di dalamnya.

---

## 6. Tampilan (UI)

### Partial bersama

- `templates/partials/_timeline_proses.html` — daftar `.timeline` 4 tahap
  (Diajukan Pegawai → Dalam Proses Unor → Dalam Proses Biro PAKLN → Selesai),
  dipakai semua peran.
- `templates/partials/_riwayat_pengajuan.html` — card "Timeline Proses"
  yang membungkus partial di atas (halaman Admin Unor & Biro PAKLN).

View menambahkan `**riwayat.konteks(pengajuan, request.user)` ke context.
Template **tidak** berisi logika peran — hanya menampilkan data yang sudah
difilter.

Setiap tahap menampilkan judul, deskripsi, tanggal, dan status
(selesai/aktif/belum). Di bawahnya, entri riwayat yang terjadi di tahap itu
(dikelompokkan menurut `status_dari`, mis. "Dikembalikan ke Pegawai" berada di
tahap Dalam Proses Unor), urut lama → baru, per baris:

- ikon/warna per aksi (kembali = kuning/warning, selesai = hijau, lainnya = biru),
- label aksi, nama/peran aktor, tanggal & jam (format Indonesia),
- kotak pesan bila `catatan` terlihat untuk user tersebut.

Gunakan token warna & kelas yang sudah ada di [static/css/style.css](../../static/css/style.css)
(pola `.timeline` + `.riwayat-list.timeline-riwayat`); naikkan versi `?v=` di `base.html`
bila CSS berubah.

### Letak per peran

| Peran | Halaman | Keterangan |
|---|---|---|
| Pegawai | `pegawai/monitor.html` | Card "Timeline Proses" yang include `_timeline_proses.html` (tidak ada card Riwayat terpisah) |
| Admin Unor | `unor/preview.html`, `unor/upload.html` | Preview: grid `.preview-split` — card Pratinjau ∣ Direktori Unggahan Pegawai, lalu ↩ Kembalikan ∣ Timeline Proses. Upload: di atas tombol navigasi bawah |
| Admin PAKLN | `pakln/preview.html`, `pakln/upload.html` | Preview: grid `.preview-split` — Pratinjau ∣ Direktori Dokumen dari Unor, lalu ↩ Kembalikan ∣ Timeline Proses (Timeline Proses penuh bila tombol Kembalikan tidak tampil). Upload: di atas tombol navigasi bawah |

Opsional (tahap berikutnya): kolom "Jumlah dikembalikan" pada tabel
dashboard Admin PAKLN, dan tombol "Lihat Riwayat" (modal) di dashboard
Unor/PAKLN.

---

## 7. Migrasi Data Lama

Pengajuan yang sudah berjalan tidak punya riwayat. Data migration
`0015_backfill_riwayat.py` membuat baris *perkiraan* dari data yang ada:

| Sumber | Baris yang dibuat |
|---|---|
| `tgl_pengajuan` terisi | `dikirim` |
| `tgl_masuk_pakln` terisi | `diteruskan_pakln` |
| `tgl_selesai` terisi | `selesai` |
| `catatan_unor` tidak kosong | `dikembalikan_unor` dengan pesan tsb. |
| `catatan_pakln` tidak kosong | `dikembalikan_pakln` dengan pesan tsb. |

- Aksi `dikirim`: `aktor` = pegawai pemilik pengajuan (pasti diketahui).
- Aksi admin: `aktor` = `NULL`, `aktor_nama` = "(data lama)", `aktor_role` sesuai aksi.
- `created_at` diisi dari tanggal terkait (jam 00:00); pengembalian tanpa
  tanggal diisi `updated_at` pengajuan.
- Urutan logis dijaga: waktu tiap baris tidak boleh lebih awal dari baris sebelumnya.
- Lewati pengajuan yang sudah punya riwayat (migrasi aman dijalankan ulang).
- Pengembalian lama yang sudah dikosongkan memang tidak bisa dipulihkan.

---

## 8. Peta Kode

| File | Perubahan |
|---|---|
| `pengajuan/models.py` | Model `RiwayatPengajuan` |
| `pengajuan/migrations/0014_riwayatpengajuan.py` | Skema |
| `pengajuan/migrations/0015_backfill_riwayat.py` | Backfill data lama |
| `pengajuan/riwayat.py` (baru) | `catat`, `riwayat_untuk`, `boleh_lihat_pesan`, `timeline_dengan_riwayat`, `konteks` |
| `pengajuan/views_pegawai.py` | `upload_dokumen` (catat `dikirim`/`dikirim_ulang`); `monitor_progres` (kirim `riwayat` ke context) |
| `pengajuan/views_unor.py` | `preview` (catat `dikembalikan_unor`, kirim `riwayat`); `upload_dokumen` (catat `diteruskan_pakln`, kirim `riwayat`) |
| `pengajuan/views_pakln.py` | `preview` (catat `dikembalikan_pakln`, kirim `riwayat`); `upload_dokumen` (catat `selesai`, kirim `riwayat`) |
| `pengajuan/admin.py` | Daftarkan `RiwayatPengajuan` sebagai *read-only* (tanpa add/change/delete) + inline read-only di `PengajuanAdmin` |
| `templates/partials/_timeline_proses.html`, `templates/partials/_riwayat_pengajuan.html` (baru) | Timeline 4 tahap + riwayat per tahap; card Timeline Proses (Unor/PAKLN) |
| `templates/pegawai/monitor.html`, `templates/unor/preview.html`, `templates/unor/upload.html`, `templates/pakln/preview.html`, `templates/pakln/upload.html` | Include partial (pegawai: `_timeline_proses.html`) |
| `static/css/style.css`, `templates/base.html` | Gaya timeline & riwayat per tahap; naikkan `?v=` |
| `pengajuan/tests.py` (baru) | Lihat [§9](#9-pengujian) |

---

## 9. Pengujian

Buat `pengajuan/tests.py` (pola data mengikuti `_DataMixin` di
[paspor/tests.py](../../paspor/tests.py)). Jalankan `python manage.py test pengajuan`.

**Pencatatan**

1. Pegawai kirim → 1 baris `dikirim`, `belum` → `proses`, aktor = pegawai.
2. Unor kembalikan dengan catatan → baris `dikembalikan_unor` berisi catatan.
3. Pegawai kirim ulang → baris `dikirim_ulang` (bukan `dikirim`).
4. Unor teruskan → `diteruskan_pakln`; PAKLN kembalikan → `dikembalikan_pakln` berisi catatan.
5. PAKLN selesaikan → `selesai`.
6. Dua kali pengembalian → dua baris dengan pesan masing-masing (tidak tertimpa).
7. Kembalikan tanpa catatan (ditolak view) → tidak ada baris baru.

**Visibilitas** — skenario penuh: kirim → dikembalikan Unor → kirim ulang →
diteruskan → dikembalikan PAKLN → diteruskan → selesai.

8. Pegawai: pesan Unor terlihat; pesan PAKLN **tidak ada di response** (`assertNotContains`).
9. Admin Unor: pesan PAKLN dan pesan Unor sendiri terlihat.
10. Admin PAKLN: kedua pesan terlihat.
11. Pegawai lain / Admin Unor unit lain → 404 (akses pengajuan tetap terbatas).
12. `riwayat_untuk` mengosongkan `catatan` untuk peran yang tidak berhak (uji unit tanpa template).

**Regresi**

13. Banner `catatan_unor` / `catatan_pakln` & notifikasi tetap berfungsi seperti sebelumnya.

---

## 10. Keputusan & Pertanyaan Terbuka

### Keputusan

| # | Keputusan | Alasan |
|---|---|---|
| 1 | Tabel log terpisah, bukan memperluas `Notification` | Notifikasi per penerima & bisa di-dismiss; riwayat harus satu sumber yang utuh |
| 2 | `catatan_unor` / `catatan_pakln` tetap ada | Banner & deteksi kirim ulang tidak perlu diubah |
| 3 | Peran & nama aktor di-snapshot | Visibilitas bergantung peran saat pesan ditulis |
| 4 | Peristiwa tetap tampil untuk semua peran, hanya pesan yang disaring | Timeline tetap utuh & jujur ("pernah dikembalikan") tanpa membocorkan isi pesan |
| 5 | Filter di server (`riwayat_untuk`) | Pesan terlarang tidak pernah sampai ke browser |

### Pertanyaan terbuka (implementasi memakai default di bawah)

1. ~~Admin Unor melihat pesannya sendiri ke pegawai?~~ **Diputuskan: ya** —
   setiap peran selalu melihat pesan yang ditulis perannya sendiri.
2. **Pegawai melihat peristiwa "dikembalikan PAKLN ke Unor"?** Rencana ini
   menampilkannya dengan label netral tanpa pesan. Alternatif: sembunyikan
   baris tersebut sepenuhnya dari pegawai.
3. **Perlu catat `dibuat` (draft pertama disimpan)?** Default: tidak.
