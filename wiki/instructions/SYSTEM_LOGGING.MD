# Log Sistem (Activity Log)

Dokumen rancangan fitur **Log Sistem**: pencatatan aktivitas tiap pengguna
pada sistem PASPOR (alur Non-Dinas dan PDLN), halaman monitoring untuk Admin
Biro PAKLN, dan mekanisme reset log.

> **Status:** sudah diimplementasi (app `logs`): model `ActivityLog`, `record_activity`, dekorator
> `@log_aktivitas`, signal login/logout/login gagal, pencatatan di view utama (lihat 2.3), command
> `bersihkan_log`, halaman monitoring + endpoint DataTables, tombol Reset Log, dan konfigurasi `LOGGING`.

## 1. Tujuan dan ruang lingkup

Sistem mencatat **siapa** melakukan **apa**, **hasilnya**, **kapan**, dan
**menggunakan apa** (IP dan User-Agent).

| Pertanyaan | Kolom |
|---|---|
| Siapa | `user`, `username`, `role` |
| Melakukan apa | `aktivitas`, `deskripsi`, `target_type`, `target_id` |
| Hasil aktivitas | `status`, `detail` |
| Kapan | `timestamp` |
| Menggunakan apa | `ip_address`, `user_agent`, `request_method`, `request_path` |

Di luar ruang lingkup: Celery, notifikasi real-time, dan pencatatan isi berkas
atau kata sandi.

## 2. Pendekatan logging

Dua lapis, dengan tugas berbeda:

| Lapis | Alat | Isi | Penyimpanan |
|---|---|---|---|
| Log aktivitas (audit) | Model `ActivityLog` | Aktivitas pengguna yang bisa dicari di UI | Database |
| Log teknis | Modul `logging` Django (`LOGGING` di `settings.py`) | Error dan peringatan sistem | File |

Pencatatan aktivitas dilakukan dengan **pemanggilan fungsi utilitas** atau
**decorator** di dalam view (tanpa middleware yang mencatat semua request).
Alasannya, nama aktivitas harus bermakna ("Mengirim pengajuan ke Unor"), bukan
sekadar URL.

### 2.1 Fungsi utilitas

Lokasi usulan: `logs/utils.py`.

```python
record_activity(request, aktivitas, deskripsi="", *, status="success",
                target_type="", target_id="", detail="", username="", user=None)
```

- `request`: sumber `user`, IP, User-Agent, method, dan path.
- `aktivitas`: kode dari katalog (lihat 2.3).
- `deskripsi`: kalimat yang tampil di tabel, mis.
  "Mengirim pengajuan PLN01-071026-001 ke Admin Unor".
- `target_type` dan `target_id`: objek terkait (mis. `pengajuan` dan kode
  pengajuan).
- `username`: dipakai bila belum ada pengguna login (mis. login gagal).
- `user`: menyebut pengguna secara eksplisit (mis. dari signal login/logout). Bila
  kosong, dipakai `request.user`.
- `status`: `success` atau `failed`.
- `detail`: teks atau dict kecil, mis. alasan gagal.

Aturan wajib:
1. **Pencatatan tidak boleh menggagalkan request.** Seluruh isi fungsi
   dibungkus `try/except`. Bila gagal, tulis ke log teknis (`logger.exception`)
   dan lanjutkan.
2. **Jangan mencatat data sensitif:** kata sandi, token, CSRF, isi berkas, dan
   isi formulir lengkap.
3. `user_agent` dipotong maksimal 512 karakter, dan `detail` maksimal 1000.

### 2.2 Decorator

```python
@log_aktivitas("pengajuan.kirim", "Mengirim pengajuan")
def view_...(request, ...):
```

Dipakai untuk view sederhana. Hasil ditentukan dari response:
- Status HTTP di bawah 400 (termasuk redirect) dicatat `success`.
- Status 400 ke atas, atau exception, dicatat `failed`.

Untuk view form yang menampilkan ulang halaman (status 200) saat validasi gagal,
pakai `sukses_redirect=True`: hanya response redirect (3xx) yang dicatat `success`,
response 200 dicatat `failed` dengan detail "Validasi formulir gagal".
Hanya request ber-method `methods` (bawaan `POST`) yang dicatat, jadi membuka
halaman (GET) tidak menambah log. Letakkan dekorator **di bawah** `@role_required`
dan `@require_POST`, agar hanya akses yang sah yang tercatat.

Untuk view dengan beberapa hasil berbeda (mis. kirim pengajuan), panggil
`record_activity` langsung di dalam view.

### 2.3 Katalog aktivitas (awal)

