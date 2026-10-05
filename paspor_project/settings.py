"""
Django settings for the PASPOR project (Kementerian Pekerjaan Umum).

Alur yang diimplementasikan pada tahap ini: Perjalanan Luar Negeri
Non-Kedinasan, dengan 3 role: Pegawai, Admin Unor, Admin Biro PAKLN.
Alur Perjalanan Dinas Luar Negeri (PDLN) dengan role tambahan Admin BPSDM
akan menyusul pada tahap pengembangan berikutnya.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Muat pasangan KEY=VALUE dari file `.env` ke ``os.environ`` tanpa
    menimpa variabel yang sudah di-set di lingkungan. Sengaja dibuat minimal
    agar proyek tidak butuh dependency tambahan (python-dotenv, dkk.)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw_lines = fh.readlines()
    except OSError:
        return
    for raw in raw_lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-CHANGE-ME-IN-PRODUCTION")

DEBUG = env("DJANGO_DEBUG", "True") == "True"

ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

# Origin lengkap (dengan skema & port) yang boleh mengirim form POST,
# mis. "http://10.101.21.55:8000,https://paspor.domainanda.go.id".
# Wajib diisi bila aplikasi diakses lewat reverse proxy / domain HTTPS.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

# Aktifkan hanya bila aplikasi berada di belakang reverse proxy HTTPS
# (mis. Reverse Proxy DSM) yang mengirim header X-Forwarded-Proto.
if env("DJANGO_BEHIND_HTTPS_PROXY", "False") == "True":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # Aplikasi PASPOR
    "paspor",
    "accounts",
    "pengajuan",
    "notifications",
    "fileupload",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Sajikan file static (CSS/JS/gambar) langsung dari Gunicorn saat DEBUG=False.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Izinkan halaman & berkas media dibingkai (iframe) oleh aplikasi PASPOR
# sendiri — dipakai untuk pratinjau dokumen di dalam modal.
X_FRAME_OPTIONS = "SAMEORIGIN"

ROOT_URLCONF = "paspor_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "notifications.context_processors.notifications",
                "pengajuan.context_processors.badge_sidebar",
            ],
        },
    },
]

WSGI_APPLICATION = "paspor_project.wsgi.application"


# ---------------------------------------------------------------------------
# Database (MySQL)
# ---------------------------------------------------------------------------
# Butuh driver `mysqlclient` (lihat requirements.txt). Konfigurasi dapat
# ditimpa melalui environment variable, contoh nilai ada di file .env.example.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", "paspor_db"),
        "USER": env("DB_USER", "paspor_user"),
        "PASSWORD": env("DB_PASSWORD", "paspor_password"),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    }
}


# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "id-id"
TIME_ZONE = "Asia/Jakarta"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static & media files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media tidak lagi disimpan di disk lokal — semua FileField & unggahan
# memakai bucket S3 (lihat STORAGES di bawah). MEDIA_ROOT hanya dipakai
# sebagai sumber oleh command `sync_media_to_s3` untuk memindahkan berkas
# lama ke bucket.
MEDIA_ROOT = BASE_DIR / "media"

# Batas ukuran unggahan dokumen (10 MB), selaras dengan aturan pada mockup.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Object storage (S3-compatible: Garage di Synology NAS)
# ---------------------------------------------------------------------------
# Seluruh berkas unggahan (FileField pada app `pengajuan` maupun app
# `fileupload`) disimpan lewat django-storages ke bucket S3. Penjelasan
# lengkap ada di wiki/instructions/S3BUCKET_FILE_UPLOAD.MD.
from botocore.config import Config as BotoConfig  # noqa: E402

S3_ENDPOINT = env("S3_ENDPOINT", "http://127.0.0.1:3900")
S3_BUCKET_NAME = env("S3_BUCKET_NAME", "paspor-uploads")
S3_REGION_NAME = env("S3_REGION_NAME", "garage")
S3_QUERYSTRING_EXPIRE = int(env("S3_QUERYSTRING_EXPIRE", "3600"))

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": S3_ENDPOINT,
            "access_key": os.environ["S3_ACCESS_KEY"],   # Key ID (wajib)
            "secret_key": os.environ["S3_SECRET_KEY"],   # Secret key (wajib)
            "bucket_name": S3_BUCKET_NAME,
            "region_name": S3_REGION_NAME,
            # `addressing_style` & `signature_version` diabaikan django-storages
            # bila `client_config` diisi, jadi keduanya diset di sini. Timeout
            # mencegah request menggantung bila NAS tidak bisa dijangkau.
            "client_config": BotoConfig(
                s3={"addressing_style": "path"},
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
            "default_acl": None,
            "file_overwrite": False,
            "querystring_auth": True,                     # presigned download links
            "querystring_expire": S3_QUERYSTRING_EXPIRE,  # default 1 jam
        },
    },
    # WhiteNoise: file static dikompresi (gzip/brotli) saat collectstatic.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Integrasi Aplikasi PINTAR (pencalonan beasiswa, PDLN Tipe 2) — kosong = pakai
# data stub lokal (paspor/integrasi/pintar.py). Lihat BISNIS_PROSES_PDLN.MD §12.
PINTAR_API_URL = env("PINTAR_API_URL", "")
PINTAR_API_TOKEN = env("PINTAR_API_TOKEN", "")
PINTAR_API_TIMEOUT = int(env("PINTAR_API_TIMEOUT", "5"))
