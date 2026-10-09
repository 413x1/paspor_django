"""
Pembuatan notifikasi untuk tiap trigger pada modul Pengajuan, sesuai
wiki/instructions/SKENARIO_NOTIFIKASI_SURAT.md dan
wiki/instructions/BISNIS_PROSES_PDLN.MD §11.

    Event 1  (NOTIF_01_SUBMIT_UNOR)       — pegawai mengirim pengajuan ke Unor
    Event 2A (NOTIF_02A_APPROVE_UNOR)     — diteruskan ke Biro PAKLN (oleh Unor atau BPSDM)
    Event 2B (NOTIF_02B_REJECT_UNOR)      — Unor mengembalikan ke pegawai
    Event 2C (NOTIF_02C_RESUBMIT_UNOR)    — pegawai mengirim ulang perbaikan
    Event 3A (NOTIF_03A_COMPLETE_PKLN)    — Biro PAKLN menyelesaikan
    Event 3B (NOTIF_03B_REJECT_PKLN...)   — Biro PAKLN mengembalikan ke tahap sebelumnya
    Event 4x (NOTIF_04*)                  — tahap BPSDM (PDLN Tipe 2)
    Event 5x (NOTIF_05*)                  — Laporan PDLN
    Event 6x (NOTIF_06*)                  — Pembatalan (mekanisme interim)
"""

from django.urls import reverse

from . import email_queue
from .models import Notification

JENIS_SURAT = "Surat Izin Perjalanan Luar Negeri Non-Kedinasan"


def _jenis_surat(pengajuan):
    if getattr(pengajuan, "is_pdln", False):
        return f"pengajuan {pengajuan.jenis_label}"
    return JENIS_SURAT


def _profile(pengajuan):
    return getattr(pengajuan.pegawai, "profile", None)


def _nama_pegawai(pengajuan):
    profile = _profile(pengajuan)
    return (profile.nama if profile else None) or pengajuan.pegawai.get_full_name() or pengajuan.pegawai.username


def _nip_pegawai(pengajuan):
    profile = _profile(pengajuan)
    return profile.nip if profile else "-"


def _unit_organisasi(pengajuan):
    if pengajuan.unit_organisasi_id:
        return pengajuan.unit_organisasi
    profile = _profile(pengajuan)
    return profile.unit_organisasi if profile else None


def _perihal(pengajuan):
    if getattr(pengajuan, "is_pdln", False):
        detail = pengajuan.detail
        if detail and (detail.penyelenggara or detail.perguruan_tinggi):
            return detail.penyelenggara or detail.perguruan_tinggi
    return pengajuan.maksud or (pengajuan.kategori.nama_kategori if pengajuan.kategori_id else None) or "-"


def _admin_unor_recipients(pengajuan):
    from accounts.models import User

    unit = _unit_organisasi(pengajuan)
    if not unit:
        return User.objects.none()
    return User.objects.filter(role=User.Role.ADMIN_UNOR, unit_organisasi_id=unit.id, is_active=True)


def _admin_bpsdm_recipients():
    from accounts.models import User

    return User.objects.filter(role=User.Role.ADMIN_BPSDM, is_active=True)


def _admin_pakln_recipients():
    from accounts.models import User

    return User.objects.filter(role=User.Role.ADMIN_PAKLN, is_active=True)


def _create(recipients, *, pengajuan, event, level, title, body, redirect_url):
    notifs = [
        Notification(
            recipient=user,
            pengajuan=pengajuan,
            event=event,
            level=level,
            title=title,
            body=body,
            redirect_url=redirect_url,
        )
        for user in recipients
    ]
    if notifs:
        Notification.objects.bulk_create(notifs)
        # Email dipicu dari titik yang sama agar sinkron dengan notifikasi in-app;
        # tidak pernah melempar error (lihat email_queue.enqueue).
        email_queue.enqueue(notifs)


def _url_monitor(pengajuan):
    return reverse("pegawai:monitor_progres", args=[pengajuan.kode])


# ---------------------------------------------------------------------------
# Alur utama
# ---------------------------------------------------------------------------