| Kode | Deskripsi | Pencatatan |
|---|---|---|
| `auth.login` | Login berhasil | Signal `user_logged_in` |
| `auth.login_failed` | Login gagal | Signal `user_login_failed` |
| `auth.logout` | Logout | Signal `user_logged_out` |
| `pengajuan.simpan_formulir` | Menyimpan formulir pengajuan | View pegawai |
| `pengajuan.kirim` | Mengirim pengajuan | View pegawai dan Unor |
| `pengajuan.teruskan` | Meneruskan ke tahap berikutnya | View Unor |
| `pengajuan.kembalikan` | Mengembalikan untuk diperbaiki | View Unor dan PAKLN |
| `pengajuan.selesai` | Menyelesaikan pengajuan | View PAKLN |
| `dokumen.unggah` | Mengunggah dokumen | Semua role |
| `dokumen.hapus` | Menghapus dokumen | Semua role |
| `dokumen.generate_nd` | Generate atau unduh ND Kabag/Karo | View PAKLN |
| `master.ubah` | Mengubah data master (negara, kategori, template, setting) | View PAKLN |
| `log.reset` | Reset Log | View reset |

Katalog ini dikelola sebagai `TextChoices` (`ActivityLog.Aktivitas`) agar dropdown
filter di halaman monitoring otomatis ikut. Kode `pengajuan.proses` dipakai sebagai
cadangan untuk transisi status yang belum punya kode sendiri.

**Titik pemasangan (implementasi):**

| Aktivitas | Dipasang di |
|---|---|
| `auth.*` | `logs/signals.py` (signal Django) |
| `pengajuan.simpan_formulir` | `views_pegawai.formulir_pengajuan` dan `_formulir_pdln` (berhasil dan gagal validasi) |
| `pengajuan.kirim/teruskan/kembalikan/selesai` | `logs.utils.catat_riwayat(...)` tepat setelah tiap `riwayat.catat(...)` di view Pegawai, Unor, BPSDM, dan PAKLN, sehingga selalu sejalan dengan Riwayat Pemrosesan |
| `dokumen.unggah/hapus` | `pengajuan/tahap.py` (`proses_unggah`, `hapus`) dan dokumen pendukung di view Unor dan PAKLN |
| `dokumen.generate_nd` | `views_pakln._simpan_log_generate` |
| `master.ubah` | Dekorator `@log_aktivitas` pada view Manajemen PAKLN (user, template, negara, kalender, sumber pembiayaan, kategori, setting dokumen); impor kalender dicatat langsung di view |
| `log.reset` | Command `bersihkan_log` |

Isi catatan (alasan pengembalian) tidak disalin ke Log Sistem, cukup di Riwayat
Pemrosesan. Pada validasi gagal, hanya **nama field** yang dicatat, tidak pernah nilainya.

### 2.4 Mengambil IP

Secara bawaan IP = `request.META["REMOTE_ADDR"]`. Bila aplikasi berjalan di
belakang reverse proxy (mis. Synology), baca `X-Forwarded-For` **hanya** jika
proxy tersebut tepercaya. Bila tidak, header ini bisa dipalsukan pengguna.
Dikendalikan setting `ACTIVITY_LOG_TRUST_PROXY` (bawaan `False`, bisa diisi lewat
`.env`). Penjelasan operasional ada di `DEPLOY_SYNOLOGY.MD` bagian 12.

### 2.5 Log teknis (file)

Konfigurasi `LOGGING` di `settings.py`: logger `logs`, `pengajuan`, dan
`django.request` ditulis ke konsol dan file `paspor.log` (RotatingFileHandler, 5 MB x 5)
di `LOG_DIR` (bawaan `var/log/`, bisa diubah lewat `.env`). Bila folder tidak bisa
dibuat, log hanya ke konsol. Kegagalan `record_activity` ditulis ke log ini.

## 3. Skema database: model `ActivityLog`

Lokasi usulan: app baru `logs` (tabel `logs_activitylog`). App perlu
didaftarkan di `INSTALLED_APPS`.

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | BigAutoField | PK |
| `user` | FK ke `accounts.User`, `null=True`, `blank=True`, `on_delete=SET_NULL` | Kosong untuk pengguna anonim; baris tetap ada walau akun dihapus |
| `username` | CharField(150), `blank=True` | Snapshot, tetap terbaca bila user dihapus; kosong pada login gagal tanpa akun |
| `role` | CharField(30), `blank=True` | Snapshot role saat aksi dilakukan |
| `aktivitas` | CharField(50) | Kode dari katalog 2.3 (tanpa `choices` di field, agar kode baru tidak perlu migrasi) |
| `deskripsi` | CharField(255), `blank=True` | Kalimat aktivitas yang tampil di tabel |
| `target_type` | CharField(50), `blank=True` | Mis. `pengajuan`, `dokumen` |
| `target_id` | CharField(100), `blank=True` | Mis. kode pengajuan |
| `status` | CharField(10), `choices` | `success` / `failed` (bawaan `success`) |
| `detail` | TextField, `blank=True` | Hasil atau alasan gagal (maks. 1000 karakter) |
| `ip_address` | GenericIPAddressField, `null=True` | |
| `user_agent` | TextField, `blank=True` | Dipotong 512 karakter oleh `record_activity` |
| `request_method` | CharField(10), `blank=True` | |
| `request_path` | CharField(255), `blank=True` | Tanpa query string |
| `timestamp` | DateTimeField, `auto_now_add` | Waktu kejadian |

