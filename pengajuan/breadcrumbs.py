"""
Breadcrumb navigasi untuk semua halaman yang memakai `base.html`.

Setiap halaman didaftarkan di `CRUMBS` sebagai
`view_name -> (label, view_name induk)`. Jejak dibangun dengan menelusuri
induk sampai ke halaman awal role (Beranda/Dasbor). Label boleh memuat
placeholder kwargs URL, mis. `{kode}`. Induk berawalan `grup:` adalah grup
menu sidebar (tanpa tautan).
"""

from django.urls import NoReverseMatch, reverse

from accounts.models import User

# Halaman awal per role — selalu menjadi crumb pertama.
ROOT = {
    User.Role.PEGAWAI: "pegawai:beranda",
    User.Role.ADMIN_UNOR: "unor:dashboard",
    User.Role.ADMIN_BPSDM: "bpsdm:dashboard",
    User.Role.ADMIN_PAKLN: "pakln:dashboard",
}

CRUMBS = {
    # --- Bersama -----------------------------------------------------------
    "profil": ("Profil", None),
    "notifications:list": ("Notifikasi", None),

    # --- Pegawai -----------------------------------------------------------
    "pegawai:beranda": ("Beranda", None),
    "pegawai:formulir_pengajuan": ("Formulir Pengajuan", "pegawai:beranda"),
    "pegawai:upload_dokumen": ("Unggah Dokumen {kode}", "pegawai:beranda"),
    "pegawai:monitor_progres": ("Monitor Progres {kode}", "pegawai:beranda"),
    "pegawai:pelaporan": ("Pelaporan PDLN", "pegawai:beranda"),
    "pegawai:unggah_laporan": ("Laporan {kode}", "pegawai:pelaporan"),
    "pegawai:pembatalan": ("Pembatalan", "pegawai:beranda"),
    "pegawai:ajukan_pembatalan": ("Ajukan Pembatalan {kode}", "pegawai:pembatalan"),

    # --- Admin Unor --------------------------------------------------------
    "unor:dashboard": ("Dasbor", None),
    "unor:preview": ("Pratinjau {kode}", "unor:dashboard"),
    "unor:upload_dokumen": ("Administrasi Unor", "unor:preview"),
    "unor:ajukan_pembatalan": ("Ajukan Pembatalan {kode}", "unor:pembatalan"),
    "unor:pembatalan": ("Pembatalan", "unor:dashboard"),
    "unor:putuskan_pembatalan": ("Putuskan Pembatalan", "unor:pembatalan"),
    "unor:pelaporan": ("Pelaporan PDLN", "unor:dashboard"),
    "unor:rekap": ("Rekap", "unor:dashboard"),
    "unor:export": ("Export", "unor:dashboard"),

    # --- Admin BPSDM -------------------------------------------------------
    "bpsdm:dashboard": ("Dasbor", None),
    "bpsdm:preview": ("Pratinjau {kode}", "bpsdm:dashboard"),
    "bpsdm:upload_dokumen": ("Administrasi BPSDM", "bpsdm:preview"),
    "bpsdm:pembatalan": ("Pembatalan", "bpsdm:dashboard"),
    "bpsdm:rekap": ("Rekap", "bpsdm:dashboard"),
    "bpsdm:export": ("Export", "bpsdm:dashboard"),

    # --- Admin Biro PAKLN --------------------------------------------------
    "pakln:dashboard": ("Dasbor", None),
    "pakln:preview": ("Pratinjau {kode}", "pakln:dashboard"),
    "pakln:upload_dokumen": ("Administrasi Biro PAKLN", "pakln:preview"),
    "pakln:generate_nd_kabag": ("Generate ND Kabag", "pakln:dashboard"),
    "pakln:generate_nd_karo": ("Generate ND Karo", "pakln:dashboard"),
    "pakln:pelaporan": ("Pelaporan PDLN", "pakln:dashboard"),
    "pakln:verifikasi_laporan": ("Verifikasi Laporan {kode}", "pakln:pelaporan"),
    "pakln:pembatalan": ("Pembatalan", "pakln:dashboard"),
    "pakln:putuskan_pembatalan": ("Putuskan Pembatalan", "pakln:pembatalan"),
    "pakln:rekap": ("Rekap", "pakln:dashboard"),
    "pakln:export": ("Export", "pakln:dashboard"),
    "pakln:pengaturan_dokumen": ("Setting", "pakln:dashboard"),
    "grup:manajemen": ("Manajemen", "pakln:dashboard"),
    "pakln:kelola_user": ("Manajemen User", "grup:manajemen"),
    "pakln:edit_user": ("Edit User", "pakln:kelola_user"),
    "pakln:kelola_template": ("Manajemen Template", "grup:manajemen"),
    "pakln:edit_template": ("Edit Template", "pakln:kelola_template"),
    "pakln:kelola_negara": ("Manajemen Negara", "grup:manajemen"),
    "pakln:edit_negara": ("Edit Negara", "pakln:kelola_negara"),
    "pakln:kelola_sumber_pembiayaan": ("Sumber Pembiayaan", "grup:manajemen"),
    "pakln:edit_sumber_pembiayaan": ("Edit Sumber Pembiayaan", "pakln:kelola_sumber_pembiayaan"),
    "pakln:kelola_kategori": ("Kategori Perjalanan", "grup:manajemen"),
    "pakln:edit_kategori": ("Edit Kategori Perjalanan", "pakln:kelola_kategori"),
    "pakln:kelola_kalender": ("Setting Kalender", "grup:manajemen"),
    "pakln:edit_hari_libur": ("Edit Hari Libur", "pakln:kelola_kalender"),
    "pakln:histori_generate": ("Histori Generate Dokumen", "grup:manajemen"),
}


class _Kwargs(dict):
    """Placeholder yang tidak ada di kwargs URL dibiarkan kosong."""

    def __missing__(self, key):
        return ""


def _url(view_name, kwargs):
    if view_name.startswith("grup:"):
        return None
    try:
        return reverse(view_name)
    except NoReverseMatch:
        pass
    # Induk berparameter (mis. pratinjau `<kode>`) memakai kwargs halaman ini.
    if "kode" in kwargs:
        try:
            return reverse(view_name, kwargs={"kode": kwargs["kode"]})
        except NoReverseMatch:
            pass
    return None


def build(request):
    """Daftar crumb `[{"label", "url"}]`; kosong bila halaman tak terdaftar
    atau halaman tersebut adalah halaman awal role."""
    match = request.resolver_match
    user = request.user
    if not match or match.view_name not in CRUMBS:
        return []

    trail, current = [], match.view_name
    while current and current not in trail:
        trail.append(current)
        current = CRUMBS[current][1]
    root = ROOT.get(user.role)
    if root and trail[-1] != root:
        trail.append(root)
    trail.reverse()
    if len(trail) < 2:
        return []

    kwargs = _Kwargs(match.kwargs)
    items = [
        {"label": CRUMBS[name][0].format_map(kwargs).strip(), "url": _url(name, match.kwargs)}
        for name in trail
    ]
    items[-1]["url"] = None
    return items
