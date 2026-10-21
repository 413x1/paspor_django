"""Admin BKO — track paralel SK Tugas Belajar PDLN Tipe 2 Pendidikan (T2P),
lihat wiki/instructions/PDLN_TIPE_2_FLOW.MD §8. Cakupan: seluruh T2P lintas
unit organisasi yang sudah diteruskan Admin BPSDM (`report.queryset_untuk`).

Admin BKO tidak mengembalikan/meneruskan pengajuan: hanya mengunggah SK
Tubel, atau menutup pemrosesan dengan alasan (dan membukanya kembali)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape, format_html

from logs.utils import catat_riwayat

from . import bko, persyaratan, report, riwayat, tahap
from .decorators import role_required, tolak_pengajuan_sendiri
from .models import Pengajuan, PermohonanPembatalan, RiwayatPengajuan
from .views_unor import status_html

S = Pengajuan.Status
SB = Pengajuan.StatusBko
Aksi = RiwayatPengajuan.Aksi


def _scoped(request):
    return report.queryset_untuk(request.user)


@role_required("admin_bko")
def dashboard(request):
    return render(request, "bko/dashboard.html", {
        "summary": report.ringkasan_bko(_scoped(request)),
        "opsi_status_bko": SB.choices,
    })


_ORDER_FIELDS = {
    "0": "pegawai__profile__nama",
    "1": "unit_organisasi__name",
    "3": "tgl_berangkat",
    "4": "tgl_masuk_bko",
    "5": "status",
    "6": "status_bko",
}


@role_required("admin_bko")
def dashboard_data(request):
    qs = _scoped(request).select_related("pegawai__profile", "unit_organisasi", "detail_pdln")
    status_bko = request.GET.get("status_bko")
    if status_bko in SB.values:
        qs = qs.filter(status_bko=status_bko)

    def baris(p):
        if bko.bisa_diubah(p) and p.status_bko != SB.DIUNGGAH:
            aksi = format_html('<a href="{}" class="button is-warning is-small">Proses →</a>',
                               reverse("bko:proses", args=[p.kode]))
        else:
            aksi = format_html('<a href="{}" class="button is-small">Lihat</a>', reverse("bko:proses", args=[p.kode]))
        detail = p.detail
        return [
            format_html("<strong>{}</strong><br><span class=\"cell-muted\">{}</span>",
                        p.pegawai.profile.nama, p.pegawai.profile.nip),
            escape(p.unit_organisasi.alias if p.unit_organisasi else "—"),
            escape(detail.perguruan_tinggi if detail and detail.perguruan_tinggi else "—"),
            p.tgl_berangkat.strftime("%d %b %Y") if p.tgl_berangkat else "—",
            p.tgl_masuk_bko.strftime("%d %b %Y") if p.tgl_masuk_bko else "—",
            status_html(p, dengan_bko=False),
            format_html('<span class="tag bko-status is-{}">{}</span>', p.status_bko, p.get_status_bko_display()),
            aksi,
        ]

    return report.datatable(request, qs, _ORDER_FIELDS, baris, report.search_pengajuan, "-tgl_masuk_bko")


@role_required("admin_bko")
def proses(request, kode):
    """Satu halaman: pratinjau data pegawai & pengajuan (read-only),
    unggah SK Tubel, Tutup Pemrosesan, atau Buka Kembali."""
    pengajuan = get_object_or_404(_scoped(request), kode=kode)
    if request.method == "POST":
        tolak_pengajuan_sendiri(request, pengajuan)  # AB-12

    if request.method == "POST":
        hasil = _proses_post(request, pengajuan)
        if hasil:
            return hasil
        pengajuan.refresh_from_db()

    dok = tahap.konteks_dokumen(pengajuan, "bko")
    alasan_kunci = bko.alasan_tidak_bisa_ubah(pengajuan)
    return render(request, "bko/proses.html", {
        "pengajuan": pengajuan,
        "direktori": persyaratan.direktori(pengajuan, "bko"),
        **dok,
        "readonly": bool(alasan_kunci) or pengajuan.status_bko == SB.DITUTUP,
        "alasan_kunci": alasan_kunci,
        "pembatalan_terbuka": pengajuan.pembatalan_terbuka,
        **riwayat.konteks(pengajuan, request.user),
    })


def _proses_post(request, pengajuan):
    pesan = bko.alasan_tidak_bisa_ubah(pengajuan)
    if pesan:
        messages.error(request, pesan)
        return redirect("bko:proses", kode=pengajuan.kode)

    try:
        if "tutup" in request.POST:
            p = bko.tutup(pengajuan, request.user, request.POST.get("catatan", ""))
            catat_riwayat(request, p, Aksi.DITUTUP_BKO)
            messages.success(request, f"Pemrosesan SK Tugas Belajar {p.kode} ditutup beserta alasan.")
            return redirect("bko:dashboard")
        if "buka_kembali" in request.POST:
            p = bko.buka_kembali(pengajuan, request.user, request.POST.get("catatan", ""))
            catat_riwayat(request, p, Aksi.DIBUKA_ULANG_BKO)
            messages.success(request, f"Pemrosesan SK Tugas Belajar {p.kode} dibuka kembali.")
            return redirect("bko:proses", kode=p.kode)
    except bko.BkoError as exc:
        messages.error(request, str(exc))
        return None

    if pengajuan.status_bko == SB.DITUTUP:
        messages.error(request, "Pemrosesan BKO sedang ditutup — buka kembali sebelum mengunggah SK Tubel.")
        return None
    hasil = tahap.proses_unggah(request, pengajuan, "bko", "bko:proses")
    if hasil:
        try:
            p = bko.setelah_unggah(pengajuan, request.user)
            catat_riwayat(request, p, Aksi.SK_TUBEL_DIUNGGAH)
        except bko.BkoError as exc:
            messages.error(request, str(exc))
    return hasil


@role_required("admin_bko")
def hapus_dokumen(request, kode, jenis):
    pengajuan = get_object_or_404(_scoped(request), kode=kode)
    tolak_pengajuan_sendiri(request, pengajuan)  # AB-12
    if request.method == "POST" and bko.bisa_diubah(pengajuan) and pengajuan.status_bko == SB.DIUNGGAH:
        tahap.hapus(request, pengajuan, "bko", jenis)
        bko.setelah_hapus(pengajuan)
    return redirect("bko:proses", kode=kode)


@role_required("admin_bko")
def daftar_pembatalan(request):
    """Permohonan pembatalan T2P — read-only (BKO bukan jenjang persetujuan)."""
    qs = PermohonanPembatalan.objects.filter(pengajuan__in=_scoped(request)).select_related("pengajuan__pegawai__profile")
    return render(request, "bersama/pembatalan.html", {
        "daftar": qs.order_by("-created_at"),
        "semua": True,
        "menunggu": None,
        "putuskan_url": "",
        "preview_url": "bko:proses",
        "jumlah_menunggu": 0,
    })
