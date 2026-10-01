"""Salin berkas lama di MEDIA_ROOT (penyimpanan lokal sebelum migrasi ke
S3) ke bucket `default_storage` dengan key yang sama persis, supaya nilai
FileField yang sudah tersimpan di database tetap valid.

    python manage.py sync_media_to_s3 [--dry-run] [--overwrite]
"""

from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Unggah seluruh berkas di MEDIA_ROOT ke bucket S3 (key = path relatif)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Tampilkan saja, jangan unggah.")
        parser.add_argument("--overwrite", action="store_true", help="Timpa object yang sudah ada di bucket.")

    def handle(self, *args, dry_run=False, overwrite=False, **options):
        root = Path(settings.MEDIA_ROOT)
        if not root.is_dir():
            self.stdout.write(self.style.WARNING(f"MEDIA_ROOT tidak ditemukan: {root}"))
            return

        uploaded = skipped = 0
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            key = path.relative_to(root).as_posix()
            if not overwrite and default_storage.exists(key):
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(f"[dry-run] {key}")
                uploaded += 1
                continue
            if overwrite and default_storage.exists(key):
                default_storage.delete(key)
            with path.open("rb") as fh:
                saved = default_storage.save(key, File(fh))
            if saved != key:
                self.stdout.write(self.style.WARNING(f"Key berubah: {key} -> {saved}"))
            self.stdout.write(f"OK {key}")
            uploaded += 1

        self.stdout.write(self.style.SUCCESS(f"Selesai: {uploaded} diunggah, {skipped} dilewati (sudah ada)."))
