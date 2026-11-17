"""
Jalur paralel Surat Tugas Pimpinan Unor — PDLN Tipe 2 (T2P dan T2L), lihat
wiki/instructions/RANCANGAN_UPDATE_AJUAN_TP2_PENDIDIKAN_TP2_PELATIHAN.md.

Surat Tugas bukan bagian `Pengajuan.status`: jalurnya dibuka saat Admin BPSDM pertama kali
mengunggah Izin Prinsip Menteri, lalu berjalan di `Pengajuan.status_surat_tugas`:

    (kosong) ──Izin Prinsip diunggah──► menunggu ──Admin Unor kirim──► dikirim
                                                                          │
                              dikembalikan ◄──Biro PAKLN kembalikan───────┘
                                   │
                                   └──Admin Unor kirim ulang──► dikirim

Pengunggah tetap Admin Unor dan berkasnya tetap `DokumenUnor` jenis `surat_tugas`. Admin BPSDM tidak
menunggu jalur ini; yang menunggu adalah Biro PAKLN (unggah dokumen PAKLN dan Selesai terkunci
selama Surat Tugas belum `dikirim`).

Semua perubahan `status_surat_tugas` lewat modul ini (row lock `alur.kunci`), pola yang sama dengan `bko.py`.
Notifikasi dikirim setelah transaksi selesai: `kirim` -> Admin Biro PAKLN, `kembalikan` -> Admin Unor. Notifikasi
pembukaan jalur (ke Admin Unor) dikirim oleh view BPSDM setelah transaksi unggah Izin Prinsip, seperti track BKO.
"""

from django.db import transaction
from django.utils import timezone
from django.utils.formats import date_format

from accounts.models import User
from notifications import services as notif

from . import alur, riwayat
from .decorators import PESAN_PENGAJUAN_SENDIRI, pengajuan_milik_sendiri
from .models import DokumenUnor, Pengajuan, RiwayatPengajuan

S = Pengajuan.Status
SS = Pengajuan.StatusSuratTugas
Aksi = RiwayatPengajuan.Aksi

# Jalur hanya bisa diubah selama pengajuan berada di tahap BPSDM atau Biro PAKLN.
STATUS_JALUR_AKTIF = (S.PROSES_BPSDM, S.PROSES_PAKLN)


class SuratTugasError(Exception):
    """Aksi jalur Surat Tugas ditolak — pesan siap tampil ke pengguna."""


def _wajib(teks, pesan):
    teks = (teks or "").strip()
    if not teks:
        raise SuratTugasError(pesan)
    return teks


# ---------------------------------------------------------------------------
# Pemeriksaan (tanpa efek samping) — dipakai view/template untuk mengunci tombol
# ---------------------------------------------------------------------------

def alasan_tidak_bisa_ubah(pengajuan):
    """'' bila jalur Surat Tugas pengajuan ini masih boleh diubah (unggah, kirim, kembalikan),
    selain itu kalimat alasannya."""
    if not pengajuan.pakai_surat_tugas_paralel:
        return "Jalur Surat Tugas hanya berlaku untuk PDLN Tipe 2."
    if not pengajuan.track_surat_tugas_terbuka:
        return "Surat Tugas baru dapat diproses setelah Admin BPSDM mengunggah Izin Prinsip Menteri."
    if pengajuan.status in (S.SELESAI, S.DIBATALKAN):
        return f"Pengajuan {pengajuan.kode} sudah {pengajuan.get_status_display().lower()}."
    if pengajuan.status not in STATUS_JALUR_AKTIF:
        return "Surat Tugas hanya dapat diproses selama pengajuan berada di tahap BPSDM atau Biro PAKLN."
    return alur.alasan_dibekukan(pengajuan)


def alasan_berkas_terkunci(pengajuan):
    """'' bila Admin Unor boleh mengunggah, mengganti, atau menghapus berkas Surat Tugas; selain itu alasannya.
    Berkas terkunci setelah `dikirim` dan terbuka lagi hanya bila dikembalikan Biro PAKLN."""
    pesan = alasan_tidak_bisa_ubah(pengajuan)
    if pesan:
        return pesan
    if pengajuan.status_surat_tugas == SS.DIKIRIM:
        return "Surat Tugas sudah dikirim ke Biro PAKLN dan terkunci, kecuali dikembalikan."
    return ""


def alasan_menunggu_surat_tugas(pengajuan):
    """'' bila Biro PAKLN boleh mengunggah/menghapus dokumen PAKLN dan menekan Selesai
    (Surat Tugas sudah dikirim dan tidak sedang dikembalikan); selain itu alasannya.
    Selalu '' untuk pengajuan di luar PDLN Tipe 2."""
    if not pengajuan.pakai_surat_tugas_paralel:
        return ""
    if pengajuan.status_surat_tugas == SS.DIKIRIM:
        return ""
    if pengajuan.status_surat_tugas == SS.DIKEMBALIKAN:
        catatan = (pengajuan.catatan_surat_tugas or "").strip().rstrip(".")
        return (f"Surat Tugas dikembalikan ke Admin Unor: {catatan}. "
                "Dokumen PAKLN terbuka lagi setelah Surat Tugas dikirim ulang.")
    return "Menunggu Surat Tugas Pimpinan Unor dikirim. Berkas hanya dapat ditinjau."


# ---------------------------------------------------------------------------
# Perubahan status
# ---------------------------------------------------------------------------

