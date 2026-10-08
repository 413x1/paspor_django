import re
from datetime import date, datetime, time, timedelta
from io import StringIO

from django.contrib import messages
from django.core.management import CommandError, call_command
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.html import escape, format_html
from django.views.decorators.http import require_POST

from pengajuan.decorators import role_required

from .models import ActivityLog

MAKS_BARIS = 100  # batas baris per permintaan DataTables

# Kolom DataTables -> field urut (hanya whitelist ini yang boleh diurutkan).
_ORDER_FIELDS = {"0": "timestamp", "1": "username", "4": "status"}

# Pilihan rentang pada modal Reset Log: nilai form -> argumen management command.
_RENTANG_RESET = {
    "7": {"hari": 7},
    "30": {"hari": 30},
    "semua": {"semua": True},
}


def ringkas_user_agent(ua):
    """Ringkasan "Browser · OS" dari string User-Agent (cukup untuk tampilan tabel)."""
    ua = ua or ""
    browser = next(
        (nama for pola, nama in (
            (r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"), (r"Firefox/", "Firefox"),
            (r"Chrome/|CriOS/", "Chrome"), (r"Safari/", "Safari"),
        ) if re.search(pola, ua)),
        "Lainnya",
    )
    os_ = next(
        (nama for pola, nama in (
            (r"Windows", "Windows"), (r"Android", "Android"), (r"iPhone|iPad|iOS", "iOS"),
            (r"Mac OS X|Macintosh", "macOS"), (r"Linux", "Linux"),
        ) if re.search(pola, ua)),
        "Lainnya",
    )
    return f"{browser} · {os_}" if ua else "—"


@role_required("admin_pakln")
def log_sistem(request):
    """Halaman monitoring Log Sistem (tabel diisi lewat `log_sistem_data`)."""
    return render(request, "pakln/log_sistem.html", {
        "aktivitas_choices": ActivityLog.Aktivitas.choices,
        "status_choices": ActivityLog.Status.choices,
        "total": ActivityLog.objects.count(),
    })


def _tanggal(nilai):
    try:
        return date.fromisoformat(nilai) if nilai else None
    except ValueError:
        return None


def _filter(request, qs):
    GET = request.GET
    dari, sampai = _tanggal(GET.get("tgl_dari")), _tanggal(GET.get("tgl_sampai"))
    zona = timezone.get_current_timezone()
    if dari:
        qs = qs.filter(timestamp__gte=datetime.combine(dari, time.min, tzinfo=zona))
    if sampai:  # inklusif: sampai akhir hari tsb
        qs = qs.filter(timestamp__lt=datetime.combine(sampai + timedelta(days=1), time.min, tzinfo=zona))
    if GET.get("aktivitas") in ActivityLog.Aktivitas.values:
        qs = qs.filter(aktivitas=GET["aktivitas"])
    if GET.get("status") in ActivityLog.Status.values:
        qs = qs.filter(status=GET["status"])
    pengguna = GET.get("pengguna", "").strip()
    if pengguna:
        qs = qs.filter(username__icontains=pengguna)
    return qs


def _baris(log):
    if log.status == ActivityLog.Status.BERHASIL:
        hasil = format_html('<span class="tag paspor-status is-selesai"><span class="dot"></span>{}</span>', "Berhasil")
    else:
        hasil = format_html('<span class="tag paspor-status is-dibatalkan"><span class="dot"></span>{}</span>', "Gagal")
    if log.detail:
        hasil = format_html('{}<br><span class="cell-muted">{}</span>', hasil, log.detail)
    waktu = timezone.localtime(log.timestamp).strftime("%d %b %Y %H:%M:%S")
    return [
        waktu,
        format_html('<strong>{}</strong><br><span class="cell-muted">{}</span>', log.username or "anonim", log.role or "—"),
        format_html('{}<br><span class="cell-muted">{}</span>', log.deskripsi or log.aktivitas, log.aktivitas),
        escape(log.target_id) or "—",
        hasil,
        escape(log.ip_address or "—"),
        format_html('<span title="{}">{}</span>', log.user_agent, ringkas_user_agent(log.user_agent)),
    ]


@role_required("admin_pakln")
def log_sistem_data(request):
    """Endpoint JSON server-side DataTables untuk tabel Log Sistem
    (draw/start/length/search/order + filter tambahan pada GET)."""
    semua = ActivityLog.objects.select_related("user")
    records_total = semua.count()

    qs = _filter(request, semua)
    cari = request.GET.get("search[value]", "").strip()
    if cari:
        qs = qs.filter(
            Q(username__icontains=cari) | Q(deskripsi__icontains=cari)
            | Q(target_id__icontains=cari) | Q(ip_address__icontains=cari)
        )
    records_filtered = qs.count()

    urut = _ORDER_FIELDS.get(request.GET.get("order[0][column]"), "timestamp")
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
    })


@role_required("admin_pakln")
@require_POST
def log_sistem_reset(request):
    """Tombol "Reset Log": hapus PERMANEN log lewat management command
    `bersihkan_log`. Rentang hanya boleh dari daftar tetap `_RENTANG_RESET`."""
    opsi = _RENTANG_RESET.get(request.POST.get("rentang"))
    if opsi is None:
        messages.error(request, "Pilihan rentang reset tidak valid.")
        return redirect("pakln:log_sistem")

    keluaran = StringIO()
    try:
        call_command("bersihkan_log", oleh=request.user.username, stdout=keluaran, **opsi)
    except CommandError as exc:
        messages.error(request, f"Reset Log gagal: {exc}")
        return redirect("pakln:log_sistem")

    cocok = re.search(r"Dihapus: (\d+)", keluaran.getvalue())
    messages.success(request, f"Reset Log selesai: {cocok.group(1) if cocok else 0} baris log dihapus permanen.")
    return redirect("pakln:log_sistem")
