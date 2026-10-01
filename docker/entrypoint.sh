#!/bin/sh
# Dijalankan setiap kali container web start:
#   1. tunggu MySQL siap,
#   2. jalankan migrasi database,
#   3. jalankan perintah utama (Gunicorn).
set -e

if [ "${DJANGO_MIGRATE_ON_START:-True}" = "True" ]; then
    echo "[entrypoint] Menunggu database ${DB_HOST:-127.0.0.1}:${DB_PORT:-3306} ..."
    python - <<'EOF'
import sys
import time

import django

django.setup()
from django.db import connection

for attempt in range(1, 31):
    try:
        connection.ensure_connection()
        print("[entrypoint] Database siap.")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"[entrypoint] Percobaan {attempt}/30 gagal: {exc}")
        time.sleep(2)
else:
    print("[entrypoint] Database tidak bisa dijangkau, berhenti.")
    sys.exit(1)
EOF

    echo "[entrypoint] Menjalankan migrate ..."
    python manage.py migrate --noinput
fi

exec "$@"
