"""
Antrean email berbasis database (model `EmailLog`).

Lihat wiki/instructions/EMAIL_NOTIF_IMPLEMENTATION_PLAN.MD.

- `enqueue(notifs)`  : dipanggil dari `notifications.services._create` — membuat baris
                       EmailLog (cepat, tanpa SMTP) untuk notifikasi in-app yang baru.
- `proses_antrean()` : satu putaran worker — ambil & kunci, kirim, tulis hasil.
- `kirim_ulang(log)` : mengembalikan email gagal ke antrean (tombol "Kirim Ulang").

Logika ada di fungsi biasa (bukan di command) agar kelak Celery cukup memanggil
fungsi yang sama; modelnya tidak berubah.
"""

import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import F, Q
from django.template.loader import render_to_string, select_template
from django.utils import timezone

from .models import EmailLog, Notification

logger = logging.getLogger("notifications.email")

Event = Notification.Event

# Daftar putih: event yang diemailkan dan peran penerima yang menerimanya.
# Event di luar daftar ini TIDAK mengirim email (hanya notifikasi in-app).
EMAIL_EVENTS = {
    Event.SUBMIT_UNOR: {"admin_unor"},
    Event.RESUBMIT_UNOR: {"admin_unor"},
    Event.APPROVE_UNOR: {"pegawai", "admin_pakln"},
    Event.REJECT_UNOR: {"pegawai"},
    Event.REJECT_PKLN_UNOR: {"pegawai"},
    Event.COMPLETE_PKLN: {"pegawai"},
    Event.PEMBATALAN_DITOLAK: {"pegawai"},
    Event.PEMBATALAN_DISETUJUI: {"pegawai"},
}

_MAKS_BACKOFF = 3600  # detik


def _cfg():
    return settings.MAIL_QUEUE


# ---------------------------------------------------------------------------
# Antre (dipanggil dari _create)
# ---------------------------------------------------------------------------

def _url_absolut(path):
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{settings.SITE_BASE_URL}{path}"


def _template_event(event, ext):
    """Template khusus event bila ada, selain itu template umum."""
    slug = str(event).split("_", 2)[-1].lower() if event else "default"
    return select_template([f"email/event/{slug}.{ext}", f"email/event/default.{ext}"])


def _konteks(notif, nama):
    from . import services  # impor lazy: services mengimpor modul ini

    pengajuan = notif.pengajuan
    ringkasan = None
    if pengajuan is not None:
        ringkasan = {
            "kode": pengajuan.kode,
            "pegawai": services._nama_pegawai(pengajuan),
            "perihal": services._perihal(pengajuan),
            "status": pengajuan.get_status_display(),
        }
    return {
        "nama": nama,
        "title": notif.title,
        "body": notif.body,
        "level": notif.level,
        "url": _url_absolut(notif.redirect_url),
        "ringkasan": ringkasan,
        "site_name": settings.MAIL_SITE_NAME,
        "site_url": settings.SITE_BASE_URL,
    }


def _baris_email(notif):
    """Rakit satu EmailLog (belum disimpan) dari satu Notification (belum disimpan)."""
    user = notif.recipient
    nama = (user.get_full_name() or user.username).strip()
    konteks = _konteks(notif, nama)

    status, catatan = EmailLog.Status.PENDING, ""
    if not (user.email or "").strip():
        status, catatan = EmailLog.Status.SKIPPED, "Penerima belum memiliki email"
    elif not settings.MAIL_ALLOW_SEND:
        status, catatan = EmailLog.Status.SKIPPED, "Pengiriman dimatikan (MAIL_ALLOW_SEND=false)"

    return EmailLog(
        recipient=user,
        to_email=(user.email or "").strip(),
        to_name=nama[:150],
        pengajuan=notif.pengajuan,
        event=notif.event,
        subject=f"[PASPOR] {notif.title}"[:255],
        body_text=_template_event(notif.event, "txt").render(konteks),
        body_html=_template_event(notif.event, "html").render(konteks),
        status=status,
        status_note=catatan,
        max_attempts=_cfg()["MAX_ATTEMPTS"],
    )


def enqueue(notifs):
    """Antre email untuk notifikasi in-app yang baru dibuat. TIDAK PERNAH melempar
    error: kegagalan mengantre email tidak boleh menggagalkan alur pengajuan."""
    try:
        baris = []
        for notif in notifs:
            peran = EMAIL_EVENTS.get(notif.event)
            if peran and notif.recipient.role in peran:
                baris.append(_baris_email(notif))
        if baris:
            EmailLog.objects.bulk_create(baris)
        return len(baris)
    except Exception:
        logger.exception("Gagal mengantre email notifikasi")
        return 0


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def _klaim(batch_size, worker_id):
    """Ambil dan kunci sekumpulan baris siap kirim. `SKIP LOCKED` membuat dua worker
    tidak pernah mengambil baris yang sama. Baris `sending` yang kuncinya sudah
    kedaluwarsa (worker mati) diambil ulang."""
    sekarang = timezone.now()
    batas_kunci = sekarang - timedelta(seconds=_cfg()["LOCK_TTL"])

    # Baris macet yang percobaannya sudah habis dinyatakan gagal, bukan dicoba terus.
    EmailLog.objects.filter(
        status=EmailLog.Status.SENDING, locked_at__lt=batas_kunci, attempts__gte=F("max_attempts"),
    ).update(
        status=EmailLog.Status.FAILED, locked_at=None, locked_by="",
        last_error="Worker berhenti saat mengirim dan percobaan sudah habis",
    )

    with transaction.atomic():
        ids = list(
            EmailLog.objects.select_for_update(skip_locked=True)
            .filter(
                Q(status=EmailLog.Status.PENDING, next_attempt_at__lte=sekarang)
                | Q(status=EmailLog.Status.SENDING, locked_at__lt=batas_kunci)
            )
            .order_by("next_attempt_at", "id")
            .values_list("pk", flat=True)[:batch_size]
        )
        if not ids:
            return []
        EmailLog.objects.filter(pk__in=ids).update(
            status=EmailLog.Status.SENDING, locked_at=sekarang, locked_by=worker_id,
            attempts=F("attempts") + 1,
        )
    return list(EmailLog.objects.filter(pk__in=ids).order_by("next_attempt_at", "id"))


