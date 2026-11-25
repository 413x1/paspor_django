# Mekanisme Login PASPOR

Dokumen ini menjelaskan cara pengguna masuk ke PASPOR. Isinya meliputi metode login, peran aktif, logout, pembatas percobaan login (anti *password guessing*), pencatatan log, dan konfigurasinya.

Dokumen terkait:
- [SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD](SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD): rancangan SSO dan role ganda.
- [SYSTEM_LOGGING.MD](SYSTEM_LOGGING.MD): Log Sistem.
- [DEPLOY_SYNOLOGY.MD](DEPLOY_SYNOLOGY.MD): deployment.

---

## 1. Ringkasan

| Aspek | Ringkasan |
|---|---|
| Halaman login | Satu halaman untuk semua peran: `/login/` (`accounts.views.login_view`) |
| Metode | (a) Username & password; (b) SSO (`/login/sso/`) |
| Setelah login | `/` (`role_redirect`) mengarahkan ke beranda/dasbor sesuai **peran aktif** |
| Role ganda | Peran aktif disimpan di sesi dan dapat diganti tanpa login ulang (`/akun/peran/`) |
| Pembatas login | 5x gagal per **IP + username** atau 20x gagal per **IP** membuat login diblokir 10 menit (HTTP 429) |
| Log | Login berhasil, gagal, SSO, blokir, dan logout dicatat di Log Sistem (`ActivityLog`) |

### Alur umum

```
POST /login/
  │
  ├─ PembatasLoginMiddleware ── IP / IP+username sedang diblokir? ── ya ──► 429 + pesan "coba lagi dalam N menit"
  │                                                                          (kredensial tidak diperiksa)
  ▼ tidak
login_view → authenticate(username, password)
  │
  ├─ berhasil & aktif ──► login() ──► signal user_logged_in
  │                                     ├─ Log Sistem: "Login berhasil"
  │                                     └─ reset hitungan gagal IP+username
  │                       redirect "/" ──► role_redirect ──► beranda sesuai peran aktif
  │
  └─ gagal ──► signal user_login_failed
                 ├─ Log Sistem: "Login gagal" (username saja, password TIDAK dicatat)
                 └─ catat_gagal(): hitung pada 2 lapis; blokir bila mencapai batas
               ──► halaman login + pesan error (429 bila percobaan ini memicu blokir)
```

---

## 2. Login username & password

**Rute:** `GET/POST /login/` (nama URL `login`), view `accounts.views.login_view`. Template: `templates/registration/login.html`.

1. User yang sudah login dan membuka `/login/` langsung diarahkan ke `home`.
2. POST membaca `username` (spasi tepi dibuang) dan `password`, lalu memanggil `authenticate()`. Backend yang memeriksa adalah `django.contrib.auth.backends.ModelBackend`.
3. Bila user ditemukan dan `is_active`, view memanggil `login()` lalu redirect ke `home`.
4. Bila gagal, halaman login tampil lagi dengan pesan umum *"Username atau password salah. Silakan coba lagi."* Pesan ini sengaja tidak membedakan username salah dan password salah.
   - **Pengecualian AB-04:** bila username milik akun aktif yang **tidak memiliki password** (akun khusus SSO), pesannya menjadi *"Akun ini belum memiliki password. Masuk dengan SSO, lalu atur password di menu Profil."*
5. Akun **nonaktif** (`is_active=False`) ditolak oleh `ModelBackend` dan diperlakukan sebagai login gagal, termasuk dihitung oleh pembatas login.

**Password**
- Disimpan sebagai hash (hasher bawaan Django, PBKDF2). Password asli tidak pernah disimpan atau dicatat.
- Validator `AUTH_PASSWORD_VALIDATORS`: kemiripan dengan atribut user, panjang minimum, password umum, dan password yang seluruhnya angka.
- Password diatur oleh Admin Biro PAKLN di Manajemen User (tambah akun, edit user: password baru atau hapus password). Pengguna yang masuk lewat SSO dapat mengatur password sendiri di menu **Profil**.

## 3. Login SSO

**Rute:** `/login/sso/` (nama URL `sso_login`). Logikanya ada di `accounts/sso.py`. Tombol **"Masuk dengan SSO"** tampil bila `SSO_ENABLED=True`, atau bila `DEBUG=True` (stub).

| Kondisi | Perilaku `/login/sso/` |
|---|---|
| `SSO_ENABLED=True` | Adaptor protokol (OIDC/SAML/CAS) **belum diimplementasikan** (menunggu keputusan Q1). Saat ini pengguna dikembalikan ke `/login/` dengan pesan "Login SSO belum tersedia". |
| `SSO_ENABLED=False`, `DEBUG=True` | **Stub pengembangan:** pilih NIP dari data stub e-HRM, lalu alur SSO dijalankan seolah penyedia SSO mengembalikan NIP tersebut. |
| `SSO_ENABLED=False`, `DEBUG=False` | 404 |

