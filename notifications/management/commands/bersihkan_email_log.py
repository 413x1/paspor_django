from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notifications.models import EmailLog


class Command(BaseCommand):
    help = (
        "Hapus PERMANEN riwayat email lama (retensi). Secara bawaan hanya status "
        "terkirim dan dilewati; email gagal dipertahankan kecuali --termasuk-gagal."
    )

    def add_arguments(self, parser):
        parser.add_argument("--hari", type=int, required=True, help="Hapus email yang lebih lama dari N hari.")
        parser.add_argument("--termasuk-gagal", action="store_true", help="Ikut menghapus email berstatus gagal.")
        parser.add_argument("--dry-run", action="store_true", help="Hanya hitung, tanpa menghapus.")

    def handle(self, *args, hari, termasuk_gagal=False, dry_run=False, **options):
        if hari < 1:
            raise CommandError("--hari harus bernilai 1 atau lebih.")
        status = [EmailLog.Status.SENT, EmailLog.Status.SKIPPED]
        if termasuk_gagal:
            status.append(EmailLog.Status.FAILED)
        qs = EmailLog.objects.filter(status__in=status, created_at__lt=timezone.now() - timedelta(days=hari))
        if dry_run:
            self.stdout.write(f"[dry-run] Akan dihapus: {qs.count()} baris.")
            return
        dihapus, _ = qs.delete()
        self.stdout.write(f"Dihapus: {dihapus} baris email lebih lama dari {hari} hari.")
