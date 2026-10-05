"""Admin BPSDM — tahap khusus PDLN Tipe 2 (Pendidikan & Pelatihan), lihat
wiki/instructions/BISNIS_PROSES_PDLN.MD §3–§4. Cakupan: seluruh pengajuan
T2P/T2L lintas unit organisasi (`report.queryset_untuk`)."""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape, format_html

from notifications.services import notify_approve_unor, notify_reject_bpsdm

from . import alur, persyaratan, report, riwayat, tahap
from .decorators import role_required
from .models import Pengajuan, PermohonanPembatalan, RiwayatPengajuan
from .views_unor import status_html

S = Pengajuan.Status
Aksi = RiwayatPengajuan.Aksi


def _scoped(request):
    return report.queryset_untuk(request.user)


@role_required("admin_bpsdm")
def dashboard(request):
    qs = _scoped(request)
    return render(request, "bpsdm/dashboard.html", {"summary": report.ringkasan(request.user, qs)})


_ORDER_FIELDS = {
    "0": "pegawai__profile__nama",
    "1": "unit_organisasi__name",
    "2": "tipe_pdln",
    "3": "kategori__nama_kategori",
    "5": "tgl_berangkat",
    "6": "tgl_masuk_bpsdm",
    "7": "status",
}


@role_required("admin_bpsdm")
def dashboard_data(request):
    qs = _scoped(request).select_related("pegawai__profile", "kategori", "unit_organisasi", "detail_pdln")

    def baris(p):
        if p.status == S.PROSES_BPSDM and not p.pembatalan_terbuka:
            url = reverse("bpsdm:upload_dokumen" if p.preview_bpsdm_agree else "bpsdm:preview", args=[p.kode])
            aksi = format_html('<a href="{}" class="button is-warning is-small">TL →</a>', url)
        elif p.status in (S.PROSES, S.BELUM):
            aksi = format_html('<span class="cell-muted">Menunggu Admin Unor</span>')
        else:
            aksi = format_html('<a href="{}" class="button is-small">Lihat</a>', reverse("bpsdm:preview", args=[p.kode]))
        detail = p.detail
        return [
            format_html("<strong>{}</strong><br><span class=\"cell-muted\">{}</span>",
                        p.pegawai.profile.nama, p.pegawai.profile.nip),
            escape(p.unit_organisasi.alias if p.unit_organisasi else "—"),
            escape(p.jenis_label),
            escape(p.kategori.nama_kategori) if p.kategori else "—",
            escape((detail.perguruan_tinggi or detail.penyelenggara) if detail else "—"),
            p.tgl_berangkat.strftime("%d %b %Y") if p.tgl_berangkat else "—",
            p.tgl_masuk_bpsdm.strftime("%d %b %Y") if p.tgl_masuk_bpsdm else "—",
            status_html(p),
            aksi,
        ]

    return report.datatable(request, qs, _ORDER_FIELDS, baris, report.search_pengajuan)


@role_required("admin_bpsdm")
def preview(request, kode):
    pengajuan = get_object_or_404(_scoped(request), kode=kode)

    if request.method == "POST":
        pesan = alur.alasan_dibekukan(pengajuan)
        if pesan:
            messages.error(request, pesan)
            return redirect("bpsdm:preview", kode=kode)
        if "lanjutkan" in request.POST and pengajuan.status == S.PROSES_BPSDM:
            pengajuan.preview_bpsdm_agree = True
            pengajuan.save(update_fields=["preview_bpsdm_agree"])
            return redirect("bpsdm:upload_dokumen", kode=kode)
        if "kembalikan" in request.POST:
            catatan = request.POST.get("catatan", "").strip()
            if not catatan:
                messages.error(request, "Isi catatan perbaikan untuk Admin Unor sebelum mengembalikan pengajuan.")
            else:
                with transaction.atomic():
                    p = alur.kunci(pengajuan)
                    if p.status != S.PROSES_BPSDM or alur.alasan_dibekukan(p):
                        messages.error(request, "Pengajuan sudah diproses pihak lain atau sedang dibekukan.")
                        return redirect("bpsdm:preview", kode=kode)
                    status_dari = p.status
                    p.status = S.PROSES
                    p.preview_unor_agree = False
                    p.preview_bpsdm_agree = False
                    p.catatan_bpsdm = catatan
                    p.save()
                    riwayat.catat(p, Aksi.DIKEMBALIKAN_BPSDM, request.user, status_dari, catatan=catatan)
                notify_reject_bpsdm(p, catatan)
                messages.success(request, f"Pengajuan {p.kode} dikembalikan ke Admin Unor beserta catatan.")
                return redirect("bpsdm:dashboard")

    catatan_pakln = pengajuan.catatan_pakln if pengajuan.status == S.PROSES_BPSDM else ""
    return render(request, "bpsdm/preview.html", {
        "pengajuan": pengajuan,
        "direktori": persyaratan.direktori(pengajuan, "bpsdm"),
        "catatan_pakln": catatan_pakln,
        "dibekukan": alur.alasan_dibekukan(pengajuan),
        "pembatalan_terbuka": pengajuan.pembatalan_terbuka,
        "catatan_perbaikan": riwayat.catatan_perbaikan(pengajuan, Aksi.DITERUSKAN_ULANG_BPSDM),
        **riwayat.konteks(pengajuan, request.user),
    })


