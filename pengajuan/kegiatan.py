"""
Layanan Kegiatan PDLN — wiki/instructions/EVENT_IMPLEMENTATION_PLAN.MD.

- `simpan`      : simpan form Kegiatan + formset dasar (B15) dalam satu transaksi.
- `usulkan`     : Pegawai / Admin BPSDM mengusulkan kegiatan (status menunggu, B10/B10a).
- `setujui`     : Admin Biro PAKLN menyetujui usulan (B11).
- `tolak`       : Admin Biro PAKLN menolak usulan dengan catatan wajib (B11).
- `snapshot`    : salin data kegiatan ke DetailPdln (B13).
- `mirip`       : kegiatan serupa untuk mencegah duplikat saat mengusulkan.
"""

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User
from notifications import services as notif
from paspor.models import Kegiatan

from .models import DetailPdln, Pengajuan

K = Kegiatan.Status

SUMBER_USULAN = {
    User.Role.PEGAWAI: Kegiatan.SumberData.USULAN_PEGAWAI,
    User.Role.ADMIN_BPSDM: Kegiatan.SumberData.USULAN_BPSDM,
}


class KegiatanError(Exception):
    pass


def simpan(form, formset, user):
    """Simpan Kegiatan dari `form` beserta dasar dari `formset` (keduanya
    sudah valid). Mengembalikan objek Kegiatan."""
    with transaction.atomic():
        kegiatan = form.save()
        formset.instance = kegiatan
        for dasar in formset.save(commit=False):
            if not dasar.pk:
                dasar.ditambahkan_oleh = user
            dasar.save()
        for dasar in formset.deleted_objects:
            if dasar.berkas:
                dasar.berkas.delete(save=False)
            dasar.delete()
    return kegiatan


def usulkan(form, formset, user):
    """Pegawai / Admin BPSDM mengusulkan kegiatan baru — belum dapat dipilih
    sebelum disetujui Admin Biro PAKLN."""
    kegiatan = form.instance
    kegiatan.status = K.MENUNGGU
    kegiatan.sumber_data = SUMBER_USULAN[user.role]
    kegiatan.diusulkan_oleh = user
    kegiatan = simpan(form, formset, user)
    notif.notify_kegiatan_diusulkan(kegiatan)
    return kegiatan


def _kunci(kegiatan):
    return Kegiatan.objects.select_for_update().get(pk=kegiatan.pk)


def setujui(kegiatan, user, catatan=""):
    with transaction.atomic():
        k = _kunci(kegiatan)
        if k.status != K.MENUNGGU:
            raise KegiatanError("Usulan kegiatan ini sudah diputus.")
        k.status = K.DISETUJUI
        k.diputus_oleh = user
        k.tgl_diputus = timezone.now()
        k.catatan_keputusan = catatan.strip()
        k.save(update_fields=["status", "diputus_oleh", "tgl_diputus", "catatan_keputusan", "updated_at"])
    notif.notify_kegiatan_disetujui(k)
    return k


def tolak(kegiatan, user, catatan):
    catatan = (catatan or "").strip()
    if not catatan:
        raise KegiatanError("Isi catatan penolakan untuk pengusul.")
    with transaction.atomic():
        k = _kunci(kegiatan)
        if k.status != K.MENUNGGU:
            raise KegiatanError("Usulan kegiatan ini sudah diputus.")
        k.status = K.DITOLAK
        k.diputus_oleh = user
        k.tgl_diputus = timezone.now()
        k.catatan_keputusan = catatan
        k.save(update_fields=["status", "diputus_oleh", "tgl_diputus", "catatan_keputusan", "updated_at"])
    notif.notify_kegiatan_ditolak(k)
    return k


def boleh_disunting_pengusul(kegiatan, user):
    """Pengusul (Admin BPSDM) hanya boleh menyunting usulannya sendiri
    selama masih menunggu persetujuan (§14.2 #12)."""
    return kegiatan.status == K.MENUNGGU and kegiatan.diusulkan_oleh_id == user.pk


def snapshot(pengajuan):
    """Salin data kegiatan pengajuan ke DetailPdln (B13). Dipanggil saat
    formulir disimpan dan saat pengajuan dikirim ke Admin Unor; setelah
    dikirim, perubahan Kegiatan tidak lagi mengubah pengajuan."""
    kegiatan = pengajuan.kegiatan
    detail, _ = DetailPdln.objects.get_or_create(pengajuan=pengajuan)
    if kegiatan is None:
        return detail
    pendidikan = pengajuan.tipe_pdln == Pengajuan.TipePdln.T2P
    detail.kegiatan_nama = kegiatan.nama[:255]
    detail.kegiatan_tahun = kegiatan.tahun_pelaksanaan
    detail.penyelenggara = "" if pendidikan else kegiatan.penyelenggara[:200]
    detail.perguruan_tinggi = kegiatan.penyelenggara[:200] if pendidikan else ""
    detail.kota_tujuan = kegiatan.kota[:150]
    detail.tgl_mulai_kegiatan = kegiatan.tgl_mulai
    detail.tgl_selesai_kegiatan = kegiatan.tgl_selesai
    detail.save()
    return detail


def mirip(nama, tahun=None, kecuali=None, batas=5):
    """Kegiatan disetujui/menunggu yang namanya mirip (setiap kata ≥ 4 huruf
    yang sama), untuk peringatan duplikat (§7.1)."""
    kata = [w for w in (nama or "").split() if len(w) >= 4][:5]
    if not kata:
        return Kegiatan.objects.none()
    q = Q()
    for w in kata:
        q |= Q(nama__icontains=w)
    qs = Kegiatan.objects.filter(q).exclude(status=K.DITOLAK)
    if tahun:
        qs = qs.filter(tahun_pelaksanaan=tahun)
    if kecuali:
        qs = qs.exclude(pk=kecuali)
    return qs.order_by("-tgl_mulai")[:batas]


def dengan_jumlah_peserta(qs):
    return qs.annotate(jumlah_peserta=Count("pengajuan_list", distinct=True))
