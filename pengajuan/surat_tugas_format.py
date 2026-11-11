"""
Format Surat Tugas Pimpinan Unor (PDLN Tipe 2: T2P dan T2L) yang dibangkitkan sistem — pola Generate ND
(WeasyPrint), lihat wiki/instructions/RANCANGAN_UPDATE_AJUAN_TP2_PENDIDIKAN_TP2_PELATIHAN.md.

Berbeda dari `DokumenTemplate` (berkas statis yang diunggah Admin Biro PAKLN), format ini terisi otomatis dari
data pengajuan dan memuat **Tanggal Surat Izin Prinsip Menteri** yang diunggah Admin BPSDM. Admin Unor melengkapi
beberapa isian (nomor surat, pejabat penandatangan), mengunduh PDF, meminta tanda tangan Pimpinan Unor, lalu
mengunggah hasilnya sebagai berkas Surat Tugas (`pengajuan.surat_tugas`).

CATATAN: tata letak di bawah adalah format umum; format resmi menunggu contoh dari Biro PAKLN/BPSDM
(BISNIS_PROSES_PDLN.MD §14 butir 10). Cukup ubah `templates/unor/pdf_template_surat_tugas.html`.
"""

import base64
from datetime import datetime

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.utils import timezone

_BULAN_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

# Teks pengganti bila isian belum dilengkapi, supaya bagian yang harus diisi tangan tetap terlihat di PDF.
KOSONG_NOMOR = "......../........./........"
KOSONG_NAMA_PIMPINAN = "[Nama Pimpinan Unor]"
KOSONG_JABATAN_PIMPINAN = "[Jabatan Pimpinan Unor]"
KOSONG_IZIN_PRINSIP = "[tanggal Izin Prinsip]"
KOTA_DEFAULT = "Jakarta"


def tanggal_indonesia(tanggal):
    """date -> '5 Oktober 2026'."""
    return f"{tanggal.day} {_BULAN_ID[tanggal.month - 1]} {tanggal.year}"


def _tanggal_dari_input(nilai, default):
    """String <input type="date"> (YYYY-MM-DD) -> date; `default` bila kosong/tidak valid."""
    try:
        return datetime.strptime((nilai or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return default


def tanggal_izin_prinsip(pengajuan):
    """Tanggal Surat Izin Prinsip Menteri yang diunggah Admin BPSDM, atau None bila belum ada."""
    dokumen = next((d for d in pengajuan.dokumen_bpsdm.all() if d.jenis == "izin_prinsip"), None)
    return dokumen.tanggal_surat if dokumen else None


def logo_data_uri():
    """Logo sebagai data URI: WeasyPrint tidak perlu mengambil berkas lewat jaringan (lihat views_pakln._logo_data_uri)."""
    path = finders.find("images/logopu.png")
    if not path:
        return ""
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")


def _rentang(berangkat, kembali):
    if berangkat and kembali:
        hari = (kembali - berangkat).days + 1
        return f"{tanggal_indonesia(berangkat)} s.d. {tanggal_indonesia(kembali)} ({hari} hari)"
    return tanggal_indonesia(berangkat or kembali) if (berangkat or kembali) else ""


def konteks(pengajuan, isian=None):
    """Konteks template cetak. `isian` = dict/QueryDict isian Admin Unor: nomor_surat, kota, tanggal_surat,
    jabatan_pimpinan, nama_pimpinan. Semua opsional; yang kosong diganti teks pengganti."""
    isian = isian or {}
    profil = getattr(pengajuan.pegawai, "profile", None)
    detail = pengajuan.detail
    unit = pengajuan.unit_organisasi or (profil.unit_organisasi if profil else None)
    izin = tanggal_izin_prinsip(pengajuan)
    kegiatan = (detail.kegiatan_nama if detail and detail.kegiatan_nama else
                (pengajuan.kegiatan.nama if pengajuan.kegiatan else "")) or pengajuan.maksud
    penyelenggara = (detail.penyelenggara or detail.perguruan_tinggi) if detail else ""
    return {
        "logo_data_uri": logo_data_uri(),
        "unit_organisasi": (unit.name if unit else "").upper(),
        "nomor_surat": (isian.get("nomor_surat") or "").strip() or KOSONG_NOMOR,
        "kota": (isian.get("kota") or "").strip() or KOTA_DEFAULT,
        "tanggal_surat": tanggal_indonesia(_tanggal_dari_input(isian.get("tanggal_surat"), timezone.localdate())),
        "jabatan_pimpinan": (isian.get("jabatan_pimpinan") or "").strip() or KOSONG_JABATAN_PIMPINAN,
        "nama_pimpinan": (isian.get("nama_pimpinan") or "").strip() or KOSONG_NAMA_PIMPINAN,
        "tanggal_izin_prinsip": tanggal_indonesia(izin) if izin else KOSONG_IZIN_PRINSIP,
        "pegawai_nama": profil.nama if profil else pengajuan.pegawai.get_full_name(),
        "pegawai_nip": profil.nip if profil else "",
        "pegawai_pangkat": profil.pangkat_golongan if profil else "",
        "pegawai_jabatan": profil.jabatan if profil else "",
        "pegawai_unit_kerja": (profil.unit_kerja if profil else pengajuan.pegawai.unit_kerja) or "",
        "jenis_tugas": pengajuan.jenis_label,
        "kegiatan": kegiatan,
        "penyelenggara": penyelenggara,
        "tujuan": ", ".join(filter(None, [detail.kota_tujuan if detail else "", pengajuan.tujuan_negara_display])),
        "rentang_tanggal": _rentang(pengajuan.tgl_berangkat, pengajuan.tgl_kembali),
    }


def render_html(pengajuan, isian=None):
    return render_to_string("unor/pdf_template_surat_tugas.html", konteks(pengajuan, isian))


def buat_pdf(pengajuan, isian=None):
    """Bytes PDF. Dapat melempar ImportError (WeasyPrint belum terpasang) atau OSError (pustaka GTK/Pango belum ada)."""
    from weasyprint import HTML

    return HTML(string=render_html(pengajuan, isian)).write_pdf()


def nama_berkas(pengajuan):
    return f"Surat_Tugas_{pengajuan.kode}.pdf"
