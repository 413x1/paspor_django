"""
Track paralel Admin BKO — SK Tugas Belajar PDLN Tipe 2 Pendidikan (T2P),
lihat wiki/instructions/PDLN_TIPE_2_FLOW.MD §8.

Track BKO bukan bagian `Pengajuan.status`: dibuka saat Admin BPSDM
meneruskan ke Biro PAKLN, lalu berjalan di `Pengajuan.status_bko`:

    menunggu ──unggah──► diunggah        (hapus SK Tubel → menunggu)
    menunggu ──tutup───► ditutup ──buka kembali──► menunggu

Semua perubahan `status_bko` lewat modul ini (row lock `alur.kunci`).
Notifikasi dikirim setelah transaksi selesai.
"""

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from notifications import services as notif

from . import alur, riwayat
from .models import Pengajuan, RiwayatPengajuan

S = Pengajuan.Status
SB = Pengajuan.StatusBko
Aksi = RiwayatPengajuan.Aksi

_ROLE_BUKA_KEMBALI = {User.Role.ADMIN_BKO, User.Role.ADMIN_PAKLN}


class BkoError(Exception):
    """Aksi track BKO ditolak — pesan siap tampil ke pengguna."""


def _wajib(teks, pesan):
    teks = (teks or "").strip()
    if not teks:
        raise BkoError(pesan)
    return teks


def alasan_tidak_bisa_ubah(pengajuan):
    """'' bila track BKO pengajuan ini masih boleh diubah (unggah, hapus,
    tutup, buka kembali), selain itu kalimat alasannya."""
    if not pengajuan.track_bko_terbuka:
        return "Pengajuan ini tidak sedang menunggu proses Admin BKO."
    if pengajuan.status in (S.SELESAI, S.DIBATALKAN):
        return f"Pengajuan {pengajuan.kode} sudah {pengajuan.get_status_display().lower()}."
    return alur.alasan_dibekukan(pengajuan)


def bisa_diubah(pengajuan):
    return not alasan_tidak_bisa_ubah(pengajuan)


def alasan_tidak_bisa_selesai(pengajuan):
    """'' bila Biro PAKLN boleh menekan Selesai normal; selain itu alasan
    yang berasal dari track BKO. Selalu '' untuk selain T2P."""
    if not pengajuan.pakai_bko:
        return ""
    if pengajuan.status_bko == SB.DIUNGGAH:
        return ""
    if pengajuan.status_bko == SB.DITUTUP:
        return f"Pemrosesan ditutup Admin BKO: {pengajuan.catatan_bko}"
    return "Menunggu SK Tugas Belajar dari Admin BKO."


def _kunci_dan_cek(pengajuan, status_bko_diizinkan):
    p = alur.kunci(pengajuan)
    pesan = alasan_tidak_bisa_ubah(p)
    if pesan:
        raise BkoError(pesan)
    if p.status_bko not in status_bko_diizinkan:
        raise BkoError("Status pemrosesan BKO sudah berubah. Muat ulang halaman.")
    return p


def buka_track(pengajuan, aktor):
    """Dipanggil Admin BPSDM saat meneruskan ke Biro PAKLN, di dalam
    transaksi & lock yang sama. Mengembalikan True bila track baru dibuka
    (penerusan pertama), False bila sudah terbuka atau bukan T2P."""
    if not pengajuan.pakai_bko or pengajuan.status_bko:
        return False
    pengajuan.tgl_masuk_bko = timezone.localdate()
    pengajuan.status_bko = SB.MENUNGGU
    pengajuan.save(update_fields=["tgl_masuk_bko", "status_bko", "updated_at"])
    riwayat.catat(pengajuan, Aksi.DITERUSKAN_BKO, aktor, pengajuan.status)
    return True


def setelah_unggah(pengajuan, aktor):
    """SK Tubel baru saja diunggah/diganti lewat `tahap.proses_unggah`."""
    with transaction.atomic():
        p = _kunci_dan_cek(pengajuan, (SB.MENUNGGU, SB.DIUNGGAH))
        p.status_bko = SB.DIUNGGAH
        p.save(update_fields=["status_bko", "updated_at"])
        riwayat.catat(p, Aksi.SK_TUBEL_DIUNGGAH, aktor, p.status)
    notif.notify_sk_tubel_diunggah(p)
    return p


def setelah_hapus(pengajuan):
    """SK Tubel baru saja dihapus Admin BKO — kembali menunggu."""
    with transaction.atomic():
        p = alur.kunci(pengajuan)
        if p.status_bko == SB.DIUNGGAH and not p.dokumen_bko.exists():
            p.status_bko = SB.MENUNGGU
            p.save(update_fields=["status_bko", "updated_at"])
    return p


def tutup(pengajuan, aktor, catatan):
    """Admin BKO menutup pemrosesan karena SK Tubel tidak dapat diterbitkan."""
    if aktor.role != User.Role.ADMIN_BKO:
        raise BkoError("Hanya Admin BKO yang dapat menutup pemrosesan BKO.")
    catatan = _wajib(catatan, "Isi alasan penutupan pemrosesan.")
    with transaction.atomic():
        p = _kunci_dan_cek(pengajuan, (SB.MENUNGGU,))
        p.status_bko = SB.DITUTUP
        p.catatan_bko = catatan
        p.tgl_bko_ditutup = timezone.localdate()
        p.save(update_fields=["status_bko", "catatan_bko", "tgl_bko_ditutup", "updated_at"])
        riwayat.catat(p, Aksi.DITUTUP_BKO, aktor, p.status, catatan=catatan)
    notif.notify_bko_ditutup(p, catatan)
    return p


def buka_kembali(pengajuan, aktor, catatan):
    """Admin BKO atau Admin Biro PAKLN membuka kembali track yang ditutup."""
    if aktor.role not in _ROLE_BUKA_KEMBALI:
        raise BkoError("Hanya Admin BKO atau Admin Biro PAKLN yang dapat membuka kembali pemrosesan BKO.")
    catatan = _wajib(catatan, "Isi catatan pembukaan kembali.")
    with transaction.atomic():
        p = _kunci_dan_cek(pengajuan, (SB.DITUTUP,))
        p.status_bko = SB.MENUNGGU
        p.catatan_bko = ""
        p.tgl_bko_ditutup = None
        p.save(update_fields=["status_bko", "catatan_bko", "tgl_bko_ditutup", "updated_at"])
        riwayat.catat(p, Aksi.DIBUKA_ULANG_BKO, aktor, p.status, catatan=catatan)
    notif.notify_bko_dibuka(p, catatan, aktor.role)
    return p


def keterangan_timeline(pengajuan):
    """(teks, tone) sub-keterangan track BKO pada Timeline Proses, atau
    (None, None) bila tidak relevan."""
    if not pengajuan.track_bko_terbuka:
        return None, None
    if pengajuan.status_bko == SB.DITUTUP:
        tgl = f" ({pengajuan.tgl_bko_ditutup:%d %b %Y})" if pengajuan.tgl_bko_ditutup else ""
        return f"Pemrosesan ditutup Admin BKO{tgl}: {pengajuan.catatan_bko}", "warning"
    if pengajuan.status_bko == SB.DIUNGGAH:
        dok = pengajuan.dokumen_bko.first()
        tgl = f" {timezone.localtime(dok.uploaded_at):%d %b %Y}" if dok else ""
        return f"SK Tugas Belajar (Admin BKO): Diunggah{tgl}", "success"
    return "SK Tugas Belajar (Admin BKO): Menunggu", "info"
