import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import User
from logs.models import ActivityLog
from logs.utils import record_activity


class Command(BaseCommand):
    help = (
        "Hapus PERMANEN log aktivitas (tabel ActivityLog). Wajib salah satu dari "
        "--hari atau --semua. Lihat wiki/instructions/SYSTEM_LOGGING.MD."
    )

    def add_arguments(self, parser):
        parser.add_argument("--hari", type=int, help="Hapus log yang lebih lama dari N hari.")
        parser.add_argument("--semua", action="store_true", help="Hapus seluruh log.")
        parser.add_argument("--dry-run", action="store_true", help="Hanya hitung, tanpa menghapus.")
        parser.add_argument("--batch-size", type=int, default=5000, help="Jumlah baris per batch hapus.")
        parser.add_argument("--oleh", default="sistem", help="Username pelaku, dicatat pada entri audit.")

    def handle(self, *args, hari=None, semua=False, dry_run=False, batch_size=5000, oleh="sistem", **options):
        if semua == (hari is not None):
            raise CommandError("Pilih tepat salah satu: --hari N atau --semua.")
        if hari is not None and hari < 1:
            raise CommandError("--hari harus bernilai 1 atau lebih.")
        if batch_size < 1:
            raise CommandError("--batch-size harus bernilai 1 atau lebih.")

        qs = ActivityLog.objects.all()
        kriteria = "semua log"
        if hari is not None:
            qs = qs.filter(timestamp__lt=timezone.now() - timedelta(days=hari))
            kriteria = f"log lebih lama dari {hari} hari"

        if dry_run:
            self.stdout.write(f"[dry-run] Akan dihapus: {qs.count()} baris ({kriteria}).")
            return

        mulai = time.monotonic()
        dihapus = 0
        while True:
            # Hapus per batch (berdasarkan PK) agar tabel besar tidak terkunci lama.
            pks = list(qs.order_by("pk").values_list("pk", flat=True)[:batch_size])
            if not pks:
                break
            ActivityLog.objects.filter(pk__in=pks).delete()
            dihapus += len(pks)

        # Entri audit reset dibuat SETELAH penghapusan, sehingga tidak ikut terhapus.
        record_activity(
            None, ActivityLog.Aktivitas.RESET_LOG, f"Reset Log: {kriteria} ({dihapus} baris dihapus)",
            username=oleh, user=User.objects.filter(username=oleh).first(), detail=f"oleh={oleh}",
        )
        # Format baris ini dibaca view reset (regex "Dihapus: N") — jangan diubah sembarangan.
        self.stdout.write(f"Dihapus: {dihapus} baris ({kriteria}) dalam {time.monotonic() - mulai:.2f} detik.")
