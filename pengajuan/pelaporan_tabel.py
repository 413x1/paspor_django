"""Tabel Pelaporan PDLN server-side (DataTables) — dipakai bersama oleh Admin Biro PAKLN dan Admin Unor.

Satu sumber aturan untuk dua halaman: PDLN berstatus Selesai (wajib lapor) yang terlihat oleh pengguna
(`report.queryset_untuk`: Admin Unor hanya melihat unit organisasinya), enam angka kartu ringkasan lewat agregasi
database, dan baris tabel untuk protokol DataTables (draw/start/length/search/order pada GET).

Perbedaan antar peran hanya dua: tautan kode ke halaman pratinjau milik perannya, dan tombol Verifikasi/Request
Perbaikan yang hanya ada untuk Admin PAKLN (`verifikasi_url`)."""

from datetime import timedelta

from django.db.models import Count, Q
from django.template.defaultfilters import date as filter_tanggal
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from . import report
from .models import LaporanPdln, Pengajuan


def qs_pelaporan(user):
    """PDLN berstatus Selesai (wajib lapor) yang terlihat oleh `user` — dasar halaman Pelaporan PDLN."""
    return report.queryset_untuk(user).filter(
        jenis_perjalanan=Pengajuan.JenisPerjalanan.PDLN, status=Pengajuan.Status.SELESAI,
    )


def hitung_pelaporan(qs):
    """Angka 6 kartu ringkasan lewat agregasi database (satu query): laporan draft dihitung "belum melapor";
    "terlambat" hanya untuk yang belum melapor dan sudah lewat `report.BATAS_HARI_LAPORAN` hari sejak tanggal kembali."""
    batas = timezone.localdate() - timedelta(days=report.BATAS_HARI_LAPORAN)
    belum_lapor = Q(laporan_pdln__isnull=True) | Q(laporan_pdln__status=LaporanPdln.Status.DRAFT)
    hitung = qs.aggregate(
        selesai=Count("pk"),
        menunggu=Count("pk", filter=Q(laporan_pdln__status=LaporanPdln.Status.MENUNGGU)),
        dikembalikan=Count("pk", filter=Q(laporan_pdln__status=LaporanPdln.Status.DIKEMBALIKAN)),
        disetujui=Count("pk", filter=Q(laporan_pdln__status=LaporanPdln.Status.DISETUJUI)),
        terlambat=Count("pk", filter=belum_lapor & Q(tgl_kembali__lt=batas)),
    )
    hitung["belum"] = hitung["selesai"] - hitung["menunggu"] - hitung["dikembalikan"] - hitung["disetujui"]
    return hitung


# Kolom tabel Pelaporan PDLN (index sesuai urutan kolom pada pelaporan.html) -> field ORDER BY.
# Kolom Negara (many-to-many), Status Pelaporan (turunan), dan Aksi tidak dapat diurutkan.
ORDER_FIELDS = {
    "0": "pegawai__profile__nama",
    "1": "unit_organisasi__alias",
    "2": "kode",
    "4": "tgl_kembali",
    "6": "laporan_pdln__uploaded_at",
}


def cari(nilai):
    return (
        Q(kode__icontains=nilai)
        | Q(pegawai__profile__nama__icontains=nilai)
        | Q(pegawai__profile__nip__icontains=nilai)
        | Q(unit_organisasi__alias__icontains=nilai)
        | Q(unit_organisasi__name__icontains=nilai)
        | Q(tujuan_negara__nama_negara__icontains=nilai)
    )


def respons_data(request, *, preview_url, verifikasi_url=None):
    """Endpoint JSON server-side untuk tabel Pelaporan PDLN.

    `preview_url`: nama URL halaman pratinjau pengajuan milik peran ini (mis. "unor:preview").
    `verifikasi_url`: nama URL verifikasi laporan; hanya Admin PAKLN yang mengisinya. Bila kosong, kolom Aksi
    hanya berisi tombol Lihat (tanpa tombol Verifikasi/Request Perbaikan dan ringkasan modal)."""
    qs = (
        qs_pelaporan(request.user)
        .select_related("pegawai__profile", "unit_organisasi", "laporan_pdln")
        .prefetch_related("tujuan_negara")
    )
    hari_ini = timezone.localdate()

    def baris(p):
        profil = getattr(p.pegawai, "profile", None)
        laporan = p.laporan
        if laporan is not None and laporan.status == LaporanPdln.Status.DRAFT:
            laporan = None   # draft belum dilaporkan: dihitung "belum melapor"
        status = laporan.status if laporan else "belum"
        terlambat = bool(laporan is None and p.tgl_kembali and (hari_ini - p.tgl_kembali).days > report.BATAS_HARI_LAPORAN)
        uraian = [] if laporan is None else [
            ("Tujuan Kegiatan", laporan.tujuan_kegiatan), ("Materi Kegiatan", laporan.materi_kegiatan),
            ("Tindak Lanjut", laporan.tindak_lanjut), ("Dampak Rekomendasi", laporan.dampak_rekomendasi),
        ]
        pegawai_html = format_html(
            '{}<br><span class="cell-muted">{}</span>',
            profil.nama if profil else "", profil.nip if profil else "",
        )
        kode_html = format_html(
            '<a href="{}">{}</a><br><span class="cell-muted">{}</span>',
            reverse(preview_url, kwargs={"kode": p.kode}), p.kode, p.jenis_label,
        )
        status_html = format_html(
            "{}{}",
            laporan.get_status_display() if laporan else "Belum melapor",
            mark_safe('<br><span class="text-danger is-strong">Terlambat</span>') if terlambat else "",
        )
        aksi_html = render_to_string("partials/_pelaporan_aksi.html", {
            "p": p, "laporan": laporan, "status": status, "uraian": uraian,
            "dapat_verifikasi": bool(verifikasi_url),
            "verifikasi_url": reverse(verifikasi_url, kwargs={"kode": p.kode}) if verifikasi_url else "",
        }).strip()
        return [
            pegawai_html,
            p.unit_organisasi.alias if p.unit_organisasi else "—",
            kode_html,
            # `.all()` memakai hasil prefetch (tanpa query per baris), berbeda dengan `tujuan_negara_display`.
            ", ".join(n.nama_negara for n in p.tujuan_negara.all()),
            filter_tanggal(p.tgl_kembali, "d M Y") if p.tgl_kembali else "",
            status_html,
            filter_tanggal(laporan.uploaded_at, "d M Y") if laporan and laporan.uploaded_at else "—",
            aksi_html,
        ]

    return report.datatable(request, qs, ORDER_FIELDS, baris, cari, default_order="-tgl_selesai")
