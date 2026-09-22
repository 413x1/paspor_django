"""
Pembuatan notifikasi untuk tiap trigger pada modul Pengajuan Surat, sesuai
wiki/instructions/SKENARIO_NOTIFIKASI_SURAT.md.

Hanya event yang punya pemicu (trigger) nyata pada alur yang sudah
diimplementasikan yang dipasang di sini:
    Event 1  (NOTIF_01_SUBMIT_UNOR)    — pegawai mengirim pengajuan ke Unor
    Event 2A (NOTIF_02A_APPROVE_UNOR)  — Unor menyetujui & meneruskan ke PKLN
    Event 2B (NOTIF_02B_REJECT_UNOR)   — Unor mengembalikan ke pegawai
    Event 2C (NOTIF_02C_RESUBMIT_UNOR) — pegawai mengirim ulang perbaikan
    Event 3A (NOTIF_03A_COMPLETE_PKLN) — PKLN menyelesaikan/menerbitkan surat

Event 2B/3B/3C/3D/4 lain pada dokumen (kembalikan PKLN ke Unor/Pegawai,
resubmit ke PKLN, tolak permanen) belum punya aksi/status pada aplikasi ini
sehingga belum dipasang.
"""

from django.urls import reverse

from .models import Notification

JENIS_SURAT = "Surat Izin Perjalanan Luar Negeri Non-Kedinasan"


def _profile(pengajuan):
    return getattr(pengajuan.pegawai, "profile", None)


def _nama_pegawai(pengajuan):
    profile = _profile(pengajuan)
    return (profile.nama if profile else None) or pengajuan.pegawai.get_full_name() or pengajuan.pegawai.username


def _nip_pegawai(pengajuan):
    profile = _profile(pengajuan)
    return profile.nip if profile else "-"


def _unit_organisasi(pengajuan):
    profile = _profile(pengajuan)
    return profile.unit_organisasi if profile else None


def _perihal(pengajuan):
    return pengajuan.maksud or pengajuan.get_kategori_display() or "-"


def _admin_unor_recipients(pengajuan):
    from accounts.models import User

    unit = _unit_organisasi(pengajuan)
    if not unit:
        return User.objects.none()
    return User.objects.filter(role=User.Role.ADMIN_UNOR, unit_organisasi_id=unit.id, is_active=True)


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
        title=f"Pengajuan Surat Baru - {pengajuan.kode}",
        body=(
            f'Pegawai {nama} (NIP: {nip}) telah mengajukan {JENIS_SURAT} '
            f'dengan perihal "{perihal}". Silakan lakukan verifikasi.'
        ),
        redirect_url=reverse("unor:preview", args=[pengajuan.kode]),
    )


def notify_resubmit_unor(pengajuan):
    """Event 2C: Pegawai mengirim ulang perbaikan surat ke Admin Unor."""
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
            f"Silakan periksa kembali."
        ),
        redirect_url=reverse("unor:preview", args=[pengajuan.kode]),
    )


def notify_reject_unor(pengajuan, catatan):
    """Event 2B: Admin Unor mengembalikan pengajuan ke pegawai untuk revisi."""
    perihal = _perihal(pengajuan)
    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.REJECT_UNOR,
        level=Notification.Level.WARNING,
        title="Pengajuan Surat Dikembalikan oleh Admin Unor",
        body=(
            f'{JENIS_SURAT} perihal "{perihal}" dikembalikan. '
            f'Catatan Unor: "{catatan}". Silakan lakukan perbaikan.'
        ),
        redirect_url=reverse("pegawai:upload_dokumen", args=[pengajuan.kode]),
    )


def notify_approve_unor(pengajuan):
    """Event 2A: Admin Unor menyetujui & meneruskan ke Admin PKLN."""
    perihal = _perihal(pengajuan)
    nama = _nama_pegawai(pengajuan)
    unit = _unit_organisasi(pengajuan)
    nama_unor = unit.name if unit else "-"

    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.APPROVE_UNOR,
        level=Notification.Level.SUCCESS,
        title="Pengajuan Surat Disetujui Unor",
        body=(
            f'Surat Anda perihal "{perihal}" telah disetujui oleh Admin Unor '
            f"dan diteruskan ke Admin PKLN."
        ),
        redirect_url=reverse("pegawai:monitor_progres", args=[pengajuan.kode]),
    )
    _create(
        _admin_pakln_recipients(),
        pengajuan=pengajuan,
        event=Notification.Event.APPROVE_UNOR,
        level=Notification.Level.INFO,
        title="Penugasan Verifikasi Surat PKLN Baru",
        body=(
            f'Diterima pengajuan surat dari Unor {nama_unor} atas nama {nama} '
            f'perihal "{perihal}".'
        ),
        redirect_url=reverse("pakln:preview", args=[pengajuan.kode]),
    )


def notify_complete_pkln(pengajuan):
    """Event 3A: Admin PKLN menyelesaikan/menerbitkan surat."""
    perihal = _perihal(pengajuan)
    nama = _nama_pegawai(pengajuan)

    _create(
        [pengajuan.pegawai],
        pengajuan=pengajuan,
        event=Notification.Event.COMPLETE_PKLN,
        level=Notification.Level.SUCCESS,
        title="Pengajuan Surat Selesai (Siap Unduh)",
        body=(
            f'Selamat, surat Anda perihal "{perihal}" telah selesai diproses oleh '
            f"Admin PKLN. Silakan unduh dokumen resmi."
        ),
        redirect_url=reverse("pegawai:monitor_progres", args=[pengajuan.kode]),
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