def _kunci_dan_cek(pengajuan, status_diizinkan):
    p = alur.kunci(pengajuan)
    pesan = alasan_tidak_bisa_ubah(p)
    if pesan:
        raise SuratTugasError(pesan)
    if p.status_surat_tugas not in status_diizinkan:
        raise SuratTugasError("Status Surat Tugas sudah berubah. Muat ulang halaman.")
    return p


def _cek_bukan_milik_sendiri(aktor, pengajuan):
    if pengajuan_milik_sendiri(aktor, pengajuan):
        raise SuratTugasError(PESAN_PENGAJUAN_SENDIRI)


def buka_jalur(pengajuan):
    """Dipanggil saat Admin BPSDM mengunggah Izin Prinsip Menteri, di dalam transaksi & lock yang sama.
    Mengembalikan True bila jalur baru dibuka (Izin Prinsip pertama), False bila sudah terbuka/sudah berisi
    status (mis. hasil migrasi data) atau bukan PDLN Tipe 2. Mengganti Izin Prinsip tidak membuka ulang."""
    if not pengajuan.pakai_surat_tugas_paralel or pengajuan.status_surat_tugas:
        return False
    pengajuan.status_surat_tugas = SS.MENUNGGU
    pengajuan.save(update_fields=["status_surat_tugas", "updated_at"])
    return True


def kirim(pengajuan, aktor):
    """Admin Unor mengirim Surat Tugas ke Biro PAKLN (pertama kali atau kirim ulang setelah dikembalikan)."""
    if aktor.role != User.Role.ADMIN_UNOR:
        raise SuratTugasError("Hanya Admin Unor yang dapat mengirim Surat Tugas.")
    _cek_bukan_milik_sendiri(aktor, pengajuan)
    with transaction.atomic():
        p = _kunci_dan_cek(pengajuan, (SS.MENUNGGU, SS.DIKEMBALIKAN))
        if not DokumenUnor.objects.filter(pengajuan=p, jenis="surat_tugas").exists():
            raise SuratTugasError("Unggah berkas Surat Tugas terlebih dahulu sebelum mengirim.")
        p.status_surat_tugas = SS.DIKIRIM
        p.catatan_surat_tugas = ""
        p.save(update_fields=["status_surat_tugas", "catatan_surat_tugas", "updated_at"])
        riwayat.catat(p, Aksi.SURAT_TUGAS_DIKIRIM, aktor, p.status)
    notif.notify_surat_tugas_dikirim(p)
    return p


def kembalikan(pengajuan, aktor, catatan):
    """Admin Biro PAKLN mengembalikan Surat Tugas ke Admin Unor. Status pengajuan tidak berubah."""
    if aktor.role != User.Role.ADMIN_PAKLN:
        raise SuratTugasError("Hanya Admin Biro PAKLN yang dapat mengembalikan Surat Tugas.")
    _cek_bukan_milik_sendiri(aktor, pengajuan)
    catatan = _wajib(catatan, "Isi catatan alasan pengembalian Surat Tugas.")
    with transaction.atomic():
        p = _kunci_dan_cek(pengajuan, (SS.DIKIRIM,))
        if p.status != S.PROSES_PAKLN:
            raise SuratTugasError("Surat Tugas hanya dapat dikembalikan saat pengajuan berada di Biro PAKLN.")
        p.status_surat_tugas = SS.DIKEMBALIKAN
        p.catatan_surat_tugas = catatan
        p.save(update_fields=["status_surat_tugas", "catatan_surat_tugas", "updated_at"])
        riwayat.catat(p, Aksi.SURAT_TUGAS_DIKEMBALIKAN, aktor, p.status, catatan=catatan)
    notif.notify_surat_tugas_dikembalikan(p, catatan)
    return p


# ---------------------------------------------------------------------------
# Tampilan: penanda dasbor dan keterangan Timeline Proses
# ---------------------------------------------------------------------------

# Penanda singkat pada tabel dasbor — hanya untuk keadaan yang menahan proses (menunggu atau dikembalikan).
LABEL_PENANDA = {
    SS.MENUNGGU: "Menunggu Surat Tugas",
    SS.DIKEMBALIKAN: "Surat Tugas dikembalikan",
}


def penanda_dasbor(pengajuan):
    """(label, status) penanda jalur Surat Tugas untuk tabel dasbor, atau (None, None) bila tidak perlu."""
    if (pengajuan.track_surat_tugas_terbuka and pengajuan.status in STATUS_JALUR_AKTIF
            and pengajuan.status_surat_tugas in LABEL_PENANDA):
        return LABEL_PENANDA[pengajuan.status_surat_tugas], pengajuan.status_surat_tugas
    return None, None


def keterangan_timeline(pengajuan):
    """(teks, tone) sub-keterangan jalur Surat Tugas pada Timeline Proses, atau (None, None) bila jalur belum
    dibuka. Catatan pengembalian sengaja tidak dimuat di sini (timeline juga dilihat Pegawai)."""
    if not pengajuan.track_surat_tugas_terbuka:
        return None, None
    awal = "Surat Tugas Pimpinan Unor (Admin Unor): "
    if pengajuan.status_surat_tugas == SS.DIKEMBALIKAN:
        return awal + "Dikembalikan Biro PAKLN, menunggu perbaikan", "warning"
    if pengajuan.status_surat_tugas == SS.DIKIRIM:
        dikirim = pengajuan.riwayat.filter(aksi=Aksi.SURAT_TUGAS_DIKIRIM).order_by("-created_at").first()
        tgl = f" ({date_format(timezone.localtime(dikirim.created_at), 'd M Y')})" if dikirim else ""
        return awal + f"Dikirim ke Biro PAKLN{tgl}", "success"
    return awal + "Menunggu diunggah dan dikirim", "info"
