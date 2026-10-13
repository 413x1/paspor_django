import os
import signal
import socket
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from notifications import email_queue


class Command(BaseCommand):
    help = (
        "Worker antrean email (tabel EmailLog). Tanpa opsi: berjalan terus (loop) sampai dihentikan. "
        "Dengan --once: satu putaran lalu keluar. "
        "Lihat wiki/instructions/EMAIL_NOTIF_IMPLEMENTATION_PLAN.MD."
    )

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Satu putaran lalu keluar (cron, tes, debugging).")
        parser.add_argument("--batch-size", type=int, help="Menimpa MAIL_DB_QUEUE_WORKER_BATCH_SIZE.")
        parser.add_argument("--interval", type=float, help="Menimpa jeda antar putaran (detik).")

    def handle(self, *args, once=False, batch_size=None, interval=None, **options):
        cfg = settings.MAIL_QUEUE
        if not once and not cfg["ENABLE_WORKER"]:
            raise CommandError(
                "Mode loop dinonaktifkan: set MAIL_DB_QUEUE_ENABLE_WORKER=true di .env, atau pakai --once."
            )
        if not settings.MAIL_ALLOW_SEND:
            self.stderr.write(self.style.WARNING(
                "MAIL_ALLOW_SEND=false: tidak ada email yang dikirim via SMTP (saklar pengaman aktif)."
            ))

        worker_id = f"{socket.gethostname()}:{os.getpid()}"
        interval = cfg["INTERVAL"] if interval is None else interval

        if once:
            self._putaran(worker_id, batch_size)
            return

        berhenti = {"ya": False}

        def _stop(signum, frame):  # selesaikan email yang sedang dikirim, lalu berhenti
            berhenti["ya"] = True

        signal.signal(signal.SIGINT, _stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _stop)

        self.stdout.write(f"Worker email aktif ({worker_id}); interval {interval}s. Tekan Ctrl+C untuk berhenti.")
        while not berhenti["ya"]:
            hasil = self._putaran(worker_id, batch_size)
            if hasil["diambil"]:
                continue  # masih ada kemungkinan antrean; langsung putaran berikutnya
            # tidur dalam potongan kecil agar sinyal berhenti cepat ditanggapi
            selesai = time.monotonic() + interval
            while not berhenti["ya"] and time.monotonic() < selesai:
                time.sleep(min(0.5, max(selesai - time.monotonic(), 0)))
        self.stdout.write("Worker email berhenti.")

    def _putaran(self, worker_id, batch_size):
        hasil = email_queue.proses_antrean(worker_id=worker_id, batch_size=batch_size)
        if hasil["diambil"]:
            self.stdout.write(
                f"Diambil {hasil['diambil']}: terkirim {hasil['terkirim']}, "
                f"ditunda {hasil['ditunda']}, gagal {hasil['gagal']}."
            )
        return hasil
