# Rencana Implementasi — SSO, e-HRM, Role Ganda, Nomor HP & Edit Profil

> **Status (19 Oktober 2026):** Fase 1–4 selesai; Fase 5 selesai untuk alur inti + stub DEBUG
> (adaptor protokol menunggu **Q1**); Fase 6 belum dikerjakan (menunggu produksi stabil).
> Semua dikerjakan dalam satu cabang (`alex/improvement_12102026`), belum dipecah per PR.
>
> **Penyimpangan dari rancangan:**
> - `Notification.untuk_peran` diturunkan otomatis dari namespace `redirect_url`
>   (`notifications.services.peran_untuk_url`), tidak dikirim satu per satu oleh pemanggil
>   `_create`. Parameter `untuk_peran=` tetap tersedia untuk menimpa.
> - `daftar_peran()` selalu terurut `URUTAN_PERAN`; preferensi peran terakhir (`User.role`)
>   diterapkan di `PeranAktifMiddleware` (`tentukan_peran`).
> - Signal kompatibilitas membuat `PeranUser` setiap kali `User` disimpan dengan `role` yang
>   belum tercatat (bukan hanya saat dibuat), agar seed/test lama yang mengganti `role` tetap
>   jalan. Peran yang sudah dicabut tidak diaktifkan ulang.
> - Penerima Admin Unor & `unit_admin_id()` memakai `User.unit_organisasi` sebagai cadangan bila
>   `PeranUser(admin_unor).unit_organisasi` kosong (data lama).
> - Daftar User kini menampilkan semua user (sebelumnya hanya Pegawai/Admin Unor/Admin BPSDM);
>   Tambah User menyediakan Admin Biro PAKLN dan tidak lagi menyediakan Pegawai (§6.3).
> - Data kepegawaian akun e-HRM di Edit User tampil baca-saja (kecuali sisa cuti); reset password
>   akun SSO lewat checkbox "Hapus password".
> - AB-12: penanda "Pengajuan Anda" tampil di halaman pratinjau/proses admin
>   (`_ringkasan_pengajuan.html`); tombol aksi tidak disembunyikan, tetapi server menolak (403).
>   Badge di tabel dasbor belum dibuat.
> - `SSO_ENABLED=True` saat ini hanya menampilkan pesan "Login SSO belum tersedia" sampai adaptor
>   protokol (§7.4) diimplementasikan.
> - Rate limit login (IMPROVEMENT_PLAN §10) belum dikerjakan.
> - Test & uji migrasi dijalankan dengan override SQLite (user MySQL tidak berhak membuat
>   database test); migrasi belum diuji pada salinan database produksi.
> **Sumber kebutuhan:** [IMPROVEMENT_PLAN_19102026.MD](IMPROVEMENT_PLAN_19102026.MD). Kode aturan
> `AB-xx` dan pertanyaan `Qx` di dokumen ini merujuk ke sana.
> **Terkait:** [SYSTEM_LOGGING.MD](SYSTEM_LOGGING.MD), [SKENARIO_NOTIFIKASI_SURAT.md](SKENARIO_NOTIFIKASI_SURAT.md),
> [PASPOR_DESIGN_GUIDE.MD](PASPOR_DESIGN_GUIDE.MD).

---

## Daftar Isi

