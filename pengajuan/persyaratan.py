"""
Registri persyaratan dokumen per (jenis/tipe, tahap) — satu sumber
kebenaran untuk halaman unggah, pratinjau, dan validasi tombol
Kirim/Teruskan/Selesai. Lihat wiki/instructions/BISNIS_PROSES_PDLN.MD §6.

Tahap: "pegawai", "unor", "bpsdm", "pakln". Kunci tipe: "nondinas" atau
kode tipe PDLN ("T1", "T2P", "T2L", "T3").
"""

from dataclasses import dataclass, field
from typing import Callable, Union

from .models import DokumenBpsdm, DokumenPakln, DokumenPegawai, DokumenUnor

TAHAP_MODEL = {
    "pegawai": DokumenPegawai,
    "unor": DokumenUnor,
    "bpsdm": DokumenBpsdm,
    "pakln": DokumenPakln,
}

TAHAP_RELATED = {
    "pegawai": "dokumen_pegawai",
    "unor": "dokumen_unor",
    "bpsdm": "dokumen_bpsdm",
    "pakln": "dokumen_pakln",
}

TAHAP_LABEL = {
    "pegawai": "Pegawai",
    "unor": "Admin Unor",
    "bpsdm": "Admin BPSDM",
    "pakln": "Admin Biro PAKLN",
}


@dataclass(frozen=True)
class Syarat:
    jenis: str
    label: str = ""
    # bool, atau callable(pengajuan) -> bool untuk syarat kondisional (visa).
    wajib: Union[bool, Callable] = True
    # Minta "Tanggal Surat" lewat modal sebelum berkas diunggah.
    tanggal_surat: bool = False
    # None / "format" (template tersedia) / "generate" (akan dibuat sistem).
    aksi: str = None
    keterangan: str = field(default="")

    def is_wajib(self, pengajuan):
        return self.wajib(pengajuan) if callable(self.wajib) else bool(self.wajib)


def _perlu_visa(pengajuan):
    return pengajuan.perlu_visa


_PEGAWAI_T1 = [
    Syarat("undangan"),
    Syarat("kak"),
    Syarat("rab"),
    Syarat("itinerary"),
    Syarat("notadinas", "Nota Dinas Pimpinan Unit Kerja ke Sekretaris Unor", tanggal_surat=True),
]

_PAKLN_PDLN = [
    Syarat("sp_setneg", aksi="generate"),
    Syarat("paspor_dinas"),
    Syarat("exit_permit"),
    Syarat("visa", wajib=_perlu_visa,
           keterangan="Wajib bila salah satu negara tujuan memerlukan visa; opsional bila tidak."),
    Syarat("nd_karo_unor", tanggal_surat=True, aksi="generate"),
]

PERSYARATAN = {
    # --- Non-Kedinasan (alur yang sudah berjalan) ---------------------
    ("nondinas", "pegawai"): [
        Syarat("cuti", tanggal_surat=True),
        Syarat("iln"),
        Syarat("notadinas", tanggal_surat=True),
        Syarat("pendukung"),
    ],
    ("nondinas", "unor"): [
        Syarat("disposisi", tanggal_surat=True),
        Syarat("iln_pimpinan"),
        Syarat("nd_biropakln", tanggal_surat=True),
    ],
    ("nondinas", "pakln"): [
        Syarat("iln_sekjen", tanggal_surat=True),
    ],

    # --- PDLN Tipe 1 --------------------------------------------------
    ("T1", "pegawai"): _PEGAWAI_T1,
    ("T1", "unor"): [
        Syarat("izin_prinsip", "Izin Prinsip Menteri"),
        Syarat("surat_tugas", "Surat Tugas", tanggal_surat=True, aksi="format"),
        Syarat("nd_kabiro_pakln", tanggal_surat=True, aksi="format"),
    ],
    ("T1", "pakln"): _PAKLN_PDLN,

    # --- PDLN Tipe 3 (alur sama dengan Tipe 1) -------------------------
    ("T3", "pegawai"): _PEGAWAI_T1,
    ("T3", "unor"): [
        Syarat("izin_prinsip", "Izin Prinsip/Disposisi Menteri"),
        Syarat("surat_tugas", "Surat Tugas", tanggal_surat=True, aksi="format"),
        Syarat("nd_kabiro_pakln", tanggal_surat=True, aksi="format"),
    ],
    ("T3", "pakln"): _PAKLN_PDLN,

    # --- PDLN Tipe 2 — Pendidikan ---------------------------------------
    ("T2P", "pegawai"): [
        Syarat("loa"),
        Syarat("log"),
        Syarat("surat_pernyataan"),
        Syarat("drh"),
        Syarat("ikatan_dinas"),
        Syarat("notadinas", "Nota Dinas Pimpinan Unit Kerja ke Sekretaris Unor", tanggal_surat=True),
    ],
    ("T2P", "unor"): [
        Syarat("nd_sek_bpsdm", tanggal_surat=True, aksi="format"),
        Syarat("surat_tugas", "Surat Tugas Pimpinan Unor", tanggal_surat=True, aksi="format"),
        Syarat("drh_ttd"),
    ],
    ("T2P", "bpsdm"): [
        Syarat("izin_prinsip"),
        Syarat("ikatan_dinas_ttd", aksi="generate"),
        Syarat("nd_kabiro_pakln", tanggal_surat=True, aksi="format"),
    ],
    ("T2P", "pakln"): _PAKLN_PDLN[:4] + [
        Syarat("sk_tubel", aksi="generate"),
        _PAKLN_PDLN[4],
    ],

    # --- PDLN Tipe 2 — Pelatihan ----------------------------------------
    ("T2L", "pegawai"): [
        Syarat("loa"),
        Syarat("kak"),
        Syarat("surat_pernyataan"),
        Syarat("notadinas", "Nota Dinas Pimpinan Unit Kerja ke Sekretaris Unor", tanggal_surat=True),
    ],
    ("T2L", "unor"): [
        Syarat("nd_sek_bpsdm", tanggal_surat=True, aksi="format"),
        Syarat("surat_tugas", "Surat Tugas Pimpinan Unor", tanggal_surat=True, aksi="format"),
    ],
    ("T2L", "bpsdm"): [
        Syarat("izin_prinsip"),
        Syarat("nd_kabiro_pakln", tanggal_surat=True, aksi="format"),
    ],
    ("T2L", "pakln"): _PAKLN_PDLN,
}


