"""
Alur proses pengajuan per jenis/tipe — satu sumber kebenaran urutan tahap,
lihat wiki/instructions/BISNIS_PROSES_PDLN.MD §2.1 & §4.

    ALUR[kunci] = urutan status, dengan kunci "nondinas" atau kode tipe PDLN.

`dibatalkan` bukan bagian urutan: status final yang bisa dicapai dari
status mana pun lewat `pengajuan.pembatalan`.
"""

from .models import LaporanPdln, Pengajuan, PermohonanPembatalan

S = Pengajuan.Status

ALUR = {
    "nondinas": [S.BELUM, S.PROSES, S.PROSES_PAKLN, S.SELESAI],
    "T1": [S.BELUM, S.PROSES, S.PROSES_PAKLN, S.SELESAI],
    "T3": [S.BELUM, S.PROSES, S.PROSES_PAKLN, S.SELESAI],
    "T2P": [S.BELUM, S.PROSES, S.PROSES_BPSDM, S.PROSES_PAKLN, S.SELESAI],
    "T2L": [S.BELUM, S.PROSES, S.PROSES_BPSDM, S.PROSES_PAKLN, S.SELESAI],
}

# Status tempat masing-masing role admin bertindak.
STATUS_ROLE = {
    "admin_unor": S.PROSES,
    "admin_bpsdm": S.PROSES_BPSDM,
    "admin_pakln": S.PROSES_PAKLN,
}

# Judul & deskripsi tahap Timeline Proses per kunci alur (teks mockup).
_JUDUL = {
    S.BELUM: "Diajukan Pegawai",
    S.PROSES: "Dalam Proses Unor",
    S.PROSES_BPSDM: "Dalam Proses BPSDM",
    S.PROSES_PAKLN: "Dalam Proses Biro PAKLN",
    S.SELESAI: "Selesai",
}

_DESKRIPSI = {
    "nondinas": {
        S.BELUM: "Pengisian Formulir dan Unggah Berkas untuk disampaikan ke Unor.",
        S.PROSES: "Pratinjau Formulir dan Berkas, permohonan tanda tangan Pimpinan Unor, "
                  "permohonan persetujuan Menteri, penyampaian berkas ke Biro PAKLN.",
        S.PROSES_PAKLN: "Permohonan tanda tangan Sekretaris Jenderal a.n. Menteri.",
        S.SELESAI: "Seluruh proses administrasi perizinan telah rampung.",
    },
    "T1": {
        S.BELUM: "Pengisian Formulir Detail PDLN dan unggah berkas untuk disampaikan ke Unor.",
        S.PROSES: "Permohonan Izin Prinsip Menteri, penerbitan Surat Tugas, penyampaian berkas ke Biro PAKLN.",
        S.PROSES_PAKLN: "Proses SP Setneg, Paspor Dinas, Exit Permit, dan Rekomendasi Visa (jika diperlukan).",
        S.SELESAI: "Seluruh proses administrasi PDLN telah rampung — unggah Laporan PDLN setelah perjalanan.",
    },
    "T3": {
        S.BELUM: "Pengisian Formulir Detail PDLN (atas disposisi Menteri) dan unggah berkas untuk disampaikan ke Unor.",
        S.PROSES: "Permohonan Izin Prinsip/Disposisi Menteri, penerbitan Surat Tugas, penyampaian berkas ke Biro PAKLN.",
        S.PROSES_PAKLN: "Proses SP Setneg, Paspor Dinas, Exit Permit, dan Rekomendasi Visa (jika diperlukan).",
        S.SELESAI: "Seluruh proses administrasi PDLN telah rampung — unggah Laporan PDLN setelah perjalanan.",
    },
    "T2P": {
        S.BELUM: "Pengisian Formulir Detail Tugas Belajar dan unggah berkas untuk disampaikan ke Unor.",
        S.PROSES: "Permohonan Surat Tugas Pimpinan Unor dan penyampaian berkas ke Admin BPSDM.",
        S.PROSES_BPSDM: "Permohonan Izin Prinsip Menteri, penandatanganan Perjanjian Ikatan Dinas/SK Tugas "
                        "Belajar, penyampaian berkas ke Biro PAKLN.",
        S.PROSES_PAKLN: "Proses SP Setneg, Paspor Dinas, Exit Permit, Rekomendasi Visa (jika diperlukan), "
                        "dan SK Tugas Belajar.",
        S.SELESAI: "Seluruh proses administrasi PDLN telah rampung — unggah Laporan PDLN setelah perjalanan.",
    },
    "T2L": {
        S.BELUM: "Pengisian Formulir Detail Pelatihan dan unggah berkas untuk disampaikan ke Unor.",
        S.PROSES: "Permohonan Surat Tugas Pimpinan Unor dan penyampaian berkas ke Admin BPSDM.",
        S.PROSES_BPSDM: "Permohonan Izin Prinsip Menteri dan penyampaian berkas ke Biro PAKLN.",
        S.PROSES_PAKLN: "Proses SP Setneg, Paspor Dinas, Exit Permit, dan Rekomendasi Visa (jika diperlukan).",
        S.SELESAI: "Seluruh proses administrasi PDLN telah rampung — unggah Laporan PDLN setelah perjalanan.",
    },
}

