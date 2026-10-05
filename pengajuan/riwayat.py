"""
Riwayat Pemrosesan Pengajuan — satu pintu untuk menulis & membaca
`RiwayatPengajuan`, lihat wiki/instructions/RIWAYAT_PEMROSESAN_PENGAJUAN.MD
dan wiki/instructions/BISNIS_PROSES_PDLN.MD §7.

Catatan berjalan dua arah pada beberapa jalur:
  - Pegawai <-> Admin Unor          : dikembalikan_unor, dikirim_ulang
  - Admin Unor <-> Admin BPSDM      : dikembalikan_bpsdm, diteruskan_ulang_bpsdm
  - Admin Unor/BPSDM <-> Biro PAKLN : dikembalikan_pakln, diteruskan_ulang

Aturan visibilitas pesan:
  - Pegawai : pesan jalur Pegawai <-> Admin Unor, serta pesan pelaporan
              PDLN & pembatalan (menyangkut perjalanannya sendiri).
  - Admin   : seluruh pesan (Unor, BPSDM, PAKLN).

Penyaringan dilakukan di sini (server), sehingga pesan yang tidak berhak
tidak pernah sampai ke template.
"""

from accounts.models import User

from .models import Pengajuan, RiwayatPengajuan

Aksi = RiwayatPengajuan.Aksi
S = Pengajuan.Status

_LABEL_PERAN = {
    User.Role.PEGAWAI: "Pegawai",
    User.Role.ADMIN_UNOR: "Admin Unor",
    User.Role.ADMIN_BPSDM: "Admin BPSDM",
    User.Role.ADMIN_PAKLN: "Biro PAKLN",
}

# Aksi yang pesannya berada pada jalur Pegawai <-> Admin Unor.
_JALUR_PEGAWAI = {Aksi.DIKEMBALIKAN_UNOR, Aksi.DIKIRIM_ULANG}

# Aksi yang pesannya boleh dibaca semua pihak (termasuk Pegawai).
_TERBUKA_SEMUA = {
    Aksi.LAPORAN_DIUNGGAH, Aksi.LAPORAN_DIKEMBALIKAN, Aksi.LAPORAN_DISETUJUI,
    Aksi.PEMBATALAN_DIAJUKAN, Aksi.PEMBATALAN_DITARIK, Aksi.PEMBATALAN_DISETUJUI_UNOR,
    Aksi.PEMBATALAN_DITOLAK_UNOR, Aksi.PEMBATALAN_DITOLAK_PAKLN, Aksi.DIBATALKAN,
}

_ROLE_ADMIN = {User.Role.ADMIN_UNOR, User.Role.ADMIN_BPSDM, User.Role.ADMIN_PAKLN}

_TONE = {
    Aksi.DIKEMBALIKAN_UNOR: "warning",
    Aksi.DIKEMBALIKAN_BPSDM: "warning",
    Aksi.DIKEMBALIKAN_PAKLN: "warning",
    Aksi.SELESAI: "success",
    Aksi.LAPORAN_DIKEMBALIKAN: "warning",
    Aksi.LAPORAN_DISETUJUI: "success",
    Aksi.PEMBATALAN_DIAJUKAN: "warning",
    Aksi.PEMBATALAN_DISETUJUI_UNOR: "warning",
    Aksi.DIBATALKAN: "danger",
}

_IKON = {
    Aksi.DIKIRIM: "↑",
    Aksi.DIKIRIM_ULANG: "↻",
    Aksi.DIKEMBALIKAN_UNOR: "↩",
    Aksi.DITERUSKAN_PAKLN: "→",
    Aksi.DITERUSKAN_BPSDM: "→",
    Aksi.DIKEMBALIKAN_BPSDM: "↩",
    Aksi.DIKEMBALIKAN_PAKLN: "↩",
    Aksi.DITERUSKAN_ULANG: "↻",
    Aksi.DITERUSKAN_ULANG_BPSDM: "↻",
    Aksi.SELESAI: "✓",
    Aksi.LAPORAN_DIUNGGAH: "↑",
    Aksi.LAPORAN_DIKEMBALIKAN: "↩",
    Aksi.LAPORAN_DISETUJUI: "✓",
    Aksi.PEMBATALAN_DIAJUKAN: "✕",
    Aksi.PEMBATALAN_DITARIK: "↶",
    Aksi.PEMBATALAN_DISETUJUI_UNOR: "✓",
    Aksi.PEMBATALAN_DITOLAK_UNOR: "↩",
    Aksi.PEMBATALAN_DITOLAK_PAKLN: "↩",
    Aksi.DIBATALKAN: "✕",
}


