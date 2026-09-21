# Panduan Instalasi & Pengembangan — PASPOR

Panduan lengkap untuk menyiapkan lingkungan pengembangan lokal aplikasi
**PASPOR** (Django + MySQL + MinIO), dari instalasi awal hingga mengisi
database dengan data seed/demo. Untuk gambaran arsitektur & struktur
proyek, lihat [wiki/README.md](README.md).

---

## 1. Prasyarat

| Kebutuhan | Versi | Keterangan |
|---|---|---|
| Python | 3.10+ | Cek dengan `python --version` |
| MySQL / MariaDB | MySQL 8.x atau MariaDB 10.6+ | Harus sudah berjalan sebelum `migrate` |
| MinIO | terbaru | Object storage untuk fitur unggah berkas (app `fileupload`). Tidak wajib untuk `runserver`/`migrate`, tapi wajib untuk mengunggah dokumen |
| Build tools `mysqlclient` | — | Ubuntu/Debian: `sudo apt install python3-dev default-libmysqlclient-dev build-essential pkg-config`. macOS: `brew install mysql pkg-config`. Windows: wheel prebuilt biasanya otomatis lewat `pip install`, jika gagal gunakan WSL2 |

---

## 2. Clone & Virtual Environment

```powershell
cd D:\Labs\paspor_django
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS
```

## 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

> **Catatan encoding:** `requirements.txt` tersimpan sebagai UTF-16. Jika
> menambah/mengubah dependency dengan editor yang menyimpan ulang sebagai
> UTF-8 secara otomatis, itu tidak masalah — `pip` membaca keduanya. Yang
> perlu dihindari adalah karakter/format rusak akibat copy-paste antar
> encoding.

Isi utama `requirements.txt`: `Django==6.1.1`, `mysqlclient` (driver MySQL),
`minio` (klien object storage), `argon2-cffi`/`pycryptodome` (hashing &
kripto pendukung).

## 4. Siapkan Database MySQL

```sql
mysql -u root -p
```
```sql
CREATE DATABASE paspor_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'paspor_user'@'localhost' IDENTIFIED BY 'paspor_password';
GRANT ALL PRIVILEGES ON paspor_db.* TO 'paspor_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Sesuaikan nama database/user/password bila berbeda — nilainya dibaca dari
environment variable pada langkah berikutnya (lihat `paspor_project/settings.py`
bagian `DATABASES`).

## 5. Siapkan MinIO (untuk fitur unggah dokumen)

Aplikasi membaca konfigurasi MinIO lewat env var (`MINIO_ENDPOINT`,
`MINIO_PORT`, dst. — lihat `settings.py`). Jalankan MinIO lokal dengan Docker:

```powershell
docker run -d --name paspor-minio `
  -p 9000:9000 -p 9001:9001 `
  -e MINIO_ROOT_USER=minioadmin `
  -e MINIO_ROOT_PASSWORD=minioadmin `
  -v paspor_minio_data:/data `
  minio/minio server /data --console-address ":9001"
```

Buka console di `http://localhost:9001` (login `minioadmin`/`minioadmin`)
dan buat bucket sesuai nilai `MINIO_BUCKET_NAME` di `.env` — atau biarkan
kosong, karena `fileupload.minio_client.ensure_bucket()` akan membuat
bucket otomatis saat unggahan pertama kali dilakukan.

Tanpa MinIO berjalan, seluruh aplikasi tetap bisa di-`migrate`, di-seed, dan
dijalankan — hanya alur **unggah/lihat/hapus dokumen** (app `fileupload`,
dipakai di halaman Upload Dokumen Pegawai/Unor/PAKLN) yang akan gagal
dengan error koneksi. Detail mekanismenya ada di
[wiki/UPLOAD_FILE.MD](UPLOAD_FILE.MD).

## 6. Konfigurasi Environment Variable

```powershell
copy .env.example .env
```

Edit `.env` sesuai kredensial MySQL & MinIO Anda:

```env
DJANGO_SECRET_KEY=ganti-dengan-secret-key-acak-yang-panjang
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=paspor_db
DB_USER=paspor_user
DB_PASSWORD=paspor_password
DB_HOST=127.0.0.1
DB_PORT=3306

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BUCKET_NAME=paspor-dev
MINIO_ENDPOINT=localhost
MINIO_PORT=9000
MINIO_USE_SSL=false
```

> Proyek ini membaca env var langsung lewat `os.environ` (helper `env()` di
> `settings.py`) — **tidak** ada auto-load `.env` bawaan. Di Windows,
> pastikan variabel benar-benar ter-set di sesi terminal Anda (mis. lewat
> `python-decouple`/`django-environ`, atau `set` manual per variabel)
> sebelum menjalankan `manage.py`.

## 7. Verifikasi, Migrasi, dan Superuser

```powershell
# Tangkap error import/konfigurasi lebih awal sebelum migrate
python manage.py check

# Migrasi database (buat migrations baru dulu jika belum ada)
python manage.py makemigrations accounts pengajuan
python manage.py migrate

# (Opsional) akun admin Django untuk akses /admin/
python manage.py createsuperuser
```

## 8. Menjalankan Development Server

```powershell
python manage.py runserver
```

Buka `http://127.0.0.1:8000/` — akan diarahkan ke halaman login.

---

## 9. Seed Data

Ada 3 management command untuk mengisi data awal/demo, semuanya **idempoten**
(pakai `get_or_create`/`update_or_create`) sehingga aman dijalankan berulang
kali tanpa membuat duplikat.

### 9.1 `seed_demo_data` — wajib dijalankan pertama

```powershell
python manage.py seed_demo_data
```

Membuat:
- 11 baris **`org_units`** (unit eselon I Kementerian PU — Setjen, Itjen,
  DJSDA, dst.), lihat referensi di
  [wiki/tables/UNIT_ORGANISASI.MD](tables/UNIT_ORGANISASI.MD).
- 3 akun demo (password sama untuk semua: **`paspor123`**):

  | Username | Role | Catatan |
  |---|---|---|
  | `andra.wibisono` | Pegawai | unit organisasi DJSDA, punya `PegawaiProfile` lengkap |
  | `admin.unor` | Admin Unor | mengelola unit organisasi yang sama dengan `andra.wibisono` |
  | `admin.pakln` | Admin Biro PAKLN | — |

- 2 contoh riwayat `Pengajuan` berstatus **Selesai** milik `andra.wibisono`
  (kategori Ibadah & Keperluan Pribadi), untuk mengisi tampilan Monitor
  Progres/Dasbor tanpa perlu mengisi form dari nol.

Perintah lain (§9.2, §9.3) bergantung pada `org_units` yang dibuat di sini
— jalankan `seed_demo_data` dulu, atau perintah tersebut akan berhenti
dengan pesan error "Tabel org_units kosong".

### 9.2 `seed_pegawai_org_units` — opsional

```powershell
python manage.py seed_pegawai_org_units
```

Membuat **3 akun Pegawai** untuk **setiap** unit organisasi (11 unit × 3 =
33 akun), berguna untuk menguji tampilan Dasbor Admin Unor/PAKLN dengan
banyak pengajuan dari berbagai unit.

- Username: `pegawai.<alias(lower)><1|2|3>` — mis. `pegawai.djsda1`,
  `pegawai.djsda2`, `pegawai.djsda3`