def notify_submit_unor(pengajuan):
    """Event 1: Pegawai mengirim pengajuan baru ke Admin Unor."""
    nama = _nama_pegawai(pengajuan)
    nip = _nip_pegawai(pengajuan)
    perihal = _perihal(pengajuan)
    _create(
        _admin_unor_recipients(pengajuan),
        pengajuan=pengajuan,
        event=Notification.Event.SUBMIT_UNOR,
        level=Notification.Level.INFO,
        title=f"Pengajuan Baru - {pengajuan.kode}",
        body=(
            f'Pegawai {nama} (NIP: {nip}) telah mengajukan {_jenis_surat(pengajuan)} '
            f'dengan perihal "{perihal}". Silakan lakukan verifikasi.'
        ),
        redirect_url=reverse("unor:preview", args=[pengajuan.kode]),
    )


def notify_resubmit_unor(pengajuan, catatan=""):
    """Event 2C: Pegawai mengirim ulang perbaikan ke Admin Unor, beserta
    catatan balasan pegawai."""
    nama = _nama_pegawai(pengajuan)
    perihal = _perihal(pengajuan)
    _create(
        _admin_unor_recipients(pengajuan),
        pengajuan=pengajuan,
        event=Notification.Event.RESUBMIT_UNOR,
        level=Notification.Level.INFO,
        title=f"Perbaikan Surat Diterima - {nama}",
        body=(
            f'Pegawai {nama} telah mengirimkan perbaikan surat perihal "{perihal}". '
            + (f'Catatan Pegawai: "{catatan}". ' if catatan else "")
            + "Silakan periksa kembali."
        ),
        redirect_url=reverse("unor:preview", args=[pengajuan.kode]),
    )


def notify_reject_unor(pengajuan, catatan):
    """Event 2B: Admin Unor mengembalikan pengajuan ke pegawai untuk revisi."""
    perihal = _perihal(pengajuan)
    jenis = _jenis_surat(pengajuan)
    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.REJECT_UNOR,
        level=Notification.Level.WARNING,
        title="Pengajuan Dikembalikan oleh Admin Unor",
        body=(
            f'{jenis[0].upper() + jenis[1:]} perihal "{perihal}" dikembalikan. '
            f'Catatan Unor: "{catatan}". Silakan lakukan perbaikan.'
        ),
        redirect_url=reverse("pegawai:upload_dokumen", args=[pengajuan.kode]),
    )


def notify_forward_bpsdm(pengajuan, catatan=""):
    """Event 4A/4B: Admin Unor meneruskan (ulang) PDLN Tipe 2 ke Admin
    BPSDM. Catatan balasan hanya untuk BPSDM, tidak ke pegawai."""
    nama = _nama_pegawai(pengajuan)
    perihal = _perihal(pengajuan)
    unit = _unit_organisasi(pengajuan)
    nama_unor = unit.name if unit else "-"
    _create(
        _admin_bpsdm_recipients(),
        pengajuan=pengajuan,
        event=Notification.Event.RESUBMIT_BPSDM if catatan else Notification.Event.FORWARD_BPSDM,
        level=Notification.Level.INFO,
        title=(f"Perbaikan Berkas dari Unor - {pengajuan.kode}" if catatan
               else f"Pengajuan {pengajuan.jenis_label} Baru - {pengajuan.kode}"),
        body=(
            f'Unor {nama_unor} meneruskan {pengajuan.jenis_label} atas nama {nama} perihal "{perihal}".'
            + (f' Catatan Unor: "{catatan}".' if catatan else "")
        ),
        redirect_url=reverse("bpsdm:preview", args=[pengajuan.kode]),
    )
    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.FORWARD_BPSDM,
        level=Notification.Level.SUCCESS,
        title="Pengajuan Diteruskan ke Admin BPSDM",
        body=f'Pengajuan Anda perihal "{perihal}" telah diteruskan Admin Unor ke Admin BPSDM.',
        redirect_url=_url_monitor(pengajuan),
    )


