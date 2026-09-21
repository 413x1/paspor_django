# PASPOR — Django + MySQL

Implementasi aplikasi web dari mockup **PASPOR (Platform Administrasi Surat
Perjalanan Overseas Request)** — Kementerian Pekerjaan Umum, menggunakan
**Django** dan **MySQL**.

Tahap ini mencakup alur **Perjalanan Luar Negeri Non-Kedinasan** dengan 3
role: **Pegawai**, **Admin Unor**, dan **Admin Biro PAKLN**. Alur
**Perjalanan Dinas Luar Negeri (PDLN)** dengan role tambahan **Admin BPSDM**
belum diimplementasikan (menyusul tahap berikutnya — lihat bagian
[Keterbatasan & Rencana Lanjutan](#keterbatasan--rencana-lanjutan)).

> **Catatan:** Kode ini disusun berdasarkan spesifikasi mockup interaktif
> (`PASPOR_Mockup_Tahap1_3_NonKedinasan.html`) dan dokumen panduan
> pengembangan yang telah dibuat sebelumnya. Karena disusun di lingkungan
> tanpa akses internet/Django terpasang, kode **belum pernah dijalankan
> secara langsung** — jalankan langkah verifikasi di bagian
> [Instalasi](#instalasi--menjalankan) untuk memastikan semuanya berjalan
> mulus, dan laporkan bila ada error yang perlu diperbaiki.

---

## 1. Struktur Proyek

```
paspor_django/
├── manage.py
├── requirements.txt
├── .env.example
├── paspor_project/          # Konfigurasi Django (settings, urls, wsgi/asgi)
├── accounts/                 # User kustom (role) + Profil Pegawai
│   ├── models.py             # User(role), PegawaiProfile
│   ├── views.py               # login, logout, redirect sesuai role
│   └── management/commands/seed_demo_data.py
├── pengajuan/                 # Inti alur pengajuan
│   ├── models.py              # Pengajuan, DokumenPegawai/Unor/Pakln
│   ├── decorators.py          # role_required(...)
│   ├── forms.py
│   ├── views_pegawai.py       # Beranda, Formulir, Upload, Monitor
│   ├── views_unor.py          # Dasbor, Pratinjau, Upload, Export
│   ├── views_pakln.py         # Dasbor, Pratinjau, Upload, Export
│   ├── urls_pegawai.py / urls_unor.py / urls_pakln.py
│   └── templatetags/pengajuan_extras.py
├── templates/                 # HTML (base, registration, pegawai, unor, pakln)
├── static/css/style.css       # Tema visual (navy/gold), meniru mockup
└── media/                     # Lokasi unggahan dokumen (dev)
```

## 2. Pemetaan ke Mockup

| Role (mockup) | Django | Halaman |
|---|---|---|
| Pegawai (Mobile/Web) | app `pengajuan`, namespace `pegawai` | Beranda → Formulir Pengajuan → Unggah Dokumen → Monitor Progres |
| Admin Unor | app `pengajuan`, namespace `unor` | Dasbor → Pratinjau Pengajuan → Upload Dok. Administrasi → Export Database |
| Admin Biro PAKLN | app `pengajuan`, namespace `pakln` | Dasbor → Pratinjau Pengajuan → Upload Dok. Administrasi → Manajemen User → Manajemen Template → Export Database |

Siklus status pengajuan (`Pengajuan.status`) identik dengan mockup:

```
belum  →  proses  →  proses_pakln  →  selesai
```

Field boolean `form_saved`, `submitted`, `preview_unor_agree`, dan
`preview_pakln_agree` pada model `Pengajuan` meniru nama field pada state
JavaScript mockup, dan dipakai sebagai syarat unlock halaman berikutnya
(divalidasi di sisi **server**, bukan hanya UI — lihat masing-masing view).

Mode single-page role-switcher pada mockup digantikan alur produksi yang
sesungguhnya: login per akun, redirect otomatis ke beranda/dasbor sesuai
`role` user (lihat `accounts.views.role_redirect`).

## 3. Prasyarat

- Python 3.10+
- MySQL Server 8.x (atau MariaDB 10.6+) yang sudah berjalan
- Build tools untuk `mysqlclient`:
  - **Ubuntu/Debian:** `sudo apt install python3-dev default-libmysqlclient-dev build-essential pkg-config`
  - **macOS (Homebrew):** `brew install mysql pkg-config`
  - **Windows:** disarankan pakai WSL2, atau gunakan wheel prebuilt `mysqlclient` dari PyPI (biasanya tersedia otomatis via `pip install`).

## 4. Instalasi & Menjalankan

```bash
# 1) Masuk ke folder proyek & buat virtual environment
cd paspor_django
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Siapkan database MySQL
mysql -u root -p
```
```sql
CREATE DATABASE paspor_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'paspor_user'@'localhost' IDENTIFIED BY 'paspor_password';
GRANT ALL PRIVILEGES ON paspor_db.* TO 'paspor_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

```bash
# 4) Konfigurasi environment variable
cp .env.example .env
# lalu edit .env sesuai kredensial MySQL Anda, atau export manual:
export DB_NAME=paspor_db
export DB_USER=paspor_user
export DB_PASSWORD=paspor_password
export DB_HOST=127.0.0.1
export DB_PORT=3306
export DJANGO_SECRET_KEY="ganti-dengan-random-string-panjang"

# 5) Verifikasi konfigurasi Django (jalankan ini pertama kali untuk
#    menangkap error import/konfigurasi sebelum migrate)
python manage.py check

# 6) Migrasi database
python manage.py makemigrations accounts pengajuan
python manage.py migrate

# 7) (Opsional) Buat akun admin Django (akses /admin/)
python manage.py createsuperuser

# 8) Buat akun & data demo (meniru data dummy pada mockup)
python manage.py seed_demo_data

# 8b) (Opsional) Buat 3 akun Pegawai untuk tiap unit organisasi (org_units)
python manage.py seed_pegawai_org_units

# 8c) (Opsional) Buat 1 akun Admin Unor untuk tiap unit organisasi (org_units)
python manage.py seed_admin_unor_org_units

# 9) Jalankan development server
python manage.py runserver
```

Buka `http://127.0.0.1:8000/` — Anda akan diarahkan ke halaman login.

### Akun demo (dibuat oleh `seed_demo_data`)

| Username | Password | Role |
|---|---|---|
| `andra.wibisono` | `paspor123` | Pegawai |
| `admin.unor` | `paspor123` | Admin Unor |
| `admin.pakln` | `paspor123` | Admin Biro PAKLN |

> Ganti seluruh password demo ini sebelum digunakan di lingkungan
> staging/produksi.

### Akun Pegawai per unit organisasi (dibuat oleh `seed_pegawai_org_units`)

Untuk tiap baris pada `org_units` (lihat [UNIT_ORGANISASI.MD](tables/UNIT_ORGANISASI.MD)),
dibuat 3 akun Pegawai dengan skema:

- Username: `pegawai.<alias(lower)><1|2|3>` (mis. `pegawai.djsda1`, `pegawai.djsda2`, `pegawai.djsda3`)
- Password: `paspor123` (sama untuk semua)

Perintah ini idempoten (`get_or_create`/`update_or_create`) dan aman dijalankan berulang.

### Akun Admin Unor per unit organisasi (dibuat oleh `seed_admin_unor_org_units`)

Untuk tiap baris pada `org_units`, dibuat 1 akun Admin Unor dengan skema:

- Username: `admin.unor.<alias(lower)>` (mis. `admin.unor.djsda`)
- Password: `paspor123` (sama untuk semua)

Idempoten, aman dijalankan berulang.

## 5. Alur Pengujian Manual (End-to-End)

1. Login sebagai **andra.wibisono** → Beranda → **Tambah Usulan Baru** →
   isi Formulir Pengajuan → Simpan & Lanjutkan.
2. Di halaman Unggah Dokumen, unggah keempat jenis dokumen (bisa file apa
   saja untuk pengujian) → centang pernyataan → **Kirim ke Admin Unor**.
3. Logout, login sebagai **admin.unor** → pengajuan baru akan muncul di
   Dasbor berstatus *Proses* → klik **TL →** → Pratinjau → centang &
   **Lanjutkan** → unggah 5 dokumen administrasi Unor → **Teruskan ke
   Biro PAKLN**.
4. Logout, login sebagai **admin.pakln** → pengajuan muncul berstatus
   *Dalam Proses Biro PAKLN* → ulangi pola pratinjau + unggah 3 dokumen →
   **Selesaikan Proses**.
5. Logout, login kembali sebagai **andra.wibisono** → buka Monitor
   Progres → status akhir harus **Selesai**.

## 6. Keterbatasan & Rencana Lanjutan

Sama seperti dicatat pada dokumen panduan pengembangan sebelumnya, hal-hal
berikut **belum** termasuk dalam implementasi ini dan perlu dirancang pada
tahap berikutnya:

- **Alur PDLN** (Perjalanan Dinas Luar Negeri) dengan role tambahan
  **Admin BPSDM**.
- **Integrasi database kepegawaian** sungguhan — saat ini `PegawaiProfile`
  diisi manual/lewat `seed_demo_data`, bukan ditarik otomatis dari sistem
  kepegawaian Kementerian PU.
- **SSO / autentikasi terintegrasi** dengan akun Satu Bravo — saat ini
  memakai autentikasi bawaan Django (username/password).
- **Notifikasi** (email/push) pada setiap perpindahan status.
- **Generate dokumen otomatis** (mis. Formulir Izin Luar Negeri dari data
  pengajuan) — saat ini seluruh dokumen diunggah manual sebagai file.
- **Export Excel** sesungguhnya — saat ini export berupa **CSV** (via
  tombol "Export CSV"); pertimbangkan `openpyxl` bila format `.xlsx`
  sungguhan diperlukan.
- **Penyimpanan file produksi**: konfigurasi `MEDIA_ROOT` saat ini untuk
  pengembangan lokal. Untuk produksi, arahkan ke object storage (S3-
  compatible) via storage backend seperti `django-storages`.
- **Halaman error kustom** (403/404/500) belum dibuat — saat ini memakai
  halaman bawaan Django.
- Belum ada test otomatis (`pytest`/`unittest`) — disarankan ditambahkan
  sebelum masuk tahap produksi.

## 7. Production Checklist (ringkas)

Sebelum deploy ke produksi, minimal:

- Set `DJANGO_DEBUG=False` dan isi `DJANGO_ALLOWED_HOSTS` dengan domain asli.
- Ganti `DJANGO_SECRET_KEY` dengan nilai acak & rahasia (jangan commit ke git).
- Jalankan `python manage.py collectstatic` dan sajikan static file via
  Nginx/WhiteNoise, bukan Django dev server.
- Gunakan WSGI server produksi (Gunicorn/uWSGI) di belakang Nginx.
- Aktifkan HTTPS (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE`, dsb.).
- Pertimbangkan storage backend eksternal untuk `MEDIA_ROOT`.