**Index** (untuk tabel besar):
- `(timestamp)`: urutan bawaan dan filter rentang tanggal.
- `(aktivitas, timestamp)`.
- `(status, timestamp)`.
- `(user, timestamp)`.

**Aturan model:**
- Baris log **tidak boleh diedit**. Tidak ada view update, dan di Django Admin
  didaftarkan read-only.
- `Meta.ordering = ["-timestamp"]`.
- Migrasi hanya menambah tabel baru, tidak menyentuh tabel yang sudah ada.

## 4. Halaman monitoring

### 4.1 Rute

Semua di bawah `/admin-biropakln/` (namespace `pakln`), dilindungi
`@role_required("admin_pakln")`. Rute statis ditaruh **sebelum** pola
`<str:kode>/...` di `pengajuan/urls_pakln.py`.

| Rute | Nama | Method | Fungsi |
|---|---|---|---|
| `log-sistem/` | `pakln:log_sistem` | GET | Halaman monitoring (HTML) |
| `log-sistem/data/` | `pakln:log_sistem_data` | GET | Endpoint JSON DataTables |
| `log-sistem/reset/` | `pakln:log_sistem_reset` | POST | Menjalankan reset log |

Menu baru "Log Sistem" ditambahkan di `templates/partials/_sidebar.html`
hanya untuk role `admin_pakln`.

### 4.2 View halaman

Merender `pakln/log_sistem.html` dengan:
- Dropdown filter: aktivitas (dari katalog) dan status.
- Input filter: tanggal dari dan sampai, serta nama pengguna.
- Tabel kosong yang diisi DataTables.
- Tombol "Reset Log" dengan modal konfirmasi.

### 4.3 Endpoint DataTables (server-side)

Memakai protokol DataTables 2.x (`serverSide: true`) dengan pola yang sama seperti
endpoint dasbor lain. Endpoint ditulis sendiri (`logs/views.py`), tidak memakai
`report.datatable(...)`, karena helper itu mengurutkan sekunder berdasarkan
`created_at` milik `Pengajuan`, sedangkan `ActivityLog` memakai `timestamp`.

**Parameter yang dibaca:**

| Parameter | Fungsi |
|---|---|
| `draw`, `start`, `length` | Paginasi (`length` dibatasi maksimal 100) |
| `search[value]` | Cari di `username`, `deskripsi`, `target_id`, `ip_address` |
| `order[0][column]`, `order[0][dir]` | Urutan, dipetakan lewat whitelist kolom |
| `tgl_dari`, `tgl_sampai` | Filter rentang `timestamp` |
| `aktivitas`, `status`, `pengguna` | Filter tambahan dari form di atas tabel |

**Respons JSON:** `{draw, recordsTotal, recordsFiltered, data: [...]}`.

**Kolom tabel:**

| # | Kolom | Sumber | Urut |
|---|---|---|---|
| 0 | Waktu | `timestamp` | Ya (bawaan: terbaru dulu) |
| 1 | Pengguna | `username` + `role` | Ya |
| 2 | Aktivitas | `deskripsi` | Tidak |
| 3 | Objek | `target_id` | Tidak |
| 4 | Hasil | `status` (tag hijau/merah) + `detail` | Ya |
| 5 | IP | `ip_address` | Tidak |
| 6 | Perangkat | ringkasan `user_agent` (browser/OS) | Tidak |

**Keamanan dan performa:**
- Semua isi sel di-escape (`escape` / `format_html`). `user_agent`, `path`,
  dan `detail` berasal dari pengguna dan rawan XSS.
- Kolom urutan hanya dari whitelist, tidak menerima nama kolom bebas.
- `select_related("user")` dan filter tanggal memakai index.
- Jumlah baris per halaman maksimal 100.

### 4.4 Frontend

- Bulma (tabel, form filter, tag status) dan jQuery. Tidak ada library lain.
- DataTables 2.x vendored (`static/vendors/datatables/`), pola sama dengan tabel
  Riwayat di Beranda Pegawai.
- Filter memicu `table.ajax.reload()`, dan nilainya dikirim lewat
  `ajax.data`.
- Bahasa antarmuka DataTables diindonesiakan.