def notify_reject_bpsdm(pengajuan, catatan):
    """Event 4C: Admin BPSDM mengembalikan PDLN Tipe 2 ke Admin Unor."""
    nama = _nama_pegawai(pengajuan)
    perihal = _perihal(pengajuan)
    _create(
        _admin_unor_recipients(pengajuan),
        pengajuan=pengajuan,
        event=Notification.Event.REJECT_BPSDM_UNOR,
        level=Notification.Level.WARNING,
        title="Berkas Dikembalikan oleh Admin BPSDM",
        body=f'Pengajuan {nama} dikembalikan oleh BPSDM. Catatan BPSDM: "{catatan}". Mohon diperbaiki.',
        redirect_url=reverse("unor:preview", args=[pengajuan.kode]),
    )
    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.REJECT_BPSDM_UNOR,
        level=Notification.Level.INFO,
        title="Status Pengajuan (Dalam Penanganan Unor)",
        body=f'Pengajuan Anda perihal "{perihal}" membutuhkan penyesuaian dari Admin Unor.',
        redirect_url=_url_monitor(pengajuan),
    )


def notify_approve_unor(pengajuan, catatan="", dari_bpsdm=False):
    """Event 2A: pengajuan diteruskan ke Biro PAKLN — oleh Admin Unor, atau
    oleh Admin BPSDM untuk PDLN Tipe 2 (`dari_bpsdm`). `catatan` terisi
    bila ini penerusan ulang setelah dikembalikan PAKLN — hanya
    disampaikan ke Admin PAKLN, tidak ke pegawai."""
    perihal = _perihal(pengajuan)
    nama = _nama_pegawai(pengajuan)
    unit = _unit_organisasi(pengajuan)
    pengirim = "Admin BPSDM" if dari_bpsdm else f"Unor {unit.name if unit else '-'}"

    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.APPROVE_UNOR,
        level=Notification.Level.SUCCESS,
        title="Pengajuan Diteruskan ke Biro PAKLN" if dari_bpsdm else "Pengajuan Surat Disetujui Unor",
        body=(
            f'Surat Anda perihal "{perihal}" telah disetujui oleh '
            f'{"Admin BPSDM" if dari_bpsdm else "Admin Unor"} dan diteruskan ke Admin PKLN.'
        ),
        redirect_url=_url_monitor(pengajuan),
    )
    _create(
        _admin_pakln_recipients(),
        pengajuan=pengajuan,
        event=Notification.Event.APPROVE_UNOR,
        level=Notification.Level.INFO,
        title=(f"Perbaikan Berkas dari {pengirim} Diterima" if catatan
               else "Penugasan Verifikasi Surat PKLN Baru"),
        body=(
            f'{pengirim} telah mengirimkan perbaikan berkas atas nama {nama} '
            f'perihal "{perihal}". Catatan: "{catatan}".'
            if catatan else
            f'Diterima {_jenis_surat(pengajuan)} dari {pengirim} atas nama {nama} '
            f'perihal "{perihal}".'
        ),
        redirect_url=reverse("pakln:preview", args=[pengajuan.kode]),
    )


def notify_reject_pakln_to_unor(pengajuan, catatan):
    """Event 3B: Admin PKLN mengembalikan pengajuan ke tahap sebelumnya —
    Admin Unor, atau Admin BPSDM untuk PDLN Tipe 2."""
    nama = _nama_pegawai(pengajuan)
    perihal = _perihal(pengajuan)
    ke_bpsdm = getattr(pengajuan, "is_tipe2", False)
    penerima = _admin_bpsdm_recipients() if ke_bpsdm else _admin_unor_recipients(pengajuan)
    tujuan = "Admin BPSDM" if ke_bpsdm else "Admin Unor"

    _create(
        penerima,
        pengajuan=pengajuan,
        event=Notification.Event.REJECT_PKLN_UNOR,
        level=Notification.Level.WARNING,
        title="Berkas Surat Dikembalikan oleh Admin PKLN",
        body=(
            f'Surat pengajuan {nama} dikembalikan oleh PKLN. '
            f'Catatan PKLN: "{catatan}". Mohon diperbaiki.'
        ),
        redirect_url=reverse("bpsdm:preview" if ke_bpsdm else "unor:preview", args=[pengajuan.kode]),
    )
    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.REJECT_PKLN_UNOR,
        level=Notification.Level.INFO,
        title=f"Status Pengajuan Surat (Dalam Penanganan {tujuan})",
        body=f'Pengajuan surat Anda perihal "{perihal}" membutuhkan penyesuaian dari {tujuan}.',
        redirect_url=_url_monitor(pengajuan),
    )


