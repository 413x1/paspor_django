# Implementasi SSO & Penambahan Pegawai — Panduan Porting ke Django

Dokumen ini menjabarkan cara kerja **login SSO (OIDC)**, **penambahan Pegawai** (dari eHRM maupun manual), dan **penambahan Pengguna dari eHRM** di project EILN (Next.js + NextAuth + Prisma), lalu menerjemahkannya menjadi implementasi siap pakai untuk project **Django**.

---

## 1. Konsep Dasar: `Pengguna` vs `Pegawai`

Di EILN ada dua entitas yang sering tertukar:

| Entitas | Tabel | Fungsi | Sumber data |
|---|---|---|---|
| **Pengguna** | `pengguna` | Akun yang bisa **login** ke aplikasi (admin/operator unit). Punya `username`, `password`, `kdunit`, `is_super_admin`. | Dibuat admin (manual / dari eHRM) atau di-provision otomatis saat login SSO |
| **Pegawai** | `pegawai` | **Master data pegawai** (NIP, jabatan, golongan, unit). Dipakai sebagai peserta perjalanan dinas, paspor, dsb. Tidak dipakai untuk login. | Ditarik dari API eHRM berdasarkan NIP, atau diinput manual |
| **UnitKerja** | `unit_kerja` | Master unit organisasi (`kd_unit` 8 digit, `parent_unit`, `unit_induk`). Dipakai untuk scoping hak akses pengguna. | Disinkronkan dari eHRM (`/api/sync-unit-kerja`) |

Relasi penting: `Pengguna.kdunit → UnitKerja.kd_unit` dan `Pegawai.kdunit → UnitKerja.kd_unit`.

> **Penting:** Login SSO hanya memetakan identitas SSO ke **Pengguna**, bukan ke Pegawai. Keduanya tidak otomatis terhubung (tidak ada FK `pengguna → pegawai`). Hubungannya hanya tersirat lewat `description` (`EHRM;NIP=...`) dan `username` (biasanya `email_pu`).

---

## 2. Arsitektur SSO di EILN

### 2.1 Alur

```
Browser                          EILN (NextAuth)                       SSO / IdP (OIDC)
   │  klik "Masuk dengan SSO"         │                                       │
   │  signIn('sso')  ─────────────────▶ /api/auth/signin/sso                   │
   │                                  │  generate state + PKCE verifier       │
   │◀──── 302 ke authorization_endpoint (scope "openid profile email") ───────▶│
   │                                  │                                       │ user login di IdP
   │◀──────────────────────── 302 /api/auth/callback/sso?code=...&state=... ──│
   │  ───────────────────────────────▶│ tukar code → token (client_secret+PKCE)│
   │                                  │ validasi id_token, ambil claims        │
   │                                  │                                       │
   │                                  │ callbacks.signIn():                   │
   │                                  │   username = claim (SSO_USERNAME_CLAIM│
   │                                  │     | preferred_username | username   │
   │                                  │     | upn | email | sub)              │
   │                                  │   cari Pengguna(username, aktif,      │
   │                                  │     tidak dihapus)                    │
   │                                  │   ├─ ada → (isi email_notifikasi bila │
   │                                  │   │        kosong) → lanjut           │
   │                                  │   ├─ tidak ada & SSO_AUTO_PROVISION   │
   │                                  │   │   =true → buat Pengguna minimal   │
   │                                  │   │   (password random)               │
   │                                  │   └─ tidak ada → TOLAK login          │
   │                                  │ callbacks.jwt(): simpan id, username, │
   │                                  │   name, kdunit, is_super_admin, sso   │
   │◀──── set cookie session (JWT, 30 hari) + redirect /dashboard ───────────│
```

File sumber:
- [src/lib/auth/config.js](src/lib/auth/config.js) — konfigurasi provider, mapping claim, provisioning.
- [src/pages/api/auth/[...nextauth].js](src/pages/api/auth/[...nextauth].js) — endpoint NextAuth.
- [src/app/home/login/page.jsx](src/app/home/login/page.jsx) — tombol SSO, cek provider, deep-link `?sso=1`.
- [src/middleware/authMiddleware.js](src/middleware/authMiddleware.js) — proteksi API berbasis session.
- [src/proxy.js](src/proxy.js) — proteksi halaman (`/dashboard`, `/portal`, `/home`).

### 2.2 Poin desain yang perlu dipertahankan

1. **SSO bersifat opsional** — provider `sso` hanya didaftarkan bila `issuer`, `client_id`, `client_secret` semuanya terisi. Login username/password (credentials) tetap tersedia.
2. **OIDC discovery** — endpoint diambil dari `{ISSUER}/.well-known/openid-configuration`.
3. **Keamanan flow**: `checks: ["pkce", "state"]`, `idToken: true`.
4. **Mapping identitas** — claim username bisa dikonfigurasi (`SSO_USERNAME_CLAIM`), fallback berurutan: `preferred_username → username → upn → email → sub`.
5. **Hanya user lokal yang aktif** (`is_active=true`, `is_deleted=false`) yang boleh masuk.
6. **Auto-provision opsional** (`SSO_AUTO_PROVISION=true`) — default **mati**, sehingga admin harus mendaftarkan Pengguna dulu (lihat §4).
7. **Isi email notifikasi** dari claim `email` bila masih kosong.
8. **Password random** untuk user SSO/eHRM (32 byte hex, di-hash bcrypt) agar kolom `password` NOT NULL terisi tapi tidak bisa dipakai login.
9. **Audit log**: `LOGIN_SSO_SUCCESS` / `LOGIN_SSO_FAILED` / `LOGIN_SUCCESS` / `LOGIN_FAILED`.
10. **Session** memuat `id, username, name, kdunit, is_super_admin` — semua otorisasi di API membaca dari sini.
11. **Halaman login**: memanggil `/api/auth/providers` untuk tahu apakah SSO aktif; mendukung `/home/login?sso=1` untuk langsung redirect ke SSO.

### 2.3 Variabel lingkungan (EILN)

| Variabel | Alias yang juga didukung | Keterangan |
|---|---|---|
| `SSO_ISSUER` | `SSOBaseUrl`, `SSO_BASE_URL` | Base URL issuer OIDC |
| `SSO_CLIENT_ID` | `SSOClientId` | |
| `SSO_CLIENT_SECRET` | `SSOClientSecret` | |
| `SSO_SCOPE` | — | default `openid profile email` |
| `SSO_NAME` | — | label tombol, default `SSO` |
| `SSO_USERNAME_CLAIM` | — | claim yang dipakai sebagai username |
| `SSO_AUTO_PROVISION` | — | `true` = buat Pengguna otomatis |
| `NEXT_PUBLIC_SSO_ENABLED` | — | `false` = sembunyikan tombol SSO |
| `NEXTAUTH_SECRET`, `NEXTAUTH_URL` | — | secret session & URL callback |

Redirect URI yang didaftarkan di IdP: `https://<domain>/eiln/api/auth/callback/sso`.

**Yang benar-benar dipakai di `.env` EILN saat ini:** `SSOBaseUrl`, `SSOClientId`, `SSOClientSecret` (nama alias, bukan `SSO_ISSUER`/`SSO_CLIENT_*`), `SSO_USERNAME_CLAIM`, `SSO_AUTO_PROVISION`, `NEXT_PUBLIC_SSO_ENABLED`, `NEXTAUTH_URL`, `NEXTAUTH_SECRET`. `SSO_SCOPE` dan `SSO_NAME` **tidak diset**, jadi memakai default (`openid profile email` dan `SSO`).

