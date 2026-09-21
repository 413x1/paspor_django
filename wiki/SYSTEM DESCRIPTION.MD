# PASPOR — System Description

**PASPOR** (Platform Administrasi Surat Perjalanan Overseas Request) is a
Django web application built for Kementerian Pekerjaan Umum (Ministry of Public
Works, Indonesia). It digitises the administrative workflow for **Perjalanan
Luar Negeri Non-Kedinasan** (private / non-official overseas travel permits) for
ministry employees.

This document describes what the current codebase implements. It is a
faithful reproduction of an interactive mockup
(`PASPOR_Mockup_Tahap1_3_NonKedinasan.html`); the mockup's client-side state
machine has been re-implemented with server-side validation.

---

## 1. Purpose & Scope

| In scope (implemented) | Out of scope (planned) |
|---|---|
| Non-official overseas travel permit flow (Non-Kedinasan) | Official travel flow (PDLN) + `Admin BPSDM` role |
| 3 roles: Pegawai, Admin Unor, Admin Biro PAKLN | Integration with real HR/kepegawaian database |
| Manual document upload per stage | Automatic document generation (e.g. Izin Luar Negeri form) |
| CSV export | True `.xlsx` export |
| Django username/password auth | SSO / Satu Bravo integration |
| Local filesystem media storage | Object storage (S3) for production |
| — | Email / push notifications on status change |
| — | Custom 403/404/500 pages, automated tests |

---

## 2. Technology Stack

| Layer | Choice |
|---|---|
| Language / runtime | Python 3.10+ |
| Framework | Django 6.1.1 |
| Database | MySQL 8.x / MariaDB 10.6+ (`mysqlclient` 2.2.8, `utf8mb4`) |
| Templating | Django templates (server-rendered HTML) |
| Frontend | Static CSS only (`static/css/style.css`, navy/gold theme); no JS framework |
| Auth | `django.contrib.auth` with a custom user model |
| File storage | Local filesystem (`MEDIA_ROOT = <BASE_DIR>/media`) |
| Config | Environment variables, optionally loaded from `.env` by a minimal built-in loader in `settings.py` |

Dependencies (`requirements.txt`): `Django`, `mysqlclient`, `asgiref`,
`sqlparse`, `tzdata`.

---

## 3. Project Structure

```
paspor_django/
├── manage.py
├── requirements.txt
├── .env.example / .env
├── paspor_project/            # Project config
│   ├── settings.py            # env loader, MySQL, custom user model, media limits
│   ├── urls.py                # root routing + role namespaces
│   ├── wsgi.py / asgi.py
├── accounts/                  # Authentication & identity
│   ├── models.py              # User(role), PegawaiProfile
│   ├── views.py               # login, logout, role_redirect
│   ├── admin.py               # UserAdmin + PegawaiProfile inline
│   └── management/commands/seed_demo_data.py
├── pengajuan/                 # Core permit workflow
│   ├── models.py              # Pengajuan, DokumenPegawai/Unor/Pakln
│   ├── decorators.py          # role_required(*roles)
│   ├── forms.py               # PengajuanForm + 3 document upload forms
│   ├── views_pegawai.py       # Employee: beranda, formulir, upload, monitor
│   ├── views_unor.py          # Admin Unor: dashboard, preview, upload, export
│   ├── views_pakln.py         # Admin PAKLN: dashboard, preview, upload, export
│   ├── urls_pegawai.py / urls_unor.py / urls_pakln.py
│   ├── admin.py               # PengajuanAdmin with document inlines
│   └── templatetags/pengajuan_extras.py   # get_item, file_url filters
├── templates/                 # base.html + registration/ pegawai/ unor/ pakln/
├── static/css/style.css
└── media/                     # Uploaded documents (dev)
```

---

## 4. Roles

Defined on the custom `User` model (`accounts/models.py`), field `role`:

