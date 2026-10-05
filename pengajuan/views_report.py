"""Halaman report bersama Admin Unor/BPSDM/PAKLN — Export Database &
Rekap (BISNIS_PROSES_PDLN.MD §10). Dipasang di namespace masing-masing role
(`unor:export`, `bpsdm:rekap`, …); cakupan data mengikuti role lewat
`report.queryset_untuk`."""

from django.shortcuts import render
from django.utils import timezone
from django.utils.html import escape, format_html

from paspor.models import KategoriPerjalanan, Negara, SumberPembiayaan, UnitOrganisasi

from . import report
from .decorators import role_required
from .models import Pengajuan

ADMIN_ROLES = ("admin_unor", "admin_bpsdm", "admin_pakln")


def _konteks_filter(request):
    f = report.baca_filter(request.GET)
    params = request.GET.copy()
    params.pop("format", None)
    return {
        "f": f,
        "query": params.urlencode(),
        "ns": request.resolver_match.namespace,
        "opsi_jenis": Pengajuan.JenisPerjalanan.choices,
        "opsi_tipe": Pengajuan.TipePdln.choices if request.user.role != "admin_bpsdm"
        else [c for c in Pengajuan.TipePdln.choices if c[0] in ("T2P", "T2L")],
        "opsi_status": Pengajuan.Status.choices,
        "opsi_unor": UnitOrganisasi.objects.all() if request.user.role != "admin_unor" else [],
        "opsi_negara": Negara.objects.filter(is_active=True),
        "opsi_kategori": KategoriPerjalanan.objects.filter(is_active=True),
        "opsi_sumber": SumberPembiayaan.objects.filter(is_active=True),
        "opsi_kanal": Pengajuan.Kanal.choices,
    }


def _qs(request):
    return report.terapkan_filter(report.queryset_untuk(request.user), report.baca_filter(request.GET))


def _nama_berkas(request):
    return f"paspor_{request.user.role}_{timezone.localdate():%Y%m%d}"


@role_required(*ADMIN_ROLES)
def export_database(request):
    """Export Database terpadu (Dinas & Non-Dinas) — CSV atau XLSX
    (sheet Data + Ringkasan), seluruh baris yang cocok dengan filter."""
    fmt = request.GET.get("format")
    if fmt == "csv":
        return report.respons_csv(_qs(request), _nama_berkas(request))
    if fmt == "xlsx":
        qs = _qs(request)
        return report.respons_xlsx(qs, _nama_berkas(request), rekap_data=report.rekap(qs))
    return render(request, "report/export.html", _konteks_filter(request))


_EXPORT_ORDER_FIELDS = {
    "0": "kode",
    "2": "pegawai__profile__nama",
    "3": "unit_organisasi__name",
    "4": "kategori__nama_kategori",
    "6": "tgl_berangkat",
    "7": "tgl_pengajuan",
    "8": "status",
}


@role_required(*ADMIN_ROLES)
def export_data(request):
    """Endpoint DataTables untuk pratinjau Export Database."""
    qs = _qs(request).select_related("pegawai__profile", "kategori", "unit_organisasi")

    def baris(p):
        prof = getattr(p.pegawai, "profile", None)
        return [
            format_html("<strong>{}</strong>", p.kode),
            escape(p.jenis_label),
            escape(prof.nama if prof else p.pegawai.get_full_name()),
            escape(p.unit_organisasi.name if p.unit_organisasi else "—"),
            escape(p.kategori.nama_kategori if p.kategori else "—"),
            escape(p.tujuan_negara_display or "—"),
            p.tgl_berangkat.strftime("%d %b %Y") if p.tgl_berangkat else "—",
            p.tgl_pengajuan.strftime("%d %b %Y") if p.tgl_pengajuan else "—",
            format_html('<span class="tag paspor-status is-{}"><span class="dot"></span>{}</span>',
                        p.status, p.get_status_display()),
        ]

    return report.datatable(request, qs, _EXPORT_ORDER_FIELDS, baris, report.search_pengajuan, "-tgl_pengajuan")


@role_required(*ADMIN_ROLES)
def rekap(request):
    qs = _qs(request)
    blok = report.rekap(qs)
    tab = request.GET.get("tab", "status")
    if tab not in {b["kunci"] for b in blok}:
        tab = "status"
    return render(request, "report/rekap.html", {
        **_konteks_filter(request),
        "blok": blok,
        "tab": tab,
        "total": qs.count(),
    })