Alur inti `masuk_dari_sso(request, sub, nip, klaim)` tidak bergantung pada protokol. Adaptor yang nanti dibuat cukup memvalidasi respons penyedia lalu memanggil fungsi ini:

1. Cari user berdasarkan `sso_sub`. Bila ada, lanjut ke langkah 4.
2. Bila tidak ada, cari user berdasarkan `profile__nip`. Bila ada, akun lama **ditautkan** (`sso_sub` diisi, `sumber_akun=SSO`) dan password lama tetap berlaku. Bila NIP itu sudah tertaut ke `sso_sub` lain, login ditolak.
3. Bila belum ada sama sekali, data diambil dari e-HRM dan user baru dibuat (`buat_user_dari_ehrm`). NIP yang tidak ada di e-HRM, atau e-HRM yang tidak tersedia, membuat login ditolak.
4. Akun nonaktif ditolak dan dicatat sebagai login gagal.
5. Profil user lama disinkronkan dari e-HRM. Bila e-HRM tidak tersedia, kegagalan sinkron dicatat dan data terakhir tetap dipakai.
6. `login()` dipanggil dengan backend `accounts.sso.SsoBackend`, lalu Log Sistem mencatat *"Login lewat SSO"*.

`SsoBackend.authenticate()` selalu mengembalikan `None`. Backend ini hanya ada agar sesi user SSO dikenali (`get_user`); verifikasi identitas dilakukan oleh adaptor protokol.

Kegagalan di langkah SSO (`SsoGagal`) ditampilkan sebagai pesan kepada pengguna dan **tidak** dihitung oleh pembatas login, karena tidak melewati `authenticate()`.

Metode login yang dimiliki sebuah akun ditampilkan sebagai `User.metode_login_display`, misalnya "SSO + Username & Password".

## 4. Setelah login: peran aktif & role ganda

- **Landing `/`** (`role_redirect`) mengarahkan sesuai peran aktif:

  | Peran | Tujuan |
  |---|---|
  | Pegawai | `pegawai:beranda` |
  | Admin Unor | `unor:dashboard` |
  | Admin BPSDM | `bpsdm:dashboard` |
  | Admin Biro PAKLN | `pakln:dashboard` |
  | Admin BKO | `bko:dashboard` |

- **Role ganda:** satu user dapat memiliki beberapa peran (`PeranUser`). `PeranAktifMiddleware` menentukan peran aktif di tiap request dengan urutan berikut:
  1. peran di sesi (`session["peran_aktif"]`) bila masih dimiliki;
  2. bila tidak, peran terakhir (`User.role`);
  3. bila tidak, peran pertama menurut `URUTAN_PERAN` (PAKLN → Unor → BKO → BPSDM → Pegawai).

  Peran ini ditimpakan ke `request.user.role` **hanya di memori**, sehingga `role_required`, sidebar, dan Log Sistem otomatis mengikutinya.
- **Ganti peran:** `POST /akun/peran/` (`ganti_peran`) tanpa login ulang. Peran yang dipilih menjadi default pada login berikutnya dan dicatat di Log Sistem.
- **Hak akses halaman:** decorator `pengajuan.decorators.role_required(*roles)` (menyertakan `login_required`). Peran yang tidak sesuai mendapat 403. User yang belum login diarahkan ke `LOGIN_URL = "login"`.

## 5. Logout

`/logout/` (`logout_view`) memanggil `logout()` (sesi dihapus) lalu redirect ke `/login/`. Log Sistem mencatat "Logout" bila sebelumnya ada user yang login.

---

## 6. Pembatas percobaan login (anti password guessing)

**Latar belakang (temuan keamanan):** sebelumnya tidak ada lapisan pembatas di depan proses autentikasi, sehingga *password guessing online* bisa dijalankan terus-menerus. Pembatas ini dibangun dengan **django-ratelimit 4.1.0**.

**Berkas:**

| Berkas | Isi |
|---|---|
| `accounts/pembatas_login.py` | Logika: hitung gagal, cek blokir, reset, pesan |
| `accounts/signals.py` | `user_login_failed` → `catat_gagal()`; `user_logged_in` → `reset_gagal()` |
| `accounts/middleware.py` | `PembatasLoginMiddleware`: menolak POST login dari pihak yang diblokir |
| `accounts/views.py` | Menampilkan pesan blokir pada percobaan yang memicunya |
| `accounts/tests_pembatas_login.py` | Test perilaku pembatas |

### 6.1 Dua lapis penghitung

| Lapis | Kunci | Batas (bawaan) | Yang diblokir | Direset saat login berhasil? |
|---|---|---|---|---|
| **IP + username** | `IP\|username` | `LOGIN_BATAS_GAGAL` = **5** | username itu dari IP itu | **Ya**, hanya untuk username yang berhasil login |
| **IP** | IP klien | `LOGIN_BATAS_GAGAL_IP` = **20** | seluruh IP (semua username) | **Tidak** |