> **Catatan eHRM:** `.env` EILN **tidak berisi** variabel `EHRM_*` sama sekali (hanya ada di `.env.minimal`). Akibatnya di environment ini fitur yang bergantung eHRM — tambah pegawai via NIP, sinkron, dan tambah Pengguna dari eHRM — akan gagal; yang berfungsi hanya **input manual**. Karena itu versi Django di bawah membuat integrasi eHRM **opsional** (lihat §5.1 & §5.6).

---

## 3. Arsitektur Penambahan Pegawai di EILN

### 3.1 Integrasi eHRM (API Gateway PU, DreamFactory)

**Token** — [src/lib/get-oauth-token.js](src/lib/get-oauth-token.js)
- `POST EHRM_LOGIN_URL` dengan body `{ email: EHRM_EMAIL, password: EHRM_PASSWORD, remember_me: false }`.
- Response berisi `session_token`.
- Token di-cache di tabel `api_access_tokens` (1 baris) dengan masa berlaku **24 jam**; diperbarui bila kedaluwarsa.

**Ambil data pegawai** — [src/lib/pegawai-info.js](src/lib/pegawai-info.js)
```
GET {EHRM_PEGAWAI_API_URL}/{nip}
Headers:
  X-DreamFactory-Session-Token: <session_token>
  X-DreamFactory-Api-Key:       <EHRM_API_KEY>
  Accept-Encoding: gzip, deflate
```
Field response yang dipakai: `nip, nama, foto, kdkelamin (1=L, 2=P), email, email_pu, telphp, noktp, golongan, deskripsi_gol, jabatan, jabatan_lengkap, unor, unker, kdunit, eselon`.

Setiap langkah dicatat ke activity log; error dari eHRM dibungkus menjadi pesan generik ("Terjadi kesalahan pada server").

### 3.2 Endpoint

| Endpoint | Fungsi |
|---|---|
| `GET /api/pegawai-by-nip/{nip}` / `GET /api/pegawai-info?nip=` | **Preview** data eHRM (tanpa simpan). UI memanggilnya otomatis saat NIP sudah 18 digit. |
| `POST /api/signup` `{nip, sync}` | **Tambah pegawai dari eHRM** / **sinkron ulang**. |
| `POST /api/signup/manual` | **Tambah pegawai manual** (non-eHRM, mis. pegawai non-ASN). |
| `GET /api/pegawai` | List (paginasi + pencarian nama/nip/jabatan/unor) atau detail via `?uuid=`. |
| `POST /api/user/ehrm` | **Buat Pengguna (akun login) dari NIP eHRM** — lihat §4. |

### 3.3 Logika `POST /api/signup` (dari eHRM)

```
validasi nip wajib
pegawai = Pegawai.where(nip)
info    = eHRM.fetch(nip)              # selalu ambil data terbaru
jika pegawai belum ada  → CREATE (uuid baru + mapping field) → 201 "Pendaftaran berhasil!"
jika ada & sync=true     → UPDATE semua field dari eHRM      → 200 "Data pegawai berhasil disinkronkan..."
jika ada & sync=false    → tidak diubah                      → 200 "Akun dengan NIP ini telah terdaftar..."
error Prisma P2002/P2003/P2025 → pesan ramah; detail error hanya ke log
```

Mapping eHRM → kolom `pegawai`:

| eHRM | Pegawai |
|---|---|
| `nip` | `nip` (unique) |
| `nama` | `nama` |
| `foto` | `foto` |
| `kdkelamin` (`1`/lainnya) | `kd_kelamin` (`LAKI_LAKI`/`PEREMPUAN`) |
| `email` | `email` (unique) |
| `email_pu` | `email_pu` |
| `telphp` | `telphp` |
| `noktp` | `nik` |
| `golongan`, `deskripsi_gol` | sama |
| `jabatan`, `jabatan_lengkap` | sama |
| `unor`, `unker` | sama |
| `kdunit` | `kdunit` (FK ke unit_kerja) |
| `eselon` | `eselon` |

### 3.4 Logika `POST /api/signup/manual`

- Wajib: `nama`, `nik`, `email`, `telphp`.
- NIP opsional — bila kosong dibuat **NIP internal** `MN` + 10 digit terakhir timestamp + 4 digit random, diulang sampai unik.
- Tolak bila sudah ada pegawai dengan `nip` **atau** `nik` **atau** `email` yang sama.
- `tipe_pengguna = REGULAR`, `is_active = true`.

### 3.5 Alur UI ([PegawaiClient.jsx](src/app/dashboard/pegawai/PegawaiClient.jsx))

1. Modal "Tambah Pegawai" punya 2 tab: **eHRM (NIP)** dan **Manual**.
2. Tab eHRM: ketik NIP → saat panjang = 18 → preview (`/api/pegawai-by-nip`) → tombol simpan memanggil `/api/signup`.
3. Tab Manual: form lengkap → `/api/signup/manual`.
4. Di tabel list ada tombol **Sinkron** per baris → `/api/signup { nip, sync: true }`.

---

## 4. Penambahan Pengguna dari eHRM (penghubung SSO ↔ Pegawai)

Karena `SSO_AUTO_PROVISION` default mati, pegawai baru bisa login SSO **setelah** admin membuat Pengguna untuknya. EILN menyediakan `POST /api/user/ehrm` ([src/pages/api/user/ehrm.js](src/pages/api/user/ehrm.js)) dan UI di [users/page.jsx](src/app/dashboard/users/page.jsx) (mode "Pengguna eHRM (NIP)"):

```
input: nip*, email_notifikasi*, username?, kdunit?, is_active?, is_super_admin?, description?
info      = eHRM.fetch(nip)
username  = override || info.email_pu || info.email || nip     ← harus SAMA dengan claim SSO
name      = info.nama
kdunit    = resolveUnitKerjaKdUnit(override || info.kdunit)
tolak bila username sudah dipakai Pengguna aktif / kdunit tidak cocok master unit
password  = bcrypt(random 32 byte)                              ← login via SSO saja
description = "EHRM;NIP=<nip>;KDUNIT_CHILD=<kd asli>;KDUNIT_SELECTED=<kd terpilih>; Jabatan=<...>;"
```

**`resolveUnitKerjaKdUnit`** (penting untuk scoping hak akses):
1. Normalisasi: ambil digit saja; ≥ 8 digit → potong 8 digit pertama; < 8 digit → `zfill(8)`.
2. Bila `kd_unit` ada di master → pilih `parent_unit` (jika ada di master), lalu `unit_induk` (jika ada), lalu dirinya sendiri.
3. Bila tidak ada → fallback ke grup `XX000000` (2 digit pertama + `000000`) bila ada di master.
4. Gagal semua → tolak (minta sinkron master unit kerja dulu).

> **Kunci keberhasilan SSO:** `username` Pengguna harus sama persis dengan nilai claim SSO (`SSO_USERNAME_CLAIM`). Di EILN default-nya `email_pu` dari eHRM, jadi IdP diasumsikan mengirim email PU di `preferred_username`/`email`. Pastikan ini dikonfirmasi ke pengelola IdP.

