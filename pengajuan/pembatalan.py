"""
Pembatalan perjalanan — mekanisme interim (wiki/instructions/
BISNIS_PROSES_PDLN.MD §4.5). Sengaja dipisahkan dari alur utama agar mudah
diganti saat rumusan resmi pembatalan tersedia.

    Pegawai    ──ajukan──► menunggu_unor ──Admin Unor setuju──► menunggu_pakln ──Admin PAKLN setuju──► disetujui
    Admin Unor ──ajukan──────────────────────────────────────► menunggu_pakln
    tolak (catatan wajib) → ditolak · pengaju menarik → ditarik

Selama permohonan terbuka, aksi alur utama dibekukan (`alur.alasan_dibekukan`).
Disetujui ⇒ `Pengajuan.status = dibatalkan` (tuntas).
"""

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from notifications import services as notif

from . import alur, riwayat
from .models import Pengajuan, PermohonanPembatalan, RiwayatPengajuan

Aksi = RiwayatPengajuan.Aksi
P = PermohonanPembatalan.Status


class PembatalanError(Exception):
    """Aksi pembatalan tidak dapat dilakukan — pesan untuk pengguna."""


def _belum_lewat_batas(pengajuan):
    """Batas waktu untuk pengajuan yang sudah `selesai` (§14 #6, default):
    Non-Dinas sampai tanggal berangkat; PDLN selama laporan belum disetujui."""
    if pengajuan.status != Pengajuan.Status.SELESAI:
        return True
    if pengajuan.is_pdln:
        return not pengajuan.tuntas
    return bool(pengajuan.tgl_berangkat and timezone.localdate() <= pengajuan.tgl_berangkat)


def alasan_tidak_bisa(pengajuan, user):
    """'' bila `user` boleh mengajukan pembatalan untuk pengajuan ini,
    selain itu kalimat alasannya. Cakupan unor/kepemilikan diperiksa view."""
    if user.role not in (User.Role.PEGAWAI, User.Role.ADMIN_UNOR):
        return "Hanya Pegawai atau Admin Unor yang dapat mengajukan pembatalan."
    if pengajuan.status == Pengajuan.Status.DIBATALKAN:
        return "Pengajuan sudah dibatalkan."
    if not pengajuan.pernah_dikirim:
        if user.role == User.Role.PEGAWAI:
            return ""  # draft — dibatalkan langsung (batalkan_draft)
        return "Pengajuan belum pernah dikirim pegawai."
    if pengajuan.tuntas:
        return "Pengajuan sudah tuntas."
    if not _belum_lewat_batas(pengajuan):
        return "Batas waktu pembatalan sudah lewat (tanggal keberangkatan telah terlampaui)."
    if pengajuan.pembatalan_terbuka:
        return "Sudah ada permohonan pembatalan yang sedang diproses."
    return ""


def bisa_diajukan(pengajuan, user):
    return not alasan_tidak_bisa(pengajuan, user)


def _wajib(teks, pesan):
    teks = (teks or "").strip()
    if not teks:
        raise PembatalanError(pesan)
    return teks


def batalkan_draft(pengajuan, user, alasan):
    """Draft yang belum pernah dikirim dibatalkan langsung oleh pemiliknya
    (tanpa persetujuan)."""
    alasan = _wajib(alasan, "Isi alasan pembatalan.")
    with transaction.atomic():
        p = alur.kunci(pengajuan)
        if p.pegawai_id != user.pk or p.pernah_dikirim or p.status != Pengajuan.Status.BELUM:
            raise PembatalanError("Draft ini tidak dapat dibatalkan langsung.")
        status_dari = p.status
        p.status = Pengajuan.Status.DIBATALKAN
        p.tgl_dibatalkan = timezone.localdate()
        p.save(update_fields=["status", "tgl_dibatalkan", "updated_at"])
        riwayat.catat(p, Aksi.DIBATALKAN, user, status_dari, catatan=alasan)
    return p


