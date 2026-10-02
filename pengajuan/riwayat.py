"""
Riwayat Pemrosesan Pengajuan — satu pintu untuk menulis & membaca
`RiwayatPengajuan`, lihat wiki/instructions/RIWAYAT_PEMROSESAN_PENGAJUAN.MD.

Catatan berjalan dua arah pada dua jalur (§3):
  - Pegawai <-> Admin Unor        : dikembalikan_unor, dikirim_ulang
  - Admin Unor <-> Admin Biro PAKLN : dikembalikan_pakln, diteruskan_ulang

Aturan visibilitas pesan:
  - Pegawai     : hanya pesan pada jalur Pegawai <-> Admin Unor.
  - Admin Unor  : seluruh pesan (Unor ada di kedua jalur).
  - Admin PAKLN : seluruh pesan.

Penyaringan dilakukan di sini (server), sehingga pesan yang tidak berhak
tidak pernah sampai ke template.
"""

from accounts.models import User

from .models import Pengajuan, RiwayatPengajuan

Aksi = RiwayatPengajuan.Aksi

_LABEL_PERAN = {
    User.Role.PEGAWAI: "Pegawai",
    User.Role.ADMIN_UNOR: "Admin Unor",
    User.Role.ADMIN_PAKLN: "Biro PAKLN",
}

# Label khusus untuk pegawai: pengembalian PAKLN -> Unor tampil netral,
# tanpa pesan.
_LABEL_AKSI_PEGAWAI = {
    Aksi.DIKEMBALIKAN_PAKLN: "Dikembalikan ke Admin Unor untuk perbaikan",
}

# Aksi yang pesannya berada pada jalur Pegawai <-> Admin Unor.
_JALUR_PEGAWAI = {Aksi.DIKEMBALIKAN_UNOR, Aksi.DIKIRIM_ULANG}

_TONE = {
    Aksi.DIKEMBALIKAN_UNOR: "warning",
    Aksi.DIKEMBALIKAN_PAKLN: "warning",
    Aksi.SELESAI: "success",
}

_IKON = {
    Aksi.DIKIRIM: "↑",
    Aksi.DIKIRIM_ULANG: "↻",
    Aksi.DIKEMBALIKAN_UNOR: "↩",
    Aksi.DITERUSKAN_PAKLN: "→",
    Aksi.DIKEMBALIKAN_PAKLN: "↩",
    Aksi.DITERUSKAN_ULANG: "↻",
    Aksi.SELESAI: "✓",
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
    if user.role == User.Role.PEGAWAI:
        return riwayat.aksi in _JALUR_PEGAWAI
    return user.role in (User.Role.ADMIN_UNOR, User.Role.ADMIN_PAKLN)


def catatan_perbaikan(pengajuan, aksi):
    """Catatan balasan penerima pengembalian (`dikirim_ulang` /
    `diteruskan_ulang`) bila itu peristiwa terakhir — untuk banner di
    halaman pihak yang mengembalikan. Kosong bila tidak ada."""
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


def riwayat_untuk(pengajuan, user):
    """Daftar riwayat siap tampil untuk `user`: pesan yang tidak berhak
    sudah dikosongkan, label & nama aktor sudah disesuaikan peran."""
    hasil = []
    for r in pengajuan.riwayat.all():
        label = r.get_aksi_display()
        if user.role == User.Role.PEGAWAI:
            label = _LABEL_AKSI_PEGAWAI.get(r.aksi, label)
        hasil.append({
            "aksi": r.aksi,
            "status_dari": r.status_dari,
            "label": label,
            "aktor": _label_aktor(user, r),
            "waktu": r.created_at,
            "catatan": r.catatan if boleh_lihat_pesan(user, r) else "",
            "tone": _TONE.get(r.aksi, "info"),
            "ikon": _IKON.get(r.aksi, "•"),
        })
    return hasil


def timeline_dengan_riwayat(pengajuan, user):
    """Timeline Proses yang digabung dengan Riwayat Pemrosesan:
    setiap entri riwayat ditempel ke tahap tempat aksi itu terjadi
    (`status_dari`), urut kronologis."""
    urutan = [
        Pengajuan.Status.BELUM,
        Pengajuan.Status.PROSES,
        Pengajuan.Status.PROSES_PAKLN,
        Pengajuan.Status.SELESAI,
    ]
    langkah = [dict(step, riwayat=[]) for step in pengajuan.timeline]
    for entri in riwayat_untuk(pengajuan, user):
        idx = urutan.index(entri["status_dari"]) if entri["status_dari"] in urutan else 0
        langkah[idx]["riwayat"].append(entri)
    return langkah


def konteks(pengajuan, user):
    """Context template untuk partial `partials/_riwayat_pengajuan.html`."""
    return {"timeline": timeline_dengan_riwayat(pengajuan, user)}