def notify_complete_pkln(pengajuan):
    """Event 3A: Admin PKLN menyelesaikan/menerbitkan surat."""
    perihal = _perihal(pengajuan)
    nama = _nama_pegawai(pengajuan)
    lanjutan = (
        " Setelah perjalanan, unggah Laporan PDLN pada menu Pelaporan PDLN."
        if getattr(pengajuan, "is_pdln", False) else " Silakan unduh dokumen resmi."
    )

    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.COMPLETE_PKLN,
        level=Notification.Level.SUCCESS,
        title="Pengajuan Surat Selesai (Siap Unduh)",
        body=f'Selamat, surat Anda perihal "{perihal}" telah selesai diproses oleh Admin PKLN.{lanjutan}',
        redirect_url=_url_monitor(pengajuan),
    )
    _create(
        _admin_unor_recipients(pengajuan),
        pengajuan=pengajuan,
        event=Notification.Event.COMPLETE_PKLN,
        level=Notification.Level.SUCCESS,
        title="Proses Surat PKLN Selesai",
        body=(
            f'Pengajuan surat milik {nama} perihal "{perihal}" telah selesai '
            f"diproses oleh Admin PKLN."
        ),
        redirect_url=reverse("unor:preview", args=[pengajuan.kode]),
    )


# ---------------------------------------------------------------------------
# Laporan PDLN
# ---------------------------------------------------------------------------

def notify_laporan_diunggah(pengajuan, catatan=""):
    nama = _nama_pegawai(pengajuan)
    _create(
        _admin_pakln_recipients(),
        pengajuan=pengajuan,
        event=Notification.Event.LAPORAN_DIUNGGAH,
        level=Notification.Level.INFO,
        title=f"Laporan PDLN {'Diunggah Ulang' if catatan else 'Baru'} - {pengajuan.kode}",
        body=(
            f"{nama} mengunggah Laporan PDLN untuk {pengajuan.kode}. Mohon diverifikasi."
            + (f' Catatan perbaikan: "{catatan}".' if catatan else "")
        ),
        redirect_url=reverse("pakln:pelaporan"),
    )
    _create(
        _admin_unor_recipients(pengajuan),
        pengajuan=pengajuan,
        event=Notification.Event.LAPORAN_DIUNGGAH,
        level=Notification.Level.INFO,
        title=f"Laporan PDLN Diunggah - {pengajuan.kode}",
        body=f"{nama} telah mengunggah Laporan PDLN untuk {pengajuan.kode}.",
        redirect_url=reverse("unor:pelaporan"),
    )


def notify_laporan_dikembalikan(pengajuan, catatan):
    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.LAPORAN_DIKEMBALIKAN,
        level=Notification.Level.WARNING,
        title="Laporan PDLN Dikembalikan",
        body=f'Laporan PDLN {pengajuan.kode} dikembalikan Biro PAKLN. Catatan: "{catatan}". Mohon unggah ulang.',
        redirect_url=reverse("pegawai:pelaporan"),
    )


def notify_laporan_disetujui(pengajuan):
    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.LAPORAN_DISETUJUI,
        level=Notification.Level.SUCCESS,
        title="Laporan PDLN Disetujui",
        body=(
            f"Laporan PDLN {pengajuan.kode} telah disetujui. Pengajuan dinyatakan tuntas — "
            "Anda dapat mengajukan perjalanan baru."
        ),
        redirect_url=_url_monitor(pengajuan),
    )


# ---------------------------------------------------------------------------
# Pembatalan (mekanisme interim)
# ---------------------------------------------------------------------------