def _kirim(log):
    """Kirim satu email lewat backend Django (SMTP). Melempar exception bila gagal."""
    tujuan, subjek = log.to_email, log.subject
    if settings.MAIL_DEV_REDIRECT_TO:  # mode uji: semua email dialihkan
        tujuan, subjek = settings.MAIL_DEV_REDIRECT_TO, f"[untuk: {log.to_email}] {log.subject}"
    pesan = EmailMultiAlternatives(subjek, log.body_text, settings.DEFAULT_FROM_EMAIL, [tujuan])
    if log.body_html:
        pesan.attach_alternative(log.body_html, "text/html")
    pesan.send(fail_silently=False)


def _tandai_berhasil(log):
    EmailLog.objects.filter(pk=log.pk).update(
        status=EmailLog.Status.SENT, sent_at=timezone.now(), locked_at=None, locked_by="",
        last_error="", updated_at=timezone.now(),
    )


def _tandai_gagal(log, exc):
    galat = f"{type(exc).__name__}: {exc}"[:1000]
    if log.attempts >= log.max_attempts:
        EmailLog.objects.filter(pk=log.pk).update(
            status=EmailLog.Status.FAILED, locked_at=None, locked_by="", last_error=galat,
            updated_at=timezone.now(),
        )
        return EmailLog.Status.FAILED
    jeda = min(_cfg()["RETRY_DELAY"] * (2 ** (log.attempts - 1)), _MAKS_BACKOFF)  # backoff eksponensial
    EmailLog.objects.filter(pk=log.pk).update(
        status=EmailLog.Status.PENDING, next_attempt_at=timezone.now() + timedelta(seconds=jeda),
        locked_at=None, locked_by="", last_error=galat, updated_at=timezone.now(),
    )
    return EmailLog.Status.PENDING


def proses_antrean(worker_id="worker", batch_size=None, pacing=None):
    """Satu putaran worker. Mengembalikan ringkasan {"diambil", "terkirim", "ditunda", "gagal"}."""
    hasil = {"diambil": 0, "terkirim": 0, "ditunda": 0, "gagal": 0}
    if not settings.MAIL_ALLOW_SEND:
        return hasil  # saklar pengaman: tidak ada pengiriman SMTP
    batch_size = batch_size or _cfg()["BATCH_SIZE"]
    pacing = _cfg()["SEND_PACING"] if pacing is None else pacing

    baris = _klaim(batch_size, worker_id)
    hasil["diambil"] = len(baris)
    for i, log in enumerate(baris):
        try:
            _kirim(log)
        except Exception as exc:  # noqa: BLE001 - semua kegagalan kirim ditangani sama
            status = _tandai_gagal(log, exc)
            hasil["gagal" if status == EmailLog.Status.FAILED else "ditunda"] += 1
            logger.warning("Email #%s gagal (percobaan %s/%s): %s", log.pk, log.attempts, log.max_attempts, exc)
        else:
            _tandai_berhasil(log)
            hasil["terkirim"] += 1
        if pacing and i < len(baris) - 1:
            time.sleep(pacing)  # jaga batas kecepatan SMTP
    return hasil


# ---------------------------------------------------------------------------
# Kirim ulang
# ---------------------------------------------------------------------------

def bisa_kirim_ulang(log):
    """`failed` selalu bisa. `skipped` hanya bila kini penerima punya email dan
    pengiriman diaktifkan (mis. email baru diisi di Manajemen User)."""
    if log.status == EmailLog.Status.FAILED:
        return True
    if log.status == EmailLog.Status.SKIPPED:
        return bool(log.recipient_id and (log.recipient.email or "").strip()) and settings.MAIL_ALLOW_SEND
    return False


def kirim_ulang(log):
    """Kembalikan email ke antrean (percobaan diulang dari nol). True bila berhasil."""
    if not bisa_kirim_ulang(log):
        return False
    pembaruan = dict(
        status=EmailLog.Status.PENDING, attempts=0, next_attempt_at=timezone.now(),
        locked_at=None, locked_by="", last_error="", status_note="",
        max_attempts=_cfg()["MAX_ATTEMPTS"],
    )
    if log.recipient_id:  # alamat bisa berubah sejak email diantre
        pembaruan["to_email"] = (log.recipient.email or "").strip()
    EmailLog.objects.filter(pk=log.pk).update(**pembaruan, updated_at=timezone.now())
    return True