1. [Ringkasan & Urutan Kerja](#1-ringkasan--urutan-kerja)
2. [Prinsip Implementasi](#2-prinsip-implementasi)
3. [Fase 1 — Nomor HP & Kontak](#3-fase-1--nomor-hp--kontak)
4. [Fase 2 — Akun Mandiri (Username & Password)](#4-fase-2--akun-mandiri-username--password)
5. [Fase 3 — Role Ganda](#5-fase-3--role-ganda)
6. [Fase 4 — Integrasi e-HRM](#6-fase-4--integrasi-e-hrm)
7. [Fase 5 — Login SSO](#7-fase-5--login-sso)
8. [Fase 6 — Pembersihan](#8-fase-6--pembersihan)
9. [Daftar Audit Pemakaian `role` & `unit_organisasi`](#9-daftar-audit-pemakaian-role--unit_organisasi)
10. [Konfigurasi & Deploy](#10-konfigurasi--deploy)
11. [Definition of Done](#11-definition-of-done)

---

## 1. Ringkasan & Urutan Kerja

| Fase | Judul | Bergantung pada | Bisa mulai |
|---|---|---|---|
| 1 | Nomor HP & kontak | — | Sekarang |
| 2 | Akun mandiri (username & password) | Fase 1 (field `sso_sub`) | Sekarang |
| 3 | Role ganda | — (paralel dengan 1–2, tetapi merge setelahnya) | Sekarang |
| 4 | Integrasi e-HRM | Fase 1 (kunci kontak), Fase 3 (`PeranUser`) | Sekarang, dengan stub |
| 5 | Login SSO | Fase 2, 3, 4 | Alur internal sekarang; adaptor protokol menunggu **Q1** |
| 6 | Pembersihan | Fase 1–5 | Setelah produksi stabil |

- **Satu fase = satu PR** ke `development`, masing-masing dengan migrasi dan test-nya
  sendiri.
- **Penomoran migrasi** `accounts` dimulai setelah `0007_alter_user_role_admin_bko`.

## 2. Prinsip Implementasi

1. **Peran aktif menimpa `request.user.role` di memori** (Fase 3). Dengan begitu ±100
   pemanggilan `role_required` dan pemeriksaan `user.role` pada user yang sedang login
   tidak perlu diubah. Yang wajib diubah hanya:
   - query yang mencari user **berdasarkan role** di database;
   - pemakaian `role` atau `unit_organisasi` pada **user lain** (lihat [§9](#9-daftar-audit-pemakaian-role--unit_organisasi)).
2. **Whitelist field per peran di server.** View Profil tidak pernah memakai
   `request.POST` untuk field yang tidak diizinkan, sekalipun HTML dimanipulasi.
3. **Integrasi eksternal di balik antarmuka + stub.** e-HRM dan SSO mengikuti pola
   [paspor/integrasi/pintar.py](../../paspor/integrasi/pintar.py): dataclass frozen,
   stub lokal saat URL kosong, HTTP saat dikonfigurasi.
4. **Semua perubahan akun tercatat** lewat `logs.utils.record_activity`. Kode
   aktivitas baru ditambahkan ke `ActivityLog.Aktivitas`; tidak perlu migrasi.
5. **Nomor HP selalu disimpan ternormalisasi** (`62…`). Format tampilan hanya
   dilakukan di template filter.

---

## 3. Fase 1 — Nomor HP & Kontak

**Tujuan:** AB-14, AB-15, AB-17, AB-18 (field kunci), AB-19, dan AB-22. Admin Biro
PAKLN dapat mengelola email dan nomor HP.

### 3.1 Model & migrasi

[accounts/models.py](../../accounts/models.py), class `User`. Migrasi
`0008_user_kontak_sso.py`.

```python
no_hp = models.CharField("Nomor HP (WhatsApp)", max_length=20, blank=True, db_index=True)
sso_sub = models.CharField(max_length=100, null=True, blank=True, unique=True, editable=False)

class SumberAkun(models.TextChoices):
    SSO = "sso", "SSO"
    LOKAL = "lokal", "Lokal"
sumber_akun = models.CharField(max_length=10, choices=SumberAkun.choices, default=SumberAkun.LOKAL)

email_dikunci = models.BooleanField(default=False)
no_hp_dikunci = models.BooleanField(default=False)
ehrm_sinkron_at = models.DateTimeField(null=True, blank=True)
```

Catatan:

- `sso_sub` dan `ehrm_sinkron_at` sudah ditambahkan sekarang (meskipun dipakai di
  Fase 4–5) agar migrasi `User` cukup satu.
- Tambah method `User.punya_sso()`, yang mengembalikan `bool(self.sso_sub)`.

### 3.2 Normalisasi nomor HP

File baru `accounts/validators.py`:

```python
def normalisasi_no_hp(nilai: str) -> str:
    """'0812-3456 7890' / '+62 812…' / '62812…' -> '6281234567890'.
    Raise ValidationError bila bukan 10–15 digit setelah normalisasi."""
```

Aturan:

1. Buang semua karakter kecuali digit dan `+`.
2. Awalan `+62` diubah menjadi `62`, dan `0` menjadi `62`.
3. Hasil wajib diawali `62` dan berisi 10–15 digit.

### 3.3 Template filter

[pengajuan/templatetags/pengajuan_extras.py](../../pengajuan/templatetags/pengajuan_extras.py):

- `format_hp`: `6281234567890` menjadi `+62 812-3456-7890`.
- `wa_link`: menghasilkan `https://wa.me/6281234567890`. Bila input kosong,
  menghasilkan string kosong.
- Partial baru `templates/partials/_kontak_wa.html`: ikon WhatsApp beserta nomor
  terformat, `target="_blank" rel="noopener"`. Bila kosong, menampilkan "—".

### 3.4 Form Kelola User (Admin Biro PAKLN)

[accounts/forms.py](../../accounts/forms.py):

- **`KontakForm`** (baru, dipakai ulang di Fase 2):
  - field `email` (wajib) dan `no_hp` (wajib);
  - `clean_no_hp` memanggil `normalisasi_no_hp`;
  - `clean_email` memeriksa keunikan (`iexact`, kecuali instance);
  - `save(user, *, kunci=False)`: bila `kunci=True`, field yang **berubah** di-set
    `*_dikunci=True`.
- **`TambahUserForm`**: tambah `email` dan `no_hp` (wajib, normalisasi). `save()`
  mengisi `sumber_akun=LOKAL`.
- **`EditUserForm`**:
  - tambah `email` dan `no_hp`;
  - `save()` membandingkan nilai lama dan baru, lalu mengunci field yang berubah
    **bila** `user.punya_sso()` (akun lokal tidak perlu dikunci);
  - tambah checkbox `buka_kunci_email` dan `buka_kunci_no_hp`, yang hanya tampil bila
    field tersebut dikunci.

### 3.5 View & template Kelola User

[pengajuan/views_pakln.py](../../pengajuan/views_pakln.py):

- `users_data`:
  - tambah kolom **No. HP** (format + tautan WA) dan **Sumber Akun**;
  - tambah parameter filter `?tanpa_hp=1`, yang menghasilkan `no_hp=""`.
- `edit_user`: catat log `akun.ubah_kontak` (nilai lama → baru) dan
  `akun.buka_kunci_kontak`.

Template:

- [templates/pakln/users.html](../../templates/pakln/users.html): kolom baru dan
  checkbox filter "Tanpa No. HP".
- [templates/pakln/edit_user.html](../../templates/pakln/edit_user.html): bagian
  "Kontak" berisi `email` dan `no_hp`. Badge **Dikunci** ditampilkan bila
  `*_dikunci`, beserta checkbox buka kunci.

### 3.6 Tampilan kontak & banner

- [templates/akun/profil.html](../../templates/akun/profil.html): Email dan No. HP
  ditampilkan **baca-saja** di Data Personal, dengan keterangan
  "Perubahan melalui Admin Biro PAKLN". Pengecualian untuk Admin Biro PAKLN dibuat di
  Fase 2.
- **Detail pengajuan di sisi admin** (Unor, BPSDM, BKO, PAKLN): pakai
  `_kontak_wa.html` untuk pegawai pengusul. Template yang perlu dicari adalah template
  detail/proses di `templates/unor/`, `templates/bpsdm/`, `templates/bko/`, dan
  `templates/pakln/` yang menampilkan nama/NIP pengusul. Tambahkan baris
  "No. HP (WhatsApp)".
- **Banner nomor HP kosong (AB-19):**
  - context processor baru `accounts.context_processors.status_profil`, yang
    menghasilkan `{"no_hp_kosong": user.is_authenticated and not user.no_hp}`;
  - daftarkan di `settings.TEMPLATES`;
  - [templates/base.html](../../templates/base.html): banner `notification is-warning`
    di atas konten.
    - Teks untuk selain Admin Biro PAKLN: "Nomor HP belum tercatat — hubungi Admin
      Biro PAKLN."
    - Teks untuk Admin Biro PAKLN: tautan ke Profil.

### 3.7 Log

Kode baru di `ActivityLog.Aktivitas`:

- `UBAH_KONTAK = "akun.ubah_kontak"`
- `BUKA_KUNCI_KONTAK = "akun.buka_kunci_kontak"`

### 3.8 Seed

- `seed_demo_data`, `seed_admin_unor_org_units`, `seed_pegawai_org_units`: isi `no_hp`
  dummy yang unik per user (misalnya `62811000000xx`) dan `email`.
- Bila deploy produksi memakai seed (`DJANGO_SEED_*`), pastikan seed tidak menimpa
  nomor yang sudah ada.

### 3.9 Test

File baru `accounts/tests_kontak.py`:

- `normalisasi_no_hp` diuji dengan input `0812-3456-7890`, `+62 812 3456 7890`,
  `6281234567890`, `812345` (ditolak), `0812abc` (ditolak), dan 16 digit (ditolak).
- Filter `format_hp` dan `wa_link`, termasuk input kosong.
- Admin Biro PAKLN:
  - membuat user lokal tanpa `no_hp` akan ditolak;
  - mengedit `no_hp` user ber-`sso_sub` membuat `no_hp_dikunci=True`;
  - mengedit user lokal tidak mengunci field;
  - buka kunci mengembalikan nilai `False`.
- Role non-PAKLN mengakses `pakln:edit_user` mendapat 403.
- Banner tampil untuk user dengan `no_hp=""`, dan tidak tampil bila terisi.
- Filter `?tanpa_hp=1` hanya mengembalikan user tanpa nomor HP.

---

## 4. Fase 2 — Akun Mandiri (Username & Password)

**Tujuan:** AB-04, AB-07, AB-16, AB-20, dan AB-21.

### 4.1 Form

[accounts/forms.py](../../accounts/forms.py):

| Form | Basis | Catatan |
|---|---|---|
| `UbahUsernameForm` | `forms.ModelForm` (`fields=["username"]`) | `clean_username`: strip, unik `iexact` kecuali diri sendiri. Opsional: tolak 18 digit angka yang bukan NIP sendiri. |
| `AturPasswordForm` | `django.contrib.auth.forms.SetPasswordForm` | Hanya bila `not user.has_usable_password()`. |
| `GantiPasswordForm` | `django.contrib.auth.forms.PasswordChangeForm` | Hanya bila `user.has_usable_password()`. |
| `HapusPasswordForm` | `forms.Form` dengan `password_lama` | Hanya bila `user.punya_sso() and user.has_usable_password()`. `save()` memanggil `set_unusable_password()`. |
| `KontakForm` | dari Fase 1 | Di Profil **hanya** bila peran aktif `admin_pakln`, dengan `kunci=user.punya_sso()`. |

### 4.2 View Profil

[pengajuan/views_pegawai.py](../../pengajuan/views_pegawai.py), fungsi `profil`.

Tambah cabang baru untuk `aksi` (pola `aksi` yang sudah ada dipertahankan):

```python
AKSI_AKUN = {
    "ubah_username": UbahUsernameForm,
    "atur_password": AturPasswordForm,
    "ganti_password": GantiPasswordForm,
    "hapus_password": HapusPasswordForm,
    "ubah_kontak": KontakForm,          # hanya admin_pakln
}
```

- **Prasyarat tiap aksi.** Cek prasyarat (lihat tabel §4.1). Bila tidak terpenuhi,
  tampilkan `messages.error` lalu redirect. Jangan sampai terjadi 500.
- **Setelah ganti/atur password:** `update_session_auth_hash(request, user)`.
- **Bila form tidak valid:** render ulang halaman Profil dengan form yang berisi error
  dan tandai bagian yang terbuka (jangan redirect, agar pesan error tidak hilang).
  Konsekuensinya, `profil` perlu membangun context lengkap di dua jalur. Pindahkan
  pembuatan context ke helper `_context_profil(request, **form_override)`.
- **Log:**
  - `akun.ubah_username` (lama → baru);
  - `akun.atur_password`, `akun.ganti_password`, `akun.hapus_password` (tanpa nilai);
  - `akun.ubah_kontak`.

### 4.3 Template Profil

[templates/akun/profil.html](../../templates/akun/profil.html):

- **Bagian "Akun" baru:**
  - username dengan tombol **Ubah** (form inline atau modal, mengikuti pola modal
    yang ada di `base.html`);
  - metode login: "SSO", "SSO + Username & Password", atau "Username & Password"
    (lokal);
  - daftar peran baca-saja. Untuk Fase 2 cukup `user.get_role_display`; diganti
    daftar `PeranUser` di Fase 3.
- **Bagian "Keamanan" baru:** tampilkan tombol sesuai kondisi, yaitu Atur Password,
  Ganti Password, atau Hapus Password.
- **Email/No. HP:** untuk `admin_pakln`, tampilkan tombol **Ubah** yang memakai
  `KontakForm`. Untuk role lain, tampil baca-saja seperti Fase 1.
- Label wajib otomatis bekerja lewat skrip penanda `*` yang sudah ada di `base.html`.

### 4.4 Login form

[accounts/views.py](../../accounts/views.py), fungsi `login_view`:

- Bila `authenticate` gagal, cari user (`username__iexact`). Bila user ditemukan,
  aktif, dan `not has_usable_password()`, tampilkan pesan "Akun ini belum memiliki
  password. Masuk dengan SSO, lalu atur password di menu Profil." Untuk kasus lain,
  tetap tampilkan pesan generik.
- Catatan keamanan: pesan khusus ini membocorkan keberadaan username. Hal ini bisa
  diterima karena username bukan rahasia di lingkungan internal. Bila tidak
  diinginkan, cukup tampilkan pesan generik ditambah petunjuk SSO statis di halaman.
- Login gagal tetap dicatat `auth.login_failed` (sudah ada lewat signal).

### 4.5 Test

File baru `accounts/tests_profil.py`:

**Whitelist:**

- POST `ubah_username` oleh pegawai dengan tambahan `email`, `no_hp`, `nama`, `role`:
  hanya username yang berubah.
- Pegawai mengirim `aksi=ubah_kontak`: ditolak, data tidak berubah.
- Admin Biro PAKLN mengirim `ubah_kontak`: email & nomor HP berubah, dan tetap tidak
  bisa mengubah `role`.

**Username:**

- Username duplikat beda huruf besar/kecil ditolak.

**Password:**

- Akun tanpa password bisa `atur_password` tanpa password lama.
- `ganti_password` tanpa password lama yang benar ditolak.
- Setelah ganti password, sesi tetap login (`client.get` ke Profil mengembalikan 200).
- `hapus_password` pada akun lokal ditolak.
- `hapus_password` pada akun ber-`sso_sub` berhasil, dan setelah itu login via form
  gagal dengan pesan SSO.

**Log:**

- Log tercatat, dan field `detail` tidak memuat password.

---

## 5. Fase 3 — Role Ganda

**Tujuan:** AB-08 s.d. AB-13.

### 5.1 Model & migrasi

Model baru `accounts.PeranUser` (lihat skema di IMPROVEMENT_PLAN §5.2):

- Migrasi `0009_peranuser.py` membuat tabel.
- Migrasi `0010_isi_peranuser.py` (RunPython) membuat, untuk setiap `User`,
  `PeranUser(user, role=user.role, unit_organisasi=user.unit_organisasi if role == admin_unor)`.
  `reverse` = hapus semua.
- Tambah `clean()` di `PeranUser`:
  - `admin_unor` wajib punya unit;
  - `pegawai` wajib punya `PegawaiProfile`.

Method `User`:

```python
def daftar_peran(self):            # cache per instance (self._cache_peran)
    ...
def punya_peran(self, role): ...
def unit_admin_id(self):           # unit PeranUser(admin_unor); fallback self.unit_organisasi_id
    ...
```

`is_pegawai()` / `is_admin_*()` tetap membaca `self.role` (peran aktif). Untuk "apakah
user memiliki peran X", pakai `punya_peran`.

### 5.2 Middleware peran aktif

File baru `accounts/middleware.py`, `PeranAktifMiddleware`, dipasang tepat setelah
`AuthenticationMiddleware`:

```python
def __call__(self, request):
    user = request.user  # SimpleLazyObject; evaluasi hanya bila authenticated
    if user.is_authenticated:
        peran = request.session.get("peran_aktif")
        dimiliki = user.daftar_peran()
        if peran not in dimiliki:
            peran = user.role if user.role in dimiliki else (dimiliki[0] if dimiliki else user.role)
            request.session["peran_aktif"] = peran
        user._role_db = user.role
        user.role = peran
    return self.get_response(request)
```

**Penjaga agar peran aktif tidak tersimpan ke database.** Tambahkan override di
`User.save()`:

```python
def save(self, *args, **kwargs):
    role_db = self.__dict__.get("_role_db")
    if role_db is not None and self.role != role_db:
        aktif, self.role = self.role, role_db
        try:
            return super().save(*args, **kwargs)
        finally:
            self.role = aktif
    return super().save(*args, **kwargs)
```

Urutan prioritas peran saat sesi baru:
*admin_pakln → admin_unor → admin_bko → admin_bpsdm → pegawai*. Aturan ini
dikodekan sebagai `URUTAN_PERAN` di `accounts/models.py`, dan `daftar_peran()`
mengembalikan daftar yang sudah terurut. Bila `User.role` (peran terakhir) dimiliki,
peran itu didahulukan.

### 5.3 Ganti peran

- **URL:** `path("akun/peran/", account_views.ganti_peran, name="ganti_peran")` di
  [paspor_project/urls.py](../../paspor_project/urls.py).
- **View** `ganti_peran` (`@login_required`, `@require_POST`):
  1. validasi `punya_peran`;
  2. `request.session["peran_aktif"] = peran`;
  3. `User.objects.filter(pk=user.pk).update(role=peran)`, supaya peran ini menjadi
     default pada login berikutnya;
  4. log `akun.ganti_peran`;
  5. `redirect("home")`.
- **UI:** partial baru `templates/partials/_peran_switcher.html`, disisipkan di
  header `base.html`. Partial hanya tampil bila `user.daftar_peran|length > 1`.
  Isinya dropdown dengan beberapa `<form method="post">` (satu per peran), dan peran
  aktif ditandai.
- **Badge peran aktif** di header untuk semua user admin (sudah ada `user.get_role_display`
  di Profil; tambahkan juga di header).

### 5.4 Refactor penerima notifikasi

[notifications/services.py](../../notifications/services.py):

```python
def _pemegang_peran(role, **filter_peran):
    from accounts.models import User
    return User.objects.filter(
        is_active=True, peran_list__role=role, peran_list__is_active=True,
        **{f"peran_list__{k}": v for k, v in filter_peran.items()},
    ).distinct()
```

- `_admin_unor_recipients`: `_pemegang_peran(ADMIN_UNOR, unit_organisasi_id=unit.id)`.
- `_admin_bpsdm_recipients` / `_admin_pakln_recipients` / `_admin_bko_recipients`:
  `_pemegang_peran(...)`.
- **Peran tujuan per notifikasi.** Notifikasi digabung (AB-13), tetapi tautannya harus
  dibuka dengan peran yang tepat:
  - tambah field `Notification.untuk_peran = CharField(20, blank=True)` (migrasi
    `notifications`);
  - `_create(recipients, *, untuk_peran="", ...)` mengisi field ini;
  - setiap pemanggil `_create` mengirim peran sesuai helper penerima (Admin Unor →
    `admin_unor`, pegawai pengusul → `pegawai`, dan seterusnya).
- **Deduplikasi** di `_create`: satu baris per `(recipient, untuk_peran)`. Untuk
  `_penerima_bko_semua`, user yang muncul di beberapa kelompok mendapat satu baris per
  peran. Ini sengaja, karena tautan tiap peran berbeda.
- [notifications/views.py](../../notifications/views.py), fungsi `go`: bila
  `notif.untuk_peran` diisi, berbeda dari peran aktif, dan `request.user.punya_peran(...)`,
  maka set `session["peran_aktif"]` sebelum redirect. Dengan begitu, mengklik
  notifikasi Admin Unor saat sedang menjadi Pegawai tidak berakhir 403.
- [templates/notifications/_item.html](../../templates/notifications/_item.html):
  tampilkan label kecil peran bila `user.daftar_peran|length > 1`.

### 5.5 Cakupan unit Admin Unor

Ganti `user.unit_organisasi_id` menjadi `user.unit_admin_id()` pada:

- [pengajuan/views_unor.py:27-29](../../pengajuan/views_unor.py#L27-L29);
- [pengajuan/report.py:49-51](../../pengajuan/report.py#L49-L51);
- fungsi lain di `report.py` yang memakai unit admin, misalnya `pembatalan_menunggu`
  dan cabang `ADMIN_UNOR` di sekitar baris 129 (lihat [§9](#9-daftar-audit-pemakaian-role--unit_organisasi)).

`User.get_unit_organisasi()`: untuk peran aktif `admin_unor`, kembalikan unit
`PeranUser`. Untuk `pegawai`, kembalikan unit profil (perilaku sekarang).

### 5.6 Larangan memproses pengajuan sendiri (AB-12)

- Helper baru di [pengajuan/decorators.py](../../pengajuan/decorators.py):

  ```python
  def tolak_pengajuan_sendiri(request, pengajuan):
      if pengajuan.pegawai_id == request.user.pk and request.user.role != User.Role.PEGAWAI:
          raise PermissionDenied("Anda tidak dapat memproses pengajuan milik sendiri.")
  ```

- Panggil helper ini di setiap view aksi admin terhadap pengajuan (teruskan,
  kembalikan, setujui, selesai, proses BKO, rekomendasi BPSDM, keputusan pembatalan).
  Daftar view-nya ada di `views_unor.py`, `views_bpsdm.py`, `views_bko.py`,
  `views_pakln.py`, dan `pembatalan.py`.
- Di daftar/dashboard admin, pengajuan milik sendiri **tetap tampil** dengan badge
  "Pengajuan Anda" dan tanpa tombol aksi.

### 5.7 Kelola peran (Admin Biro PAKLN)

- **Form** `KelolaPeranForm` di [accounts/forms.py](../../accounts/forms.py):
  - checkbox per role admin;
  - pilihan unit untuk `admin_unor`.
  - `pegawai` tidak bisa dicentang/dihapus manual: otomatis ada bila user punya
    `PegawaiProfile`.
  - Validasi: minimal satu peran.
- [pengajuan/views_pakln.py](../../pengajuan/views_pakln.py), fungsi `edit_user`:
  bagian "Peran" memakai form ini.
  - Mencabut peran = `is_active=False`. Baris tidak dihapus, demi jejak audit.
  - Mencabut peran yang sedang aktif di sesi user lain aman, karena middleware jatuh ke
    peran lain pada request berikutnya.
- **Log:** `akun.peran_diberikan` / `akun.peran_dicabut`.
- **`TambahUserForm`:** setelah `user.save()`, buat `PeranUser` sesuai pilihan. Akun
  admin darurat **tidak** mendapat peran `pegawai` (Q6).
- **`users_data`:** kolom Peran menampilkan semua peran (badge). Filter role memakai
  `peran_list__role`.

### 5.8 Test

File baru `accounts/tests_peran.py`. Fixture: user `ganda` dengan peran Pegawai (+
`PegawaiProfile` unit A) dan Admin Unor (unit B).

**Peran aktif & middleware:**

- Login → peran aktif `admin_unor` (prioritas) → dashboard unor 200, beranda pegawai
  403.
- Setelah `ganti_peran` ke pegawai, hasilnya terbalik dan sidebar berubah.
- POST `ganti_peran` dengan `admin_pakln` (tidak dimiliki) ditolak.
- `request.user.save()` saat peran aktif berbeda tidak mengubah kolom `role` di
  database.

**Cakupan unit & AB-12:**

- Sebagai Admin Unor, `ganda` melihat pengajuan unit B, bukan unit A.
- Pengajuan milik `ganda` (dibuat sebagai pegawai, unit A): Admin Unor lain di unit A
  bisa memprosesnya, sedangkan `ganda` sebagai Admin Unor (bila unitnya sama) mendapat
  403.

**Notifikasi:**

- Pengajuan unit B yang dikirim menghasilkan notifikasi `untuk_peran=admin_unor` untuk
  `ganda`.
- Membuka `go` saat peran aktif pegawai mengubah peran ke admin_unor dan redirect
  berhasil.
- Penerima tidak menerima notifikasi ganda untuk peran yang sama.

**Kelola peran & migrasi:**

- Mencabut peran Admin Unor → request berikutnya jatuh ke peran pegawai.
- Data migration: setiap user lama punya tepat satu `PeranUser` yang sama dengan
  `role`.

**Regresi:** seluruh suite test lama (`pengajuan/tests*.py`, `logs/tests*.py`) harus
tetap hijau. Fixture lama yang membuat `User(role=...)` perlu helper yang sekaligus
membuat `PeranUser`. Tambahkan juga signal `post_save` sementara: bila `User` baru
dibuat tanpa `PeranUser`, buat satu dari `role`. Signal ini menjaga kompatibilitas
seed dan test, lalu dihapus di Fase 6.

---

## 6. Fase 4 — Integrasi e-HRM

**Tujuan:** AB-02 dan AB-18 (sinkron menghormati kunci), serta pra-daftar via NIP.

### 6.1 Klien

File baru `paspor/integrasi/ehrm.py`:

```python
@dataclass(frozen=True)
class DataPegawai:
    nip: str
    nama: str
    jabatan: str
    pangkat_golongan: str
    unit_kerja: str
    kode_unit_organisasi: str
    email: str
    no_hp: str

class EhrmTidakTersedia(Exception): ...

def ambil_pegawai(nip: str) -> DataPegawai | None:
    """None = NIP tidak ditemukan. EhrmTidakTersedia = gangguan jaringan/server."""
```

- Bila `settings.EHRM_API_URL` kosong, dipakai stub dari dict lokal (data
  `seed_pegawai_org_units`).
- **HTTP:**
  - `urllib.request` dengan timeout `EHRM_TIMEOUT` (default 5 detik), seperti
    `pintar.py`;
  - header autentikasi dari `EHRM_API_TOKEN`. Skema autentikasi disesuaikan dengan
    spesifikasi (Q2).

### 6.2 Sinkronisasi

File baru `accounts/ehrm_sync.py`:

```python
def sinkron_profil(user, data: DataPegawai) -> list[str]:
    """Perbarui PegawaiProfile + User dari data e-HRM. Kembalikan daftar field
    yang berubah (untuk log). Email/no_hp dilewati bila *_dikunci."""

def buat_user_dari_ehrm(data: DataPegawai, *, sso_sub=None) -> User:
    """User(sumber_akun=SSO, username=nip, unusable password) + PegawaiProfile
    + PeranUser(pegawai). Dalam transaction.atomic."""
```

- **Pemetaan unit:** `UnitOrganisasi.objects.filter(<kolom kode>=data.kode_unit_organisasi).first()`.
  Kolom kode perlu dicek di [wiki/tables/UNIT_ORGANISASI.MD](../tables/UNIT_ORGANISASI.MD).
  Bila tidak ditemukan, unit lama dipertahankan dan dicatat `logger.warning`.
- **`no_hp`:** jalankan `normalisasi_no_hp`. Bila nilai e-HRM tidak valid, abaikan
  dan catat warning, jangan sampai error.
- **Username:** `username` untuk user baru = NIP. Bila NIP sudah dipakai sebagai
  username orang lain, tambahkan sufiks `-1`, `-2`, dan seterusnya.
- Setelah sinkron, set `user.ehrm_sinkron_at = timezone.now()`.

### 6.3 Fitur Admin Biro PAKLN

Di `edit_user`:

- **Tombol "Sinkron ulang dari e-HRM"** (`aksi=sinkron_ehrm`), hanya untuk user yang
  memiliki `PegawaiProfile`. Pesan sukses menyebut field yang berubah.
- **Tombol "Kembalikan ke data e-HRM"** per field yang dikunci: buka kunci lalu
  langsung sinkron.

**Pra-daftar via NIP** di halaman Kelola User:

- Form `PraDaftarForm(nip)`. Alurnya: `ambil_pegawai(nip)`, lalu tampilkan pratinjau,
  lalu konfirmasi, lalu `buat_user_dari_ehrm(data)` tanpa `sso_sub`.
- Setelah dibuat, langsung diarahkan ke `edit_user` untuk menambah peran admin.
- Dengan adanya fitur ini, opsi role **Pegawai** di `TambahUserForm` dihapus. Pegawai
  hanya lewat pra-daftar atau SSO.

### 6.4 Tampilan Profil

Teks "Terakhir sinkron: {{ user.ehrm_sinkron_at|date }}" ditampilkan di bagian Data
Personal. Kalimat placeholder "akan tersinkron saat integrasi e-HRM tersedia" dihapus.

### 6.5 Management command (opsional)

`accounts/management/commands/sinkron_ehrm.py`: sinkron semua user yang memiliki
`PegawaiProfile`, dengan opsi `--nip` dan `--dry-run`. Bisa dijadwalkan lewat cron di
NAS.

### 6.6 Test

File baru `accounts/tests_ehrm.py` (stub + `unittest.mock.patch` untuk HTTP):

- `buat_user_dari_ehrm` membuat User, profil, dan `PeranUser(pegawai)`, dengan
  password *unusable*.
- `sinkron_profil` memperbarui jabatan. Email yang `email_dikunci=True` tidak berubah.
  `no_hp` e-HRM yang tidak valid diabaikan.
- Kode unit yang tidak dikenal membuat unit lama tetap dipakai.
- Tabrakan username memberi sufiks.
- `EhrmTidakTersedia` dari HTTP timeout diteruskan ke pemanggil.
- Pra-daftar via NIP menghasilkan user tanpa `sso_sub`. Sinkron ulang dan kembalikan ke
  e-HRM bekerja.

---

## 7. Fase 5 — Login SSO

**Tujuan:** AB-01 s.d. AB-06. Adaptor protokol menunggu **Q1**. Komponen
§7.1–§7.3 bisa dikerjakan sekarang.

### 7.1 Alur inti (tidak bergantung pada protokol)

File baru `accounts/sso.py`:

```python
class SsoGagal(Exception):
    """Pesan aman untuk ditampilkan ke pengguna."""

def masuk_dari_sso(request, *, sub: str, nip: str, klaim: dict) -> User:
    """
    1. User by sso_sub → ada: lanjut ke 4.
    2. User by profile__nip=nip → ada: tautkan (sso_sub=sub, sumber_akun=SSO).
    3. Tidak ada: data = ehrm.ambil_pegawai(nip); None/EhrmTidakTersedia → SsoGagal;
       user = buat_user_dari_ehrm(data, sso_sub=sub).
    4. user.is_active False → SsoGagal("Akun dinonaktifkan").
    5. Sinkron e-HRM (user lama: tangkap EhrmTidakTersedia → log, lanjut).
    6. login(request, user, backend="accounts.sso.SsoBackend"); log auth.login_sso.
    """
```

`SsoBackend` adalah backend minimal (`get_user` saja; `authenticate` mengembalikan
`None`). Fungsinya supaya `login()` dan sesi bisa mengenali user yang masuk lewat SSO.
Daftarkan:

```python
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend", "accounts.sso.SsoBackend"]
```

### 7.2 Stub pengembangan

- **View** `sso_stub`, hanya bila `settings.DEBUG and not settings.SSO_ENABLED`.
  - **GET:** form pilih NIP dari daftar stub e-HRM.
  - **POST:** `masuk_dari_sso(request, sub=f"stub-{nip}", nip=nip, klaim={})`.
- **URL:** `login/sso/` diarahkan ke stub atau adaptor nyata, tergantung konfigurasi.
- **Halaman login** [templates/registration/login.html](../../templates/registration/login.html):
  - tombol **"Masuk dengan SSO"** bila `SSO_ENABLED` atau `DEBUG`;
  - pemisah "atau";
  - form username/password tetap ada.

### 7.3 Test alur inti

File baru `accounts/tests_sso.py`, memakai stub, tanpa jaringan:

- NIP baru membuat user + login, dengan peran aktif `pegawai`.
- NIP milik user lama (seed) menautkan akun yang sama (jumlah `User` tidak bertambah),
  dan password lama tetap valid.
- Login SSO kedua mencari lewat `sso_sub`. Setelah username diganti, login tetap
  berhasil.
- User nonaktif: SSO ditolak.
- e-HRM down: user lama tetap login (log `sinkron_ehrm_gagal`), user baru gagal dengan
  pesan ramah.
- `sso_stub` mengembalikan 404 saat `DEBUG=False`.

### 7.4 Adaptor protokol (setelah Q1 terjawab)

| Protokol | Library | Yang diimplementasi |
|---|---|---|
| OIDC (mis. Keycloak) | `mozilla-django-oidc` atau `authlib` | View `sso_mulai` (redirect + `state`/`nonce`/PKCE di sesi), `sso_callback` (tukar code, validasi `id_token`, ambil `sub` dan klaim NIP `SSO_NIP_CLAIM`), lalu `masuk_dari_sso`. |
| SAML 2.0 | `djangosaml2` / `pysaml2` | ACS view: ambil NameID + atribut NIP, lalu `masuk_dari_sso`. |
| CAS | `django-cas-ng` | Callback: ambil `user` + atribut NIP, lalu `masuk_dari_sso`. |

Test adaptor: validasi `state` salah, token kedaluwarsa, dan klaim NIP hilang, semuanya
berakhir dengan `SsoGagal`. Response penyedia di-mock.

---

## 8. Fase 6 — Pembersihan

- **`User.unit_organisasi`:** hapus field (beserta migrasinya) setelah semua pemakaian
  beralih ke `PeranUser`/`unit_admin_id()`. `User.unit_kerja` juga dihapus bila sudah
  tidak dipakai.
- **Signal kompatibilitas:** hapus signal `post_save` dari Fase 3. Seed dan test sudah
  membuat `PeranUser` secara eksplisit.
- **`TambahUserForm`:** sederhanakan, hanya untuk akun lokal admin.
- **`accounts/admin.py`:** inline `PeranUser` di admin `User`.
- **Wiki:**
  - [BISNIS_PROSES_PDLN.MD](BISNIS_PROSES_PDLN.MD) §3 (peran) & §9.1 (profil);
  - [perancangan/05_CLASS_ERD.md](../perancangan/05_CLASS_ERD.md);
  - [perancangan/01_USE_CASE.md](../perancangan/01_USE_CASE.md);
  - [DEPLOY_SYNOLOGY.MD](DEPLOY_SYNOLOGY.MD) (env baru);
  - status di IMPROVEMENT_PLAN_19102026.MD.

---

## 9. Daftar Audit Pemakaian `role` & `unit_organisasi`

Hasil `grep` pada 19 Oktober 2026. Kolom **Tindakan** memakai keterangan berikut:

- **aman**: membaca `request.user.role`, jadi otomatis mengikuti peran aktif.
- **ubah**: harus diubah.

| Lokasi | Pemakaian | Tindakan |
|---|---|---|
| `pengajuan/decorators.py` `role_required` | `request.user.role` | aman |
| `accounts/views.py` `role_redirect` | `request.user.role` | aman |
| `templates/partials/_sidebar.html` | `user.role` | aman |
| `pengajuan/context_processors.py` | `user.role`, `report.pembatalan_menunggu(user)` | aman; fungsi report: lihat baris `report.py` |
| `pengajuan/breadcrumbs.py:137` | `user.role` | aman |
| `pengajuan/kegiatan.py:56` | `SUMBER_USULAN[user.role]` | aman (user = pengusul yang sedang login) |
| `pengajuan/models.py:704-708` `relevan_untuk` | `user.role` | aman bila dipanggil dengan `request.user` (cek pemanggil) |
| `pengajuan/pembatalan.py` | `user.role`, `diajukan_role=user.role` | aman (snapshot peran aktif). Tambah AB-12 pada keputusan pembatalan. |
| `pengajuan/riwayat.py:114` | `aktor_role=aktor.role` | aman (snapshot) |
| `pengajuan/bko.py:114,130,140` | `aktor.role` | aman (aktor = request.user) |
| `pengajuan/views_pegawai.py` `profil` | `user.role == "pegawai"` (jenis dokumen) | aman. Pertimbangkan: user ganda dengan peran aktif admin melihat dokumen SK Penugasan, bukan dokumen kepegawaian. Bisa diterima, atau tampilkan keduanya bila `punya_peran(pegawai)`. |
| `pengajuan/views_unor.py:27-29` | `request.user.unit_organisasi_id` | **ubah** → `unit_admin_id()` |
| `pengajuan/report.py:48-56, 129-144` | `user.unit_organisasi_id` | **ubah** → `unit_admin_id()` |
| `notifications/services.py:61-85` | `filter(role=...)` | **ubah** → `_pemegang_peran` (§5.4) |
| `notifications/services.py:609` `_url_usulan_pengusul` | `pengusul.role` (**user lain**) | **ubah** → `pengusul.punya_peran(ADMIN_BPSDM)`, atau lebih tepat: simpan `Kegiatan.diusulkan_sebagai` (snapshot peran saat mengusulkan). |
| `notifications/services.py:617` | `pengusul.get_role_display()` | **ubah** → pakai snapshot yang sama |
| `accounts/forms.py:128,228,252` | `role` user yang dibuat/diedit | **ubah** di §5.7 (berbasis `PeranUser`) |
| `accounts/admin.py:25` | `obj.role` | **ubah** → `punya_peran(PEGAWAI)` |
| `accounts/management/commands/seed_*.py` | set `role` | **ubah** → buat `PeranUser` |
| `logs/utils.py:56` | snapshot `user.role` | aman (peran aktif = yang diinginkan) |

---

## 10. Konfigurasi & Deploy

Tambahkan ke [.env.example](../../.env.example) dan `settings.py` (dibaca lewat
`os.environ`, mengikuti pola yang ada):

```
# ======================
# e-HRM (kosong = stub lokal)
# ======================
EHRM_API_URL=
EHRM_API_TOKEN=
EHRM_TIMEOUT=5

# ======================
# SSO
# ======================
SSO_ENABLED=False
SSO_PROTOCOL=oidc
SSO_ISSUER_URL=
SSO_CLIENT_ID=
SSO_CLIENT_SECRET=
SSO_NIP_CLAIM=nip
SSO_SCOPES=openid profile email
```

Langkah deploy per fase:

1. `migrate`.
2. Untuk Fase 1: lengkapi `no_hp` akun lokal lewat filter **Tanpa No. HP**.
3. Untuk Fase 3: verifikasi jumlah `PeranUser` sama dengan jumlah `User` sebelum
   membuka akses.
4. Fase 5 di produksi:
   - daftarkan *redirect URI* `https://<host>/login/sso/callback/` di penyedia SSO;
   - pastikan `DJANGO_BEHIND_HTTPS_PROXY=True` agar URL callback ber-skema https.

Dependensi baru (Fase 5, setelah Q1) ditambahkan ke `requirements.txt` dengan versi
dipatok.

## 11. Definition of Done

Setiap fase dianggap selesai bila:

- [ ] Migrasi berjalan maju & mundur di database salinan produksi.
- [ ] Test baru fase tersebut dan **seluruh** suite lama hijau (`python manage.py test`).
- [ ] Semua aksi baru tercatat di Log Sistem dan tidak memuat password.
- [ ] Tampilan dicek di desktop dan lebar ponsel, dalam mode terang & gelap, sesuai
  [PASPOR_DESIGN_GUIDE.MD](PASPOR_DESIGN_GUIDE.MD).
- [ ] Whitelist server diuji dengan POST manual (bukan hanya lewat UI).
- [ ] `.env.example` dan wiki terkait diperbarui.
- [ ] Bagian "Status" di dokumen ini diperbarui (fase selesai + catatan penyimpangan
  dari rancangan).
