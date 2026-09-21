from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from paspor.models import UnitOrganisasi

# 1 nama dummy per unit organisasi (11 unit), dipetakan berurutan sesuai
# `code` org_units.
NAMA_ADMIN_UNOR = [
    "Rahmat Hidayat", "Kartini Suryani", "Bagus Wicaksono",
    "Retno Wulandari", "Bayu Aditya", "Sari Kusuma",
    "Herman Santoso", "Dewi Anjani", "Fajar Nugraha",
    "Ika Rahayu", "Gunawan Saputra",
]


class Command(BaseCommand):
    help = (
        "Membuat 1 akun Admin Unor untuk tiap unit organisasi (org_units), "
        "username admin.unor.<alias(lower)>, password 'paspor123'."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        org_units = list(UnitOrganisasi.objects.order_by("code"))
        if not org_units:
            self.stderr.write(self.style.ERROR(
                "Tabel org_units kosong. Jalankan migrasi/seed_demo_data lebih dulu."
            ))
            return

        nama_iter = iter(NAMA_ADMIN_UNOR)
        created_count = 0
        for unit in org_units:
            alias_lower = unit.alias.lower()
            username = f"admin.unor.{alias_lower}"
            nama = next(nama_iter, f"Admin Unor {unit.alias}")

            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": nama.split(" ")[0],
                    "last_name": " ".join(nama.split(" ")[1:]),
                    "role": User.Role.ADMIN_UNOR,
                },
            )
            if created:
                user.set_password("paspor123")
                created_count += 1
            user.role = User.Role.ADMIN_UNOR
            user.unit_kerja = unit.name
            user.unit_organisasi = unit
            user.save()

        self.stdout.write(self.style.SUCCESS(
            f"\nSelesai. {created_count} user Admin Unor baru dibuat "
            f"({len(org_units)} total, password sama untuk semua: 'paspor123')."
        ))
