from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import escape, format_html
from django.views.decorators.http import require_POST

from logs.models import ActivityLog
from logs.utils import record_activity
from pengajuan.decorators import role_required

from . import email_queue
from .models import EmailLog

MAKS_BARIS = 100  # batas baris per permintaan DataTables

# Kolom DataTables -> field urut (hanya whitelist ini yang boleh diurutkan).
_ORDER_FIELDS = {"0": "created_at", "1": "to_email", "3": "status", "5": "sent_at"}

_TAG_STATUS = {
    EmailLog.Status.PENDING: "is-proses",
    EmailLog.Status.SENDING: "is-proses_pakln",
    EmailLog.Status.SENT: "is-selesai",
    EmailLog.Status.FAILED: "is-dibatalkan",
    EmailLog.Status.SKIPPED: "is-belum",
}


def _ringkasan():
    jumlah = dict(EmailLog.objects.values_list("status").annotate(n=Count("id")))
    return [(kode, label, jumlah.get(kode, 0)) for kode, label in EmailLog.Status.choices]


@role_required("admin_pakln")
def monitor_email(request):
    """Halaman Monitor Email (tabel diisi lewat `monitor_email_data`)."""
    return render(request, "pakln/monitor_email.html", {
        "status_choices": EmailLog.Status.choices,
        "ringkasan": _ringkasan(),
        "total": EmailLog.objects.count(),
    })


def _tanggal(nilai):
    try:
        return date.fromisoformat(nilai) if nilai else None
    except ValueError:
        return None


def _filter(request, qs):
    GET = request.GET
    zona = timezone.get_current_timezone()
    dari, sampai = _tanggal(GET.get("tgl_dari")), _tanggal(GET.get("tgl_sampai"))
    if dari:
        qs = qs.filter(created_at__gte=datetime.combine(dari, time.min, tzinfo=zona))
    if sampai:  # inklusif: sampai akhir hari tsb
        qs = qs.filter(created_at__lt=datetime.combine(sampai + timedelta(days=1), time.min, tzinfo=zona))
    if GET.get("status") in EmailLog.Status.values:
        qs = qs.filter(status=GET["status"])
    return qs


def _baris(log):
    penerima = format_html(
        "<strong>{}</strong><br><span class=\"cell-muted\">{}</span>",
        log.to_name or "—", log.to_email or "belum punya email",
    )
    subjek = format_html("{}<br><span class=\"cell-muted\">{}</span>", log.subject, log.event or "—")
    status = format_html(
        '<span class="tag paspor-status {}"><span class="dot"></span>{}</span>',
        _TAG_STATUS.get(log.status, ""), log.get_status_display(),
    )
    if log.status == EmailLog.Status.PENDING and log.attempts:
        status = format_html(
            "{}<br><span class=\"cell-muted\">coba lagi {}</span>",
            status, timezone.localtime(log.next_attempt_at).strftime("%d %b %H:%M:%S"),
        )
    keterangan = log.last_error or log.status_note
    if email_queue.bisa_kirim_ulang(log):
        aksi = format_html(
            '<button type="button" class="button is-small is-warning" data-kirim-ulang="{}">↻ Kirim Ulang</button>', log.pk,
        )
    else:
        aksi = "—"
    return [
        timezone.localtime(log.created_at).strftime("%d %b %Y %H:%M:%S"),
        penerima,
        subjek,
        status,
        f"{log.attempts} / {log.max_attempts}",
        timezone.localtime(log.sent_at).strftime("%d %b %Y %H:%M:%S") if log.sent_at else "—",
        format_html('<span title="{}">{}</span>', keterangan, keterangan[:80] or "—"),
        aksi,
    ]


@role_required("admin_pakln")
def monitor_email_data(request):
    """Endpoint JSON server-side DataTables untuk tabel Monitor Email."""
    semua = EmailLog.objects.select_related("recipient")
    records_total = semua.count()

    qs = _filter(request, semua)
    cari = request.GET.get("search[value]", "").strip()
    if cari:
        qs = qs.filter(Q(to_email__icontains=cari) | Q(to_name__icontains=cari) | Q(subject__icontains=cari))
    records_filtered = qs.count()

    urut = _ORDER_FIELDS.get(request.GET.get("order[0][column]"), "created_at")
    if request.GET.get("order[0][dir]", "desc") == "desc":
        urut = f"-{urut}"
    qs = qs.order_by(urut, "-pk")

    try:
        start = max(int(request.GET.get("start", 0)), 0)
        length = int(request.GET.get("length", 10))
    except ValueError:
        start, length = 0, 10
    length = MAKS_BARIS if length < 1 else min(length, MAKS_BARIS)

    return JsonResponse({
        "draw": int(request.GET.get("draw", 1) or 1),
        "recordsTotal": records_total,
        "recordsFiltered": records_filtered,
        "data": [_baris(log) for log in qs[start:start + length]],
        "ringkasan": {kode: n for kode, _label, n in _ringkasan()},
    })


@role_required("admin_pakln")
@require_POST
def monitor_email_kirim_ulang(request, pk):
    """Kembalikan satu email gagal/dilewati ke antrean (tombol "Kirim Ulang")."""
    log = get_object_or_404(EmailLog.objects.select_related("recipient"), pk=pk)
    berhasil = email_queue.kirim_ulang(log)
    record_activity(
        request, ActivityLog.Aktivitas.KIRIM_ULANG_EMAIL, f"Kirim ulang email: {log.subject}",
        status=ActivityLog.Status.BERHASIL if berhasil else ActivityLog.Status.GAGAL,
        target_type="email", target_id=str(pk),
        detail="" if berhasil else f"Tidak dapat dikirim ulang (status {log.status})",
    )
    if not berhasil:
        return JsonResponse({"ok": False, "error": "Email ini tidak dapat dikirim ulang."}, status=400)
    return JsonResponse({"ok": True})