| Role value | Label | Responsibility |
|---|---|---|
| `pegawai` | Pegawai | Employee applicant. Fills the application form, uploads 4 required documents, submits, and monitors progress. |
| `admin_unor` | Admin Unor | Unit-organisation admin. Reviews the employee submission, uploads 5 administrative documents, forwards to Biro PAKLN. |
| `admin_pakln` | Admin Biro PAKLN | Bureau admin (final stage). Reviews the forwarded case, uploads 3 administrative documents, closes the case. |

A fourth role, **Admin BPSDM** (for the official-travel PDLN flow), is
referenced in comments but **not implemented**.

Helper predicates: `user.is_pegawai()`, `user.is_admin_unor()`,
`user.is_admin_pakln()`.

Access control is enforced by `@role_required(*roles)`
(`pengajuan/decorators.py`), which wraps `@login_required` and raises
`PermissionDenied` (HTTP 403) when `request.user.role` is not allowed.

---

## 5. Data Model

### 5.1 `accounts.User` (AUTH_USER_MODEL)

Extends `AbstractUser`; adds `role` (`TextChoices`: PEGAWAI / ADMIN_UNOR /
ADMIN_PAKLN).

### 5.2 `accounts.PegawaiProfile`

One-to-one with `User` (`related_name="profile"`). Simulates data that would in
production be pulled from the ministry HR system. Currently populated manually
or via `seed_demo_data`.

Fields: `nip` (unique), `nama`, `jabatan`, `pangkat_golongan`, `unit_kerja`,
`unit_organisasi`, `sisa_cuti_tahun_berjalan` (default 12).

### 5.3 `pengajuan.Pengajuan`

One overseas-travel permit application. It is the single source of truth for
workflow state.

| Group | Fields |
|---|---|
| Identity | `kode` (auto `PSP-<year>-<0001>`, generated in `save()`), `pegawai` (FK → User) |
| Travel detail (employee-entered) | `kategori`, `maksud`, `tujuan_negara`, `sumber_pembiayaan`, `tgl_berangkat`, `tgl_kembali`, `jumlah_hari_kerja` |
| Channel / state | `kanal` (`mobile` / `web`, default `web`), `status` |
| Workflow flags | `form_saved`, `submitted`, `preview_unor_agree`, `preview_pakln_agree` (all boolean) — mirror the mockup's JS state, re-checked server-side to unlock each next page |
| Return-to-employee | `catatan_unor` (text) — note Admin Unor attaches when sending an application back to the employee for correction (see §6) |
| Reporting dates | `tgl_pengajuan`, `tgl_masuk_pakln`, `tgl_selesai` |
| Audit | `created_at`, `updated_at` |

Choice sets:
- `Kategori`: Ibadah, Pendidikan, Keperluan Pribadi, Lainnya
- `SumberPembiayaan`: Biaya Sendiri, Sponsor/Penyelenggara, Negara/Lembaga Lain
- `Kanal`: mobile, web
- `Status`: `belum` → `proses` → `proses_pakln` → `selesai`

Derived properties:
- `jumlah_hari_kalender` — calendar days between departure and return (inclusive)
- `timeline` — 4-step structure (Diajukan Pegawai → Dalam Proses Unor → Dalam
  Proses Biro PAKLN → Selesai) with per-step state `done` / `current` /
  `upcoming`, consumed by the employee's Monitor page.

### 5.4 Document models

Three parallel models, one per workflow stage, each: FK → `Pengajuan`, `jenis`
(choice), `file` (`FileField`), `uploaded_at`. Each enforces
`unique_together = ("pengajuan", "jenis")` — one file per document type — and
files are stored under `media/pengajuan/<kode>/<stage>/<jenis>/<filename>`.

| Model | Stage | Document types (`jenis`) |
|---|---|---|
| `DokumenPegawai` | Employee (4) | Formulir Persetujuan Cuti; Formulir Izin Luar Negeri; Dokumen Pendukung; Nota Dinas Pimpinan Unit Kerja ke Sekretaris Unor |
| `DokumenUnor` | Admin Unor (3, wajib) | Lembar Disposisi; Formulir Izin Luar Negeri (TTD Pimpinan Unor); Nota Dinas ke Biro PAKLN |
| `DokumenPakln` | Admin Biro PAKLN (3) | Nota Dinas Kepala Bagian; Nota Dinas Kepala Biro; Izin Luar Negeri (TTD Sekjen a.n. Menteri) |

