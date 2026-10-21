# Rencana Implementasi Celery & Celery Beat

Dokumen riset dan perencanaan (*learning task*): memahami Celery dan Celery Beat, menjelaskan
mengapa PASPOR membutuhkannya, mendata requirement dan fitur yang terdampak, serta
merumuskan cara menjalankannya di Docker. **Dokumen ini belum berisi implementasi**: belum
ada kode Celery di project.

> **Status:** draf rencana, diperbarui Oktober 2026 setelah sistem antrean email berbasis
> database (`EmailLog`) dan Monitor Email berjalan.
>
> **Menunggu keputusan mentor:** pemilihan **Redis** sebagai message broker adalah
> *rekomendasi*, bukan keputusan final. Lihat [bagian 2.3](#23-message-broker-rekomendasi-redis)
> dan [bagian 7](#7-keputusan-yang-perlu-dikonfirmasi-mentor).
>
> Bagian bertanda **[Verifikasi]** harus dicek ulang saat implementasi (versi paket,
> perilaku, dan keputusan tim).

## Daftar isi

1. [Pengantar](#1-pengantar)
2. [Kebutuhan sistem (requirements)](#2-kebutuhan-sistem-requirements)
3. [Rencana implementasi fitur](#3-rencana-implementasi-fitur)
4. [Metode deployment Docker](#4-metode-deployment-docker)
5. [Rencana tahapan](#5-rencana-tahapan)
6. [Risiko dan catatan penting](#6-risiko-dan-catatan-penting)
7. [Keputusan yang perlu dikonfirmasi mentor](#7-keputusan-yang-perlu-dikonfirmasi-mentor)
8. [Referensi](#8-referensi)

---

## 1. Pengantar

### 1.1 Celery: antrean tugas asinkron

Secara bawaan, Django memproses satu request secara berurutan: view berjalan sampai
selesai, baru pengguna menerima halaman. Pekerjaan yang lambat (membuat PDF, mengirim
email, memanggil API luar) membuat pengguna menunggu, dan bila melewati batas waktu
Gunicorn (di project ini `GUNICORN_TIMEOUT=120` dengan 3 worker) request gagal serta satu
worker Gunicorn terblokir.

**Celery** memindahkan pekerjaan lambat itu ke proses lain:

```
Pengguna ──request──▶ Django (web) ──"tolong kerjakan X"──▶ Broker (Redis) ──▶ Worker Celery
              ◀──respons cepat──┘                                              (mengerjakan X di latar belakang)
```

| Istilah | Arti |
|---|---|
| **Task** | Fungsi Python biasa dengan dekorator `@shared_task`. Unit pekerjaan |
| **Producer** | Kode Django yang memanggil `task.delay(...)`. Hanya menaruh pesan, tidak menunggu hasil |
| **Broker** | Perantara antrean pesan (Redis atau RabbitMQ) |
| **Worker** | Proses terpisah yang mengambil pesan dari broker dan menjalankan task |
| **Queue** | Jalur antrean bernama (mis. `email`, `pdf`) agar pekerjaan berat tidak menghalangi yang ringan |
| **Result backend** | (Opsional) tempat menyimpan hasil/status task |

Intinya: **web hanya menitipkan pesan, worker yang bekerja**. Web tetap responsif dan
jumlah worker dapat ditambah tanpa mengubah kode.

### 1.2 Celery Beat: penjadwal

Celery hanya menjalankan task saat diminta. **Celery Beat** adalah proses terpisah yang
berperan sebagai *jam alarm*: pada waktu terjadwal (mis. "setiap hari 07.00" atau "tiap
60 detik") Beat menaruh pesan task ke broker, lalu worker mengerjakannya. Beat adalah
pengganti cron yang terintegrasi dengan Django.

```
Beat (jadwal) ──"07.00: pengingat_laporan"──▶ Redis ──▶ Worker
```

Dua cara mendefinisikan jadwal:
- **Statis** di `settings.py` lewat `CELERY_BEAT_SCHEDULE`. Sederhana dan ikut versi kode.
- **Dinamis** lewat `django-celery-beat`. Jadwal disimpan di database dan dapat diubah dari
  Django Admin tanpa deploy ulang (menambah tabel dan migrasi).

**Aturan penting:** hanya boleh ada **satu** proses Beat. Dua Beat berarti setiap task
terjadwal terkirim dua kali. Worker boleh banyak.

### 1.3 Masalah (*bottleneck*) di PASPOR yang diselesaikan

Hasil pemeriksaan kode (Oktober 2026):

| # | Kondisi sekarang | Dampak | Diselesaikan oleh |
|---|---|---|---|
| 1 | **Email** diantre di tabel `EmailLog`, dikirim oleh *worker loop* manual `kirim_email_antrean` yang mengetuk tabel tiap 15 detik dan memberi jeda 2 detik per email (`MAIL_DB_QUEUE_*`). Service `mail-worker` terpisah dan tidak menyala otomatis (`profiles: ["email"]`) | Latensi sampai 15 detik; polling menambah beban MySQL; retry dan *lock* ditulis sendiri | Celery worker (antrean `email`) |
| 2 | **PDF Nota Dinas** (`generate_nd_kabag`, `generate_nd_karo`, `download_nd_*_pdf`) dirender WeasyPrint **di dalam request** | Memakan CPU/memori dan menahan 1 dari 3 worker Gunicorn selama pembuatan PDF | Celery worker (antrean `pdf`) |
| 3 | **Export CSV/XLSX dan rekap** (`report.respons_csv`, `respons_xlsx`, `rekap`) dibuat saat request | Data besar memperlambat halaman dan berisiko *timeout* | Celery worker |
| 4 | **Integrasi Platform BPSDM** (`paspor/integrasi/pintar.py`) memakai `urllib` sinkron, timeout 5 detik, saat ini memakai data contoh (*stub*) | Rentan timeout; belum ada cache | Celery worker + cache |
| 5 | **Sinkronisasi e-HRM** (`sinkron_ehrm`) hanya dijalankan manual | Data kepegawaian (termasuk email/HP) bisa basi | Celery Beat |
| 6 | **Pengingat** belum ada. Batas laporan PDLN 14 hari (`report.BATAS_HARI_LAPORAN`) baru berupa penanda "Terlambat" di tabel | Pegawai tidak diingatkan | Celery Beat |
| 7 | **Pemeliharaan** (`bersihkan_log`, `bersihkan_email_log`, `sync_media_to_s3`, `hitung_ulang_hari_kerja`) berupa *management command* manual | Tabel log membengkak bila lupa dijalankan | Celery Beat |

### 1.4 Hubungan dengan antrean email yang sudah ada

Antrean email berbasis database **sudah diimplementasikan** (lihat
`EMAIL_NOTIF_IMPLEMENTATION_PLAN.MD`): model `EmailLog`, fungsi `email_queue.enqueue` yang
dipanggil dari `notifications.services._create`, `proses_antrean` (kunci baris, retry
eksponensial, jeda antar email), dan halaman **Monitor Email** untuk Admin Biro PAKLN.

Rencana ini **tidak membuang** itu. Rekomendasinya:

- **Tabel `EmailLog` dan Monitor Email dipertahankan** sebagai catatan resmi (pola *outbox*:
  baris dicatat di MySQL dalam transaksi yang sama dengan data bisnis).
- **Yang diganti hanya pengirimnya:** worker loop `kirim_email_antrean` digantikan task
  Celery. Hasilnya: latensi turun dari interval polling ke milidetik, dan tidak ada lagi
  container loop yang mengetuk MySQL.
- Beat menjalankan **jaring pengaman** (menyapu baris `pending`) sehingga pesan yang hilang
  saat Redis mati tidak membuat email tertinggal.

---

## 2. Kebutuhan sistem (requirements)

### 2.1 Library Python (`requirements.txt`)

| Paket | Fungsi | Wajib |
|---|---|---|
| `celery[redis]` | Inti: task, worker, Beat. *Extra* `redis` menarik klien Redis dengan versi yang kompatibel | Ya |
| `django-celery-beat` | Jadwal Beat di database yang dapat diedit di Django Admin | Opsional (lihat 3.3) |
| `flower` | Dasbor web pemantauan worker dan task | Opsional |

Versi terbaru saat dokumen ini diperbarui: `celery 5.6.3`, `django-celery-beat 2.9.0`,
`flower 2.2.0`, dan klien `redis 8.1.0`.

**[Verifikasi]**
- Pakai `celery[redis]` (bukan `redis` terpisah) agar versi klien Redis mengikuti batas yang
  diizinkan Celery/Kombu; klien `redis` terbaru dapat melampaui batas tersebut.
- Pastikan rilis Celery yang dipilih resmi mendukung **Django 6.1** dan **Python 3.13**
  (image Docker memakai `python:3.13-slim`). Project ini memin versi (`Django==6.1.1`), jadi
  kunci versi hanya setelah uji.
- Cache Redis memakai backend bawaan Django (`django.core.cache.backends.redis.RedisCache`),
  sehingga **tidak perlu** paket `django-redis`.

### 2.2 Infrastruktur

| Komponen | Keterangan |
|---|---|
| **Redis** | Broker pesan (dan cache). Image `redis:7-alpine`, satu container, tanpa port ke luar |
| **Celery worker** | Container yang menjalankan `celery worker`, **image yang sama** dengan `web` |
| **Celery Beat** | Container yang menjalankan `celery beat`, tepat 1 instance |
| **MySQL** | Tetap di luar container (project terpisah di NAS). Tidak berubah; `django-celery-beat` menambah beberapa tabel bila dipakai |
| **S3 (Garage)** | Tetap di luar container; dipakai worker untuk menyimpan PDF/export hasil |

Image Docker yang ada sudah memuat dependensi sistem WeasyPrint (pango, harfbuzz, font), jadi
worker yang memakai image yang sama otomatis dapat membuat PDF.

### 2.3 Message broker: rekomendasi Redis

> **Catatan:** pemilihan **Redis** di bawah ini adalah **rekomendasi** penulis dan
> **masih menunggu persetujuan/konfirmasi final dari mentor**.

Alasan merekomendasikan Redis:

1. **Lebih ringan dibanding RabbitMQ.** Satu proses kecil, memori sedikit, cocok untuk NAS
   dengan CPU dan RAM terbatas. RabbitMQ (Erlang) lebih berat dan fiturnya (routing
   kompleks, federasi) belum dibutuhkan.
2. **Image tersedia di Synology Container Manager** (`redis:7-alpine`), sehingga dapat
   dijalankan sebagai service di compose yang sama.
3. **Umum dan stabil bersama Celery.** Dokumentasi dan contoh Celery–Django paling banyak
   memakai Redis; masalahnya mudah dicari solusinya.
4. **Sekalian menjadi cache.** Redis yang sama dapat dipakai backend cache Django (mis. untuk
   hasil integrasi Platform BPSDM).

Pembanding singkat:

| Opsi | Kelebihan | Kekurangan |
|---|---|---|
| **Redis** (rekomendasi) | Ringan, mudah, serbaguna (broker + cache) | Pesan di memori; perlu AOF agar tahan restart |
| RabbitMQ | Pengiriman pesan paling andal, fitur routing lengkap | Lebih berat dan rumit dijaga untuk kebutuhan sekarang |
| Antrean database (kondisi sekarang) | Tanpa komponen baru | Polling membebani MySQL, latensi, tanpa penjadwalan, retry/lock ditulis sendiri |
| `django.tasks` (Django 6) | Standar framework | Pekerja produksinya bergantung paket tambahan dan tidak memiliki Beat; ekosistem lebih muda **[Verifikasi]** |

Konfigurasi Redis yang aman sebagai broker:
- `--appendonly yes` + volume, agar pesan bertahan saat restart.
- `--maxmemory-policy noeviction`, agar Redis **menolak** tulis saat penuh, bukan diam-diam
  membuang pesan antrean.
- Tidak membuka `ports` ke luar; hanya dijangkau antar-container.

### 2.4 Konfigurasi baru (`.env`)

| Variabel | Contoh | Keterangan |
|---|---|---|
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Alamat Redis. Di Docker, `redis` adalah nama service |
| `CELERY_TIMEZONE` | `Asia/Jakarta` | Samakan dengan `TIME_ZONE` Django agar jam jadwal Beat sesuai WIB |
| `REDIS_CACHE_URL` | `redis://redis:6379/1` | (Opsional) database Redis terpisah untuk cache |

### 2.5 Perubahan kode dasar

**`paspor_project/celery.py`** (aplikasi Celery)

```python
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paspor_project.settings")

app = Celery("paspor_project")
app.config_from_object("django.conf:settings", namespace="CELERY")  # baca setting berawalan CELERY_
app.autodiscover_tasks()                                            # cari tasks.py di tiap app
```

**`paspor_project/__init__.py`**

```python
from .celery import app as celery_app

__all__ = ("celery_app",)
```

**`settings.py`** (tambahan)

```python
CELERY_BROKER_URL = env("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_TIMEZONE = TIME_ZONE                      # Asia/Jakarta
CELERY_TASK_IGNORE_RESULT = True                 # status dicatat di tabel sendiri, bukan result backend
CELERY_TASK_ACKS_LATE = True                     # pesan dianggap selesai setelah task sukses
CELERY_WORKER_PREFETCH_MULTIPLIER = 1            # worker tidak menimbun banyak pesan
CELERY_TASK_TIME_LIMIT = 300                     # batas keras 5 menit
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "notifications.tasks.*": {"queue": "email"},
    "pengajuan.tasks.buat_*": {"queue": "pdf"},
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", "redis://127.0.0.1:6379/1"),
    }
}
```

---

## 3. Rencana implementasi fitur

Lambang pemicu: **E** = dipicu kejadian di aplikasi, **J** = terjadwal oleh Beat.

### 3.1 Asynchronous tasks (Celery worker)

| # | Fitur | Pemicu | Antrean | Prioritas |
|---|---|---|---|---|
| A1 | Email notifikasi (pengganti worker loop `kirim_email_antrean`) | E | `email` | 1 |
| A2 | Generate PDF Nota Dinas (WeasyPrint) | E | `pdf` | 2 |
| A3 | Export CSV/XLSX dan rekap data besar | E | `pdf` (atau `export`) | 3 |
| A4 | Integrasi API Platform BPSDM (asinkron + cache) | E / J | `default` | 4 |

#### A1. Email notifikasi

**Kondisi sekarang:** `notifications.services._create` membuat `Notification` lalu memanggil
`email_queue.enqueue`, yang menulis baris `EmailLog` berstatus `pending`. Pengiriman SMTP
dilakukan worker loop `kirim_email_antrean` (`email_queue.proses_antrean`) di container
`mail-worker`.

**Rancangan:**

```python
# notifications/tasks.py
from celery import shared_task

from . import email_queue


@shared_task(bind=True, queue="email", acks_late=True)
def kirim_antrean_email(self):
    """Satu putaran pengiriman: mengambil baris `pending` (kunci baris dan jeda SMTP tetap
    ditangani email_queue) lalu mengirimnya. Aman dijalankan berulang (idempotent)."""
    return email_queue.proses_antrean(worker_id=self.request.hostname)
```

```python
# notifications/email_queue.py, di akhir enqueue(), setelah EmailLog.objects.bulk_create(baris)
from django.db import transaction
from .tasks import kirim_antrean_email

transaction.on_commit(kirim_antrean_email.delay)   # picu segera setelah data tersimpan
```

- **Pemicu ganda yang saling melengkapi:** (1) `on_commit(...delay)` untuk latensi rendah;
  (2) Beat tiap 60 detik memanggil `kirim_antrean_email` sebagai **jaring pengaman** bila
  pesan hilang (Redis restart) atau baris menunggu `next_attempt_at` (backoff).
- **Mengapa memanggil `proses_antrean`, bukan satu task per email:** MySQL tidak
  mengembalikan *primary key* pada `bulk_create`, dan logika kunci baris (`LOCK_TTL`), retry
  eksponensial, serta jeda antar email sudah teruji. Cukup dipakai ulang.
- **Antrean `email` dengan `--concurrency 1`** (atau `rate_limit`) menjaga jeda antar email
  sesuai batas kecepatan SMTP Office 365 (`MAIL_DB_QUEUE_SEND_PACING_MS`).
- **Dipertahankan:** model `EmailLog`, Monitor Email, tombol **Kirim Ulang** (cukup memanggil
  `kirim_antrean_email.delay()` setelah baris dikembalikan ke `pending`), saklar
  `MAIL_ALLOW_SEND` dan `MAIL_DEV_REDIRECT_TO`.
- **Dipensiunkan:** service `mail-worker` dan mode loop `kirim_email_antrean`
  (command `--once` boleh tetap ada untuk *debugging*).

#### A2. Generate PDF Nota Dinas (WeasyPrint)

**Kondisi sekarang:** `download_nd_kabag_pdf` dan `download_nd_karo_pdf` memanggil
`HTML(string=...).write_pdf()` di dalam request lalu menyimpan salinan ke
`DokumenGenerateLog` (Histori Generate Dokumen).

**Rancangan:** `buat_pdf_nota_dinas(jenis, pengajuan_ids, dibuat_oleh_id)` merender PDF,
menyimpannya ke S3, dan mengisi `DokumenGenerateLog.file`.

| Aspek | Rancangan |
|---|---|
| Alur pengguna | Admin menekan **Unduh PDF** → halaman menampilkan "Sedang dibuat" → baris di **Histori Generate** berubah menjadi *selesai* (dipoll) dan Admin menerima notifikasi in-app berisi tautan unduh |
| Perubahan data | Tambah `status` (`menunggu`/`selesai`/`gagal`) dan `catatan_galat` pada `DokumenGenerateLog` (migrasi) |
| Argumen task | ID saja (`pengajuan_ids`, `dibuat_oleh_id`), bukan objek |
| Batas | `soft_time_limit` 120 detik; `--concurrency` rendah (WeasyPrint berat) |
| Tahap awal | Asinkron hanya untuk **batch multi-pengajuan**; satu dokumen kecil boleh tetap sinkron sampai pola ini terbukti |

#### A3. Export CSV/XLSX dan rekap

**Kondisi sekarang:** `report.respons_csv`/`respons_xlsx` membuat berkas saat request,
mengikuti cakupan data tiap peran (`pengajuan/report.py`).

**Rancangan:** ambang batas (mis. > 2.000 baris, **[Verifikasi]** angka) mengalihkan export ke
task `buat_export(parameter_filter, format, user_id)`. Hasil disimpan ke S3, pengguna diberi
notifikasi in-app dengan tautan unduh bertanda tangan (kedaluwarsa), dan baris pelacak
mencatat status. Di bawah ambang batas tetap sinkron.

**Catatan desain:** A2 dan A3 sebaiknya berbagi satu model pelacak berkas hasil (mis.
`BerkasHasil`: jenis, pemilik, status, `file`, `created_at`) agar tidak ada dua mekanisme
serupa. Keputusannya dibahas saat tahap implementasi.

#### A4. Integrasi API Platform BPSDM

**Kondisi sekarang:** `paspor.integrasi.pintar.daftar_pencalonan_selesai(nip, jenis)` memakai
`urllib` sinkron dengan `PINTAR_API_TIMEOUT` 5 detik, dan memakai data contoh bila
`PINTAR_API_URL` kosong. Saat ini fungsi tersebut **belum dipanggil dari view mana pun**
(droplist beasiswa sudah digantikan master **Kegiatan**); integrasinya disiapkan untuk
sinkronisasi kegiatan (`Kegiatan.kode_pintar`, `sumber_data = pintar`).

**Rancangan:**
- Task terjadwal `sinkron_platform_bpsdm` (J, mis. tiap 30 menit) mengambil data dan
  memperbarui `Kegiatan` berkode unik; kegagalan API hanya dicatat dan diulang (retry dengan
  *backoff*), **tidak pernah** memengaruhi halaman pengguna.
- Task sesuai permintaan `segarkan_pencalonan(nip)` untuk pembaruan satu pegawai, hasilnya
  disimpan di **cache Redis** dengan TTL (mis. 15 menit) agar halaman tidak memanggil API
  luar secara langsung.
- Kontrak API masih berupa asumsi (lihat docstring `pintar.py`); [Verifikasi] saat
  spesifikasi resmi tersedia.

### 3.2 Scheduled / cron tasks (Celery Beat)

| # | Task | Jadwal (WIB) | Isi |
|---|---|---|---|
| S0 | `kirim_antrean_email` | Tiap 60 detik | Jaring pengaman antrean email (lihat A1) |
| S1 | `sinkron_ehrm` | Harian 01.00 | Memanggil logika `sinkron_ehrm` untuk semua user ber-`PegawaiProfile`; menghormati kunci email/HP |
| S2 | `pengingat_laporan_pdln` | Harian 07.00 | Mengingatkan pegawai PDLN yang belum melapor |
| S3 | `pengingat_masa_berlaku_paspor` | Harian 07.15 | Mengingatkan paspor yang akan kedaluwarsa |
| S4 | `bersihkan_log_sistem` | Minggu 02.00 | `bersihkan_log --hari N` (retensi **[Verifikasi]**, mis. 365) |
| S5 | `bersihkan_email_log` | Minggu 02.30 | `bersihkan_email_log --hari 90` (retensi 90 hari sesuai rencana email) |
| S6 | `hitung_ulang_hari_kerja` | Harian 03.00 | Jaring pengaman untuk draf setelah kalender libur berubah |
| S7 | `sync_media_to_s3` | Opsional, Minggu 03.30 | Hanya selama masa transisi bila masih ada berkas di `MEDIA_ROOT`; nonaktifkan setelah semuanya di S3 |

#### S1. Sinkronisasi e-HRM

Command `sinkron_ehrm` (opsi `--nip`, `--dry-run`) sudah ada dan menyebut dapat dijadwalkan
lewat cron. Task membungkusnya (mis. `call_command("sinkron_ehrm")`) dengan **kunci**
(`cache.add("kunci:sinkron_ehrm", ..., timeout)`) agar dua eksekusi tidak tumpang tindih.
Selama `EHRM_API_URL` kosong, sistem memakai data contoh (*stub*). Task juga disarankan
dapat dipanggil per NIP (mis. saat login SSO) lewat `.delay(nip=...)`.

#### S2 dan S3. Pengingat otomatis

| Pengingat | Kriteria | Kanal |
|---|---|---|
| **Laporan PDLN** | PDLN berstatus `selesai`, laporan belum dikirim/disetujui; mengacu `report.BATAS_HARI_LAPORAN` (14 hari sejak `tgl_kembali`). Tahap: **H+10** (peringatan) dan **melewati batas** (terlambat) | Notifikasi in-app + email ke pegawai; tembusan Admin Unor untuk yang terlambat |
| **Masa berlaku paspor** | `PasporPegawai.tgl_expired` dalam **180 hari** dan dalam **30 hari** (**[Verifikasi]** ambang) | Notifikasi in-app + email ke pegawai |

Syarat teknis:
- **Anti-duplikat:** satu tabel kecil pelacak (mis. `PengingatTerkirim`: jenis, id objek,
  tahap; *unique constraint*) agar pengingat harian tidak dikirim berulang.
- Notifikasi dibuat lewat `notifications.services` (menurunkan email otomatis). Perlu event
  baru pada `Notification.Event` (migrasi pilihan) dan penambahan ke daftar putih pegawai di
  `email_queue.EMAIL_EVENTS`.
- Jam dijalankan di luar jam kerja agar tidak berbenturan dengan lalu lintas pengguna.

#### S4 sampai S7. Pembersihan rutin

Semua sudah berupa *management command* dengan `--dry-run`; task cukup memanggilnya dengan
`call_command` dan mencatat hasilnya. `bersihkan_log` dan `bersihkan_email_log` menghapus
**permanen**, jadi retensi harus disetujui pemilik proses bisnis sebelum dijadwalkan.
`hitung_ulang_hari_kerja` hanya menyentuh draf (`status = belum`).

Contoh jadwal statis:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "antrean-email-jaring-pengaman": {
        "task": "notifications.tasks.kirim_antrean_email",
        "schedule": 60.0,
    },
    "sinkron-ehrm-harian": {
        "task": "accounts.tasks.sinkron_ehrm",
        "schedule": crontab(hour=1, minute=0),
    },
    "pengingat-laporan-pdln": {
        "task": "pengajuan.tasks.pengingat_laporan_pdln",
        "schedule": crontab(hour=7, minute=0),
    },
    "pengingat-masa-berlaku-paspor": {
        "task": "accounts.tasks.pengingat_masa_berlaku_paspor",
        "schedule": crontab(hour=7, minute=15),
    },
    "bersihkan-log-sistem": {
        "task": "logs.tasks.bersihkan_log_sistem",
        "schedule": crontab(hour=2, minute=0, day_of_week="sun"),
    },
    "bersihkan-email-log": {
        "task": "notifications.tasks.bersihkan_email_log",
        "schedule": crontab(hour=2, minute=30, day_of_week="sun"),
    },
    "hitung-ulang-hari-kerja": {
        "task": "paspor.tasks.hitung_ulang_hari_kerja",
        "schedule": crontab(hour=3, minute=0),
    },
}
```

### 3.3 Pola umum untuk semua task

1. **Kirim ID, bukan objek model**, sebagai argumen (data bisa berubah, objek tidak aman
   diserialisasi).
2. **Pakai `transaction.on_commit`** saat memanggil `.delay()` dari dalam transaksi. Project
   ini banyak memakai `transaction.atomic()` pada perubahan status; tanpa `on_commit`, worker
   dapat berjalan sebelum data tersimpan.
3. **Idempotent:** task boleh berjalan dua kali tanpa merugikan (cek status "sudah
   dikirim/selesai" lebih dulu).
4. **Retry dengan *backoff*** untuk pekerjaan yang bergantung sistem luar
   (`autoretry_for`, `retry_backoff=True`, `max_retries`).
5. **Kunci** untuk task terjadwal agar eksekusi tidak tumpang tindih.
6. **Statis atau dinamis?** Untuk MVP pakai `CELERY_BEAT_SCHEDULE` statis (tanpa migrasi).
   `django-celery-beat` dipertimbangkan bila jadwal perlu diubah dari Django Admin.

---

## 4. Metode deployment Docker

### 4.1 Arsitektur container

```
                         ┌───────────────────────── NAS Synology ─────────────────────────┐
                         │                                                                │
  Pengguna ──▶ web ──────┼──▶ redis ◀── celery-worker  (antrean: default, email, pdf)    │
  (Gunicorn)   │         │       ▲                                                        │
               │         │       └──── celery-beat     (penjadwal, TEPAT 1)               │
               │         │                                                                │
               └─────────┼──▶ MySQL (project terpisah)   ──▶ Garage S3 (project terpisah) │
                         └────────────────────────────────────────────────────────────────┘
```

Kondisi sekarang pada `docker-compose.yml`: service **`web`** (build dari `Dockerfile`,
`python:3.13-slim`, Gunicorn, port 8000, *healthcheck*) dan **`mail-worker`** (image yang
sama, `command: kirim_email_antrean`, `profiles: ["email"]`). MySQL dan Garage berada di
project lain di NAS dan dijangkau lewat IP di `.env`.

### 4.2 Prinsip

- **Satu image, banyak peran.** `web`, `celery-worker`, dan `celery-beat` memakai image
  `paspor-django` yang sama; beda hanya pada *command* (meniru pola `mail-worker`).
- **Satu proses per container.** Worker dan Beat tidak digabung.
- **Hanya `web` yang menjalankan migrasi.** `docker/entrypoint.sh` menjalankan `migrate` dan
  `deploy_init` pada setiap start, kecuali `DJANGO_MIGRATE_ON_START=False` dan
  `DJANGO_INIT_ON_START=False`. Worker dan Beat **wajib** mematikan keduanya, seperti yang
  sudah dilakukan `mail-worker`.
- **Beat tepat satu.** Jangan menambah replika Beat.
- **Urutan start:** Redis sehat, `web` sehat (tabel sudah ada), lalu worker dan Beat.
- **Profil bertahap.** Tiru `mail-worker`: service baru diberi `profiles: ["celery"]` sehingga
  tidak mengubah deploy yang sudah berjalan sampai diaktifkan.

### 4.3 Contoh `docker-compose.yml`

Tambahan di atas file yang ada (service `web` dan `mail-worker` tidak diubah, kecuali `web`
menerima `CELERY_BROKER_URL` agar dapat memanggil `.delay()`). Bagian baru:

```yaml
x-celery-env: &celery-env
  TZ: Asia/Jakarta
  CELERY_BROKER_URL: redis://redis:6379/0
  REDIS_CACHE_URL: redis://redis:6379/1
  DJANGO_MIGRATE_ON_START: "False"     # migrasi hanya oleh service web
  DJANGO_INIT_ON_START: "False"

services:
  web:
    # ... (tetap seperti sekarang) ...
    environment:
      TZ: Asia/Jakarta
      CELERY_BROKER_URL: redis://redis:6379/0
      REDIS_CACHE_URL: redis://redis:6379/1

  # mail-worker: dipensiunkan setelah email berpindah ke Celery (lihat tahap 2)

  # --- Redis: broker pesan dan cache -----------------------------------------
  redis:
    image: redis:7-alpine
    container_name: paspor-redis
    profiles: ["celery"]
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--maxmemory", "256mb", "--maxmemory-policy", "noeviction"]
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    # Tanpa "ports": Redis hanya dijangkau antar-container.

  # --- Celery worker: mengerjakan task ------------------------------------------
  celery-worker:
    image: paspor-django:latest
    container_name: paspor-celery-worker
    profiles: ["celery"]
    restart: unless-stopped
    env_file: .env
    environment: *celery-env
    command: ["celery", "-A", "paspor_project", "worker", "-l", "info", "-Q", "default,email,pdf", "--concurrency", "2"]
    depends_on:
      web:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "celery -A paspor_project inspect ping -d celery@$$HOSTNAME"]
      interval: 60s
      timeout: 15s
      retries: 3
      start_period: 40s

  # --- Celery Beat: penjadwal (TEPAT SATU instance) ----------------------------------
  celery-beat:
    image: paspor-django:latest
    container_name: paspor-celery-beat
    profiles: ["celery"]
    restart: unless-stopped
    env_file: .env
    environment: *celery-env
    command: ["celery", "-A", "paspor_project", "beat", "-l", "info", "--schedule", "/tmp/celerybeat-schedule"]
    depends_on:
      web:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  redis-data:
```

Aktivasi: `docker compose --profile celery up -d --build` (sama pola dengan
`docker compose --profile email up -d`).

Penjelasan:

| Bagian | Alasan |
|---|---|
| `command:` pada worker/beat | Menimpa `CMD` Gunicorn. `ENTRYPOINT` tetap `entrypoint.sh`, yang menunggu database lalu `exec "$@"` |
| `DJANGO_*_ON_START=False` | Mencegah migrasi dan seed berjalan serentak di tiga container |
| `-Q default,email,pdf` | Satu worker melayani tiga antrean untuk MVP. Bila PDF mulai menghambat email, pisahkan: worker khusus `-Q email --concurrency 1` dan worker `-Q pdf,default` |
| `--concurrency 2` | NAS umumnya terbatas CPU/RAM; WeasyPrint berat |
| `--schedule /tmp/...` | Image berjalan sebagai user non-root `app`; `/tmp` selalu dapat ditulis. Jadwal statis, jadi file boleh hilang saat container dibuat ulang |
| `--appendonly yes` + volume + `noeviction` | Pesan bertahan saat restart dan tidak dibuang saat memori penuh |
| Tanpa `ports` pada Redis | Mengurangi permukaan serangan |
| `depends_on ... service_healthy` | Menjamin Redis dan tabel database siap |

### 4.4 Perintah operasional

```bash
docker compose --profile celery up -d --build      # bangun dan jalankan semua service Celery
docker compose ps                                  # cek status service
docker compose logs -f celery-worker celery-beat   # log worker dan Beat
docker compose restart celery-worker               # setelah mengubah kode task
docker compose exec celery-worker celery -A paspor_project inspect active   # task yang sedang berjalan
```

Di Synology Container Manager, compose dijalankan sebagai *Project* (lihat
`DEPLOY_SYNOLOGY.MD`). Redis tidak perlu dibuat terpisah: ia ikut dalam project yang sama.

### 4.5 Pengembangan lokal (Windows)

Celery tidak mendukung Windows secara resmi untuk pool bawaan (**[Verifikasi]**). Opsi untuk
belajar di laptop:
- Redis lewat Docker: `docker run -p 6379:6379 redis:7-alpine`.
- Worker dengan pool `solo`: `celery -A paspor_project worker -l info --pool=solo`.
- Atau jalankan seluruh stack lewat `docker compose` agar identik dengan produksi.

### 4.6 Pemantauan

- Minimal: `docker compose logs` dan `celery inspect ping/active`.
- Opsional: **Flower** sebagai service tambahan (tidak dibuka ke luar tanpa autentikasi).
- Monitor Email di aplikasi tetap menjadi sumber kebenaran status pengiriman email.

---

## 5. Rencana tahapan

| Tahap | Isi | Hasil yang dapat dicek |
|---|---|---|
| 0. Belajar | Baca dokumentasi Celery; coba di laptop: Redis via Docker, satu task `add(x, y)`, jalankan worker | Task berjalan dan hasil terlihat di log worker |
| 1. Fondasi | Tambah paket, `celery.py`, setting `CELERY_*`, cache; service `redis` dan `celery-worker` di compose | `docker compose ps` sehat; `celery inspect ping` menjawab |
| 2. Email (A1) | Task `kirim_antrean_email`, `on_commit`, Beat jaring pengaman (S0); pensiunkan `mail-worker` | Email terkirim tanpa memperlambat halaman; Monitor Email tetap akurat |
| 3. Beat | Tambah `celery-beat`; jadwalkan pembersihan (S4 dan S5) lalu sinkron e-HRM (S1) | Task terjadwal muncul di log Beat dan worker |
| 4. Pengingat | Event baru, tabel anti-duplikat, task S2 dan S3 | Pengingat harian terkirim sekali per tahap |
| 5. PDF dan export | A2 dan A3: pelacak berkas hasil, S3, notifikasi | PDF/export besar tidak menahan request |
| 6. Platform BPSDM | A4: sinkron terjadwal dan cache (menunggu kontrak API) | Kegagalan API tidak memengaruhi halaman |
| 7. Pengerasan | Retry, batas waktu, pemantauan, perbarui `DEPLOY_SYNOLOGY.MD` dan runbook | Dokumen operasional |

Urutan prioritas belajar: **A1 (email)**, lalu **S4/S5 (pembersihan)** karena paling mudah
untuk mencoba Beat, lalu **S2 (pengingat laporan)**.

---

## 6. Risiko dan catatan penting

- **Satu Beat saja.** Beat ganda menggandakan semua task terjadwal.
- **Task harus idempotent.** Pesan dapat terkirim dua kali (retry atau Redis restart).
- **Redis bukan penyimpanan permanen.** Data bisnis dan status email tetap di MySQL; baris
  `EmailLog` adalah sumber kebenaran sehingga pesan yang hilang dapat disapu ulang oleh Beat.
- **Migrasi di container.** Pastikan hanya `web` yang menjalankan `migrate`.
- **Sumber daya NAS.** Jaga `--concurrency` rendah; tiap worker membawa Django penuh dan
  library PDF.
- **Penghapusan permanen.** Task pembersihan menghapus data tanpa pemulihan; retensi harus
  disetujui dan `--dry-run` dicoba lebih dulu.
- **Kredensial.** Jangan menulis kata sandi SMTP atau Redis di dokumen atau repo; simpan di
  `.env` (sudah di-*ignore* git). Redis tidak dibuka ke luar container.
- **Zona waktu.** Samakan `CELERY_TIMEZONE` dengan `TIME_ZONE` (WIB).
- **Pemantauan.** Tanpa pemantauan, task gagal dapat tidak terlihat; minimal pantau log
  worker, pertimbangkan Flower.
- **Dampak data.** A2, A3, dan pengingat menambah migrasi (status pelacak, event baru,
  tabel anti-duplikat). Rencanakan nomor migrasi dengan hati-hati agar tidak bentrok antar
  branch.

---

## 7. Keputusan yang perlu dikonfirmasi mentor

| # | Pertanyaan | Rekomendasi |
|---|---|---|
| 1 | **Message broker:** Redis, RabbitMQ, atau tetap antrean database? | **Redis** (menunggu konfirmasi final) |
| 2 | Antrean email yang sudah ada: diganti total atau hanya pengirimnya? | Pertahankan `EmailLog` dan Monitor Email; ganti hanya worker loop dengan Celery |
| 3 | Jadwal Beat: statis di kode atau `django-celery-beat` (dapat diedit di admin)? | Statis dahulu; `django-celery-beat` bila jadwal perlu diubah tanpa deploy |
| 4 | Retensi Log Sistem dan email (hapus permanen) | Email 90 hari; Log Sistem **[Verifikasi]** (mis. 365 hari) |
| 5 | Ambang pengingat: laporan PDLN (H+10 dan terlambat) dan paspor (180/30 hari) | Sesuai usulan di bagian 3.2 |
| 6 | Ambang export besar menjadi asinkron | Mulai 2.000 baris, sesuaikan setelah diukur |
| 7 | Perlu pemantauan Flower di produksi? | Opsional |
| 8 | Kontrak API Platform BPSDM dan kebutuhan sinkron tetap | Menunggu spesifikasi resmi |

---

## 8. Referensi

- Dokumentasi Celery: <https://docs.celeryq.dev/>
- Celery dengan Django (*First steps with Django*):
  <https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html>
- Periodic Tasks (Celery Beat):
  <https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html>
- Menggunakan Redis sebagai broker:
  <https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html>
- `django-celery-beat`: <https://github.com/celery/django-celery-beat>
- Backend cache Redis Django:
  <https://docs.djangoproject.com/en/stable/topics/cache/#redis>
- Dokumen terkait di project: `EMAIL_NOTIF_IMPLEMENTATION_PLAN.MD`, `DEPLOY_SYNOLOGY.MD`,
  `SKENARIO_NOTIFIKASI_SURAT.md`, `SYSTEM_LOGGING.MD`
