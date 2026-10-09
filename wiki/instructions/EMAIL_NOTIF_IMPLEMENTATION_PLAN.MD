# Rencana Implementasi Email Notification System

Rencana mengirim **email notifikasi** secara paralel dengan notifikasi in-app yang sudah
ada, memakai **antrean berbasis database** (model `EmailLog`) dan worker berupa Django
management command. Dirancang agar kelak bisa dipindah ke Celery tanpa mengubah model
(lihat `CELERY_IMPLEMENTATION_PLAN.MD`).

> **Status:** sudah diimplementasi (lihat "Catatan implementasi" di akhir dokumen). Bagian
> bertanda **[Putusan]** masih perlu keputusan mentor, dan **[Verifikasi]** perlu dicek
> dengan akses Office 365 yang sebenarnya.

## Daftar isi

1. [Objective dan validasi data](#1-objective-dan-validasi-data)
2. [Konfigurasi lingkungan](#2-konfigurasi-lingkungan)
3. [Database queue: model `EmailLog`](#3-database-queue-model-emaillog)
4. [Worker: management command](#4-worker-management-command)
5. [Skema trigger (sinkron dengan in-app)](#5-skema-trigger-sinkron-dengan-in-app)
6. [Desain dan template email](#6-desain-dan-template-email)
7. [Frontend monitoring (Admin PAKLN)](#7-frontend-monitoring-admin-pakln)
8. [Langkah Git](#8-langkah-git)
9. [Pengujian](#9-pengujian)
10. [Tahapan pengerjaan](#10-tahapan-pengerjaan)
11. [Risiko dan keamanan](#11-risiko-dan-keamanan)
12. [Keputusan yang perlu dikonfirmasi](#12-keputusan-yang-perlu-dikonfirmasi)

---

## 1. Objective dan validasi data

### 1.1 Objective

Mengirim email ke pihak yang relevan setiap kali ada kejadian penting pada pengajuan
(kirim, kembalikan, teruskan, selesai, pembatalan), tanpa membuat pengguna menunggu SMTP.
Prinsip utama:

- **Web tidak pernah berbicara dengan SMTP.** Web hanya menulis satu baris `EmailLog`
  (cepat, satu transaksi dengan data bisnis). Pengiriman SMTP dilakukan worker terpisah.
- **Email adalah pelengkap, bukan pengganti** notifikasi in-app. Kegagalan email tidak
  boleh menggagalkan alur pengajuan.
- **Jejak lengkap:** semua email (terkirim, gagal, dilewati) tercatat dan terlihat di
  halaman monitoring.

### 1.2 Temuan kondisi data (pemeriksaan 8 Oktober 2026)

| Temuan | Dampak |
|---|---|
| Dari 47 akun (34 Pegawai, 12 Admin Unor, 1 Admin PAKLN), **semuanya `email` kosong** | Saat ini tidak ada satu pun penerima yang bisa dikirimi email |
| Model `User` sudah punya field `email` (bawaan Django), tetapi `PegawaiProfile` tidak | Sumber email = `User.email` |
| Form **Tambah User** dan **Edit User** (Manajemen User) **tidak memiliki** field email | Admin PAKLN belum punya jalan mengisi email lewat UI |
| Tidak ada setting `EMAIL_*` maupun URL situs di `settings.py` | Perlu ditambah, termasuk `SITE_BASE_URL` untuk tautan di email |

### 1.3 Strategi penanganan akun tanpa email

Rekomendasi (**[Putusan]**, lihat bagian 12): **opsional, dilewati dengan jejak**, bukan wajib.

1. **Field email dibuat tersedia, tidak wajib.** Tambahkan field `email` pada form Tambah
   User dan Edit User, dengan validasi format. Kolom "Email" ditambahkan di tabel
   Manajemen User, dengan penanda "Belum diisi" untuk yang kosong.
2. **Mewajibkan sekarang berisiko:** 47 akun yang ada tidak punya email, sehingga
   mewajibkan field di form Edit User akan memaksa semua diisi lebih dulu, dan alur seed
   data (`seed_demo_data`, seed pegawai/admin unor) ikut berubah.
3. **Penerima tanpa email dilewati, bukan hilang diam-diam.** Saat antre, bila
   `User.email` kosong, sistem tetap membuat baris `EmailLog` berstatus **`skipped`**
   dengan alasan "Penerima belum memiliki email". Dengan begitu admin melihat di halaman
   monitoring siapa yang tidak menerima email dan mengapa.
4. **Notifikasi in-app tetap terkirim** apa pun status email.
5. **Pengisian data awal:** sediakan cara mengisi email massal untuk 47 akun (mis. kolom
   email pada berkas seed, atau impor sederhana). Keputusannya mengikuti sumber data email
   pegawai yang resmi.
6. **Validasi tambahan:** format email valid, huruf kecil, batasi spasi. Domain tidak
   dipaksa `@pu.go.id` karena belum ada aturan itu.
7. Setelah mayoritas akun terisi, bisa dipertimbangkan menjadikan email **wajib hanya
   pada akun baru**.

---

## 2. Konfigurasi lingkungan

### 2.1 Pemetaan variabel `.env` ke `settings.py`

| Variabel `.env` | Setting Django / pemakaian | Keterangan |
|---|---|---|
| `MAIL_ALLOW_SEND` | `MAIL_ALLOW_SEND` (bool kustom) | **Saklar pengaman.** Bawaan `False` bila variabel tidak ada |
| `MAIL_DRIVER` | `EMAIL_BACKEND` | `smtp` → `django.core.mail.backends.smtp.EmailBackend`. Untuk dev: `console` → backend konsol |
| `MAIL_HOST` | `EMAIL_HOST` | `smtp.office365.com` |
| `MAIL_PORT` | `EMAIL_PORT` | `587` |
| `MAIL_USERNAME` | `EMAIL_HOST_USER` | |
| `MAIL_PASSWORD` | `EMAIL_HOST_PASSWORD` | **Rahasia**, hanya di `.env` |
| `MAIL_ENCRYPTION` | `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | `tls` → `EMAIL_USE_TLS=True` (STARTTLS, port 587). `ssl` → `EMAIL_USE_SSL=True` (port 465) |
| `MAIL_TIMEOUT_MS` | `EMAIL_TIMEOUT` | Django memakai **detik**: `MAIL_TIMEOUT_MS / 1000` |
| `MAIL_FROM_EMAIL`, `MAIL_FROM_NAME` | `DEFAULT_FROM_EMAIL` | Format `"Nama" <alamat>` |
| `MAIL_SITE_NAME` | Variabel konteks template | Nama situs di header dan footer email |
| `MAIL_RETRY_ATTEMPTS`, `MAIL_RETRY_DELAY_MS` | Percobaan ulang **koneksi dalam satu kali kirim** | Berbeda dari retry antrean di bawah. Boleh dibiarkan 1 percobaan |
| `MAIL_DB_QUEUE_ENABLE_WORKER` | Pengaman worker | Bila `false`, command worker menolak berjalan dalam mode loop (kecuali `--once`) |
| `MAIL_DB_QUEUE_WORKER_INTERVAL_MS` | Jeda antar putaran worker | Contoh 15000 (15 detik) |
| `MAIL_DB_QUEUE_WORKER_BATCH_SIZE` | Jumlah email diambil per putaran | Contoh 20 |
| `MAIL_DB_QUEUE_MAX_ATTEMPTS` | Batas percobaan sebelum `failed` | Contoh 5 |
| `MAIL_DB_QUEUE_RETRY_DELAY_MS` | Jeda dasar sebelum mencoba lagi | Contoh 30000 (30 detik) |
| `MAIL_DB_QUEUE_LOCK_TTL_MS` | Umur kunci baris `sending` | Contoh 60000. Lewat itu, baris dianggap macet dan boleh diambil ulang |

**Variabel baru yang perlu ditambah** (belum ada di `.env.example`):

| Variabel | Fungsi |
|---|---|
| `SITE_BASE_URL` | Alamat dasar untuk tautan absolut di email, mis. `http://10.101.21.55:8000`. Tanpa ini tautan "Buka di PASPOR" tidak bisa dibuat |
| `MAIL_DEV_REDIRECT_TO` (opsional) | Bila diisi, **semua** email dialihkan ke alamat ini (alamat asli dicatat di subjek). Mencegah email nyata terkirim saat pengujian |

### 2.2 Cuplikan `settings.py` (ilustrasi)

```python
def _bool(key, default="False"):
    return env(key, default).lower() in ("1", "true", "yes")

# Saklar pengaman: bila False, email tetap dicatat di EmailLog tetapi TIDAK dikirim via SMTP.
MAIL_ALLOW_SEND = _bool("MAIL_ALLOW_SEND", "False")

_MAIL_DRIVER = env("MAIL_DRIVER", "smtp")
EMAIL_BACKEND = {
    "smtp": "django.core.mail.backends.smtp.EmailBackend",
    "console": "django.core.mail.backends.console.EmailBackend",
}.get(_MAIL_DRIVER, "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("MAIL_HOST", "localhost")
EMAIL_PORT = int(env("MAIL_PORT", "587"))
EMAIL_HOST_USER = env("MAIL_USERNAME", "")
EMAIL_HOST_PASSWORD = env("MAIL_PASSWORD", "")
EMAIL_USE_TLS = env("MAIL_ENCRYPTION", "tls").lower() == "tls"
EMAIL_USE_SSL = env("MAIL_ENCRYPTION", "tls").lower() == "ssl"
EMAIL_TIMEOUT = int(env("MAIL_TIMEOUT_MS", "15000")) / 1000
DEFAULT_FROM_EMAIL = f'"{env("MAIL_FROM_NAME", "PASPOR")}" <{env("MAIL_FROM_EMAIL", "noreply@example.com")}>'
MAIL_SITE_NAME = env("MAIL_SITE_NAME", "PASPOR PU")
SITE_BASE_URL = env("SITE_BASE_URL", "http://127.0.0.1:8000")

# Antrean database
MAIL_QUEUE = {
    "ENABLE_WORKER": _bool("MAIL_DB_QUEUE_ENABLE_WORKER"),
    "INTERVAL": int(env("MAIL_DB_QUEUE_WORKER_INTERVAL_MS", "15000")) / 1000,
    "BATCH_SIZE": int(env("MAIL_DB_QUEUE_WORKER_BATCH_SIZE", "20")),
    "MAX_ATTEMPTS": int(env("MAIL_DB_QUEUE_MAX_ATTEMPTS", "5")),
    "RETRY_DELAY": int(env("MAIL_DB_QUEUE_RETRY_DELAY_MS", "30000")) / 1000,
    "LOCK_TTL": int(env("MAIL_DB_QUEUE_LOCK_TTL_MS", "60000")) / 1000,
}
```

### 2.3 Saklar `MAIL_ALLOW_SEND` (perilaku)

| `MAIL_ALLOW_SEND` | Saat email diantre | Saat worker memproses |
|---|---|---|
| `true` | Baris `pending` | Dikirim lewat SMTP |
| `false` | Baris langsung `skipped`, alasan "Pengiriman dimatikan (MAIL_ALLOW_SEND=false)" | Tidak diproses |

Nilai bawaan `false` jika variabel hilang, supaya lingkungan baru (laptop, staging)
tidak mengirim email nyata secara tidak sengaja. Sebaiknya `MAIL_ALLOW_SEND=true`
hanya di `.env` produksi.

### 2.4 Catatan Office 365 **[Verifikasi]**

- Pengiriman SMTP ke `smtp.office365.com:587` memakai STARTTLS dan perlu **SMTP AUTH
  diaktifkan** untuk kotak surat pengirim. Banyak tenant Microsoft 365 menonaktifkannya
  secara bawaan atau membatasi autentikasi dasar (*basic auth*). Konfirmasi ke pengelola
  email PU sebelum implementasi.
- Alamat **From** umumnya harus sama dengan kotak surat yang login (atau alias yang
  diizinkan), jadi `MAIL_FROM_EMAIL` sebaiknya sama dengan `MAIL_USERNAME`.
- Microsoft membatasi kecepatan kirim per kotak surat (sekitar 30 pesan per menit untuk
  pengiriman SMTP klien, dan batas harian). Konfigurasi `BATCH_SIZE=20` tiap 15 detik
  berpotensi 80 email per menit, **melebihi** batas itu. Worker perlu **pacing** (jeda
  antar email) atau `BATCH_SIZE` lebih kecil. Cek batas aktual tenant PU.

---

## 3. Database queue: model `EmailLog`

Satu tabel untuk dua fungsi: **antrean** (baris yang menunggu dikirim) dan **riwayat**
(semua email yang pernah dibuat). Lokasi usulan: app `notifications`
(`notifications/models.py`), tabel `notifications_emaillog`.

### 3.1 Kolom

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | BigAutoField | PK |
| `recipient` | FK ke `User`, `null=True`, `on_delete=SET_NULL` | Penerima. Tetap terbaca bila akun dihapus |
| `to_email` | EmailField | Snapshot alamat saat diantre. Kosong bila penerima tak punya email |
| `to_name` | CharField(150) | Snapshot nama |
| `pengajuan` | FK ke `Pengajuan`, `null=True`, `on_delete=SET_NULL` | Pengajuan terkait |
| `event` | CharField(40) | Kode event (`Notification.Event`), mis. `NOTIF_01_SUBMIT_UNOR` |
| `subject` | CharField(255) | Subjek email |
| `body_text` | TextField | Versi teks polos |
| `body_html` | TextField | Versi HTML |
| `status` | CharField(10), `choices` | `pending`, `sending`, `sent`, `failed`, `skipped` |
| `attempts` | PositiveSmallIntegerField, default 0 | **Jumlah percobaan** yang sudah dilakukan |
| `max_attempts` | PositiveSmallIntegerField | Snapshot `MAIL_DB_QUEUE_MAX_ATTEMPTS` saat dibuat |
| `next_attempt_at` | DateTimeField | **Waktu percobaan berikutnya**. Baris baru: waktu sekarang. Setelah gagal: sekarang + jeda |
| `locked_at` | DateTimeField, `null=True` | **Penguncian:** kapan baris diambil worker |
| `locked_by` | CharField(100), `blank=True` | Identitas worker (hostname dan PID), untuk penelusuran |
| `last_error` | TextField, `blank=True` | Pesan error percobaan terakhir (dipotong 1000 karakter) |
| `status_note` | CharField(255), `blank=True` | Alasan `skipped` (tanpa email, pengiriman dimatikan) |
| `created_at` | DateTimeField, `auto_now_add` | |
| `sent_at` | DateTimeField, `null=True` | Waktu berhasil dikirim |
| `updated_at` | DateTimeField, `auto_now` | |

### 3.2 Status dan perpindahan

```
                 ┌──────────── (MAIL_ALLOW_SEND=false / tanpa email) ───▶ skipped
 dibuat ─▶ pending ──(worker mengambil)──▶ sending ──(SMTP ok)──▶ sent
              ▲                              │
              │        (gagal, attempts < max_attempts)
              └──── next_attempt_at = sekarang + jeda ◀────┤
                                             │ (gagal, attempts >= max_attempts)
                                             ▼
                                           failed ──(tombol "Kirim Ulang")──▶ pending
```

| Status | Arti |
|---|---|
| `pending` | Menunggu giliran, atau menunggu percobaan ulang (`next_attempt_at` di masa depan) |
| `sending` | Sedang diproses worker (`locked_at` terisi) |
| `sent` | Berhasil dikirim |
| `failed` | Gagal **permanen** setelah `max_attempts`. Hanya bisa dikirim ulang manual |
| `skipped` | Sengaja tidak dikirim: penerima tanpa email atau `MAIL_ALLOW_SEND=false`. Status ini **tambahan** di luar empat status yang diminta, agar kasus "dilewati" tidak bercampur dengan "gagal" |

Kegagalan sementara (SMTP timeout, dll.) mengembalikan baris ke `pending` dengan
`last_error` terisi. Status `failed` hanya muncul setelah percobaan habis.

### 3.3 Index

- `(status, next_attempt_at)`: query utama worker.
- `(created_at)`: urutan bawaan dan filter tanggal.
- `(recipient)`: penelusuran per pengguna.

### 3.4 Aturan model

- Baris tidak diedit dari UI selain lewat aksi **Kirim Ulang**.
- `Meta.ordering = ["-created_at"]`.
- Migrasi hanya menambah tabel baru.
- Isi email (`body_*`) tidak boleh memuat kata sandi atau token.

---

## 4. Worker: management command

Command kustom `kirim_email_antrean` (`notifications/management/commands/kirim_email_antrean.py`).
Logika inti ditaruh di fungsi biasa (`notifications/email_queue.py`) yang dipanggil command,
sehingga kelak **Celery tinggal memanggil fungsi yang sama**, dan modelnya tidak berubah.

### 4.1 Opsi

| Opsi | Fungsi |
|---|---|
| (tanpa opsi) | Mode loop: ulangi putaran tiap `INTERVAL`. Menolak berjalan bila `MAIL_DB_QUEUE_ENABLE_WORKER=false` |
| `--once` | Satu putaran lalu keluar. Cocok untuk cron, tes, dan debugging. Diizinkan walau `ENABLE_WORKER=false` |
| `--batch-size N` | Menimpa `BATCH_SIZE` |
| `--interval DETIK` | Menimpa `INTERVAL` |

### 4.2 Satu putaran

1. **Ambil dan kunci** (dalam satu transaksi pendek):
   - Pilih baris dengan `status = pending` dan `next_attempt_at <= sekarang`,
     **atau** `status = sending` dengan `locked_at < sekarang - LOCK_TTL` (baris macet
     akibat worker mati).
   - Urutkan `next_attempt_at, id`, batasi `BATCH_SIZE`.
   - Gunakan `SELECT ... FOR UPDATE SKIP LOCKED` (`select_for_update(skip_locked=True)`).
     MySQL server project ini versi 8.4, sehingga didukung. Dengan ini dua worker tidak
     pernah mengambil baris yang sama.
   - Ubah ke `status = sending`, `locked_at = sekarang`, `locked_by = <id worker>`,
     `attempts = attempts + 1`, lalu commit.
2. **Kirim di luar transaksi** (SMTP lambat tidak boleh menahan kunci database):
   rakit `EmailMultiAlternatives` (teks + HTML) dari baris, kirim lewat backend Django.
   Beri jeda pacing antar email (bagian 2.4).
3. **Tulis hasil:**
   - Berhasil: `status = sent`, `sent_at = sekarang`, `locked_at = NULL`, `last_error` dikosongkan.
   - Gagal dan `attempts < max_attempts`: `status = pending`,
     `next_attempt_at = sekarang + RETRY_DELAY`, `last_error` diisi, kunci dilepas.
     Opsional: *exponential backoff* (`RETRY_DELAY × 2^(attempts-1)`).
   - Gagal dan `attempts >= max_attempts`: `status = failed`, kunci dilepas.
4. **Tidur** `INTERVAL` bila tidak ada baris, lalu ulangi.

### 4.3 Hal-hal penting

- **Penghentian rapi:** tangani `SIGTERM`/`SIGINT` (Docker memakai `SIGTERM` saat stop):
  selesaikan email yang sedang dikirim, lalu berhenti. Baris yang sempat `sending`
  otomatis diambil ulang lewat aturan `LOCK_TTL`.
- **Idempotensi:** bila worker mati tepat setelah SMTP menerima email tetapi sebelum
  `sent` ditulis, email bisa terkirim dua kali setelah kunci kedaluwarsa. Risiko ini
  melekat pada setiap antrean ("minimal satu kali") dan dapat diterima untuk notifikasi.
  Dokumentasikan.
- **Log teknis:** tulis ke logger `notifications.email` (konfigurasi `LOGGING` yang sudah
  ada). Jangan mencatat isi email atau kata sandi.
- **Pembersihan:** tambahkan command `bersihkan_email_log --hari N` (hapus `sent` dan
  `skipped` yang lebih tua dari N hari). Alamat email adalah data pribadi, jadi retensi
  perlu ditetapkan.

### 4.4 Menjalankan worker

| Lingkungan | Cara |
|---|---|
| Lokal | `python manage.py kirim_email_antrean` di terminal terpisah, atau `--once` untuk satu putaran |
| Docker | Service tersendiri `mail-worker` dari image yang sama: `command: ["python", "manage.py", "kirim_email_antrean"]`, dengan `DJANGO_MIGRATE_ON_START=False` dan `DJANGO_INIT_ON_START=False` (hanya service `web` yang boleh migrasi) |
| Alternatif | Cron/Task Scheduler memanggil `kirim_email_antrean --once` tiap menit |

Setelah migrasi ke Celery: `kirim_email_antrean` digantikan task Celery yang memanggil
fungsi `proses_antrean()` yang sama, dijadwalkan oleh Beat atau dipicu langsung.

---

## 5. Skema trigger (sinkron dengan in-app)

### 5.1 Titik pemasangan

Seluruh notifikasi in-app dibuat lewat satu fungsi pusat: `_create(recipients, ...)` di
`notifications/services.py`. **Email dipicu dari titik yang sama**, sehingga notifikasi
in-app dan email selalu sinkron dan tidak perlu mengubah belasan fungsi `notify_*`.

```python
def _create(recipients, *, pengajuan, event, level, title, body, redirect_url):
    notifs = [Notification(...) for user in recipients]
    if notifs:
        Notification.objects.bulk_create(notifs)
        email_queue.enqueue(notifs)   # BARU: antre email untuk event yang masuk daftar
```

Aturan pemasangan:
- **Aman:** `email_queue.enqueue` dibungkus `try/except` + log. Gagal mengantre email
  **tidak boleh** menggagalkan pembuatan notifikasi in-app atau alur pengajuan.
- **Daftar putih event:** hanya event yang terdaftar di tabel 5.2 yang diemailkan.
  Event baru tidak otomatis mengirim email.
- **Satu transaksi:** baris `EmailLog` dibuat dalam transaksi yang sama dengan data
  bisnis bila `_create` dipanggil di dalamnya. Bila transaksi dibatalkan, email ikut
  batal. Worker hanya melihat baris yang sudah di-*commit*.
- **MySQL tidak mengembalikan PK** pada `bulk_create`, sehingga `EmailLog` tidak memakai
  FK ke `Notification`. Keterkaitan lewat `recipient`, `pengajuan`, dan `event`.
- Penerima tanpa email atau `MAIL_ALLOW_SEND=false` menghasilkan baris `skipped`
  (bagian 1.3 dan 2.3).

### 5.2 Matriks trigger

Cakupan sesuai arahan: tiga arah. Event diambil dari `Notification.Event` yang sudah ada.

| Arah | Kejadian | Event | Fungsi sumber |
|---|---|---|---|
| **Sistem → Admin Unor** | Pegawai mengajukan | `NOTIF_01_SUBMIT_UNOR` | `notify_submit_unor` |
| | Pegawai memperbaiki dan mengirim ulang | `NOTIF_02C_RESUBMIT_UNOR` | `notify_resubmit_unor` |
| **Sistem → Pegawai** | Ajuan disetujui Unor dan diproses lebih lanjut (diteruskan) | `NOTIF_02A_APPROVE_UNOR` (salinan pegawai) | `notify_approve_unor` |
| | Ajuan dikembalikan Admin Unor | `NOTIF_02B_REJECT_UNOR` | `notify_reject_unor` |
| | Ajuan dikembalikan PAKLN (status penanganan) | `NOTIF_03B_REJECT_PKLN_TO_UNOR` (salinan pegawai) | `notify_reject_pakln_to_unor` |
| | Pembatalan disetujui | `NOTIF_06D_PEMBATALAN_DISETUJUI` | `notify_pembatalan_disetujui` |
| | Pembatalan ditolak | `NOTIF_06C_PEMBATALAN_DITOLAK` | `notify_pembatalan_ditolak` |
| | Ajuan selesai | `NOTIF_03A_COMPLETE_PKLN` (salinan pegawai) | `notify_complete_pkln` |
| **Sistem → Admin PAKLN ("Admin KLN")** | Ajuan diteruskan ke PAKLN | `NOTIF_02A_APPROVE_UNOR` (salinan admin PAKLN) | `notify_approve_unor` |
| | Perbaikan berkas diteruskan ulang | `NOTIF_02A_APPROVE_UNOR` (dengan catatan) | `notify_approve_unor(catatan=...)` |

Pembeda salinan: satu event dapat menghasilkan notifikasi untuk beberapa peran (pegawai,
admin). Template dipilih berdasarkan **event + peran penerima** (`recipient.role`).

**Fase 2 (opsional, di luar cakupan awal):** event pembatalan ke Admin Unor/PAKLN,
laporan PDLN, alur BPSDM, dan pengingat terjadwal.

### 5.3 Isi dinamis

Konten email memakai data yang sama dengan notifikasi in-app: `title`, `body`, dan
`redirect_url` (diubah menjadi URL absolut dengan `SITE_BASE_URL`). Wording sama dengan
in-app agar konsisten.

---

## 6. Desain dan template email

### 6.1 Prinsip

- Bahasa Indonesia, nada resmi, selaras dengan penamaan "PASPOR PU" (Platform
  Administrasi Surat Perjalanan Overseas Request, Kementerian PU).
- **Modular:** satu kerangka dasar, bagian-bagian kecil dipakai ulang, dan template per
  event hanya menimpa bagian yang berbeda.
- Selalu menyertakan **versi teks polos** (untuk klien email yang menolak HTML).
- Konten pengguna (catatan revisi, nama) di-*escape* otomatis oleh template Django.

### 6.2 Struktur berkas

```
templates/email/
  base_email.html          kerangka: header PASPOR PU, slot isi, footer
  base_email.txt           kerangka versi teks
  partials/
    _tombol.html           tombol ajakan bertindak ("Buka di PASPOR")
    _ringkasan.html        blok ringkas: kode pengajuan, pegawai, perihal, status
    _catatan.html          kotak catatan revisi (bila ada)
  event/
    default.html / .txt    template umum: judul + isi + tombol
    submit_unor.html       dst., hanya bila butuh wording khusus
```

### 6.3 Kerangka email

| Bagian | Isi |
|---|---|
| **Subjek** | `[PASPOR] {title}`, mis. `[PASPOR] Pengajuan Baru - PLN01-071026-001` |
| **Header** | Nama "PASPOR PU" dan subjudul platform. Logo sebaiknya disematkan sebagai lampiran inline (CID) karena banyak klien memblokir gambar eksternal |
| **Salam** | `Yth. {nama penerima},` |
| **Isi** | Kalimat utama dari `body`, lalu blok ringkasan (kode pengajuan, nama pegawai, perihal, status) |
| **Catatan** | Kotak catatan revisi bila event berupa pengembalian |
| **Tombol** | **Buka di PASPOR** menuju `redirect_url` (pengguna tetap harus login) |
| **Footer** | "Email ini dikirim otomatis oleh sistem PASPOR PU. Mohon tidak membalas email ini." plus nama unit penyelenggara |

### 6.4 Aturan teknis

- Tata letak berbasis **tabel** dengan CSS **inline** (kompatibilitas Outlook, yang
  juga penerima utama karena domain Office 365).
- Lebar sekitar 600 px, responsif untuk layar kecil.
- Tidak ada JavaScript, tidak ada gambar latar kritis.
- Tidak melampirkan dokumen (PDF/Nota Dinas). Pengguna mengunduh lewat sistem.
- Pratinjau: halaman kecil khusus admin (opsional) atau command `kirim_email_antrean
  --once` pada `MAIL_DRIVER=console` untuk melihat hasil render.

---

## 7. Frontend monitoring (Admin PAKLN)

Halaman kustom di bawah `/admin-biropakln/`, **bukan** Django Admin standar. Mengikuti
pola menu **Log Sistem** yang sudah ada (`logs/views.py`, `templates/pakln/log_sistem.html`):
Django template + Bulma + jQuery + DataTables 2.x server-side.

### 7.1 Rute

Dilindungi `@role_required("admin_pakln")`. Rute statis ditaruh **sebelum** pola
`<str:kode>/...` di `pengajuan/urls_pakln.py`.

| Rute | Nama | Method | Fungsi |
|---|---|---|---|
| `monitor-email/` | `pakln:monitor_email` | GET | Halaman monitoring |
| `monitor-email/data/` | `pakln:monitor_email_data` | GET | Endpoint JSON DataTables |
| `monitor-email/<int:pk>/kirim-ulang/` | `pakln:monitor_email_kirim_ulang` | POST | Kirim ulang satu email gagal |

Menu **Monitor Email** ditambahkan di `templates/partials/_sidebar.html` untuk
`admin_pakln`, di dekat **Log Sistem**.

### 7.2 Tampilan

- **Ringkasan di atas tabel:** kartu jumlah per status (`pending`, `sending`, `sent`,
  `failed`, `skipped`), agar kesehatan antrean terlihat sekilas.
- **Filter:** status, tanggal dari dan sampai, serta pencarian penerima/subjek.
- **Tabel (DataTables server-side):**

| Kolom | Isi |
|---|---|
| Waktu | `created_at` |
| Penerima | Nama dan alamat email (atau "belum punya email") |
| Subjek / Event | `subject`, dengan kode event kecil di bawahnya |
| Status | Tag berwarna per status |
| Percobaan | `attempts / max_attempts` dan `next_attempt_at` bila masih `pending` |
| Terkirim | `sent_at` |
| Keterangan | `status_note` atau `last_error` ringkas (lengkap pada tooltip) |
| Aksi | Tombol **Kirim Ulang** (hanya untuk `failed`) |

- Endpoint JSON: protokol DataTables (`draw`, `start`, `length`, `search[value]`,
  `order[0]`), batas 100 baris per permintaan, urutan hanya dari daftar putih kolom,
  semua isi sel di-*escape*. Jumlah per status dikirim bersama respons (atau endpoint
  kecil terpisah).
- **Kirim Ulang:** dialog konfirmasi (`pasporConfirm` / `data-confirm`), lalu `POST`
  dengan CSRF. Efek: `status = pending`, `attempts = 0`, `next_attempt_at = sekarang`,
  `locked_at = NULL`. Aksi ini dicatat ke **Log Sistem** (kode aktivitas baru
  `email.kirim_ulang`). Baris `skipped` karena tidak punya email tidak bisa dikirim ulang
  (tombol nonaktif) sampai email penerima diisi.

### 7.3 Django Admin (read-only)

`EmailLog` juga didaftarkan di Django Admin dalam mode **hanya-baca**: tidak bisa
ditambah, diubah, atau dihapus dari sana (pola sama dengan `ActivityLog`). Fungsinya
sebagai alat bantu teknis untuk superuser.

---

## 8. Langkah Git

Nama branch: **`feat/email_notifications`**, dibuat dari `origin/development`.

```bash
# 1. Pastikan pekerjaan lain sudah bersih / tersimpan
git status --short

# 2. Ambil data terbaru dan buat branch dari development
git fetch origin
git switch -c feat/email_notifications origin/development

# 3. Kerjakan bertahap, commit kecil per tahap (lihat bagian 10)
git add <file-yang-relevan>          # jangan pakai "git add ."
git commit -m "feat(email): model EmailLog dan migrasi"

# 4. Push (pertama kali pakai --set-upstream)
git push --set-upstream origin feat/email_notifications

# 5. Buka Pull Request ke development
#    https://github.com/413x1/paspor_django/compare/development...feat/email_notifications?expand=1
```

Saran pemisahan commit: (1) konfigurasi dan model, (2) worker, (3) trigger dan template,
(4) halaman monitoring, (5) tes dan dokumentasi. Dokumen rencana ini sebaiknya
di-commit lebih dulu (commit terpisah) agar mentor bisa membacanya sebelum kode.

Aturan keamanan Git: jangan commit `.env`. Kredensial SMTP hanya di `.env`.

---

## 9. Pengujian

Memakai backend email `locmem` Django (`mail.outbox`) agar tidak ada email nyata.

| Area | Kasus uji |
|---|---|
| Konfigurasi | `MAIL_ALLOW_SEND` bawaan `False`; pemetaan `MAIL_*` ke `EMAIL_*`; `MAIL_TIMEOUT_MS` ke detik |
| Antre | Baris `pending` dibuat untuk penerima beremail; `skipped` untuk tanpa email; `skipped` bila `MAIL_ALLOW_SEND=false`; event di luar daftar putih tidak diantre |
| Hook | Kegagalan `enqueue` tidak menggagalkan `_create` dan notifikasi in-app tetap terbuat |
| Worker | Satu putaran mengirim sesuai `BATCH_SIZE`; `sent` ditandai; gagal kembali ke `pending` dengan `next_attempt_at`; `failed` setelah `max_attempts`; baris `sending` kedaluwarsa diambil ulang; baris dengan `next_attempt_at` di masa depan tidak diambil |
| Konkurensi | Dua pemanggil bersamaan tidak mengambil baris yang sama (`SKIP LOCKED`) |
| Mode | `ENABLE_WORKER=false` menolak loop, tetapi `--once` jalan |
| Template | Render HTML dan teks; konten pengguna ter-escape; tautan absolut memakai `SITE_BASE_URL` |
| Monitoring | Akses hanya `admin_pakln`; filter dan urutan; batas 100 baris; sel ter-escape |
| Kirim Ulang | Hanya `failed` yang bisa; mereset `attempts`; tercatat di Log Sistem; `skipped` tanpa email ditolak |
| User | Field email pada form Tambah/Edit User tervalidasi dan tersimpan |

Uji manual (Office 365): kirim ke satu alamat uji dengan `MAIL_DEV_REDIRECT_TO`, cek
folder spam, dan cek tampilan di Outlook dan Gmail.

---

## 10. Tahapan pengerjaan

| Tahap | Isi | Hasil yang bisa dicek |
|---|---|---|
| 0 | Konfirmasi keputusan (bagian 12) dan akses SMTP Office 365 | Keputusan tercatat |
| 1 | Setting `EMAIL_*`, saklar `MAIL_ALLOW_SEND`, `SITE_BASE_URL`; model `EmailLog` + migrasi + admin read-only | Tabel ada; `manage.py check` bersih |
| 2 | Field email di Manajemen User; kolom Email di tabelnya | Email bisa diisi dan tampil |
| 3 | `email_queue.enqueue` + hook di `_create`; template dasar | Pengajuan baru membuat baris `EmailLog` |
| 4 | Command `kirim_email_antrean` + pacing + penghentian rapi | Email terkirim ke alamat uji |
| 5 | Halaman Monitor Email + Kirim Ulang + menu sidebar | Admin PAKLN dapat memantau dan mengirim ulang |
| 6 | Template per event, `bersihkan_email_log`, service `mail-worker` di `docker-compose.yml`, dokumentasi di `DEPLOY_SYNOLOGY.MD` | Siap uji coba terbatas |

---

## 11. Risiko dan keamanan

| Risiko | Mitigasi |
|---|---|
| Email nyata terkirim saat pengujian | `MAIL_ALLOW_SEND=false` bawaan; `MAIL_DEV_REDIRECT_TO` |
| 47 akun tanpa email | Status `skipped` terlihat di monitoring; rencana pengisian data (bagian 1.3) |
| SMTP AUTH Office 365 ditolak atau dibatasi | Konfirmasi lebih awal ke pengelola email (bagian 2.4) |
| Melebihi batas kecepatan kirim | Pacing dan `BATCH_SIZE` kecil |
| Email terkirim ganda | Sifat "minimal satu kali" diterima; kunci dengan `LOCK_TTL` |
| Worker mati tanpa terlihat | Kartu status di monitoring; log teknis; `healthcheck` pada service Docker |
| Kebocoran kredensial | Hanya di `.env` (ter-*ignore* git), tidak di wiki atau commit, rotasi bila pernah terpapar |
| Data pribadi (alamat email) menumpuk | Retensi lewat `bersihkan_email_log` |
| Konten pengguna menyisipkan HTML | *Autoescape* template; tidak memakai `|safe` pada konten pengguna |
| Email dianggap spam | SPF/DKIM domain pengirim (urusan pengelola email PU); subjek dan isi wajar; teks polos tersedia |

---

## 12. Keputusan yang perlu dikonfirmasi

| # | Pertanyaan | Rekomendasi |
|---|---|---|
| 1 | Email akun wajib atau opsional? | Opsional + dilewati dengan jejak (`skipped`) dulu |
| 2 | Dari mana data email pegawai diisi? | Tentukan sumber resmi (SDM/Biro). Sementara via Manajemen User |
| 3 | Boleh menambah status `skipped` di luar empat status yang diminta? | Ya, agar "dilewati" tidak bercampur dengan "gagal" |
| 4 | Apakah SMTP AUTH Office 365 sudah diaktifkan untuk `support.eiln@pu.go.id`, dan berapa batas kirimnya? | Konfirmasi ke pengelola email PU |
| 5 | Cakupan event awal sudah sesuai tabel 5.2? | Ya; sisanya Fase 2 |
| 6 | Retensi `EmailLog` berapa hari? | 90 hari untuk `sent` dan `skipped`; `failed` disimpan lebih lama |
| 7 | Worker dijalankan sebagai container terpisah atau cron? | Container `mail-worker` terpisah |

---

## Catatan implementasi

Ringkasan hasil pengerjaan, dan hal yang berbeda atau ditambahkan dari rancangan di atas.

**Berkas utama**

| Berkas | Isi |
|---|---|
| `paspor_project/settings.py` | Pemetaan `MAIL_*` ke `EMAIL_*`, `MAIL_ALLOW_SEND`, `SITE_BASE_URL`, `MAIL_DEV_REDIRECT_TO`, `MAIL_QUEUE` |
| `notifications/models.py` | Model `EmailLog` (+ migrasi `0005_emaillog`) |
| `notifications/email_queue.py` | `enqueue`, `proses_antrean`, `kirim_ulang` |
| `notifications/services.py` | Hook `email_queue.enqueue(...)` di `_create` |
| `notifications/management/commands/` | `kirim_email_antrean`, `bersihkan_email_log` |
| `notifications/views_email.py` + `templates/pakln/monitor_email.html` | Halaman Monitor Email |
| `templates/email/` | Kerangka, partial, dan template per event |
| `accounts/forms.py` + template user | Field email opsional di Tambah/Edit User |
| `docker-compose.yml` | Service `mail-worker` (profile `email`) |

**Perbedaan dan tambahan dari rancangan**

- **`MAIL_DB_QUEUE_SEND_PACING_MS`** (baru, bawaan 2000 ms): jeda antar email dalam satu putaran,
  untuk menjaga batas kecepatan SMTP Office 365 (bagian 2.4).
- **Backoff eksponensial** dipakai untuk jeda percobaan ulang (`RETRY_DELAY x 2^(percobaan-1)`,
  maksimal 1 jam).
- **Kirim Ulang** juga berlaku untuk email `skipped` bila penerima kini punya email dan
  `MAIL_ALLOW_SEND=true` (alamat tujuan diperbarui dari akun saat dikirim ulang).
- **Logo** belum disematkan sebagai lampiran inline (CID); header memakai teks "PASPOR PU".
- **`MAIL_RETRY_ATTEMPTS` dan `MAIL_RETRY_DELAY_MS`** tidak dipakai (retry ditangani antrean).
- **Service `mail-worker`** memakai `profiles: ["email"]` agar tidak menyala otomatis dan
  tidak mengubah deploy yang sudah berjalan.
- **Kolom Email** pada tabel Manajemen User ditampilkan sebagai baris kedua pada kolom Nama
  (penanda "email belum diisi"), bukan kolom baru, agar urutan kolom tabel tidak berubah.
- **Aktivitas Log Sistem** baru: `email.kirim_ulang`.

**Belum dilakukan / perlu tindak lanjut**

- Pengisian email untuk 47 akun yang ada (bagian 1.3). Email baru bisa diisi lewat Manajemen User.
- Uji pengiriman nyata lewat Office 365 (SMTP AUTH, batas kecepatan) dan tampilan di Outlook/Gmail.
- Event Fase 2 (pembatalan ke admin, laporan PDLN, alur BPSDM, pengingat terjadwal).