`DokumenUnorPendukung` (one-to-one with `Pengajuan`) holds the Admin Unor
"Dokumen Pendukung Lainnya": a single `file` plus three independent boolean
flags (`nd_sekunor`, `nd_menteri`, `lainnya`). Uploading/replacing the file
and toggling a flag are deliberately separate, order-independent actions on
`unor:upload_dokumen` (`"pendukung_upload"` / `"pendukung_hapus"` /
`"toggle_pendukung"` POST branches) — neither requires the other to happen
first. "Lengkap" = all 3 `DokumenUnor` wajib present **and**
`DokumenUnorPendukung.is_lengkap()` (file present and at least one flag set).

Upload size cap: 10 MB (`DATA_UPLOAD_MAX_MEMORY_SIZE`,
`FILE_UPLOAD_MAX_MEMORY_SIZE` in `settings.py`).

### 5.5 `pengajuan.DokumenTemplate`

Reference templates (PDF/DOCX only, enforced via `FileExtensionValidator`)
uploaded by Admin Biro PAKLN so Pegawai/Admin Unor upload documents in a
consistent format. Managed at **Manajemen Template** (`pakln:kelola_template`).

| Field | Purpose |
|---|---|
| `nama`, `keterangan`, `file` | Template identity + the PDF/DOCX itself |
| `untuk_pegawai`, `untuk_admin_unor` | Audience toggles (at least one required) |
| `unit_organisasi` (M2M → `paspor.UnitOrganisasi`) | Optional restriction to specific unit(s); empty = all units |
| `kategori` (`Pengajuan.Kategori`, optional) | Optional restriction to one travel category (e.g. Ibadah/Umroh); empty = all categories |
| `aktif` | Show/hide toggle |

`relevan_untuk(user, kategori=None)` centralizes the visibility rule (role
match, unit match via `user.unit_organisasi_id`, category match) and is used
by both `pegawai:upload_dokumen` and `unor:upload_dokumen` to surface a
"Template Dokumen Tersedia" box with download links, filtered to the
viewer's role/unit and the current `pengajuan.kategori`.

---

## 6. Workflow / State Machine

```
        ┌─────────┐   employee submits    ┌────────┐   Unor forwards      ┌──────────────┐   PAKLN closes   ┌─────────┐
        │  belum  │ ────────────────────► │ proses │ ──────────────────► │ proses_pakln │ ───────────────► │ selesai │
        │ (draft) │  form + 4 docs + ack  │ (Unor) │  +5 docs + preview  │   (PAKLN)    │  +3 docs + ack   │ (done)  │
        └─────────┘                       └────────┘  ack + ack          └──────────────┘                  └─────────┘
```

### Stage 1 — Pegawai (`views_pegawai.py`, namespace `pegawai`)

| Step | URL name | Behaviour |
|---|---|---|
| Beranda | `pegawai:beranda` | Shows the active application (any status ≠ `selesai`) + history. Only one active application at a time. |
| Formulir Pengajuan | `pegawai:formulir_pengajuan` | `PengajuanForm` (travel detail only; profile shown read-only). On save sets `form_saved = True`. Validates `tgl_kembali >= tgl_berangkat`. If an active application is already submitted, redirects forward. |
| Unggah Dokumen | `pegawai:upload_dokumen` (`<kode>`) | Requires `form_saved`. Upload the 4 `DokumenPegawai` types. "Kirim" requires all 4 present **and** the acknowledgement checkbox → sets `status = proses`, `submitted = True`, `tgl_pengajuan = today`. |
| Monitor Progres | `pegawai:monitor_progres` (`<kode>`) | Requires `submitted`. Renders the `timeline` property. |

### Stage 2 — Admin Unor (`views_unor.py`, namespace `unor`)