# Sub-status laporan pada tahap Selesai (PDLN).
_LABEL_LAPORAN = {
    None: "Menunggu Laporan PDLN",
    LaporanPdln.Status.MENUNGGU: "Laporan menunggu verifikasi Biro PAKLN",
    LaporanPdln.Status.DIKEMBALIKAN: "Laporan dikembalikan — perlu diunggah ulang",
    LaporanPdln.Status.DISETUJUI: "Laporan disetujui — tuntas",
}


def urutan(pengajuan):
    return ALUR.get(pengajuan.kunci_alur, ALUR["nondinas"])


def tahap_berikut(pengajuan):
    """Status sesudah status saat ini pada alur tipe pengajuan."""
    langkah = urutan(pengajuan)
    if pengajuan.status not in langkah:
        return None
    idx = langkah.index(pengajuan.status)
    return langkah[idx + 1] if idx + 1 < len(langkah) else None


def tahap_sebelumnya(pengajuan):
    """Status tujuan bila pengajuan dikembalikan (selalu tahap tepat
    sebelumnya, BISNIS_PROSES_PDLN.MD §4.2)."""
    langkah = urutan(pengajuan)
    if pengajuan.status not in langkah:
        return None
    idx = langkah.index(pengajuan.status)
    return langkah[idx - 1] if idx > 0 else None


def label_tahap(status):
    return _JUDUL.get(status, Pengajuan.Status(status).label if status in Pengajuan.Status.values else status)


def _tanggal(pengajuan, status):
    return {
        S.BELUM: pengajuan.tgl_pengajuan,
        S.PROSES_BPSDM: pengajuan.tgl_masuk_bpsdm,
        S.PROSES_PAKLN: pengajuan.tgl_masuk_pakln,
        S.SELESAI: pengajuan.tgl_selesai,
    }.get(status)


def _status_saat_dibatalkan(pengajuan):
    permohonan = pengajuan.permohonan_pembatalan.filter(
        status=PermohonanPembatalan.Status.DISETUJUI
    ).first()
    return (permohonan.status_pengajuan_saat_diajukan if permohonan else S.BELUM), permohonan


