# Rencana Implementasi — Pendaftaran Akun Pegawai (SSO & eHRM)

> **Status:** rancangan — belum ada kode yang diubah.
> - Bagian **eHRM** (pendaftaran oleh Admin Biro PAKLN / Admin Unor, sinkron data) **dapat dikembangkan** sekarang.
> - Bagian **SSO** (login & pendaftaran mandiri) **belum dapat dikembangkan** sampai client IdP, issuer,
>   dan redirect URI PASPOR tersedia ([§16](#16-keputusan-default--pertanyaan-terbuka) #1–#4).
>
> **Sumber:** [IMPLEMENTASI_SSO_PENAMBAHAN_PEGAWAI.MD](IMPLEMENTASI_SSO_PENAMBAHAN_PEGAWAI.MD) (panduan porting dari EILN)
> dan konfigurasi `.env` PASPOR. Panduan sumber ditulis untuk proyek Django generik
> (model `Pengguna`/`Pegawai`/`UnitKerja` baru); rencana ini menyesuaikannya dengan model PASPOR.
> **Terkait:** [BISNIS_PROSES_PDLN.MD](BISNIS_PROSES_PDLN.MD) §3 & §9, [SYSTEM_LOGGING.MD](SYSTEM_LOGGING.MD),
> [SKENARIO_NOTIFIKASI_SURAT.md](SKENARIO_NOTIFIKASI_SURAT.md), [PASPOR_DESIGN_GUIDE.MD](PASPOR_DESIGN_GUIDE.MD).

---

## Daftar Isi

1. [Tujuan & Ruang Lingkup](#1-tujuan--ruang-lingkup)
2. [Kondisi Saat Ini](#2-kondisi-saat-ini)
3. [Konsep & Istilah](#3-konsep--istilah)
4. [Aktor & Hak Akses](#4-aktor--hak-akses)
5. [Aturan Bisnis](#5-aturan-bisnis)
6. [Proses Bisnis](#6-proses-bisnis)
7. [Rancangan Flow & Status](#7-rancangan-flow--status)
8. [Perancangan Data](#8-perancangan-data)
9. [Konfigurasi & `.env`](#9-konfigurasi--env)
10. [Komponen Kode](#10-komponen-kode)
11. [Rancangan Halaman](#11-rancangan-halaman)
12. [Notifikasi](#12-notifikasi)
13. [Keamanan](#13-keamanan)
14. [Log Sistem](#14-log-sistem)
15. [Rencana Implementasi per Fase & Test](#15-rencana-implementasi-per-fase--test)
16. [Keputusan Default & Pertanyaan Terbuka](#16-keputusan-default--pertanyaan-terbuka)

---

## 1. Tujuan & Ruang Lingkup

SSO dan integrasi eHRM dipakai untuk **mendaftarkan akun pegawai ke PASPOR** dengan data
kepegawaian yang benar (dari eHRM), lewat tiga jalur:

| Jalur | Pemicu | Hasil |
|---|---|---|
| **A. Pendaftaran mandiri** | Pegawai menekan "Login dengan SSO" dan belum punya akun PASPOR | Akun Pegawai dibuat otomatis bila identitasnya terverifikasi eHRM; bila tidak, menjadi **permohonan** yang diverifikasi admin |
| **B. Didaftarkan Admin Biro PAKLN** | Admin memasukkan NIP di Manajemen User | Akun Pegawai unit mana pun |
| **C. Didaftarkan Admin Unor** | Admin Unor memasukkan NIP di menu Pegawai Unor | Akun Pegawai **hanya untuk unit organisasinya** |

Akun dari ketiga jalur login melalui SSO. Login username/password lokal tetap ada untuk
akun admin, akun demo, dan pegawai non-ASN yang tidak ada di eHRM.

Di luar cakupan: pembuatan akun **admin** lewat SSO (tetap manual oleh Admin Biro PAKLN),
sinkron master unit kerja eHRM 8 digit, login OTP/JWT lama EILN.

---

## 2. Kondisi Saat Ini

| Area | PASPOR sekarang |
|---|---|
| Akun | `accounts.User` (`AbstractUser`) + `role` (pegawai, admin_unor, admin_bpsdm, admin_pakln, admin_bko), `unit_kerja`, `unit_organisasi` |
| Data pegawai | `accounts.PegawaiProfile` (1:1 User): `nip` unik, `nama`, `jabatan`, `pangkat_golongan`, `unit_kerja`, `unit_organisasi`, `sisa_cuti_tahun_berjalan` |
| Unit | `paspor.UnitOrganisasi` (`org_units`, `code` **2 digit**, 11 unit eselon I) |
| Login | `accounts.views.login_view` (username/password). Tombol "Login dengan SSO" di `registration/login.html` masih placeholder |
| Tambah akun | Hanya Admin Biro PAKLN → Manajemen User (`TambahUserForm`), input manual, password wajib |
| Notifikasi | In-app (`notifications.Notification`, penerima = User). **Belum ada pengiriman email** walau `.env` berisi blok `MAIL_*` |
| Log | `logs.ActivityLog` + `record_activity`; login dicatat signal `user_logged_in` / `user_login_failed` |
| `.env` | Dimuat `_load_dotenv` di `settings.py`; blok `SSO_*` dan `EHRM_*` sudah ada tetapi belum dibaca kode |

---

## 3. Konsep & Istilah

| Istilah | Arti di PASPOR |
|---|---|
| **Akun** | `accounts.User`. Di PASPOR pegawai adalah pengguna — tidak ada pemisahan `Pengguna`/`Pegawai` seperti EILN |
| **Profil pegawai** | `PegawaiProfile` — data kepegawaian (NIP, nama, jabatan, golongan, unit) yang bersumber dari eHRM atau input manual |
| **Identitas SSO** | Klaim dari IdP: `sub` (ID tetap), `email`, `preferred_username`, dan — bila disediakan — `nip` |
| **Tautan SSO** | `User.sso_subject` = `sub` IdP. Sekali tertaut, login SSO berikutnya langsung dikenali walau email di IdP berubah |
| **Verifikasi identitas** | Bukti bahwa orang yang login SSO adalah pemilik NIP: `nip` dari klaim sama dengan NIP, **atau** `email` klaim sama dengan `email_pu`/`email` pegawai di eHRM |
| **Permohonan akun** | `PermohonanAkun` — pendaftaran mandiri yang belum bisa diaktifkan otomatis dan menunggu Admin Unor / Admin Biro PAKLN |
| **Pemetaan unit** | 2 digit pertama `kdunit` eHRM → `UnitOrganisasi.code` |

---

## 4. Aktor & Hak Akses

| Aktor | Daftar pegawai via eHRM | Daftar manual | Verifikasi permohonan | Sinkron eHRM | Kelola tautan SSO | Buat akun admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| **Pegawai** (belum punya akun) | mandiri via SSO (jalur A) | — | — | — | — | — |
| **Pegawai** (sudah punya akun) | — | — | — | profilnya sendiri ([§16](#16-keputusan-default--pertanyaan-terbuka) #10) | — | — |
| **Admin Unor** | unit sendiri | unit sendiri | permohonan unit sendiri | pegawai unit sendiri | — | — |
| **Admin Biro PAKLN** | semua unit | semua unit | semua (termasuk unit tak terpetakan) | semua | lepas tautan | ✅ |
| Admin BPSDM, Admin BKO | — | — | — | — | — | — |

---

## 5. Aturan Bisnis

### 5.1 Umum

| # | Aturan |
|:-:|---|
| B1 | **SSO opsional**: aktif bila `SSO_ISSUER`, `SSO_CLIENT_ID`, `SSO_CLIENT_SECRET` terisi. Bila tidak, tombol SSO tersembunyi dan pendaftaran mandiri tidak tersedia. |
| B2 | **eHRM opsional**: aktif bila semua `EHRM_*` terisi. Bila tidak, pendaftaran oleh admin hanya manual, dan pendaftaran mandiri selalu menjadi permohonan (B13). |
| B3 | **Satu NIP = satu akun.** `PegawaiProfile.nip` unik; satu `sso_subject` hanya tertaut ke satu akun. |
| B4 | Akun yang dibuat lewat SSO/eHRM tidak punya password yang dapat dipakai (`set_unusable_password`) — login hanya via SSO, kecuali admin menetapkan password lokal. |
| B5 | Role akun hasil SSO/eHRM **selalu Pegawai**. Perubahan role hanya oleh Admin Biro PAKLN. |
| B6 | Data dari eHRM yang disimpan: nama, jabatan, golongan, unor, unit kerja, `kdunit`, eselon, email PU. **Tidak disimpan**: NIK (`noktp`), telepon, foto. |
| B7 | **Pemetaan unit**: `kdunit[:2]` → `UnitOrganisasi.code`. Tidak cocok → unit dipilih admin (jalur B), ditolak (jalur C), atau permohonan ke Admin Biro PAKLN (jalur A). |

### 5.2 Login SSO & penautan

| # | Aturan |
|:-:|---|
| B8 | Pencocokan akun berurutan: (1) `sso_subject = sub`; (2) klaim `nip` = `PegawaiProfile.nip`; (3) klaim `SSO_USERNAME_CLAIM` (sekarang `email`) = `User.email` (tanpa beda huruf besar/kecil); (4) = `User.username`. Hanya akun **aktif**. Lebih dari satu kecocokan → ditolak & dicatat. |
| B9 | Login SSO pertama yang cocok lewat (2)–(4) **menautkan** akun: isi `sso_subject` (dan `email` bila kosong). Akun yang sudah tertaut ke `sub` lain **tidak** ditautkan ulang — ditolak, minta Admin Biro PAKLN melepas tautan. |
| B10 | Akun nonaktif (`is_active=False`) selalu ditolak, termasuk lewat SSO. |
| B11 | Akun **admin** tidak pernah dibuat lewat SSO; admin hanya bisa login SSO bila akunnya sudah dibuat dan cocok (B8). |

### 5.3 Pendaftaran mandiri (jalur A)

| # | Aturan |
|:-:|---|
| B12 | Bila login SSO tidak menemukan akun dan `PENDAFTARAN_MANDIRI_AKTIF=true`, pegawai diarahkan ke **Lengkapi Pendaftaran**: NIP diambil dari klaim `nip` bila ada, selain itu diketik pegawai. |
| B13 | Akun **langsung aktif** bila semua terpenuhi: eHRM aktif, data NIP ditemukan, identitas terverifikasi (klaim `nip` = NIP, atau klaim `email` = `email_pu`/`email` eHRM), unit terpetakan, NIP belum punya akun. Selain itu dibuat **permohonan akun** (bila tidak bertentangan dengan B14). |
| B14 | Ditolak tanpa permohonan bila NIP **sudah punya akun** yang tertaut ke `sub` lain (B9), atau sudah ada permohonan **menunggu** untuk NIP/`sub` yang sama (pegawai diarahkan ke halaman status). |
| B15 | NIP sudah punya akun yang **belum tertaut** SSO dan identitas terverifikasi → akun lama **ditautkan** (bukan dibuat baru) — kasus akun yang dulu dibuat manual. |
| B16 | Permohonan diverifikasi **Admin Unor** unit hasil pemetaan; bila unit tak terpetakan, oleh **Admin Biro PAKLN**. Admin Biro PAKLN dapat memutus permohonan unit mana pun. |
| B17 | Setuju → akun Pegawai dibuat dan ditautkan ke `sub` permohonan. Tolak → catatan wajib; pegawai dapat mengajukan ulang setelah memperbaiki data. |
| B18 | Opsi `PENDAFTARAN_MANDIRI_SELALU_VERIFIKASI=true` membuat semua pendaftaran mandiri menjadi permohonan (tidak ada aktivasi otomatis) — untuk masa uji coba. |

### 5.4 Pendaftaran oleh admin (jalur B & C)

| # | Aturan |
|:-:|---|
| B19 | NIP 18 digit; pratinjau eHRM wajib sebelum simpan. NIP yang sudah punya akun ditolak dengan tawaran **Sinkron**. |
| B20 | `username` = bagian lokal `email_pu` (sebelum `@`) → NIP bila tidak tersedia/terpakai; `User.email` = `email_pu` (bila ada) → `email` eHRM, agar cocok dengan klaim SSO. |
| B21 | **Admin Unor** hanya dapat mendaftarkan pegawai yang unit hasil pemetaannya = unit organisasinya; input manual Admin Unor terkunci ke unitnya. |
| B22 | Input manual (eHRM tidak aktif/tidak ditemukan, pegawai non-ASN): password lokal wajib, `sumber = manual`. Akun manual tetap dapat ditautkan ke SSO di login pertama (B8–B9). |
| B23 | Bila ada **permohonan menunggu** untuk NIP yang didaftarkan admin, permohonan otomatis ditandai *disetujui* dan akun ditautkan ke `sub` permohonan tersebut. |

### 5.5 Sinkron

| # | Aturan |
|:-:|---|
| B24 | Sinkron memperbarui field B6 dan unit organisasi. Field milik PASPOR (`sisa_cuti_tahun_berjalan`, role, password, paspor, dokumen kepegawaian) tidak disentuh. Snapshot pengajuan yang sudah dikirim (mis. `Pengajuan.unit_organisasi`) tidak berubah. |
| B25 | Bila sinkron memindahkan pegawai ke unit lain, Admin Unor lama kehilangan akses ke pegawai tersebut untuk pengajuan **baru**; pengajuan berjalan tetap di unit snapshot-nya. |
| B26 | Sinkron otomatis saat login SSO (opsional, `EHRM_SINKRON_SAAT_LOGIN_HARI`) tidak boleh menggagalkan login bila eHRM error. |

---

## 6. Proses Bisnis

### 6.1 Proses A1 — Login SSO (akun sudah ada)

1. Pegawai/admin menekan **Login dengan SSO PU** → login di IdP → kembali ke PASPOR.
2. Sistem mencocokkan akun (B8). Cocok & aktif → tautkan bila perlu (B9) → masuk ke beranda/dasbor sesuai role.
3. Akun nonaktif / tertaut ke `sub` lain / ganda → halaman login dengan pesan dan saran menghubungi admin.

### 6.2 Proses A2 — Pendaftaran mandiri via SSO

1. Login SSO tidak menemukan akun (B8) → halaman **Lengkapi Pendaftaran** (tanpa sesi login PASPOR;
   identitas SSO disimpan sementara di sesi, maks. 15 menit).
2. NIP: otomatis dari klaim `nip`, atau diketik pegawai. Sistem memanggil eHRM dan menampilkan
   ringkasan (nama, jabatan, unit) — pegawai mencentang pernyataan "Data ini adalah data saya".
3. Sistem mengevaluasi B13–B15:
   - **Terverifikasi** → akun dibuat (atau akun lama ditautkan, B15) → langsung masuk PASPOR
     dengan pesan "Akun PASPOR Anda berhasil dibuat".
   - **Belum terverifikasi** (email tidak cocok, eHRM tidak aktif/tidak menemukan NIP, unit tak
     terpetakan) → pegawai melengkapi isian permohonan (nama, unit organisasi, unit kerja, jabatan,
     golongan; NIP wajib) → **permohonan** dikirim → halaman **Status Pendaftaran**.
   - **Ditolak** (B14) → pesan dengan arahan (hubungi Admin Unor / lihat status permohonan).
4. Login SSO berikutnya selama permohonan menunggu/ditolak → langsung ke halaman **Status Pendaftaran**
   (status, unit tujuan, catatan penolakan, tombol "Ajukan ulang" bila ditolak).

### 6.3 Proses A3 — Verifikasi permohonan (Admin Unor / Admin Biro PAKLN)

1. Notifikasi + badge menu **Pegawai Unor → Permohonan Akun** (Admin Unor) atau
   **Manajemen User → Permohonan Akun** (Admin Biro PAKLN).
2. Admin membuka permohonan: identitas SSO (email, nama di IdP), data isian pegawai, dan —
   bila eHRM aktif — data eHRM untuk NIP tersebut berdampingan, dengan penanda kecocokan.
3. **Setujui** → akun Pegawai dibuat (data eHRM bila tersedia, selain itu isian permohonan;
   unit boleh dikoreksi admin dalam cakupannya) dan ditautkan ke `sub` permohonan (B17).
4. **Tolak** → catatan wajib (mis. "NIP tidak sesuai data kepegawaian Unor").
5. Pegawai melihat hasilnya saat login SSO berikutnya (dan lewat email bila diaktifkan, §12).

### 6.4 Proses B — Pendaftaran oleh Admin Biro PAKLN

1. Manajemen User → tab **Dari eHRM (NIP)** → ketik NIP → pratinjau otomatis.
2. NIP sudah punya akun → tampil "Sudah terdaftar" + tombol **Sinkron**.
3. Konfirmasi unit organisasi (terisi hasil pemetaan, boleh diubah) → **Simpan Pegawai** →
   akun dibuat tanpa password lokal (B4, B20), dan permohonan menunggu untuk NIP itu ikut
   diselesaikan (B23).
4. Tab **Manual** tetap untuk non-ASN/eHRM tidak aktif (form sekarang, password wajib).

### 6.5 Proses C — Pendaftaran oleh Admin Unor

Sama dengan Proses B, pada menu baru **Pegawai Unor**, dengan batas B21: pratinjau
menampilkan unit hasil pemetaan; bila bukan unitnya, tombol Simpan nonaktif dengan pesan
"Pegawai ini terdaftar di unit {X} pada eHRM. Hubungi Admin Unor {X} atau Admin Biro PAKLN."

### 6.6 Proses D — Sinkron data pegawai

- Tombol **↻ Sinkron dari eHRM** di detail pegawai (Admin Biro PAKLN: semua; Admin Unor: unitnya).
- Opsional di login SSO bila data lebih lama dari N hari (B26).
- Hasil: ringkasan perubahan ("Jabatan: A → B; Unit: SDA → BM") ditampilkan & dicatat di log.

---

## 7. Rancangan Flow & Status

### 7.1 Login & pendaftaran mandiri

```
                [Login dengan SSO PU] → IdP → /oidc/callback/
                                   │
                         cocokkan akun (B8)
           ┌───────────────┬───────┴─────────────┬──────────────────────────┐
     cocok, aktif     cocok, nonaktif /     tidak cocok               ada permohonan
           │          tertaut sub lain /         │                    menunggu/ditolak
   tautkan (B9)       ganda                      │                         │
           │               │              [Lengkapi Pendaftaran]     [Status Pendaftaran]
     MASUK PASPOR     TOLAK + pesan       NIP (klaim / input) → eHRM
                                                 │
                     ┌───────────────────────────┼─────────────────────────────┐
              terverifikasi & unit OK     NIP punya akun belum         tidak terverifikasi /
              & NIP belum punya akun      tertaut & terverifikasi      eHRM gagal / unit ?
                     │                           │                             │
             BUAT AKUN PEGAWAI            TAUTKAN AKUN LAMA          [isian permohonan]
                     │                           │                             │
               MASUK PASPOR                MASUK PASPOR           PERMOHONAN (menunggu)
                                                                  → Admin Unor / PAKLN
```

### 7.2 Status permohonan akun

```
 pegawai kirim ──► [menunggu] ──setujui──► [disetujui] → akun dibuat & ditautkan
                       │
                       ├──tolak (catatan)──► [ditolak] ──ajukan ulang──► [menunggu] (baris baru)
                       │
                       └──admin daftarkan NIP yang sama (B23)──► [disetujui]
                       └──dibatalkan pegawai──► [dibatalkan]
```

### 7.3 Siklus akun pegawai

```
 (tidak ada) ──jalur A/B/C──► [aktif, sumber=sso|ehrm|manual]
                                  │  login SSO pertama → tertaut (sso_subject terisi)
                                  │  sinkron eHRM → data diperbarui
                                  └──dinonaktifkan Admin Biro PAKLN──► [nonaktif] ──aktifkan──┘
```

---

## 8. Perancangan Data

### 8.1 `accounts.User` — field baru

| Field | Tipe | Keterangan |
|---|---|---|
| `sso_subject` | `CharField(255)`, `null=True`, `unique=True` | Klaim `sub` IdP (B9). NULL agar unique hanya berlaku untuk yang terisi |
| `sso_tertaut_pada` | `DateTimeField`, null | Waktu penautan pertama |
| `sumber_akun` | `CharField(10)` choices `manual` / `ehrm` / `sso` | `manual` = form admin; `ehrm` = admin dari NIP eHRM; `sso` = pendaftaran mandiri |
| `didaftarkan_oleh` | `FK User` (`SET_NULL`, null) | Admin pembuat akun (kosong untuk mandiri) |

`email` (bawaan) = email notifikasi & kunci pencocokan klaim `email`; keunikan dicek di layanan/form.

### 8.2 `accounts.PegawaiProfile` — field baru

| Field | Tipe | Sumber eHRM |
|---|---|---|
| `email_pu` | `EmailField`, blank | `email_pu` |
| `golongan` | `CharField(10)`, blank | `golongan` (`pangkat_golongan` tetap diisi `deskripsi_gol`) |
| `eselon` | `CharField(10)`, blank | `eselon` |
| `unor_ehrm` | `CharField(255)`, blank | `unor` |
| `kdunit_ehrm` | `CharField(20)`, blank | `kdunit` asli |
| `sumber` | `CharField(10)` choices `manual` / `ehrm`, default `manual` | — |
| `tgl_sinkron_ehrm` | `DateTimeField`, null | Sinkron terakhir |

Pemetaan field lama: `nip ← nip`, `nama ← nama`, `jabatan ← jabatan_lengkap || jabatan`,
`pangkat_golongan ← deskripsi_gol || golongan`, `unit_kerja ← unker`, `unit_organisasi ← pemetaan(kdunit)`.

### 8.3 `accounts.PermohonanAkun` (baru)

| Field | Tipe | Keterangan |
|---|---|---|
| `sso_subject` | `CharField(255)` | `sub` pemohon |
| `sso_email` | `EmailField`, blank | Klaim `email` |
| `sso_nama` | `CharField(150)`, blank | Klaim `name` |
| `nip` | `CharField(20)` | |
| `nama`, `jabatan`, `pangkat_golongan`, `unit_kerja` | `CharField` | Isian pegawai (diisi otomatis dari eHRM bila tersedia) |
| `unit_organisasi` | `FK UnitOrganisasi` (`PROTECT`, null) | Unit tujuan verifikasi; NULL = Admin Biro PAKLN |
| `data_ehrm` | `JSONField`, null | Ringkasan eHRM saat diajukan (hanya field B6) untuk dibandingkan admin |
| `alasan_verifikasi` | `CharField(30)` choices `email_tidak_cocok` / `ehrm_tidak_aktif` / `nip_tidak_ditemukan` / `unit_tidak_terpetakan` / `wajib_verifikasi` | Mengapa tidak aktif otomatis |
| `status` | `CharField(12)` choices `menunggu` / `disetujui` / `ditolak` / `dibatalkan`, index | |
| `diputus_oleh` | `FK User` (`SET_NULL`, null) | |
| `tgl_diputus` | `DateTimeField`, null | |
| `catatan_keputusan` | `TextField`, blank | Wajib saat ditolak |
| `user` | `FK User` (`SET_NULL`, null) | Akun yang dibuat saat disetujui |
| `created_at`, `updated_at` | | |

Keunikan "maksimal satu permohonan menunggu per NIP dan per `sso_subject`" ditegakkan di
layanan dengan `select_for_update` (MySQL tidak mendukung conditional unique constraint —
pola yang sama dengan `PermohonanPembatalan`).

### 8.4 `paspor.TokenIntegrasi` (baru)

| Field | Tipe | Keterangan |
|---|---|---|
| `nama` | `CharField(30)`, unique | `ehrm` (dapat dipakai integrasi lain) |
| `token` | `TextField` | `session_token` eHRM |
| `kedaluwarsa` | `DateTimeField` | `now + 24 jam` |
| `updated_at` | `DateTimeField` auto | |

### 8.5 Diagram relasi

```
                     ┌──────────────── didaftarkan_oleh ───────────────┐
                     ▼                                                  │
 UnitOrganisasi ◄── User (role, sso_subject, sumber_akun, email) ───────┘
       ▲   ▲           │ 1:1
       │   │           ▼
       │   └──── PegawaiProfile (nip unik, data eHRM, tgl_sinkron_ehrm)
       │
       └──── PermohonanAkun (sso_subject, nip, status) ── user ──► User (setelah disetujui)
                                                        ── diputus_oleh ──► User (admin)
 TokenIntegrasi (cache token eHRM)
```

### 8.6 Migrasi

| Migrasi | Isi |
|---|---|
| `accounts/0008_pendaftaran_akun` | Field §8.1 & §8.2, model `PermohonanAkun`. Data lama: `sumber_akun = manual`, `PegawaiProfile.sumber = manual` |
| `paspor/00xx_tokenintegrasi` | Model §8.4 |
| `notifications/00xx_event_akun` | Event §12 |

---

## 9. Konfigurasi & `.env`

### 9.1 Variabel yang sudah ada di `.env`

| Variabel | Isi saat ini | Catatan |
|---|---|---|
| `SSO_ISSUER` | `https://sso.example.go.id/realms/pu` | **Masih contoh** — perlu issuer sebenarnya. Pola `/realms/…` = Keycloak |
| `SSO_CLIENT_ID` | `eiln` | Client milik EILN — perlu client PASPOR atau redirect URI tambahan (§16 #1) |
| `SSO_CLIENT_SECRET` | terisi | Rahasia |
| `SSO_SCOPE` | `openid profile email` | |
| `SSO_NAME` | `SSO PU` | Label tombol |
| `SSO_USERNAME_CLAIM` | `email` | Dicocokkan ke `User.email` (B8) |
| `SSO_AUTO_PROVISION` | `false` | Digantikan `PENDAFTARAN_MANDIRI_AKTIF` (lebih tepat: pendaftaran mandiri tetap melalui verifikasi eHRM/admin). Tetap dibaca sebagai alias |
| `EHRM_LOGIN_URL` | `https://apigw.pu.go.id/user/login` | |
| `EHRM_EMAIL`, `EHRM_PASSWORD`, `EHRM_API_KEY` | terisi | Akun layanan eHRM — rahasia |
| `EHRM_PEGAWAI_API_URL` | `http://apigw.pu.go.id/v1/ehrm/pegawai` | **`http`** — token & API key terkirim tanpa enkripsi; minta endpoint `https` (§13) |

Alias EILN (`SSOBaseUrl`, `SSOClientId`, `SSOClientSecret`) diterima sebagai fallback.

### 9.2 Variabel baru

| Variabel | Default | Fungsi |
|---|---|---|
| `PENDAFTARAN_MANDIRI_AKTIF` | `false` | Jalur A (B12) |
| `PENDAFTARAN_MANDIRI_SELALU_VERIFIKASI` | `false` | B18 |
| `SSO_NIP_CLAIM` | kosong | Nama klaim berisi NIP bila IdP menyediakannya (mis. `nip`) |
| `SSO_SIGN_ALGO` | `RS256` | |
| `SSO_LOGOUT_IDP` | `true` | Logout juga dari IdP bila `end_session_endpoint` ada |
| `EHRM_TIMEOUT` | `20` | Detik |
| `EHRM_SINKRON_SAAT_LOGIN_HARI` | `0` (mati) | B26 |

`.env.example` belum berisi blok `SSO_*`/`EHRM_*` — ditambahkan dengan placeholder (tanpa nilai rahasia).

### 9.3 Redirect URI di IdP

| Lingkungan | Callback | Post-logout |
|---|---|---|
| Development | `http://localhost:8000/oidc/callback/` | `http://localhost:8000/login/` |
| Staging/produksi | `https://<host-paspor>/oidc/callback/` | `https://<host-paspor>/login/` |

Redirect URI dibuka oleh **browser pengguna** — server IdP tidak perlu menjangkau PASPOR, tetapi
server PASPOR harus menjangkau IdP (penukaran token) dan `apigw.pu.go.id` (eHRM). Pergantian
domain hanya memerlukan penambahan redirect URI di IdP, bukan perubahan kode. Di belakang
reverse proxy, atur `SECURE_PROXY_SSL_HEADER` agar callback memakai `https`.

---

## 10. Komponen Kode

| Komponen | Berkas | Isi |
|---|---|---|
| Library OIDC | `requirements.txt` | `mozilla-django-oidc` (state, nonce, PKCE, verifikasi JWKS). **Verifikasi dukungan Django 6.1** di Fase 0; alternatif Authlib. `requests` untuk eHRM |
| Settings | `paspor_project/settings.py` | Baca §9; `SSO_ENABLED`, `EHRM_ENABLED`; backend OIDC sebelum `ModelBackend`; PKCE S256; `OIDC_STORE_ID_TOKEN`. Endpoint IdP **tidak** di-discover saat import settings (panduan sumber melakukannya → aplikasi gagal start bila IdP mati) |
| Backend SSO | `accounts/sso.py` | Discovery lazy + cache 1 jam; `PasporOIDCBackend`: `filter_users_by_claims` (B8), `verify_claims` (cukup `sub`), `get_userinfo` (gabung id_token + userinfo), `update_user` (B9, B26). Bila tidak ada akun → **tidak** membuat user; menyimpan identitas SSO di sesi dan mengarahkan ke Lengkapi Pendaftaran |
| Klien eHRM | `paspor/integrasi/ehrm.py` | `token()` (cache `TokenIntegrasi`, `select_for_update`), `ambil_pegawai(nip)` (header DreamFactory, retry sekali bila 401), hasil `DataPegawaiEhrm` hanya field B6, `EhrmError` / `EhrmTidakAktif` |
| Layanan akun | `accounts/pendaftaran.py` | `petakan_unit`, `pratinjau(nip, aktor)`, `buat_pegawai_dari_ehrm`, `buat_pegawai_manual`, `daftar_mandiri(identitas_sso, nip)` → `AKTIF / DITAUTKAN / PERMOHONAN / DITOLAK`, `setujui_permohonan`, `tolak_permohonan`, `sinkron_pegawai`, `lepas_tautan_sso` |
| View | `accounts/views.py` (login, logout, `pendaftaran_lengkapi`, `pendaftaran_status`), `pengajuan/views_pakln.py` (Manajemen User + permohonan), `pengajuan/views_unor.py` (menu Pegawai Unor) | |
| URL | `paspor_project/urls.py` | `/oidc/` (bila SSO aktif), `/daftar/lengkapi/`, `/daftar/status/` |
| Form | `accounts/forms.py` | `PratinjauNipForm`, `TambahPegawaiEhrmForm`, `PermohonanAkunForm`, `KeputusanPermohonanForm`; `TambahUserForm` dibatasi unit untuk Admin Unor |

### URL baru

| URL | Nama | Akses |
|---|---|---|
| `/oidc/authenticate/`, `/oidc/callback/`, `/oidc/logout/` | `mozilla_django_oidc.urls` | publik |
| `/daftar/lengkapi/` | `pendaftaran_lengkapi` | identitas SSO di sesi |
| `/daftar/status/` | `pendaftaran_status` | identitas SSO di sesi |
| `admin-biropakln/users/ehrm/pratinjau/?nip=` | `pakln:ehrm_pratinjau` | Admin Biro PAKLN |
| `admin-biropakln/users/ehrm/` | `pakln:tambah_user_ehrm` | Admin Biro PAKLN |
| `admin-biropakln/users/<id>/sinkron-ehrm/` | `pakln:sinkron_user_ehrm` | Admin Biro PAKLN |
| `admin-biropakln/users/<id>/lepas-sso/` | `pakln:lepas_sso` | Admin Biro PAKLN |
| `admin-biropakln/permohonan-akun/`, `…/<id>/` | `pakln:permohonan_akun`, `pakln:putus_permohonan_akun` | Admin Biro PAKLN |
| `admin-unor/pegawai/`, `…/data/`, `…/tambah/`, `…/ehrm/pratinjau/`, `…/<id>/`, `…/<id>/sinkron-ehrm/` | `unor:pegawai*` | Admin Unor (unitnya) |
| `admin-unor/permohonan-akun/`, `…/<id>/` | `unor:permohonan_akun*` | Admin Unor (unitnya) |

---

## 11. Rancangan Halaman

Mengikuti [PASPOR_DESIGN_GUIDE.MD](PASPOR_DESIGN_GUIDE.MD).

| Halaman | Isi |
|---|---|
| **Login** | Tombol "Login dengan SSO PU" (tautan `/oidc/authenticate/`, tersembunyi bila SSO tidak aktif); banner `?error=sso`; deep-link `/login/?sso=1` |
| **Lengkapi Pendaftaran** (tanpa sidebar, gaya kartu login) | Identitas SSO (nama, email); field NIP (terkunci bila dari klaim); ringkasan eHRM + pernyataan "Data ini adalah data saya"; bila perlu permohonan: isian nama, unit organisasi, unit kerja, jabatan, golongan + alasan mengapa perlu verifikasi; tombol **Daftar** / **Kirim Permohonan** |
| **Status Pendaftaran** | Status (`menunggu`/`ditolak`), unit tujuan, tanggal, catatan penolakan, tombol **Ajukan Ulang** / **Batalkan Permohonan**, tombol keluar SSO |
| **Manajemen User** (Admin Biro PAKLN) | Tab **Dari eHRM (NIP)** · **Manual** · **Permohonan Akun** (badge). Pratinjau eHRM `.field-readonly-grid`; tabel user menambah kolom **Sumber** (Manual/eHRM/SSO) dan penanda **SSO tertaut** |
| **Edit User** | Panel **Sinkron eHRM** (waktu terakhir, tombol ↻ dengan konfirmasi, ringkasan perubahan); panel **SSO** (status tertaut, `sub` disamarkan, tombol "Lepas tautan SSO" `is-danger is-light`); keterangan password untuk akun SSO/eHRM |
| **Pegawai Unor** (menu baru Admin Unor) | Daftar pegawai unitnya (DataTables), tombol **+ Daftarkan Pegawai** (tab eHRM / Manual terkunci unit), tab **Permohonan Akun** (badge sidebar) |
| **Detail permohonan** | Dua kolom: data isian pemohon vs data eHRM (penanda ✓/⚠ per field), identitas SSO; panel **Setujui** (`is-success`, unit dapat dikoreksi dalam cakupan) / **Tolak** (`is-danger is-light`, catatan wajib) |

---

## 12. Notifikasi

| Kode | Pemicu | Penerima | Kanal |
|---|---|---|---|
| `NOTIF_09A_PERMOHONAN_AKUN` | Permohonan akun dibuat | Admin Unor unit tujuan; Admin Biro PAKLN bila unit kosong | In-app + badge |
| `NOTIF_09B_AKUN_DIBUAT` | Akun didaftarkan admin / permohonan disetujui | Pegawai (akun baru) | In-app (terbaca saat login pertama) + email bila diaktifkan |
| `NOTIF_09C_PERMOHONAN_DITOLAK` | Permohonan ditolak | Pemohon | Halaman Status Pendaftaran + email bila diaktifkan |

Pemohon belum punya akun, sehingga notifikasi in-app tidak dapat diterima sebelum disetujui;
status selalu tampil saat login SSO berikutnya. Email memerlukan modul pengirim baru berbasis
`MAIL_*` di `.env` (belum ada di kode) — §16 #8.

---

## 13. Keamanan

1. **PKCE + state + nonce**, verifikasi tanda tangan id_token via JWKS.
2. **Pendaftaran mandiri tidak boleh mengklaim NIP orang lain**: aktivasi otomatis hanya bila
   identitas terverifikasi (B13); selain itu wajib diverifikasi admin. NIP yang sudah tertaut
   ke `sub` lain tidak dapat diambil alih (B9, B14).
3. Identitas SSO pada sesi sementara (sebelum akun ada) disimpan hanya `sub`, `email`, `name`, `nip`
   — tanpa token — dan kedaluwarsa 15 menit.
4. Akun admin tidak pernah dibuat lewat SSO (B11); role tetap dikelola Admin Biro PAKLN.
5. Rahasia (`SSO_CLIENT_SECRET`, `EHRM_PASSWORD`, `EHRM_API_KEY`, token eHRM) tidak masuk log,
   pesan error, maupun dokumen. `.env` sudah di `.gitignore`.
6. `EHRM_PEGAWAI_API_URL` saat ini `http://` — minta endpoint `https`.
7. Pratinjau eHRM: hanya Admin Biro PAKLN, Admin Unor (dibatasi unit), dan pemohon untuk NIP yang
   diketiknya sendiri; tidak mengembalikan NIK/telepon/foto (B6); rate limit (mis. 30/menit per
   admin, 5 percobaan NIP per sesi pendaftaran) untuk mencegah enumerasi NIP.
8. Pesan error eHRM/IdP ke pengguna bersifat generik; detail hanya di logger aplikasi.

---

## 14. Log Sistem

Tambahan katalog `ActivityLog.Aktivitas` ([SYSTEM_LOGGING.MD](SYSTEM_LOGGING.MD)):

| Kode | Kapan |
|---|---|
| `auth.login_sso` / `auth.login_sso_failed` | Login SSO berhasil / ditolak (alasan: tidak terdaftar, nonaktif, ganda, tertaut lain, token tidak valid) |
| `akun.tautan_sso` / `akun.lepas_sso` | Akun ditautkan / dilepas dari identitas SSO |
| `akun.daftar_mandiri` | Akun dibuat otomatis lewat pendaftaran mandiri |
| `akun.permohonan` | Permohonan diajukan / dibatalkan / disetujui / ditolak |
| `akun.daftar_ehrm` / `akun.daftar_manual` | Admin mendaftarkan pegawai |
| `pegawai.sinkron_ehrm` | Sinkron berhasil/gagal (+ ringkasan field berubah) |
| `integrasi.ehrm_error` | Kegagalan memanggil eHRM (status HTTP saja) |

---

## 15. Rencana Implementasi per Fase & Test

### 15.1 Fase

| Fase | Pekerjaan | Bergantung |
|:-:|---|---|
| 0 | Konfirmasi ke pengelola IdP & eHRM (§16 #1–#6); cek kompatibilitas `mozilla-django-oidc` × Django 6.1; akses jaringan server ke IdP & `apigw.pu.go.id` | — |
| 1 | Model & migrasi §8 | — |
| 2 | Klien eHRM + layanan pendaftaran admin & sinkron (test dengan mock HTTP) | 1 |
| 3 | Halaman admin: Manajemen User (tab eHRM, sinkron, lepas SSO), menu **Pegawai Unor** | 2 |
| 4 | SSO login: settings, backend, discovery lazy, URL, tombol login/logout, penautan akun lama | 0 (IdP) |
| 5 | Pendaftaran mandiri: Lengkapi Pendaftaran, Status, permohonan & verifikasi, notifikasi 09A–C | 2, 4 |
| 6 | Log, `.env.example`, `requirements.txt`, dokumentasi (`BISNIS_PROSES_PDLN.MD` §3/§9, `SYSTEM_LOGGING.MD`, `DEPLOY_SYNOLOGY.MD`) | — |
| 7 | Uji staging dengan IdP & eHRM nyata | semua |

Fase 1–3 dapat dirilis lebih dulu (pendaftaran oleh admin dari eHRM); Fase 4–5 menunggu IdP.

### 15.2 Test otomatis (IdP & eHRM di-mock)

| # | Skenario | Harapan |
|:-:|---|---|
| 1 | Env SSO kosong | Tombol SSO tersembunyi, `/oidc/*` & `/daftar/*` 404, login lokal berjalan |
| 2 | Klaim `email` = `User.email` (beda kapital) | Masuk; `sso_subject` terisi; log `akun.tautan_sso` |
| 3 | Login ulang, email IdP berubah, `sub` sama | Masuk akun yang sama |
| 4 | Akun nonaktif / dua akun cocok / tertaut `sub` lain | Ditolak dengan pesan, log gagal |
| 5 | Mandiri: klaim email = `email_pu` eHRM, unit terpetakan | Akun Pegawai aktif, password unusable, `sumber_akun=sso`, langsung masuk |
| 6 | Mandiri: email tidak cocok | Permohonan `menunggu` ke Admin Unor unit hasil pemetaan; notifikasi 09A |
| 7 | Mandiri: unit tidak terpetakan / eHRM tidak aktif | Permohonan ke Admin Biro PAKLN / alasan sesuai |
| 8 | Mandiri: NIP punya akun manual belum tertaut, identitas terverifikasi | Akun lama ditautkan, tidak membuat akun baru |
| 9 | Mandiri: NIP tertaut `sub` lain / permohonan menunggu sudah ada | Ditolak / diarahkan ke Status |
| 10 | `PENDAFTARAN_MANDIRI_SELALU_VERIFIKASI=true` | Selalu menjadi permohonan |
| 11 | Admin Unor menyetujui permohonan unitnya / unit lain | Akun dibuat & tertaut / 403 |
| 12 | Tolak tanpa catatan / dengan catatan | Ditolak validasi / status ditolak, tampil di halaman Status |
| 13 | Admin Biro PAKLN mendaftarkan NIP via eHRM | Akun + profil, `email = email_pu`, username dari email PU |
| 14 | Admin Unor mendaftarkan NIP unit lain | Simpan ditolak (B21) |
| 15 | Admin mendaftarkan NIP yang punya permohonan menunggu | Permohonan disetujui otomatis, akun tertaut `sub` (B23) |
| 16 | NIP sudah punya akun | Ditolak + tawaran Sinkron |
| 17 | Sinkron | Field B6 & unit berubah; `sisa_cuti`, role, password, snapshot pengajuan tetap |
| 18 | Token eHRM 401 | Login ulang otomatis sekali |
| 19 | eHRM error/timeout | Pesan generik, log `integrasi.ehrm_error` tanpa rahasia |
| 20 | Pratinjau oleh Admin BPSDM / pegawai berakun | 403 |
| 21 | Akun SSO/eHRM login dengan password | Ditolak |
| 22 | Role hasil pendaftaran mana pun | Selalu `pegawai` |

### 15.3 Uji manual staging

Login SSO akun admin & pegawai nyata; pendaftaran mandiri (cocok & tidak cocok); verifikasi oleh
Admin Unor; logout IdP; sinkron; callback `https` di belakang reverse proxy.

---

## 16. Keputusan Default & Pertanyaan Terbuka

| # | Pertanyaan | Default rancangan |
|:-:|---|---|
| 1 | Client IdP: client baru `paspor` atau client `eiln` + redirect URI PASPOR? | Client baru — audit & pencabutan terpisah dari EILN |
| 2 | Issuer sebenarnya (`.env` masih `sso.example.go.id`) dan jenis IdP? | Menunggu pengelola IdP; implementasi OIDC standar |
| 3 | Apakah IdP mengirim **NIP** di klaim? | Bila ada, isi `SSO_NIP_CLAIM` → NIP otomatis & verifikasi terkuat; bila tidak, NIP diketik pegawai dan diverifikasi lewat email |
| 4 | Klaim `email` berisi email PU (`@pu.go.id`)? Apakah redirect ke `localhost` diizinkan untuk development? | Email PU; localhost diizinkan |
| 5 | Logout IdP sekaligus? | Ya bila `end_session_endpoint` tersedia |
| 6 | Benarkah 2 digit pertama `kdunit` eHRM = `UnitOrganisasi.code`? | Diasumsikan ya; dikonfirmasi dengan contoh data eHRM di Fase 0 |
| 7 | Pendaftaran mandiri yang terverifikasi: langsung aktif, atau tetap disetujui Admin Unor? | Langsung aktif; `PENDAFTARAN_MANDIRI_SELALU_VERIFIKASI` untuk masa uji coba |
| 8 | Perlu email ke pemohon (akun dibuat / ditolak)? | Fase berikut — perlu modul email berbasis `MAIL_*`; sementara via halaman Status |
| 9 | Admin Unor boleh menonaktifkan akun pegawai unitnya? | Tidak — tetap Admin Biro PAKLN |
| 10 | Pegawai boleh menyinkronkan profilnya sendiri dari eHRM (menu Profil)? | Ya, tombol "Perbarui dari eHRM" di Profil |
| 11 | NIK/telepon pegawai perlu disimpan? | Tidak (B6) |
| 12 | Login lokal untuk pegawai dimatikan setelah SSO stabil? | Tetap aktif; dapat dimatikan per lingkungan di fase berikut |
| 13 | Masa berlaku token eHRM 24 jam? | Ya (asumsi EILN) + retry 401 |
| 14 | Sinkron otomatis saat login SSO? | Mati (`EHRM_SINKRON_SAAT_LOGIN_HARI=0`) |