| Step | URL name | Behaviour |
|---|---|---|
| Dasbor | `unor:dashboard` | All applications with `status ≠ belum` + counts (total / proses / proses_pakln / selesai). |
| Pratinjau | `unor:preview` (`<kode>`) | Read-only view. "Lanjutkan" sets `preview_unor_agree = True`. "Kembalikan ke Pegawai" (requires a note) resets `status = belum`, `submitted = False`, `preview_unor_agree = False`, and stores the note in `catatan_unor` — the application drops out of both dashboards and reappears as the employee's active (draft-status) application with the note shown on Beranda/Formulir/Upload; `catatan_unor` is cleared when the employee resubmits. |
| Unggah Dokumen | `unor:upload_dokumen` (`<kode>`) | Requires `preview_unor_agree`. Upload the 3 wajib `DokumenUnor` documents individually, plus the independent `DokumenUnorPendukung` upload/checklist (§5.4). "Teruskan" requires all 3 wajib + `DokumenUnorPendukung.is_lengkap()` + acknowledgement → sets `status = proses_pakln`, `tgl_masuk_pakln = today`. |
| Export Database | `unor:export` | HTML table; `?format=csv` streams `paspor_pengajuan_unor.csv`. |

### Stage 3 — Admin Biro PAKLN (`views_pakln.py`, namespace `pakln`)

| Step | URL name | Behaviour |
|---|---|---|
| Dasbor | `pakln:dashboard` | Only applications with `status in {proses_pakln, selesai}` + counts. |
| Pratinjau | `pakln:preview` (`<kode>`) | Read-only. "Lanjutkan" sets `preview_pakln_agree = True`. |
| Unggah Dokumen | `pakln:upload_dokumen` (`<kode>`) | Requires `preview_pakln_agree`. Upload the 3 `DokumenPakln` types. "Selesaikan" requires all 3 + acknowledgement → sets `status = selesai`, `tgl_selesai = today`. |
| Export Database | `pakln:export` | HTML table; `?format=csv` streams `paspor_pengajuan_pakln.csv`. |

Every "unlock" precondition (`form_saved`, `submitted`, `preview_unor_agree`,
`preview_pakln_agree`, document completeness, acknowledgement checkbox) is
re-validated in the view; failing it redirects back or shows an error message.

---

## 7. Routing

Root URLconf: `paspor_project/urls.py`

| Path | Target |
|---|---|
| `/admin/` | Django admin |
| `/` | `accounts.views.role_redirect` (name `home`) — redirects to the role's landing page |
| `/login/` | `accounts.views.login_view` (custom template, single login for all roles) |
| `/logout/` | `accounts.views.logout_view` |
| `/pegawai/…` | `pengajuan.urls_pegawai` (namespace `pegawai`) |
| `/admin-unor/…` | `pengajuan.urls_unor` (namespace `unor`) |
| `/admin-biropakln/…` | `pengajuan.urls_pakln` (namespace `pakln`) |
| `/media/…` | Served by Django only when `DEBUG = True` |

`LOGIN_URL = "login"`, `LOGIN_REDIRECT_URL = "home"`,
`LOGOUT_REDIRECT_URL = "login"`.

---

## 8. Templates & Frontend

- `templates/base.html` — top bar (brand, role pill, user name, logout),
  Django messages, `{% block content %}`.
- `registration/login.html` — login form.
- `pegawai/` — `beranda`, `formulir`, `upload`, `monitor`.
- `unor/` and `pakln/` — `dashboard`, `preview`, `upload`, `export`.
- `static/css/style.css` — single stylesheet, navy/gold theme mirroring the
  mockup. No JavaScript framework; forms are plain server-rendered HTML.
- Custom template filters (`pengajuan/templatetags/pengajuan_extras.py`):
  - `get_item(mapping, key)` — dict lookup by document `jenis` in templates.
  - `file_url(document)` — safe `document.file.url` or `None`.

---

## 9. Configuration

