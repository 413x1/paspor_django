from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from paspor.impor_libur import ImporError, baca_csv, baca_xlsx, simpan

# Berkas seed bawaan: satu CSV per tahun (hari_libur_2026.csv, dst.).
DATA_DIR = Path(settings.BASE_DIR) / "scripts" / "data"


class Command(BaseCommand):
    help = (
        "Isi tabel HariLibur (Setting Kalender) dari CSV/Excel berkolom "
        "tanggal,keterangan,jenis sesuai SKB 3 Menteri. Tanpa --file, memuat "
        "semua scripts/data/hari_libur_<tahun>.csv. Idempoten: tanggal yang "
        "sudah ada dilewati (kecuali --timpa)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Path satu berkas .csv/.xlsx (default: semua CSV bawaan).")
        parser.add_argument("--tahun", type=int, help="Opsional — hanya impor baris pada tahun ini.")
        parser.add_argument(
            "--timpa", action="store_true",
            help="Perbarui keterangan & jenis tanggal yang sudah ada.",
        )

    def handle(self, *args, **options):
        if options["file"]:
            files = [Path(options["file"])]
        else:
            files = sorted(DATA_DIR.glob("hari_libur_*.csv"))
            if not files:
                raise CommandError(f"Tidak ada berkas hari_libur_*.csv di {DATA_DIR}.")

        baris = []
        try:
            for path in files:
                baca = baca_xlsx if path.suffix.lower() == ".xlsx" else baca_csv
                with open(path, "rb") as f:
                    baris += baca(f, path.name)
        except FileNotFoundError as e:
            raise CommandError(f"Berkas {e.filename} tidak ditemukan.")
        except ImporError as e:
            raise CommandError("\n".join(e.errors))

        if options["tahun"]:
            baris = [b for b in baris if b.tanggal.year == options["tahun"]]

        hasil = simpan(baris, timpa=options["timpa"])
        self.stdout.write(self.style.SUCCESS(
            f"{hasil['dibuat']} ditambahkan, {hasil['diperbarui']} diperbarui, "
            f"{hasil['dilewati']} dilewati — dari {', '.join(p.name for p in files)}."
        ))