@role_required("admin_bpsdm")
def upload_dokumen(request, kode):
    pengajuan = get_object_or_404(_scoped(request), kode=kode)
    if not pengajuan.preview_bpsdm_agree or pengajuan.status != S.PROSES_BPSDM:
        return redirect("bpsdm:preview", kode=kode)

    if request.method == "POST":
        if "teruskan" in request.POST:
            hasil = _teruskan(request, pengajuan)
        else:
            hasil = tahap.proses_unggah(request, pengajuan, "bpsdm", "bpsdm:upload_dokumen")
        if hasil:
            return hasil

    return render(request, "bpsdm/upload.html", {
        "pengajuan": pengajuan,
        **tahap.konteks_dokumen(pengajuan, "bpsdm"),
        "catatan_pakln": pengajuan.catatan_pakln,
        "dibekukan": alur.alasan_dibekukan(pengajuan),
        "templates": tahap.templates_untuk(request.user, pengajuan, "bpsdm"),
        **riwayat.konteks(pengajuan, request.user),
    })


def _teruskan(request, pengajuan):
    is_ulang = bool(pengajuan.catatan_pakln)
    catatan = request.POST.get("catatan", "").strip() if is_ulang else ""
    kurang = tahap.konteks_dokumen(pengajuan, "bpsdm")["dokumen_kurang"]
    if kurang:
        messages.error(request, "Lengkapi dokumen administrasi BPSDM sebelum meneruskan: " + ", ".join(kurang) + ".")
        return None
    if is_ulang and not catatan:
        messages.error(request, "Isi catatan perbaikan untuk Admin Biro PAKLN sebelum meneruskan ulang.")
        return None
    if not request.POST.get("agree"):
        messages.error(request, "Centang pernyataan kelengkapan dokumen terlebih dahulu.")
        return None

    with transaction.atomic():
        p = alur.kunci(pengajuan)
        pesan = alur.alasan_dibekukan(p)
        if p.status != S.PROSES_BPSDM or pesan:
            messages.error(request, pesan or "Pengajuan sudah diproses pihak lain.")
            return redirect("bpsdm:dashboard")
        status_dari = p.status
        p.status = S.PROSES_PAKLN
        p.tgl_masuk_pakln = timezone.now().date()
        p.catatan_pakln = ""
        p.save()
        riwayat.catat(p, Aksi.DITERUSKAN_ULANG if is_ulang else Aksi.DITERUSKAN_PAKLN, request.user, status_dari, catatan=catatan)

    notify_approve_unor(p, catatan, dari_bpsdm=True)
    messages.success(request, f"Pengajuan {p.kode} diteruskan ke Admin Biro PAKLN.")
    return redirect("bpsdm:dashboard")


@role_required("admin_bpsdm")
def hapus_dokumen(request, kode, jenis):
    pengajuan = get_object_or_404(_scoped(request), kode=kode)
    if pengajuan.status == S.PROSES_BPSDM:
        tahap.hapus(request, pengajuan, "bpsdm", jenis)
    return redirect("bpsdm:upload_dokumen", kode=kode)


@role_required("admin_bpsdm")
def daftar_pembatalan(request):
    """Permohonan pembatalan PDLN Tipe 2 — read-only (BPSDM bukan jenjang
    persetujuan)."""
    qs = PermohonanPembatalan.objects.filter(pengajuan__in=_scoped(request)).select_related("pengajuan__pegawai__profile")
    return render(request, "bersama/pembatalan.html", {
        "daftar": qs.order_by("-created_at"),
        "semua": True,
        "menunggu": None,
        "putuskan_url": "",
        "preview_url": "bpsdm:preview",
        "jumlah_menunggu": 0,
    })
