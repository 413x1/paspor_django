# Rencana Implementasi — PDLN Tipe 2 Pendidikan v2 (Admin BKO)

> **Acuan bisnis:** [PDLN_TIPE_2_FLOW.MD §8](PDLN_TIPE_2_FLOW.MD#8-versi-lanjutan-v2--sk-tubel-oleh-admin-bko)
> (semua keputusan #1–#11 sudah final).
> **Cakupan:** hanya `tipe_pdln = T2P`. T2L, T1, T3, dan Non-Dinas tidak berubah.
> **Status:** sudah diimplementasikan. Penyimpangan dari rencana dicatat di
> [§13](#13-catatan-implementasi).

---

## Daftar Isi

1. [Ringkasan Perubahan](#1-ringkasan-perubahan)
2. [Prinsip Desain](#2-prinsip-desain)
3. [Fase 1 — Model, Role & Migrasi](#3-fase-1--model-role--migrasi)
4. [Fase 2 — Logika Domain](#4-fase-2--logika-domain)
5. [Fase 3 — Halaman Admin BKO](#5-fase-3--halaman-admin-bko)
6. [Fase 4 — Perubahan Alur Aktor Lain](#6-fase-4--perubahan-alur-aktor-lain)
7. [Fase 5 — Notifikasi](#7-fase-5--notifikasi)
8. [Fase 6 — Navigasi, Seed & Admin](#8-fase-6--navigasi-seed--admin)
9. [Fase 7 — Test](#9-fase-7--test)
10. [Fase 8 — Dokumentasi](#10-fase-8--dokumentasi)
11. [Urutan Pengerjaan & Checklist](#11-urutan-pengerjaan--checklist)
12. [Asumsi & Risiko](#12-asumsi--risiko)
13. [Catatan Implementasi](#13-catatan-implementasi)

---

## 1. Ringkasan Perubahan

| # | Perubahan | Keputusan acuan |
|:-:|---|---|
| 1 | Role baru **Admin BKO** (`admin_bko`), cakupan semua unor, hanya T2P | #1, #5 |
| 2 | Teruskan dari BPSDM membuka **track BKO paralel** di samping tahap PAKLN | — |
| 3 | SK Tugas Belajar pindah dari dokumen PAKLN ke dokumen **BKO** | — |
| 4 | Admin BKO: **Unggah SK Tubel** atau **Tutup Pemrosesan** (catatan wajib, terlihat semua pihak); tidak bisa mengembalikan | #2 |
| 5 | Admin BKO boleh bertindak saat pengajuan sedang dikembalikan | #3 |
| 6 | **Buka Kembali** track yang ditutup oleh Admin BKO **atau** Admin PAKLN (catatan wajib) | #8, #10 |
| 7 | PAKLN **Selesai** terkunci sampai SK Tubel ada; bila track ditutup PAKLN memilih **Buka Kembali / Lanjutkan tanpa SK Tubel / Hentikan** | #4, #7 |
| 8 | Catatan "Lanjutkan tanpa SK Tubel" wajib, **hanya terlihat Admin PAKLN** | #11 |
| 9 | **Hentikan** = Admin PAKLN mengajukan & langsung menyetujui pembatalan (tanpa jenjang Unor), hanya saat track ditutup | #9 |
| 10 | Label `ikatan_dinas_ttd` BPSDM menjadi "Perjanjian Ikatan Dinas ttd full" | — |
| 11 | Semua data T2P (data QC) dimigrasikan ke pola v2 | #6 |

---

## 2. Prinsip Desain

1. **Track BKO bukan status pengajuan.** `Pengajuan.status` dan `alur.ALUR["T2P"]`
   tidak berubah; kemajuan BKO disimpan di field terpisah `status_bko`.
   Pengembalian berjenjang, timeline 5 tahap, dan report status tetap berjalan.
2. **Ikuti pola tahap yang sudah ada.** Tahap `"bko"` didaftarkan di registri
   `persyaratan` (model dokumen sendiri `DokumenBko`) sehingga halaman unggah,
   pratinjau direktori, dan validasi kelengkapan memakai helper yang sama
   (`tahap.konteks_dokumen`, `tahap.proses_unggah`, `persyaratan.direktori`).
3. **Satu pintu untuk transisi track BKO.** Semua perubahan `status_bko`
   lewat modul baru `pengajuan/bko.py` (di dalam `transaction.atomic()` +
   `alur.kunci`), dipanggil dari `views_bpsdm`, `views_bko`, dan `views_pakln`.
4. **Visibilitas catatan diputuskan di server** (`riwayat.boleh_lihat_pesan`),
   tidak di template.
5. **Pembekuan:** semua aksi track BKO (unggah, hapus, tutup, buka kembali,
   lanjutkan tanpa SK Tubel, hentikan) ditolak bila `alur.alasan_dibekukan(p)`.

---

## 3. Fase 1 — Model, Role & Migrasi

### 3.1 `accounts`

| File | Perubahan |
|---|---|
| `accounts/models.py` | `User.Role.ADMIN_BKO = "admin_bko", "Admin BKO"`; method `is_admin_bko()`. |
| `accounts/migrations/0007_alter_user_role_admin_bko.py` | `AlterField` choices `role`. |
| `accounts/forms.py` | Pastikan pilihan role di form kelola user memuat Admin BKO (ikuti cara `admin_bpsdm` ditangani). |
| `accounts/views.py` | Redirect setelah login: `admin_bko` → `bko:dashboard`. |

### 3.2 `pengajuan/models.py`

**`Pengajuan` — field baru:**

```python
class StatusBko(models.TextChoices):
    MENUNGGU = "menunggu", "Menunggu SK Tubel"
    DIUNGGAH = "diunggah", "SK Tubel Diunggah"
    DITUTUP = "ditutup", "Ditutup Admin BKO"

tgl_masuk_bko = models.DateField(null=True, blank=True)
status_bko = models.CharField(max_length=10, choices=StatusBko.choices, blank=True)
catatan_bko = models.TextField("Catatan Penutupan BKO", blank=True)
tgl_bko_ditutup = models.DateField(null=True, blank=True)
```

Property bantu:

```python
@property
def pakai_bko(self):            # T2P saja
    return self.tipe_pdln == self.TipePdln.T2P

@property
def track_bko_terbuka(self):    # sudah diteruskan BPSDM
    return self.pakai_bko and bool(self.status_bko)
```

Tambah index `models.Index(fields=["tipe_pdln", "status_bko"])` untuk antrean dasbor BKO.

**Model baru `DokumenBko`** (pola sama dengan `DokumenBpsdm`):

```python
def dokumen_bko_path(instance, filename):
    return f"pengajuan/{instance.pengajuan.kode}/bko/{instance.jenis}/{filename}"

class DokumenBko(models.Model):
    """Dokumen administrasi Admin BKO (khusus PDLN Tipe 2 Pendidikan)."""
    class Jenis(models.TextChoices):
        SK_TUBEL = "sk_tubel", "SK Tugas Belajar"
    pengajuan = FK(Pengajuan, related_name="dokumen_bko")
    jenis, file, tanggal_surat, uploaded_at   # identik DokumenBpsdm
    class Meta: unique_together = ("pengajuan", "jenis")
```

**`RiwayatPengajuan.Aksi` — aksi baru:**

| Kode | Label | Aktor | status_dari → status_ke |
|---|---|---|---|
| `diteruskan_bko` | Diteruskan ke Admin BKO | Admin BPSDM | `proses_bpsdm → proses_pakln` |
| `sk_tubel_diunggah` | SK Tugas Belajar diunggah | Admin BKO | tetap (status saat itu) |
| `ditutup_bko` | Pemrosesan ditutup Admin BKO | Admin BKO | tetap |
| `dibuka_ulang_bko` | Pemrosesan BKO dibuka kembali | Admin BKO / Admin PAKLN | tetap |
| `selesai_tanpa_sk_tubel` | Selesai diproses tanpa SK Tugas Belajar | Admin PAKLN | `proses_pakln → selesai` |

> Penghapusan SK Tubel oleh BKO tidak dicatat di riwayat (cukup Log Sistem
> `HAPUS_DOKUMEN`, sama seperti hapus dokumen tahap lain).

**Perubahan lain:**

- `DokumenBpsdm.Jenis.IKATAN_DINAS_TTD` label → "Perjanjian Ikatan Dinas ttd full".
- `DokumenPakln.Jenis.SK_TUBEL` dihapus (setelah data dipindah, lihat 3.3).

### 3.3 Migrasi `pengajuan`

| Migrasi | Isi |
|---|---|
| `0020_v2_bko_skema.py` | Field baru `Pengajuan`, index, model `DokumenBko`, choices `RiwayatPengajuan.aksi`, label `DokumenBpsdm.jenis`. |
| `0021_v2_bko_data.py` | `RunPython` (lihat bawah). Reverse: kembalikan `DokumenBko` → `DokumenPakln`. |
| `0022_v2_hapus_sk_tubel_pakln.py` | `AlterField` choices `DokumenPakln.jenis` tanpa `sk_tubel`. |

Isi `0021` (data QC, semua ikut v2):

1. Setiap `DokumenPakln(jenis="sk_tubel")` → buat `DokumenBko` dengan `file.name`,
   `tanggal_surat`, `uploaded_at` yang sama (path berkas tidak dipindah fisik —
   cukup referensinya), lalu hapus baris `DokumenPakln`.
2. Setiap `Pengajuan` T2P dengan `tgl_masuk_pakln` terisi:
   `tgl_masuk_bko = tgl_masuk_pakln`; `status_bko = "diunggah"` bila punya
   `DokumenBko` SK Tubel, selain itu `"menunggu"`.
3. T2P yang belum pernah diteruskan BPSDM: biarkan `status_bko` kosong.
4. Tidak membuat baris riwayat backfill.

### 3.4 Migrasi `notifications`

`notifications/migrations/0005_alter_notification_event.py` — choices `Event` baru (lihat [§7](#7-fase-5--notifikasi)).

---

## 4. Fase 2 — Logika Domain

### 4.1 `pengajuan/persyaratan.py`

```python
TAHAP_MODEL["bko"] = DokumenBko
TAHAP_RELATED["bko"] = "dokumen_bko"
TAHAP_LABEL["bko"] = "Admin BKO"

("T2P", "bpsdm"): [
    Syarat("izin_prinsip"),
    Syarat("ikatan_dinas_ttd", aksi="generate"),
    Syarat("nd_kabiro_pakln", tanggal_surat=True, aksi="format"),
],
("T2P", "bko"): [Syarat("sk_tubel", tanggal_surat=True)],
("T2P", "pakln"): _PAKLN_PDLN,        # sk_tubel dihapus
```

- `tahap_untuk_role`: tambah `"admin_bko": "bko"`.
- `direktori(pengajuan, sampai_tahap)`: urutan menjadi
  `["pegawai", "unor", "bpsdm", "bko", "pakln"]`; lewati `"bpsdm"` bila bukan
  Tipe 2 dan lewati `"bko"` bila bukan T2P. Hasil: Pratinjau PAKLN menampilkan
  dokumen BKO; Pratinjau BKO menampilkan Pegawai + Unor + BPSDM.
- `syarat_untuk` sudah generik — tidak perlu diubah.

### 4.2 Modul baru `pengajuan/bko.py`

Satu pintu transisi track BKO. Semua fungsi memanggil `alur.kunci(p)` di dalam
`transaction.atomic()`, memeriksa ulang kondisi, menulis `riwayat.catat` +
`logs.utils.catat_riwayat`, lalu memanggil notifikasi **setelah** commit.
Kegagalan validasi dilempar sebagai `BkoError(pesan)` (pola sama `PembatalanError`).

| Fungsi | Prasyarat | Efek |
|---|---|---|
| `buka_track(p, aktor)` | Dipanggil dari `views_bpsdm._teruskan`; `p.pakai_bko` dan `status_bko` kosong | `tgl_masuk_bko = today`, `status_bko = menunggu`, riwayat `diteruskan_bko`. Bila track sudah ada: tidak melakukan apa pun. |
| `setelah_unggah(p, aktor)` | Dipanggil setelah `tahap.proses_unggah(..., "bko", ...)` berhasil; `status_bko ∈ {menunggu, diunggah}` | `status_bko = diunggah`; riwayat `sk_tubel_diunggah` (setiap unggah/ganti); notifikasi PAKLN. |
| `setelah_hapus(p)` | Setelah `tahap.hapus(..., "bko", "sk_tubel")` | `status_bko = menunggu`. |
| `tutup(p, aktor, catatan)` | Role `admin_bko`; `status_bko = menunggu`; catatan wajib | `status_bko = ditutup`, `catatan_bko`, `tgl_bko_ditutup = today`; riwayat `ditutup_bko` + catatan; notifikasi semua pihak. |
| `buka_kembali(p, aktor, catatan)` | Role `admin_bko`/`admin_pakln`; `status_bko = ditutup`; catatan wajib | `status_bko = menunggu`, kosongkan `catatan_bko` & `tgl_bko_ditutup`; riwayat `dibuka_ulang_bko` + catatan; notifikasi. |
| `alasan_tidak_bisa_selesai(p)` | — | `""` bila boleh Selesai normal; pesan "Menunggu SK Tugas Belajar dari Admin BKO" bila `menunggu`; pesan "Pemrosesan ditutup Admin BKO: …" bila `ditutup`. Untuk non-T2P selalu `""`. |
| `bisa_diubah(p)` | — | `p.track_bko_terbuka` dan `p.status ∉ {selesai, dibatalkan}` dan tidak dibekukan. |

Prasyarat umum semua aksi: pengajuan belum `selesai`/`dibatalkan`, tidak
dibekukan (`alur.alasan_dibekukan`). Tidak ada syarat terhadap `p.status`
lainnya — BKO boleh bertindak saat pengajuan dikembalikan (keputusan #3).

### 4.3 `pengajuan/pembatalan.py` — Hentikan oleh PAKLN

Fungsi baru `hentikan_oleh_pakln(pengajuan, user, alasan)`:

1. Validasi: role `admin_pakln`, `p.pakai_bko`, `p.status_bko == ditutup`,
   `p.status ∉ {selesai, dibatalkan}`, tidak ada permohonan pembatalan terbuka,
   alasan wajib (default isian form = `catatan_bko`).
2. Dalam satu transaksi: buat `PermohonanPembatalan` dengan
   `diajukan_role = admin_pakln`, `status = disetujui`,
   `status_pengajuan_saat_diajukan = p.status`, `pakln_oleh/waktu/catatan` terisi;
   `p.status = dibatalkan`, `p.tgl_dibatalkan = today`.
3. Riwayat: `pembatalan_diajukan` (catatan = alasan) lalu `dibatalkan`.
4. Notifikasi `notify_pembatalan_disetujui(permohonan)` (penerima diperluas, lihat §7).
5. **Tidak** memeriksa `_belum_lewat_batas` (lihat [§12](#12-asumsi--risiko) A1).

`alasan_tidak_bisa` (jalur biasa Pegawai/Admin Unor) tidak berubah.

### 4.4 `pengajuan/riwayat.py`

```python
_LABEL_PERAN[User.Role.ADMIN_BKO] = "Admin BKO"
_ROLE_ADMIN |= {User.Role.ADMIN_BKO}

_TERBUKA_SEMUA |= {Aksi.DITUTUP_BKO, Aksi.DIBUKA_ULANG_BKO}
_HANYA_PAKLN = {Aksi.SELESAI_TANPA_SK_TUBEL}

def boleh_lihat_pesan(user, riwayat):
    if riwayat.aksi in _HANYA_PAKLN:
        return user.role == User.Role.ADMIN_PAKLN
    ...  # aturan lama
```

- `_TONE`: `ditutup_bko` → warning, `dibuka_ulang_bko` → info,
  `sk_tubel_diunggah` → success, `selesai_tanpa_sk_tubel` → success.
- `_IKON`: `diteruskan_bko` "→", `sk_tubel_diunggah` "↑", `ditutup_bko` "■",
  `dibuka_ulang_bko` "↻", `selesai_tanpa_sk_tubel` "✓".
- Docstring modul: tambah jalur BKO dan pengecualian visibilitas.

### 4.5 `pengajuan/alur.py`

- `timeline()`: untuk T2P dengan `track_bko_terbuka`, tambahkan key
  `sub` pada tahap `proses_pakln`:
  - `menunggu` → "SK Tugas Belajar (Admin BKO): Menunggu"
  - `diunggah` → "SK Tugas Belajar (Admin BKO): Diunggah dd Mmm yyyy" (dari `DokumenBko.uploaded_at`)
  - `ditutup` → "Pemrosesan ditutup Admin BKO (tgl): <catatan_bko>" (`sub_tone = warning`)
- Tahap `selesai` T2P yang riwayat terakhir penyelesaiannya
  `selesai_tanpa_sk_tubel` → tambahkan `sub` "Diselesaikan tanpa SK Tugas Belajar" (tanpa catatan).
- `_DESKRIPSI["T2P"]`:
  - `PROSES_BPSDM`: "Permohonan Izin Prinsip Menteri, penandatanganan Perjanjian Ikatan Dinas, penyampaian berkas ke Biro PAKLN dan Admin BKO."
  - `PROSES_PAKLN`: "Proses SP Setneg, Paspor Dinas, Exit Permit, Rekomendasi Visa (jika diperlukan); SK Tugas Belajar oleh Admin BKO."
- `STATUS_ROLE` tidak ditambah (BKO tidak terikat satu status).
- Template `partials/_timeline_proses.html`: render `sub` / `sub_tone` bila ada.

### 4.6 `pengajuan/report.py` & `views_report.py`

- `queryset_untuk`: `admin_bko` → `jenis_perjalanan = pdln`, `tipe_pdln = T2P`,
  `tgl_masuk_bko__isnull = False`.
- `ringkasan`: untuk BKO hitung kartu *Menunggu*, *Diunggah*, *Ditutup*
  (berdasar `status_bko`) — fungsi baru `ringkasan_bko(qs)` agar `ringkasan`
  lama tidak berubah.
- Export (kolom tambahan, semua role yang melihat T2P): "Tgl Masuk BKO",
  "Status BKO", "Tgl SK Tubel". **Tidak** menyertakan catatan Lanjutkan tanpa SK Tubel.
- `views_report`: izinkan role `admin_bko` untuk Export & Rekap (cakupan dari `queryset_untuk`).

### 4.7 `logs/utils.py`

Peta `_aktivitas_riwayat()`: `diteruskan_bko` → `TERUSKAN_PENGAJUAN`,
`selesai_tanpa_sk_tubel` → `SELESAI_PENGAJUAN`, sisanya default `PROSES_PENGAJUAN`.

---

## 5. Fase 3 — Halaman Admin BKO

### 5.1 URL — `pengajuan/urls_bko.py` (namespace `bko`, prefix `admin-bko/`)

| Path | View | Nama |
|---|---|---|
| `""` | `dashboard` | `bko:dashboard` |
| `dashboard/data/` | `dashboard_data` | `bko:dashboard_data` |
| `pembatalan/` | `daftar_pembatalan` (read-only) | `bko:pembatalan` |
| `export/`, `export/data/`, `rekap/` | `views_report.*` | `bko:export`, `bko:export_data`, `bko:rekap` |
| `<kode>/` | `proses` | `bko:proses` |
| `<kode>/hapus/<jenis>/` | `hapus_dokumen` | `bko:hapus_dokumen` |

Daftarkan di `paspor_project/urls.py`:
`path("admin-bko/", include(("pengajuan.urls_bko", "bko"), namespace="bko"))`.

### 5.2 `pengajuan/views_bko.py`

- `_scoped(request)` = `report.queryset_untuk(request.user)`.
- **`dashboard`** — kartu `ringkasan_bko`, tabel DataTables.
- **`dashboard_data`** — kolom: Pegawai (nama/NIP), Unor, Perguruan Tinggi,
  Tgl Berangkat, Tgl Masuk BKO, Status Pengajuan, Status BKO (badge), Aksi
  (`Proses →` bila `bko.bisa_diubah`, selain itu `Lihat`). Filter `?status_bko=`.
- **`proses`** (satu halaman — BKO tidak punya gerbang "Lanjutkan" seperti BPSDM):
  - Ringkasan pengajuan + data pegawai (`partials/_ringkasan_pengajuan.html`).
  - Direktori dokumen `persyaratan.direktori(p, "bko")`.
  - Panel SK Tubel: `partials/_dokumen_tahap.html` dengan `tahap.konteks_dokumen(p, "bko")`,
    `readonly = not bko.bisa_diubah(p) or status_bko == ditutup`.
  - Panel aksi:
    - `menunggu`: tombol **Tutup Pemrosesan** (modal, catatan wajib).
    - `ditutup`: banner alasan + tombol **Buka Kembali** (modal, catatan wajib).
  - Riwayat (`riwayat.konteks`), banner pembatalan/dibekukan.
  - POST: `tutup` → `bko.tutup`; `buka_kembali` → `bko.buka_kembali`;
    selain itu unggah → `tahap.proses_unggah(request, p, "bko", "bko:proses")`
    lalu `bko.setelah_unggah`. Semua ditolak bila `not bko.bisa_diubah(p)`.
- **`hapus_dokumen`** — `tahap.hapus(..., "bko", jenis)` + `bko.setelah_hapus`
  (hanya saat `status_bko = diunggah` dan `bisa_diubah`).
- **`daftar_pembatalan`** — salin pola `views_bpsdm.daftar_pembatalan` (read-only).

### 5.3 Template baru `templates/bko/`

| File | Isi |
|---|---|
| `dashboard.html` | Kartu ringkasan BKO + tabel + filter status BKO. |
| `proses.html` | Sesuai 5.2; modal Tutup/Buka Kembali memakai pola modal catatan yang ada di `bpsdm/preview.html`. |

Partial bersama baru `partials/_status_bko.html` — badge/banner status track
BKO (dipakai di halaman BKO, PAKLN, Unor, BPSDM, Pegawai). Banner `ditutup`
menampilkan `catatan_bko` + tanggal.

---

## 6. Fase 4 — Perubahan Alur Aktor Lain

### 6.1 Admin BPSDM — `views_bpsdm._teruskan`

Di dalam transaksi yang sama setelah `p.save()` dan riwayat penerusan:
`bko.buka_track(p, request.user)` bila `p.pakai_bko`. Notifikasi
`notify_forward_bko(p)` hanya bila track baru dibuka; bila penerusan ulang,
`notify_info_bko(p)` (info saja). Pesan sukses: "diteruskan ke Admin Biro PAKLN dan Admin BKO".

Template `bpsdm/upload.html` & `bpsdm/preview.html`: tampilkan `_status_bko.html`
bila track sudah terbuka (mis. saat dikembalikan PAKLN).

### 6.2 Admin Biro PAKLN — `views_pakln`

**`upload_dokumen`:**
- Context tambahan: `status_bko`, dokumen SK Tubel (`p.dokumen_bko`),
  `alasan_selesai_bko = bko.alasan_tidak_bisa_selesai(p)`.
- POST baru:
  - `buka_kembali_bko` → `bko.buka_kembali(p, user, catatan)`.
  - `selesaikan_tanpa_sk_tubel` → `_selesaikan(request, p, tanpa_sk_tubel=True)`.
  - `hentikan` → `pembatalan.hentikan_oleh_pakln(p, user, alasan)`.

**`_selesaikan(request, pengajuan, tanpa_sk_tubel=False)`:**
1. Cek dokumen PAKLN lengkap (seperti sekarang).
2. T2P:
   - `tanpa_sk_tubel=False` → tolak bila `bko.alasan_tidak_bisa_selesai(p)` tidak kosong.
   - `tanpa_sk_tubel=True` → wajib `status_bko == ditutup` dan catatan terisi.
3. Di dalam lock, periksa ulang `status_bko` (BKO bisa membuka kembali bersamaan).
4. Riwayat `selesai_tanpa_sk_tubel` + catatan **atau** `selesai` (tanpa catatan).
5. Notifikasi `notify_complete_pkln(p)` tanpa catatan.

**`preview`:** banner `_status_bko.html`. Kembalikan ke BPSDM tidak berubah
(track BKO tidak disentuh).

**`dashboard_data`:** untuk T2P tambahkan badge kecil status BKO di kolom status.

**Template `pakln/upload.html`:** panel "SK Tugas Belajar (Admin BKO)" berisi
status + pratinjau berkas; bila `ditutup`, tiga tombol (Buka Kembali /
Lanjutkan tanpa SK Tubel / Hentikan Pengajuan), masing-masing modal dengan
catatan wajib. Tombol Selesai normal disabled + tooltip bila `menunggu`.

### 6.3 Admin Unor — `views_unor`

`preview`/`upload_dokumen`: tampilkan `_status_bko.html` bila track terbuka
(terutama banner `ditutup`). Tidak ada aksi baru.

### 6.4 Pegawai — `views_pegawai`

- `_UNDUH_HASIL_PDLN`: hapus `DokumenPakln.Jenis.SK_TUBEL`; tambahkan sumber
  `DokumenBko` (`sk_tubel`). `monitor_progres` menggabungkan hasil PAKLN + BKO;
  `unduh_hasil` mencari `jenis` di PAKLN lalu BKO.
- `monitor_progres`: banner `ditutup` (alasan BKO). Catatan
  `selesai_tanpa_sk_tubel` tidak tampil (sudah tersaring `riwayat`).

---

## 7. Fase 5 — Notifikasi

### 7.1 `notifications/models.py` — Event baru

| Kode | Label |
|---|---|
| `NOTIF_07A_FORWARD_BKO` | Diteruskan ke Admin BKO |
| `NOTIF_07B_SK_TUBEL_DIUNGGAH` | SK Tugas Belajar diunggah |
| `NOTIF_07C_BKO_DITUTUP` | Pemrosesan ditutup Admin BKO |
| `NOTIF_07D_BKO_DIBUKA` | Pemrosesan BKO dibuka kembali |
| `NOTIF_07E_INFO_BKO` | Perbaikan diteruskan ulang (info BKO) |

### 7.2 `notifications/services.py`

Helper `_admin_bko_recipients()` (role `admin_bko`, aktif).

| Fungsi | Penerima | Isi |
|---|---|---|
| `notify_forward_bko(p)` | Admin BKO | Pengajuan T2P menunggu SK Tubel → `bko:proses` |
| `notify_info_bko(p)` | Admin BKO | Info penerusan ulang BPSDM → PAKLN (tanpa catatan antar-admin) |
| `notify_sk_tubel_diunggah(p)` | Admin PAKLN | SK Tubel tersedia → `pakln:upload_dokumen` |
| `notify_bko_ditutup(p, catatan)` | Pegawai, Admin Unor (unornya), Admin BPSDM, Admin PAKLN | **dengan** alasan (level warning) |
| `notify_bko_dibuka(p, catatan, aktor)` | Pegawai, Admin Unor, Admin BPSDM, + Admin BKO/PAKLN yang bukan aktor | dengan catatan |

Perluasan yang ada:
- `notify_pembatalan_diajukan/disetujui`: tambahkan Admin BKO bila `track_bko_terbuka`
  (pola sama dengan BPSDM, baris ~459).
- `notify_complete_pkln`: **tidak** memuat catatan `selesai_tanpa_sk_tubel`.

---

## 8. Fase 6 — Navigasi, Seed & Admin

| File | Perubahan |
|---|---|
| `templates/partials/_sidebar.html` | Blok `{% elif user.role == 'admin_bko' %}`: Dasbor, Pembatalan, Rekap, Export. |
| `pengajuan/breadcrumbs.py` | `User.Role.ADMIN_BKO: "bko:dashboard"`; entri `bko:dashboard`, `bko:proses` ("Proses {kode}"), `bko:pembatalan`, `bko:rekap`, `bko:export`. |
| `pengajuan/views_pegawai.py` | Tambah `"admin_bko"` pada `role_required` view bersama (baris 263 & 564 — hitung hari & profil). |
| `pengajuan/admin.py` | Register `DokumenBko`; inline di admin `Pengajuan`; tampilkan `status_bko`. |
| `pengajuan/tahap.py` | `FORM_TAHAP["bko"] = DokumenBkoForm`. Tidak perlu `_FLAG_TEMPLATE` (SK Tubel tidak memakai format template). |
| `pengajuan/forms.py` | `DokumenBkoForm` (salin `DokumenBpsdmForm`). |
| `accounts/management/commands/seed_demo_data.py` | User `admin.bko` / `paspor123`, role `admin_bko`; tambahkan ke daftar akun yang dicetak. |

---

## 9. Fase 7 — Test

File: `pengajuan/tests_pdln.py` (kelas baru `AlurT2PBkoTests`) + helper di `_Basis`
(`admin_bko`, `bko_unggah(p)`, `bko_tutup(p, catatan)`, `bko_buka(p, user, catatan)`).

**Penyesuaian test lama:**
- `AlurTipe2Tests.test_alur_t2p_...`: daftar aksi riwayat kini memuat
  `diteruskan_bko` setelah `diteruskan_pakln` pertama, dan sebelum `pakln_selesai`
  perlu `bko_unggah(p)` (+ `sk_tubel_diunggah` di daftar aksi).
- Fixture dokumen PAKLN T2P tidak lagi menyertakan `sk_tubel`.

**Test baru:**

| # | Skenario | Harapan |
|:-:|---|---|
| 1 | BPSDM teruskan T2P | `status_bko = menunggu`, `tgl_masuk_bko` terisi, riwayat `diteruskan_bko`, notifikasi ke BKO |
| 2 | BPSDM teruskan T2L | `status_bko` tetap kosong; Admin BKO 404 pada pengajuan T2L |
| 3 | PAKLN pratinjau & unggah dokumen saat BKO `menunggu` | Berhasil |
| 4 | PAKLN Selesai saat `menunggu` | Ditolak, status tetap `proses_pakln` |
| 5 | BKO unggah SK Tubel → PAKLN Selesai | `selesai`, riwayat `selesai` |
| 6 | BKO hapus SK Tubel | `status_bko = menunggu` |
| 7 | BKO tutup tanpa catatan | Ditolak |
| 8 | BKO tutup dengan catatan | `ditutup`; catatan terlihat Pegawai, Unor, BPSDM, PAKLN di `riwayat_untuk` |
| 9 | PAKLN Selesai normal saat `ditutup` | Ditolak |
| 10 | PAKLN Lanjutkan tanpa SK Tubel tanpa catatan | Ditolak |
| 11 | PAKLN Lanjutkan tanpa SK Tubel dengan catatan | `selesai`; riwayat `selesai_tanpa_sk_tubel`; catatan **hanya** terlihat PAKLN (kosong untuk Pegawai, Unor, BPSDM, BKO) |
| 12 | Buka kembali oleh BKO & oleh PAKLN | `menunggu`, `catatan_bko` kosong, riwayat `dibuka_ulang_bko` |
| 13 | Buka kembali oleh Unor/BPSDM/Pegawai | 403/ditolak |
| 14 | Buka kembali setelah `selesai`/`dibatalkan` | Ditolak |
| 15 | PAKLN Hentikan saat `ditutup` | `dibatalkan`, permohonan `diajukan_role = admin_pakln`, `status = disetujui` |
| 16 | PAKLN Hentikan saat `menunggu`/`diunggah` | Ditolak |
| 17 | PAKLN kembalikan ke BPSDM setelah SK Tubel diunggah | SK Tubel tetap ada, `status_bko = diunggah` |
| 18 | BKO unggah saat pengajuan di `proses_bpsdm` (dikembalikan) | Berhasil |
| 19 | Permohonan pembatalan terbuka | Semua aksi BKO & tiga aksi PAKLN ditolak (dibekukan) |
| 20 | Pegawai unduh hasil SK Tubel setelah selesai | Berkas dari `DokumenBko` |
| 21 | Migrasi data `0021` | `DokumenPakln sk_tubel` pindah ke `DokumenBko`, `status_bko` terisi benar |
| 22 | Timeline T2P | Sub-keterangan BKO sesuai status; tetap 5 tahap |

Jalankan: `python manage.py test pengajuan logs notifications accounts`.

---

## 10. Fase 8 — Dokumentasi

- `PDLN_TIPE_2_FLOW.MD`: ubah status v2 menjadi "sudah diimplementasikan"
  setelah merge; v1 tetap sebagai catatan historis.
- `BISNIS_PROSES_PDLN.MD`: §3 (aktor), §6.3–§6.4 (dokumen T2P), §7 (jalur catatan),
  §11 (notifikasi) — tambahkan rujukan ke `PDLN_TIPE_2_FLOW.MD §8`.
- `RIWAYAT_PEMROSESAN_PENGAJUAN.MD`: aksi baru & pengecualian visibilitas.
- `SKENARIO_NOTIFIKASI_SURAT.md`: event 7A–7E.

---

## 11. Urutan Pengerjaan & Checklist

Satu branch (mis. `alex/pdln-t2p-v2-bko`), commit per fase agar mudah ditinjau.

- [x] **F1** Role `admin_bko` + migrasi accounts
- [x] **F1** Model `Pengajuan` (field BKO), `DokumenBko`, aksi riwayat, label BPSDM + migrasi `0020`
- [x] **F1** Data migration `0021` + hapus choice `sk_tubel` PAKLN (`0022`)
- [x] **F2** `persyaratan` (tahap `bko`), `forms.DokumenBkoForm`, `tahap.FORM_TAHAP`
- [x] **F2** `pengajuan/bko.py`
- [x] **F2** `pembatalan.hentikan_oleh_pakln`
- [x] **F2** `riwayat` (label, visibilitas), `alur` (timeline sub), `report`, `logs/utils`
- [x] **F3** `urls_bko`, `views_bko`, template `bko/*`, `partials/_status_bko.html`
- [x] **F4** `views_bpsdm._teruskan`
- [x] **F4** `views_pakln` (upload, `_selesaikan`, tiga aksi, dashboard badge) + template
- [x] **F4** `views_unor`, `views_pegawai` (banner, unduh hasil)
- [x] **F5** Event notifikasi + migrasi + fungsi `services`
- [x] **F6** Sidebar, breadcrumbs, login redirect, admin, seed
- [x] **F7** Sesuaikan test lama + test baru (`AlurT2PBkoTests`); semua hijau kecuali `test_kode_dan_detail_pdln` yang sudah gagal sebelumnya (format kode `PLN…`)
- [ ] **F7** Uji manual end-to-end dengan akun seed (pegawai → unor → bpsdm → bko ‖ pakln → selesai / tutup → buka / lanjutkan / hentikan)
- [x] **F8** Update wiki

---

## 12. Asumsi & Risiko

| # | Asumsi / risiko | Penanganan |
|:-:|---|---|
| A1 | **Hentikan** oleh PAKLN tidak dibatasi tanggal keberangkatan (berbeda dari pembatalan biasa yang ditolak setelah tanggal berangkat lewat). | Asumsi: penghentian administratif boleh kapan pun sebelum selesai. Konfirmasi ke pemilik proses bila perlu dibatasi. |
| A2 | Unggah ulang (ganti) SK Tubel mencatat riwayat `sk_tubel_diunggah` lagi & notifikasi PAKLN lagi. | Wajar sebagai jejak; bila terlalu ramai, batasi notifikasi hanya unggahan pertama. |
| A3 | Track BKO yang dibuka kembali tidak mengubah `tgl_masuk_bko`. | Tanggal masuk tetap tanggal pertama; tanggal buka kembali dibaca dari riwayat. |
| A4 | Admin BKO tidak memakai Manajemen Template (SK Tubel diterbitkan di luar sistem). | Tidak menambah flag `untuk_admin_bko` di `DokumenTemplate`. |
| R1 | **Race condition** BKO buka kembali / unggah bersamaan dengan PAKLN Selesai. | Semua transisi memakai `alur.kunci` dan memeriksa ulang `status_bko` di dalam lock. |
| R2 | Test lama T2P gagal karena urutan riwayat & syarat Selesai berubah. | Disesuaikan di F7 (sudah dipetakan). |
| R3 | Data migration memindahkan referensi berkas, bukan berkas fisik — path lama `pengajuan/<kode>/pakln/sk_tubel/…` tetap dipakai oleh `DokumenBko`. | Aman untuk storage S3/lokal; berkas baru otomatis ke `…/bko/sk_tubel/…`. |
| R4 | Pengecualian visibilitas (`_TERBUKA_SEMUA`, `_HANYA_PAKLN`) bocor lewat jalur lain (notifikasi, export, template). | Catatan `selesai_tanpa_sk_tubel` tidak dikirim ke notifikasi/export; test #11 memverifikasi `riwayat_untuk`. |

---

## 13. Catatan Implementasi

Hal yang berbeda atau lebih rinci dibanding rencana di atas:

| # | Catatan |
|:-:|---|
| 1 | **A1 tidak relevan.** `pembatalan._belum_lewat_batas` hanya membatasi pengajuan yang sudah `selesai`; Hentikan hanya tersedia sebelum selesai, jadi tidak ada batas tanggal yang terlewati. |
| 2 | Notifikasi `BKO_DITUTUP` / `BKO_DIBUKA` dikirim ke banyak role, sehingga `redirect_url` dikosongkan — klik notifikasi membawa penerima ke halaman awal role-nya (`home`). |
| 3 | Badge status BKO ditambahkan di `views_unor.status_html` (dipakai dasbor Unor, BPSDM, PAKLN) selama pengajuan masih berjalan; dasbor BKO memakai kolom sendiri (`dengan_bko=False`). |
| 4 | Label riwayat `dibuka_ulang_bko` menyebut pembukanya ("… oleh Admin BKO" / "… oleh Biro PAKLN"). |
| 5 | Notifikasi pembatalan yang **diajukan** tidak dikirim ke Admin BKO (hanya yang **disetujui**), sama seperti perlakuan Admin BPSDM. |
| 6 | Test migrasi data (#21) memanggil `maju()` dari `0021_v2_bko_data` langsung dengan app registry aktif. |
| 7 | Test dijalankan di SQLite + `FileSystemStorage` (settings sementara di luar repo) karena MySQL & S3 pada `.env` tidak terjangkau dari mesin pengembang. Jalankan ulang di MySQL sebelum deploy. |
