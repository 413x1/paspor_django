from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import PegawaiProfile, User
from paspor.models import UnitOrganisasi

# 3 nama dummy per unit organisasi (11 unit x 3 = 33), dipetakan berurutan
# sesuai `code` org_units.
NAMA_PEGAWAI = [
    "Ahmad Fauzan", "Siti Rahmawati", "Bambang Prasetyo",
    "Dewi Kartika", "Rudi Hartono", "Nur Aisyah",
    "Agus Setiawan", "Indah Permatasari", "Hendra Gunawan",
    "Yulia Anggraini", "Eko Wibowo", "Sri Wahyuni",
    "Dedi Kurniawan", "Fitriani Lestari", "Arif Rahman",
    "Lina Marlina", "Joko Susanto", "Ratna Sari",
    "Wahyu Nugroho", "Dian Puspita", "Anton Saputra",
    "Wulan Damayanti", "Rizal Firmansyah", "Mega Lestari",
    "Fajar Ramadhan", "Putri Ayu", "Irwan Setiadi",
    "Novita Sari", "Taufik Hidayat", "Rina Susanti",
    "Yudi Alamsyah", "Maya Sartika", "Hadi Purnomo",
]

PANGKAT_GOLONGAN = [
    "Penata Muda / III-a",
    "Penata / III-c",
    "Penata Tk. I / III-d",
]


class Command(BaseCommand):
    help = (
        "Membuat 3 akun Pegawai untuk tiap unit organisasi (org_units), "
        "username pegawai.<alias(lower)><n>, password 'paspor123'."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        org_units = list(UnitOrganisasi.objects.order_by("code"))
        if not org_units:
            self.stderr.write(self.style.ERROR(
                "Tabel org_units kosong. Jalankan migrasi/seed_demo_data lebih dulu."
            ))
            return

        nama_iter = iter(NAMA_PEGAWAI)
        created_count = 0
        for unit in org_units:
            alias_lower = unit.alias.lower()
            for n in range(1, 4):
                username = f"pegawai.{alias_lower}{n}"
                nama = next(nama_iter, f"Pegawai {unit.alias} {n}")

                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "first_name": nama.split(" ")[0],
                        "last_name": " ".join(nama.split(" ")[1:]),
                        "role": User.Role.PEGAWAI,
                    },
                )
                if created:
                    user.set_password("paspor123")
                user.unit_kerja = unit.name
                user.unit_organisasi = unit
                user.save()
                if created:
                    created_count += 1

                nip = f"90{unit.code}{n}" + "0" * 13
                PegawaiProfile.objects.update_or_create(
                    user=user,
                    defaults={
                        "nip": nip,
                        "nama": nama,
                        "jabatan": "Staf Pelaksana",
                        "pangkat_golongan": PANGKAT_GOLONGAN[n - 1],
                        "unit_kerja": unit.name,
                        "unit_organisasi": unit,
                        "sisa_cuti_tahun_berjalan": 12,
                    },
                )

        self.stdout.write(self.style.SUCCESS(
            f"\nSelesai. {created_count} user pegawai baru dibuat "
            f"({len(org_units) * 3} total, password sama untuk semua: 'paspor123')."
        ))
