# Rencana Perbaikan — SSO, Data e-HRM, Role Ganda & Nomor HP

> **Tanggal:** 19 Oktober 2026 (revisi 1: keputusan Q2–Q9, lihat [§14](#14-keputusan--pertanyaan-terbuka))
> **Status:** rancangan — belum diimplementasikan.
> **Cakupan:** autentikasi (SSO + username/password), sinkronisasi profil dari e-HRM,
> satu akun dengan beberapa role, nomor HP wajib (tautan WhatsApp), dan halaman Edit Profil.
> **Terkait:** [BISNIS_PROSES_PDLN.MD](BISNIS_PROSES_PDLN.MD) §3 (peran) & §9.1 (profil),
> [SYSTEM_LOGGING.MD](SYSTEM_LOGGING.MD), [PEGAWAI_SEEDS.md](PEGAWAI_SEEDS.md).

---

## Daftar Isi

1. [Latar Belakang](#1-latar-belakang)
2. [Kondisi Saat Ini](#2-kondisi-saat-ini)
3. [Aturan Bisnis](#3-aturan-bisnis)
4. [Alur Login](#4-alur-login)
5. [Perancangan Data](#5-perancangan-data)
6. [Role Ganda](#6-role-ganda)
7. [Edit Profil](#7-edit-profil)
8. [Kelola User oleh Admin Biro PAKLN](#8-kelola-user-oleh-admin-biro-pakln)
9. [Integrasi SSO & e-HRM](#9-integrasi-sso--e-hrm)
10. [Log & Keamanan](#10-log--keamanan)
11. [Migrasi Data](#11-migrasi-data)
12. [Rencana Implementasi per Fase](#12-rencana-implementasi-per-fase)
13. [Test](#13-test)
14. [Keputusan & Pertanyaan Terbuka](#14-keputusan--pertanyaan-terbuka)

---

## 1. Latar Belakang

- **Login pertama lewat SSO.** Pegawai dan admin (kecuali Admin Biro PAKLN) masuk
  pertama kali lewat SSO. Data profil pegawai, **termasuk email dan nomor HP**,
  ditarik dari **e-HRM**, tidak lagi diinput manual oleh Admin Biro PAKLN.
- **Login berikutnya bisa dua cara.** Pengguna tetap boleh memakai SSO, atau
  mengatur **username & password** sendiri di Edit Profil lalu login dengan itu.
- **Satu orang bisa punya beberapa role.** Setiap pengguna SSO adalah pegawai.
  Sebagian juga menjadi admin, misalnya *Pegawai + Admin Unor*, *Pegawai + Admin BKO*,
  atau *Pegawai + Admin BPSDM*.
- **Nomor HP wajib untuk semua user.** Nomor ini dipakai sebagai jalur komunikasi
  alternatif lewat WhatsApp. Sistem hanya menampilkan **tautan** yang membuka aplikasi
  WhatsApp; percakapannya berlangsung di luar sistem.
- **Isian Edit Profil dibatasi.** Pegawai dan admin selain Admin Biro PAKLN hanya
  boleh mengubah **username dan password**. Email dan nomor HP hanya bisa diubah oleh
  **Admin Biro PAKLN**: miliknya sendiri lewat Edit Profil, dan milik user lain lewat
  Kelola User.

## 2. Kondisi Saat Ini

| Aspek | Implementasi sekarang | Dampak terhadap kebutuhan baru |
|---|---|---|
| Login | [accounts/views.py](../../accounts/views.py) `login_view`: hanya username/password (`authenticate`). | Perlu jalur SSO dan akun tanpa password. |
| Pembuatan akun | Admin Biro PAKLN membuat semua akun lewat `TambahUserForm` ([accounts/forms.py](../../accounts/forms.py)), termasuk data kepegawaian manual. | Akun pegawai dibuat otomatis saat login SSO pertama, dengan data dari e-HRM. Pembuatan manual tetap ada untuk akun lokal. |
| Role | Satu field `User.role` (CharField). Dipakai langsung di `role_required` ([pengajuan/decorators.py](../../pengajuan/decorators.py), ±100 view), `role_redirect`, sidebar ([templates/partials/_sidebar.html](../../templates/partials/_sidebar.html)), `context_processors`, `notifications/services.py` (`filter(role=...)`), dan snapshot `role` di `logs`. | Satu user perlu bisa punya beberapa role. |
| Cakupan Admin Unor | `User.unit_organisasi` ([pengajuan/views_unor.py:27](../../pengajuan/views_unor.py#L27)). Untuk pegawai, unitnya ada di `PegawaiProfile.unit_organisasi`. | Pada user ber-role ganda, unit sebagai pegawai bisa berbeda dari unit yang dikelola sebagai Admin Unor. |
| Data personal | `PegawaiProfile` (NIP, nama, jabatan, pangkat, unit). Halaman Profil sudah berlabel "Sinkronisasi e-HRM", tetapi belum ada integrasinya. | Diisi dan diperbarui dari e-HRM. |
| Nomor HP | Belum ada. | Field baru, wajib, bersumber dari e-HRM atau diisi Admin Biro PAKLN. |
| Email | `AbstractUser.email` (`blank=True`). | Bersumber dari e-HRM. Koreksi hanya oleh Admin Biro PAKLN. |
| Halaman Profil | `pengajuan/views_pegawai.py` `profil`: hanya Data Paspor & dokumen. Belum ada pengaturan akun. | Tambah bagian **Akun & Kontak** (username, password). |

## 3. Aturan Bisnis

**A. Login & akun**

| Kode | Aturan |
|---|---|
| AB-01 | Pegawai dan admin yang berasal dari SSO **login pertama kali lewat SSO**. Akun dibuat otomatis (*just-in-time provisioning*) dan dikaitkan dengan identitas SSO (NIP / *subject id*). |
| AB-02 | Saat login SSO, data kepegawaian (nama, NIP, jabatan, pangkat/golongan, unit kerja, unit organisasi, **email, nomor HP**) **ditarik dari e-HRM**. Data ini diperbarui setiap kali pengguna login lewat SSO, kecuali nilai yang dikunci Admin Biro PAKLN (AB-18). |
| AB-03 | Setelah login pertama, pengguna boleh mengatur username & password di Edit Profil. Setelah itu ia bisa login dengan **SSO maupun username/password**. |
| AB-04 | Akun yang belum mengatur password (password *unusable*) **tidak bisa** login lewat form username/password dan diarahkan ke SSO. |
| AB-05 | **Akun lokal** dibuat oleh Admin Biro PAKLN (atau seed) dan login hanya dengan username/password. Akun lokal mencakup **Admin Biro PAKLN** dan **akun admin darurat** (Admin Unor/BPSDM/BKO yang dibuat manual tanpa SSO). |
| AB-06 | Akun yang dinonaktifkan (`is_active=False`) ditolak di **kedua** jalur login. |
| AB-07 | Pengguna yang sudah memiliki password boleh **menghapus password**-nya (kembali ke SSO saja). Opsi ini hanya untuk akun yang memiliki kaitan SSO (`sso_sub` terisi), supaya akun lokal tidak terkunci. |

**B. Role**

| Kode | Aturan |
|---|---|
| AB-08 | Setiap user SSO otomatis memiliki role **Pegawai**. |
| AB-09 | Role admin (Admin Unor, Admin BPSDM, Admin BKO, Admin Biro PAKLN) adalah **tambahan** dan hanya diberikan oleh Admin Biro PAKLN. Admin Unor wajib memiliki unit organisasi yang dikelola. |
| AB-10 | User dengan lebih dari satu role memilih **peran aktif**. Menu, dasbor, dan hak akses mengikuti peran aktif. Peran bisa diganti tanpa login ulang. |
| AB-11 | Pengajuan selalu milik **user**, bukan milik role. Admin Unor yang juga pegawai tetap mengajukan perjalanan sebagai Pegawai. |
| AB-12 | Admin **tidak boleh memproses pengajuannya sendiri**, misalnya Admin Unor memverifikasi pengajuan miliknya. Server wajib menolak hal ini. |
| AB-13 | Notifikasi untuk user ber-role ganda **digabung** dalam satu daftar, tanpa dipisah per peran aktif. |

**C. Profil & kontak**

| Kode | Aturan |
|---|---|
| AB-14 | **Semua user wajib memiliki nomor HP** yang aktif WhatsApp. Akun SSO memperolehnya dari e-HRM. Akun lokal diisi Admin Biro PAKLN saat akun dibuat (wajib di form). |
| AB-15 | Nomor HP disimpan dalam format internasional tanpa `+` (`62812xxxxxxx`). Input `08…`, `+62…`, `62…`, spasi, dan tanda `-` dinormalisasi. Panjang 10–15 digit. |
| AB-16 | Di **Edit Profil**, Pegawai, Admin Unor, Admin BPSDM, dan Admin BKO **hanya** dapat mengubah **username dan password**. Email, nomor HP, dan data e-HRM tampil sebagai baca-saja. **Admin Biro PAKLN** dapat mengubah **username, password, email, dan nomor HP** miliknya sendiri. |
| AB-17 | **Email dan nomor HP** user lain hanya dapat diubah oleh **Admin Biro PAKLN** lewat Kelola User. Karena perubahannya dilakukan admin, tidak ada verifikasi OTP. |
| AB-18 | Email/nomor HP yang dikoreksi Admin Biro PAKLN **dikunci**, sehingga tidak ditimpa sinkronisasi e-HRM berikutnya. Admin Biro PAKLN dapat membuka kunci ("Kembalikan ke data e-HRM"). |
| AB-19 | Bila nomor HP user kosong (e-HRM tidak menyediakannya), user tetap bisa login. Ia melihat banner "Nomor HP belum tercatat — hubungi Admin Biro PAKLN", dan user tersebut muncul pada filter **Tanpa No. HP** di Kelola User. |
| AB-20 | Username unik tanpa membedakan huruf besar/kecil. Email unik bila diisi. |
| AB-21 | Mengganti password yang sudah ada **wajib memasukkan password lama**. Mengatur password untuk pertama kali (akun SSO tanpa password) tidak memerlukan password lama, karena pengguna sudah terautentikasi lewat SSO pada sesi itu. |
| AB-22 | Nomor HP ditampilkan sebagai tautan `https://wa.me/62…` yang membuka aplikasi WhatsApp. Sistem **tidak** mengirim atau mencatat pesan WhatsApp. |

## 4. Alur Login

```
                    ┌──────────────── Halaman Login ────────────────┐
                    │  [ Masuk dengan SSO ]                         │
                    │  ── atau ──                                   │
                    │  Username / Password  [ Masuk ]               │
                    └───────┬─────────────────────────────┬─────────┘
                            │ SSO                         │ form
                            ▼                             ▼
                 Callback SSO (sub/NIP)          authenticate(username, pw)
                            │                             │ gagal / password unusable
                 cari User by sso_sub ──tidak ada──┐      └─► pesan error / "gunakan SSO"
                            │ ada                  ▼
                            │            ambil data e-HRM by NIP
                            │            buat User + PegawaiProfile
                            │            + role Pegawai
                            ▼                  │
                 sinkron data e-HRM ◄──────────┘
                 (email/HP dikunci tidak ditimpa)
                            │
                            ▼
                 login(); tentukan peran aktif (§6.2)
                            │
                            ▼
                 role_redirect → dasbor peran aktif
                 (banner bila no_hp kosong, AB-19)
```

**Catatan:**

- Login SSO pertama untuk NIP yang **sudah ada** di database (data seed/manual lama)
  akan **mengaitkan** akun lama itu. Akun baru tidak dibuat. Lihat [§11](#11-migrasi-data).
- Bila e-HRM tidak tersedia saat login:
  - **user lama**: login tetap berhasil dengan data terakhir yang tersimpan, dan
    kegagalannya dicatat di log;
  - **user baru**: login ditolak dengan pesan "Data kepegawaian tidak dapat diambil,
    coba lagi nanti", karena profil minimum tidak bisa dibentuk.
- Logout dari PASPOR hanya mengakhiri sesi PASPOR. *Single logout* ke penyedia SSO
  tidak diperlukan (Q8).

## 5. Perancangan Data

### 5.1 `accounts.User` (perubahan)

| Field | Tipe | Keterangan |
|---|---|---|
| `no_hp` | `CharField(20, blank=True, db_index=True)` | Disimpan ternormalisasi (`62…`). `blank=True` di DB agar migrasi user lama dan data e-HRM yang kosong tetap aman. Kewajiban ditegakkan oleh form Admin Biro PAKLN dan banner (AB-14, AB-19). |
| `email` | (bawaan) | Tetap. Unik bila diisi, divalidasi di form (AB-20). |
| `sso_sub` | `CharField(100, null=True, unique=True)` | ID unik dari penyedia SSO. Dipakai mencari akun saat callback, jadi username boleh diubah tanpa memutus kaitan SSO. |
| `sumber_akun` | `CharField(choices=["sso","lokal"])` | `sso` = dibuat lewat SSO, `lokal` = dibuat Admin Biro PAKLN/seed. |
| `email_dikunci`, `no_hp_dikunci` | `BooleanField(default=False)` | Di-set `True` saat Admin Biro PAKLN mengoreksi nilainya, sehingga sinkronisasi e-HRM tidak menimpanya (AB-18). |
| `ehrm_sinkron_at` | `DateTimeField(null=True)` | Waktu sinkronisasi e-HRM terakhir, ditampilkan di Profil. |
| `role` | (tetap ada) | Berganti makna menjadi **peran default/utama**, dan menjadi *fallback* bila sesi belum memilih peran aktif. Lihat [§6](#6-role-ganda). |
| `unit_organisasi` | (tetap ada sementara) | Dipindah ke `PeranUser.unit_organisasi` untuk Admin Unor, lalu dihapus pada fase pembersihan. |

### 5.2 Model baru `accounts.PeranUser`

```python
class PeranUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="peran_list")
    role = models.CharField(max_length=20, choices=User.Role.choices)
    # Wajib untuk admin_unor: unit organisasi yang dikelola (bisa berbeda dari
    # unit tempat user bertugas sebagai pegawai).
    unit_organisasi = models.ForeignKey("paspor.UnitOrganisasi", on_delete=models.PROTECT,
                                        null=True, blank=True, related_name="+")
    is_active = models.BooleanField(default=True)
    diberikan_oleh = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "role")
```

- `admin_pakln` juga tercatat di tabel ini, supaya semua pemeriksaan role melewati satu
  sumber.
- **Validasi:**
  - `admin_unor` wajib punya `unit_organisasi`;
  - role `pegawai` wajib punya `PegawaiProfile`;
  - akun admin darurat (lokal, tanpa NIP) **tidak** memiliki role `pegawai`.

### 5.3 `PegawaiProfile`

Struktur tetap. Sumber datanya kini e-HRM. Tambah `ehrm_id` (opsional). Email dan
nomor HP dari e-HRM disalin ke `User.email` / `User.no_hp` (kecuali dikunci). Field
`sisa_cuti_tahun_berjalan` tetap dikelola PASPOR, kecuali e-HRM ternyata menyediakannya.

## 6. Role Ganda

### 6.1 Strategi: "peran aktif" di sesi

Agar ±100 pemanggilan `request.user.role` tidak perlu diubah satu per satu:

1. Middleware baru `accounts.middleware.PeranAktifMiddleware`, dipasang setelah
   `AuthenticationMiddleware`, membaca `request.session["peran_aktif"]`. Bila nilainya
   valid (ada di `PeranUser` aktif milik user), nilai itu **di-set ke
   `request.user.role` di memori**. Bila tidak valid, middleware memakai peran default.
   Dengan begitu `role_required`, sidebar, `role_redirect`, `context_processors`, dan
   snapshot `role` di `logs` otomatis mengikuti peran aktif.
2. Atribut tersebut **tidak pernah di-`save()`**. Kode yang memanggil `user.save()`
   pada `request.user` perlu diaudit, atau `User.save()` dibuat agar tidak menulis
   field `role` ketika nilai di memori sudah ditimpa (lihat [Fase 3](#12-rencana-implementasi-per-fase)).
3. Method baru di `User`:
   - `daftar_peran()`: daftar role aktif dari `PeranUser`;
   - `punya_peran(role)`;
   - `unit_organisasi_admin()`: unit dari `PeranUser(role=admin_unor)`.

   `get_unit_organisasi()` dan `views_unor` beralih ke `unit_organisasi_admin()`.

### 6.2 Penentuan peran aktif saat login

- Bila user hanya punya satu role, role itu langsung dipakai.
- Bila punya lebih dari satu, dipakai peran aktif terakhir (disimpan di
  `User.role`/preferensi). Bila belum ada, dipakai urutan prioritas
  *admin_pakln → admin_unor → admin_bko → admin_bpsdm → pegawai*. Pengguna bisa
  langsung menggantinya lewat *switcher*.

### 6.3 Pengganti peran (UI)

- Dropdown **"Masuk sebagai: Pegawai ▾"** di header/sidebar. Hanya tampil bila user
  punya lebih dari satu role.
- `POST /akun/peran/` dengan `peran=<role>`:
  1. validasi kepemilikan role;
  2. set session;
  3. catat log;
  4. redirect ke `home`.

  Dikirim dengan CSRF, tidak boleh lewat GET.
- Setiap halaman memberi tanda peran aktif, misalnya badge di header, supaya admin
  tidak bingung sedang bertindak sebagai siapa.

### 6.4 Penyesuaian kode yang membaca role dari database

Middleware hanya memengaruhi `request.user`. Query yang mencari user **berdasarkan
role** harus beralih ke `PeranUser`:

| Lokasi | Perubahan |
|---|---|
| `notifications/services.py` (`_admin_unor_*`, `_admin_bpsdm`, `_admin_pakln`, `_admin_bko`, `_penerima_bko_semua`) | `User.objects.filter(peran_list__role=..., peran_list__is_active=True, peran_list__unit_organisasi=...)`, ditambah `.distinct()`. |
| `views_unor.py` (cakupan unit) | `request.user.unit_organisasi_admin()`. |
| `pengajuan/report.py`, `riwayat.py`, `pembatalan.py`, `bko.py` | Audit pemakaian `.role` pada **user lain**, misalnya `pengusul.role`. Untuk user lain yang dibutuhkan adalah "peran saat bertindak", jadi sebaiknya disimpan sebagai snapshot di riwayat (sudah dilakukan untuk log). |
| `accounts/admin.py`, seed, tests | Isi `PeranUser` bersamaan dengan `User.role`. |

Untuk AB-12, tambahkan pemeriksaan `pengajuan.pegawai_id != request.user.id` di view
proses Admin Unor, BPSDM, BKO, dan PAKLN.

### 6.5 Notifikasi

Notifikasi tetap **per user** dan **digabung** dalam satu daftar/lonceng, tanpa
pemisahan per peran aktif (AB-13). Satu hal yang perlu dijaga:
`_penerima_bko_semua` dan fungsi sejenis harus memakai `.distinct()`/`set` per user,
supaya user ber-role ganda tidak menerima notifikasi yang sama dua kali.

Setiap notifikasi menyimpan `untuk_peran` (hanya sebagai metadata, bukan untuk
memisahkan daftar). Saat notifikasi diklik, peran aktif otomatis berpindah ke peran
tersebut, sehingga tautan tidak berakhir 403. Detailnya ada di
[SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD §5.4](SSO_PROFIL_ROLE_GANDA_IMPLEMENTATION_PLAN.MD#54-refactor-penerima-notifikasi).

## 7. Edit Profil

### 7.1 Tata letak halaman Profil (`/profil/`)

```
┌ Data Personal ─────────────── [Sinkronisasi e-HRM] ┐   baca-saja
│ Nama, NIP, Jabatan, Pangkat, Unit Kerja, Unit Org  │   + "Terakhir sinkron: 19 Okt 2026 08:12"
│ Email, No. HP (WhatsApp)                           │   baca-saja; "Perubahan melalui Admin Biro PAKLN"
└────────────────────────────────────────────────────┘     (bagi Admin Biro PAKLN: dapat diubah, lihat §7.2)
┌ Akun ────────────────────────────────────── [Ubah] ┐   ← BARU
│ Username                                           │   dapat diubah
│ Metode login: "SSO" / "SSO + Username & Password"  │
│ Peran: Pegawai, Admin Unor (Dit. X)                │   baca-saja (diatur PAKLN)
└────────────────────────────────────────────────────┘
┌ Keamanan ──────────────────────────────────────────┐   ← BARU
│ [Atur Password] / [Ganti Password] / [Hapus Password]│
└────────────────────────────────────────────────────┘
Data Paspor / Dokumen Kepegawaian (tetap)
```

Untuk akun lokal (tanpa data e-HRM), bagian **Data Personal** menampilkan nama, unit,
email, dan nomor HP dari `User`, juga sebagai baca-saja.

### 7.2 Form

| Form | Isian | Aturan |
|---|---|---|
| `UbahUsernameForm` | `username` | Unik tanpa membedakan huruf besar/kecil (AB-20). |
| `AturPasswordForm` (akun tanpa password) | `password_baru`, `konfirmasi` | `validate_password`. Tidak perlu password lama (AB-21). |
| `GantiPasswordForm` | `password_lama`, `password_baru`, `konfirmasi` | Pakai `django.contrib.auth.forms.PasswordChangeForm`, lalu `update_session_auth_hash` agar sesi tidak terputus. |
| Hapus password | `password_lama` (konfirmasi) | Hanya bila `sso_sub` terisi (AB-07). Memanggil `set_unusable_password()`. |
| `KontakForm` (**khusus Admin Biro PAKLN**) | `email`, `no_hp` | `no_hp` wajib dan dinormalisasi (AB-15). Email unik (AB-20). Bila akun juga terhubung ke e-HRM, field yang diubah ikut dikunci (AB-18). Form yang sama dipakai di Edit User (§8). |

- Empat form pertama berlaku untuk **semua role**. `KontakForm` hanya tampil dan hanya
  diproses bila peran aktif adalah Admin Biro PAKLN.
- **Whitelist di server:** view hanya memproses field yang diizinkan untuk peran
  aktif. Field lain yang dikirim (nama, NIP, role, unit, serta email/no_hp untuk
  selain Admin Biro PAKLN) diabaikan, sekalipun HTML dimanipulasi.
- **Banner nomor HP kosong** (AB-19): context processor `profil_belum_lengkap`, ditampilkan
  di `base.html` pada semua halaman.

### 7.3 Tampilan nomor HP

- Nomor ditampilkan sebagai `+62 812-xxxx-xxxx` dengan ikon WhatsApp dan tautan
  `https://wa.me/62812…` (`target="_blank" rel="noopener"`). Tautan ini membuka
  aplikasi/web WhatsApp, dan komunikasi berlangsung di luar sistem (AB-22).
- Lokasi tautan:
  - Profil sendiri;
  - Kelola User (Admin Biro PAKLN);
  - **detail pengajuan** di sisi admin (kontak pegawai pengusul);
  - di sisi pegawai, kontak admin yang memproses, bila diputuskan perlu.
- Filter template `wa_link` / `format_hp` di `pengajuan/templatetags/pengajuan_extras.py`.

## 8. Kelola User oleh Admin Biro PAKLN

| Fitur | Perubahan |
|---|---|
| **Tambah user** (`TambahUserForm`) | Membuat **akun lokal**: Admin Biro PAKLN dan **akun admin darurat** (Admin Unor/BPSDM/BKO, Q6). Isian `no_hp` dan `email` wajib. Pegawai sebaiknya tidak dibuat manual. Sebagai gantinya ada **pra-daftar via NIP**: data ditarik dari e-HRM, user dibuat tanpa password, dan `sso_sub` diisi saat login pertama. Ini berguna untuk memberi role admin sebelum orangnya login. |
| **Edit user** (`EditUserForm`) | Admin Biro PAKLN bisa mengubah **email dan nomor HP** semua user (AB-17). Setiap perubahan mengunci field tersebut (AB-18) dan menampilkan tombol **"Kembalikan ke data e-HRM"**. Untuk akun `sumber_akun=sso`, data e-HRM lain tampil baca-saja, disertai tombol **"Sinkron ulang dari e-HRM"**. Yang juga bisa diatur: aktif/nonaktif, reset password (menjadi *unusable* untuk akun SSO, atau password baru untuk akun lokal), dan **role**. |
| **Kelola peran** (baru) | Bagian "Peran" di Edit User: tambah/cabut Admin Unor (+ pilih unit), Admin BPSDM, Admin BKO, dan Admin Biro PAKLN. Role Pegawai tidak bisa dicabut dari akun SSO. Setiap perubahan dicatat (`diberikan_oleh`, log). |
| **Daftar user** (`pakln/users.html`) | Kolom role menampilkan semua role (badge). Ditambah kolom No. HP (tautan WhatsApp), metode login, dan sumber akun. Filter: per role (via `PeranUser`) dan **Tanpa No. HP** (AB-19). |

## 9. Integrasi SSO & e-HRM

### 9.1 SSO

> **Belum diputuskan** (Q1): protokol, penyedia, dan klaim yang tersedia. Rancangan di
> bawah ini adalah asumsi kerja, dan kodenya dibuat dengan batas antarmuka yang jelas
> agar mudah disesuaikan.

- Asumsi kerja: **OpenID Connect** (Authorization Code + PKCE). Kandidat library:
  `mozilla-django-oidc` atau `authlib`. Bila ternyata SAML, kandidatnya `djangosaml2`;
  bila CAS, `django-cas-ng`.
- Kode ditempatkan di `accounts/sso.py`. Semua logika setelah identitas diterima
  dipusatkan di satu fungsi yang **tidak bergantung pada protokol**:
  `masuk_dari_sso(request, sub, nip, klaim)`. Fungsi ini mencari/menautkan user,
  menyinkronkan e-HRM, lalu memanggil `login`.
- Klaim minimum yang dibutuhkan: pengenal unik (`sub`) dan **NIP**. Bila SSO tidak
  menyediakan NIP, perlu jalur pemetaan lain (misalnya email kantor ke e-HRM), dan itu
  harus dikonfirmasi.
- Env baru di `.env.example`:

  ```
  SSO_ENABLED=False
  SSO_ISSUER_URL=
  SSO_CLIENT_ID=
  SSO_CLIENT_SECRET=
  SSO_NIP_CLAIM=nip
  SSO_SCOPES=openid profile email
  ```

- Bila `SSO_ENABLED=False`, tombol SSO disembunyikan. Untuk pengembangan, disediakan
  **stub** (pilih NIP dari daftar seed, hanya saat `DEBUG=True`) yang memanggil
  `masuk_dari_sso`, mengikuti pola `paspor/integrasi/pintar.py`.

### 9.2 e-HRM

- Modul `paspor/integrasi/ehrm.py` dengan antarmuka yang sama dengan `pintar.py`:
  `ambil_pegawai(nip) -> DataPegawai | None` (dataclass frozen). Bila `EHRM_API_URL`
  kosong, dipakai data stub lokal.
- e-HRM **menyediakan email dan nomor HP** (Q2). Kontrak yang diasumsikan (endpoint
  dan autentikasi menunggu spesifikasi):

  ```
  GET {EHRM_API_URL}/pegawai/{nip}
  -> {"nip","nama","jabatan","pangkat_golongan","unit_kerja","kode_unit_organisasi","email","no_hp"}
  ```

- Fungsi `sinkron_profil(user, data)`:
  1. memperbarui `PegawaiProfile`;
  2. memetakan `kode_unit_organisasi` ke `UnitOrganisasi` (bila tidak ada padanan,
     unit dibiarkan, lalu dicatat warning);
  3. menormalisasi `no_hp` (AB-15), lalu mengisi `User.email`/`User.no_hp` **kecuali
     dikunci** (AB-18);
  4. memperbarui `ehrm_sinkron_at`.
- Timeout pendek (5 detik) dan tidak memblokir login user lama (lihat [§4](#4-alur-login)).
- Opsional: management command `sinkron_ehrm` untuk sinkronisasi massal terjadwal.

## 10. Log & Keamanan

**Event baru di `logs`** (lihat [SYSTEM_LOGGING.MD](SYSTEM_LOGGING.MD)):

- `login_sso`, `login_password`, `login_gagal`;
- `ganti_peran`;
- `ubah_username`;
- `atur_password`, `ganti_password`, `hapus_password` (**tanpa nilai password**);
- `ubah_kontak_oleh_pakln` (field yang berubah, nilai lama → baru), `buka_kunci_kontak`;
- `peran_diberikan`, `peran_dicabut`;
- `sinkron_ehrm_gagal`.

**Keamanan:**

- **Sesi:**
  - `request.session.cycle_key()` saat login (sudah dilakukan oleh `login()`);
  - sesi lain dibatalkan saat password diganti (`update_session_auth_hash` hanya
    mempertahankan sesi aktif).
- **Rate limit** login username/password, misalnya `django-axes` atau penghitung
  sederhana per IP+username. Saat ini belum ada.
- **Username:** penggantian username tidak boleh mengambil format NIP milik orang lain
  (opsional: larang username berupa 18 digit angka selain NIP sendiri).
- **Email & nomor HP** hanya diubah oleh Admin Biro PAKLN, sehingga tidak perlu OTP
  (Q4). Semua perubahan tercatat di log.
- **Nomor HP** adalah data pribadi. Nomor hanya ditampilkan ke pemilik, ke Admin yang
  memproses pengajuan pemilik, dan ke Admin Biro PAKLN. Nomor tidak diekspor ke
  report kecuali diminta.

## 11. Migrasi Data

1. Migrasi skema: tambah `no_hp`, `sso_sub`, `sumber_akun`, `email_dikunci`,
   `no_hp_dikunci`, dan `ehrm_sinkron_at` di `User`, serta buat tabel `PeranUser`.
2. Data migration:
   - untuk setiap `User`, buat `PeranUser(role=user.role, unit_organisasi=user.unit_organisasi
     bila admin_unor)`;
   - set `sumber_akun="lokal"`.
3. User lama yang punya `PegawaiProfile`: saat login SSO pertama, akun dikaitkan
   berdasarkan **NIP** (`sso_sub` diisi, `sumber_akun` diubah menjadi `sso`), dan
   password lama tetap berlaku.
4. User lama tanpa `no_hp` mendapat nomor dari e-HRM saat login SSO berikutnya. Akun
   lokal tanpa nomor HP dilengkapi Admin Biro PAKLN lewat filter **Tanpa No. HP**.
5. Admin non-PAKLN lama yang **tidak punya NIP**, misalnya akun admin seed generik,
   tetap berlaku sebagai **akun admin darurat** (lokal). Bila orangnya sebenarnya
   pegawai, Admin Biro PAKLN dapat memindahkan role-nya ke akun SSO pegawai tersebut,
   lalu menonaktifkan akun lama.
6. Seed (`seed_demo_data`, `seed_admin_unor_org_units`, `seed_pegawai_org_units`):
   - isi `PeranUser` dan `no_hp` dummy;
   - tambahkan minimal satu user demo ber-role ganda (Pegawai + Admin Unor).

## 12. Rencana Implementasi per Fase

| Fase | Isi | Keluaran |
|---|---|---|
| **1. Nomor HP & kontak** | `User.no_hp` + normalisasi (`accounts/validators.py`), field kunci, `no_hp`/`email` wajib di Tambah User dan bisa diubah di Edit User (Admin Biro PAKLN), filter "Tanpa No. HP", banner, filter template `wa_link`, tautan WhatsApp di Profil, Kelola User, dan detail pengajuan. | Semua user bisa memiliki nomor HP dan dihubungi via tautan WhatsApp. |
| **2. Akun mandiri** | Bagian Akun & Keamanan di Profil: `UbahUsernameForm`, `AturPasswordForm`, `GantiPasswordForm`, hapus password, serta `KontakForm` untuk Admin Biro PAKLN. Pemeriksaan password *unusable* di `login_view` (pesan "gunakan SSO"). | Pengguna bisa mengubah username dan mengatur/mengganti password sendiri. |
| **3. Role ganda** | Model `PeranUser` + data migration, `PeranAktifMiddleware`, switcher peran, refactor `notifications/services.py` & `views_unor.py` (termasuk dedup penerima), guard AB-12, UI kelola peran di Admin Biro PAKLN. | Satu akun bisa punya banyak role. |
| **4. e-HRM** | `paspor/integrasi/ehrm.py` (stub + HTTP), `sinkron_profil` (dengan kunci email/HP), tombol sinkron ulang & kembalikan ke e-HRM, tanda "terakhir sinkron", pra-daftar via NIP. | Data personal dan kontak bersumber dari e-HRM. |
| **5. SSO** | `masuk_dari_sso` + stub DEBUG, adaptor protokol (menunggu Q1), URL login/callback, tombol di halaman login, provisioning JIT, penautan berdasarkan NIP, env & dokumentasi deploy. | Login SSO berjalan end-to-end. |
| **6. Pembersihan** | Hapus `User.unit_organisasi` (setelah semua beralih ke `PeranUser`), sederhanakan `TambahUserForm`, perbarui wiki (BISNIS_PROSES_PDLN §3, perancangan/05_CLASS_ERD). | Tidak ada jalur ganda. |

Fase 1–4 bisa dikerjakan sekarang (Fase 4 memakai stub sampai spesifikasi API e-HRM
tersedia). Adaptor protokol di Fase 5 menunggu jawaban Q1, tetapi alur di belakangnya
(`masuk_dari_sso`) bisa disiapkan dan dites memakai stub.

## 13. Test

**Nomor HP**

- Normalisasi `0812-3456-7890`, `+62 812 3456 7890`, dan `6281234567890` menghasilkan
  `6281234567890`.
- Input huruf atau yang terlalu pendek/panjang ditolak.
- Filter `wa_link` menghasilkan `https://wa.me/6281234567890`.

**Edit profil**

- POST oleh Pegawai/Admin Unor/BPSDM/BKO yang menyertakan `email`/`no_hp`/`nama`/`nip`/`role`
  tidak mengubah field tersebut (whitelist).
- Admin Biro PAKLN bisa mengubah email & nomor HP miliknya sendiri, tetapi tetap tidak
  bisa mengubah `nama`/`nip`/`role` lewat Edit Profil.
- User ber-role ganda (Pegawai + Admin Biro PAKLN) hanya bisa mengubah email/nomor HP
  saat peran aktifnya Admin Biro PAKLN.
- Username duplikat (beda huruf besar/kecil) ditolak.

**Kontak oleh Admin Biro PAKLN**

- Admin Biro PAKLN mengubah nomor HP user lain, lalu `no_hp_dikunci=True`.
- Sinkronisasi e-HRM berikutnya tidak menimpa nomor itu.
- Setelah "Kembalikan ke data e-HRM", sinkronisasi menimpanya lagi.
- Role selain Admin Biro PAKLN tidak bisa mengakses endpoint ubah kontak.

**Banner**

- User dengan `no_hp` kosong melihat banner.
- User tersebut muncul pada filter "Tanpa No. HP".

**Password**

- Akun SSO tanpa password bisa mengatur password tanpa password lama.
- Akun berpassword wajib memasukkan password lama.
- Setelah password diganti, sesi tetap aktif.
- Akun dengan password *unusable* gagal login lewat form.
- Hapus password ditolak untuk akun lokal (tanpa `sso_sub`).

**Role ganda**

- User Pegawai + Admin Unor:
  - mengganti peran mengubah sidebar dan akses `role_required`;
  - tidak bisa memverifikasi pengajuannya sendiri (AB-12);
  - menerima notifikasi Admin Unor untuk unit yang dikelolanya, dan notifikasi yang
    sama tidak terkirim dua kali.
- Peran yang tidak dimiliki tidak bisa dipilih lewat POST manual.
- `request.user.role` hasil override tidak tersimpan ke database setelah `user.save()`.

**Akun admin darurat**

- Admin Biro PAKLN membuat Admin Unor lokal tanpa NIP.
- Akun tersebut bisa login dengan username/password dan tidak memiliki role Pegawai.

**e-HRM (stub)**

- Login SSO pertama membuat `User` + `PegawaiProfile` + `PeranUser(pegawai)`, lengkap
  dengan email dan nomor HP dari e-HRM.
- Login berikutnya memperbarui jabatan.
- Saat e-HRM gagal: user lama tetap bisa login, user baru ditolak.

**SSO (via `masuk_dari_sso`)**

- NIP yang sudah ada dikaitkan ke akun lama, tidak membuat akun baru.
- User nonaktif ditolak.
- Validasi `state`/`nonce` ditambahkan setelah protokol diputuskan.

## 14. Keputusan & Pertanyaan Terbuka

| No | Pertanyaan | Status | Keputusan |
|---|---|---|---|
| Q1 | Protokol dan penyedia SSO apa yang dipakai (OIDC/Keycloak, SAML, CAS)? Klaim apa yang tersedia (NIP?) | **Terbuka** | Belum ada jawaban. Dikerjakan dengan asumsi OIDC dan alur `masuk_dari_sso` yang tidak bergantung pada protokol (§9.1). |
| Q2 | Spesifikasi API e-HRM? Apakah e-HRM menyediakan email & nomor HP? | Sebagian | e-HRM **menyediakan** email & nomor HP. Perubahan nomor HP (dan email) pegawai/admin lain hanya oleh Admin Biro PAKLN. Endpoint & autentikasi API masih menunggu spesifikasi. |
| Q3 | Apa saja yang boleh diubah Admin Biro PAKLN di profilnya sendiri? | Diputuskan | **Username, password, email, dan nomor HP.** Konsisten dengan wewenang Admin Biro PAKLN mengubah email & nomor HP (AB-16, AB-17). Perluasan lain (misalnya nama) dibahas belakangan. |
| Q4 | Apakah perubahan email/nomor HP perlu verifikasi OTP? | Diputuskan | **Tidak.** Email & nomor HP hanya diubah Admin Biro PAKLN, sehingga Edit Profil pengguna hanya berisi **username & password**. |
| Q5 | Apakah user boleh menonaktifkan login username/password (kembali ke SSO saja)? | Diputuskan | **Ya**, lewat tombol "Hapus password" (`set_unusable_password`), khusus akun yang memiliki kaitan SSO (AB-07). |
| Q6 | Apakah admin non-PAKLN tetap boleh dibuat manual tanpa SSO (akun darurat)? | Diputuskan | **Tetap bisa.** Admin Biro PAKLN dapat membuat akun lokal Admin Unor/BPSDM/BKO (AB-05, §8). |
| Q7 | Notifikasi untuk user ber-role ganda: digabung atau dipisah per peran aktif? | Diputuskan | **Digabung** (AB-13). |
| Q8 | Apakah single logout ke SSO diperlukan? | Diputuskan | **Tidak**; logout hanya mengakhiri sesi PASPOR. |
| Q9 | Apakah pengiriman notifikasi lewat WhatsApp termasuk lingkup sekarang? | Diputuskan | **Tidak.** Nomor WhatsApp hanya berupa tautan `wa.me` yang membuka aplikasi WhatsApp; komunikasi dilakukan di luar sistem (AB-22). |