Read from environment variables (with a minimal `.env` loader in `settings.py`
that does not override already-set variables):

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | `django-insecure-CHANGE-ME-IN-PRODUCTION` | Django secret |
| `DJANGO_DEBUG` | `True` | Debug mode (string `"True"` toggle) |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |
| `DB_NAME` | `paspor_db` | MySQL database |
| `DB_USER` | `paspor_user` | MySQL user |
| `DB_PASSWORD` | `paspor_password` | MySQL password |
| `DB_HOST` | `127.0.0.1` | MySQL host |
| `DB_PORT` | `3306` | MySQL port |

Locale: `LANGUAGE_CODE = "id-id"`, `TIME_ZONE = "Asia/Jakarta"`, `USE_TZ = True`.

---

## 10. Setup & Run

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# MySQL: create database `paspor_db` (utf8mb4) and a user with full privileges

cp .env.example .env              # then edit credentials
python manage.py check
python manage.py makemigrations accounts pengajuan
python manage.py migrate
python manage.py createsuperuser  # optional, for /admin/
python manage.py seed_demo_data   # demo accounts + sample applications
python manage.py seed_pegawai_org_units  # optional: 3 Pegawai accounts per org unit
python manage.py seed_admin_unor_org_units  # optional: 1 Admin Unor account per org unit
python manage.py runserver
```

### Demo accounts (`seed_demo_data`)

| Username | Password | Role |
|---|---|---|
| `andra.wibisono` | `paspor123` | Pegawai |
| `admin.unor` | `paspor123` | Admin Unor |
| `admin.pakln` | `paspor123` | Admin Biro PAKLN |

`seed_demo_data` also creates a `PegawaiProfile` for the employee and two
sample `selesai` applications (`PSP-2026-0091`, `PSP-2026-0114`).

`seed_pegawai_org_units` creates 3 Pegawai accounts per `org_units` row
(username `pegawai.<alias(lower)><1|2|3>`, password `paspor123`), each with
a matching `PegawaiProfile`. Idempotent — safe to re-run.

`seed_admin_unor_org_units` creates 1 Admin Unor account per `org_units` row
(username `admin.unor.<alias(lower)>`, password `paspor123`), scoped to that
unit via `unit_organisasi`. Idempotent — safe to re-run.

### End-to-end test path

1. Login as `andra.wibisono` → Beranda → new application → fill form → save.
2. Upload the 4 documents → check acknowledgement → send to Admin Unor.
3. Login as `admin.unor` → Dashboard → preview + agree → upload 5 documents →
   forward to Biro PAKLN.
4. Login as `admin.pakln` → preview + agree → upload 3 documents → finish.
5. Back as `andra.wibisono` → Monitor Progres → status **Selesai**.

---

## 11. Django Admin

- `UserAdmin`: adds the `role` fieldset, `role`-based list filter, and a
  `PegawaiProfile` inline shown only for `pegawai` users.
- `PegawaiProfileAdmin`: list + search by `nama` / `nip`.
- `PengajuanAdmin`: list (kode, pegawai, kategori, tujuan, kanal, status, date),
  filters (status / kanal / kategori), search (kode, username, profile nama /
  nip), read-only `kode`/`created_at`/`updated_at`, and inlines for all three
  document models.

---

## 12. Known Limitations

- Official-travel (PDLN) flow and the `Admin BPSDM` role are not implemented.
- `PegawaiProfile` is entered manually — no HR-system integration.
- Authentication is local username/password — no SSO / Satu Bravo.
- No notifications (email/push) on status transitions.
- All documents are uploaded manually; none are generated from application data.
- "Export" produces CSV, not real `.xlsx`.
- `MEDIA_ROOT` is local disk — production needs an external storage backend.
- No custom 403/404/500 pages; no automated test suite.
- Per the README, the code was authored offline against the mockup spec and
  should be verified with `python manage.py check` before first use.

### Production checklist (from README)

Set `DJANGO_DEBUG=False` and real `DJANGO_ALLOWED_HOSTS`; replace
`DJANGO_SECRET_KEY`; run `collectstatic` and serve static via Nginx/WhiteNoise;
use Gunicorn/uWSGI behind Nginx; enable HTTPS
(`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`);
move media to external object storage.