def ajukan(pengajuan, user, alasan):
    alasan = _wajib(alasan, "Alasan pembatalan wajib diisi.")
    if not pengajuan.pernah_dikirim and user.role == User.Role.PEGAWAI:
        batalkan_draft(pengajuan, user, alasan)
        return None
    with transaction.atomic():
        p = alur.kunci(pengajuan)
        pesan = alasan_tidak_bisa(p, user)
        if pesan:
            raise PembatalanError(pesan)
        sekarang = timezone.now()
        oleh_unor = user.role == User.Role.ADMIN_UNOR
        permohonan = PermohonanPembatalan.objects.create(
            pengajuan=p,
            diajukan_oleh=user,
            diajukan_role=user.role,
            alasan=alasan,
            status=P.MENUNGGU_PAKLN if oleh_unor else P.MENUNGGU_UNOR,
            status_pengajuan_saat_diajukan=p.status,
            unor_oleh=user if oleh_unor else None,
            unor_waktu=sekarang if oleh_unor else None,
            unor_catatan="Diajukan oleh Admin Unor." if oleh_unor else "",
        )
        riwayat.catat(p, Aksi.PEMBATALAN_DIAJUKAN, user, p.status, catatan=alasan)
    notif.notify_pembatalan_diajukan(permohonan)
    return permohonan


def putuskan(permohonan, user, setuju, catatan=""):
    """Keputusan jenjang Unor (status menunggu_unor) atau jenjang akhir
    PAKLN (menunggu_pakln). Menolak wajib disertai catatan."""
    catatan = (catatan or "").strip()
    if not setuju and not catatan:
        raise PembatalanError("Catatan wajib diisi bila menolak permohonan pembatalan.")

    with transaction.atomic():
        p = alur.kunci(permohonan.pengajuan)
        permohonan = PermohonanPembatalan.objects.select_for_update().get(pk=permohonan.pk)
        sekarang = timezone.now()

        if user.role == User.Role.ADMIN_UNOR:
            if permohonan.status != P.MENUNGGU_UNOR:
                raise PembatalanError("Permohonan ini tidak sedang menunggu keputusan Admin Unor.")
            permohonan.unor_oleh, permohonan.unor_waktu, permohonan.unor_catatan = user, sekarang, catatan
            if setuju:
                permohonan.status = P.MENUNGGU_PAKLN
                riwayat.catat(p, Aksi.PEMBATALAN_DISETUJUI_UNOR, user, p.status, catatan=catatan)
            else:
                permohonan.status = P.DITOLAK
                riwayat.catat(p, Aksi.PEMBATALAN_DITOLAK_UNOR, user, p.status, catatan=catatan)
        elif user.role == User.Role.ADMIN_PAKLN:
            if permohonan.status != P.MENUNGGU_PAKLN:
                raise PembatalanError("Permohonan ini tidak sedang menunggu keputusan Biro PAKLN.")
            permohonan.pakln_oleh, permohonan.pakln_waktu, permohonan.pakln_catatan = user, sekarang, catatan
            if setuju:
                permohonan.status = P.DISETUJUI
                status_dari = p.status
                p.status = Pengajuan.Status.DIBATALKAN
                p.tgl_dibatalkan = timezone.localdate()
                p.save(update_fields=["status", "tgl_dibatalkan", "updated_at"])
                riwayat.catat(p, Aksi.DIBATALKAN, user, status_dari, catatan=catatan or permohonan.alasan)
            else:
                permohonan.status = P.DITOLAK
                riwayat.catat(p, Aksi.PEMBATALAN_DITOLAK_PAKLN, user, p.status, catatan=catatan)
        else:
            raise PembatalanError("Anda tidak berwenang memutuskan permohonan pembatalan.")
        permohonan.save()

    if permohonan.status == P.MENUNGGU_PAKLN:
        notif.notify_pembatalan_menunggu_pakln(permohonan)
    elif permohonan.status == P.DITOLAK:
        notif.notify_pembatalan_ditolak(permohonan, catatan, "unor" if user.role == User.Role.ADMIN_UNOR else "pakln")
    elif permohonan.status == P.DISETUJUI:
        notif.notify_pembatalan_disetujui(permohonan)
    return permohonan


def tarik(permohonan, user):
    with transaction.atomic():
        p = alur.kunci(permohonan.pengajuan)
        permohonan = PermohonanPembatalan.objects.select_for_update().get(pk=permohonan.pk)
        if permohonan.diajukan_oleh_id != user.pk:
            raise PembatalanError("Hanya pengaju yang dapat menarik permohonan ini.")
        if not permohonan.terbuka:
            raise PembatalanError("Permohonan sudah diputus dan tidak dapat ditarik.")
        status_sebelumnya = permohonan.status
        permohonan.status = P.DITARIK
        permohonan.save(update_fields=["status", "updated_at"])
        riwayat.catat(p, Aksi.PEMBATALAN_DITARIK, user, p.status)
    notif.notify_pembatalan_ditarik(permohonan, status_sebelumnya)
    return permohonan
