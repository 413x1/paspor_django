# Deploy PASPOR ke Synology NAS (Container Manager)

> **Cakupan:** menjalankan aplikasi Django PASPOR sebagai container di
> Synology DS725+, memakai MySQL dan Garage (S3) yang sudah berjalan di NAS
> yang sama.

## Daftar Isi

1. [Arsitektur](#1-arsitektur)
2. [Prasyarat](#2-prasyarat)
3. [Ambil Kode ke NAS](#3-ambil-kode-ke-nas)
4. [Buat File `.env` Produksi](#4-buat-file-env-produksi)
5. [Izinkan Container Mengakses MySQL & Garage](#5-izinkan-container-mengakses-mysql--garage)
6. [Build & Jalankan](#6-build--jalankan)
7. [Akun Admin & Data Awal](#7-akun-admin--data-awal)
8. [Update Aplikasi](#8-update-aplikasi)
9. [Akses Lewat Domain HTTPS (Opsional)](#9-akses-lewat-domain-https-opsional)
10. [Troubleshooting](#10-troubleshooting)
11. [Catatan Keamanan](#11-catatan-keamanan)

---

## 1. Arsitektur

```
Browser ──http://10.101.21.55:8000──▶ paspor-web (Gunicorn + Django)
                                          │
                       ┌──────────────────┼───────────────────┐
                       ▼                                      ▼
            MySQL 8.4 (port 3306)                  Garage S3 (port 3900)
            database paspor_db                     bucket paspor-uploads

Browser ──presigned URL──▶ Garage (unduh/pratinjau dokumen langsung)
```

- **Gunicorn** menjalankan Django (3 worker, timeout 120 detik untuk PDF).
- **WhiteNoise** menyajikan file static; tidak perlu nginx terpisah.
- **WeasyPrint** beserta font Liberation (pengganti Times New Roman) sudah
  terpasang di image.
- **Migrasi database** dijalankan otomatis setiap container start.

File terkait di repo:

| File | Fungsi |
|---|---|
| `Dockerfile` | Build image produksi (multi-stage) |
| `docker-compose.yml` | Definisi project untuk Container Manager |
| `docker/entrypoint.sh` | Tunggu DB → `migrate` → jalankan Gunicorn |
| `docker/gunicorn.conf.py` | Konfigurasi Gunicorn |
| `.dockerignore` | Mencegah `.env`, venv, dan media ikut masuk image |

## 2. Prasyarat

- Project **mysql** dan **garage** di Container Manager sudah berjalan.
- Database `paspor_db`, user `paspor_django`, bucket `paspor-uploads`, dan
  key Garage sudah dibuat.
- SSH ke NAS aktif (Control Panel → Terminal & SNMP).
- Paket **Git Server** terpasang dari Package Center (menyediakan perintah
  `git` di NAS).

## 3. Ambil Kode ke NAS

Lewat SSH:

```bash
cd /volume1/docker
sudo git clone -b development https://github.com/413x1/paspor_django.git paspor
```

Kode berada di `/volume1/docker/paspor`.

> Tanpa Git: unduh ZIP branch dari GitHub (Code → Download ZIP), upload ke
> `docker/` lewat File Station, ekstrak, lalu ubah nama foldernya menjadi
> `paspor`. Cara ini membuat update lebih repot (lihat bagian 8).

## 4. Buat File `.env` Produksi

Buat `/volume1/docker/paspor/.env` (file ini di-*ignore* git dan tidak ikut
masuk image):

```env
DJANGO_SECRET_KEY=ISI_DENGAN_HASIL_openssl_rand_-hex_32
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=10.101.21.55,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://10.101.21.55:8000
DJANGO_BEHIND_HTTPS_PROXY=False

DB_NAME=paspor_db
DB_USER=paspor_django
DB_PASSWORD=PASSWORD_DARI_mysql.env
DB_HOST=10.101.21.55
DB_PORT=3306

S3_ACCESS_KEY=GKxxxxxxxxxxxxxxxxxxxxxxxx
S3_SECRET_KEY=SECRET_KEY_GARAGE
S3_BUCKET_NAME=paspor-uploads
S3_ENDPOINT=http://10.101.21.55:3900
S3_REGION_NAME=garage
S3_QUERYSTRING_EXPIRE=3600

DJANGO_MIGRATE_ON_START=True
GUNICORN_WORKERS=3
GUNICORN_TIMEOUT=120

MAIL_ALLOW_SEND=false
```

Aturan penulisan:

- Satu variabel per baris, **tanpa tanda kutip** dan **tanpa komentar** di
  baris yang sama.
- Buat `DJANGO_SECRET_KEY` dengan `openssl rand -hex 32` di SSH NAS.
- `127.0.0.1` wajib ada di `DJANGO_ALLOWED_HOSTS` karena dipakai
  healthcheck container.

Cara membuatnya lewat SSH:

```bash
sudo cp /volume1/docker/paspor/.env.example /volume1/docker/paspor/.env
sudo vi /volume1/docker/paspor/.env
```

Atau tulis di komputer lalu upload ke folder `docker/paspor` lewat File
Station (pastikan namanya persis `.env`).

## 5. Izinkan Container Mengakses MySQL & Garage

Container `paspor-web` menghubungi MySQL dan Garage lewat IP NAS, dengan
alamat sumber dari jaringan Docker (`172.16.0.0/12`), bukan IP NAS.

Jika **Firewall DSM** aktif dan port 3306/3900 dibatasi, tambahkan aturan
**Allow** untuk sumber `172.16.0.0` subnet `255.240.0.0` ke port 3306 dan
3900 (Control Panel → Security → Firewall → Edit Rules). Letakkan di atas
aturan Deny.

## 6. Build & Jalankan

Di **Container Manager → Project → Create**:

1. **Project name:** `paspor`
2. **Path:** `/volume1/docker/paspor`
3. **Source:** pilih *Use existing docker-compose.yml*.
4. Tidak perlu web portal Web Station.
5. **Done** → Container Manager akan build image (pertama kali ±5–10 menit).

Setelah status container **healthy**, buka:

```
http://10.101.21.55:8000
```

Log bisa dilihat di Container Manager → Container → `paspor-web` → Log.
Baris `[entrypoint] Database siap.` dan `Listening at: http://0.0.0.0:8000`
menandakan aplikasi sudah jalan.

## 7. Akun Admin & Data Awal

Lewat SSH (sekali saja untuk database baru):

```bash
sudo docker exec -it paspor-web python manage.py createsuperuser
sudo docker exec -it paspor-web python manage.py seed_hari_libur
```

Perintah seed lain yang tersedia: `seed_admin_unor_org_units`,
`seed_pegawai_org_units`, `seed_demo_data` (jangan jalankan data demo di
produksi kecuali memang dibutuhkan).

Berkas lama di folder `media/` lokal bisa dipindahkan ke bucket dengan
`python manage.py sync_media_to_s3` dari komputer pengembang (lihat
[S3BUCKET_FILE_UPLOAD.MD](S3BUCKET_FILE_UPLOAD.MD)).

## 8. Update Aplikasi

Setelah perubahan di-push ke branch `development`:

```bash
cd /volume1/docker/paspor
sudo git pull
sudo docker compose up -d --build
```

(Jika `docker compose` tidak dikenal, pakai `sudo docker-compose up -d --build`.)

Atau di Container Manager: Project → `paspor` → **Action → Build**.
Migrasi baru dijalankan otomatis saat container start.

## 9. Akses Lewat Domain HTTPS (Opsional)

1. **Control Panel → Login Portal → Advanced → Reverse Proxy → Create**
   - Source: `HTTPS`, hostname `paspor.domainanda.go.id`, port `443`
   - Destination: `HTTP`, `localhost`, port `8000`
   - Custom Header → Create → isi nama `X-Forwarded-Proto` dengan nilai
     `$scheme` (agar Django tahu request aslinya HTTPS)
2. Pasang sertifikat di **Control Panel → Security → Certificate**.
3. Tambahkan ke `.env`, lalu rebuild/restart project:

   ```env
   DJANGO_ALLOWED_HOSTS=paspor.domainanda.go.id,10.101.21.55,localhost,127.0.0.1
   DJANGO_CSRF_TRUSTED_ORIGINS=https://paspor.domainanda.go.id,http://10.101.21.55:8000
   DJANGO_BEHIND_HTTPS_PROXY=True
   ```

> Dengan `DJANGO_BEHIND_HTTPS_PROXY=True`, cookie login hanya dikirim lewat
> HTTPS, sehingga login lewat `http://10.101.21.55:8000` tidak lagi bisa
> dipakai.

Catatan: link unduh dokumen (presigned URL) tetap mengarah ke
`S3_ENDPOINT`. Agar dokumen bisa dibuka dari luar jaringan kantor, Garage
juga perlu diekspos lewat reverse proxy HTTPS dan `S3_ENDPOINT` diganti ke
alamat tersebut.

## 10. Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| Log: `Percobaan x/30 gagal ... Can't connect to MySQL` | MySQL mati, `DB_HOST/DB_PORT` salah, atau firewall memblokir subnet Docker (bagian 5). |
| Log: `Access denied for user` | `DB_USER`/`DB_PASSWORD` tidak cocok dengan user MySQL. |
| `Bad Request (400)` di browser | Host yang dipakai belum ada di `DJANGO_ALLOWED_HOSTS`. |
| `Forbidden (403) CSRF verification failed` | Origin belum ada di `DJANGO_CSRF_TRUSTED_ORIGINS` (harus lengkap dengan `http://` dan port). |
| Tampilan tanpa CSS | Build ulang image; `collectstatic` dijalankan saat build. |
| Upload gagal `403 Forbidden` | Key Garage salah atau belum di-*allow* ke bucket. |
| Container status *unhealthy* | `127.0.0.1` belum ada di `DJANGO_ALLOWED_HOSTS`. |
| `exec /app/docker/entrypoint.sh: no such file or directory` | Line ending CRLF; build ulang (Dockerfile sudah mengonversi otomatis). |
| `413 Request Entity Too Large` lewat reverse proxy | Batas ukuran upload di reverse proxy; aplikasi sendiri membatasi 10 MB. |

## 11. Catatan Keamanan

- **`/upload/` (demo publik)** bisa diakses dan menghapus berkas **tanpa
  login**. Nonaktifkan atau lindungi dengan login sebelum dipakai di
  produksi.
- Jangan pernah commit `.env`.
- `DJANGO_DEBUG` harus `False` di produksi.
- Matikan SSH NAS bila tidak dipakai.