def daftar_syarat(pengajuan, tahap):
    return PERSYARATAN.get((pengajuan.kunci_alur, tahap), [])


def dokumen_map(pengajuan, tahap):
    return {d.jenis: d for d in getattr(pengajuan, TAHAP_RELATED[tahap]).all()}


def syarat_untuk(pengajuan, tahap, dok_map=None):
    """Daftar baris siap tampil: dict {jenis, label, wajib, tanggal_surat,
    aksi, keterangan, dok}."""
    model = TAHAP_MODEL[tahap]
    labels = dict(model.Jenis.choices)
    if dok_map is None:
        dok_map = dokumen_map(pengajuan, tahap)
    baris = []
    for s in daftar_syarat(pengajuan, tahap):
        wajib = s.is_wajib(pengajuan)
        keterangan = s.keterangan
        if s.jenis == "visa":
            keterangan = (
                f"Wajib — {pengajuan.negara_perlu_visa} memerlukan visa." if wajib
                else "Opsional — negara tujuan tidak memerlukan visa."
            )
        baris.append({
            "jenis": s.jenis,
            "label": s.label or labels.get(s.jenis, s.jenis),
            "wajib": wajib,
            "tanggal_surat": s.tanggal_surat,
            "aksi": s.aksi,
            "keterangan": keterangan,
            "dok": dok_map.get(s.jenis),
        })
    return baris


def dokumen_kurang(pengajuan, tahap, dok_map=None):
    """Label dokumen wajib yang belum diunggah."""
    return [b["label"] for b in syarat_untuk(pengajuan, tahap, dok_map) if b["wajib"] and not b["dok"]]


def dokumen_lengkap(pengajuan, tahap, dok_map=None):
    return not dokumen_kurang(pengajuan, tahap, dok_map)


def jenis_valid(pengajuan, tahap, jenis):
    return any(s.jenis == jenis for s in daftar_syarat(pengajuan, tahap))


def jenis_perlu_tanggal_surat(pengajuan, tahap, jenis):
    return any(s.jenis == jenis and s.tanggal_surat for s in daftar_syarat(pengajuan, tahap))


def tahap_untuk_role(role):
    return {"pegawai": "pegawai", "admin_unor": "unor", "admin_bpsdm": "bpsdm", "admin_pakln": "pakln"}[role]


def direktori(pengajuan, sampai_tahap):
    """Dokumen yang sudah diunggah tahap-tahap sebelum `sampai_tahap`
    (untuk halaman Pratinjau), dikelompokkan per tahap."""
    urutan = ["pegawai", "unor", "bpsdm", "pakln"]
    hasil = []
    for tahap in urutan[:urutan.index(sampai_tahap)]:
        if tahap == "bpsdm" and not pengajuan.is_tipe2:
            continue
        model = TAHAP_MODEL[tahap]
        labels = dict(model.Jenis.choices)
        overrides = {s.jenis: s.label for s in daftar_syarat(pengajuan, tahap) if s.label}
        dokumen = [
            {"label": overrides.get(d.jenis) or labels.get(d.jenis, d.jenis), "dok": d}
            for d in getattr(pengajuan, TAHAP_RELATED[tahap]).all()
        ]
        hasil.append({"tahap": tahap, "label": TAHAP_LABEL[tahap], "dokumen": dokumen})
    return hasil
