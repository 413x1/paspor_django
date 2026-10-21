"""Konfigurasi Gunicorn untuk container produksi.

Nilai bisa diatur lewat environment variable di file .env.
"""

import os

bind = "0.0.0.0:8000"

# 3 worker cukup untuk DS725+ (4 core, RAM 4 GB) dengan pengguna kantor.
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))

# Pembuatan PDF (WeasyPrint) dan unggah ke bucket bisa agak lama.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))

# Restart worker secara berkala untuk mencegah kebocoran memori.
max_requests = 1000
max_requests_jitter = 100

# Log ke stdout/stderr agar tampil di log Container Manager.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
