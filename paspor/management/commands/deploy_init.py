"""Inisialisasi data otomatis saat container start.

Dipanggil oleh ``docker/entrypoint.sh`` setelah ``migrate``. Semua langkah
dikendalikan lewat environment variable (lihat ``.env.example``):

- Seed data awal (``seed_demo_data`` + opsional seed akun per unit) hanya
  dijalankan pada **database baru** (belum ada user sama sekali), supaya
  akun demo yang sudah dihapus/diubah admin tidak dibuat ulang setiap
  restart. Paksa ulang dengan ``DJANGO_SEED_FORCE=True``.
- ``seed_hari_libur`` dijalankan setiap start (idempoten; CSV tahun baru
  di ``scripts/data/`` otomatis ikut termuat).
- Superuser dibuat dari ``DJANGO_SUPERUSER_*`` bila username tersebut
  belum ada. Password user yang sudah ada tidak pernah ditimpa.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand


def _flag(name, default="False"):
    return os.environ.get(name, default).strip().lower() in ("true", "1", "yes")


class Command(BaseCommand):
    help = "Seed data awal & superuser untuk deploy (dipanggil entrypoint Docker)."

    def handle(self, *args, **options):
        User = get_user_model()
        database_baru = not User.objects.exists()

        if database_baru or _flag("DJANGO_SEED_FORCE"):
            self.stdout.write("[deploy_init] Menjalankan seed_demo_data ...")
            call_command("seed_demo_data")

            if _flag("DJANGO_SEED_PEGAWAI_ORG_UNITS"):
                self.stdout.write("[deploy_init] Menjalankan seed_pegawai_org_units ...")
                call_command("seed_pegawai_org_units")

            if _flag("DJANGO_SEED_ADMIN_UNOR_ORG_UNITS"):
                self.stdout.write("[deploy_init] Menjalankan seed_admin_unor_org_units ...")
                call_command("seed_admin_unor_org_units")
        else:
            self.stdout.write("[deploy_init] Database sudah berisi user, seed data awal dilewati.")

        if _flag("DJANGO_SEED_HARI_LIBUR", "True"):
            self.stdout.write("[deploy_init] Menjalankan seed_hari_libur ...")
            call_command("seed_hari_libur")

        self._buat_superuser(User)

    def _buat_superuser(self, User):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not username or not password:
            self.stdout.write("[deploy_init] DJANGO_SUPERUSER_* kosong, superuser tidak dibuat.")
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"[deploy_init] Superuser '{username}' sudah ada, dilewati.")
            return

        User.objects.create_superuser(
            username=username,
            email=os.environ.get("DJANGO_SUPERUSER_EMAIL", ""),
            password=password,
            role=User.Role.ADMIN_PAKLN,
        )
        self.stdout.write(self.style.SUCCESS(f"[deploy_init] Superuser '{username}' dibuat."))