def notify_pembatalan_diajukan(permohonan):
    p = permohonan.pengajuan
    nama = _nama_pegawai(p)
    alasan = permohonan.alasan
    if permohonan.status == permohonan.Status.MENUNGGU_UNOR:
        _create(
            _admin_unor_recipients(p),
            pengajuan=p,
            event=Notification.Event.PEMBATALAN_DIAJUKAN,
            level=Notification.Level.WARNING,
            title=f"Permohonan Pembatalan - {p.kode}",
            body=f'{nama} mengajukan pembatalan {p.kode}. Alasan: "{alasan}". Mohon diputuskan.',
            redirect_url=reverse("unor:pembatalan"),
        )
    else:
        _create(
            _admin_pakln_recipients(),
            pengajuan=p,
            event=Notification.Event.PEMBATALAN_DIAJUKAN,
            level=Notification.Level.WARNING,
            title=f"Permohonan Pembatalan dari Admin Unor - {p.kode}",
            body=f'Admin Unor mengajukan pembatalan {p.kode} atas nama {nama}. Alasan: "{alasan}".',
            redirect_url=reverse("pakln:pembatalan"),
        )
        _create(
            [p.pegawai],
            pengajuan=p,
            event=Notification.Event.PEMBATALAN_DIAJUKAN,
            level=Notification.Level.WARNING,
            title="Admin Unor Mengajukan Pembatalan Perjalanan Anda",
            body=f'Pembatalan {p.kode} diajukan Admin Unor. Alasan: "{alasan}". Menunggu keputusan Biro PAKLN.',
            redirect_url=_url_monitor(p),
        )


def notify_pembatalan_menunggu_pakln(permohonan):
    p = permohonan.pengajuan
    _create(
        _admin_pakln_recipients(),
        pengajuan=p,
        event=Notification.Event.PEMBATALAN_MENUNGGU_PAKLN,
        level=Notification.Level.WARNING,
        title=f"Pembatalan Menunggu Keputusan - {p.kode}",
        body=f'Admin Unor menyetujui permohonan pembatalan {p.kode}. Alasan: "{permohonan.alasan}".',
        redirect_url=reverse("pakln:pembatalan"),
    )
    _create(
        [p.pegawai],
        pengajuan=p,
        event=Notification.Event.PEMBATALAN_MENUNGGU_PAKLN,
        level=Notification.Level.INFO,
        title="Pembatalan Disetujui Admin Unor",
        body=f"Permohonan pembatalan {p.kode} disetujui Admin Unor dan menunggu keputusan Biro PAKLN.",
        redirect_url=_url_monitor(p),
    )


def notify_pembatalan_ditolak(permohonan, catatan, oleh):
    p = permohonan.pengajuan
    penerima = list(_admin_unor_recipients(p)) if oleh == "pakln" else []
    penerima.append(p.pegawai)
    _create(
        penerima,
        pengajuan=p,
        event=Notification.Event.PEMBATALAN_DITOLAK,
        level=Notification.Level.WARNING,
        title=f"Permohonan Pembatalan Ditolak - {p.kode}",
        body=(
            f'Permohonan pembatalan {p.kode} ditolak {"Biro PAKLN" if oleh == "pakln" else "Admin Unor"}. '
            f'Catatan: "{catatan}". Proses pengajuan dilanjutkan.'
        ),
        redirect_url=_url_monitor(p),
    )


def notify_pembatalan_disetujui(permohonan):
    p = permohonan.pengajuan
    penerima = [p.pegawai, *_admin_unor_recipients(p)]
    if p.is_tipe2 and (p.tgl_masuk_bpsdm or permohonan.status_pengajuan_saat_diajukan == "proses_bpsdm"):
        penerima.extend(_admin_bpsdm_recipients())
    _create(
        penerima,
        pengajuan=p,
        event=Notification.Event.PEMBATALAN_DISETUJUI,
        level=Notification.Level.INFO,
        title=f"Perjalanan Dibatalkan - {p.kode}",
        body=f'Pembatalan {p.kode} disetujui Biro PAKLN. Alasan: "{permohonan.alasan}".',
        redirect_url=_url_monitor(p),
    )


def notify_pembatalan_ditarik(permohonan, status_sebelumnya):
    p = permohonan.pengajuan
    if status_sebelumnya == permohonan.Status.MENUNGGU_UNOR:
        penerima, url = _admin_unor_recipients(p), reverse("unor:pembatalan")
    else:
        penerima, url = _admin_pakln_recipients(), reverse("pakln:pembatalan")
    _create(
        penerima,
        pengajuan=p,
        event=Notification.Event.PEMBATALAN_DITARIK,
        level=Notification.Level.INFO,
        title=f"Permohonan Pembatalan Ditarik - {p.kode}",
        body=f"Permohonan pembatalan {p.kode} ditarik oleh pengaju. Proses pengajuan dilanjutkan.",
        redirect_url=url,
    )
