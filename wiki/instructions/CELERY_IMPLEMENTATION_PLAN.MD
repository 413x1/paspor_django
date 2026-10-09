# Rencana Implementasi Celery & Celery Beat

Dokumen *learning task*: memahami Celery dan Celery Beat, menjelaskan kebutuhannya
untuk project PASPOR, daftar requirement, daftar fitur yang cocok, dan metode
menjalankannya di Docker.

> **Status:** draft awal untuk dipelajari dan dilengkapi. Belum ada kode Celery di
> project. Bagian bertanda **[Verifikasi]** adalah hal yang harus dicek ulang saat
> implementasi (versi paket, perilaku, dan keputusan tim).

## Daftar isi

1. [Memahami tools](#1-memahami-tools)
2. [Gambaran kebutuhan](#2-gambaran-kebutuhan)
3. [Daftar requirements](#3-daftar-requirements)
4. [Daftar fitur](#4-daftar-fitur)
5. [Metode deployment container](#5-metode-deployment-container)
6. [Contoh kode inti](#6-contoh-kode-inti)
7. [Rencana tahapan](#7-rencana-tahapan)
8. [Risiko dan catatan penting](#8-risiko-dan-catatan-penting)
9. [Referensi](#9-referensi)

---

## 1. Memahami tools

### 1.1 Celery: antrean tugas asinkron

Secara bawaan, Django memproses satu request secara berurutan: view berjalan sampai
selesai, baru pengguna menerima halaman. Pekerjaan yang lambat (membuat PDF, mengirim
email, memanggil API luar) membuat pengguna menunggu, dan bila melewati batas waktu
Gunicorn (di project ini `GUNICORN_TIMEOUT=120`), request gagal.

**Celery** memindahkan pekerjaan lambat itu ke proses lain:

```
Pengguna ──request──▶ Django (web) ──"tolong kerjakan X"──▶ Broker (Redis) ──▶ Worker Celery
              ◀──respons cepat──┘                                              (mengerjakan X di latar belakang)
```

| Istilah | Arti |
|---|---|
| **Task** | Fungsi Python biasa yang diberi dekorator `@shared_task`. Ini unit pekerjaan |
| **Producer** | Kode Django yang memanggil `task.delay(...)`. Hanya menaruh pesan, tidak menunggu hasil |
| **Broker** | Perantara antrean pesan. Pilihan umum: Redis atau RabbitMQ |
| **Worker** | Proses terpisah yang mengambil pesan dari broker dan menjalankan task |
| **Result backend** | (Opsional) tempat menyimpan hasil atau status task |

Intinya: **web hanya menitipkan pesan, worker yang bekerja**. Web tetap responsif, dan
jumlah worker bisa ditambah tanpa mengubah kode.

### 1.2 Celery Beat: penjadwal

Celery sendiri hanya menjalankan task saat diminta. **Celery Beat** adalah proses
terpisah yang berperan sebagai *jam alarm*: pada waktu yang dijadwalkan (mis. "setiap
hari 07.00" atau "tiap 15 menit"), Beat menaruh pesan task ke broker, lalu worker
mengerjakannya. Ini pengganti cron yang terintegrasi dengan Django.

```
Beat (jadwal) ──"jam 07.00: kirim_pengingat_laporan"──▶ Redis ──▶ Worker
```

Dua cara mendefinisikan jadwal:
- **Statis** di `settings.py` lewat `CELERY_BEAT_SCHEDULE`. Sederhana, ikut versi kode.
- **Dinamis** lewat paket `django-celery-beat`. Jadwal disimpan di database dan bisa
  diubah dari Django Admin tanpa deploy ulang.

**Aturan penting:** hanya boleh ada **satu** proses Beat. Bila dua Beat berjalan, setiap
task terjadwal terkirim dua kali. Worker boleh banyak.

---

## 2. Gambaran kebutuhan

### 2.1 Temuan kondisi project saat ini

Pemeriksaan kode (Oktober 2026):

- Variabel email `MAIL_*` (termasuk `MAIL_DB_QUEUE_ENABLE_WORKER`,
  `MAIL_DB_QUEUE_WORKER_INTERVAL_MS`, `MAIL_DB_QUEUE_MAX_ATTEMPTS`,
  `MAIL_DB_QUEUE_RETRY_DELAY_MS`, `MAIL_DB_QUEUE_LOCK_TTL_MS`) **ada di `.env.example`**.
- Namun **tidak ada kode Python** di project ini yang membaca variabel tersebut. Tidak ada
  `EMAIL_*` di `settings.py`, tidak ada pemakaian `send_mail`, dan tidak ada worker atau
  model antrean email. Jadi antrean berbasis database itu **belum diimplementasikan di
  Django project ini**. Variabelnya kemungkinan sisa dari templat konfigurasi.
- Notifikasi yang berjalan saat ini hanya **in-app** (model `notifications.Notification`).
  Dokumen `SKENARIO_NOTIFIKASI_SURAT.md` menyebut email sebagai target, tetapi belum dibuat.
- Pekerjaan berat saat ini **sinkron di dalam request**: pembuatan PDF Nota Dinas
  (WeasyPrint), export Excel, impor kalender libur, dan pemanggilan integrasi PINTAR.
- Beberapa pekerjaan berkala masih berupa *management command* manual
  (`hitung_ulang_hari_kerja`, `seed_hari_libur`, dan `bersihkan_log` bila fitur Log
  Sistem sudah di-merge). Tidak ada yang menjadwalkannya.

**[Verifikasi]** Konfirmasikan ke mentor: apakah antrean database itu memang direncanakan
ada (dan belum dibuat), atau memang tidak dipakai. Ini memengaruhi apakah Celery
"menggantikan" sesuatu atau "mengisi" kekosongan.

### 2.2 Mengapa Celery + Redis, bukan antrean berbasis database

Pola *DB queue* (tabel antrean di MySQL + worker yang memeriksa tabel secara berkala,
seperti tersirat dari variabel `WORKER_INTERVAL_MS` dan `LOCK_TTL_MS`) bisa dipakai untuk
skala kecil. Namun untuk project ini Celery + Redis lebih baik karena:

| Aspek | DB queue | Celery + Redis |
|---|---|---|
| **Beban database utama** | Worker mengetuk tabel secara berkala (*polling*) dan menulis status baris: tambahan beban baca/tulis pada MySQL yang sama dengan aplikasi | Antrean hidup di Redis (memori). MySQL tidak terbebani oleh urusan antrean |
| **Latensi** | Tergantung interval polling (mis. 15 detik) | Pesan langsung diambil worker, hitungan milidetik |
| **Konkurensi antar worker** | Perlu mekanisme kunci sendiri (*lock* dan TTL) agar satu pekerjaan tidak diambil dua worker | Ditangani Celery/broker (pesan hanya diterima satu worker) |
| **Retry dan backoff** | Ditulis sendiri (hitung percobaan, tunda ulang) | Bawaan: `autoretry_for`, `retry_backoff`, `max_retries` |
| **Penjadwalan** | Tidak ada, perlu cron terpisah | Celery Beat terintegrasi |
| **Skalabilitas** | Menambah worker menambah tekanan ke MySQL | Tambah worker/container tanpa menyentuh MySQL |
| **Pemantauan** | Query manual ke tabel | Alat siap pakai (`celery inspect`, Flower) |
| **Pemisahan tanggung jawab** | Data aplikasi dan antrean bercampur di satu database | Data bisnis di MySQL, pesan sementara di Redis |

Catatan jujur (**[Verifikasi]**):
- Redis sebagai broker menambah satu komponen infrastruktur yang harus dijaga (satu
  container lagi di NAS).
- Pesan di Redis bukan penyimpanan permanen. Bila Redis mati sebelum pesan diproses,
  pesan bisa hilang. Mitigasi: Redis dengan `appendonly yes`, task bersifat *idempotent*,
  dan untuk email penting bisa dipakai pola *outbox* (catat dulu di database, kirim
  lewat task).
- Django 6.x memperkenalkan kerangka `django.tasks` (API standar untuk task latar
  belakang). Layak dibandingkan, tetapi worker produksinya masih bergantung paket
  tambahan, dan Celery menyediakan Beat serta ekosistem yang matang.

---

## 3. Daftar requirements

### 3.1 Library Python (`requirements.txt`)

| Paket | Fungsi | Wajib |
|---|---|---|
| `celery` | Inti: task, worker, dan Beat | Ya |
| `redis` | Klien Python untuk berbicara dengan Redis (transport broker) | Ya |
| `django-celery-beat` | Jadwal Beat yang disimpan di database dan bisa diedit di Django Admin | Opsional |
| `django-celery-results` | Menyimpan hasil/status task di database | Opsional (hanya bila status task perlu ditampilkan ke pengguna) |
| `flower` | Dasbor web untuk memantau worker dan task | Opsional (pemantauan) |

**[Verifikasi]** Versi: gunakan rilis Celery 5.x terbaru yang resmi mendukung Django 6.1
dan Python 3.13 (image Docker project memakai `python:3.13-slim`). Cek catatan rilis
Celery dan `django-celery-beat` sebelum mengunci versi di `requirements.txt` (project
ini memakai versi yang dipin, mis. `Django==6.1.1`).

### 3.2 Infrastruktur

| Komponen | Keterangan |
|---|---|
| **Redis** | Broker pesan. Image resmi `redis` (mis. `redis:7-alpine`), cukup 1 container |
| **Worker** | Container yang menjalankan `celery worker`, memakai **image yang sama** dengan web |
| **Beat** | Container yang menjalankan `celery beat` (tepat 1 instance) |
| **MySQL** | Tetap dipakai aplikasi (tidak berubah). Bila memakai `django-celery-beat`, ada tabel tambahan |

### 3.3 Konfigurasi baru (`.env`)

| Variabel | Contoh | Keterangan |
|---|---|---|
| `CELERY_BROKER_URL` | `redis://redis:6379/0` | Alamat Redis. Di Docker, `redis` adalah nama service |
| `CELERY_TIMEZONE` | `Asia/Jakarta` | Samakan dengan `TIME_ZONE` Django agar jam jadwal Beat benar |

Image Docker yang ada sudah memiliki dependensi sistem untuk WeasyPrint, sehingga worker
yang memakai image yang sama otomatis bisa membuat PDF.

---

## 4. Daftar fitur

Fitur di sistem PASPOR yang idealnya memakai Celery (pemicu: **E** = dipicu kejadian,
**J** = terjadwal oleh Beat):

| # | Fitur | Pemicu | Mengapa cocok untuk Celery |
|---|---|---|---|
| 1 | **Email notifikasi** (pengajuan dikirim, diteruskan, dikembalikan, selesai, laporan PDLN) | E | Kirim SMTP lambat dan bisa gagal; perlu retry. Pengguna tidak boleh menunggu SMTP. Melengkapi notifikasi in-app yang sudah ada (`SKENARIO_NOTIFIKASI_SURAT.md`) |
| 2 | **Rekap data bulanan otomatis** (XLSX rekap pengajuan per unit, dikirim ke Admin PAKLN dan Admin Unor) | J (tiap tanggal 1) | Query dan pembuatan Excel besar; sebaiknya di luar jam kerja |
| 3 | **Pengingat laporan PDLN terlambat** (laporan belum diunggah setelah `BATAS_HARI_LAPORAN` = 14 hari sejak tanggal kembali) | J (harian) | Aturan batas sudah ada di `report.py`. Saat ini hanya tampil sebagai penanda di tabel, belum ada pengingat aktif |
| 4 | **Generate PDF Nota Dinas** (ND Kabag/Karo, terutama bila multi-pengajuan) | E | WeasyPrint berat di CPU/memori dan bisa mendekati batas waktu request |
| 5 | **Sinkronisasi data PINTAR** (pencalonan beasiswa PDLN Tipe 2) | J / E | Panggilan API luar yang lambat atau bisa gagal; kini sinkron dengan timeout 5 detik |
| 6 | **Pembersihan terjadwal** (Log Sistem lama lewat `bersihkan_log`, notifikasi in-app lama, berkas unggahan yatim) | J (mingguan/bulanan) | Command sudah ada atau mudah dibuat; tinggal dijadwalkan |
| 7 | **Hitung ulang hari kerja otomatis** saat kalender libur diubah | E | Perulangan atas banyak draf; sudah ada commandnya (`hitung_ulang_hari_kerja`) |
| 8 | **Pengingat keberangkatan** (mis. H-7 sebelum tanggal berangkat) | J (harian) | Notifikasi proaktif ke pegawai dan admin |
| 9 | **Impor kalender libur skala besar** | E | Validasi dan penyimpanan per baris dapat berjalan di latar belakang |

Saran urutan prioritas pembelajaran: **1 (email)**, lalu **6 (pembersihan)** karena
paling sederhana untuk mencoba Beat, lalu **3 (pengingat laporan)**.

---

## 5. Metode deployment container

### 5.1 Prinsip

- **Satu image, banyak peran.** Web, worker, dan Beat memakai image `paspor-django` yang
  sama. Perbedaannya hanya pada *command* yang dijalankan.
- **Satu proses per container.** Worker dan Beat tidak digabung dalam satu container,
  agar bisa di-restart dan diskalakan terpisah.
- **Hanya web yang menjalankan migrasi.** `docker/entrypoint.sh` saat ini menjalankan
  `migrate` dan `deploy_init` pada setiap start. Worker dan Beat **harus mematikannya**
  lewat `DJANGO_MIGRATE_ON_START=False` dan `DJANGO_INIT_ON_START=False`, kalau tidak,
  tiga container menjalankan migrasi dan seed bersamaan.
- **Beat tepat satu.** Jangan memakai `deploy.replicas` lebih dari 1 untuk Beat.
- **Urutan start:** Redis sehat, web sehat (tabel sudah ada), lalu worker dan Beat.

### 5.2 Contoh `docker-compose.yml`

Berdasarkan `docker-compose.yml` yang ada (service `web`; MySQL dan Garage berjalan di
project lain di NAS). Tambahan: `worker`, `beat`, dan `redis`.

```yaml
x-paspor-app: &paspor-app
  image: paspor-django:latest
  build: .
  env_file: .env
  restart: unless-stopped

x-paspor-env: &paspor-env
  TZ: Asia/Jakarta
  CELERY_BROKER_URL: redis://redis:6379/0

services:
  # --- Aplikasi web (Gunicorn) -------------------------------------------
  web:
    <<: *paspor-app
    container_name: paspor-web
    environment:
      <<: *paspor-env
    ports:
      - "8000:8000"
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/login/', timeout=5)"]
      interval: 30s
      timeout: 10s
      start_period: 60s
      retries: 3

  # --- Worker Celery: mengerjakan task ------------------------------------
  worker:
    <<: *paspor-app
    container_name: paspor-worker
    command: ["celery", "-A", "paspor_project", "worker", "-l", "info", "--concurrency", "2"]
    environment:
      <<: *paspor-env
      DJANGO_MIGRATE_ON_START: "False"   # migrasi hanya oleh service web
      DJANGO_INIT_ON_START: "False"
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

  # --- Celery Beat: penjadwal (TEPAT SATU instance) ------------------------
  beat:
    <<: *paspor-app
    container_name: paspor-beat
    command: ["celery", "-A", "paspor_project", "beat", "-l", "info", "--schedule", "/tmp/celerybeat-schedule"]
    environment:
      <<: *paspor-env
      DJANGO_MIGRATE_ON_START: "False"
      DJANGO_INIT_ON_START: "False"
    depends_on:
      web:
        condition: service_healthy
      redis:
        condition: service_healthy

  # --- Redis: broker pesan -------------------------------------------------
  redis:
    image: redis:7-alpine
    container_name: paspor-redis
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    # Tidak ada "ports": Redis hanya dijangkau antar-container, tidak dibuka ke luar.

volumes:
  redis-data:
```

Penjelasan singkat:

| Bagian | Alasan |
|---|---|
| `command:` pada worker/beat | Menimpa `CMD` Gunicorn dari Dockerfile. `ENTRYPOINT` tetap `entrypoint.sh`, yang tetap menunggu database lalu `exec "$@"` |
| `DJANGO_*_ON_START=False` | Mencegah migrasi dan seed berjalan di worker dan Beat |
| `--concurrency 2` | NAS umumnya terbatas CPU dan RAM. Pembuatan PDF WeasyPrint cukup berat |
| `--schedule /tmp/...` | Image berjalan sebagai user non-root `app`. `/tmp` selalu bisa ditulis. Karena jadwal bersifat statis, file ini boleh hilang saat container dibuat ulang |
| `--appendonly yes` + volume | Pesan antrean bertahan saat Redis restart |
| Tanpa `ports` pada Redis | Mengurangi permukaan serangan |
| `depends_on ... service_healthy` | Menjamin Redis dan tabel database siap sebelum worker/Beat berjalan |

### 5.3 Perintah operasional

```bash
docker compose up -d --build          # bangun dan jalankan semua service
docker compose ps                      # cek status keempat service
docker compose logs -f worker beat     # lihat log worker dan Beat
docker compose up -d --scale worker=2  # tambah worker (Beat tetap 1)
docker compose restart worker          # restart worker setelah ubah kode task
```

Di Synology Container Manager, compose ini dijalankan sebagai *Project* (lihat
`DEPLOY_SYNOLOGY.MD`).

### 5.4 Pengembangan lokal (Windows)

Celery tidak mendukung Windows secara resmi untuk pool bawaan. **[Verifikasi]** Opsi
praktis untuk belajar di laptop:
- Jalankan Redis lewat Docker: `docker run -p 6379:6379 redis:7-alpine`.
- Jalankan worker dengan pool `solo` atau `threads`:
  `celery -A paspor_project worker -l info --pool=solo`.
- Atau jalankan seluruh stack lewat `docker compose` agar identik dengan produksi.

---

## 6. Contoh kode inti

Contoh ini bersifat ilustrasi untuk memahami alurnya (belum ada di project).

**`paspor_project/celery.py`** (aplikasi Celery)

```python
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paspor_project.settings")

app = Celery("paspor_project")
app.config_from_object("django.conf:settings", namespace="CELERY")  # baca setting berawalan CELERY_
app.autodiscover_tasks()  # cari tasks.py di tiap app
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
CELERY_TASK_IGNORE_RESULT = True                 # tidak menyimpan hasil (lebih ringan)
CELERY_TASK_ACKS_LATE = True                     # pesan baru dianggap selesai setelah task sukses
CELERY_WORKER_PREFETCH_MULTIPLIER = 1            # worker tidak menimbun banyak pesan sekaligus
CELERY_TASK_TIME_LIMIT = 300                     # batas keras 5 menit per task
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "pengingat-laporan-pdln": {
        "task": "pengajuan.tasks.kirim_pengingat_laporan_terlambat",
        "schedule": crontab(hour=7, minute=0),                   # tiap hari 07.00 WIB
    },
    "bersihkan-log-lama": {
        "task": "logs.tasks.bersihkan_log_lama",
        "schedule": crontab(hour=2, minute=0, day_of_week="sun"),  # Minggu 02.00
    },
}
```

**Task dan cara memanggilnya** (contoh email notifikasi)

```python
# notifications/tasks.py
from celery import shared_task


@shared_task(autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def kirim_email_notifikasi(notification_id):
    """Kirim email untuk satu Notification. Aman diulang (idempotent)."""
    ...  # ambil Notification by id; bila sudah terkirim, berhenti; kirim; tandai terkirim
```

```python
# di service notifikasi, setelah baris Notification dibuat
from django.db import transaction

transaction.on_commit(lambda: kirim_email_notifikasi.delay(notif.pk))
```

Dua kebiasaan penting:
1. **Kirim ID, bukan objek model**, sebagai argumen task. Data bisa berubah sebelum
   worker mengambilnya, dan objek tidak aman diserialisasi.
2. **Pakai `transaction.on_commit`** saat memanggil `.delay()` dari dalam transaksi
   (project ini banyak memakai `transaction.atomic()` pada perubahan status). Tanpa itu,
   worker bisa berjalan sebelum data tersimpan dan tidak menemukan barisnya.

---

## 7. Rencana tahapan

| Tahap | Isi | Hasil yang bisa dicek |
|---|---|---|
| 0. Belajar | Baca dokumentasi Celery; coba di laptop: Redis via Docker, satu task `add(x, y)`, jalankan worker | Task berjalan dan hasilnya terlihat di log worker |
| 1. Fondasi | Tambah paket, `celery.py`, setting `CELERY_*`; tambah service `redis` dan `worker` di compose | `docker compose ps` sehat; `celery inspect ping` menjawab |
| 2. Task pertama | Email notifikasi (fitur 1), dengan konfigurasi SMTP dari `.env` | Email terkirim setelah pengajuan dikirim, tanpa memperlambat halaman |
| 3. Beat | Tambah service `beat`; jadwalkan pembersihan (fitur 6) dan pengingat laporan (fitur 3) | Task terjadwal muncul di log Beat dan worker |
| 4. Pengerasan | Retry dan batas waktu, pemantauan (Flower atau `inspect`), dokumentasi di `DEPLOY_SYNOLOGY.MD` | Dokumen operasional dan runbook singkat |

---

## 8. Risiko dan catatan penting

- **Satu Beat saja.** Beat ganda menggandakan semua task terjadwal.
- **Task harus idempotent.** Task bisa terkirim dua kali (retry atau Redis restart).
  Rancang agar menjalankannya dua kali tidak merugikan (mis. cek status "sudah dikirim").
- **Redis bukan penyimpanan permanen.** Jangan jadikan Redis satu-satunya catatan
  pekerjaan penting. Data bisnis tetap di MySQL.
- **Migrasi di container.** Pastikan hanya `web` yang menjalankan `migrate` (lihat 5.1).
- **Sumber daya NAS.** Jaga `--concurrency` rendah. Tiap worker membawa Django penuh dan
  library PDF.
- **Kata sandi.** Jangan menulis kredensial SMTP atau Redis di dokumen atau repo. Simpan di
  `.env` (sudah di-*ignore* git).
- **Zona waktu.** Samakan `CELERY_TIMEZONE` dengan `TIME_ZONE` agar jadwal Beat sesuai WIB.
- **Pemantauan.** Tanpa pemantauan, task gagal bisa tidak terlihat. Minimal pantau log
  worker; pertimbangkan Flower.

---

## 9. Referensi

- Dokumentasi Celery: <https://docs.celeryq.dev/>
- Celery dengan Django (*First steps with Django*):
  <https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html>
- Periodic Tasks (Celery Beat):
  <https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html>
- `django-celery-beat`: <https://github.com/celery/django-celery-beat>
- Dokumen terkait di project: `DEPLOY_SYNOLOGY.MD`, `SKENARIO_NOTIFIKASI_SURAT.md`,
  `SYSTEM_LOGGING.MD`