def _nama_aktor(user):
    profile = getattr(user, "profile", None)
    if profile and profile.nama:
        return profile.nama
    return user.get_full_name() or user.username


def catat(pengajuan, aksi, aktor, status_dari, catatan=""):
    """Tambah satu baris riwayat. `status_ke` diambil dari
    `pengajuan.status` — panggil SETELAH status diubah, di dalam
    `transaction.atomic()` yang sama dengan `pengajuan.save()`."""
    return RiwayatPengajuan.objects.create(
        pengajuan=pengajuan,
        aksi=aksi,
        status_dari=status_dari,
        status_ke=pengajuan.status,
        aktor=aktor,
        aktor_role=aktor.role,
        aktor_nama=_nama_aktor(aktor)[:150],
        catatan=catatan,
    )


def boleh_lihat_pesan(user, riwayat):
    if riwayat.aksi in _TERBUKA_SEMUA:
        return True
    if user.role == User.Role.PEGAWAI:
        return riwayat.aksi in _JALUR_PEGAWAI
    return user.role in _ROLE_ADMIN


def catatan_perbaikan(pengajuan, aksi):
    """Catatan balasan penerima pengembalian (`dikirim_ulang` /
    `diteruskan_ulang` / `diteruskan_ulang_bpsdm`) bila itu peristiwa
    terakhir — untuk banner di halaman pihak yang mengembalikan."""
    terakhir = pengajuan.riwayat.last()
    if terakhir and terakhir.aksi == aksi:
        return terakhir.catatan
    return ""


def _label_aktor(user, riwayat):
    peran = _LABEL_PERAN.get(riwayat.aktor_role, riwayat.aktor_role)
    if user.role == User.Role.PEGAWAI:
        # Pegawai tidak melihat nama pribadi admin.
        return "Anda" if riwayat.aktor_role == User.Role.PEGAWAI else peran
    return f"{riwayat.aktor_nama} ({peran})"


def _label_aksi(user, r):
    """Label aksi; pengembalian antar-admin tampil netral bagi pegawai dan
    menyebut tujuan sebenarnya (Unor / BPSDM)."""
    if r.aksi == Aksi.DIKEMBALIKAN_PAKLN:
        tujuan = "Admin BPSDM" if r.status_ke == S.PROSES_BPSDM else "Admin Unor"
        if user.role == User.Role.PEGAWAI:
            return f"Dikembalikan ke {tujuan} untuk perbaikan"
        return f"Dikembalikan Biro PAKLN ke {tujuan}"
    if r.aksi == Aksi.DIKEMBALIKAN_BPSDM and user.role == User.Role.PEGAWAI:
        return "Dikembalikan ke Admin Unor untuk perbaikan"
    if r.aksi == Aksi.DITERUSKAN_PAKLN and r.aktor_role == User.Role.ADMIN_BPSDM:
        return "Diteruskan BPSDM ke Biro PAKLN"
    return r.get_aksi_display()


def riwayat_untuk(pengajuan, user):
    """Daftar riwayat siap tampil untuk `user`: pesan yang tidak berhak
    sudah dikosongkan, label & nama aktor sudah disesuaikan peran."""
    hasil = []
    for r in pengajuan.riwayat.all():
        hasil.append({
            "aksi": r.aksi,
            "status_dari": r.status_dari,
            "label": _label_aksi(user, r),
            "aktor": _label_aktor(user, r),
            "waktu": r.created_at,
            "catatan": r.catatan if boleh_lihat_pesan(user, r) else "",
            "tone": _TONE.get(r.aksi, "info"),
            "ikon": _IKON.get(r.aksi, "•"),
        })
    return hasil


def timeline_dengan_riwayat(pengajuan, user):
    """Timeline Proses yang digabung dengan Riwayat Pemrosesan: setiap
    entri riwayat ditempel ke tahap tempat aksi itu terjadi
    (`status_dari`), urut kronologis. Tahap mengikuti alur tipe
    pengajuan (`alur.timeline`)."""
    langkah = [dict(step, riwayat=[]) for step in pengajuan.timeline]
    posisi = {step["status"]: i for i, step in enumerate(langkah)}
    for entri in riwayat_untuk(pengajuan, user):
        idx = posisi.get(entri["status_dari"], 0)
        langkah[idx]["riwayat"].append(entri)
    return langkah


def konteks(pengajuan, user):
    """Context template untuk partial `partials/_riwayat_pengajuan.html`."""
    return {"timeline": timeline_dengan_riwayat(pengajuan, user)}