## 5. Mekanisme Reset Log

Logika pembersihan ada di **management command**. Tombol di halaman hanya
memanggil command itu lewat `call_command`. Tidak menggunakan Celery.

### 5.1 Management command `bersihkan_log`

Lokasi: `logs/management/commands/bersihkan_log.py`.

| Opsi | Fungsi |
|---|---|
| `--hari N` | Hapus log yang lebih lama dari N hari |
| `--semua` | Hapus seluruh log |
| `--dry-run` | Hanya hitung dan tampilkan jumlah, tanpa menghapus |
| `--batch-size N` | Ukuran hapus per batch (bawaan 5000) |
| `--oleh USERNAME` | Pelaku, dicatat pada entri audit reset |

Aturan:
1. Salah satu dari `--hari` atau `--semua` **wajib**. Tanpa keduanya, command
   menolak berjalan (mencegah hapus tidak sengaja).
2. Penghapusan dilakukan **per batch** (hapus berdasarkan rentang `id`), supaya
   tabel besar tidak terkunci lama.
3. Setelah selesai, command menulis **satu entri baru** `log.reset`: siapa
   pelakunya, kriteria, dan jumlah baris yang dihapus. Entri ini tidak ikut
   terhapus.
4. Keluaran command: satu baris `Dihapus: N baris (...) dalam X detik.` Format ini dibaca oleh
   view reset untuk menampilkan jumlah, jadi tidak boleh diubah sembarangan.
5. Entri audit `log.reset` mencatat `username` pelaku (dan akunnya bila ada), tetapi tidak
   mencatat IP, karena command tidak memiliki `request`.

### 5.2 Tombol "Reset Log" di halaman monitoring

- Tombol membuka **modal** berisi pilihan rentang. Saat form dikirim, muncul
  **dialog konfirmasi** (atribut `data-confirm` yang sudah ada di `base.html`)
  sebelum penghapusan benar-benar dijalankan.
- Pilihan di modal:
  - Lebih lama dari 7 hari (1 minggu)
  - Lebih lama dari 30 hari (1 bulan)
  - Semua log
- Modal menampilkan peringatan bahwa penghapusan **tidak dapat dibatalkan**.
- Form dikirim dengan `POST` ke `pakln:log_sistem_reset`, dengan CSRF.
- View: `@role_required("admin_pakln")` dan `@require_POST`. View memvalidasi
  pilihan dari daftar tetap (tidak menerima angka bebas), lalu memanggil:

```python
call_command("bersihkan_log", hari=7, oleh=request.user.username, stdout=out)
```

- Setelah selesai, view mengirim pesan hasil (`messages`) berisi jumlah baris
  yang dihapus, lalu redirect ke halaman monitoring.

### 5.3 Penjadwalan otomatis (opsional)

Karena logikanya di command, pembersihan berkala bisa dijadwalkan tanpa
mengubah kode:
- Windows: Task Scheduler, menjalankan `python manage.py bersihkan_log --hari 30`.
- Linux/Synology: cron dengan perintah yang sama.

Kebutuhan ini belum ditetapkan. Bila mentor meminta otomatis, cukup
penjadwalan di server.

## 6. Status data: hapus permanen

**Keputusan mentor:** bila log sudah penuh, admin menghapusnya sendiri secara
manual, dan data **boleh dihapus permanen (hard delete)** dari database, tanpa
perlu diarsipkan.

Konsekuensi pada rancangan:
- Tidak ada fitur arsip (opsi `--arsip-ke` tidak dibuat).
- Reset dilakukan manual lewat tombol "Reset Log" oleh Admin Biro PAKLN.
  Penjadwalan otomatis (5.3) hanya opsional dan tidak dikerjakan kecuali diminta.
- Setiap reset tetap meninggalkan satu entri audit `log.reset`.

## 7. Hak akses dan keamanan

- Hanya `admin_pakln` yang dapat membuka halaman, mengambil data JSON, dan
  melakukan reset.
- Tidak ada fitur menghapus atau mengubah satu baris log.
- Reset hanya lewat `POST` dengan CSRF.
- Isi log tidak boleh memuat kata sandi, token, atau isi berkas.

## 8. Rencana pengerjaan

1. Model `ActivityLog`, migrasi, dan fungsi `record_activity` beserta decorator.
2. Signal login, logout, dan login gagal.
3. Pasang pencatatan di view penting (lihat katalog 2.3).
4. Management command `bersihkan_log`.
5. Halaman monitoring, endpoint DataTables, dan menu sidebar.
6. View reset dan modal konfirmasi.
7. Tes: pencatatan tidak menggagalkan request, akses per role, endpoint
   DataTables (filter, urutan, paginasi), serta command (`--dry-run`, batch,
   dan penolakan tanpa opsi).