---

## 5. Implementasi di Django

Stack yang direkomendasikan:
- Django ≥ 4.2, PostgreSQL
- [`mozilla-django-oidc`](https://mozilla-django-oidc.readthedocs.io/) ≥ 4.0 (OIDC + PKCE + state) — padanan NextAuth OAuth provider
- `djangorestframework` untuk endpoint JSON
- `requests` untuk eHRM

```bash
pip install "django>=4.2" "mozilla-django-oidc>=4.0" djangorestframework requests psycopg[binary]
```

Struktur app:

```
project/
  settings.py
  urls.py
accounts/        # Pengguna (custom user), OIDC backend, login view
  models.py
  oidc.py
  views.py
  urls.py
  templates/accounts/login.html
organisasi/      # UnitKerja + resolver kdunit
  models.py
  services.py
ehrm/            # klien eHRM (token + fetch pegawai)
  models.py
  client.py
pegawai/         # master Pegawai + endpoint tambah/sinkron
  models.py
  services.py
  views.py
  urls.py
audit/           # ActivityLog
  models.py
```

### 5.1 `settings.py`

```python
import os

INSTALLED_APPS = [
    # ...
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "mozilla_django_oidc",
    "accounts",
    "organisasi",
    "ehrm",
    "pegawai",
    "audit",
]

AUTH_USER_MODEL = "accounts.Pengguna"

# --- SSO (OIDC) -----------------------------------------------------------
# Dukung nama yang sama dengan EILN (.env EILN memakai SSOBaseUrl/SSOClientId/SSOClientSecret)
SSO_ISSUER = os.getenv("SSO_ISSUER") or os.getenv("SSOBaseUrl") or os.getenv("SSO_BASE_URL", "")
OIDC_RP_CLIENT_ID = os.getenv("SSO_CLIENT_ID") or os.getenv("SSOClientId", "")
OIDC_RP_CLIENT_SECRET = os.getenv("SSO_CLIENT_SECRET") or os.getenv("SSOClientSecret", "")
SSO_ENABLED = bool(SSO_ISSUER and OIDC_RP_CLIENT_ID and OIDC_RP_CLIENT_SECRET)

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]  # credentials

if SSO_ENABLED:
    # mozilla-django-oidc tidak melakukan discovery; ambil endpoint dari
    # {SSO_ISSUER}/.well-known/openid-configuration dan isi di env, atau
    # gunakan helper discover_oidc() di bawah saat startup.
    from accounts.oidc import discover_oidc
    _oidc = discover_oidc(SSO_ISSUER)
    OIDC_OP_AUTHORIZATION_ENDPOINT = _oidc["authorization_endpoint"]
    OIDC_OP_TOKEN_ENDPOINT = _oidc["token_endpoint"]
    OIDC_OP_USER_ENDPOINT = _oidc["userinfo_endpoint"]
    OIDC_OP_JWKS_ENDPOINT = _oidc["jwks_uri"]
    OIDC_OP_LOGOUT_ENDPOINT = _oidc.get("end_session_endpoint")
    OIDC_RP_SIGN_ALGO = os.getenv("SSO_SIGN_ALGO", "RS256")
    OIDC_RP_SCOPES = os.getenv("SSO_SCOPE", "openid profile email")
    OIDC_USE_PKCE = True                         # = checks: ["pkce"]
    OIDC_PKCE_CODE_CHALLENGE_METHOD = "S256"
    # state & nonce sudah divalidasi default oleh mozilla-django-oidc
    OIDC_CREATE_USER = os.getenv("SSO_AUTO_PROVISION", "false").lower() == "true"
    AUTHENTICATION_BACKENDS.insert(0, "accounts.oidc.PenggunaOIDCBackend")

SSO_NAME = os.getenv("SSO_NAME", "SSO")
SSO_USERNAME_CLAIM = os.getenv("SSO_USERNAME_CLAIM", "")

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGIN_REDIRECT_URL_FAILURE = "/accounts/login/?error=sso"
LOGOUT_REDIRECT_URL = "/accounts/login/"

SESSION_COOKIE_AGE = 30 * 24 * 60 * 60   # 30 hari, sama dengan EILN
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Bila aplikasi berjalan di sub-path (seperti /eiln), set FORCE_SCRIPT_NAME
# FORCE_SCRIPT_NAME = "/eiln"

# --- eHRM (OPSIONAL) --------------------------------------------------------
# Bila salah satu kosong, fitur eHRM dimatikan: UI hanya menampilkan input manual,
# dan endpoint eHRM mengembalikan 503 "Integrasi eHRM belum dikonfigurasi".
EHRM_LOGIN_URL = os.getenv("EHRM_LOGIN_URL", "")              # https://apigw.pu.go.id/user/login
EHRM_EMAIL = os.getenv("EHRM_EMAIL", "")
EHRM_PASSWORD = os.getenv("EHRM_PASSWORD", "")
EHRM_API_KEY = os.getenv("EHRM_API_KEY", "")
EHRM_PEGAWAI_API_URL = os.getenv("EHRM_PEGAWAI_API_URL", "")  # .../v1/ehrm/pegawai
EHRM_TIMEOUT = int(os.getenv("EHRM_TIMEOUT", "20"))
EHRM_ENABLED = all([EHRM_LOGIN_URL, EHRM_EMAIL, EHRM_PASSWORD, EHRM_API_KEY, EHRM_PEGAWAI_API_URL])

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}
```

Redirect URI yang didaftarkan di IdP: `https://<domain>[/<script_name>]/oidc/callback/`.

### 5.2 Model

**`organisasi/models.py`**

```python
from django.db import models


class UnitKerja(models.Model):
    kd_unit = models.CharField(max_length=8, unique=True)
    parent_unit = models.CharField(max_length=8)
    unit_induk = models.CharField(max_length=20)
    keterangan = models.TextField()
    nama_jabatan = models.TextField()
    nama_singkat = models.CharField(max_length=255, null=True, blank=True)
    eselon = models.IntegerField()
    struktural = models.SmallIntegerField()
    aktif = models.SmallIntegerField()
    kd_unit_bkn = models.CharField(max_length=64)
    unit_induk_bkn = models.CharField(max_length=64)
    kd_propinsi = models.CharField(max_length=6)
    kota_kab = models.CharField(max_length=255)
    alamat = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "unit_kerja"

    def __str__(self):
        return f"{self.kd_unit} - {self.keterangan}"
```

**`accounts/models.py`** — Pengguna sebagai custom user model:

```python
import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class PenggunaManager(BaseUserManager):
    def create_user(self, username, password=None, **extra):
        user = self.model(username=username, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()   # padanan "password random" di EILN
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password, **extra):
        extra.setdefault("is_super_admin", True)
        return self.create_user(username, password, **extra)

    def active(self):
        return self.filter(is_active=True, is_deleted=False)


class Pengguna(AbstractBaseUser, PermissionsMixin):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    username = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    kdunit = models.ForeignKey(
        "organisasi.UnitKerja", to_field="kd_unit", db_column="kdunit",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="pengguna",
    )
    email_notifikasi = models.EmailField(max_length=255, null=True, blank=True)
    permissions_json = models.JSONField(null=True, blank=True, db_column="permissions")
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    is_super_admin = models.BooleanField(default=False)
    sso_subject = models.CharField(max_length=255, null=True, blank=True, unique=True)  # opsional, lihat §6
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PenggunaManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "pengguna"

    @property
    def is_staff(self):            # akses Django admin
        return self.is_super_admin

    @property
    def is_superuser(self):
        return self.is_super_admin
```

> Catatan: `PermissionsMixin` sudah punya field `is_superuser`. Bila ingin memakai field bawaan, ganti `is_super_admin` dengan `is_superuser` dan hapus property di atas. Contoh ini mempertahankan nama kolom EILN agar migrasi data mudah.

**`pegawai/models.py`**

```python
import uuid
from django.db import models


class Pegawai(models.Model):
    class KdKelamin(models.TextChoices):
        LAKI_LAKI = "1", "Laki-laki"
        PEREMPUAN = "2", "Perempuan"

    class TipePengguna(models.TextChoices):
        REGULAR = "0", "Regular"
        ADMIN = "1", "Admin"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nama = models.CharField(max_length=255)
    foto = models.CharField(max_length=255, null=True, blank=True)
    kd_kelamin = models.CharField(max_length=1, choices=KdKelamin.choices, null=True, blank=True)
    nip = models.CharField(max_length=20, unique=True)
    nik = models.CharField(max_length=20)
    golongan = models.CharField(max_length=10, null=True, blank=True)
    deskripsi_gol = models.TextField(null=True, blank=True)
    jabatan = models.CharField(max_length=255, null=True, blank=True)
    jabatan_lengkap = models.CharField(max_length=255, null=True, blank=True)
    eselon = models.CharField(max_length=10, null=True, blank=True)
    unor = models.CharField(max_length=255, null=True, blank=True)
    unker = models.CharField(max_length=255, null=True, blank=True)
    kdunit = models.ForeignKey(
        "organisasi.UnitKerja", to_field="kd_unit", db_column="kdunit",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="pegawai",
        db_constraint=False,   # eHRM bisa mengirim kdunit yang belum ada di master
    )
    tipe_pengguna = models.CharField(max_length=1, choices=TipePengguna.choices, default=TipePengguna.REGULAR)
    email = models.EmailField(max_length=255, unique=True)
    email_pu = models.EmailField(max_length=255, null=True, blank=True)
    telphp = models.CharField(max_length=15, null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pegawai"
        ordering = ["-updated_at"]
```

**`ehrm/models.py`** — cache token (padanan `api_access_tokens`):

```python
from django.db import models


class ApiAccessToken(models.Model):
    access_token = models.TextField()
    scope = models.CharField(max_length=255, default="ehrm_api")
    token_type = models.CharField(max_length=20, default="Bearer")
    expires_in = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "api_access_tokens"
```

> Alternatif lebih sederhana: simpan token di `django.core.cache` (Redis) dengan TTL 24 jam. Tabel DB dipakai di EILN agar token bertahan antar-restart dan dipakai bersama oleh banyak container.

**`audit/models.py`**

```python
from django.conf import settings
from django.db import models


class UserActivityLog(models.Model):
    pengguna = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_activity_logs"


def log_activity(user_or_id, action, description):
    pengguna_id = getattr(user_or_id, "pk", user_or_id)
    try:
        UserActivityLog.objects.create(pengguna_id=pengguna_id, action=action, description=description)
    except Exception:   # logging tidak boleh menggagalkan proses utama (sama seperti EILN)
        pass
```

### 5.3 Backend SSO (`accounts/oidc.py`)

```python
import logging

import requests
from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from audit.models import log_activity

logger = logging.getLogger(__name__)


def discover_oidc(issuer: str) -> dict:
    """Ambil metadata dari {issuer}/.well-known/openid-configuration (padanan `wellKnown` NextAuth)."""
    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_sso_username(claims: dict) -> str | None:
    """Urutan sama dengan EILN: SSO_USERNAME_CLAIM → preferred_username → username → upn → email → sub."""
    if not isinstance(claims, dict):
        return None
    custom = getattr(settings, "SSO_USERNAME_CLAIM", "")
    if custom and claims.get(custom):
        return str(claims[custom]).strip()
    for key in ("preferred_username", "username", "upn", "email", "sub"):
        if claims.get(key):
            return str(claims[key]).strip()
    return None


def build_name(claims: dict) -> str | None:
    if claims.get("name"):
        return str(claims["name"])[:50]
    full = f"{claims.get('given_name', '')} {claims.get('family_name', '')}".strip()
    return full[:50] or None


class PenggunaOIDCBackend(OIDCAuthenticationBackend):
    """Memetakan identitas SSO ke Pengguna lokal (padanan findOrProvisionPenggunaFromSso)."""

    def filter_users_by_claims(self, claims):
        username = get_sso_username(claims)
        if not username:
            return self.UserModel.objects.none()
        return self.UserModel.objects.active().filter(username=username)

    def verify_claims(self, claims):
        # Jangan wajibkan email (default mozilla-django-oidc mewajibkan "email" di scope).
        return bool(get_sso_username(claims))

    def create_user(self, claims):
        # Hanya terpanggil bila OIDC_CREATE_USER=True (SSO_AUTO_PROVISION=true)
        username = get_sso_username(claims)
        email = (claims.get("email") or "").strip() or (username if "@" in username else None)
        user = self.UserModel.objects.create_user(
            username=username,
            password=None,                    # unusable password
            name=build_name(claims),
            email_notifikasi=email,
            is_active=True,
            is_deleted=False,
        )
        log_activity(user, "SSO_AUTO_PROVISION", f"Pengguna {username} dibuat otomatis via SSO")
        return user

    def update_user(self, user, claims):
        # Isi email_notifikasi bila masih kosong (sama dengan EILN)
        email = (claims.get("email") or "").strip()
        if not user.email_notifikasi and email:
            user.email_notifikasi = email
            user.save(update_fields=["email_notifikasi", "updated_at"])
        return user

    def get_or_create_user(self, access_token, id_token, payload):
        user = super().get_or_create_user(access_token, id_token, payload)
        if user is None:
            log_activity(
                None, "LOGIN_SSO_FAILED",
                "SSO login ditolak (tidak ada Pengguna lokal / belum dipetakan). "
                f"usernameClaim={settings.SSO_USERNAME_CLAIM or 'auto'}",
            )
        else:
            log_activity(user, "LOGIN_SSO_SUCCESS", f"User {user.username} login via SSO")
            self.request.session["sso"] = True
        return user
```

Catatan perilaku `mozilla-django-oidc`:
- Bila `filter_users_by_claims` mengembalikan > 1 user → `SuspiciousOperation` (tidak akan terjadi karena `username` unique).
- Bila 0 user dan `OIDC_CREATE_USER=False` → `None` → redirect ke `LOGIN_REDIRECT_URL_FAILURE` (setara `return false` di `signIn` callback).
- Claim yang dibaca berasal dari **userinfo endpoint**. Bila IdP hanya menaruh claim di `id_token`, override `get_userinfo()` untuk mendekode `payload` id_token yang sudah terverifikasi:

```python
    def get_userinfo(self, access_token, id_token, payload):
        info = {}
        try:
            info = super().get_userinfo(access_token, id_token, payload)
        except Exception:
            logger.warning("userinfo endpoint gagal, pakai claims id_token")
        return {**payload, **(info or {})}
```

### 5.4 Login view (credentials + tombol SSO)

**`accounts/views.py`**

```python
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.urls import reverse

from audit.models import log_activity


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True   # padanan: /home + token → redirect /dashboard

    def get(self, request, *args, **kwargs):
        # Deep-link /accounts/login/?sso=1 → langsung ke SSO (sama seperti EILN)
        if request.GET.get("sso") == "1" and settings.SSO_ENABLED and not request.user.is_authenticated:
            return redirect(reverse("oidc_authentication_init"))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sso_enabled"] = settings.SSO_ENABLED
        ctx["sso_name"] = settings.SSO_NAME
        ctx["sso_error"] = self.request.GET.get("error") == "sso"
        return ctx

    def form_valid(self, form):
        user = form.get_user()
        if user.is_deleted:
            form.add_error(None, "Akun tidak aktif.")
            return self.form_invalid(form)
        log_activity(user, "LOGIN_SUCCESS", f"User {user.username} logged in successfully")
        return super().form_valid(form)

    def form_invalid(self, form):
        log_activity(None, "LOGIN_FAILED",
                     f"Failed login attempt for username: {form.data.get('username', '')}")
        return super().form_invalid(form)
```

**`accounts/templates/accounts/login.html`** (inti):

```html
<h1>Masuk</h1>
{% if sso_error %}
  <p class="error">Login SSO ditolak: akun Anda belum terdaftar di aplikasi. Hubungi administrator.</p>
{% endif %}
<form method="post">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Masuk</button>
</form>

{% if sso_enabled %}
  <a class="btn-sso" href="{% url 'oidc_authentication_init' %}?next={{ next|default:'/dashboard/'|urlencode }}">
    Masuk dengan {{ sso_name }}
  </a>
{% endif %}
```

**`project/urls.py`**

```python
from django.conf import settings
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from accounts.views import LoginView

urlpatterns = [
    path("accounts/login/", LoginView.as_view(), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("api/", include("pegawai.urls")),
]
if settings.SSO_ENABLED:
    urlpatterns.append(path("oidc/", include("mozilla_django_oidc.urls")))
    # menyediakan: oidc/authenticate/ (init), oidc/callback/, oidc/logout/
```

> Untuk **logout dari IdP** juga (bukan hanya sesi lokal), set `OIDC_OP_LOGOUT_URL_METHOD` ke fungsi yang membangun URL `end_session_endpoint?id_token_hint=...&post_logout_redirect_uri=...` dan simpan id_token di sesi (`OIDC_STORE_ID_TOKEN = True`).

### 5.5 Proteksi halaman & API (padanan `proxy.js` dan `authMiddleware`)

```python
# accounts/permissions.py
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_super_admin)


def super_admin_page(view_func):
    """Non-admin hanya boleh /dashboard, /dashboard/status-iln, /dashboard/paspor-visa."""
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_super_admin:
            return redirect("/dashboard/")
        return view_func(request, *args, **kwargs)
    return _wrapped
```

Scoping data per unit kerja dapat dibaca dari `request.user.kdunit_id` (padanan `session.user.kdunit`).

### 5.6 Klien eHRM (`ehrm/client.py`)

```python
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.models import log_activity
from .models import ApiAccessToken

logger = logging.getLogger(__name__)


class EhrmError(Exception):
    """Pesan aman untuk ditampilkan ke user; detail ada di log."""
    status_code = 502


class EhrmNotConfigured(EhrmError):
    status_code = 503


def ensure_ehrm_enabled():
    if not settings.EHRM_ENABLED:
        raise EhrmNotConfigured("Integrasi eHRM belum dikonfigurasi. Gunakan input manual.")


def get_ehrm_token() -> str:
    ensure_ehrm_enabled()
    """Ambil session_token eHRM dari cache DB, login ulang bila kedaluwarsa (TTL 24 jam)."""
    with transaction.atomic():
        token = ApiAccessToken.objects.select_for_update().first()
        if token and token.expires_in > timezone.now():
            return token.access_token

        resp = requests.post(
            settings.EHRM_LOGIN_URL,
            json={"email": settings.EHRM_EMAIL, "password": settings.EHRM_PASSWORD, "remember_me": False},
            timeout=settings.EHRM_TIMEOUT,
        )
        resp.raise_for_status()
        session_token = resp.json()["session_token"]
        expires = timezone.now() + timedelta(hours=24)

        if token:
            token.access_token, token.expires_in = session_token, expires
            token.save(update_fields=["access_token", "expires_in", "updated_at"])
        else:
            ApiAccessToken.objects.create(access_token=session_token, expires_in=expires)
        return session_token


def _invalidate_token():
    ApiAccessToken.objects.all().update(expires_in=timezone.now())


def fetch_pegawai_info(nip: str) -> dict:
    ensure_ehrm_enabled()
    if not nip:
        log_activity(None, "PEGAWAI_INFO_VALIDATION_FAILED", "NIP is required for fetching pegawai info")
        raise EhrmError("NIP wajib diisi")

    for attempt in (1, 2):   # retry sekali bila token ditolak (401)
        try:
            token = get_ehrm_token()
            resp = requests.get(
                f"{settings.EHRM_PEGAWAI_API_URL.rstrip('/')}/{nip}",
                headers={
                    "Accept-Encoding": "gzip, deflate",
                    "X-DreamFactory-Session-Token": token,
                    "X-DreamFactory-Api-Key": settings.EHRM_API_KEY,
                },
                timeout=settings.EHRM_TIMEOUT,
            )
            if resp.status_code == 401 and attempt == 1:
                _invalidate_token()
                continue
            resp.raise_for_status()
            data = resp.json()
            if not data or not data.get("nip"):
                raise EhrmError("Data pegawai tidak ditemukan di eHRM")
            log_activity(None, "PEGAWAI_INFO_SUCCESS",
                         f"Fetched pegawai info for NIP: {nip}, Name: {data.get('nama', 'N/A')}")
            return data
        except EhrmError:
            raise
        except requests.HTTPError as exc:
            detail = f"eHRM API responded with status {exc.response.status_code}"
        except requests.RequestException:
            detail = "No response received from eHRM API"
        log_activity(None, "PEGAWAI_INFO_ERROR", f"Error fetching pegawai info for NIP: {nip} - {detail}")
        logger.exception("eHRM fetch gagal untuk NIP %s", nip)
        raise EhrmError("Terjadi kesalahan pada server eHRM")
```

> Peningkatan dibanding EILN: retry otomatis saat token ditolak sebelum masa 24 jam habis, dan `select_for_update` mencegah banyak request login ke eHRM bersamaan.

### 5.7 Service Pegawai (`pegawai/services.py`)

```python
import random
import time

from django.db import IntegrityError, transaction

from audit.models import log_activity
from ehrm.client import fetch_pegawai_info
from .models import Pegawai


def map_ehrm_to_pegawai(info: dict) -> dict:
    """Mapping field eHRM → kolom Pegawai (lihat tabel §3.3)."""
    return {
        "nip": info.get("nip"),
        "foto": info.get("foto"),
        "kd_kelamin": Pegawai.KdKelamin.LAKI_LAKI if str(info.get("kdkelamin")) == "1"
                      else Pegawai.KdKelamin.PEREMPUAN,
        "nama": info.get("nama"),
        "email": info.get("email"),
        "email_pu": info.get("email_pu"),
        "telphp": info.get("telphp"),
        "nik": info.get("noktp") or "",
        "golongan": info.get("golongan"),
        "deskripsi_gol": info.get("deskripsi_gol"),
        "jabatan": info.get("jabatan"),
        "jabatan_lengkap": info.get("jabatan_lengkap"),
        "unor": info.get("unor"),
        "unker": info.get("unker"),
        "kdunit_id": info.get("kdunit"),
        "eselon": info.get("eselon"),
    }


def tambah_atau_sinkron_pegawai(nip: str, sync: bool = False, actor=None) -> tuple[str, int, Pegawai | None]:
    """Padanan POST /api/signup. Return (pesan, http_status, pegawai)."""
    pegawai = Pegawai.objects.filter(nip=nip).first()
    info = fetch_pegawai_info(nip)
    data = map_ehrm_to_pegawai(info)

    if pegawai is None:
        pegawai = Pegawai.objects.create(**data)
        log_activity(actor, "SIGNUP_SUCCESS", f"New pegawai registered: {data['nama']} (NIP: {data['nip']})")
        return "Pendaftaran berhasil!", 201, pegawai

    if sync:
        data.pop("nip")
        for field, value in data.items():
            setattr(pegawai, field, value)
        pegawai.save()
        log_activity(actor, "PEGAWAI_SYNC", f"Pegawai data synced with eHRM: {pegawai.nama} (NIP: {nip})")
        return "Data pegawai berhasil disinkronkan dengan eHRM.", 200, pegawai

    log_activity(actor, "SIGNUP_DUPLICATE", f"Duplicate signup attempt for NIP: {nip}")
    return ("Akun dengan NIP ini telah terdaftar. Jika Anda mengalami kesulitan untuk masuk, "
            "mohon hubungi administrator sistem."), 200, pegawai


def generate_internal_nip() -> str:
    """NIP internal untuk pegawai non-eHRM: 'MN' + 10 digit timestamp + 4 digit acak."""
    while True:
        candidate = f"MN{str(int(time.time() * 1000))[-10:]}{random.randint(0, 9999):04d}"
        if not Pegawai.objects.filter(nip=candidate).exists():
            return candidate


@transaction.atomic
def tambah_pegawai_manual(data: dict, actor=None) -> Pegawai:
    """Padanan POST /api/signup/manual. `data` sudah tervalidasi serializer."""
    nip = (data.get("nip") or "").strip() or generate_internal_nip()
    if Pegawai.objects.filter(nip=nip).exists() \
            or Pegawai.objects.filter(nik=data["nik"]).exists() \
            or Pegawai.objects.filter(email=data["email"]).exists():
        log_activity(actor, "MANUAL_SIGNUP_DUPLICATE",
                     f"Duplicate entry for NIP: {nip}, NIK: {data['nik']}, or Email: {data['email']}")
        raise ValueError("Pegawai sudah terdaftar")

    pegawai = Pegawai.objects.create(
        **{**data, "nip": nip},
        tipe_pengguna=Pegawai.TipePengguna.REGULAR,
        is_active=True,
    )
    log_activity(actor, "MANUAL_SIGNUP_SUCCESS",
                 f"Manual pegawai registration successful - Name: {pegawai.nama}, NIP: {nip}")
    return pegawai
```

### 5.8 Resolver unit kerja & Pengguna dari eHRM (`organisasi/services.py`, `accounts/services.py`)

```python
# organisasi/services.py
import re

from .models import UnitKerja


def normalize_kdunit(raw) -> str | None:
    digits = re.sub(r"\D", "", str(raw or ""))
    if not digits:
        return None
    return digits[:8] if len(digits) >= 8 else digits.zfill(8)


def resolve_unit_kerja_kdunit(raw) -> str | None:
    """Pilih kd_unit untuk scoping: parent_unit → unit_induk → diri sendiri → grup XX000000."""
    candidate = normalize_kdunit(raw)
    if not candidate:
        return None

    exact = UnitKerja.objects.filter(kd_unit=candidate).only("kd_unit", "parent_unit", "unit_induk").first()
    if exact:
        for code in ((exact.parent_unit or "").strip(), (exact.unit_induk or "").strip()):
            if code and UnitKerja.objects.filter(kd_unit=code).exists():
                return code
        return exact.kd_unit

    group = f"{candidate[:2]}000000"
    return group if UnitKerja.objects.filter(kd_unit=group).exists() else None
```

```python
# accounts/services.py
from django.contrib.auth import get_user_model

from audit.models import log_activity
from ehrm.client import fetch_pegawai_info
from organisasi.services import normalize_kdunit, resolve_unit_kerja_kdunit

Pengguna = get_user_model()


def buat_pengguna_dari_ehrm(*, nip, email_notifikasi, username=None, kdunit=None,
                            is_active=True, is_super_admin=False, description=None, actor=None):
    """Padanan POST /api/user/ehrm — akun ini yang nanti dipakai saat login SSO."""
    info = fetch_pegawai_info(nip)
    kdunit_child = normalize_kdunit(info.get("kdunit"))

    username = (username or info.get("email_pu") or info.get("email") or str(nip)).strip()
    name = (info.get("nama") or "").strip()
    if not username or not name:
        raise ValueError("Tidak bisa menentukan username/nama dari data eHRM")

    if Pengguna.objects.filter(username=username, is_deleted=False).exists():
        raise ValueError("Username sudah dipakai")

    kdunit_resolved = resolve_unit_kerja_kdunit(kdunit or info.get("kdunit"))
    if not kdunit_resolved:
        raise ValueError("Tidak bisa mencocokkan kdunit eHRM dengan master Unit Kerja. "
                         "Pastikan master unit kerja sudah tersinkron.")

    jabatan = f" Jabatan={info['jabatan']};" if info.get("jabatan") else ""
    user = Pengguna.objects.create_user(
        username=username,
        password=None,   # unusable → hanya bisa login via SSO (atau reset password)
        name=name[:50],
        email_notifikasi=email_notifikasi.strip(),
        description=description or
            f"EHRM;NIP={nip};KDUNIT_CHILD={kdunit_child or ''};KDUNIT_SELECTED={kdunit_resolved};{jabatan}",
        kdunit_id=kdunit_resolved,
        is_active=bool(is_active),
        is_super_admin=bool(is_super_admin),
        is_deleted=False,
    )
    log_activity(actor, "USER_CREATE_EHRM", f"Pengguna {username} dibuat dari eHRM (NIP {nip})")
    return user
```

### 5.9 Endpoint API (`pegawai/views.py`, `pegawai/urls.py`)

```python
# pegawai/views.py
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsSuperAdmin
from accounts.services import buat_pengguna_dari_ehrm
from ehrm.client import EhrmError, fetch_pegawai_info
from .models import Pegawai
from .services import tambah_atau_sinkron_pegawai, tambah_pegawai_manual


class PegawaiSerializer(serializers.ModelSerializer):
    kdunit = serializers.CharField(source="kdunit_id", allow_null=True, required=False)

    class Meta:
        model = Pegawai
        fields = ["id", "uuid", "nip", "nama", "foto", "kd_kelamin", "golongan", "deskripsi_gol",
                  "jabatan", "jabatan_lengkap", "unor", "unker", "kdunit", "is_active",
                  "created_at", "updated_at"]


class PegawaiManualSerializer(serializers.Serializer):
    nip = serializers.CharField(required=False, allow_blank=True, max_length=20)
    nama = serializers.CharField(max_length=255)
    nik = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    email_pu = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    telphp = serializers.CharField(max_length=15)
    golongan = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    deskripsi_gol = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    jabatan = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    jabatan_lengkap = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    unor = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    unker = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    kdunit_id = serializers.CharField(source="kdunit", required=False, allow_blank=True, allow_null=True)
    kd_kelamin = serializers.ChoiceField(choices=Pegawai.KdKelamin.choices, default=Pegawai.KdKelamin.LAKI_LAKI)


class PegawaiListView(APIView):
    """GET /api/pegawai?page=&limit=&search=   atau   ?uuid="""
    def get(self, request):
        if uuid := request.query_params.get("uuid"):
            pegawai = get_object_or_404(Pegawai, uuid=uuid)
            return Response({"message": "Data pegawai berhasil ditemukan",
                             "data": PegawaiSerializer(pegawai).data, "error": None})

        page = max(int(request.query_params.get("page", 1) or 1), 1)
        limit = max(int(request.query_params.get("limit", 10) or 10), 1)
        search = (request.query_params.get("search") or "").strip()

        qs = Pegawai.objects.all()
        if search:
            qs = qs.filter(Q(nama__icontains=search) | Q(nip__icontains=search) |
                           Q(jabatan__icontains=search) | Q(unor__icontains=search))
        total = qs.count()
        items = qs.order_by("-updated_at")[(page - 1) * limit: page * limit]
        total_pages = (total + limit - 1) // limit
        return Response({
            "message": "Data pegawai berhasil ditemukan",
            "data": {
                "pegawai": PegawaiSerializer(items, many=True).data,
                "pagination": {"total": total, "totalPages": total_pages, "currentPage": page,
                               "limit": limit, "hasNextPage": page < total_pages, "hasPrevPage": page > 1},
            },
            "error": None,
        })


class PegawaiPreviewView(APIView):
    """GET /api/pegawai-by-nip/<nip>/ — preview data eHRM tanpa menyimpan."""
    def get(self, request, nip):
        try:
            return Response({"message": "Data pegawai berhasil ditemukan",
                             "data": fetch_pegawai_info(nip), "error": None})
        except EhrmError as exc:
            return Response({"message": str(exc), "error": str(exc)}, status=exc.status_code)


class PegawaiSignupView(APIView):
    """POST /api/signup  {nip, sync}"""
    permission_classes = [IsAuthenticated]   # di EILN endpoint ini TIDAK diproteksi — lihat §6

    def post(self, request):
        nip = (request.data.get("nip") or "").strip()
        if not nip:
            return Response({"message": "NIP (Nomor Induk Pegawai) harus diisi. Silakan masukkan NIP Anda."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            message, code, _ = tambah_atau_sinkron_pegawai(nip, bool(request.data.get("sync")), request.user)
            return Response({"message": message}, status=code)
        except EhrmError as exc:
            return Response({"message": str(exc)}, status=exc.status_code)
        except IntegrityError:
            return Response({"message": "Data yang dimasukkan sudah ada dalam sistem."},
                            status=status.HTTP_400_BAD_REQUEST)


class PegawaiManualView(APIView):
    """POST /api/signup/manual"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = PegawaiManualSerializer(data=request.data)
        if not ser.is_valid():
            missing = ", ".join(ser.errors.keys())
            return Response({"message": f"Data tidak lengkap. Field yang harus diisi: {missing}",
                             "error": "Missing required fields", "missingFields": list(ser.errors.keys())},
                            status=status.HTTP_400_BAD_REQUEST)
        data = dict(ser.validated_data)
        data["kdunit_id"] = data.pop("kdunit", None) or None
        try:
            pegawai = tambah_pegawai_manual(data, request.user)
        except (ValueError, IntegrityError):
            return Response({"message": "Pegawai sudah terdaftar", "error": "Pegawai already exists"},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Pendaftaran pegawai berhasil",
                         "data": PegawaiSerializer(pegawai).data, "error": None},
                        status=status.HTTP_201_CREATED)


class PenggunaEhrmView(APIView):
    """POST /api/user/ehrm — buat akun login (untuk SSO) dari NIP."""
    permission_classes = [IsSuperAdmin]

    def post(self, request):
        nip = (request.data.get("nip") or "").strip()
        email = (request.data.get("email_notifikasi") or "").strip()
        if not nip or not email:
            return Response({"message": "Missing required fields",
                             "error": "nip dan email_notifikasi wajib diisi"}, status=400)
        try:
            user = buat_pengguna_dari_ehrm(
                nip=nip, email_notifikasi=email,
                username=request.data.get("username"), kdunit=request.data.get("kdunit"),
                is_active=request.data.get("is_active", True),
                is_super_admin=request.data.get("is_super_admin", False),
                description=request.data.get("description"), actor=request.user,
            )
        except EhrmError as exc:
            return Response({"message": str(exc)}, status=exc.status_code)
        except ValueError as exc:
            return Response({"message": str(exc), "error": str(exc)}, status=400)
        return Response({"message": "User created successfully (eHRM)",
                         "data": {"id": user.id, "uuid": str(user.uuid), "username": user.username,
                                  "name": user.name, "kdunit": user.kdunit_id}, "error": None},
                        status=201)
```

```python
# pegawai/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path("pegawai/", views.PegawaiListView.as_view()),
    path("pegawai-by-nip/<str:nip>/", views.PegawaiPreviewView.as_view()),
    path("signup/", views.PegawaiSignupView.as_view()),
    path("signup/manual/", views.PegawaiManualView.as_view()),
    path("user/ehrm/", views.PenggunaEhrmView.as_view()),
]
```

### 5.10 Frontend (template/JS) — alur tambah pegawai

```html
<input id="nip" maxlength="18" placeholder="NIP 18 digit">
<div id="preview"></div>
<button id="simpan" disabled>Simpan</button>

<script>
const csrftoken = document.cookie.match(/csrftoken=([^;]+)/)?.[1];
let found = false;

document.getElementById("nip").addEventListener("input", async (e) => {
  const nip = e.target.value.trim();
  const preview = document.getElementById("preview");
  found = false; document.getElementById("simpan").disabled = true;
  if (nip.length !== 18) { preview.textContent = ""; return; }
  preview.textContent = "Mencari data pegawai di eHRM...";
  const res = await fetch(`/api/pegawai-by-nip/${nip}/`, { credentials: "same-origin" });
  const json = await res.json();
  if (!res.ok) { preview.textContent = "Data eHRM tidak ditemukan. Gunakan input manual."; return; }
  preview.textContent = `${json.data.nama} — ${json.data.jabatan ?? ""} (${json.data.unker ?? ""})`;
  found = true; document.getElementById("simpan").disabled = false;
});

document.getElementById("simpan").addEventListener("click", async () => {
  const res = await fetch("/api/signup/", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrftoken },
    body: JSON.stringify({ nip: document.getElementById("nip").value.trim(), sync: found }),
  });
  alert((await res.json()).message);
});
</script>
```

> Perilaku EILN: `sync` dikirim `true` bila preview eHRM ditemukan — artinya bila NIP sudah ada, datanya otomatis diperbarui. Tombol **Sinkron** per baris di tabel juga memanggil `/api/signup/` dengan `sync: true`.

### 5.11 Variabel lingkungan Django

Sama dengan `.env` EILN (nama alias `SSOBaseUrl/SSOClientId/SSOClientSecret` didukung, jadi nilainya bisa disalin langsung):

```dotenv
# SSO — WAJIB (salin nilai dari .env EILN)
SSOBaseUrl=<issuer URL dari .env EILN>
SSOClientId=<client id>
SSOClientSecret=<client secret>
SSO_USERNAME_CLAIM=<sama dengan EILN>
SSO_AUTO_PROVISION=false

# SSO — OPSIONAL (EILN tidak mengisinya; default dipakai)
# SSO_SCOPE=openid profile email
# SSO_NAME=SSO

# eHRM — OPSIONAL (tidak ada di .env EILN).
# Kosongkan → fitur eHRM nonaktif, hanya input pegawai manual.
# EHRM_LOGIN_URL=https://apigw.pu.go.id/user/login
# EHRM_EMAIL=
# EHRM_PASSWORD=
# EHRM_API_KEY=
# EHRM_PEGAWAI_API_URL=http://apigw.pu.go.id/v1/ehrm/pegawai
```

> **Penting:** client SSO di IdP terdaftar dengan redirect URI EILN (`.../eiln/api/auth/callback/sso`). Untuk aplikasi Django, minta pengelola IdP **menambahkan** redirect URI `https://<domain>/oidc/callback/` atau buat client baru — jangan pakai client EILN tanpa itu, karena callback akan ditolak.

> **Tanpa eHRM:** Pengguna untuk login SSO dibuat lewat form/admin biasa (`Pengguna.objects.create_user(username=<nilai claim SSO>, password=None, kdunit_id=..., ...)`) atau aktifkan `SSO_AUTO_PROVISION=true` lalu admin mengatur `kdunit`/`is_super_admin` setelah login pertama. Di UI, sembunyikan tab "eHRM (NIP)" bila `settings.EHRM_ENABLED` bernilai `False`.

---

## 6. Catatan, Perbedaan & Perbaikan yang Disarankan

1. **Endpoint tambah pegawai di EILN tidak diproteksi.** `/api/signup` dan `/api/signup/manual` tidak dibungkus `authMiddleware`, sehingga siapa pun bisa memicu panggilan eHRM dan menambah data. Di Django, contoh di atas sudah memakai `IsAuthenticated`; pertimbangkan `IsSuperAdmin` bila hanya admin yang boleh.
2. **Mapping SSO hanya berdasarkan `username` (mutable).** Bila email/username di IdP berubah, user kehilangan akses. Disarankan simpan juga `sub` (claim immutable) di `Pengguna.sso_subject` saat login pertama, lalu cari berdasarkan `sso_subject` terlebih dahulu dan fallback ke `username`:
   ```python
   def filter_users_by_claims(self, claims):
       qs = self.UserModel.objects.active()
       if claims.get("sub") and (u := qs.filter(sso_subject=claims["sub"])).exists():
           return u
       return qs.filter(username=get_sso_username(claims))
   ```
   dan di `update_user` isi `user.sso_subject = claims["sub"]` bila kosong.
3. **Pengguna ≠ Pegawai.** Bila project Django perlu "user login = pegawai", tambahkan `Pengguna.pegawai = OneToOneField(Pegawai, null=True)` dan isi saat `buat_pengguna_dari_ehrm`, sehingga tidak perlu mem-parsing `description`.
4. **Status user diperiksa ulang tiap request.** Di EILN, JWT session berlaku 30 hari dan tidak mengecek ulang `is_active/is_deleted`. Dengan session Django berbasis DB, `request.user` dimuat ulang tiap request; pastikan `is_deleted=True` juga memblokir akses (mis. `ModelBackend.user_can_authenticate` di-override, atau set `is_active=False` saat soft-delete).
5. **Data sensitif dari eHRM** (NIK/`noktp`, telepon, email) — batasi field yang dikembalikan endpoint preview untuk non-admin, dan jangan log payload lengkap.
6. **Token eHRM** — EILN mengasumsikan TTL 24 jam tanpa retry; versi Django di atas menambahkan retry saat 401.
7. **Error handling** — pesan detail error hanya ke log, ke client hanya pesan generik (sama dengan EILN).
8. **Kode lama yang tidak perlu diporting**: `src/lib/auth.js` (token JWE custom + `refresh_tokens`), `verify-otp.js`, `refresh-token.js`, `get-refresh-token.js` adalah mekanisme login lama berbasis OTP/NIP yang sudah digantikan NextAuth; skema Prisma-nya pun sudah tidak sinkron (mis. `OTP.pegawai_id` vs `pengguna_id`). Tidak perlu dibawa ke Django — gunakan session Django + OIDC.

---

## 7. Checklist Implementasi

- [ ] Daftarkan aplikasi di IdP: redirect URI `https://<domain>/oidc/callback/`, post-logout URI, scope `openid profile email`, aktifkan PKCE.
- [ ] Konfirmasi ke pengelola IdP claim mana yang berisi username/email PU → set `SSO_USERNAME_CLAIM`.
- [ ] Set env SSO (wajib) dan eHRM (opsional); pastikan server dapat mengakses `.well-known` issuer (dan `apigw.pu.go.id` bila eHRM dipakai).
- [ ] Buat model + `makemigrations` + `migrate` (set `AUTH_USER_MODEL` **sebelum** migrasi pertama).
- [ ] Sinkronkan master `unit_kerja` terlebih dahulu (diperlukan oleh `resolve_unit_kerja_kdunit`).
- [ ] Buat superuser (`createsuperuser`) untuk login credentials pertama.
- [ ] Tambahkan Pengguna untuk tiap admin unit (via eHRM `POST /api/user/ehrm/` atau manual bila eHRM tidak dikonfigurasi), lalu uji login SSO.
  - [ ] Tanpa env eHRM → endpoint eHRM mengembalikan 503 dan input manual tetap berfungsi.
- [ ] Uji skenario:
  - [ ] Login SSO user terdaftar → masuk, `email_notifikasi` terisi bila kosong.
  - [ ] Login SSO user tidak terdaftar (`SSO_AUTO_PROVISION=false`) → ditolak dengan pesan.
  - [ ] Login SSO dengan `SSO_AUTO_PROVISION=true` → Pengguna baru terbentuk tanpa password usable.
  - [ ] User `is_active=False` / `is_deleted=True` → ditolak.
  - [ ] `/accounts/login/?sso=1` langsung redirect ke IdP.
  - [ ] Tambah pegawai via NIP baru → 201; NIP sudah ada tanpa sync → pesan duplikat; dengan sync → data terbarui.
  - [ ] Tambah pegawai manual tanpa NIP → NIP `MN…` terbentuk; duplikat NIK/email → 400.
  - [ ] Token eHRM kedaluwarsa / 401 → token diperbarui otomatis.
  - [ ] Endpoint tambah pegawai menolak request tanpa login (401/403).