- Hitungan berlaku dalam jendela `LOGIN_DURASI_BLOKIR` detik (bawaan 600 = 10 menit).
- Begitu batas tercapai, blokir berlaku **10 menit sejak kegagalan yang memicunya**.
- Username dinormalkan (huruf kecil, tanpa spasi tepi), sehingga `budi`, `BUDI`, dan ` Budi` dihitung sebagai satu username.
- Kegagalan dari halaman login aplikasi **dan** `/admin/login/` sama-sama dihitung, karena penghitungan memakai signal `user_login_failed`.

**Mengapa dua lapis?**
- Lapis **IP + username** menahan tebakan berulang ke satu akun. Lapis ini tidak mengganggu pengguna lain di jaringan yang sama, misalnya satu kantor di balik NAT.
- Lapis **IP** menutup dua celah:
  1. **Penyerang yang punya akun.** Tanpa lapis ini, penyerang bisa menebak 4x ke akun korban, login dengan akunnya sendiri untuk mereset hitungan, lalu mengulang. Dengan dua lapis, login berhasil hanya mereset kombinasi IP + akun yang dipakai login, sedangkan hitungan per IP tidak pernah direset.
  2. **Password spraying.** Tebakan yang disebar ke banyak username tetap terkumpul di hitungan per IP.

### 6.2 Selama diblokir

- Setiap **POST** ke `/login/` atau `/admin/login/` dari IP yang diblokir, atau dari IP + username yang diblokir, langsung ditolak oleh `PembatasLoginMiddleware`. Penolakannya berupa:
  - status **429 Too Many Requests**;
  - header `Retry-After: <detik>`;
  - halaman login dengan pesan *"Terlalu banyak percobaan login yang gagal dari perangkat/jaringan Anda. Silakan coba lagi dalam N menit."*
- `authenticate()` **tidak dipanggil**, jadi password yang benar pun ditolak sampai blokir berakhir.
- `GET /login/` tetap bisa dibuka.
- Bila yang diblokir hanya IP + username, username lain dari IP yang sama tetap bisa login.

### 6.3 Contoh skenario (bawaan 5 / 20 / 10 menit)

| Skenario | Hasil |
|---|---|
| Salah password 4x, lalu benar | Login berhasil; hitungan IP + username kembali 0 |
| Salah password 5x untuk `budi` | Percobaan ke-5 langsung 429; `budi` dari IP ini diblokir 10 menit |
| `budi` diblokir, user lain di IP yang sama login | Berhasil |
| 4x salah ke `budi`, login akun sendiri, 1x salah ke `budi` | 429 (hitungan `budi` tidak direset oleh akun lain) |
| 20x gagal ke username yang berbeda-beda dari satu IP | Seluruh IP diblokir 10 menit, termasuk akun milik penyerang |
| Login dari IP lain | Tidak terdampak |

### 6.4 Penyimpanan & ketahanan

- Penghitung dan daftar blokir disimpan di **cache Django** (`RATELIMIT_USE_CACHE = "default"`).
  - **Produksi:** Redis (`django.core.cache.backends.redis.RedisCache`) di DB `CACHE_REDIS_DB` (bawaan 1), terpisah dari broker Celery (`REDIS_DB`).
  - **Produksi WAJIB Redis.** LocMem bersifat per proses, sehingga dengan 3 worker Gunicorn batasnya menjadi sekitar 3x lipat.
- Kunci blokir: `login-blokir:<grup>:<sha256(nilai)>`, dengan TTL = durasi blokir.
- **Fail open:** bila Redis tidak dapat dihubungi, pembatas tidak aktif sementara. Login tetap berjalan dan error dicatat di log teknis (`accounts.pembatas_login`). Tujuannya agar gangguan Redis tidak mengunci seluruh pengguna.
- `reset_gagal()` membentuk kunci cache dengan fungsi internal django-ratelimit (`_make_cache_key`, `_get_window`). Versi paket dipin di `requirements.txt`. **Bila django-ratelimit di-upgrade, jalankan ulang `accounts.tests_pembatas_login`.**

### 6.5 IP klien & reverse proxy

IP diambil dengan `logs.utils._ambil_ip`, fungsi yang sama dengan Log Sistem:

- `ACTIVITY_LOG_TRUST_PROXY=False` (bawaan): memakai `REMOTE_ADDR`.
- `ACTIVITY_LOG_TRUST_PROXY=True`: memakai alamat pertama `X-Forwarded-For`.

