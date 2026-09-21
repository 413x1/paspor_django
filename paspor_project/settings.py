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
    "fileupload",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Batas ukuran unggahan dokumen (10 MB), selaras dengan aturan pada mockup.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# MinIO (object storage) — dipakai oleh app `fileupload`, lihat
# wiki/UPLOAD_FILE.MD untuk penjelasan mekanismenya.
# ---------------------------------------------------------------------------
MINIO_ENDPOINT = env("MINIO_ENDPOINT", "localhost")
MINIO_PORT = int(env("MINIO_PORT", "9000"))
MINIO_USE_SSL = env("MINIO_USE_SSL", "false").lower() == "true"
MINIO_ACCESS_KEY = env("MINIO_ACCESS_KEY", env("MINIO_ROOT_USER", "minioadmin"))
MINIO_SECRET_KEY = env("MINIO_SECRET_KEY", env("MINIO_ROOT_PASSWORD", "minioadmin"))
MINIO_BUCKET_NAME = env("MINIO_BUCKET_NAME", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
