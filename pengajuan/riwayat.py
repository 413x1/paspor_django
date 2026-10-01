"""
Riwayat Pemrosesan Pengajuan — satu pintu untuk menulis & membaca
`RiwayatPengajuan`, lihat wiki/instructions/RIWAYAT_PEMROSESAN_PENGAJUAN.MD.

Aturan visibilitas pesan (§3):
  - Setiap peran selalu melihat pesan yang ditulis perannya sendiri.
  - Pegawai     : + pesan dari Admin Unor.
  - Admin Unor  : + pesan dari Admin Biro PAKLN.
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
    if user.role == User.Role.ADMIN_PAKLN or riwayat.aktor_role == user.role:
        return True
    if user.role == User.Role.PEGAWAI:
        return riwayat.aktor_role == User.Role.ADMIN_UNOR
    if user.role == User.Role.ADMIN_UNOR:
        return riwayat.aktor_role == User.Role.ADMIN_PAKLN
    return False


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
            "label": label,
            "aktor": _label_aktor(user, r),
            "waktu": r.created_at,
            "catatan": r.catatan if boleh_lihat_pesan(user, r) else "",
            "tone": _TONE.get(r.aksi, "info"),
            "ikon": _IKON.get(r.aksi, "•"),
        })
    return hasil


def peta_alur(pengajuan):
    """4 simpul tahap + jumlah pengembalian per jalur balik (§6a)."""
    urutan = [
        (Pengajuan.Status.BELUM, "Pegawai"),
        (Pengajuan.Status.PROSES, "Admin Unor"),
        (Pengajuan.Status.PROSES_PAKLN, "Biro PAKLN"),
        (Pengajuan.Status.SELESAI, "Selesai"),
    ]
    status_list = [s for s, _ in urutan]
    idx = status_list.index(pengajuan.status) if pengajuan.status in status_list else 0
    selesai = pengajuan.status == Pengajuan.Status.SELESAI

    simpul = []
    for i, (_, judul) in enumerate(urutan):
        if i < idx or (selesai and i == idx):
            state = "done"
        elif i == idx:
            state = "current"
        else:
            state = "upcoming"
        simpul.append({"judul": judul, "state": state})

    aksi_list = [r.aksi for r in pengajuan.riwayat.all()]
    return {
        "simpul": simpul,
        "kembali_ke_pegawai": aksi_list.count(Aksi.DIKEMBALIKAN_UNOR),
        "kembali_ke_unor": aksi_list.count(Aksi.DIKEMBALIKAN_PAKLN),
    }


def konteks(pengajuan, user):
    """Context template untuk partial `partials/_riwayat_pengajuan.html`."""
    return {
        "riwayat": riwayat_untuk(pengajuan, user),
        "peta_alur": peta_alur(pengajuan),
    }