- Password: `paspor123` (sama untuk semua)
- Tiap akun otomatis punya `PegawaiProfile` (NIP dummy, jabatan "Staf
  Pelaksana", pangkat/golongan bervariasi III-a/III-c/III-d).

### 9.3 `seed_admin_unor_org_units` — opsional

```powershell
python manage.py seed_admin_unor_org_units
```

Membuat **1 akun Admin Unor** untuk **setiap** unit organisasi (11 akun) —
berguna untuk menguji alur multi-Admin Unor (tiap unit punya admin
sendiri, bukan berbagi satu akun `admin.unor` seperti di §9.1).

- Username: `admin.unor.<alias(lower)>` — mis. `admin.unor.djsda`,
  `admin.unor.setjen`
- Password: `paspor123` (sama untuk semua)

### Urutan yang disarankan

```powershell
python manage.py migrate
python manage.py seed_demo_data              # wajib — buat org_units + akun inti
python manage.py seed_pegawai_org_units       # opsional — 33 akun pegawai per unit
python manage.py seed_admin_unor_org_units    # opsional — 11 akun admin unor per unit
```

> **Reset data seed:** command ini tidak menghapus data lama. Untuk mulai
> ulang dari kosong di lingkungan dev, hapus database lalu ulangi dari
> langkah §4 (`DROP DATABASE paspor_db;` → buat ulang → `migrate` → seed),
> atau hapus baris terkait secara manual lewat `/admin/` atau shell
> (`python manage.py shell`).

---

## 10. Alur Pengujian Manual (End-to-End)

Setelah seed data (§9.1) dan MinIO (§5) siap, verifikasi alur inti:

1. Login sebagai **`andra.wibisono`** (`paspor123`) → Beranda → **Tambah
   Usulan Baru** → isi Formulir Pengajuan → Simpan & Lanjutkan.
2. Di halaman Unggah Dokumen, unggah keempat jenis dokumen (file apa saja
   untuk pengujian) → centang pernyataan → **Kirim ke Admin Unor**.
3. Logout, login sebagai **`admin.unor`** → pengajuan baru muncul di
   Dasbor berstatus *Proses* → klik **TL →** → Pratinjau → centang &
   **Lanjutkan** → unggah 5 dokumen administrasi Unor → **Teruskan ke
   Biro PAKLN**.
4. Logout, login sebagai **`admin.pakln`** → pengajuan berstatus *Dalam
   Proses Biro PAKLN* → ulangi pola pratinjau + unggah 3 dokumen →
   **Selesaikan Proses**.
5. Logout, login kembali sebagai **`andra.wibisono`** → buka Monitor
   Progres → status akhir harus **Selesai**.

Jika langkah unggah dokumen gagal dengan error koneksi, cek kembali MinIO
(§5) sudah berjalan dan variabel `MINIO_*` di `.env` sudah benar.

---

## 11. Troubleshooting Singkat

| Gejala | Kemungkinan Penyebab |
|---|---|
| `django.db.utils.OperationalError` saat `migrate`/`runserver` | MySQL belum berjalan, atau `DB_*` di `.env`/env var tidak sesuai |
| Gagal build `mysqlclient` saat `pip install` | Build tools belum terpasang (lihat §1); di Windows coba WSL2 bila wheel prebuilt tidak tersedia |
| Error koneksi saat mengunggah dokumen | MinIO belum berjalan, atau `MINIO_ENDPOINT`/`MINIO_PORT` salah |
| `ValueError: MINIO_BUCKET_NAME belum dikonfigurasi` | `MINIO_BUCKET_NAME` kosong di `.env` |
| `seed_pegawai_org_units`/`seed_admin_unor_org_units` gagal: "Tabel org_units kosong" | Jalankan `python manage.py seed_demo_data` terlebih dahulu |

---

## 12. Referensi Lanjutan

- [wiki/README.md](README.md) — struktur proyek, pemetaan mockup ↔ Django, keterbatasan & rencana lanjutan, production checklist.
- [wiki/UPLOAD_FILE.MD](UPLOAD_FILE.MD) — mekanisme unggah/lihat/hapus dokumen berbasis MinIO.
- [wiki/tables/UNIT_ORGANISASI.MD](tables/UNIT_ORGANISASI.MD) — daftar `org_units` yang dipakai seed data.
- [wiki/instructions/](instructions/) — catatan kebutuhan seed/fitur tambahan (mis. `PEGAWAI_SEEDS.md`).