def timeline(pengajuan):
    """Tahap Timeline Proses: list dict {status, title, desc, tanggal,
    state}. `state` ∈ done/current/upcoming/cancelled. Pengajuan yang
    dibatalkan diberi tahap penutup "Dibatalkan"."""
    langkah = urutan(pengajuan)
    deskripsi = _DESKRIPSI.get(pengajuan.kunci_alur, _DESKRIPSI["nondinas"])
    permohonan_batal = None

    if pengajuan.status == S.DIBATALKAN:
        status_acuan, permohonan_batal = _status_saat_dibatalkan(pengajuan)
        current_index = langkah.index(status_acuan) if status_acuan in langkah else 0
    else:
        current_index = langkah.index(pengajuan.status) if pengajuan.status in langkah else 0

    hasil = []
    for idx, status in enumerate(langkah):
        if pengajuan.status == S.DIBATALKAN:
            state = "done" if idx < current_index else "upcoming"
        elif idx < current_index:
            state = "done"
        elif idx == current_index and pengajuan.status != S.BELUM:
            state = "current"
        else:
            state = "upcoming"
        desc = deskripsi.get(status, "")
        if status == S.SELESAI and pengajuan.is_pdln and pengajuan.status == S.SELESAI:
            laporan = pengajuan.laporan
            desc = _LABEL_LAPORAN[laporan.status if laporan else None]
            if laporan and laporan.status == LaporanPdln.Status.DISETUJUI:
                state = "done"
        hasil.append({
            "status": status,
            "title": _JUDUL[status],
            "desc": desc,
            "tanggal": _tanggal(pengajuan, status),
            "state": state,
        })

    if pengajuan.status == S.DIBATALKAN:
        hasil.append({
            "status": S.DIBATALKAN,
            "title": "Dibatalkan",
            "desc": permohonan_batal.alasan if permohonan_batal else "Perjalanan dibatalkan.",
            "tanggal": pengajuan.tgl_dibatalkan,
            "state": "cancelled",
        })
    return hasil


def pengajuan_belum_tuntas(pegawai):
    """Pengajuan terbaru pegawai yang belum mencapai tahap akhir, atau
    None (aturan satu pengajuan aktif, BISNIS_PROSES_PDLN.MD §2.1)."""
    qs = (
        Pengajuan.objects.filter(pegawai=pegawai)
        .exclude(status=S.DIBATALKAN)
        .select_related("laporan_pdln")
        .order_by("-created_at")
    )
    for p in qs:
        if not p.tuntas:
            return p
    return None


def alasan_belum_tuntas(pengajuan):
    """Kalimat penjelasan mengapa pegawai belum dapat mengajukan baru."""
    if pengajuan is None:
        return ""
    if pengajuan.status == S.BELUM and not pengajuan.pernah_dikirim:
        return f"Lanjutkan draft {pengajuan.kode} yang sudah dibuat terlebih dahulu."
    if pengajuan.status == S.SELESAI and pengajuan.is_pdln:
        laporan = pengajuan.laporan
        if laporan is None:
            return f"Laporan PDLN untuk {pengajuan.kode} belum diunggah."
        if laporan.status == LaporanPdln.Status.DIKEMBALIKAN:
            return f"Laporan PDLN {pengajuan.kode} dikembalikan Biro PAKLN dan perlu diunggah ulang."
        return f"Laporan PDLN {pengajuan.kode} belum disetujui Admin Biro PAKLN."
    return f"Pengajuan {pengajuan.kode} masih berjalan ({pengajuan.get_status_display()})."


def kunci(pengajuan):
    """Ambil ulang baris pengajuan dengan row lock — panggil di dalam
    `transaction.atomic()` sebelum mengubah status, lalu periksa ulang
    statusnya agar dua admin tidak memproses bersamaan."""
    return Pengajuan.objects.select_for_update().get(pk=pengajuan.pk)


def alasan_dibekukan(pengajuan):
    """Pesan bila aksi alur utama tidak boleh dijalankan, atau ''."""
    if pengajuan.status == S.DIBATALKAN:
        return f"Pengajuan {pengajuan.kode} sudah dibatalkan."
    if pengajuan.pembatalan_terbuka:
        return (
            f"Pengajuan {pengajuan.kode} sedang dalam proses permohonan pembatalan — "
            "aksi lain dibekukan sampai permohonan diputus atau ditarik."
        )
    return ""