> **Penting:** bila aplikasi diakses lewat reverse proxy (mis. Reverse Proxy Synology DSM), set `ACTIVITY_LOG_TRUST_PROXY=True`. Tanpa itu, semua pengguna terlihat dengan IP proxy, dan 20 kegagalan dari siapa pun akan memblokir login **semua orang**. Sebaliknya, jangan aktifkan bila aplikasi diakses langsung, karena header `X-Forwarded-For` bisa dipalsukan untuk mengakali pembatas.

### 6.6 Membuka blokir secara manual

Blokir berakhir sendiri setelah 10 menit. Untuk membukanya lebih cepat, hapus kunci blokir dan penghitung dari cache. Membersihkan seluruh cache aplikasi juga ikut menghapus semua penghitung:

```bash
python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```

---

## 7. Pencatatan (Log Sistem)

Receiver ada di `logs/signals.py` dan `accounts/pembatas_login.py`:

| Kejadian | Aktivitas | Keterangan |
|---|---|---|
| Login password berhasil | `auth.login` | "Login berhasil" |
| Login SSO berhasil | `auth.login_sso` | "Login lewat SSO" |
| Login gagal | `auth.login_failed` | Hanya **username** yang dicatat; password tidak pernah disimpan |
| Blokir IP + username | `auth.login_failed` | "Username diblokir sementara 10 menit dari IP ini setelah 5 kali login gagal" |
| Blokir IP | `auth.login_failed` | "IP diblokir sementara 10 menit setelah 20 kali login gagal" |
| SSO ditolak (akun nonaktif) | `auth.login_failed` | "Login SSO ditolak: akun nonaktif" |
| Ganti peran | `akun.ganti_peran` | "Ganti peran: X → Y" |
| Logout | `auth.logout` | "Logout" |

Setiap blokir juga ditulis sebagai `WARNING` di log teknis, lengkap dengan IP dan username.

## 8. Konfigurasi

Variabel ini ada di `paspor_project/settings.py` dan dapat diatur lewat `.env`; contohnya ada di `.env.example`.

| Variabel | Bawaan | Fungsi |
|---|---|---|
| `LOGIN_BATAS_GAGAL` | `5` | Batas gagal per IP + username |
| `LOGIN_BATAS_GAGAL_IP` | `20` | Batas gagal per IP (semua username) |
| `LOGIN_DURASI_BLOKIR` | `600` | Jendela hitung & lama blokir (detik) |
| `DJANGO_CACHE_BACKEND` | `redis` bila `DEBUG=False`, `locmem` bila `DEBUG=True` | Backend cache |
| `CACHE_REDIS_DB` | `1` | Nomor DB Redis untuk cache |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` | — | Koneksi Redis (dipakai bersama Celery) |
| `ACTIVITY_LOG_TRUST_PROXY` | `False` | Percayai `X-Forwarded-For` untuk IP klien |
| `SSO_ENABLED` | `False` | Aktifkan login SSO |
| `SSO_PROTOCOL`, `SSO_ISSUER_URL`, `SSO_CLIENT_ID`, `SSO_CLIENT_SECRET`, `SSO_NIP_CLAIM`, `SSO_SCOPES` | — | Parameter adaptor SSO (belum dipakai, menunggu Q1) |
| `DJANGO_BEHIND_HTTPS_PROXY` | `False` | Cookie sesi & CSRF hanya lewat HTTPS (`*_COOKIE_SECURE`) |

Untuk pengembangan dengan LocMem, peringatan *system check* django-ratelimit (`E003`, `W001`) dibungkam. Untuk Redis, hanya `W001` yang dibungkam: backend Redis bawaan Django mendukung `incr` atomik, tetapi tidak tercantum di daftar resmi django-ratelimit.

## 9. Pengujian

```bash
python manage.py test accounts.tests_pembatas_login   # pembatas login
python manage.py test accounts.tests_sso              # alur SSO
python manage.py test accounts.tests_peran            # role ganda & peran aktif
```

Test pembatas login memakai cache LocMem tersendiri (`override_settings(CACHES=...)`) dan membersihkannya di setiap test, sehingga tidak bergantung pada Redis.

## 10. Catatan & pengembangan lanjutan

- **Adaptor SSO** (OIDC/SAML/CAS) belum ada dan menunggu keputusan protokol (Q1).
- Pembatas hanya melindungi **halaman login**. Form lain yang memeriksa password, misalnya ganti password di Profil, hanya bisa diakses user yang sudah login dan tidak dihitung.
- `/logout/` menerima GET. Pertimbangkan menjadikannya POST saja untuk mencegah logout paksa lewat tautan (CSRF logout).
- Sesi memakai pengaturan bawaan Django: masa berlaku cookie sesi 2 minggu, dan sesi tidak berakhir saat browser ditutup. Sesuaikan `SESSION_COOKIE_AGE` / `SESSION_EXPIRE_AT_BROWSER_CLOSE` bila kebijakan keamanan mensyaratkan batas sesi.
