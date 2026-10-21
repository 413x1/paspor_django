from django.core.management.base import BaseCommand

from pengajuan.models import Pengajuan


class Command(BaseCommand):
    help = (
        "Hitung ulang Jumlah Hari Kerja pengajuan DRAFT (status belum) dari "
        "kalender libur saat ini. Pengajuan yang sudah dikirim tidak disentuh "
        "karena angkanya snapshot."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Tampilkan perubahan tanpa menyimpan.")

    def handle(self, *args, **options):
        berubah = 0
        drafts = Pengajuan.objects.filter(
            status=Pengajuan.Status.BELUM, tgl_berangkat__isnull=False, tgl_kembali__isnull=False,
        )
        for pengajuan in drafts:
            lama = pengajuan.jumlah_hari_kerja
            baru = pengajuan.hitung_ulang_hari()
            if lama == baru:
                continue
            berubah += 1
            self.stdout.write(f"{pengajuan.kode}: {lama} -> {baru}")
            if not options["dry_run"]:
                pengajuan.save(update_fields=["jumlah_hari_kerja", "updated_at"])

        aksi = "akan diubah" if options["dry_run"] else "diperbarui"
        self.stdout.write(self.style.SUCCESS(f"{berubah} pengajuan draft {aksi}."))
