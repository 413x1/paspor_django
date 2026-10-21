#!/bin/sh
# Dijalankan setiap kali container web start:
#   1. cek konfigurasi Django,
#   2. tunggu MySQL siap,
#   3. jalankan migrasi database,
#   4. seed data awal & superuser (manage.py deploy_init),
#   5. jalankan perintah utama (Gunicorn).
set -e

echo "[entrypoint] Menjalankan manage.py check ..."
python manage.py check

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

if [ "${DJANGO_MIGRATE_ON_START:-True}" = "True" ]; then
    echo "[entrypoint] Menjalankan migrate ..."
    python manage.py migrate --noinput
fi

if [ "${DJANGO_INIT_ON_START:-True}" = "True" ]; then
    echo "[entrypoint] Menjalankan deploy_init (seed & superuser) ..."
    python manage.py deploy_init
fi

exec "$@"
