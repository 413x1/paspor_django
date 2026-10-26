"""Task Celery untuk notifikasi (lihat wiki/instructions/CELERY_IMPLEMENTATION_PLAN.MD, A1).

Email tetap dicatat di tabel `EmailLog` (pola outbox, Monitor Email tidak berubah). Yang berpindah
ke Celery hanya PENGIRIMNYA: menggantikan worker loop `kirim_email_antrean`.
"""

import time

from celery import shared_task
from django.conf import settings

from . import email_queue

MAKS_PUTARAN = 5     # putaran per eksekusi task (tiap putaran = satu batch EmailLog)
BATAS_DETIK = 200    # berhenti mengambil batch baru setelah ini (batas lunak task = 270 detik)


@shared_task(bind=True, name="notifications.kirim_antrean_email", queue="email", ignore_result=True)
def kirim_antrean_email(self):
    """Kirim email berstatus `pending` yang sudah waktunya.

    Aman dijalankan berulang dan oleh beberapa worker sekaligus: `email_queue.proses_antrean`
    mengunci baris (LOCK_TTL), menerapkan jeda antar email (pacing SMTP), retry dengan backoff,
    dan menghormati saklar `MAIL_ALLOW_SEND` serta `MAIL_DEV_REDIRECT_TO`.
    Dipicu (1) setelah email diantre (`email_queue.picu_pengiriman`) dan
    (2) oleh Celery Beat tiap 60 detik sebagai jaring pengaman.
    """
    if not settings.MAIL_USE_CELERY:
        return {"dilewati": "MAIL_USE_CELERY=false"}

    worker_id = f"celery@{getattr(self.request, 'hostname', None) or 'lokal'}"
    total = {"diambil": 0, "terkirim": 0, "ditunda": 0, "gagal": 0}
    mulai = time.monotonic()
    for _ in range(MAKS_PUTARAN):
        hasil = email_queue.proses_antrean(worker_id=worker_id)
        for kunci in total:
            total[kunci] += hasil[kunci]
        if hasil["diambil"] == 0 or time.monotonic() - mulai > BATAS_DETIK:
            break
    return total
